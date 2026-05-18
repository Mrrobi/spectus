from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from spectus.config import Settings
from spectus.errors import BlockedUrlError
from spectus._core.compliance import ComplianceChecker, _TokenBucket
from spectus._core.url_normalizer import normalize


@pytest.mark.asyncio
async def test_token_bucket_respects_rate():
    bucket = _TokenBucket(capacity=1.0, refill_rate=10.0, tokens=1.0, last_refill=0.0)
    bucket.last_refill = 0.0
    await bucket.acquire(deadline_s=1.0)


@pytest.mark.asyncio
async def test_ssrf_blocks_localhost():
    s = Settings(allow_private_targets=False, openai_api_key="")
    http = AsyncMock()
    checker = ComplianceChecker(http, s)
    url = normalize("http://127.0.0.1/")

    async def _fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    with patch("asyncio.get_running_loop") as loop_get:
        loop_mock = AsyncMock()
        loop_mock.getaddrinfo = _fake_getaddrinfo
        loop_get.return_value = loop_mock
        with pytest.raises(BlockedUrlError):
            await checker._ssrf_check(url)


@pytest.mark.asyncio
async def test_ssrf_allows_when_flag_set():
    s = Settings(allow_private_targets=True, openai_api_key="")
    http = AsyncMock()
    checker = ComplianceChecker(http, s)
    url = normalize("http://127.0.0.1/")

    async def _fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    with patch("asyncio.get_running_loop") as loop_get:
        loop_mock = AsyncMock()
        loop_mock.getaddrinfo = _fake_getaddrinfo
        loop_get.return_value = loop_mock
        await checker._ssrf_check(url)
