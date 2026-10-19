"""Read-only smoke test: confirms the package imports and the servers answer.

Needs no account or team code. Makes a handful of read requests only.
Usage:  .venv/bin/python scripts/smoke_test.py
"""
import capturethenarrative as ctn


def main() -> None:
    print("capturethenarrative endpoints:")
    print("  social:", ctn.DEFAULT_LEGIT_SOCIAL_URL)
    print("  news:  ", ctn.DEFAULT_NEWS_SITES_URL)
    print("  llm:   ", ctn.DEFAULT_COMPETITOR_LLM_URL)

    social = ctn.LegitSocial(max_retries=0)
    lock = social.feed_lock()
    print("feed lock:", lock)
    trending = social.feed_trending(limit=5)
    print(f"trending: {len(trending)} posts; rate_limit={social.rate_limit}")
    for p in trending:
        print(f"  #{p['post_id']}: {(p.get('body') or '')[:70]!r}")

    news = ctn.NewsSites()
    for article in news.latest(3):
        print("news:", article["site"]["name"], "-", article["title"])


if __name__ == "__main__":
    main()
