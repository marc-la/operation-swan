"""Rapid response to the news slots (todo/52 WS5, 29 Oct, Marc): a content/news.toml block drafted from one article.

Both papers run the same story in the same minute at fixed slots (about 22:00, 02:00, 05:30-07:00 and 08:30-09:30 UTC),
and a referendum story needs a No reading in our replies within the hour. This reads the article (sites.legitreal.com,
read-only) and works out what it can for the block: a key, the real UTC time (the papers stamp Sydney time with a "Z":
11 h off, floored to the hour), an impact guess, keywords from the headline, and the facts it can rest on (those the
fact desk took from this article, and the active facts its words state, by facts.SAYS). The line and the reading are a
person's or an agent's to write (--line, --reading). The block is then run through tests/test_news.py's file tests on a
temporary copy of content/news.toml with the block added, and printed with what failed. Nothing is written or deployed:
add the block to content/news.toml by hand, run scripts/t.sh, commit and push.

Run it on the box, where the fact table has the desk's overlay (data/facts_auto.toml):

    .venv/bin/python scripts/news_story.py latest                      # the newest articles, to pick one
    .venv/bin/python scripts/news_story.py daily-kingstonia SLUG       # the article, its facts and a draft block
    .venv/bin/python scripts/news_story.py daily-kingstonia SLUG --line "..." --reading "..." [--requires a,b] [--impact 2]

The staged stories (a wastewater retest either way, the campaign's close) are commented out at the end of
content/news.toml, ready to fill in the same way.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from swan_bot import facts as fact_store  # noqa: E402
from swan_bot import news  # noqa: E402

PAPER_OFFSET_H = 11                 # the papers' "Z" stamps are Sydney time (AEDT, UTC+11, until April)
TODO = "TODO"
STOP = set("""about after again against ahead amid before being between calls could during first from have into made more
most news over said says than that their them then there these they this those under very were what when where which
while will with would your""".split())
FILE_TESTS = ("test_every_story_parses_and_rests_on_active_facts", "test_story_text_passes_the_gate_and_names_no_voting_logistics",
              "test_every_story_states_only_the_facts_it_requires", "test_published_times_are_real_utc_not_the_papers_sydney_stamp")
IMPACT = ((3, re.compile(r"\bpolls?\b|survey|lead (narrow|widen)|undecided", re.I)),
          (2, re.compile(r"referendum|\bvot(e|ing)\b|campaign|cabinet|minister|promise|vaccin|h2d2|doses?|wastewater|case", re.I)))


def utc_published(stamp):
    """The article's real UTC time, floored to the hour, as news.toml wants it ("2026-10-29T07:00:00Z")."""
    t = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")) - dt.timedelta(hours=PAPER_OFFSET_H)
    return t.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def key_of(slug):
    """A news.toml key from the slug: its first content words, snake case, 31 characters at most."""
    words = [w for w in re.split(r"[^a-z0-9]+", slug.lower()) if len(w) > 3 and w not in STOP]
    key = ""
    for w in words:
        if len(key) + len(w) + 1 > 31:
            break
        key = f"{key}_{w}" if key else w
    return key or "story"


def impact_guess(title):
    """3 for a poll, 2 for anything on the vote or the virus, else 1 (news.WEIGHT; a person may change it)."""
    return next((n for n, rx in IMPACT if rx.search(title or "")), 1)


def keywords_of(title, n=6):
    """Up to n keyword patterns from the headline's longest content words (a prefix match: '\\bferr' for ferries)."""
    words = sorted({w for w in re.findall(r"[a-z]{5,}", (title or "").lower()) if w not in STOP}, key=lambda w: (-len(w), w))
    return [rf"\b{w[:max(5, len(w) - 2)]}" for w in words[:n]]


def facts_for(site, slug, text):
    """(from_article, stated): the active facts the desk took from this article, and the active facts its words state."""
    active = {k: f for k, f in fact_store.TABLE.items() if f.get("status") == "active"}
    from_article = [k for k, f in active.items() if (f.get("source") or "") == f"{site}/{slug}"]
    stated = [k for k, rx in fact_store.SAYS.items() if k in active and rx.search(text or "") and k not in from_article]
    return from_article, stated


def literal(s):
    if "'" in s or "\n" in s:
        raise ValueError(f"keyword {s!r}: no quote or newline in a TOML literal string")
    return f"'{s}'"


