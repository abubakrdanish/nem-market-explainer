"""Paths and settings. Paths can be overridden with environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

RAW_DATA_DIR = Path(os.environ.get("NEM_RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
EVENTS_FILE = Path(os.environ.get("NEM_EVENTS_FILE", PROJECT_ROOT / "data" / "events.csv"))
WAREHOUSE_PATH = Path(os.environ.get("NEM_WAREHOUSE_PATH", PROJECT_ROOT / "warehouse" / "nem.duckdb"))


@dataclass(frozen=True)
class RbaTable:
    name: str
    table: str
    url: str

    @property
    def ext(self) -> str:
        return self.url.rsplit(".", 1)[-1]


def sources() -> dict:
    return yaml.safe_load((CONFIG_DIR / "sources.yml").read_text())


def rba_tables() -> list[RbaTable]:
    return [RbaTable(**entry) for entry in sources()["rba"]]
