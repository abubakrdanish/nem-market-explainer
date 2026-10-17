"""AEMO MMSDM monthly archive: find, download and load the tables below.

Timestamps stay as published: naive NEM market time (AEST, UTC+10 all year),
and SETTLEMENTDATE marks the end of each 5-minute or 30-minute interval.
"""
from __future__ import annotations

import logging
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import duckdb

from ingestion.http_client import PoliteClient
from ingestion.load_raw import loaded_files, transaction
from ingestion.raw_files import save_raw

log = logging.getLogger(__name__)

TIMESTAMP_FORMAT = "%Y/%m/%d %H:%M:%S"


@dataclass(frozen=True)
class AemoTable:
    name: str
    columns: dict[str, str]  # AEMO column -> DuckDB type
    # Standing tables repeat their full history in every monthly file, so only the newest month is fetched.
    standing: bool = False

    @property
    def raw_table(self) -> str:
        return f"aemo_{self.name.lower()}"


TABLES = [
    AemoTable("DISPATCHPRICE", {
        "SETTLEMENTDATE": "timestamp", "REGIONID": "varchar", "INTERVENTION": "integer", "RRP": "double",
        "APCFLAG": "integer", "MARKETSUSPENDEDFLAG": "integer", "PRICE_STATUS": "varchar", "LASTCHANGED": "timestamp"}),
    AemoTable("TRADINGPRICE", {
        "SETTLEMENTDATE": "timestamp", "REGIONID": "varchar", "PERIODID": "integer", "RRP": "double",
        "INVALIDFLAG": "varchar", "PRICE_STATUS": "varchar", "LASTCHANGED": "timestamp"}),
    AemoTable("DISPATCHREGIONSUM", {
        "SETTLEMENTDATE": "timestamp", "REGIONID": "varchar", "INTERVENTION": "integer", "TOTALDEMAND": "double",
        "AVAILABLEGENERATION": "double", "DEMANDFORECAST": "double", "NETINTERCHANGE": "double",
        "TOTALINTERMITTENTGENERATION": "double", "UIGF": "double", "LASTCHANGED": "timestamp"}),
    AemoTable("DISPATCHINTERCONNECTORRES", {
        "SETTLEMENTDATE": "timestamp", "INTERCONNECTORID": "varchar", "INTERVENTION": "integer",
        "METEREDMWFLOW": "double", "MWFLOW": "double", "MWLOSSES": "double", "MARGINALVALUE": "double",
        "EXPORTLIMIT": "double", "IMPORTLIMIT": "double", "LASTCHANGED": "timestamp"}),
    AemoTable("DISPATCH_UNIT_SCADA", {"SETTLEMENTDATE": "timestamp", "DUID": "varchar", "SCADAVALUE": "double"}),
    AemoTable("DUDETAILSUMMARY", {
        "DUID": "varchar", "START_DATE": "timestamp", "END_DATE": "timestamp", "DISPATCHTYPE": "varchar",
        "SCHEDULE_TYPE": "varchar", "REGIONID": "varchar", "STATIONID": "varchar", "PARTICIPANTID": "varchar",
        "LASTCHANGED": "timestamp"}, standing=True),
    AemoTable("GENUNITS", {
        "GENSETID": "varchar", "GENSETTYPE": "varchar", "REGISTEREDCAPACITY": "double", "MAXCAPACITY": "double",
        "CO2E_ENERGY_SOURCE": "varchar", "CO2E_EMISSIONS_FACTOR": "double", "LASTCHANGED": "timestamp"},
        standing=True),
    AemoTable("DUALLOC", {
        "EFFECTIVEDATE": "timestamp", "VERSIONNO": "integer", "DUID": "varchar", "GENSETID": "varchar",
        "LASTCHANGED": "timestamp"}, standing=True),
    AemoTable("MARKET_PRICE_THRESHOLDS", {
        "EFFECTIVEDATE": "timestamp", "VERSIONNO": "integer", "VOLL": "double", "MARKETPRICEFLOOR": "double",
        "LASTCHANGED": "timestamp"}, standing=True),
]

