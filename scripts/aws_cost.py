"""AWS cost check against the $200 credit: what we've been billed, whether the bot's ledger agrees, and where we
land by 2 Nov. Read-only (Cost Explorer, CloudWatch, EC2 describe calls); runs on a laptop with the `aws` CLI and
the IAM key in .env (EC2_ACCESS_KEY / EC2_SECRET_ACCESS_KEY, never printed). Cost Explorer lags 12-24 h and its
newest day is partial, so read the totals, not single days. Writes data/aws_cost.json (the dashboard can read it).

    python scripts/aws_cost.py                   # report; the bot's ledger is read from data/llm_spend.json
    python scripts/aws_cost.py --ssh swan-ec2    # read the live ledger off the box instead (read-only cat)
    python scripts/aws_cost.py --dry             # report only, no file
    python scripts/aws_cost.py --json            # the JSON instead of the report

Calls that the IAM user isn't allowed to make (credit balance, Cost Explorer's own forecast, budgets) are listed
under "not permitted" and skipped: docs/04-technical/aws-cost.md says which permissions add them.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from swan_bot import config  # noqa: E402

OUT = config.DATA / "aws_cost.json"
INSTANCE = "i-06471b75b0166b3c7"
CE_REGION, REGION = "us-east-1", "ap-southeast-2"
CREDIT_USD = float(os.environ.get("AWS_CREDIT_USD", 200))   # the plan upgrade of 23 Oct
FIRST_DAY = "2026-10-20"                                    # the box went live
END_DAY = "2026-11-02"                                      # last Sydney day we write
LEDGER_FROM = "2026-10-22"                                  # the ledger charged nothing reliable on 21 Oct (1ef7895)
SYDNEY = ZoneInfo(config.LOCAL_TZ)
# Sydney on-demand list prices, Linux, USD/hour, checked against Cost Explorer on 23 Oct (t3.micro $0.32/day).
HOURLY = {"t3.micro": 0.0132, "t3.small": 0.0264, "t3.medium": 0.0528}
IPV4_DAY, EBS_DAY = 0.12, 0.027                             # one Elastic IP, one 8 GB gp3 volume
SURPLUS_USD_PER_CREDIT = 0.05 / 60                          # unlimited mode: $0.05 per vCPU-hour
MANTLE = re.compile(r"APS2-(?P<model>.+)-mantle-(?P<dir>input|output)-tokens-standard$")


class Denied(Exception):
    pass


def env_get(name):
    for line in (ROOT / ".env").read_text().splitlines():
        m = re.match(rf"\s*(?:export\s+)?{name}\s*=\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip("\r").strip("\"'")
    return ""


def aws(*args, region=REGION):
    env = {**os.environ, "AWS_ACCESS_KEY_ID": env_get("EC2_ACCESS_KEY"),
           "AWS_SECRET_ACCESS_KEY": env_get("EC2_SECRET_ACCESS_KEY"), "AWS_DEFAULT_REGION": region, "AWS_PAGER": ""}
    env.pop("AWS_PROFILE", None)
    p = subprocess.run(["aws", *args, "--output", "json"], env=env, capture_output=True, text=True, timeout=90)
    if p.returncode:
        if "AccessDenied" in p.stderr or "not authorized" in p.stderr:
            raise Denied(args[1] if len(args) > 1 else args[0])
        raise RuntimeError(f"aws {' '.join(args[:2])}: {p.stderr.strip()[:300]}")
    return json.loads(p.stdout) if p.stdout.strip() else {}


def ce(start, end, group, extra_filter=None, granularity="DAILY", metrics=("UnblendedCost",)):
    """{period start: {group key: {metric: float}}} for Usage records only (credits would net everything to 0)."""
    usage = {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Usage"]}}
    flt = {"And": [usage, extra_filter]} if extra_filter else usage
    r = aws("ce", "get-cost-and-usage", "--time-period", f"Start={start},End={end}", "--granularity", granularity,
            "--metrics", *metrics, "--filter", json.dumps(flt), "--group-by", f"Type=DIMENSION,Key={group}",
            region=CE_REGION)
    return {p["TimePeriod"]["Start"]: {g["Keys"][0]: {m: float(v["Amount"]) for m, v in g["Metrics"].items()}
                                       for g in p["Groups"]} for p in r["ResultsByTime"]}


def real_prices(tokens):
    """tokens = {usage type: {UnblendedCost, UsageQuantity (thousands of tokens)}} -> {model: {in, out, cost}} in USD
    per million tokens, as billed. Only the mantle (OpenAI-compatible) models: Claude's global lines mix models."""
    out = {}
    for ut, v in tokens.items():
        m = MANTLE.match(ut)
        if not m or not v["UsageQuantity"]:
            continue
        d = out.setdefault(m["model"], {"cost": 0.0, "tokens_k": {"input": 0.0, "output": 0.0}})
        d["cost"] += v["UnblendedCost"]
        d["tokens_k"][m["dir"]] += v["UsageQuantity"]
        d["in" if m["dir"] == "input" else "out"] = v["UnblendedCost"] / v["UsageQuantity"] * 1000
    return out


