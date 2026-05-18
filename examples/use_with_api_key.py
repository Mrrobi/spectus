"""Example: pass OPENAI_API_KEY directly (no env var needed).

Useful when your codebase already has secrets in its own config — e.g. AWS
Secrets Manager, Vault, Django settings, .env loaded by python-dotenv into
your own namespace.
"""
from __future__ import annotations

import json
import os

from spectus import Client, SyncClient, extract

# Pretend this came from your secrets manager:
MY_KEY = os.environ.get("MY_APP_OPENAI_KEY", "sk-replace-me")


# A. one-shot, key per call
result = extract(
    url="https://news.ycombinator.com/",
    instruction="Top stories: title, story_url, points, author",
    openai_api_key=MY_KEY,
    max_records=5,
)
print(json.dumps(result["records"], ensure_ascii=False, indent=2))


# B. reusable sync client, key passed once at open
with SyncClient.open(openai_api_key=MY_KEY) as client:
    r = client.extract("https://example.com", "extract page title")
    print(r["records"])


# C. async, key + other settings overrides
async def example_async() -> dict:
    client = await Client.create(
        openai_api_key=MY_KEY,
        settings={
            "openai_model_intent": "gpt-4o-mini",
            "openai_model_plan": "gpt-4.1",
            "browser_pool_size": 1,
            "allow_private_targets": False,
        },
    )
    try:
        return await client.extract("https://example.com", "page title")
    finally:
        await client.close()