# DISPATCHPRICE flags hold codes, not booleans, so test them against zero, never "= 1".
# MARKETSUSPENDEDFLAG is 1 or 2 while a region is suspended; APCFLAG is a bit field (1, 4, 16, 21, ...).
# See docs/data_dictionary.md.
SUSPENDED = "marketsuspendedflag <> 0"
APC_SET = "apcflag <> 0"


def suspension_runs(con: duckdb.DuckDBPyConnection) -> list[tuple[str, datetime, datetime, int]]:
    """Unbroken runs of suspended 5-minute intervals per region, from pricing-run rows (INTERVENTION = 0).

    Each run is (region, first interval end, last interval end, intervals).
    """
    return con.execute(f"""
        with suspended as (
            select distinct regionid, settlementdate from raw.aemo_dispatchprice
            where intervention = 0 and {SUSPENDED}),
        runs as (
            select *, settlementdate - to_minutes(5 * row_number() over (
                partition by regionid order by settlementdate)) as run from suspended)
        select regionid, min(settlementdate), max(settlementdate), count(*) from runs
        group by regionid, run order by 2, 1""").fetchall()


def month_url(archive_url: str, month: date) -> str:
    return urljoin(archive_url, f"{month:%Y}/MMSDM_{month:%Y_%m}/MMSDM_Historical_Data_SQLLoader/DATA/")


def published_months(listing: str) -> list[date]:
    """Months in a year folder listing, such as MMSDM_2026_09."""
    return sorted({date(int(y), int(m), 1) for y, m in re.findall(r"MMSDM_(\d{4})_(\d\d)/", listing)})


def table_links(listing: str, table: str) -> list[tuple[str, str]]:
    """(href, part) for one table in a month's DATA listing.

    Files up to 2024-07 are PUBLIC_DVD_<TABLE>_<YYYYMM>010000.zip. From 2024-08 they are
    PUBLIC_ARCHIVE#<TABLE>#FILE<nn>#<YYYYMM>010000.zip, and large tables run over several parts.
    """
    links = []
    for href in re.findall(r'HREF="([^"]+\.zip)"', listing, re.I):
        name = href.rsplit("/", 1)[-1].replace("%23", "#")
        if re.fullmatch(rf"PUBLIC_DVD_{table}_\d{{12}}\.zip", name):
            links.append((href, "01"))
        elif m := re.fullmatch(rf"PUBLIC_ARCHIVE#{table}#FILE(\d\d)#\d{{12}}\.zip", name):
            links.append((href, m.group(1)))
    return sorted(links, key=lambda link: link[1])


def stem(table: AemoTable, month: date, part: str) -> str:
    return f"{table.name.lower()}_{month:%Y%m}_{part}"


def raw_files(directory: Path, table: AemoTable) -> list[Path]:
    """Saved files for one table, oldest month first."""
    pattern = re.compile(rf"{table.name.lower()}_\d{{6}}_\d\d_\d{{8}}(T\d{{6}})?\.zip")
    return sorted(p for p in directory.glob("*.zip") if pattern.fullmatch(p.name)) if directory.exists() else []


def _saved(directory: Path, table: AemoTable, month: date) -> bool:
    return any(directory.glob(f"{stem(table, month, '01')}_*.zip"))


def download(client: PoliteClient, settings: dict, directory: Path, today: date) -> None:
    """Fetch every table-month not yet saved. Archive months are final, so each file is fetched once."""
    start = date.fromisoformat(settings["start_month"] + "-01")
    scada_start = date.fromisoformat(settings["scada_start_month"] + "-01")
    months = []
    for year in range(start.year, today.year + 1):
        months += published_months(client.get(urljoin(settings["archive_url"], f"{year}/")).decode())
    months = [m for m in months if m >= start]
    for month in months:
        wanted = [t for t in TABLES if t.standing and month == months[-1]
                  or not t.standing and month >= (scada_start if t.name == "DISPATCH_UNIT_SCADA" else start)]
        missing = [t for t in wanted if not _saved(directory, t, month)]
        if not missing:
            continue
        listing = client.get(month_url(settings["archive_url"], month)).decode()
        for table in missing:
            links = table_links(listing, table.name)
            if not links:
                raise RuntimeError(f"{table.name} is not in the {month:%Y-%m} archive listing")
            for href, part in links:
                save_raw(client.get(urljoin(settings["archive_url"], href)), directory, stem(table, month, part), "zip")


