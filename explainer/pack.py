"""Evidence pack: every figure the explainer may use for one region and market date, with its source.

The pack is data. Each fact has an id, a label, a value, a unit and the mart column it came from, and the SQL
behind each section is kept in the pack so any figure can be re-derived.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

from explainer import DISCLAIMER
from ingestion.config import WAREHOUSE_PATH

FUEL_GROUPS = ["black_coal", "brown_coal", "gas", "liquid_fuel", "hydro", "wind", "solar", "battery",
               "bioenergy", "other", "unknown"]
SETTLEMENT_CHANGE = date(2021, 10, 1)
BATTERY_TRANSITION = (date(2024, 7, 4), date(2024, 12, 10))
JUNE_2022_SUSPENSION = (date(2022, 6, 15), date(2022, 6, 24))
NEAR_DAYS = 7

QUERIES = {
    "day": """
        select * from marts.mart_region_daily where region_id = $region and market_date = $day""",
    "comparison_day": """
        select market_date, avg_price, max_price, min_price, peak_demand_mw, negative_price_intervals,
               high_price_intervals
        from marts.mart_region_daily where region_id = $region and market_date = $day""",
    "median_30d": """
        select median(avg_price) as avg_price, median(max_price) as max_price,
               median(peak_demand_mw) as peak_demand_mw, count(*) as days
        from marts.mart_region_daily
        where region_id = $region and market_date between $day - 30 and $day - 1""",
    "blocks": """
        select 4 * (hour(interval_start) // 4) as block_start, avg(price) as avg_price, max(price) as max_price,
               min(price) as min_price, avg(total_demand_mw) as avg_demand_mw,
               avg(available_generation_mw) as avg_available_generation_mw,
               avg(net_interchange_mw) as avg_net_interchange_mw
        from marts.mart_region_interval where region_id = $region and market_date = $day
        group by 1 order by 1""",
    "moment": """
        select interval_end, price, total_demand_mw, available_generation_mw, net_interchange_mw,
               (select list(interconnector_name order by interconnector_name)
                from marts.mart_interconnector_interval as links
                where links.interval_end = intervals.interval_end and links.is_binding
                  and $region in (links.from_region_id, links.to_region_id)) as binding_links
        from marts.mart_region_interval as intervals
        where region_id = $region and market_date = $day
        order by {order}, interval_end limit 1""",
    "notable": """
        select rule, any_value(rule_description) as rule_description, count(*) as intervals,
               min(interval_end) as first_interval_end, max(interval_end) as last_interval_end,
               max(rule_value) as max_value, min(rule_value) as min_value, any_value(rule_threshold) as threshold
        from marts.mart_notable_intervals where region_id = $region and market_date = $day
        group by rule order by intervals desc""",
    "flags": """
        select count(*) filter (where is_market_suspended) as suspended_intervals,
               count(*) filter (where is_apc_set) as apc_set_intervals,
               count(*) filter (where is_market_suspended and is_apc_set) as suspended_and_apc_set_intervals,
               count(*) filter (where price >= market_price_cap) as at_price_cap_intervals,
               count(*) filter (where price <= market_price_floor) as at_price_floor_intervals,
               count(*) filter (where has_intervention_run) as intervention_run_intervals,
               count(*) filter (where not has_scada) as intervals_without_scada,
               any_value(market_price_cap) as market_price_cap, any_value(market_price_floor) as market_price_floor
        from marts.mart_region_interval where region_id = $region and market_date = $day""",
    "interconnectors": """
        select interconnector_name,
               count(*) filter (where is_binding) as binding_intervals,
               count(*) filter (where limits_crossed) as limits_crossed_intervals,
               avg(case when to_region_id = $region then mw_flow else -mw_flow end) as avg_flow_into_region_mw,
               max(case when to_region_id = $region then mw_flow else -mw_flow end) as max_flow_into_region_mw,
               max(case when to_region_id = $region then -mw_flow else mw_flow end) as max_flow_out_of_region_mw
        from marts.mart_interconnector_interval
        where market_date = $day and $region in (from_region_id, to_region_id)
        group by 1 order by 1""",
    "events": """
        select event_type, title, time_sydney, scope from marts.mart_events
        where region_id = $region and market_date = $day order by title""",
    "interval": """
        select * from marts.mart_region_interval where region_id = $region and interval_end = $interval_end""",
    "interval_window": """
        select interval_end, price from marts.mart_region_interval
        where region_id = $region and interval_end between $interval_end - interval 30 minute
                                                       and $interval_end + interval 30 minute
        order by interval_end""",
    "interval_links": """
        select interconnector_name, case when to_region_id = $region then mw_flow else -mw_flow end as flow_into_region_mw,
               is_binding, limits_crossed
        from marts.mart_interconnector_interval
        where interval_end = $interval_end and $region in (from_region_id, to_region_id) order by 1""",
}

CAVEATS = {
    "rooftop_solar": ("Demand here is operational demand and generation comes from SCADA, which excludes rooftop "
                      "solar, so solar's share of supply is understated.", ["rooftop"]),
    "june_2022_finding": ("Recorded finding (docs/findings.md): prices were held at or below about $300/MWh for most "
                          "of the June 2022 suspension, and neither the suspension flag nor the administered price cap "
                          "flag explains this alone. Neither should be named as the cause.", ["300"]),
    "missing_scada": ("Some intervals in this day have no generator SCADA for the region, so generation figures "
                      "for those intervals are missing.", ["scada"]),
    "unverified_suspension": ("The suspension flag is set in some intervals of this day, but this period has not been "
                              "checked against AEMO market notices; it is a flag in the data, not a confirmed "
                              "suspension.", ["flag"]),
}

GLOSSARY = {
    "apc": "APC means administered price cap. The flag marks intervals where an administered price cap applied.",
    "suspension": "A market suspension flag is set by AEMO in the dispatch data for a region.",
    "scada": "SCADA is the metered output of each grid-connected unit. It does not include rooftop solar.",
    "binding": "An interconnector is binding when its flow is at the limit set by dispatch constraints.",
}


def connect(path: Path = WAREHOUSE_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path), read_only=True)


def _rows(con, name: str, params: dict, **fmt) -> list[dict]:
    sql = QUERIES[name].format(**fmt) if fmt else QUERIES[name]
    cur = con.execute(sql, {k: v for k, v in params.items() if f"${k}" in sql})
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _round(value, unit: str):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return round(value, 1 if unit == "%" else 0 if unit in ("MW", "MWh") else 2)
    return value


def _time(value: datetime, day: date | None = None) -> str:
    # The last interval of a market date ends at midnight on the next calendar date.
    if day is not None and value.date() > day:
        return "24:00"
    return value.strftime("%H:%M")


class Pack:
    def __init__(self, region: str, day: date):
        self.facts: list[dict] = []
        self.required: list[dict] = []
        self.region, self.day = region, day

    def add(self, fact_id: str, label: str, value, unit: str, source: str) -> None:
        if isinstance(value, datetime):
            value = _time(value, self.day)
        self.facts.append({"id": fact_id, "label": label, "value": _round(value, unit), "unit": unit,
                           "source": source})

    def require(self, fact_id: str, reason: str, key_terms: list[str] | None = None) -> None:
        self.required.append({"id": fact_id, "reason": reason, "key_terms": key_terms or []})


def _near(day: date, start: date, end: date | None = None) -> bool:
    end = end or start
    return start - timedelta(NEAR_DAYS) <= day <= end + timedelta(NEAR_DAYS)


def build_pack(con: duckdb.DuckDBPyConnection, region: str, day: date, interval: str | None = None) -> dict:
    params = {"region": region, "day": day}
    found = _rows(con, "day", params)
    if not found:
        raise ValueError(f"no data in marts.mart_region_daily for {region} on {day}")
    d = found[0]
    p = Pack(region, day)
    src = "marts.mart_region_daily"

    p.add("day.avg_price", "average 5-minute dispatch price over the day", d["avg_price"], "$/MWh", f"{src}.avg_price")
    p.add("day.max_price", "highest 5-minute price of the day", d["max_price"], "$/MWh", f"{src}.max_price")
    p.add("day.min_price", "lowest 5-minute price of the day", d["min_price"], "$/MWh", f"{src}.min_price")
    p.add("day.peak_demand_mw", "highest operational demand of the day", d["peak_demand_mw"], "MW", f"{src}.peak_demand_mw")
    p.add("day.min_demand_mw", "lowest operational demand of the day", d["min_demand_mw"], "MW", f"{src}.min_demand_mw")
    p.add("day.intervals", "5-minute intervals in the day", d["intervals"], "intervals", f"{src}.intervals")
    p.add("day.negative_price_intervals", "intervals with a price below $0", d["negative_price_intervals"],
          "intervals", f"{src}.negative_price_intervals")
    p.add("day.high_price_intervals", "intervals at or above the high-price threshold", d["high_price_intervals"],
          "intervals", f"{src}.high_price_intervals")

    baselines = {}
    for name, other in (("previous_day", day - timedelta(1)), ("week_before", day - timedelta(7))):
        rows = _rows(con, "comparison_day", {"region": region, "day": other})
        label = "previous day" if name == "previous_day" else "same weekday a week earlier"
        if not rows:
            p.add(f"{name}.missing", f"{label}: no data", "no data", "", src)
            continue
        c = baselines[name] = rows[0]
        p.add(f"{name}.market_date", f"{label}: date", str(c["market_date"]), "date", f"{src}.market_date")
        for key, unit, text in (("avg_price", "$/MWh", "average price"), ("max_price", "$/MWh", "highest price"),
                                ("min_price", "$/MWh", "lowest price"), ("peak_demand_mw", "MW", "peak demand"),
                                ("negative_price_intervals", "intervals", "negative-price intervals"),
                                ("high_price_intervals", "intervals", "high-price intervals")):
            p.add(f"{name}.{key}", f"{label}: {text}", c[key], unit, f"{src}.{key}")
    m = _rows(con, "median_30d", params)[0]
    if not m["days"]:
        p.add("median_30d.missing", "median over the previous 30 days: no data", "no data", "", src)
    for key, unit, text in (("avg_price", "$/MWh", "daily average price"), ("max_price", "$/MWh", "daily highest price"),
                            ("peak_demand_mw", "MW", "daily peak demand")):
        if m["days"]:
            p.add(f"median_30d.{key}", f"median over the previous 30 days of the {text}", m[key], unit,
                  f"median of {src}.{key}, previous 30 days")
    if m["days"]:
        baselines["median_30d"] = m

    for key, unit, text in (("avg_price", "$/MWh", "average price"), ("max_price", "$/MWh", "highest price"),
                            ("peak_demand_mw", "MW", "peak demand")):
        for base, base_text in (("median_30d", "the median of the previous 30 days"), ("previous_day", "the previous day")):
            fact = f"compare.{key}.vs_{base}"
            if base not in baselines:
                p.add(f"{fact}.missing", f"{text} compared with {base_text}: no data", "no data", "", src)
            else:
                value, other = d[key], baselines[base][key]
                p.add(f"{fact}.difference", f"{text} minus {base_text}", value - other, unit,
                      f"{src}.{key} minus {base}")
                # A ratio against a negative or zero baseline reads as nonsense, so it is only given when both are positive.
                ratio = round(value / other, 2) if value > 0 and other > 0 else "not meaningful (a value is zero or negative)"
                p.add(f"{fact}.ratio", f"{text} divided by {base_text}", ratio, "times", f"{src}.{key} divided by {base}")
            p.require(fact, f"compare the day's {text} with {base_text}")

    for b in _rows(con, "blocks", params):
        s = b["block_start"]
        label = f"{s:02d}:00-{s + 4:02d}:00"
        src_i = "marts.mart_region_interval"
        p.add(f"block{s:02d}.avg_price", f"{label}: average price", b["avg_price"], "$/MWh", f"avg {src_i}.price")
        p.add(f"block{s:02d}.max_price", f"{label}: highest price", b["max_price"], "$/MWh", f"max {src_i}.price")
        p.add(f"block{s:02d}.min_price", f"{label}: lowest price", b["min_price"], "$/MWh", f"min {src_i}.price")
        p.add(f"block{s:02d}.avg_demand_mw", f"{label}: average operational demand", b["avg_demand_mw"], "MW",
              f"avg {src_i}.total_demand_mw")
        p.add(f"block{s:02d}.avg_available_generation_mw", f"{label}: average available generation",
              b["avg_available_generation_mw"], "MW", f"avg {src_i}.available_generation_mw")
        p.add(f"block{s:02d}.avg_net_interchange_mw", f"{label}: average net interchange (negative = importing)",
              b["avg_net_interchange_mw"], "MW", f"avg {src_i}.net_interchange_mw")

    for name, order, text in (("highest_price", "price desc", "interval with the highest price"),
                              ("peak_demand", "total_demand_mw desc", "interval with the highest demand"),
                              ("lowest_price", "price", "interval with the lowest price")):
        found = _rows(con, "moment", params, order=order)
        if not found:
            continue
        x = found[0]
        src_i = "marts.mart_region_interval"
        p.add(f"{name}.interval_end", f"{text}: end time", x["interval_end"], "time", f"{src_i}.interval_end")
        p.add(f"{name}.price", f"{text}: price", x["price"], "$/MWh", f"{src_i}.price")
        p.add(f"{name}.demand_mw", f"{text}: operational demand", x["total_demand_mw"], "MW", f"{src_i}.total_demand_mw")
        p.add(f"{name}.available_generation_mw", f"{text}: available generation", x["available_generation_mw"], "MW",
              f"{src_i}.available_generation_mw")
        p.add(f"{name}.net_interchange_mw", f"{text}: net interchange (negative = importing)", x["net_interchange_mw"],
              "MW", f"{src_i}.net_interchange_mw")
        p.add(f"{name}.binding_links", f"{text}: interconnectors at a limit", ", ".join(x["binding_links"] or []) or "none",
              "", "marts.mart_interconnector_interval.is_binding")

    notable = _rows(con, "notable", params)
    if not notable:
        p.add("notable.none", "intervals flagged by any notable-interval rule", "none", "",
              "marts.mart_notable_intervals")
    for n in notable:
        rule, src_n = n["rule"], "marts.mart_notable_intervals"
        p.add(f"notable.{rule}.intervals", f"intervals flagged {rule} ({n['rule_description']})", n["intervals"],
              "intervals", src_n)
        p.add(f"notable.{rule}.first_interval_end", f"{rule}: first flagged interval ends", n["first_interval_end"],
              "time", src_n)
        p.add(f"notable.{rule}.last_interval_end", f"{rule}: last flagged interval ends", n["last_interval_end"],
              "time", src_n)
        unit = "code" if rule in ("market_suspended", "apc_set") else "$/MWh"
        p.add(f"notable.{rule}.max_value", f"{rule}: largest value tested", n["max_value"], unit, f"{src_n}.rule_value")
        p.add(f"notable.{rule}.min_value", f"{rule}: smallest value tested", n["min_value"], unit, f"{src_n}.rule_value")
        if unit != "code":
            p.add(f"notable.{rule}.threshold", f"{rule}: threshold", n["threshold"], "$/MWh", f"{src_n}.rule_threshold")
        p.require(f"notable.{rule}", f"the pack flags {n['intervals']} intervals as {rule}")

    f = _rows(con, "flags", params)[0]
    src_i = "marts.mart_region_interval"
    for key, text in (("suspended_intervals", "intervals with the market suspension flag set"),
                      ("apc_set_intervals", "intervals with the administered price cap flag set"),
                      ("suspended_and_apc_set_intervals", "intervals with both flags set"),
                      ("at_price_cap_intervals", "intervals at the market price cap"),
                      ("at_price_floor_intervals", "intervals at the market price floor"),
                      ("intervention_run_intervals", "intervals where AEMO also published an intervention run"),
                      ("intervals_without_scada", "intervals with no generator SCADA for the region")):
        p.add(f"flags.{key}", text, f[key], "intervals", src_i)
    p.add("flags.market_price_cap", "market price cap in force", f["market_price_cap"], "$/MWh",
          f"{src_i}.market_price_cap")
    p.add("flags.market_price_floor", "market price floor in force", f["market_price_floor"], "$/MWh",
          f"{src_i}.market_price_floor")

    for group in FUEL_GROUPS:
        share = d[f"{group}_share"]
        if share:
            p.add(f"mix.{group}", f"{group.replace('_', ' ')} share of SCADA generation", 100 * share, "%",
                  f"{src}.{group}_share")
    p.add("mix.total_generation_mwh", "SCADA generation over the day", d["total_generation_mwh"], "MWh",
          f"{src}.total_generation_mwh")
    p.add("caveat.rooftop_solar", "caveat on demand and generation", CAVEATS["rooftop_solar"][0], "", "docs/data_dictionary.md")
    if d["negative_price_intervals"] >= 20 or (d["solar_share"] or 0) >= 0.10:
        p.require("caveat.rooftop_solar", "negative prices or a large solar share", CAVEATS["rooftop_solar"][1])

    for link in _rows(con, "interconnectors", params):
        name, src_l = link["interconnector_name"], "marts.mart_interconnector_interval"
        p.add(f"ic.{name}.binding_intervals", f"{name}: intervals at a limit", link["binding_intervals"], "intervals", src_l)
        p.add(f"ic.{name}.limits_crossed_intervals", f"{name}: intervals with crossed limits",
              link["limits_crossed_intervals"], "intervals", src_l)
        p.add(f"ic.{name}.avg_flow_into_region_mw", f"{name}: average flow into {region} (negative = out)",
              link["avg_flow_into_region_mw"], "MW", f"{src_l}.mw_flow")
        p.add(f"ic.{name}.max_flow_into_region_mw", f"{name}: largest flow into {region}",
              link["max_flow_into_region_mw"], "MW", f"{src_l}.mw_flow")
        p.add(f"ic.{name}.max_flow_out_of_region_mw", f"{name}: largest flow out of {region}",
              link["max_flow_out_of_region_mw"], "MW", f"{src_l}.mw_flow")

    events = _rows(con, "events", params)
    if not events:
        p.add("events.none", "events recorded in data/events.csv for this region and date", "none recorded", "",
              "marts.mart_events")
    for i, e in enumerate(events, 1):
        p.add(f"events.{i}", f"event recorded for this date ({e['event_type']})", e["title"], "", "marts.mart_events")

    if _near(day, SETTLEMENT_CHANGE):
        p.add("series_break.settlement", "series break", "5-minute settlement started on 2021-10-01; before it the "
              "market settled on 30-minute prices.", "", "docs/data_dictionary.md")
        p.require("series_break.settlement", "within 7 days of the settlement change", ["settlement"])
    if _near(day, *BATTERY_TRANSITION):
        p.add("series_break.battery", "series break", "Battery accounting changed between 2024-07-04 and 2024-12-10, "
              "as batteries moved from split units to single bidirectional units; battery charging is not comparable "
              "across it.", "", "docs/data_dictionary.md")
        p.require("series_break.battery", "inside or within 7 days of the battery transition", ["battery"])
    if JUNE_2022_SUSPENSION[0] <= day <= JUNE_2022_SUSPENSION[1]:
        p.add("caveat.june_2022_finding", "recorded finding", CAVEATS["june_2022_finding"][0], "", "docs/findings.md")
        p.require("caveat.june_2022_finding", "inside the June 2022 suspension", CAVEATS["june_2022_finding"][1])
    elif f["suspended_intervals"]:
        p.add("caveat.unverified_suspension", "caveat on the suspension flag", CAVEATS["unverified_suspension"][0], "",
              "docs/data_dictionary.md")
        p.require("caveat.unverified_suspension", "suspension flag outside June 2022", CAVEATS["unverified_suspension"][1])
    if f["intervals_without_scada"]:
        p.add("caveat.missing_scada", "caveat on generation", CAVEATS["missing_scada"][0], "", "docs/data_dictionary.md")
        p.require("caveat.missing_scada", "intervals with no SCADA", CAVEATS["missing_scada"][1])

    p.add("verdict", "what the answer must say about causes", "The facts describe what happened and what happened "
          "at the same time; they record no causes. Say plainly whether these facts explain the day's price movement.",
          "", "explainer/pack.py")
    p.require("verdict", "say whether the facts explain the price movement", ["explain"])

    for key, text in GLOSSARY.items():
        p.add(f"glossary.{key}", "definition", text, "", "docs/data_dictionary.md")

    if interval:
        _add_interval(con, p, region, day, interval)

    return {
        "region": region,
        "market_date": str(day),
        "interval": interval,
        "time_basis": "NEM market time (AEST, UTC+10, no daylight saving). Times are interval ends; intervals are "
                      "5 minutes.",
        "disclaimer": DISCLAIMER,
        "facts": p.facts,
        "required": p.required,
        "queries": {name: " ".join(sql.split()) for name, sql in QUERIES.items()},
    }


def _add_interval(con, p: Pack, region: str, day: date, interval: str) -> None:
    hours, minutes = (int(x) for x in interval.split(":"))
    end = datetime(day.year, day.month, day.day) + timedelta(hours=hours, minutes=minutes)
    params = {"region": region, "interval_end": end}
    found = _rows(con, "interval", params)
    if not found:
        raise ValueError(f"no interval ending {interval} on {day} for {region}")
    x, src_i = found[0], "marts.mart_region_interval"
    p.add("interval.interval_end", "the chosen interval: end time", interval, "time", f"{src_i}.interval_end")
    for key, unit, text in (("price", "$/MWh", "price"), ("total_demand_mw", "MW", "operational demand"),
                            ("available_generation_mw", "MW", "available generation"),
                            ("net_interchange_mw", "MW", "net interchange (negative = importing)"),
                            ("market_suspended_code", "code", "market suspension flag code"),
                            ("apc_code", "code", "administered price cap flag code"),
                            ("total_generation_mw", "MW", "SCADA generation")):
        p.add(f"interval.{key}", f"the chosen interval: {text}", x[key], unit, f"{src_i}.{key}")
    for group in FUEL_GROUPS:
        if x[f"{group}_generation_mw"]:
            p.add(f"interval.{group}_generation_mw", f"the chosen interval: {group.replace('_', ' ')} generation",
                  x[f"{group}_generation_mw"], "MW", f"{src_i}.{group}_generation_mw")
    window = _rows(con, "interval_window", params)
    p.add("interval.window_prices", "prices 30 minutes either side, as time price pairs",
          "; ".join(f"{_time(w['interval_end'], day)} {w['price']:.2f}" for w in window), "$/MWh", f"{src_i}.price")
    for link in _rows(con, "interval_links", params):
        name = link["interconnector_name"]
        p.add(f"interval.ic.{name}.flow_into_region_mw", f"the chosen interval: {name} flow into {region}",
              link["flow_into_region_mw"], "MW", "marts.mart_interconnector_interval.mw_flow")
        p.add(f"interval.ic.{name}.is_binding", f"the chosen interval: {name} at a limit",
              "yes" if link["is_binding"] else "no", "", "marts.mart_interconnector_interval.is_binding")
