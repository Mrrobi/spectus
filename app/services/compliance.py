from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass, field
from time import monotonic
from typing import Literal
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.errors import BlockedByRobotsError, BlockedUrlError, FetchError
from app.logging import get_logger
from app.services.url_normalizer import NormalizedUrl

RobotsDecision = Literal["allowed", "disallowed", "no_robots"]


class ComplianceVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    robots_decision: RobotsDecision
    reason: str | None = None


@dataclass
class _RobotsRule:
    parser: RobotFileParser | None
    fetched_at: float
    failed: bool


@dataclass
class _TokenBucket:
    capacity: float
    refill_rate: float
    tokens: float
    last_refill: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def acquire(self, deadline_s: float = 5.0) -> None:
        end = monotonic() + deadline_s
        async with self.lock:
            while True:
                now = monotonic()
                elapsed = now - self.last_refill
                self.last_refill = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.refill_rate
                remaining = end - now
                if wait > remaining:
                    raise TimeoutError("rate_limit_acquire_timeout")
                await asyncio.sleep(min(wait, remaining))


class ComplianceChecker:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._robots_cache: dict[str, _RobotsRule] = {}
        self._buckets: dict[str, _TokenBucket] = {}
        self._log = get_logger("compliance")

    async def check(self, url: NormalizedUrl) -> ComplianceVerdict:
        await asyncio.wait_for(self._ssrf_check(url), timeout=2.0)
        decision = await self._robots_check(url)
        if decision == "disallowed":
            raise BlockedByRobotsError(detail=url.canonical)
        await self.acquire_rate_token(url.domain)
        return ComplianceVerdict(allowed=True, robots_decision=decision)

    async def _ssrf_check(self, url: NormalizedUrl) -> None:
        if url.scheme not in ("http", "https"):
            raise BlockedUrlError(detail="unsupported_scheme", reason="unsupported_scheme")
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(url.host, None)
        except socket.gaierror as e:
            raise FetchError(detail=f"dns_resolution_failed:{url.host}", reason="dns") from e
        for info in infos:
            sockaddr = info[4]
            try:
                ip = ipaddress.ip_address(sockaddr[0])
            except (ValueError, IndexError):
                continue
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                if not self._settings.allow_private_targets:
                    raise BlockedUrlError(
                        detail=f"private_or_internal_ip:{ip}",
                        reason=f"private_ip:{ip}",
                    )

    async def _robots_check(self, url: NormalizedUrl) -> RobotsDecision:
        rule = self._robots_cache.get(url.domain)
        ttl = self._settings.robots_cache_ttl_sec
        if rule is None or (monotonic() - rule.fetched_at) > ttl:
            rule = await self._fetch_robots(url)
            self._robots_cache[url.domain] = rule
        if rule.failed or rule.parser is None:
            return "no_robots"
        ua = self._settings.user_agent
        return "allowed" if rule.parser.can_fetch(ua, url.canonical) else "disallowed"

    async def _fetch_robots(self, url: NormalizedUrl) -> _RobotsRule:
        robots_url = f"{url.scheme}://{url.host}/robots.txt"
        try:
            r = await self._http.get(robots_url, timeout=3.0)
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            self._log.info("robots_fetch_failed", domain=url.domain, error=str(e))
            return _RobotsRule(parser=None, fetched_at=monotonic(), failed=True)
        if r.status_code >= 400:
            return _RobotsRule(parser=None, fetched_at=monotonic(), failed=True)
        parser = RobotFileParser()
        try:
            parser.parse(r.text.splitlines())
        except Exception as e:
            self._log.info("robots_parse_failed", domain=url.domain, error=str(e))
            return _RobotsRule(parser=None, fetched_at=monotonic(), failed=True)
        return _RobotsRule(parser=parser, fetched_at=monotonic(), failed=False)

    async def acquire_rate_token(self, domain: str) -> None:
        bucket = self._buckets.get(domain)
        if bucket is None:
            if len(self._buckets) >= 1000:
                oldest_key = min(self._buckets, key=lambda k: self._buckets[k].last_refill)
                self._buckets.pop(oldest_key, None)
            bucket = _TokenBucket(
                capacity=self._settings.rate_limit_burst,
                refill_rate=self._settings.rate_limit_rps,
                tokens=self._settings.rate_limit_burst,
                last_refill=monotonic(),
            )
            self._buckets[domain] = bucket
        await bucket.acquire(deadline_s=5.0)
