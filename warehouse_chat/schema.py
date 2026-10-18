"""Allowed warehouse schema, read from the dbt documentation."""
from __future__ import annotations

from functools import cache
from pathlib import Path

import duckdb
import yaml

from ingestion.config import WAREHOUSE_PATH

ROOT = Path(__file__).parent.parent
MARTS_YML = ROOT / "dbt_project" / "models" / "marts" / "_marts.yml"
SEEDS_YML = ROOT / "dbt_project" / "seeds" / "_seeds.yml"

ALLOWED_TABLES = {
    "marts.mart_region_interval",
    "marts.mart_region_daily",
    "marts.mart_notable_intervals",
    "marts.mart_interconnector_interval",
    "marts.mart_events",
    "reference.regions",
    "reference.interconnectors",
}


def _models(path: Path, key: str) -> dict[str, dict]:
    return {model["name"]: model for model in yaml.safe_load(path.read_text())[key]}


@cache
def prompt_schema() -> str:
    """Render DuckDB types and dbt descriptions for only the allowed tables."""
    sources = {
        "marts": _models(MARTS_YML, "models"),
        "reference": _models(SEEDS_YML, "seeds"),
    }
    with duckdb.connect(str(WAREHOUSE_PATH), read_only=True) as con:
        types = {(schema, table, column): kind for schema, table, column, kind in con.execute("""
            select table_schema, table_name, column_name, data_type
            from information_schema.columns
            where table_schema in ('marts', 'reference')
        """).fetchall()}
    blocks = []
    for table in sorted(ALLOWED_TABLES):
        schema, name = table.split(".")
        model = sources[schema][name]
        lines = [f"{table}: {' '.join(model['description'].split())}"]
        for column in model["columns"]:
            description = " ".join(column.get("description", "").split())
            kind = types[(schema, name, column["name"])]
            lines.append(f"  {column['name']} {kind}: {description}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
