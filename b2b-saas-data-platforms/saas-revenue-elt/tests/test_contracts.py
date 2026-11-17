import pytest

from saas_elt.contracts import MASK, load_contract, scan_pii, validate


@pytest.fixture(scope="module")
def invoices():
    return load_contract("billing_invoices")


def good_invoice(**kw):
    rec = {"invoice_id": "INV-000001", "account_id": "ACC-00001", "subscription_id": "SUB-00001",
           "invoice_date": "2026-07-01", "period_start": "2026-07-01", "period_end": "2026-07-31",
           "currency": "EUR", "amount_net": 100.0, "tax_rate": 0.19, "amount_gross": 119.0,
           "status": "open", "updated_at": "2026-07-01T22:10:00"}
    rec.update(kw)
    return rec


def test_valid_record_passes(invoices):
    assert validate(good_invoice(), invoices).ok


@pytest.mark.parametrize("change, reason", [
    ({"currency": "USD"}, "not_in_enum"),
    ({"amount_net": -5.0, "amount_gross": -5.95}, "below_min"),
    ({"invoice_id": "INV-1"}, "pattern_mismatch"),
    ({"invoice_date": "01.07.2026"}, "bad_type"),
    ({"amount_gross": 150.0}, "rule_failed: gross_equals_net_plus_tax"),
    ({"status": None}, "missing: status"),
])
def test_violations_are_named(invoices, change, reason):
    res = validate(good_invoice(**change), invoices)
    assert not res.ok
    assert any(reason in r for r in res.reasons)


def test_extra_field_is_drift_not_failure_when_allowed(invoices):
    res = validate(good_invoice(discount_eur=5.0), invoices)
    assert res.ok and res.extra_fields == ["discount_eur"]


def test_extra_field_fails_when_not_allowed():
    accounts = load_contract("crm_accounts")
    rec = {"account_id": "ACC-00001", "company_name": "Nordwerk GmbH", "country": "DE", "industry": "Retail",
           "segment": "SMB", "created_at": "2026-01-01T09:00:00", "updated_at": "2026-01-02T09:00:00",
           "contact_email": "anna@example.com"}
    res = validate(rec, accounts)
    assert not res.ok
    assert any("unexpected_fields" in r for r in res.reasons)
    assert any("pii_detected: email" in r for r in res.reasons)
    assert res.safe_record["contact_email"] == MASK


@pytest.mark.parametrize("value, kind", [
    ("mail me at max.mustermann@example.de", "email"),
    ("IBAN DE89 3704 0044 0532 0130 00", "iban"),
    ("call +49 30 1234567", "phone"),
])
def test_pii_scanner_masks_values(value, kind):
    found, masked = scan_pii({"note": value, "user_hash": "a" * 64})
    assert any(kind in f for f in found)
    assert masked["note"] == MASK
    assert masked["user_hash"] == "a" * 64


def test_unknown_contract():
    with pytest.raises(FileNotFoundError):
        load_contract("nope")