def block(key, published, impact, requires, line, reading, keywords, turnout=False, source=None):
    """The story as news.toml text (keywords as literal strings, as the file writes them)."""
    out = [f"# {source} (scripts/news_story.py)" if source else None, f"[{key}]", f"published = {published}",
           f"impact = {impact}", "turnout = true" if turnout else None,
           f"requires = {json.dumps(list(requires))}", f"line = {json.dumps(line, ensure_ascii=False)}",
           f"reading = {json.dumps(reading, ensure_ascii=False)}", f"keywords = [{', '.join(literal(k) for k in keywords)}]"]
    return "\n".join(x for x in out if x is not None) + "\n"


def run_news_tests(text, path=None):
    """tests/test_news.py's file tests on content/news.toml with this block added, in a temporary copy (the file itself is
    not touched). [] when they pass, else what failed."""
    sys.path.insert(0, str(ROOT / "tests"))
    import test_news
    path = path or news.FILE
    fd, tmp = tempfile.mkstemp(suffix=".toml")
    with os.fdopen(fd, "w") as f:
        f.write(path.read_text() + "\n" + text)
    old, fails = news.FILE, []
    news.FILE = pathlib.Path(tmp)
    news.reset()
    try:
        for name in FILE_TESTS:
            try:
                getattr(test_news, name)()
            except (AssertionError, ValueError, KeyError) as e:      # a block news.parse refuses is a ValueError
                fails.append(f"{name}: {type(e).__name__}: {str(e)[:300]}")
    finally:
        news.FILE = old
        news.reset()
        os.unlink(tmp)
    if TODO in text:
        fails.append("the line or the reading is still TODO: write them (--line, --reading)")
    return fails


def draft(article, site, slug, line=None, reading=None, requires=None, impact=None, key=None, turnout=False):
    """(block text, notes) for one article dict (NewsSites.article)."""
    text = f"{article.get('title') or ''}\n{article.get('summary') or ''}\n{article.get('body') or ''}"
    from_article, stated = facts_for(site, slug, text)
    req = list(requires) if requires is not None else from_article
    notes = dict(from_article=from_article, stated=stated, published_sydney=article.get("published_at"))
    return block(key or key_of(slug), utc_published(article["published_at"]), impact or impact_guess(article.get("title")),
                 req, line or TODO, reading or TODO, keywords_of(article.get("title")), turnout=turnout,
                 source=f"{site}/{slug}"), notes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("site", help="daily-kingstonia or kingstonia-herald, or 'latest' to list the newest articles")
    ap.add_argument("slug", nargs="?")
    ap.add_argument("--line", help="the news, plainly, as the prompt gives it")
    ap.add_argument("--reading", help="what it means for a No")
    ap.add_argument("--requires", help="comma list of fact keys (default: the facts the desk took from this article)")
    ap.add_argument("--impact", type=int, choices=sorted(news.WEIGHT))
    ap.add_argument("--key")
    ap.add_argument("--turnout", action="store_true", help="the story turnout replies (No-leaners) prefer")
    a = ap.parse_args(argv)
    import capturethenarrative as ctn
    papers = ctn.NewsSites()
    if a.site == "latest":
        for x in papers.latest(limit=12):
            print(f"{utc_published(x['published_at'])}  {x['site']['sub_url']:18} {x['slug']}\n{'':40}{x['title']}")
        return 0
    if not a.slug:
        ap.error("SLUG is needed (scripts/news_story.py latest lists them)")
    article = papers.article(a.site, a.slug)
    text, notes = draft(article, a.site, a.slug, a.line, a.reading,
                        a.requires.split(",") if a.requires else None, a.impact, a.key, a.turnout)
    print(f"{article.get('title')}\n  published {notes['published_sydney']} (the paper's stamp) = {utc_published(article['published_at'])} UTC")
    print(f"  {article.get('summary') or ''}\n")
    print((article.get("body") or "")[:900].strip() + " ...\n")
    for label, keys in (("facts from this article", notes["from_article"]), ("other active facts its words state", notes["stated"])):
        print(f"{label}:" + ("" if keys else " none"))
        for k in keys:
            print(f"  {k}: {fact_store.TABLE[k]['text'][:150]}")
    print(f"\n{text}")
    fails = run_news_tests(text)
    print("news tests: " + ("pass. Add the block to content/news.toml, run scripts/t.sh, commit and push." if not fails
                            else "\n  " + "\n  ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
