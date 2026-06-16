"""Watch-folder poller — demo fallback when Gmail is unavailable."""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff"}
POLL_INTERVAL_SEC = int(os.getenv("FOLDER_POLL_INTERVAL_SEC", "5"))
DEFAULT_WATCH_DIR = Path(__file__).resolve().parent / "data" / "watch"


class FolderWatcher:
    """Poll a directory for new invoice files and trigger the pipeline."""

    def __init__(
        self,
        on_file: Callable[[Path], None],
        watch_dir: Path | None = None,
        poll_interval_sec: int = POLL_INTERVAL_SEC,
    ) -> None:
        self._on_file = on_file
        self._watch_dir = watch_dir or Path(os.getenv("WATCH_FOLDER", str(DEFAULT_WATCH_DIR)))
        self._poll_interval_sec = poll_interval_sec
        self._seen_files: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._watch_dir.mkdir(parents=True, exist_ok=True)
        self._seed_existing_files()

        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="folder-watcher", daemon=True)
        self._thread.start()
        logger.info("Folder watcher started dir=%s interval=%ss", self._watch_dir, self._poll_interval_sec)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self._poll_interval_sec + 5)

    def _seed_existing_files(self) -> None:
        for path in self._watch_dir.iterdir():
            if path.is_file():
                self._seen_files.add(path.name)

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception:
                logger.exception("Folder poll error")

            self._stop.wait(self._poll_interval_sec)

    def _poll_once(self) -> None:
        for path in sorted(self._watch_dir.iterdir()):
            if not path.is_file():
                continue
            if path.name in self._seen_files:
                continue
            if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                self._seen_files.add(path.name)
                continue

            self._seen_files.add(path.name)
            staging = path.with_suffix(path.suffix + ".processing")
            shutil.move(path, staging)
            try:
                self._on_file(staging)
            finally:
                processed_dir = self._watch_dir / "processed"
                processed_dir.mkdir(exist_ok=True)
                dest = processed_dir / staging.name.replace(".processing", "")
                if staging.exists():
                    shutil.move(staging, dest)
