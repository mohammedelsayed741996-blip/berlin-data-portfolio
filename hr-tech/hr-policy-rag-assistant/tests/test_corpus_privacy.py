import pytest

from hrrag.corpus import parse
from hrrag.privacy import redact


def test_every_passage_has_metadata(passages):
    assert len(passages) > 40
    for p in passages:
        assert p.policy_id.startswith("HR-") and p.version and p.effective_date and p.audience in {"employee", "manager", "hr"}
        assert len(p.text.split()) > 15


def test_policies_name_only_the_fictional_company(passages):
    text = " ".join(p.text for p in passages).lower()
    assert "tesla" not in text
    assert "northlake-motors.example" in text                       # reserved example domain, not a real company


def test_front_matter_is_required(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# no header\n## A\ntext")
    with pytest.raises(ValueError):
        parse(f)


@pytest.mark.parametrize("text,kinds", [
    ("my name is Lena Fischer", ["NAME"]),
    ("write to lena.f@example.com", ["EMAIL"]),
    ("I am E-204871", ["EMPLOYEE_ID"]),
    ("call +49 151 2345 6789", ["PHONE"]),
    ("IBAN DE89 3704 0044 0532 0130 00", ["IBAN"]),
    ("Steuer-ID 12345678901", ["TAX_ID"]),
    ("born 03.04.1995", ["DATE"]),
])
def test_redaction(text, kinds):
    out, found = redact(text)
    assert found == kinds
    assert "[" in out


def test_ordinary_questions_are_untouched():
    for q in ("How many days per week can I work from home?", "i am sick today, who do I tell?", "Is the night allowance 25 percent?"):
        assert redact(q) == (q, [])
