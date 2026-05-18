"""spectus — AI-assisted web data extractor.

Quick one-shot usage (sync, simplest):

    from spectus import extract
    result = extract(
        url="https://example.com/products",
        instruction="Extract every product: title, price, rating, link",
        openai_api_key="sk-...",      # optional; falls back to OPENAI_API_KEY env
    )
    print(result["records"])

Reusable client (async, recommended for multiple calls — browser pool reused):

    import asyncio
    from spectus import Client

    async def main():
        client = await Client.create()
        try:
            for url in urls:
                r = await client.extract(url, "extract title, price")
                print(r["records"])
        finally:
            await client.close()

    asyncio.run(main())

Reusable client (sync wrapper):

    from spectus import SyncClient
    with SyncClient.open() as client:
        r1 = client.extract(url1, instruction1)
        r2 = client.extract(url2, instruction2)
"""
from __future__ import annotations

__version__ = "0.2.1"

from spectus.client import Client, SyncClient, extract

__all__ = ["Client", "SyncClient", "extract", "__version__"]
