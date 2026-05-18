from __future__ import annotations

import asyncio
import json

import httpx

DEMOS = [
    {
        "url": "https://www.example.com/",
        "instruction": "Extract the page title and main heading.",
        "options": {"max_records": 5, "use_browser": "never", "save_template": False},
    },
]


async def main() -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=60.0) as c:
        for demo in DEMOS:
            print(f"\n=== {demo['url']} ===")
            try:
                r = await c.post("/api/extractions", json=demo)
                r.raise_for_status()
                payload = r.json()
            except httpx.HTTPError as e:
                print(f"  request failed: {e}")
                continue
            print(json.dumps(payload, indent=2)[:2000])


if __name__ == "__main__":
    asyncio.run(main())