def padding_factor(prices):
    """Billed / what config.LLM_PRICES would have charged for the same tokens, over the priced models (about 0.82)."""
    real = padded = 0.0
    for model, d in prices.items():
        if model in config.LLM_PRICES:
            p_in, p_out = config.LLM_PRICES[model]
            real += d["cost"]
            padded += (d["tokens_k"]["input"] * p_in + d["tokens_k"]["output"] * p_out) / 1000
    return real / padded if padded else 0.82


def ec2_day(instance_type):
    return HOURLY.get(instance_type, HOURLY["t3.medium"]) * 24 + IPV4_DAY + EBS_DAY


def project(*, billed, ledger, today, instance_type, factor, unpriced_day, surplus):
    """Where the credit stands on END_DAY. billed = Cost Explorer gross so far; ledger = {Sydney day: ledger USD}.
    Two scenarios: 'pace' (the bot keeps its recent daily spend) and 'budget' (it spends all of LLM_BUDGET_USD).
    Cost Explorer lags up to a day, so today's ledger spend (x factor) is added on top of it: slightly pessimistic."""
    days_left = (dt.date.fromisoformat(END_DAY) - dt.date.fromisoformat(today)).days      # whole days after today
    done = [v for d, v in sorted(ledger.items()) if LEDGER_FROM <= d < today]
    rate = sum(done) / len(done) if done else ledger.get(today, 0.0)
    today_spent = ledger.get(today, 0.0)
    lag = factor * today_spent
    fixed = ec2_day(instance_type) * (days_left + 1) + unpriced_day * (days_left + 1)    # today's remaining day, rounded up
    pace = factor * (max(0.0, rate - today_spent) + rate * days_left)
    budget = factor * max(0.0, config.LLM_BUDGET_USD - sum(ledger.values()))
    base = billed + lag + fixed + surplus
    return {"days_left": days_left, "ledger_rate_per_day": rate, "factor": factor, "fixed_ec2_etc": fixed,
            "pace": {"total": base + pace, "headroom": CREDIT_USD - base - pace},
            "budget": {"total": base + budget, "headroom": CREDIT_USD - base - budget}}


def status(proj):
    """ok: even spending the whole LLM budget stays under 90% of the credit; watch: under 100%; over: above."""
    t = proj["budget"]["total"] / CREDIT_USD
    return "ok" if t <= 0.9 else "watch" if t <= 1.0 else "over"


def read_ledger(ssh):
    if ssh:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", ssh, "cat ~/ctn/data/llm_spend.json"],
                           capture_output=True, text=True, timeout=45)
        if p.returncode:
            raise RuntimeError(f"ssh {ssh}: {p.stderr.strip()[:200]}")
        return json.loads(p.stdout)
    path = config.DATA / "llm_spend.json"
    return json.loads(path.read_text()) if path.exists() else {}


