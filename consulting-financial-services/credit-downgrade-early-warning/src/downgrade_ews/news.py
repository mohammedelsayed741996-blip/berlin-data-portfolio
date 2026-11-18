"""Synthetic financial news in English and German.

Articles are written from templates, but the topic mix of each issuer follows its
latent credit path: a company sliding toward a downgrade gets more profit
warnings, refinancing stories and covenant talk, though never only those. Healthy
companies also get bad headlines, stressed ones put out upbeat press releases,
some articles deny problems, and sector stories mention a company without being
about it. The model has to cope with all of that.

No article names a person. Roles are used instead ("the chief financial officer").
The true topic of each article is kept in a separate column for validation only;
the models never see it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C

SOURCES_EN = ["Euro Credit Wire", "Market Ledger", "Continental Business Review", "Bond Desk Daily"]
SOURCES_DE = ["Finanzblatt", "Handelsdienst", "Börsenkurier", "Wirtschaftsecho"]
CITIES = ["Hamburg", "Lyon", "Rotterdam", "Turin", "Linz", "Bilbao", "Leipzig", "Dortmund", "Lille", "Graz"]

# topic: list of (headline, body) templates. Placeholders: {co} {pct} {pct2} {amt} {city} {q} {yr} {sector}
EN = {
    # --- negative, linked to deterioration -------------------------------------------------
    "profit_warning": [
        ("{co} issues profit warning, cuts full-year EBITDA outlook by {pct}%",
         "{co} lowered its full-year EBITDA guidance by about {pct}%, citing weaker orders and higher input costs. The shares fell sharply in early trading."),
        ("{co} warns on profits as demand slows",
         "In an unscheduled statement, {co} said operating profit for {yr} would come in well below its earlier forecast. Management blamed a sharp slowdown in its core markets."),
    ],
    "guidance_cut": [
        ("{co} trims revenue guidance for {yr}",
         "{co} now expects revenue to decline by {pct2}% this year after a weak {q}. The company said cost measures would only take effect next year."),
        ("{co} lowers outlook after weak {q}",
         "Results for {q} missed expectations and {co} reduced its outlook. Free cash flow was negative for the second quarter in a row."),
    ],
    "covenant": [
        ("{co} seeks covenant waiver from lenders",
         "{co} has asked its banks to relax the leverage covenant on its revolving credit facility. People familiar with the talks said the company expects to breach the threshold at the next test date."),
        ("Lenders grant {co} temporary covenant relief",
         "{co} reached an agreement with its lending banks to reset financial covenants until the end of {yr}. The margin on the facility rises by {pct2}0 basis points."),
    ],
    "refinancing": [
        ("{co} postpones bond issue amid weak investor demand",
         "{co} pulled a planned EUR {amt} million bond after investors demanded a much higher coupon. About EUR {amt} million of debt matures within the next 18 months."),
        ("Refinancing worries weigh on {co}",
         "Analysts are increasingly concerned about how {co} will refinance maturities due next year. Its bonds traded at {cents} cents on the euro this week."),
    ],
    "liquidity": [
        ("{co} draws down credit line to shore up cash",
         "{co} drew EUR {amt} million from its revolving credit facility. The company said the step was precautionary, but cash burn in {q} was higher than expected."),
        ("{co} cash position under pressure",
         "Cash and equivalents at {co} fell by {pct}% in {q}. The company is reviewing asset sales to strengthen liquidity."),
    ],
    "cfo_exit": [
        ("{co} chief financial officer to step down with immediate effect",
         "{co} announced that its chief financial officer will leave the company with immediate effect. No reason was given; an interim CFO has been appointed."),
    ],
    "audit_delay": [
        ("{co} delays publication of annual report",
         "{co} postponed the release of its audited accounts, saying the auditor needs more time to review impairment tests. A new date has not been set."),
    ],
    "restructuring": [
        ("{co} to close {city} plant, cut {pct}0 jobs",
         "{co} plans to close its site in {city} as part of a restructuring programme. The company expects one-off costs of EUR {amt} million."),
        ("{co} launches restructuring programme",
         "{co} announced a cost-cutting programme after margins fell for several quarters. The plan includes job cuts and the sale of non-core businesses."),
    ],
    "impairment": [
        ("{co} books EUR {amt} million impairment",
         "{co} wrote down the value of several assets by EUR {amt} million, mainly in its {sector} business, and will report a net loss for {yr}."),
    ],
    "dividend_cut": [
        ("{co} suspends dividend to preserve cash",
         "{co} will not pay a dividend for {yr}. The board said protecting the balance sheet had priority."),
    ],
    "spread_widening": [
        ("{co} bonds slide as investors grow nervous",
         "Bonds issued by {co} fell for a fifth day, pushing the yield above {pct2}%. Credit default swaps on the company widened sharply."),
    ],
    "rating_outlook_negative": [
        ("Agency revises {co} outlook to negative",
         "A rating agency changed its outlook on {co} to negative, pointing to rising leverage and weaker cash generation. The rating itself was affirmed."),
    ],
    "rating_downgrade": [
        ("{co} downgraded by rating agency",
         "A rating agency cut its rating on {co} by one notch, citing higher leverage than expected. The outlook is negative."),
    ],
    # --- noise: sounds negative but is not about the issuer's credit -----------------------
    "denial": [
        ("{co} denies reports of liquidity problems",
         "{co} rejected a press report that it was struggling to refinance. A spokesperson said liquidity was ample and all maturities were covered."),
    ],
    "sector_noise": [
        ("{sector} sector faces weaker demand; {co} says it is not affected",
         "Several {sector} companies have warned on profits this month. {co} said its order book remained full and it confirmed its guidance."),
        ("Analysts cautious on {sector} after peer warnings",
         "After a string of warnings from competitors, analysts trimmed estimates for the {sector} sector. {co} was mentioned as one of the more resilient names."),
    ],
    "lawsuit": [
        ("{co} faces lawsuit over supply contract",
         "A former customer has sued {co} over a disputed supply contract. The company said the claim was without merit and the amount was not material."),
    ],
    # --- neutral ---------------------------------------------------------------------------
    "agm": [
        ("{co} shareholders approve all agenda items at AGM",
         "Shareholders of {co} approved all resolutions at the annual general meeting, including the appointment of the auditor."),
    ],
    "board": [
        ("{co} appoints new supervisory board member",
         "{co} named a new member of its supervisory board, an industry veteran with experience in {sector}."),
    ],
    "results_inline": [
        ("{co} {q} results in line with expectations",
         "{co} reported {q} revenue and earnings broadly in line with analyst forecasts and confirmed its outlook for {yr}."),
    ],
    "esg": [
        ("{co} publishes sustainability report",
         "{co} released its annual sustainability report, setting a target to cut emissions by {pct}% by 2030."),
    ],
    # --- positive --------------------------------------------------------------------------
    "contract_win": [
        ("{co} wins EUR {amt} million contract",
         "{co} secured a multi-year contract worth about EUR {amt} million. The order supports growth in its {sector} business."),
    ],
    "guidance_raise": [
        ("{co} raises full-year guidance after strong {q}",
         "Strong demand in {q} led {co} to raise its full-year outlook. Margins improved by {pct2} percentage points."),
    ],
    "bond_success": [
        ("{co} bond issue heavily oversubscribed",
         "{co} placed a EUR {amt} million bond at a tight coupon. The order book was more than three times covered."),
    ],
    "deleveraging": [
        ("{co} sells non-core unit, cuts debt",
         "{co} agreed to sell a non-core division and will use the proceeds of EUR {amt} million to reduce net debt."),
    ],
    "rating_outlook_positive": [
        ("Agency revises {co} outlook to positive",
         "A rating agency changed its outlook on {co} to positive after a period of steady deleveraging."),
    ],
}

DE = {
    "profit_warning": [
        ("{co} senkt Prognose: Gewinnwarnung für {yr}",
         "{co} hat die Prognose für das operative Ergebnis um rund {pct} Prozent gesenkt. Als Grund nannte das Unternehmen schwache Aufträge und höhere Kosten."),
        ("Gewinnwarnung bei {co}",
         "Überraschend teilte {co} mit, dass das Ergebnis für {yr} deutlich unter den bisherigen Erwartungen liegen wird. Die Aktie gab deutlich nach."),
    ],
    "guidance_cut": [
        ("{co} nimmt Umsatzziel zurück",
         "Nach einem schwachen {q} rechnet {co} nun mit einem Umsatzrückgang von {pct2} Prozent. Der freie Cashflow war erneut negativ."),
    ],
    "covenant": [
        ("{co} verhandelt mit Banken über Covenants",
         "{co} hat seine Banken gebeten, die Finanzkennzahlen im Kreditvertrag zu lockern. Beim nächsten Stichtag droht ein Bruch der Verschuldungsgrenze."),
    ],
    "refinancing": [
        ("{co} verschiebt Anleihe wegen schwacher Nachfrage",
         "{co} hat eine geplante Anleihe über {amt} Millionen Euro abgesagt. In den nächsten 18 Monaten werden Schulden von {amt} Millionen Euro fällig."),
        ("Sorgen um Refinanzierung bei {co}",
         "Analysten fragen sich, wie {co} die Fälligkeiten des kommenden Jahres refinanzieren will. Die Anleihen notieren bei {cents} Prozent."),
    ],
    "liquidity": [
        ("{co} zieht Kreditlinie, Liquidität unter Druck",
         "{co} hat {amt} Millionen Euro aus der Kreditlinie gezogen. Der Mittelabfluss im {q} war höher als erwartet."),
    ],
    "cfo_exit": [
        ("Finanzvorstand von {co} geht mit sofortiger Wirkung",
         "Der Finanzvorstand von {co} verlässt das Unternehmen mit sofortiger Wirkung. Gründe wurden nicht genannt."),
    ],
    "audit_delay": [
        ("{co} verschiebt Veröffentlichung des Jahresabschlusses",
         "{co} hat die Vorlage des testierten Abschlusses verschoben. Der Abschlussprüfer benötige mehr Zeit für die Werthaltigkeitstests."),
    ],
    "restructuring": [
        ("{co} schließt Werk in {city}",
         "{co} will den Standort {city} im Rahmen eines Sparprogramms schließen. Es fallen {pct}0 Stellen weg."),
    ],
    "impairment": [
        ("{co} schreibt {amt} Millionen Euro ab",
         "{co} nimmt Abschreibungen von {amt} Millionen Euro vor und wird für {yr} einen Verlust ausweisen."),
    ],
    "dividend_cut": [
        ("{co} streicht Dividende",
         "{co} setzt die Dividende für {yr} aus, um die Liquidität zu schonen."),
    ],
    "spread_widening": [
        ("Anleihen von {co} unter Druck",
         "Die Anleihen von {co} fielen den fünften Tag in Folge, die Rendite stieg über {pct2} Prozent."),
    ],
    "rating_outlook_negative": [
        ("Ratingagentur senkt Ausblick für {co} auf negativ",
         "Eine Ratingagentur hat den Ausblick für {co} auf negativ gesenkt. Das Rating selbst wurde bestätigt."),
    ],
    "rating_downgrade": [
        ("Ratingagentur stuft {co} herab",
         "Eine Ratingagentur hat {co} um eine Stufe herabgestuft und verweist auf die gestiegene Verschuldung."),
    ],
    "denial": [
        ("{co} weist Berichte über Liquiditätsprobleme zurück",
         "{co} hat einen Bericht über Refinanzierungsprobleme zurückgewiesen. Die Liquidität sei ausreichend, alle Fälligkeiten seien gedeckt."),
    ],
    "sector_noise": [
        ("Branche {sector} unter Druck, {co} sieht sich nicht betroffen",
         "Mehrere Unternehmen der Branche haben ihre Prognosen gesenkt. {co} bestätigte dagegen den Ausblick, der Auftragsbestand sei hoch."),
    ],
    "lawsuit": [
        ("Klage gegen {co} wegen Liefervertrag",
         "Ein früherer Kunde hat {co} verklagt. Das Unternehmen hält die Klage für unbegründet, der Betrag sei nicht wesentlich."),
    ],
    "agm": [
        ("Hauptversammlung von {co} stimmt allen Punkten zu",
         "Die Aktionäre von {co} haben auf der Hauptversammlung allen Beschlussvorschlägen zugestimmt."),
    ],
    "board": [
        ("{co} beruft neues Aufsichtsratsmitglied",
         "{co} hat ein neues Mitglied in den Aufsichtsrat berufen, mit langjähriger Erfahrung in der Branche {sector}."),
    ],
    "results_inline": [
        ("{co}: Zahlen zum {q} im Rahmen der Erwartungen",
         "{co} hat für das {q} Umsatz und Ergebnis im Rahmen der Erwartungen gemeldet und die Prognose bestätigt."),
    ],
    "esg": [
        ("{co} veröffentlicht Nachhaltigkeitsbericht",
         "{co} will die Emissionen bis 2030 um {pct} Prozent senken."),
    ],
    "contract_win": [
        ("{co} erhält Großauftrag über {amt} Millionen Euro",
         "{co} hat einen mehrjährigen Auftrag im Wert von rund {amt} Millionen Euro gewonnen."),
    ],
    "guidance_raise": [
        ("{co} hebt Prognose nach starkem {q} an",
         "Dank hoher Nachfrage im {q} hebt {co} die Jahresprognose an. Die Marge stieg um {pct2} Prozentpunkte."),
    ],
    "bond_success": [
        ("{co} platziert Anleihe mit hoher Nachfrage",
         "{co} hat eine Anleihe über {amt} Millionen Euro platziert. Das Orderbuch war mehr als dreifach überzeichnet."),
    ],
    "deleveraging": [
        ("{co} verkauft Sparte und senkt Schulden",
         "{co} verkauft eine Nebensparte und nutzt den Erlös von {amt} Millionen Euro zur Schuldentilgung."),
    ],
    "rating_outlook_positive": [
        ("Ratingagentur hebt Ausblick für {co} auf positiv",
         "Eine Ratingagentur hat den Ausblick für {co} nach stetigem Schuldenabbau auf positiv angehoben."),
    ],
}

NEGATIVE = ["profit_warning", "guidance_cut", "covenant", "refinancing", "liquidity", "cfo_exit", "audit_delay",
            "restructuring", "impairment", "dividend_cut", "spread_widening"]
NOISE = ["denial", "sector_noise", "lawsuit"]
NEUTRAL = ["agm", "board", "results_inline", "esg"]
POSITIVE = ["contract_win", "guidance_raise", "bond_success", "deleveraging"]

# Relative weights inside the negative group when a company is in trouble vs. when it is fine.
NEG_WEIGHTS_STRESS = {"profit_warning": 3, "guidance_cut": 3, "covenant": 2, "refinancing": 3, "liquidity": 2,
                      "cfo_exit": 1, "audit_delay": 0.7, "restructuring": 2, "impairment": 1.5, "dividend_cut": 1.2,
                      "spread_widening": 2}
NEG_WEIGHTS_CALM = {"profit_warning": 1, "guidance_cut": 2, "covenant": 0.15, "refinancing": 0.3, "liquidity": 0.2,
                    "cfo_exit": 0.6, "audit_delay": 0.1, "restructuring": 2, "impairment": 1, "dividend_cut": 0.3,
                    "spread_widening": 0.4}


def _topic_mix(stress: float) -> dict[str, float]:
    """Topic probabilities for one article given a stress level between 0 and 1."""
    neg_share = 0.10 + 0.50 * stress
    noise_share = 0.10 + 0.06 * stress
    pos_share = max(0.05, 0.25 - 0.17 * stress)
    neu_share = max(0.05, 1 - neg_share - noise_share - pos_share)
    neg_w = {k: (1 - stress) * NEG_WEIGHTS_CALM[k] + stress * NEG_WEIGHTS_STRESS[k] for k in NEGATIVE}
    mix = {}
    tot = sum(neg_w.values())
    mix.update({k: neg_share * v / tot for k, v in neg_w.items()})
    noise_w = {"denial": 0.2 + 1.5 * stress, "sector_noise": 1.0, "lawsuit": 0.6}
    tot = sum(noise_w.values())
    mix.update({k: noise_share * v / tot for k, v in noise_w.items()})
    mix.update({k: neu_share / len(NEUTRAL) for k in NEUTRAL})
    mix.update({k: pos_share / len(POSITIVE) for k in POSITIVE})
    return mix


def _fill(template: str, rng, issuer, month: str) -> str:
    # Results refer to the last completed quarter.
    q = (int(month[5:]) - 1) // 3 or 4
    yr = int(month[:4]) - (1 if q == 4 and int(month[5:]) <= 3 else 0)
    return template.format(
        co=issuer.issuer_name, pct=int(rng.integers(5, 30)), cents=int(rng.integers(55, 86)), pct2=int(rng.integers(2, 9)),
        amt=int(rng.choice([50, 75, 100, 150, 200, 250, 300, 400, 500])), city=rng.choice(CITIES),
        q=f"Q{q}", yr=yr, sector=issuer.sector.lower())


def generate_news(issuers: pd.DataFrame, latent: pd.DataFrame, actions: pd.DataFrame,
                  rng: np.random.Generator) -> pd.DataFrame:
    lat = latent.set_index(["issuer_id", "month"])
    act = actions.set_index(["issuer_id", "month"])
    rows = []
    n = 0
    for iss in issuers.itertuples():
        de_share = 0.55 if iss.country in ("DE", "AT") else 0.08
        for month in sorted(latent.loc[latent["issuer_id"] == iss.issuer_id, "month"]):
            st = lat.loc[(iss.issuer_id, month)]
            # Stress mixes the gap to the current rating with the recent direction of travel.
            stress = float(np.clip(0.45 * max(st.stress_gap, 0) + 0.55 * max(st.momentum_3m, 0)
                                   + (0.6 if st.jump else 0.0), 0, 1))
            lam = C.ARTICLES_PER_MONTH * (0.6 + 0.4 * iss.size) * (1 + 1.5 * stress)
            k = int(rng.poisson(lam))
            mix = _topic_mix(stress)
            topics = list(mix)
            probs = np.array([mix[t] for t in topics])
            chosen = list(rng.choice(topics, size=k, p=probs / probs.sum()))
            # Agency actions are news too.
            if (iss.issuer_id, month) in act.index:
                a = act.loc[[(iss.issuer_id, month)]]
                for action in a["action"]:
                    if action == "downgrade":
                        chosen.append("rating_downgrade")
                    elif action == "outlook negative":
                        chosen.append("rating_outlook_negative")
                    elif action == "outlook positive":
                        chosen.append("rating_outlook_positive")
            days = pd.Period(month, freq="M").days_in_month
            for topic in chosen:
                lang = "de" if rng.random() < de_share else "en"
                bank = DE if lang == "de" else EN
                head, body = bank[topic][int(rng.integers(len(bank[topic])))]
                n += 1
                rows.append({
                    "article_id": f"A{n:06d}",
                    "date": f"{month}-{int(rng.integers(1, days + 1)):02d}",
                    "issuer_id": iss.issuer_id,
                    "language": lang,
                    "source": rng.choice(SOURCES_DE if lang == "de" else SOURCES_EN),
                    "headline": _fill(head, rng, iss, month),
                    "body": _fill(body, rng, iss, month),
                    "true_topic": topic,
                })
    df = pd.DataFrame(rows).sort_values(["date", "article_id"]).reset_index(drop=True)
    return df
