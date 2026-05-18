"""Example: async usage (FastAPI, aiohttp, asyncio scripts).

Use this if your codebase already runs an event loop.
"""
from __future__ import annotations

import asyncio
import json

from spectus import Client


async def main() -> None:
    client = await Client.create(browser=True)
    try:
        result = await client.extract(
            url="https://www.finn.no/realestate/homes/ad.html?finnkode=463730293",
            instruction=(
                "Return viewing_time, asking_price (integer NOK), sales_doc_url "
                "for this real estate listing."
            ),
            max_records=1,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
