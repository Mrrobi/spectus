"""Example: how any Python codebase uses spectus.

Setup (one-time, from a venv where spectus is installed):

    pip install spectus                   # or: pip install /path/to/spectus-0.1.0-py3-none-any.whl
    spectus install-browsers              # downloads Playwright Chromium (~110 MB)
    export OPENAI_API_KEY=sk-...          # Windows PowerShell: $env:OPENAI_API_KEY="sk-..."

Then in your code:
"""

from __future__ import annotations

import json

from spectus import extract


def main() -> None:
    # 1. one-shot — give URL + plain-English instruction, get JSON back.
    result = extract(
        url="https://news.ycombinator.com/",
        instruction=(
            "Extract the top stories. For each: title, points, author, comments_count, story_url."
        ),
        max_records=10,
    )

    # `result` is a plain dict:
    #   {
    #     "status":      "success" | "partial_success" | "failed",
    #     "url":         "...",
    #     "instruction": "...",
    #     "records":     [ {...}, {...}, ... ],
    #     "diagnostics": { strategy_used, quality_score, repair_attempts, ... },
    #     "message":     null | "repair hint if quality was low"
    #   }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    # If you only care about the rows:
    for row in result["records"]:
        print(row)


if __name__ == "__main__":
    main()
