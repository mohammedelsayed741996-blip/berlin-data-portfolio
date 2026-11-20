"""Checks on the full analysis: run with the cached cross-validation, as the pipeline does."""

import json

import pytest

from timepref import config as C, pipeline


@pytest.fixture(scope="module")
def out():
    return pipeline.run()


def test_scoreboard_order(out):
    c = out["summary"]["completeness"]
    assert c["oracle"] == 1 and c["base_rate"] == 0
    assert c["ml_person"] > c["itch_eb"] > c["itch"]               # ML best; shrinkage helps theory
    assert c["ml_pooled"] < c["hyperbolic"]                         # person information matters most


def test_framing_effect_found(out):
    f = out["summary"]["framing"]["log_k"]
    assert f["ci_high"] < 0 and f["p_perm"] < 0.01


def test_magnitude_effect_found(out):
    m = out["summary"]["magnitude"]
    assert m["ci_high"] < 0 and m["share_lower_k_for_large"] > 0.6


def test_parameter_recovery(out):
    assert out["summary"]["recovery_r_log_k"] > 0.9


def test_text_pipeline_is_honest_about_generalisation(out):
    t = out["summary"]["text"]
    assert t["f1_random_split"] > t["f1_grouped_cv"]               # random splits flatter the classifier
    assert out["summary"]["weekly_r_classifier"] > out["summary"]["weekly_r_lexicon"]


def test_summary_written(out):
    s = json.loads((C.Paths().outputs / "summary.json").read_text())
    assert s["analysed"] == out["clean"]["pid"].nunique()
