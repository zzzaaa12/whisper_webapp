"""Incremental metadata index for summary text files."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from src.utils.channel_mapping import get_display_name

LOGGER = logging.getLogger(__name__)
INDEX_VERSION = 1
UNKNOWN_CHANNEL = "未知頻道"


class SummaryIndexService:
    def __init__(self, summary_folder: Path, index_file: Optional[Path] = None, min_sync_interval: float = 30.0):
        self.summary_folder = Path(summary_folder)
        self.index_file = index_file or self.summary_folder / ".summary_index.json"
        self._entries: Dict[str, Dict] = {}
        self._loaded = False
        self._index_mtime_ns: Optional[int] = None
        self._last_sync_monotonic = 0.0
        self.min_sync_interval = min_sync_interval
        self._lock = threading.RLock()

    @staticmethod
    def _fallback_title(file_path: Path) -> str:
        title = re.sub(r"^var_www_html_yt_sub_\d{8}_", "", file_path.stem)
        return re.sub(r"_summary$", "", title).replace("_", " ")

    def _parse_file(self, file_path: Path, stat_result: os.stat_result) -> Dict:
        title = channel = None
        preview_parts: List[str] = []
        in_topics = False
        preview_length = 0
        with file_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle):
                line = raw_line.strip()
                if line_number <= 20:
                    if "🎬 標題：" in line:
                        title = line.split("🎬 標題：", 1)[1].strip()
                    elif "標題：" in line and not title:
                        title = line.split("標題：", 1)[1].strip()
                    if "📺 頻道：" in line:
                        channel = line.split("📺 頻道：", 1)[1].strip()
                    elif "頻道：" in line and not channel:
                        channel = line.split("頻道：", 1)[1].strip()
                if line.startswith("#") and "核心主題" in line:
                    in_topics = True
                    continue
                if in_topics:
                    if line.startswith("#"):
                        break
                    if line and not line.startswith("="):
                        preview_parts.append(line)
                        preview_length += len(line)
                        if preview_length >= 220:
                            break
        channel = channel or UNKNOWN_CHANNEL
        preview = " ".join(preview_parts)
        if len(preview) > 200:
            preview = preview[:200] + "..."
        return {
            "filename": file_path.name,
            "mtime_ns": stat_result.st_mtime_ns,
            "size": stat_result.st_size,
            "title": title or self._fallback_title(file_path),
            "channel": channel,
            "channel_display": get_display_name(channel),
            "preview": preview,
            "created_at": datetime.fromtimestamp(stat_result.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _load(self) -> None:
        self._entries = {}
        if self.index_file.exists():
            try:
                payload = json.loads(self.index_file.read_text(encoding="utf-8"))
                if payload.get("version") != INDEX_VERSION:
                    raise ValueError("unsupported index version")
                self._entries = {
                    item["filename"]: item for item in payload.get("entries", [])
                    if isinstance(item, dict) and item.get("filename")
                }
                self._index_mtime_ns = self.index_file.stat().st_mtime_ns
                self._last_sync_monotonic = time.monotonic()
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                LOGGER.warning("Unable to load summary index; rebuilding: %s", error)
                self._index_mtime_ns = None
        self._loaded = True

    def _reload_if_changed(self) -> None:
        if not self._loaded:
            self._load()
            return
        try:
            disk_mtime = self.index_file.stat().st_mtime_ns
        except OSError:
            return
        if self._index_mtime_ns and disk_mtime != self._index_mtime_ns:
            self._load()

    def _persist(self) -> None:
        self.summary_folder.mkdir(parents=True, exist_ok=True)
        payload = {"version": INDEX_VERSION, "entries": list(self._entries.values())}
        temporary = self.index_file.with_name(
            f".{self.index_file.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, self.index_file)
        self._index_mtime_ns = self.index_file.stat().st_mtime_ns

    def sync(self, force: bool = False) -> Dict[str, int]:
        started = time.perf_counter()
        with self._lock:
            self._reload_if_changed()
            if not force and self._last_sync_monotonic and time.monotonic() - self._last_sync_monotonic < self.min_sync_interval:
                return {"total_files": len(self._entries), "cache_hits": len(self._entries), "parsed_files": 0, "removed_files": 0, "index_sync_ms": 0}
            current_names = set()
            cache_hits = parsed_files = 0
            if self.summary_folder.exists():
                for file_path in self.summary_folder.glob("*.txt"):
                    if not file_path.is_file():
                        continue
                    current_names.add(file_path.name)
                    try:
                        stat_result = file_path.stat()
                        cached = self._entries.get(file_path.name)
                        if cached and cached.get("mtime_ns") == stat_result.st_mtime_ns and cached.get("size") == stat_result.st_size:
                            cache_hits += 1
                        else:
                            self._entries[file_path.name] = self._parse_file(file_path, stat_result)
                            parsed_files += 1
                    except (OSError, UnicodeError) as error:
                        LOGGER.warning("Unable to index summary %s: %s", file_path.name, error)
            removed = set(self._entries) - current_names
            for filename in removed:
                self._entries.pop(filename, None)
            if parsed_files or removed or self._index_mtime_ns is None:
                try:
                    self._persist()
                except OSError as error:
                    LOGGER.warning("Unable to persist summary index: %s", error)
            self._last_sync_monotonic = time.monotonic()
            metrics = {
                "total_files": len(self._entries), "cache_hits": cache_hits,
                "parsed_files": parsed_files, "removed_files": len(removed),
                "index_sync_ms": round((time.perf_counter() - started) * 1000),
            }
            LOGGER.info("Summary index sync: %s", metrics)
            return metrics

    def snapshot(self) -> List[Dict]:
        self.sync()
        with self._lock:
            return [dict(item) for item in self._entries.values()]

    def invalidate(self, filenames: Optional[Iterable[str]] = None) -> None:
        with self._lock:
            self._last_sync_monotonic = 0.0
            if filenames is None:
                self._loaded = False
                return
            changed = False
            for filename in filenames:
                changed = self._entries.pop(Path(filename).name, None) is not None or changed
            if changed:
                try:
                    self._persist()
                except OSError as error:
                    LOGGER.warning("Unable to persist index invalidation: %s", error)


_summary_index_service: Optional[SummaryIndexService] = None
_service_lock = threading.Lock()


def get_summary_index_service() -> SummaryIndexService:
    global _summary_index_service
    if _summary_index_service is None:
        with _service_lock:
            if _summary_index_service is None:
                from src.utils.path_manager import get_path_manager
                _summary_index_service = SummaryIndexService(get_path_manager().get_summary_folder())
    return _summary_index_service


def reset_summary_index_service() -> None:
    global _summary_index_service
    with _service_lock:
        _summary_index_service = None
