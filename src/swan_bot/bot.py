"""Operation Swan bot (Vote No). DRY-RUN BY DEFAULT: nothing is registered or posted without --live.

Every write slot goes to the most valuable job (docs/06-strategy/second-mover-plan.md):
  1. reply back to a citizen who replied to us
  2. second voice: a different persona and angle on a doubt we answered 10-30 min ago
  3. reply to an undecided citizen (mostly in the news threads), answering the doubt they voiced
  4. reply to a journalist's referendum post (at most one per 45 min)
  5. persona post, at most 1 in every 4 writes
If nothing is worth writing, it waits. Accounts are registered one at a time, 20-40 min apart.
"""
import argparse
import datetime as dt
import json
import os
import random
import secrets
import time

import openai
import capturethenarrative as ctn

from . import config, content, quality
from .llm import Generator
from .targeting import Targeter, classify


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def log(rec):
    config.LOGS.mkdir(exist_ok=True)
    with open(config.ACTIONS_LOG, "a") as f:
        f.write(json.dumps({"ts": now_iso(), **rec}) + "\n")


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj, private=False):
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    if private:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


class Accounts:
    """Registry of our accounts in secrets/swan_accounts.json (passwords, tokens, owner)."""

    def __init__(self, social, live):
        self.social, self.live = social, live
        self.records = load_json(config.ACCOUNTS_FILE, []) if live else []
        self.open = {}
        self.next_register = 0.0

    def save(self):
        if self.live:
            save_json(config.ACCOUNTS_FILE, self.records, private=True)

    def active(self):
        return [r for r in self.records if r.get("status", "active") == "active"]

    def maybe_register(self, k, code, owner):
        """Drip registration: at most one new account per call, 20-40 min apart, never more than MAX_ACCOUNTS."""
        if len(self.active()) >= k or len(self.records) >= config.MAX_ACCOUNTS or time.time() < self.next_register:
            return
        used = {r["persona"] for r in self.records}
        spare = [p for p in content.PERSONAS if p["key"] not in used]
        if not spare:
            return
        p = spare[0]
        self.next_register = time.time() + random.uniform(*config.REGISTER_GAP_S)
        if not self.live:
            self.records.append(dict(persona=p["key"], username=f"(dry){p['handle']}", account_id=None,
                                     status="active", last_write=0, writes=0))
            return
        username = f"{p['handle']}{random.randint(10, 99)}"[:32]
        password = secrets.token_urlsafe(18)
        acc = self.social.register(username, password, code, display_name=p["name"])
        rec = dict(persona=p["key"], username=username, password=password, token=acc.token,
                   account_id=acc.account_id, owner=owner, created=now_iso(), status="active",
                   last_write=0, writes=0, followed=[])
        self.records.append(rec)
        self.open[username] = acc
        self.save()
        log({"act": "register", "username": username, "account_id": acc.account_id, "persona": p["key"], "owner": owner})
        print(f"registered {username} (id {acc.account_id}) for {owner}; next in "
              f"{(self.next_register - time.time()) / 60:.0f} min")

    def session(self, rec):
        acc = self.open.get(rec["username"])
        if acc is None:
            acc = self.social.account_from_token(rec["token"])
            self.open[rec["username"]] = acc
        return acc

    def relogin(self, rec):
        acc = self.social.login(rec["username"], rec["password"])
        rec["token"] = acc.token
        self.open[rec["username"]] = acc
        self.save()
        return acc

    def eligible(self, frame=None, exclude=()):
        t = time.time()
        gap = config.ACCOUNT_MIN_GAP_S if self.live else 0      # dry runs rotate personas without waiting
        ready = [r for r in self.active() if r.get("last_write", 0) + gap <= t and r["persona"] not in exclude]
        if frame:
            fit = [r for r in ready if frame in content.PERSONA_BY_KEY[r["persona"]]["frames"]]
            ready = fit or ready
        return min(ready, key=lambda r: r.get("last_write", 0)) if ready else None

    def by_persona(self, key):
        return next((r for r in self.active() if r["persona"] == key), None)


