from __future__ import annotations

import asyncio

from spectus._db.session import make_engine, make_sessionmaker
from spectus.config import get_settings
from spectus.logging import configure_logging, get_logger


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("seed_demo")
    engine = make_engine(settings.db_url)
    _ = make_sessionmaker(engine)
    log.info("seed_demo_done", db_url=settings.db_url)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
