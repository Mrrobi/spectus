from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx


async def fetch(url: str, out: Path) -> None:
    async with httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; spectus-fixture-recorder)"},
        timeout=httpx.Timeout(30.0),
    ) as http:
        r = await http.get(url)
        r.raise_for_status()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(r.content)
        print(f"wrote {out} ({len(r.content)} bytes, status {r.status_code})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    asyncio.run(fetch(args.url, args.out))


if __name__ == "__main__":
    main()
