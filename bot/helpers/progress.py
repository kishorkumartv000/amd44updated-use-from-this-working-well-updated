from __future__ import annotations

import asyncio
import time
from typing import Optional

from bot.helpers.message import edit_message
from bot.logger import LOGGER


class ProgressReporter:
    def __init__(self, msg, label: str = "Apple Music", min_interval_seconds: float = 2.0, show_system_stats: bool = True):
        self.msg = msg
        self.label = label
        self.stage: str = "Preparing"

        self.download_percent: int = 0
        self.tracks_done: int = 0
        self.tracks_total: Optional[int] = None

        self.zip_done: int = 0
        self.zip_total: int = 0

        self.upload_current: int = 0
        self.upload_total: int = 0
        self.file_index: Optional[int] = None
        self.file_total: Optional[int] = None

        self._last_update: float = 0.0
        self._min_interval: float = min_interval_seconds
        self._lock = asyncio.Lock()
        self._show_system_stats = show_system_stats

    def _make_bar(self, percent: int) -> str:
        blocks = 10
        safe_percent = max(0, min(100, int(percent)))
        filled = int((safe_percent / 100) * blocks)
        return "".join(["▰" for _ in range(filled)] + ["▱" for _ in range(blocks - filled)])

    async def set_stage(self, stage: str):
        self.stage = stage
        await self._maybe_update(force=True)

    async def set_total_tracks(self, total: int):
        if total is not None and total >= 0:
            self.tracks_total = int(total)
        await self._maybe_update()

    async def update_download(self, percent: Optional[int] = None, tracks_done: Optional[int] = None):
        if percent is not None:
            self.download_percent = max(0, min(100, int(percent)))
        if tracks_done is not None:
            self.tracks_done = max(0, int(tracks_done))
        await self._maybe_update()

    async def update_zip(self, done: int, total: int):
        self.zip_done = max(0, int(done))
        self.zip_total = max(0, int(total))
        await self._maybe_update()

    async def update_upload(self, current: int, total: int, file_index: Optional[int] = None, file_total: Optional[int] = None, label: Optional[str] = None):
        self.upload_current = max(0, int(current))
        self.upload_total = max(0, int(total))
        if file_index is not None:
            self.file_index = int(file_index)
        if file_total is not None:
            self.file_total = int(file_total)
        if label:
            self.stage = label
        await self._maybe_update()

    def should_update(self) -> bool:
        return (time.monotonic() - self._last_update) >= self._min_interval

    async def _maybe_update(self, force: bool = False):
        async with self._lock:
            now = time.monotonic()
            if not force and (now - self._last_update) < self._min_interval:
                return
            self._last_update = now
            text = self._render()
            try:
                await edit_message(self.msg, text)
            except Exception as e:
                LOGGER.debug(f"Progress update skipped: {e}")

    def _render(self) -> str:
        lines = []
        stage_emoji = {
            "Preparing": "🟡",
            "Downloading": "⬇️",
            "Processing": "🛠️",
            "Zipping": "🗜️",
            "Uploading": "⬆️",
            "Finalizing": "🧹",
            "Done": "✅",
        }
        lines.append(f"{stage_emoji.get(self.stage, '🔄')} {self.label} • {self.stage}")

        # Optional system stats line
        if self._show_system_stats:
            try:
                import psutil, shutil, os
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                mem_used = int(mem.used / (1024**3))
                mem_total = int(mem.total / (1024**3))
                # Choose storage path; fallback to current cwd
                base = os.getenv("LOCAL_STORAGE") or os.getcwd()
                du = shutil.disk_usage(base)
                disk_used = int(du.used / (1024**3))
                disk_total = int(du.total / (1024**3))
                lines.append(f"🖥️ CPU {cpu}% • RAM {mem_used}/{mem_total} GB • Disk {disk_used}/{disk_total} GB")
            except Exception:
                pass

        # Download section
        if self.stage in ("Downloading", "Processing") or self.download_percent > 0 or self.tracks_done > 0:
            bar = self._make_bar(self.download_percent)
            if self.tracks_total:
                tracks = f"{self.tracks_done}/{self.tracks_total}"
            else:
                tracks = f"{self.tracks_done}"
            lines.append(f"🎶 {bar} {self.download_percent}%  •  Tracks: {tracks}")

        # Zip section
        if self.zip_total:
            percent = int((self.zip_done / self.zip_total) * 100) if self.zip_total else 0
            bar = self._make_bar(percent)
            lines.append(f"🗜️ {bar} {percent}%  •  Files: {self.zip_done}/{self.zip_total}")

        # Upload section
        if self.upload_total:
            percent = int((self.upload_current / self.upload_total) * 100) if self.upload_total else 0
            bar = self._make_bar(percent)
            idx = f" ({self.file_index}/{self.file_total})" if self.file_index and self.file_total else ""
            lines.append(f"📤 {bar} {percent}%{idx}")
        # Bot uptime at the end
        try:
            import time
            from bot.metrics import START_TIME
            uptime_seconds = int(time.time() - START_TIME)
            days, rem = divmod(uptime_seconds, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, seconds = divmod(rem, 60)
            if days:
                uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
            else:
                uptime_str = f"{hours}h {minutes}m {seconds}s"
            lines.append(f"⏱️ Uptime: {uptime_str}")
        except Exception:
            pass

        return "\n".join(lines)

    def snapshot(self) -> str:
        """Return a very light-weight single-line status string without system stats.
        Avoids any disk, CPU, or network calls so it can be used for /status cheaply.
        """
        segments: list[str] = []
        # Stage
        segments.append(f"{self.label} • {self.stage}")
        # Download
        if self.download_percent or self.tracks_done:
            if self.tracks_total:
                tracks = f"{self.tracks_done}/{self.tracks_total}"
            else:
                tracks = f"{self.tracks_done}"
            segments.append(f"DL {self.download_percent}% ({tracks})")
        # Zip
        if self.zip_total:
            percent_zip = int((self.zip_done / self.zip_total) * 100) if self.zip_total else 0
            segments.append(f"ZIP {percent_zip}% ({self.zip_done}/{self.zip_total})")
        # Upload
        if self.upload_total:
            percent_up = int((self.upload_current / self.upload_total) * 100) if self.upload_total else 0
            if self.file_index and self.file_total:
                segments.append(f"UP {percent_up}% ({self.file_index}/{self.file_total})")
            else:
                segments.append(f"UP {percent_up}%")
        return " • ".join(segments)