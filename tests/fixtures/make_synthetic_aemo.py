"""Write synthetic_aemo_<table>.csv: made-up AEMO archive files for one hour of 1 September 2026.

    python tests/fixtures/make_synthetic_aemo.py

The layout copies the real MMSDM files: CRLF line endings, an opening C record wider
than some tables, one I header record, D rows and a closing END OF REPORT count.
Each file has one column the pipeline does not use, to prove columns are read by name.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

OUT = Path(__file__).parent
REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
INTERCONNECTORS = ["N-Q-MNSP1", "NSW1-QLD1", "T-V-MNSP1", "V-S-MNSP1", "V-SA", "VIC1-NSW1"]
UNITS = {"SYN_COAL1": ("NSW1", "Black coal", 500.0), "SYN_WIND1": ("SA1", "Wind", 100.0),
         "SYN_BATT1": ("VIC1", "Battery Storage", 50.0)}
INTERVALS = [datetime(2026, 9, 1, 0, 5) + timedelta(minutes=5 * i) for i in range(12)]
CHANGED = "2026/09/01 00:00:00"


def ts(value: datetime) -> str:
    return value.strftime("%Y/%m/%d %H:%M:%S")


def write(table: str, category: str, report: str, columns: list[str], rows: list[list]) -> None:
    lines = [f"C,SYNTHETIC,DVD_{table},AEMO,PUBLIC,2026/10/09,00:00:00,0,MONTHLY_ARCHIVE,0",
             ",".join(["I", category, report, "1", *columns])]
    lines += [",".join(["D", category, report, "1", *(f'"{v}"' if " " in str(v) else str(v) for v in row)])
              for row in rows]
    lines.append(f'C,"END OF REPORT",{len(lines) + 1}')
    (OUT / f"synthetic_aemo_{table.lower()}.csv").write_bytes("\r\n".join(lines).encode())


def main() -> None:
    write("DISPATCHPRICE", "DISPATCH", "PRICE",
          ["SETTLEMENTDATE", "RUNNO", "REGIONID", "INTERVENTION", "RRP", "SYNTHETIC_EXTRA", "APCFLAG",
           "MARKETSUSPENDEDFLAG", "PRICE_STATUS", "LASTCHANGED"],
          [[ts(t), 1, r, 0, 100 + i + j, "x", 0, 0, "FIRM", CHANGED]
           for i, t in enumerate(INTERVALS) for j, r in enumerate(REGIONS)])
    write("TRADINGPRICE", "TRADING", "PRICE",
          ["SETTLEMENTDATE", "RUNNO", "REGIONID", "PERIODID", "RRP", "INVALIDFLAG", "SYNTHETIC_EXTRA",
           "PRICE_STATUS", "LASTCHANGED"],
          [[ts(t), 1, r, i + 1, 100 + i + j, 0, "x", "FIRM", CHANGED]
           for i, t in enumerate(INTERVALS) for j, r in enumerate(REGIONS)])
    write("DISPATCHREGIONSUM", "DISPATCH", "REGIONSUM",
          ["SETTLEMENTDATE", "RUNNO", "REGIONID", "INTERVENTION", "TOTALDEMAND", "AVAILABLEGENERATION",
           "DEMANDFORECAST", "NETINTERCHANGE", "SYNTHETIC_EXTRA", "TOTALINTERMITTENTGENERATION", "UIGF",
           "LASTCHANGED"],
          [[ts(t), 1, r, 0, 1000 + i, 2000, 1, -10, "x", 100, 110, CHANGED]
           for i, t in enumerate(INTERVALS) for r in REGIONS])
    write("DISPATCHINTERCONNECTORRES", "DISPATCH", "INTERCONNECTORRES",
          ["SETTLEMENTDATE", "RUNNO", "INTERCONNECTORID", "INTERVENTION", "METEREDMWFLOW", "MWFLOW", "MWLOSSES",
           "MARGINALVALUE", "SYNTHETIC_EXTRA", "EXPORTLIMIT", "IMPORTLIMIT", "LASTCHANGED"],
          [[ts(t), 1, ic, 0, 50, 50, 1, 0, "x", 100, -100, CHANGED] for t in INTERVALS for ic in INTERCONNECTORS])
    write("DISPATCH_UNIT_SCADA", "DISPATCH", "UNIT_SCADA",
          ["SETTLEMENTDATE", "DUID", "SCADAVALUE", "LASTCHANGED"],
          [[ts(t), duid, -10 if duid == "SYN_BATT1" else cap / 2, CHANGED]
           for t in INTERVALS for duid, (_, _, cap) in UNITS.items()])
    write("DUDETAILSUMMARY", "PARTICIPANT_REGISTRATION", "DUDETAILSUMMARY",
          ["DUID", "START_DATE", "END_DATE", "DISPATCHTYPE", "CONNECTIONPOINTID", "REGIONID", "STATIONID",
           "PARTICIPANTID", "LASTCHANGED", "SCHEDULE_TYPE", "SYNTHETIC_EXTRA"],
          [[duid, "2020/01/01 00:00:00", "2999/12/31 00:00:00", "GENERATOR", "SYNCP", region, duid, "SYNTH",
            CHANGED, "SCHEDULED", "x"] for duid, (region, _, _) in UNITS.items()])
    write("GENUNITS", "PARTICIPANT_REGISTRATION", "GENUNITS",
          ["GENSETID", "STATIONID", "REGISTEREDCAPACITY", "MAXCAPACITY", "GENSETTYPE", "SYNTHETIC_EXTRA",
           "LASTCHANGED", "CO2E_EMISSIONS_FACTOR", "CO2E_ENERGY_SOURCE"],
          [[duid, duid, cap, cap, "GENERATOR", "x", CHANGED, 0, fuel] for duid, (_, fuel, cap) in UNITS.items()])
    write("DUALLOC", "PARTICIPANT_REGISTRATION", "DUALLOC",
          ["EFFECTIVEDATE", "VERSIONNO", "DUID", "GENSETID", "LASTCHANGED"],
          [["2020/01/01 00:00:00", 1, duid, duid, CHANGED] for duid in UNITS])
    write("MARKET_PRICE_THRESHOLDS", "MARKET_CONFIG", "MARKET_PRICE_THRESHOLDS",
          ["EFFECTIVEDATE", "VERSIONNO", "VOLL", "MARKETPRICEFLOOR", "SYNTHETIC_EXTRA", "LASTCHANGED"],
          [["2020/07/01 00:00:00", 1, 9999, -999, "x", CHANGED]])


if __name__ == "__main__":
    main()
