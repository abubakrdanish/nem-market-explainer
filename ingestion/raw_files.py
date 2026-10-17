"""Save source files unchanged as date-stamped raw files, skipping exact duplicates.

A file whose bytes match any earlier file for the same dataset is not written
again. Changed content gets a new file, so revisions sit side by side.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def list_raw_files(directory: Path, stem: str, ext: str) -> list[Path]:
    """Raw files for one dataset, oldest first."""
    # An exact pattern, because a glob like "rba_f1_*" would also match a stem such as "rba_f1_extra".
    pattern = re.compile(rf"{re.escape(stem)}_\d{{8}}(T\d{{6}})?\.{re.escape(ext)}")
    if not directory.exists():
        return []
    return sorted(p for p in directory.iterdir() if pattern.fullmatch(p.name))


def save_raw(content: bytes, directory: Path, stem: str, ext: str,
             now: datetime | None = None) -> Path | None:
    """Write `<stem>_<YYYYMMDD>.<ext>` unless identical bytes are already saved. Returns the new path."""
    now = now or datetime.now(timezone.utc)
    digest = sha256(content)
    for existing in list_raw_files(directory, stem, ext):
        if sha256(existing.read_bytes()) == digest:
            log.info("%s unchanged since %s", stem, existing.name)
            return None

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_{now:%Y%m%d}.{ext}"
    if path.exists():
        path = directory / f"{stem}_{now:%Y%m%dT%H%M%S}.{ext}"
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(content)
    os.replace(tmp, path)
    log.info("Saved %s (%d bytes)", path.name, len(content))
    return path
