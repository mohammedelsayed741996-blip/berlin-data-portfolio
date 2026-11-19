"""Synthetic clients, transactions, typologies and a fictional watchlist for a mobile broker.

Normal clients deposit, trade and sometimes withdraw. A few hundred clients carry
planted suspicious behaviour (the typologies in config.TYPOLOGIES). Some legitimate
clients look unusual on purpose (an inheritance, a salary just under EUR 10,000), so the
monitoring rules produce false positives as in real life.

Names are random syllable combinations; account numbers and devices are random hashes.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from . import config as C

FIRST = ["Aren", "Bela", "Corin", "Dalia", "Eskil", "Fenna", "Garo", "Hedda", "Ilan", "Jorun", "Kasimir", "Liora",
         "Maren", "Nilo", "Orla", "Petra", "Quill", "Runa", "Soren", "Talia", "Ulric", "Vesna", "Wendel", "Ysolde",
         "Zarek", "Anouk", "Bastin", "Cilla", "Doran", "Elvi"]
LAST_A = ["Ost", "Var", "Kel", "Bran", "Tor", "Mel", "Sand", "Hav", "Lind", "Rau", "Fal", "Grim", "Wes", "Dorn", "Elm"]
LAST_M = ["", "en", "er", "il", "am", "or", "us", "ad"]
LAST_B = ["rin", "dahl", "mann", "berg", "ek", "ova", "sted", "holm", "ard", "ius", "elle", "ner", "quist", "ow"]
OCCUPATIONS = {"employee": 0.58, "self-employed": 0.12, "student": 0.12, "retired": 0.12, "cash-intensive business": 0.06}
INCOME = {"employee": 52_000, "self-employed": 70_000, "student": 9_000, "retired": 30_000, "cash-intensive business": 60_000}


def _hash(rng, prefix: str) -> str:
    return prefix + hashlib.sha1(rng.bytes(8)).hexdigest()[:12]


def _name(rng) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST_A)}{rng.choice(LAST_M)}{rng.choice(LAST_B)}"


def make_clients(rng: np.random.Generator) -> pd.DataFrame:
    n = C.N_CLIENTS
    occ = rng.choice(list(OCCUPATIONS), size=n, p=list(OCCUPATIONS.values()))
    income = np.array([INCOME[o] for o in occ]) * rng.lognormal(0, 0.35, n)
    expected = np.clip(income / 12 * rng.uniform(0.03, 0.15, n), 50, None)
    residence = rng.choice(list(C.RESIDENCE), size=n, p=list(C.RESIDENCE.values()))
    onboard = pd.to_datetime("2022-01-01") + pd.to_timedelta(rng.integers(0, 1730, n), unit="D")
    pep = rng.random(n) < 0.004
    score = (occ == "cash-intensive business") * 2 + pep * 3 + (residence != "DE") * 1 + (income > 150_000) * 1
    risk = np.where(score >= 3, "high", np.where(score >= 1, "medium", "low"))
    # A share of high-risk clients get the high rating from the onboarding questionnaire as well
    bump = rng.random(n) < 0.03
    risk = np.where(bump, "high", risk)
    cycle = pd.Series(risk).map(C.PERIODIC_REVIEW_MONTHS).values
    months_since = np.where(rng.random(n) < 0.97, rng.uniform(0, 1, n) * (cycle - 1), cycle + rng.uniform(1, 8, n))
    last_review = pd.to_datetime(C.END) - pd.to_timedelta(np.round(months_since * 30.4), unit="D")
    last_review = np.maximum(last_review, onboard)
    df = pd.DataFrame({
        "client_id": [f"C{i:06d}" for i in range(1, n + 1)],
        "name": [_name(rng) for _ in range(n)],
        "birth_year": rng.integers(1950, 2006, n),
        "onboarding_date": onboard.strftime("%Y-%m-%d"),
        "residence": residence,
        "occupation": occ,
        "declared_income_eur": income.round(-2),
        "expected_monthly_deposit_eur": expected.round(0),
        "pep": pep,
        "risk_rating": risk,
        "last_review_date": pd.Series(last_review).dt.strftime("%Y-%m-%d"),
        "device_id": [_hash(rng, "D") for _ in range(n)],
        "payout_account": [_hash(rng, "IBAN") for _ in range(n)],
        "funding_account": [_hash(rng, "IBAN") for _ in range(n)],
        "card_token": [_hash(rng, "CARD") for _ in range(n)],
    })
    # The overdue-review problem: a batch of high-risk clients last reviewed long ago
    high = df.index[df["risk_rating"] == "high"]
    stale = rng.choice(high, size=min(28, len(high)), replace=False)
    df.loc[stale, "last_review_date"] = (pd.to_datetime(C.END) - pd.to_timedelta(rng.integers(400, 700, len(stale)), unit="D")).strftime("%Y-%m-%d")
    return df


class TxBuilder:
    def __init__(self, rng):
        self.rng = rng
        self.rows = []

    def add(self, client, date, typ, amount, channel="SEPA", counterparty=None, country="DE", psp=""):
        if counterparty is None:
            counterparty = client.funding_account if typ.startswith("DEPOSIT") and channel == "SEPA" else (
                client.card_token if channel == "CARD" else (client.payout_account if typ == "WITHDRAWAL" else ""))
        own = counterparty in (client.funding_account, client.card_token, client.payout_account)
        self.rows.append((client.client_id, pd.Timestamp(date).strftime("%Y-%m-%d"), str(typ), round(float(amount), 2),
                          channel, psp, counterparty, country, own))

    def frame(self) -> pd.DataFrame:
        df = pd.DataFrame(self.rows, columns=["client_id", "date", "type", "amount_eur", "channel", "psp",
                                              "counterparty", "counterparty_country", "own_account"])
        df = df[(df["date"] >= C.START) & (df["date"] <= C.END)].sort_values(["date", "client_id"]).reset_index(drop=True)
        df.insert(0, "tx_id", [f"T{i:08d}" for i in range(1, len(df) + 1)])
        return df


def _day(rng, month: str, lo: int = 1, hi: int = 28) -> pd.Timestamp:
    return pd.Timestamp(f"{month}-01") + pd.Timedelta(days=int(rng.integers(lo - 1, hi)))


def normal_activity(tb: TxBuilder, clients: pd.DataFrame, rng) -> None:
    for c in clients.itertuples():
        if c.onboarding_date > C.END:
            continue
        for m in C.MONTHS:
            if f"{m}-28" < c.onboarding_date or rng.random() > 0.62:
                continue
            k = rng.poisson(1.1)
            dep_total = 0.0
            for _ in range(k):
                card = rng.random() < 0.3
                amt = c.expected_monthly_deposit_eur * rng.lognormal(0, 0.6)
                tb.add(c, _day(rng, m), "DEPOSIT", amt, "CARD" if card else "SEPA",
                       psp=("PSP-B" if rng.random() < 0.4 else "PSP-A") if card else "")
                dep_total += amt
            for _ in range(rng.poisson(2.0)):
                tb.add(c, _day(rng, m), rng.choice(["BUY", "SELL"], p=[0.6, 0.4]), max(20, c.expected_monthly_deposit_eur * rng.lognormal(-0.3, 0.7)))
            if rng.random() < 0.08:
                tb.add(c, _day(rng, m), "WITHDRAWAL", max(50, (dep_total or c.expected_monthly_deposit_eur) * rng.uniform(0.3, 1.5)))
    # Legitimate but unusual: one-off large transfers (inheritance, house sale, bonus)
    big = clients.sample(frac=0.02, random_state=int(rng.integers(1e9)))
    for c in big.itertuples():
        m = rng.choice(C.MONTHS)
        tb.add(c, _day(rng, m), "DEPOSIT", rng.uniform(15_000, 90_000))
        for _ in range(3):
            tb.add(c, _day(rng, m, 5, 28), "BUY", rng.uniform(3_000, 20_000))
    # Legitimate: a spouse or parent pays in from their own account
    family = clients.sample(frac=0.012, random_state=int(rng.integers(1e9)))
    for c in family.itertuples():
        payers = [_hash(rng, "IBAN") for _ in range(int(rng.integers(2, 4)))]
        for m in rng.choice(C.MONTHS, size=int(rng.integers(1, 4)), replace=False):
            for payer in payers:
                tb.add(c, _day(rng, m), "DEPOSIT", rng.uniform(200, 3_000), counterparty=payer)
    # Legitimate: family support from abroad, sometimes from a high-risk jurisdiction
    abroad = clients.sample(frac=0.003, random_state=int(rng.integers(1e9)))
    for c in abroad.itertuples():
        tb.add(c, _day(rng, rng.choice(C.MONTHS)), "DEPOSIT", rng.uniform(500, 4_000), counterparty=_hash(rng, "IBAN"),
               country=str(rng.choice(C.HIGH_RISK_JURISDICTIONS)))
    # Legitimate: salary-sized repeated deposits just below EUR 10,000 (high earners saving monthly)
    savers = clients[clients["declared_income_eur"] > 120_000].sample(frac=0.5, random_state=int(rng.integers(1e9)))
    for c in savers.itertuples():
        for m in rng.choice(C.MONTHS, size=4, replace=False):
            for _ in range(int(rng.integers(1, 4))):
                tb.add(c, _day(rng, m), "DEPOSIT", rng.uniform(8_500, 9_900))


def plant_typologies(tb: TxBuilder, clients: pd.DataFrame, rng) -> pd.DataFrame:
    eligible = clients[(~clients["pep"]) & (clients["onboarding_date"] < "2025-09-01")].copy()
    truth = []
    used = set()

    def pick(n, mask=None):
        pool = eligible if mask is None else eligible[mask(eligible)]
        pool = pool[~pool["client_id"].isin(used)]
        s = pool.sample(n, random_state=int(rng.integers(1e9)))
        used.update(s["client_id"])
        return s

    def window():
        i = int(rng.integers(0, len(C.MONTHS) - 4))
        return C.MONTHS[i:i + int(rng.integers(3, 5))]

    for c in pick(C.TYPOLOGIES["T1 structuring"]).itertuples():
        w = window()
        for m in w[:3]:
            for _ in range(int(rng.integers(3, 7))):
                tb.add(c, _day(rng, m), "DEPOSIT", rng.uniform(9_000, 9_950))
            tb.add(c, _day(rng, m, 20, 28), "BUY", rng.uniform(5_000, 15_000))
        truth.append((c.client_id, "T1 structuring", w[0], w[-1]))

    for c in pick(C.TYPOLOGIES["T2 pass-through"]).itertuples():
        w = window()
        for m in w[: int(rng.integers(2, 4))]:
            d = _day(rng, m, 1, 20)
            amt = rng.uniform(20_000, 60_000)
            tb.add(c, d, "DEPOSIT", amt, counterparty=_hash(rng, "IBAN"))
            tb.add(c, d + pd.Timedelta(days=int(rng.integers(1, 4))), "WITHDRAWAL", amt * rng.uniform(0.9, 0.98))
        truth.append((c.client_id, "T2 pass-through", w[0], w[-1]))

    for c in pick(C.TYPOLOGIES["T3 third-party funding"]).itertuples():
        w = window()
        for m in w:
            for _ in range(int(rng.integers(3, 7))):
                tb.add(c, _day(rng, m), "DEPOSIT", rng.uniform(1_000, 5_000), counterparty=_hash(rng, "IBAN"))
            tb.add(c, _day(rng, m, 15, 28), "BUY", rng.uniform(3_000, 12_000))
        truth.append((c.client_id, "T3 third-party funding", w[0], w[-1]))

    # Mule rings: card-funded, small amounts, quick round trip through a trade, payout to a shared account
    young = lambda d: d["occupation"].isin(["student", "employee"]) & (d["expected_monthly_deposit_eur"] < 400)  # noqa: E731
    members = pick(C.TYPOLOGIES["T4 mule ring"], young)
    for r, ring in enumerate(np.array_split(members.index, 6), start=1):
        shared_iban, shared_device = _hash(rng, "IBAN"), _hash(rng, "D")
        clients.loc[ring, "payout_account"] = shared_iban
        if r % 2:
            clients.loc[ring, "device_id"] = shared_device
        w = window()
        for idx in ring:
            cc = next(clients.loc[[idx]].itertuples())
            for m in w:
                for _ in range(int(rng.integers(4, 9))):
                    d = _day(rng, m, 1, 24)
                    amt = rng.uniform(300, 1_500)
                    tb.add(cc, d, "DEPOSIT", amt, "CARD", psp="PSP-A")
                    tb.add(cc, d + pd.Timedelta(days=1), "BUY", amt * 0.98)
                    tb.add(cc, d + pd.Timedelta(days=3), "SELL", amt * 0.97)
                    tb.add(cc, d + pd.Timedelta(days=4), "WITHDRAWAL", amt * 0.96, counterparty=shared_iban)
            truth.append((cc.client_id, "T4 mule ring", w[0], w[-1]))
    clients.attrs["rings"] = 6

    for c in pick(C.TYPOLOGIES["T5 high-risk jurisdiction"]).itertuples():
        w = window()
        for m in w[: int(rng.integers(2, 4))]:
            tb.add(c, _day(rng, m), "DEPOSIT", rng.uniform(3_000, 14_000), counterparty=_hash(rng, "IBAN"),
                   country=str(rng.choice(C.HIGH_RISK_JURISDICTIONS)))
        truth.append((c.client_id, "T5 high-risk jurisdiction", w[0], w[-1]))

    for c in pick(C.TYPOLOGIES["T6 profile mismatch"], lambda d: d["occupation"].isin(["student", "retired"])).itertuples():
        w = window()
        for m in w[:3]:
            for _ in range(int(rng.integers(2, 5))):
                tb.add(c, _day(rng, m), "DEPOSIT", rng.uniform(8_000, 30_000) if rng.random() < 0.5 else rng.uniform(10_000, 14_900))
            tb.add(c, _day(rng, m, 15, 28), "BUY", rng.uniform(10_000, 40_000))
        truth.append((c.client_id, "T6 profile mismatch", w[0], w[-1]))

    return pd.DataFrame(truth, columns=["client_id", "typology", "first_month", "last_month"])


def make_watchlist(clients: pd.DataFrame, rng) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A fictional sanctions and PEP list. A few clients match on purpose, with spelling variants."""
    rows = [{"entry_id": f"W{i:04d}", "list": "sanctions" if i <= 250 else "PEP", "name": _name(rng),
             "birth_year": int(rng.integers(1945, 2000))} for i in range(1, 401)]
    wl = pd.DataFrame(rows)
    # PEP clients appear on the PEP list under their own name
    peps = clients[clients["pep"]]
    pep_rows = pd.DataFrame({"entry_id": [f"W{401 + i:04d}" for i in range(len(peps))], "list": "PEP", "name": peps["name"].values,
                             "birth_year": peps["birth_year"].values})
    wl = pd.concat([wl, pep_rows], ignore_index=True)
    # Sanctioned clients: their name is a slightly different spelling of a sanctions entry
    targets = clients[(~clients["pep"]) & (clients["onboarding_date"] < "2026-06-01")].sample(C.SANCTIONED_CLIENTS, random_state=int(rng.integers(1e9)))
    truth = []
    for i, c in enumerate(targets.itertuples()):
        first, last = c.name.split(" ", 1)
        if i == 0:
            variant = f"{first} {last[:2]}{last[2] * 2}{last[3:]}"          # doubled letter
        elif i == 1:
            variant = f"{first} {last}h"                                    # transliteration ending
        else:
            variant = f"{first} {last[:2]}{last[3]}{last[2]}{last[4:]}"     # two letters swapped
        entry = f"W{900 + i:04d}"
        wl.loc[len(wl)] = [entry, "sanctions", variant, int(c.birth_year)]
        truth.append((c.client_id, entry))
    return wl, pd.DataFrame(truth, columns=["client_id", "entry_id"])


def generate(seed: int = C.SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    clients = make_clients(rng)
    tb = TxBuilder(rng)
    truth = plant_typologies(tb, clients, rng)
    normal_activity(tb, clients, rng)
    tx = tb.frame()
    wl, sanc = make_watchlist(clients, rng)
    return {"clients": clients, "transactions": tx, "typology_truth": truth, "watchlist": wl, "sanctions_truth": sanc}
