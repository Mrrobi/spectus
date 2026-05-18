"""Example: batched extraction. Reuses the browser pool — much faster than
calling `extract()` once per URL."""
from __future__ import annotations

import json

from spectus import SyncClient


URLS_AND_INSTRUCTIONS = [
    (
        "https://www.finn.no/realestate/homes/ad.html?finnkode=463730293",
        "Return one record: viewing_time, asking_price (NOK integer), sales_doc_url.",
    ),
    (
        "https://books.toscrape.com/",
        "Extract every book: title, price, availability, rating, link.",
    ),
    (
        "https://news.ycombinator.com/",
        "Top stories: title, points, author, comments_count, story_url.",
    ),
]


def main() -> None:
    with SyncClient.open(browser=True) as client:
        for url, instruction in URLS_AND_INSTRUCTIONS:
            print(f"\n=== {url} ===")
            result = client.extract(url, instruction, max_records=10)
            print(f"status: {result['status']}")
            print(f"strategy: {result['diagnostics']['strategy_used']}")
            print(f"runtime_ms: {result['diagnostics']['runtime_ms']}")
            print(f"records ({len(result['records'])}):")
            print(json.dumps(result["records"][:3], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
