"""Paths and settings. Paths can be overridden with environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"

RAW_DATA_DIR = Path(os.environ.get("ASX_RAW_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
INBOX_DIR = Path(os.environ.get("ASX_INBOX_DIR", PROJECT_ROOT / "data" / "inbox"))
EVENTS_FILE = Path(os.environ.get("ASX_EVENTS_FILE", PROJECT_ROOT / "data" / "events.csv"))
WAREHOUSE_PATH = Path(os.environ.get("ASX_WAREHOUSE_PATH", PROJECT_ROOT / "warehouse" / "asx.duckdb"))


@dataclass(frozen=True)
class RbaTable:
    name: str
    table: str
    url: str

    @property
    def ext(self) -> str:
        return self.url.rsplit(".", 1)[-1]


def load_yaml(name: str) -> dict:
    return yaml.safe_load((CONFIG_DIR / name).read_text())


def sources() -> dict:
    return load_yaml("sources.yml")


def rba_tables() -> list[RbaTable]:
    return [RbaTable(**entry) for entry in sources()["rba"]]


def expected_tickers() -> dict[str, list[str]]:
    """Current ticker -> all codes it has traded under, index included."""
    cfg = load_yaml("tickers.yml")
    codes = {cfg["index"]["ticker"]: [cfg["index"]["ticker"]]}
    for stock in cfg["stocks"]:
        codes[stock["ticker"]] = [stock["ticker"], *stock.get("former_tickers", [])]
    return codes
