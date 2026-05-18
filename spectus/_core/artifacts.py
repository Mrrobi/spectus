from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import orjson

from spectus.logging import get_logger


class ArtifactsWriter:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._log = get_logger("artifacts")

    def _job_dir(self, job_id: str) -> Path:
        d = self._base / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def write_html(self, job_id: str, name: str, html: str) -> str:
        path = self._job_dir(job_id) / name
        try:
            path.write_text(html, encoding="utf-8", errors="replace")
        except Exception as e:
            self._log.warning("artifact_write_failed", name=name, error=str(e))
            return ""
        return str(path)

    async def write_json(self, job_id: str, name: str, data: Any) -> str:
        path = self._job_dir(job_id) / name
        try:
            path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
        except Exception as e:
            self._log.warning("artifact_write_failed", name=name, error=str(e))
            try:
                path.write_text(json.dumps(data, default=str), encoding="utf-8")
            except Exception:
                return ""
        return str(path)

    async def write_screenshot(self, job_id: str, png_bytes: bytes) -> str:
        path = self._job_dir(job_id) / "screenshot.png"
        try:
            path.write_bytes(png_bytes)
        except Exception as e:
            self._log.warning("screenshot_write_failed", error=str(e))
            return ""
        return str(path)

    async def write_llm(self, job_id: str, step: str, payload: dict[str, Any]) -> str:
        llm_dir = self._job_dir(job_id) / "llm"
        llm_dir.mkdir(parents=True, exist_ok=True)
        idx = sum(1 for _ in llm_dir.glob(f"{step}.*.json"))
        path = llm_dir / f"{step}.{idx + 1}.json"
        try:
            path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
        except Exception as e:
            self._log.warning("llm_artifact_write_failed", step=step, error=str(e))
            return ""
        return str(path)

    async def write_error(self, job_id: str, error: dict[str, Any]) -> str:
        return await self.write_json(job_id, "error.json", error)
