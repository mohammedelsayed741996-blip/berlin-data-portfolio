import pandas as pd


def test_bronze_problems_are_cleaned(lake):
    d, out = lake
    assert out["silver"]["duplicates_removed"] == out["planted"]["duplicate_invoices"]
    assert out["silver"]["due_dates_derived"] == out["planted"]["missing_due_dates"] > 0
    assert out["quality"]["passed"].all()


def test_german_number_format_is_parsed():
    from agentlake.lakehouse import _de_number, _num
    assert _num(_de_number(1234567.5)) == 1234567.5 and _num("12.345,60") == 12345.6


def test_gold_has_no_personal_data_beyond_role_mailboxes(lake):
    d, _ = lake
    ar = pd.read_csv(d / "gold" / "account_ar.csv")
    assert ar["contact_email"].str.match(r"^ap@account-\d{3}\.example\.(de|ae)$").all()
    assert ar["name"].nunique() == len(ar)


def test_every_owner_has_accounts(lake):
    d, _ = lake
    ar = pd.read_csv(d / "gold" / "account_ar.csv")
    assert set(ar["owner"]) == {"AM01", "AM02", "AM03", "AM04", "AM05", "AM06"}