def reply_back_jobs(social, accounts, targeter, limit=3):
    """Citizens who replied to our posts. Reads at most `limit` replies; only those are marked resolved."""
    jobs = []
    for rec in accounts.active():
        if len(jobs) >= limit:
            break
        try:
            acc = accounts.session(rec)
            for n in acc.notifications(unresolved=True, limit=10):
                if len(jobs) >= limit:
                    break
                try:
                    if n.get("kind") != "reply":
                        continue
                    theirs = social.get_post(n["post"]["post_id"])
                    if not targeter.is_citizen(theirs["author_id"]) or not theirs.get("reply_to_post_id"):
                        continue
                    ours = social.get_post(theirs["reply_to_post_id"])
                    jobs.append(dict(mode="reply_back", rec=rec, target=theirs, our_text=ours.get("body") or "", tries=0))
                finally:
                    acc.resolve_notification(n["notification_id"])
        except ctn.APIError as e:
            print("notifications:", rec["username"], e.status, e.message)
    return jobs


def build_prompt(job, targeter):
    persona = content.PERSONA_BY_KEY[job["rec"]["persona"]]
    target = job.get("target") or {}
    body = target.get("body") or ""
    mode = job["mode"]
    if mode == "post":
        user = content.post_prompt(job["frame"], targeter.headline if random.random() < 0.3 else None)
    elif mode == "reply":
        user = content.reply_prompt(body, job["frame"], job.get("wants"), job.get("context"))
    elif mode == "second_voice":
        user = content.second_voice_prompt(body, job["frame"], job.get("wants"), job.get("context"))
    elif mode == "journalist":
        user = content.journalist_prompt(target["author_id"], body)
    else:
        user = content.reply_back_prompt(job["our_text"], body)
    return persona, content.system_prompt(persona, job["frame"]), user


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="really register accounts and post (default: dry run)")
    ap.add_argument("--accounts", type=int, default=6, help=f"active accounts to grow to, one every 20-40 min (max {config.MAX_ACCOUNTS})")
    ap.add_argument("--hours", type=float, default=8)
    ap.add_argument("--per-min", type=float, default=1.0, help="max team writes per minute (hard max 2); real pace follows the target queue")
    ap.add_argument("--samples", type=int, default=0, help="dry run: stop after this many accepted drafts")
    ap.add_argument("--allow-qwen", action="store_true", help="fall back to the weak provided model when Gemini is out")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt for --live")
    args = ap.parse_args()

    config.load_env()
    config.assigned_side()
    code, owner = config.team_code(), config.operator()
    k = max(1, min(args.accounts, config.MAX_ACCOUNTS))
    per_min = max(0.1, min(args.per_min, 2.0))

    social = ctn.LegitSocial()
    gen = Generator(code, allow_qwen=args.allow_qwen)
    targeter = Targeter(social, log=log)
    accounts = Accounts(social, args.live)
    state = load_json(config.STATE_FILE, {})
    for key, default in (("replied_posts", []), ("contacted", {}), ("recent_texts", []), ("second_voice", []),
                         ("journalist_last", {}), ("modes", []), ("journalist_any", 0)):
        state.setdefault(key, default)

    if args.live:
        lock = social.feed_lock()
        if lock.get("locked"):
            raise SystemExit(f"feed is locked: {lock.get('reason')}")
        print(f"LIVE: Vote No | owner {owner} | {len(accounts.active())} active accounts, growing to {k} "
              f"(one every 20-40 min) | up to {per_min}/min for {args.hours} h | LLM: {gen.describe()}")
        if not args.yes and input("Type GO to continue: ").strip() != "GO":
            raise SystemExit("aborted")
    else:
        print(f"DRY RUN: nothing will be registered or posted. LLM: {gen.describe()}")
        accounts.next_register = 0.0

    def save_state():
        if args.live:
            save_json(config.STATE_FILE, state)

    end = time.time() + args.hours * 3600
    next_write = next_notif = 0.0
    queue, stats = [], {"accepted": 0, "rejected": {}, "by_mode": {}}

    while time.time() < end and not (args.samples and stats["accepted"] >= args.samples):
        job = None
        try:
            # dry runs register a fake account instantly so drafts can be read without waiting
            if args.live:
                accounts.maybe_register(k, code, owner)
            else:
                while len(accounts.active()) < k:
                    accounts.next_register = 0.0
                    accounts.maybe_register(k, code, owner)
            if not accounts.active():
                time.sleep(30)
                continue
            # No retirement by action count: accounts are lost through moderator-hidden posts, not actions
            # (scoring guide s3). Parking by hidden-post count is a TODO (TODO.md, "Hidden-post watch").
            our_ids = {r.get("account_id") for r in accounts.records if r.get("account_id")}
            targeter.refresh()
            if args.live and time.time() >= next_notif:
                queue += reply_back_jobs(social, accounts, targeter)
                next_notif = time.time() + 300

            wait = next_write - time.time()
            if wait > 0:
                time.sleep(min(wait, 30))
                continue
            if gen.next_available_in() > 0 and not args.allow_qwen:
                print(f"no Gemini model available; waiting {gen.next_available_in() / 60:.0f} min")
                time.sleep(min(gen.next_available_in() + 1, 600))
                continue

            # ---- choose the job (greedy order) ----
            t = time.time()
            contacted = {a: ts for a, ts in state["contacted"].items() if t - ts < config.CONTACT_COOLDOWN_S}
            if queue:
                job = queue.pop(0)
                job["frame"] = content.PERSONA_BY_KEY[job["rec"]["persona"]]["frames"][0]
                if job["rec"].get("last_write", 0) + 60 > t:      # don't double-post from one account
                    queue.insert(0, job)
                    job = None
            if job is None:
                state["second_voice"] = [s for s in state["second_voice"] if t - s["due"] < 3600]   # stale after 1 h
                due = [s for s in state["second_voice"] if s["due"] <= t]
                for sv in due:
                    rec = accounts.eligible(sv["frame"], exclude={sv["first_persona"]})
                    if not rec:
                        continue                                     # keep it until another persona is free
                    state["second_voice"].remove(sv)
                    try:
                        target = social.get_post(sv["post_id"])
                        thread = list(social.replies(sv["post_id"], limit=20))
                    except ctn.APIError:
                        continue
                    if len(thread) > 8 or any(r["author_id"] == target["author_id"] for r in thread):
                        continue                                     # busy thread, or they already answered us
                    job = dict(mode="second_voice", rec=rec, target=target, frame=sv["frame"],
                               wants=sv.get("wants"), context=sv.get("context"))
                    break
            if job is None:
                cand = targeter.next_target(our_ids, set(state["replied_posts"]), contacted)
                if cand:
                    rec = accounts.eligible(cand["frame"])
                    if rec:
                        job = dict(mode="reply", rec=rec, target=cand["post"], frame=cand["frame"],
                                   wants=cand["wants"], context=cand["context"], source=cand["source"])
                    else:
                        targeter.candidates[cand["post"]["post_id"]] = cand      # keep it for the next slot
            if job is None and t - state["journalist_any"] > config.JOURNALIST_GAP_S:
                jp = targeter.next_journalist(set(state["replied_posts"]), state["journalist_last"])
                if jp:
                    frame, _ = classify(jp.get("body") or "")
                    rec = accounts.eligible(frame or "F14_no_yes_but")
                    if rec:
                        job = dict(mode="journalist", rec=rec, target=jp, frame=frame or "F14_no_yes_but")
            idle_post = t - state.get("last_post", 0) > config.IDLE_POST_GAP_S
            if job is None and ("post" not in state["modes"][-(config.POST_EVERY_N - 1):] or idle_post):
                rec = accounts.eligible()
                if rec:
                    job = dict(mode="post", rec=rec, frame=content.pick_frame(content.PERSONA_BY_KEY[rec["persona"]]))
            if job is None:
                time.sleep(45)
                continue

            # ---- draft and check ----
            rec, mode, target = job["rec"], job["mode"], job.get("target")
            persona, system, user = build_prompt(job, targeter)
            text = backend = None
            for _ in range(2):
                raw, backend = gen.complete(system, user)
                if raw is None:
                    break
                text, why = quality.check(raw, mode, state["recent_texts"][-300:], prompt_text=user,
                                          target_text=(target or {}).get("body") or "", wants=job.get("wants") or ())
                if text:
                    break
                stats["rejected"][why] = stats["rejected"].get(why, 0) + 1
                log({"act": "reject", "why": why, "mode": mode, "persona": persona["key"], "frame": job["frame"],
                     "backend": backend, "raw": raw})
                print(f"  rejected [{mode}] ({why}): {raw[:160]!r}")
            if not text:
                if mode == "reply_back" and job.get("tries", 0) < 2:
                    job["tries"] = job.get("tries", 0) + 1      # a citizen who answered us is worth another try
                    queue.append(job)
                continue

            # ---- send ----
            post_id = None
            if args.live:
                acc = accounts.session(rec)
                try:
                    r = acc.post(text) if mode == "post" else acc.reply(target["post_id"], text)
                except ctn.APIError as e:
                    if e.status != 401:
                        raise
                    acc = accounts.relogin(rec)
                    r = acc.post(text) if mode == "post" else acc.reply(target["post_id"], text)
                post_id = r["post_id"]
                rl = social.rate_limit
                if rl and rl.remaining == 0:
                    time.sleep(rl.reset / max(rl.limit, 1) + 1)
                # a citizen who talks back to us: follow them from that persona (separate follow budget)
                if mode == "reply_back" and target["author_id"] not in rec.setdefault("followed", []):
                    try:
                        acc.follow(target["author_id"])
                        rec["followed"].append(target["author_id"])
                        log({"act": "follow", "username": rec["username"], "account_id": target["author_id"]})
                    except ctn.APIError as e:
                        print("follow:", e.status, e.message)
            rec["last_write"], rec["writes"] = time.time(), rec.get("writes", 0) + 1
            accounts.save()
            if args.live:
                next_write = time.time() + 60.0 / per_min * random.uniform(0.7, 1.5)
            stats["accepted"] += 1
            stats["by_mode"][mode] = stats["by_mode"].get(mode, 0) + 1
            state["modes"] = (state["modes"] + [mode])[-20:]

            if target:
                state["replied_posts"] = (state["replied_posts"] + [target["post_id"]])[-5000:]
            if mode == "reply":
                state["contacted"][str(target["author_id"])] = time.time()
                state["second_voice"].append(dict(due=time.time() + random.uniform(*config.SECOND_VOICE_S),
                                                  post_id=target["post_id"], author=target["author_id"],
                                                  frame=content.FRAMES[job["frame"]]["second"],
                                                  first_persona=persona["key"], wants=job.get("wants"),
                                                  context=job.get("context")))
            if mode == "post":
                state["last_post"] = time.time()
            if mode == "journalist":
                state["journalist_any"] = time.time()
                state["journalist_last"][str(target["author_id"])] = time.time()
            state["recent_texts"] = (state["recent_texts"] + [text])[-300:]
            save_state()
            log({"act": mode, "live": args.live, "post_id": post_id, "username": rec["username"],
                 "account_id": rec.get("account_id"), "owner": rec.get("owner", owner), "persona": persona["key"],
                 "frame": job["frame"], "backend": backend, "source": job.get("source"),
                 "target_post": target and target["post_id"], "target_author": target and target["author_id"],
                 "target_text": target and (target.get("body") or "")[:300], "context": job.get("context"),
                 "text": text})
            where = ""
            if target:
                ctx = f" [under: {job['context'][:60]!r}]" if job.get("context") else ""
                where = f"\n    -> #{target['post_id']} (author {target['author_id']}){ctx}: {(target.get('body') or '')[:200]!r}"
            print(f"[{mode}|{job['frame']}|{backend}] {persona['name']}{where}\n    {text}\n")

        except ctn.RateLimited as e:
            time.sleep((e.retry_after or 30) + 1)
        except ctn.APIError as e:
            print("API error", e.status, e.message)
            msg = (e.message or "").lower()
            if e.status == 403 and "suspended" in msg and job:
                job["rec"]["status"] = "suspended"
                accounts.save()
                log({"act": "suspended", "username": job["rec"]["username"]})
            elif e.status == 403 and "locked" in msg:
                time.sleep(300)
            time.sleep(10)
        except openai.APIError as e:
            print("LLM error", type(e).__name__, str(e)[:120])
            time.sleep(20)
        except KeyboardInterrupt:
            break

    save_state()
    print("done:", json.dumps({**stats, "llm_calls": gen.calls}))


if __name__ == "__main__":
    main()
