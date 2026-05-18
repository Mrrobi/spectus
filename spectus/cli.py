"""spectus command-line interface.

Subcommands:
    spectus extract URL "instruction" [--browser auto|force|never] [--max N] [--csv|--json]
    spectus templates [--status candidate|active|needs_review|deprecated]
    spectus migrate
    spectus install-browsers
    spectus version
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from spectus import __version__


def _migrate(_: argparse.Namespace) -> int:
    from alembic.config import Config

    from alembic import command

    cfg_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    if not cfg_path.exists():
        cfg_path = Path.cwd() / "alembic.ini"
    cfg = Config(str(cfg_path))
    command.upgrade(cfg, "head")
    return 0


def _install_browsers(_: argparse.Namespace) -> int:
    print("installing playwright chromium...")
    return subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"])


def _extract(args: argparse.Namespace) -> int:
    from spectus._core.extractor import Extractor

    async def run() -> int:
        ex = await Extractor.create(
            browser=(args.browser != "never"),
            log_level=args.log_level,
        )
        try:
            resp = await ex.extract(
                url=args.url,
                instruction=args.instruction,
                use_browser=args.browser,
                max_records=args.max_records,
                save_template=not args.no_save_template,
            )
        finally:
            await ex.close()

        records = ex.records(resp)
        if args.output == "csv":
            from spectus._core.exporter import records_to_csv

            sys.stdout.write(records_to_csv(records))
            return 0 if resp.status == "success" else 1
        if args.output == "json":
            sys.stdout.write(json.dumps(records, ensure_ascii=False, indent=2))
            sys.stdout.write("\n")
            return 0 if resp.status == "success" else 1
        ex.show(resp, n=args.show)
        return 0 if resp.status == "success" else 1

    return asyncio.run(run())


def _templates(args: argparse.Namespace) -> int:
    from spectus._core.extractor import Extractor

    async def run() -> int:
        ex = await Extractor.create(browser=False, log_level=args.log_level)
        try:
            templates = await ex.list_templates(args.status)
        finally:
            await ex.close()
        if args.output == "json":
            sys.stdout.write(
                json.dumps([t.model_dump(mode="json") for t in templates], indent=2, default=str)
            )
            sys.stdout.write("\n")
            return 0
        if not templates:
            print("no templates saved")
            return 0
        for t in templates:
            print(
                f"  {t.domain:30s}  pattern={t.url_pattern:20s}  status={t.status:14s}  "
                f"successes={t.consecutive_successes}  failures={t.consecutive_failures}  "
                f"score={t.success_score:.2f}"
            )
        return 0

    return asyncio.run(run())


def _version(_: argparse.Namespace) -> int:
    print(f"spectus {__version__}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spectus",
        description="AI-assisted web data extractor",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="log verbosity (default: WARNING)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ext = sub.add_parser("extract", help="run a single extraction and print result")
    p_ext.add_argument("url")
    p_ext.add_argument("instruction")
    p_ext.add_argument(
        "--browser",
        default="auto",
        choices=["auto", "force", "never"],
        help="browser usage policy (default: auto)",
    )
    p_ext.add_argument("--max-records", type=int, default=100)
    p_ext.add_argument("--no-save-template", action="store_true")
    p_ext.add_argument("--show", type=int, default=5, help="rows to display (table mode only)")
    p_ext.add_argument(
        "--output",
        default="table",
        choices=["table", "json", "csv"],
        help="output format (default: table)",
    )
    p_ext.set_defaults(func=_extract)

    p_tpl = sub.add_parser("templates", help="list saved templates")
    p_tpl.add_argument("--status", default=None)
    p_tpl.add_argument("--output", default="table", choices=["table", "json"])
    p_tpl.set_defaults(func=_templates)

    p_mig = sub.add_parser("migrate", help="apply database migrations")
    p_mig.set_defaults(func=_migrate)

    p_ib = sub.add_parser("install-browsers", help="install Playwright Chromium")
    p_ib.set_defaults(func=_install_browsers)

    p_ver = sub.add_parser("version", help="print version")
    p_ver.set_defaults(func=_version)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
