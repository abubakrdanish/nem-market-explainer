from explainer.checks import check, render

PACK = {
    "region": "VIC1",
    "market_date": "2025-06-12",
    "facts": [
        {"id": "day.avg_price", "label": "average price", "value": 1786.27, "unit": "$/MWh"},
        {"id": "day.peak_demand_mw", "label": "highest operational demand of the day", "value": 7907.0, "unit": "MW"},
        {"id": "highest_price.interval_end", "label": "interval with the highest price: end time", "value": "19:55",
         "unit": "time"},
        {"id": "highest_price.price", "label": "interval with the highest price: price", "value": 17500.0,
         "unit": "$/MWh"},
        {"id": "median_30d.avg_price", "label": "median over the previous 30 days of the daily average price",
         "value": 111.17, "unit": "$/MWh"},
        {"id": "notable.high_price.intervals", "label": "intervals flagged high_price", "value": 40,
         "unit": "intervals"},
        {"id": "caveat.rooftop_solar", "label": "caveat", "value": "SCADA excludes rooftop solar.", "unit": ""},
    ],
    "required": [{"id": "notable.high_price", "reason": "flagged", "key_terms": []},
                 {"id": "caveat.rooftop_solar", "reason": "solar", "key_terms": ["rooftop"]}],
}


def answer(*sentences):
    return {"sentences": [{"text": t, "fact_ids": ids} for t, ids in sentences]}


GOOD = answer(
    ("The average price was $1,786.27/MWh against a 30-day median of $111.17/MWh.", ["day.avg_price", "median_30d.avg_price"]),
    ("Prices reached $17,500/MWh in the interval ending 19:55.", ["highest_price.price", "highest_price.interval_end"]),
    ("40 intervals were flagged as high-price.", ["notable.high_price.intervals"]),
    ("Generation figures exclude rooftop solar.", ["caveat.rooftop_solar"]),
)


def test_a_faithful_answer_passes():
    report = check(GOOD, PACK)
    assert report["passed"], report
    assert report["flagged_wording"] == []


def test_a_planted_number_is_caught_as_not_in_the_pack():
    planted = answer(*[(s["text"], s["fact_ids"]) for s in GOOD["sentences"]],
                     ("Demand reached 8,412 MW.", ["day.peak_demand_mw"]))
    report = check(planted, PACK)
    assert {"sentence": 4, "kind": "number_not_in_pack", "value": "8,412"} in report["problems"]
    assert not report["passed"]


def test_a_real_number_cited_against_the_wrong_fact_is_misattributed():
    wrong = answer(("Demand reached 7907 MW at the price peak.", ["highest_price.price"]))
    assert check(wrong, PACK)["problems"] == [{"sentence": 0, "kind": "number_not_in_cited_facts", "value": "7907"}]


def test_a_time_not_in_the_cited_facts_is_caught():
    wrong = answer(("The highest price was $17,500 at 18:30.", ["highest_price.price", "highest_price.interval_end"]))
    assert check(wrong, PACK)["problems"] == [{"sentence": 0, "kind": "time_not_in_pack", "value": "18:30"}]


def test_a_rounded_figure_is_accepted_at_the_precision_quoted():
    rounded = answer(("The average was about $1,786/MWh.", ["day.avg_price"]))
    assert check(rounded, PACK)["problems"] == []


def test_dates_and_label_numbers_are_not_figures():
    text = answer(("On 2025-06-12 the 30-day median was $111.17/MWh.", ["median_30d.avg_price"]))
    assert check(text, PACK)["problems"] == []


def test_an_unknown_fact_id_is_caught():
    assert check(answer(("Prices were high.", ["day.made_up"])), PACK)["problems"][0]["kind"] == "unknown_fact_id"


def test_missing_notable_rules_and_caveats_are_reported():
    report = check(answer(("The average price was $1,786.27/MWh.", ["day.avg_price"])), PACK)
    assert [m["id"] for m in report["required_missing"]] == ["notable.high_price", "caveat.rooftop_solar"]


def test_a_caveat_cited_without_its_key_words_does_not_count():
    vague = answer(("40 intervals were high-price.", ["notable.high_price.intervals"]),
                   ("Some data is incomplete.", ["caveat.rooftop_solar"]))
    assert check(vague, PACK)["required_missing"] == [
        {"id": "caveat.rooftop_solar", "why": "cited without the words ['rooftop']"}]


def test_causal_and_outside_world_wording_is_flagged():
    report = check(answer(("Prices rose because of a heatwave.", ["day.avg_price"])), PACK)
    assert report["flagged_wording"] == [
        {"sentence": 0, "reasons": ["causal wording: because", "outside-world term: heatwave"]}]


def test_saying_the_evidence_does_not_explain_the_move_is_detected():
    honest = answer(("The facts do not explain why the price rose.", ["day.avg_price"]))
    assert check(honest, PACK)["says_unexplained"]


def test_render_marks_failing_sentences():
    planted = answer(("Demand reached 8,412 MW.", ["day.peak_demand_mw"]))
    text = render(planted, check(planted, PACK))
    assert text.startswith("[!] Demand reached 8,412 MW.")
    assert "number not in pack: 8,412" in text


def test_too_few_sentences_fail_the_length_check():
    report = check(answer(("The average price was $1,786.27/MWh.", ["day.avg_price"])), PACK)
    assert not report["length_ok"] and not report["passed"]


def test_a_repeated_sentence_is_caught():
    looped = answer(*[(s["text"], s["fact_ids"]) for s in GOOD["sentences"]],
                    ("40 intervals were flagged as high-price.", ["notable.high_price.intervals"]))
    report = check(looped, PACK)
    assert report["repeated_sentences"] == [4]
    assert not report["passed"]


def test_cut_off_output_fails():
    report = check({"sentences": [], "invalid_output": '{"sentences": [{"text": "The'}, PACK)
    assert report["invalid_output"] and not report["passed"]