def _select_list(table: AemoTable) -> str:
    parts = []
    for column, kind in table.columns.items():
        value = f"nullif(\"{column}\", '')"
        if kind == "timestamp":
            value = f"strptime({value}, '{TIMESTAMP_FORMAT}')"
        elif kind != "varchar":
            value = f"{value}::{kind}"
        parts.append(f"{value} as {column.lower()}")
    return ", ".join(parts)


def _header(csv_path: Path) -> tuple[list[str], int]:
    """Column names from the I record, and the record count from the closing C record."""
    with csv_path.open("rb") as f:
        head = f.read(65536).decode()
        f.seek(max(0, csv_path.stat().st_size - 200))
        tail = f.read().decode()
    header = next(line for line in head.splitlines() if line.startswith("I,")).split(",")
    if not all(re.fullmatch(r"[A-Z0-9_]+", c) for c in header[4:]):
        raise ValueError(f"{csv_path.name}: unexpected column names in {header}")
    total = re.search(r'C,"END OF REPORT",(\d+)\s*$', tail)
    if not total:
        raise ValueError(f"{csv_path.name}: no END OF REPORT record, so the file is incomplete")
    return ["record", "category", "report", "version", *header[4:]], int(total.group(1))


def load_file(con: duckdb.DuckDBPyConnection, table: AemoTable, path: Path, loaded_at: datetime) -> int:
    """Load one saved zip in one transaction. Returns the number of rows loaded."""
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(path) as archive:
        [member] = archive.namelist()
        csv_path = Path(archive.extract(member, tmp))
        names, total = _header(csv_path)
        missing = [c for c in table.columns if c not in names]
        if missing:
            raise ValueError(f"{path.name}: columns {missing} not in this file's {table.name} layout")
        columns = "{" + ", ".join(f"'{n}': 'VARCHAR'" for n in names) + "}"
        # strict_mode is off because the opening C record can have more fields than the table, and
        # DuckDB's parallel reader then fails on some files. The record count check below catches
        # any rows the reader would otherwise drop.
        con.execute(f"""create or replace temp table incoming as select * from read_csv(?, header=false,
            auto_detect=false, delim=',', quote='"', escape='"', null_padding=true, strict_mode=false,
            parallel=false, columns={columns})""", [str(csv_path)])
        read, headers, rows = con.execute("select count(*), count(*) filter (where record = 'I'), "
                                          "count(*) filter (where record = 'D') from incoming").fetchone()
        if read != total or headers != 1:
            raise ValueError(f"{path.name}: read {read} records with {headers} headers, file says {total}")
        with transaction(con):
            con.execute(f"insert into raw.{table.raw_table} by name select {_select_list(table)}, "
                        f"? as _source_file, ? as _loaded_at from incoming where record = 'D'",
                        [path.name, loaded_at])
        con.execute("drop table incoming")
    return rows


def load(con: duckdb.DuckDBPyConnection, table: AemoTable, paths: list[Path]) -> int:
    """Load each file not yet in the table. Returns how many files were loaded."""
    already = loaded_files(con, table.raw_table)
    new = [p for p in paths if p.name not in already]
    for path in new:
        rows = load_file(con, table, path, datetime.now(timezone.utc))
        log.info("Loaded %s into raw.%s (%d rows)", path.name, table.raw_table, rows)
    return len(new)


def table_ddl(table: AemoTable) -> str:
    columns = ", ".join(f"{c.lower()} {kind}" for c, kind in table.columns.items())
    return f"{columns}, _source_file varchar not null, _loaded_at timestamptz not null"