def collect(ssh=None):
    now = dt.datetime.now(dt.timezone.utc)
    end = (now + dt.timedelta(days=1)).date().isoformat()
    today = now.astimezone(SYDNEY).date().isoformat()
    denied, unavailable = [], []

    def guarded(label, fn):
        try:
            return fn()
        except Denied as e:
            denied.append(f"{label} ({e})")
        except RuntimeError as e:                       # allowed but no answer (a new account has too little history to forecast)
            unavailable.append(f"{label}: {str(e).split(': ')[-1][:90]}")

    by_service = ce(FIRST_DAY, end, "SERVICE")
    tokens = ce(FIRST_DAY, end, "USAGE_TYPE", granularity="MONTHLY", metrics=("UnblendedCost", "UsageQuantity"))
    tokens = next(iter(tokens.values()), {})
    credits_applied = -sum(
        float(g["Metrics"]["UnblendedCost"]["Amount"])
        for p in aws("ce", "get-cost-and-usage", "--time-period", f"Start={FIRST_DAY},End={end}", "--granularity",
                     "MONTHLY", "--metrics", "UnblendedCost", "--filter",
                     json.dumps({"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit"]}}), "--group-by",
                     "Type=DIMENSION,Key=RECORD_TYPE", region=CE_REGION)["ResultsByTime"] for g in p["Groups"])
    billed = sum(c["UnblendedCost"] for day in by_service.values() for c in day.values())
    prices = real_prices(tokens)
    unpriced = sum(d["cost"] for m, d in prices.items() if m not in config.LLM_PRICES)

    inst = aws("ec2", "describe-instances", "--instance-ids", INSTANCE)["Reservations"][0]["Instances"][0]
    surplus_credits = aws("cloudwatch", "get-metric-statistics", "--namespace", "AWS/EC2", "--metric-name",
                          "CPUSurplusCreditsCharged", "--dimensions", f"Name=InstanceId,Value={INSTANCE}",
                          "--period", "86400", "--statistics", "Sum", "--start-time", f"{FIRST_DAY}T00:00:00Z",
                          "--end-time", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    surplus = sum(p["Sum"] for p in surplus_credits["Datapoints"]) * SURPLUS_USD_PER_CREDIT
    ledger = read_ledger(ssh)
    days_billed = max(1, len([d for d in by_service if by_service[d]]))
    proj = project(billed=billed, ledger=ledger, today=today, instance_type=inst["InstanceType"],
                   factor=padding_factor(prices), unpriced_day=unpriced / days_billed, surplus=surplus)

    plan = guarded("freetier:GetAccountPlanState", lambda: aws("freetier", "get-account-plan-state", region=CE_REGION))
    forecast = guarded("ce:GetCostForecast", lambda: aws(
        "ce", "get-cost-forecast", "--time-period", f"Start={end},End=2026-11-03",
        "--metric", "UNBLENDED_COST", "--granularity", "MONTHLY", "--filter",
        json.dumps({"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Usage"]}}), region=CE_REGION))
    budgets = guarded("budgets:ViewBudget", lambda: aws("budgets", "describe-budgets", "--account-id",
                                                          aws("sts", "get-caller-identity")["Account"], region=CE_REGION))
    return {
        "ts": now.isoformat(), "credit_usd": CREDIT_USD, "billed_gross": billed, "credits_applied": credits_applied,
        "billed_by_day": {d: {s[:40]: round(c["UnblendedCost"], 3) for s, c in v.items() if c["UnblendedCost"] >= 0.005}
                          for d, v in by_service.items()},
        "instance": {"type": inst["InstanceType"], "state": inst["State"]["Name"], "surplus_usd": surplus},
        "prices_per_m": {m: {"in": round(d.get("in", 0), 3), "out": round(d.get("out", 0), 3), "billed": round(d["cost"], 2),
                             "priced_in_config": m in config.LLM_PRICES} for m, d in prices.items() if d["cost"] >= 0.005},
        "unpriced_billed": unpriced, "ledger": ledger, "ledger_source": ssh or "local data/llm_spend.json",
        "projection": proj, "status": status(proj),
        "plan_state": plan, "aws_forecast": forecast, "budgets": None if budgets is None else budgets.get("Budgets", []),
        "not_permitted": denied, "unavailable": unavailable,
    }


