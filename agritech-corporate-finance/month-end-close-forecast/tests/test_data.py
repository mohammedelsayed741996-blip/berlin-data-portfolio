import re

import pandas as pd

from close_forecast import close_checks, config as C, data_generator
from close_forecast.fiscal import cutoff_date, fiscal_period, fiscal_year


def test_fiscal_calendar():
    assert fiscal_year("2026-09") == "2026/27"
    assert fiscal_year("2026-06") == "2025/26"
    assert fiscal_period("2026-07") == 1 and fiscal_period("2027-06") == 12
    # 1 Oct 2026 is a Thursday: working days 1-3 are Thu, Fri, Mon.
    assert cutoff_date("2026-09", 3).isoformat() == "2026-10-05"


def test_generator_is_deterministic():
    a = data_generator.generate()["gl_items"]
    b = data_generator.generate()["gl_items"]
    pd.testing.assert_frame_equal(a, b)


def test_only_the_planted_document_is_unbalanced(tables):
    sums = tables["gl_items"].groupby(["company_code", "doc_no"])["amount_eur"].sum().round(2)
    bad = sums[sums != 0]
    assert len(bad) == 1
    assert bad.iloc[0] == C.PLANTED_CLOSE_ISSUES["unbalanced_document"]["difference"]


def test_trial_balance_nets_to_zero_except_planted_difference(tables):
    tb = close_checks.trial_balance(tables)
    by_entity = tb.groupby("company_code")["amount_eur"].sum().round(2)
    assert by_entity["AT10"] == 0 and by_entity["FR10"] == 0
    assert by_entity["DE10"] == C.PLANTED_CLOSE_ISSUES["unbalanced_document"]["difference"]


def test_no_personal_data_only_pseudonymous_codes(tables):
    gl = tables["gl_items"]
    assert gl["user_id"].str.fullmatch(r"U\d{2}|BATCH").all()
    vendors = gl.loc[gl["vendor"] != "", "vendor"]
    assert vendors.str.fullmatch(r"V\d{4}").all()
    text = " ".join(gl["text"].unique())
    assert not re.search(r"@|\+49|IBAN|DE\d{20}", text)


def test_budget_covers_every_cost_center_and_month(tables):
    b = tables["budget"]
    assert b["month"].nunique() == 36
    assert set(b["cost_center"]) == set(C.COST_CENTERS)


def test_seasonality_is_realistic(tables):
    s = tables["sales"]
    beet = s[(s["crop"] == "sugarbeet") & (s["fiscal_year"] == "2025/26")].groupby("period")["units"].sum()
    assert beet.loc[7:9].sum() > 5 * beet.loc[1:3].sum()           # Jan-Mar vs Jul-Sep
    pay = tables["gl_items"]
    pay = pay[(pay["gl_account"] == "6000") & (pay["fiscal_year"] == "2025/26")].groupby("month")["amount_eur"].sum()
    assert pay["2025-11"] > 1.4 * pay["2025-10"]                     # 13th salary


def test_margins_are_plausible_for_a_seed_company(tables):
    gl = tables["gl_items"]
    fy = gl[(gl["fiscal_year"] == "2025/26") & gl["gl_account"].str[0].isin(["4", "5", "6"])]
    fy = fy[fy["partner_company"] == ""]
    revenue = -fy[fy["gl_account"].str[0] == "4"]["amount_eur"].sum()
    ebit = -fy["amount_eur"].sum()
    rnd = fy[fy["functional_area"] == "RND"]["amount_eur"].sum()
    assert 0.10 < ebit / revenue < 0.20
    assert 0.15 < rnd / revenue < 0.22
