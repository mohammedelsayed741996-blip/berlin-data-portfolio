"""Synthetic issuer universe: credit quality, agency ratings, financials and share prices.

Each issuer has a latent credit score in rating notches (0 = AA, 14 = CCC). It
moves with sector shocks, idiosyncratic noise, slow deterioration episodes and
rare sudden jumps. The agency rating follows the latent score with a lag: it
moves only after the gap has been large for one to three months. That lag is
what an early-warning system can exploit, and the news feed (news.py) is
written from the same latent path, so companies in trouble produce worse news
before the agency acts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

SYLL_A = ["Nor", "Val", "Ber", "Sol", "Kar", "Lun", "Ost", "Mar", "Tel", "Hel", "Gra", "Ven", "Rhe", "Alt", "Fen",
          "Dor", "Sav", "Bri", "Eld", "Kor", "Lin", "Mel", "Tor", "Wes", "Zan", "Hav", "Cal", "Rov", "Ste", "Ard"]
SYLL_B = ["valt", "ex", "ion", "ara", "ent", "ora", "is", "en", "ax", "ova", "und", "ast", "eon", "ica", "ur", "yn"]
SUFFIX = {"DE": ["AG", "GmbH", "SE"], "FR": ["SA", "SAS"], "NL": ["NV", "BV"], "IT": ["SpA"], "AT": ["AG"], "ES": ["SA"]}
SECTOR_WORD = {
    "Real estate": ["Immobilien", "Property", "Wohnen"], "Automotive": ["Automotive", "Motoren", "Drive"],
    "Chemicals": ["Chemie", "Chemicals", "Materials"], "Retail": ["Handel", "Retail", "Stores"],
    "Utilities": ["Energie", "Power", "Utilities"], "Telecoms": ["Telekom", "Networks", "Connect"],
    "Industrials": ["Industrie", "Systems", "Technik"], "Transport & logistics": ["Logistik", "Transport", "Shipping"],
    "Healthcare": ["Health", "Pharma", "Medical"], "Consumer goods": ["Brands", "Foods", "Consumer"],
}


def months() -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(C.START, C.END, freq="M")]


def make_issuers(rng: np.random.Generator) -> pd.DataFrame:
    sectors = list(C.SECTORS)
    shares = np.array([C.SECTORS[s][0] for s in sectors])
    rows, used = [], set()
    for i in range(C.N_ISSUERS):
        sector = rng.choice(sectors, p=shares / shares.sum())
        country = "DE" if rng.random() < C.SECTORS[sector][2] else rng.choice(["FR", "NL", "IT", "AT", "ES"])
        while True:
            name = f"{rng.choice(SYLL_A)}{rng.choice(SYLL_B)} {rng.choice(SECTOR_WORD[sector])} {rng.choice(SUFFIX[country])}"
            if name not in used:
                used.add(name)
                break
        start_notch = int(np.clip(np.round(rng.normal(6.2, 2.4)), 0, 12))
        rows.append({"issuer_id": f"ISS{i + 1:04d}", "issuer_name": name, "sector": sector, "country": country,
                     "listed": bool(rng.random() < 0.6), "size": float(np.round(rng.lognormal(0, 0.6), 2)),
                     "start_rating": C.RATINGS[start_notch]})
    return pd.DataFrame(rows)


def simulate(issuers: pd.DataFrame, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    ms = months()
    T = len(ms)
    shock = {s: np.zeros(T) for s in C.SECTORS}
    for sector, start, length, size in C.SECTOR_SHOCKS:
        i0 = ms.index(start)
        shock[sector][i0:i0 + length] += size * C.SECTORS[sector][1]
    market = rng.normal(0.004, 0.035, T)

    path_rows, rating_rows, action_rows, fin_rows, eq_rows = [], [], [], [], []
    for iss in issuers.itertuples():
        s0 = C.RATINGS.index(iss.start_rating) + rng.normal(0, 0.2)
        s = s0
        r = C.RATINGS.index(iss.start_rating)
        outlook = "stable"
        gap_months = 0
        good_months = 0
        lag = int(rng.integers(1, 4))
        episode = 0.0          # remaining notches of a slow deterioration
        episode_rate = 0.0
        improving = 0.0
        prev = [s] * 4
        price = 100.0
        for t, m in enumerate(ms):
            # latent dynamics -------------------------------------------------
            ds = rng.normal(0, 0.07) + shock[iss.sector][t] + 0.035 * (s0 - s)
            if episode <= 0 and rng.random() < 0.008:
                episode = float(rng.uniform(1.6, 3.6))
                episode_rate = episode / rng.integers(4, 9)
            if episode > 0:
                step = min(episode, episode_rate * rng.uniform(0.6, 1.4))
                ds += step
                episode -= step
            if improving <= 0 and rng.random() < 0.007:
                improving = float(rng.uniform(1.0, 2.0))
            if improving > 0:
                step = min(improving, 0.25)
                ds -= step
                improving -= step
            jump = 0.0
            if rng.random() < 0.0025:
                jump = float(rng.uniform(2.0, 4.0))      # sudden event: failed deal, fraud, lost lawsuit
                ds += jump
            s = float(np.clip(s + ds, -0.4, 14.6))
            momentum = s - prev[-3]
            prev = (prev + [s])[-4:]

            # agency ------------------------------------------------------------
            gap = s - r
            action = None
            if gap > 1.0:
                gap_months += 1
            else:
                gap_months = 0
            if gap < -1.2:
                good_months += 1
            else:
                good_months = 0
            if jump > 0 and gap > 1.5:
                gap_months = max(gap_months, lag)          # sudden events get a fast reaction
            if gap_months >= lag:
                new_r = int(np.clip(np.round(s), r + 1, 14))
                action = ("downgrade", r, new_r)
                r, gap_months, lag = new_r, 0, int(rng.integers(1, 4))
                outlook = "negative" if s - r > 0.3 else "stable"
            elif good_months >= 4:
                new_r = int(np.clip(np.round(s), 0, r - 1))
                action = ("upgrade", r, new_r)
                r, good_months = new_r, 0
                outlook = "stable"
            else:
                new_outlook = "negative" if gap > 0.55 else ("positive" if gap < -0.9 else ("stable" if abs(gap) < 0.3 else outlook))
                # Agencies do not review every name every month, so many downgrades come without a prior outlook change.
                reviewed = rng.random() < 0.25 or new_outlook == "stable"
                if new_outlook != outlook and reviewed:
                    action_rows.append({"issuer_id": iss.issuer_id, "month": m, "action": f"outlook {new_outlook}",
                                        "from_rating": C.RATINGS[r], "to_rating": C.RATINGS[r]})
                    outlook = new_outlook
            if action:
                action_rows.append({"issuer_id": iss.issuer_id, "month": m, "action": action[0],
                                    "from_rating": C.RATINGS[action[1]], "to_rating": C.RATINGS[action[2]]})

            path_rows.append({"issuer_id": iss.issuer_id, "month": m, "latent_notch": round(s, 3),
                              "momentum_3m": round(momentum, 3), "stress_gap": round(s - r, 3),
                              "in_episode": episode > 0, "jump": jump > 0})
            rating_rows.append({"issuer_id": iss.issuer_id, "month": m, "rating": C.RATINGS[r], "notch": r,
                                "outlook": outlook})

            # share price for listed issuers ---------------------------------------
            if iss.listed:
                ret = market[t] * 1.1 - 0.035 * ds + rng.normal(0, 0.055)
                price *= float(np.exp(ret))
                eq_rows.append({"issuer_id": iss.issuer_id, "month": m, "close": round(price, 2)})

            # quarterly financials, published two months after quarter end -----------
            if int(m[5:]) in (3, 6, 9, 12):
                lev = max(0.2, 1.2 + 0.38 * s + rng.normal(0, 0.45))
                cov = max(0.4, 13.0 - 0.75 * s + rng.normal(0, 1.2))
                fin_rows.append({"issuer_id": iss.issuer_id, "quarter_end": m,
                                 "published": (pd.Period(m, freq="M") + 2).strftime("%Y-%m"),
                                 "net_debt_to_ebitda": round(lev, 2), "interest_coverage": round(cov, 2)})

    return {"latent": pd.DataFrame(path_rows), "ratings": pd.DataFrame(rating_rows),
            "rating_actions": pd.DataFrame(action_rows), "financials": pd.DataFrame(fin_rows),
            "equity": pd.DataFrame(eq_rows)}