def report(d):
    p = d["projection"]
    lines = [f"AWS cost vs ${d['credit_usd']:.0f} credit, {d['ts'][:16]}Z   status: {d['status'].upper()}",
             f"billed so far (gross, Cost Explorer; lags up to a day): ${d['billed_gross']:.2f}"
             f"   credits applied: ${d['credits_applied']:.2f}", "", "billed by day:"]
    for day, svc in d["billed_by_day"].items():
        if svc:
            lines.append(f"  {day}  ${sum(svc.values()):6.2f}  " + ", ".join(f"{k} {v:.2f}" for k, v in
                                                                              sorted(svc.items(), key=lambda x: -x[1])[:4]))
    lines += ["", f"bot ledger ({d['ledger_source']}): " + ", ".join(f"{k[5:]} ${v:.2f}" for k, v in sorted(d["ledger"].items())),
              f"billed/ledger-price factor {p['factor']:.2f} (config.LLM_PRICES are padded; 0.80 means billed is 20% under)",
              "real $/M tokens in/out: " + "; ".join(f"{m} {v['in']}/{v['out']}" + ("" if v["priced_in_config"] else " UNPRICED")
                                                     for m, v in d["prices_per_m"].items()),
              f"EC2 {d['instance']['type']} {d['instance']['state']}, unlimited-mode surplus billed ${d['instance']['surplus_usd']:.3f}",
              "", f"to {END_DAY}, {p['days_left']} days after today (ledger run rate ${p['ledger_rate_per_day']:.2f}/day):",
              f"  at the recent pace         ${p['pace']['total']:7.2f}   headroom ${p['pace']['headroom']:7.2f}",
              f"  spending all LLM_BUDGET    ${p['budget']['total']:7.2f}   headroom ${p['budget']['headroom']:7.2f}"
              f"   (LLM_BUDGET_USD {config.LLM_BUDGET_USD:.0f})"]
    if d["aws_forecast"]:
        lines.append(f"  AWS's own forecast         ${float(d['aws_forecast']['Total']['Amount']):7.2f}  (gross usage, to 3 Nov)")
    if d["plan_state"]:
        left = d["plan_state"].get("accountPlanRemainingCredits", {}).get("amount")
        lines.append(f"AWS says {d['plan_state'].get('accountPlanType')} plan {d['plan_state'].get('accountPlanStatus')}, "
                     f"credit remaining ${left}" + (f" (credit {d['credit_usd']:.0f} - billed {d['billed_gross']:.2f} = "
                                                    f"{d['credit_usd'] - d['billed_gross']:.2f})" if left is not None else ""))
    if d["budgets"] is not None:
        lines.append(f"AWS budgets set: {len(d['budgets'])}" + ("  <- none: no spend alert exists" if not d["budgets"] else ""))
    if d["not_permitted"]:
        lines.append("not permitted: " + ", ".join(d["not_permitted"]))
    if d.get("unavailable"):
        lines.append("allowed, but AWS had no answer: " + "; ".join(d["unavailable"]))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ssh", help="ssh host to read the live data/llm_spend.json from (e.g. swan-ec2)")
    ap.add_argument("--dry", action="store_true", help="print only; don't write data/aws_cost.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    d = collect(args.ssh)
    print(json.dumps(d, indent=1) if args.json else report(d))
    if not args.dry:
        OUT.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
