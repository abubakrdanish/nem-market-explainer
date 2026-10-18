import json
import shutil
from datetime import date

import duckdb
import pytest

from explainer import __main__ as cli
from explainer import ollama
from explainer.checks import check
from explainer.pack import build_pack, connect

DAY = date(2026, 9, 1)


def facts(pack):
    return {f["id"]: f["value"] for f in pack["facts"]}


def test_the_pack_matches_the_marts(fixture_marts):
    with connect(fixture_marts) as con:
        pack = build_pack(con, "NSW1", DAY)
        avg, peak = con.execute("select round(avg_price, 2), round(peak_demand_mw) from marts.mart_region_daily "
                                "where region_id = 'NSW1' and market_date = ?", [DAY]).fetchone()
    f = facts(pack)
    assert f["day.avg_price"] == avg
    assert f["day.peak_demand_mw"] == peak
    assert f["day.intervals"] == 12
    assert f["highest_price.interval_end"] == "01:00"


def test_every_fact_has_an_id_label_value_unit_and_source(fixture_marts):
    with connect(fixture_marts) as con:
        pack = build_pack(con, "SA1", DAY)
    ids = [f["id"] for f in pack["facts"]]
    assert len(ids) == len(set(ids))
    assert all(set(f) == {"id", "label", "value", "unit", "source"} and f["source"] for f in pack["facts"])
    assert "Not energy market advice" in pack["disclaimer"]
    assert set(pack["queries"]) >= {"day", "notable", "interconnectors"}


def test_missing_comparisons_say_no_data(fixture_marts):
    with connect(fixture_marts) as con:
        f = facts(build_pack(con, "NSW1", DAY))
    assert f["previous_day.missing"] == "no data"
    assert f["median_30d.missing"] == "no data"
    assert f["events.none"] == "none recorded"
    assert f["notable.none"] == "none"


def test_the_connection_is_read_only(fixture_marts):
    with connect(fixture_marts) as con, pytest.raises(duckdb.InvalidInputException):
        con.execute("create table marts.x (i integer)")


def test_an_unknown_date_is_an_error(fixture_marts):
    with connect(fixture_marts) as con, pytest.raises(ValueError, match="no data"):
        build_pack(con, "NSW1", date(2020, 1, 1))


@pytest.fixture
def planted(fixture_marts, tmp_path):
    """A copy of the fixture marts with a notable interval, negative prices and a June 2022 day planted."""
    path = tmp_path / "planted.duckdb"
    shutil.copy(fixture_marts, path)
    with duckdb.connect(str(path)) as con:
        con.execute("""insert into marts.mart_notable_intervals (interval_start, interval_end, market_date, region_id,
                       rule, rule_description, rule_value, rule_threshold, price)
                       values ('2026-09-01 00:25', '2026-09-01 00:30', '2026-09-01', 'NSW1', 'high_price', 'test',
                               1600, 1500, 1600)""")
        con.execute("update marts.mart_region_daily set negative_price_intervals = 30 where region_id = 'NSW1'")
        con.execute("""insert into marts.mart_region_daily select * replace (date '2026-08-31' as market_date,
                       avg_price / 4 as avg_price, -5.0 as max_price)
                       from marts.mart_region_daily where region_id = 'NSW1'""")
        shift = "interval (date '2026-09-01' - date '2022-06-18') day"
        con.execute(f"""insert into marts.mart_region_interval select * replace (interval_start - {shift} as interval_start,
                        interval_end - {shift} as interval_end, date '2022-06-18' as market_date)
                        from marts.mart_region_interval where region_id = 'TAS1'""")
        con.execute("""insert into marts.mart_region_daily select * replace (date '2022-06-18' as market_date)
                       from marts.mart_region_daily where region_id = 'TAS1'""")
    return path


def test_flagged_rules_and_caveats_become_required(planted):
    with connect(planted) as con:
        pack = build_pack(con, "NSW1", DAY)
    assert [r["id"] for r in pack["required"]] == [
        "compare.avg_price.vs_median_30d", "compare.avg_price.vs_previous_day", "compare.max_price.vs_median_30d",
        "compare.max_price.vs_previous_day", "compare.peak_demand_mw.vs_median_30d",
        "compare.peak_demand_mw.vs_previous_day", "notable.high_price", "caveat.rooftop_solar", "verdict"]
    assert facts(pack)["notable.high_price.intervals"] == 1


