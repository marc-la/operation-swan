"""Operation Swan bot (Vote No). DRY-RUN BY DEFAULT: nothing is registered or posted without --live.

Every write slot goes to the most valuable job (docs/06-strategy/second-mover-plan.md):
  1. reply back to a citizen who replied to us
  2. second voice: a different persona and angle on a doubt we answered 10-30 min ago
  3. reply to an undecided citizen (mostly in the news threads), answering the doubt they voiced
  4. reply to a journalist's referendum post (at most one per 45 min)
  5. persona post, at most 1 in every 4 writes
If nothing is worth writing, it waits. Accounts are registered one at a time, 20-40 min apart.

With --amplify (todo/04-reach-amplification.md), persona posts are replaced by one amplified original every 10-16 min:
like-only booster accounts and the other voices like it on an organic-looking schedule, other voices reply in its
thread and repost it (those writes come first in the order above, after reply-backs). See amplify.py.
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
from .amplify import Amplifier
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
        created = [dt.datetime.fromisoformat(r["created"]).timestamp() for r in self.records
                   if r.get("created") and r.get("role", "voice") != "booster"]
        if created:                      # a restart must not register straight after the last registration
            self.next_register = max(created) + random.uniform(*config.REGISTER_GAP_S)

    def save(self):
        if self.live:
            save_json(config.ACCOUNTS_FILE, self.records, private=True)

    def active(self):
        return [r for r in self.records if r.get("status", "active") == "active"]

    def voices(self):
        """Persona accounts that write. Boosters (role 'booster') only view and like."""
        return [r for r in self.active() if r.get("role", "voice") != "booster"]

    def boosters(self):
        return [r for r in self.active() if r.get("role") == "booster"]

    def maybe_register(self, k, code, owner):
        """Drip registration: at most one new account per call, 20-40 min apart, never more than MAX_ACCOUNTS."""
        voices_ever = [r for r in self.records if r.get("role", "voice") != "booster"]
        if (len(self.voices()) >= k or len(voices_ever) >= config.MAX_ACCOUNTS
                or len(self.active()) >= config.MAX_ACTIVE or time.time() < self.next_register):
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

    def eligible(self, frame=None, exclude=(), gap=None):
        t = time.time()
        if gap is None or not self.live:                         # dry runs rotate personas without waiting
            gap = config.ACCOUNT_MIN_GAP_S if self.live else 0
        ready = [r for r in self.voices() if r.get("last_write", 0) + gap <= t and r["persona"] not in exclude]
        if frame:
            fit = [r for r in ready if frame in content.PERSONA_BY_KEY[r["persona"]]["frames"]]
            ready = fit or ready
        return min(ready, key=lambda r: r.get("last_write", 0)) if ready else None

    def by_persona(self, key):
        return next((r for r in self.voices() if r["persona"] == key), None)


def reply_back_jobs(social, accounts, targeter, limit=3):
    """Citizens who replied to our posts. Reads at most `limit` replies; only those are marked resolved."""
    jobs = []
    for rec in accounts.voices():
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


def second_frame(frame):
    second = content.FRAMES[frame]["second"]
    return random.choice(second) if isinstance(second, list) else second


def build_prompt(job, targeter):
    persona = content.PERSONA_BY_KEY[job["rec"]["persona"]]
    target = job.get("target") or {}
    body = target.get("body") or ""
    mode = job["mode"]
    if mode == "post":
        user = content.post_prompt(job["frame"], targeter.headline if random.random() < 0.3 else None,
                                   ask=bool(job.get("amp")))
    elif mode == "thread":
        user = content.thread_reply_prompt(body, job["frame"], job["style"])
    elif mode == "thread_answer":
        user = content.thread_answer_prompt(job["our_text"], body)
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
    ap.add_argument("--per-min", type=float, default=1.0, help="max team writes per minute (hard max 2.5); real pace follows the target queue")
    ap.add_argument("--amplify", action="store_true", help="own-team amplification of our posts (todo/04); "
                    "touch AMPLIFY_OFF in the repo root to pause it without a restart")
    ap.add_argument("--boosters", type=int, default=0, help=f"with --amplify: like-only accounts to grow to, one every "
                    f"4-9 min (max {config.MAX_BOOSTERS})")
    ap.add_argument("--samples", type=int, default=0, help="dry run: stop after this many accepted drafts")
    ap.add_argument("--allow-qwen", action="store_true", help="fall back to the weak provided model when Gemini is out")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt for --live")
    args = ap.parse_args()

    config.load_env()
    config.assigned_side()
    code, owner = config.team_code(), config.operator()
    k = max(1, min(args.accounts, config.MAX_ACCOUNTS))
    per_min = max(0.1, min(args.per_min, 2.5))

    social = ctn.LegitSocial()
    gen = Generator(code, allow_qwen=args.allow_qwen)
    targeter = Targeter(social, log=log)
    accounts = Accounts(social, args.live)
    state = load_json(config.STATE_FILE, {})
    for key, default in (("replied_posts", []), ("contacted", {}), ("recent_texts", []), ("second_voice", []),
                         ("journalist_last", {}), ("modes", []), ("journalist_any", 0)):
        state.setdefault(key, default)

    amp = None
    if args.amplify:
        amp = Amplifier(social, accounts, state, args.live, log, targeter=targeter, code=code, owner=owner,
                        boosters=args.boosters, save=lambda: save_state())

    def pause(seconds):
        """Sleep, but keep the amplifier's likes and views going meanwhile."""
        until = time.time() + seconds
        while True:
            if amp:
                amp.tick()
            left = until - time.time()
            if left <= 0:
                return
            time.sleep(min(2.0, left))

    if args.live:
        lock = social.feed_lock()
        if lock.get("locked"):
            raise SystemExit(f"feed is locked: {lock.get('reason')}")
        print(f"LIVE: Vote No | owner {owner} | {len(accounts.active())} active accounts, growing to {k} "
              f"(one every 20-40 min) | up to {per_min}/min for {args.hours} h | LLM: {gen.describe()}"
              + (f" | AMPLIFY: {len(accounts.boosters())} boosters, growing to {amp.boosters_target}" if amp else ""))
        if not args.yes and input("Type GO to continue: ").strip() != "GO":
            raise SystemExit("aborted")
    else:
        print(f"DRY RUN: nothing will be registered or posted. LLM: {gen.describe()}")
        accounts.next_register = 0.0

    def save_state():
        if args.live:
            # pending reply-backs survive a restart (their notifications are already marked resolved)
            state["queue"] = [dict(username=j["rec"]["username"], target=j["target"], our_text=j["our_text"],
                                   tries=j.get("tries", 0)) for j in queue if j["mode"] == "reply_back"]
            save_json(config.STATE_FILE, state)

    end = time.time() + args.hours * 3600
    next_write = next_notif = 0.0
    queue, stats = [], {"accepted": 0, "rejected": {}, "by_mode": {}}
    by_user = {r["username"]: r for r in accounts.active()}
    for q in state.pop("queue", []):
        if q["username"] in by_user:
            queue.append(dict(mode="reply_back", rec=by_user[q["username"]], target=q["target"],
                              our_text=q["our_text"], tries=q.get("tries", 0)))
    if queue:
        print(f"resumed {len(queue)} pending reply-back(s)")

    while time.time() < end and not (args.samples and stats["accepted"] >= args.samples):
        job = None
        try:
            # dry runs register a fake account instantly so drafts can be read without waiting
            if args.live:
                accounts.maybe_register(k, code, owner)
            else:
                while len(accounts.voices()) < k and len(accounts.records) < len(content.PERSONAS) + 50:
                    accounts.next_register = 0.0
                    before = len(accounts.records)
                    accounts.maybe_register(k, code, owner)
                    if len(accounts.records) == before:
                        break
                while amp and len(accounts.boosters()) < amp.boosters_target:
                    amp.next_register = 0.0
                    before = len(accounts.records)
                    amp.maybe_register_booster()
                    if len(accounts.records) == before:
                        break
            if not accounts.voices():
                pause(30)
                continue
            # No retirement by action count: accounts are lost through moderator-hidden posts, not actions
            # (scoring guide s3). Parking by hidden-post count is a TODO (TODO.md, "Hidden-post watch").
            our_ids = {r.get("account_id") for r in accounts.records if r.get("account_id")}
            targeter.refresh()
            if amp:
                amp.tick()
            if args.live and time.time() >= next_notif:
                queue += reply_back_jobs(social, accounts, targeter)
                next_notif = time.time() + 300

            wait = next_write - time.time()
            if wait > 0:
                pause(min(wait, 30))
                continue
            if gen.next_available_in() > 0 and not args.allow_qwen:
                print(f"no Gemini model available; waiting {gen.next_available_in() / 60:.0f} min")
                pause(min(gen.next_available_in() + 1, 600))
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
            if job is None and amp:                                  # own-thread replies, answers, reposts (due)
                job = amp.next_write_job()
            if job is None and amp and amp.amp_post_due():            # the next amplified original
                rec = accounts.eligible()
                if rec:
                    job = dict(mode="post", rec=rec, frame=content.pick_frame(content.PERSONA_BY_KEY[rec["persona"]]),
                               amp=True, level=amp.choose_level())
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
            plain_posts = not amp or amp.paused()                    # amplified originals replace plain persona posts
            if job is None and plain_posts and ("post" not in state["modes"][-(config.POST_EVERY_N - 1):] or idle_post):
                rec = accounts.eligible()
                if rec:
                    job = dict(mode="post", rec=rec, frame=content.pick_frame(content.PERSONA_BY_KEY[rec["persona"]]))
            if job is None:
                pause(45)
                continue

            # ---- draft and check ----
            rec, mode, target = job["rec"], job["mode"], job.get("target")
            persona = content.PERSONA_BY_KEY[rec["persona"]]
            text = backend = user = None
            if mode == "repost":
                text, backend = "", "none"
            else:
                persona, system, user = build_prompt(job, targeter)
            for _ in range(0 if mode == "repost" else 2):
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
            if not text and mode != "repost":
                if mode == "reply_back" and job.get("tries", 0) < 2:
                    job["tries"] = job.get("tries", 0) + 1      # a citizen who answered us is worth another try
                    queue.append(job)
                continue

            # ---- send ----
            post_id = None
            if args.live:
                def send(acc):
                    if mode == "post":
                        return acc.post(text)
                    if mode == "repost":
                        return acc.repost(target["post_id"])
                    return acc.reply(target["post_id"], text)

                acc = accounts.session(rec)
                try:
                    r = send(acc)
                except ctn.APIError as e:
                    if e.status != 401:
                        raise
                    acc = accounts.relogin(rec)
                    r = send(acc)
                post_id = r["post_id"]
                rl = acc.rate_limit                      # the team-wide write budget, as this answer reported it
                if rl and rl.remaining == 0:
                    pause(rl.reset / max(rl.limit, 1) + 1)
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
            if mode in ("reply", "reply_back"):           # either way, don't approach them again for 3 days
                state["contacted"][str(target["author_id"])] = time.time()
            if mode == "reply_back":                      # they're talking to us: no extra persona joins in
                state["second_voice"] = [s for s in state["second_voice"] if s["author"] != target["author_id"]]
            if mode == "reply":
                state["second_voice"].append(dict(due=time.time() + random.uniform(*config.SECOND_VOICE_S),
                                                  post_id=target["post_id"], author=target["author_id"],
                                                  frame=second_frame(job["frame"]),
                                                  first_persona=persona["key"], wants=job.get("wants"),
                                                  context=job.get("context")))
            if mode == "post":
                state["last_post"] = time.time()
                if job.get("amp"):
                    amp.on_post(post_id, rec, text, job["frame"], job["level"])
            if mode == "thread" and amp:
                amp.on_thread_sent(job, post_id, text)
            if mode == "journalist":
                state["journalist_any"] = time.time()
                state["journalist_last"][str(target["author_id"])] = time.time()
            if text:
                state["recent_texts"] = (state["recent_texts"] + [text])[-300:]
            save_state()
            log({"act": mode, "live": args.live, "post_id": post_id, "username": rec["username"],
                 "account_id": rec.get("account_id"), "owner": rec.get("owner", owner), "persona": persona["key"],
                 "frame": job["frame"], "backend": backend, "source": job.get("source"),
                 "target_post": target and target["post_id"], "target_author": target and target["author_id"],
                 "target_text": target and (target.get("body") or "")[:300], "context": job.get("context"),
                 "text": text, "amp_level": job.get("level"), "amp_post": job.get("amp_post"), "style": job.get("style")})
            where = ""
            if target:
                ctx = f" [under: {job['context'][:60]!r}]" if job.get("context") else ""
                where = f"\n    -> #{target['post_id']} (author {target['author_id']}){ctx}: {(target.get('body') or '')[:200]!r}"
            print(f"[{mode}|{job['frame']}|{backend}] {persona['name']}{where}\n    {text}\n")

        except ctn.RateLimited as e:
            pause((e.retry_after or 30) + 1)
        except ctn.APIError as e:
            print("API error", e.status, e.message)
            msg = (e.message or "").lower()
            if e.status == 403 and "suspended" in msg and job:
                job["rec"]["status"] = "suspended"
                accounts.save()
                log({"act": "suspended", "username": job["rec"]["username"]})
            elif e.status == 403 and "locked" in msg:
                pause(300)
            pause(10)
        except openai.APIError as e:
            print("LLM error", type(e).__name__, str(e)[:120])
            pause(20)
        except KeyboardInterrupt:
            if job and job.get("mode") == "reply_back" and job not in queue:
                queue.insert(0, job)                  # stopped mid-draft: keep the citizen's reply for next run
            break

    save_state()
    print("done:", json.dumps({**stats, "llm_calls": gen.calls}))


if __name__ == "__main__":
    main()