def test_comparisons_give_a_ratio_and_a_difference(planted):
    with connect(planted) as con:
        f = facts(build_pack(con, "NSW1", DAY))
    assert f["compare.avg_price.vs_previous_day.ratio"] == 4.0
    assert f["compare.avg_price.vs_previous_day.difference"] == round(f["day.avg_price"] * 3 / 4, 2)
    # The previous day's planted maximum is negative, so a ratio would mislead.
    assert f["compare.max_price.vs_previous_day.ratio"].startswith("not meaningful")
    assert f["compare.avg_price.vs_median_30d.difference"] == round(f["day.avg_price"] * 3 / 4, 2)


def test_a_june_2022_day_carries_the_recorded_finding(planted):
    with connect(planted) as con:
        pack = build_pack(con, "TAS1", date(2022, 6, 18))
    assert "caveat.june_2022_finding" in [r["id"] for r in pack["required"]]
    assert "$300/MWh" in facts(pack)["caveat.june_2022_finding"]


def test_an_interval_adds_its_own_facts(fixture_marts):
    with connect(fixture_marts) as con:
        f = facts(build_pack(con, "VIC1", DAY, "00:30"))
    assert f["interval.interval_end"] == "00:30"
    assert f["interval.window_prices"].startswith("00:05 ")
    assert "interval.ic.Basslink.is_binding" in f


def fake_answer(pack):
    f = facts(pack)
    return {"model": "fake", "seconds": 0.1, "sentences": [
        {"text": f"The average price was ${f['day.avg_price']}/MWh.", "fact_ids": ["day.avg_price"]},
        {"text": "There is no earlier day to compare with.",
         "fact_ids": [r["id"] + ".missing" for r in pack["required"] if r["id"].startswith("compare.")]},
        {"text": f"The highest price was ${f['day.max_price']}/MWh.", "fact_ids": ["day.max_price"]},
        {"text": "These facts do not explain the price movement.", "fact_ids": ["verdict"]}]}


def test_the_cli_prints_the_answer_checks_and_disclaimer(fixture_marts, monkeypatch, capsys):
    monkeypatch.setattr(ollama, "chat", lambda pack, model: fake_answer(pack))
    code = cli.main(["NSW1", "2026-09-01", "--warehouse", str(fixture_marts)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Checks: passed" in out
    assert out.strip().endswith("Not energy market advice or financial advice.")


def test_a_hallucinated_number_fails_the_cli(fixture_marts, monkeypatch, capsys):
    def hallucinate(pack, model):
        return {"model": "fake", "seconds": 0.1, "sentences": [
            {"text": "Prices reached $8,412/MWh during a heatwave.", "fact_ids": ["day.max_price"]}]}
    monkeypatch.setattr(ollama, "chat", hallucinate)
    assert cli.main(["NSW1", "2026-09-01", "--warehouse", str(fixture_marts)]) == 1
    out = capsys.readouterr().out
    assert "number not in pack: $8,412" in out
    assert "outside-world term: heatwave" in out


def test_pack_only_does_not_call_the_model(fixture_marts, monkeypatch, capsys):
    monkeypatch.setattr(ollama, "chat", lambda *a: pytest.fail("model called"))
    assert cli.main(["SA1", "2026-09-01", "--pack-only", "--warehouse", str(fixture_marts)]) == 0
    assert json.loads(capsys.readouterr().out)["region"] == "SA1"


def test_the_model_request_stays_local_and_deterministic(monkeypatch, fixture_marts):
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"message": {"content": '{"sentences": []}'}, "total_duration": 1e9}).encode()

    def fake_urlopen(request, timeout):
        sent["url"], sent["body"] = request.full_url, json.loads(request.data)
        return Response()

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)
    with connect(fixture_marts) as con:
        pack = build_pack(con, "NSW1", DAY)
    answer = ollama.chat(pack)
    assert sent["url"].startswith("http://localhost:11434/")
    assert sent["body"]["model"] == "qwen3:4b" and sent["body"]["think"] is False
    assert sent["body"]["options"]["temperature"] == 0
    assert "day.avg_price" in sent["body"]["messages"][1]["content"]
    assert check(answer, pack)["sentences"] == 0
