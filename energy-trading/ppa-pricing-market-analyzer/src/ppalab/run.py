"""Refresh everything: market data -> trends -> forward curve -> PPA Monte Carlo and offers -> BESS -> pipeline -> reports.

    PYTHONPATH=src python -m ppalab.run [--regenerate] [--scenarios 100]
"""

from __future__ import annotations

import argparse
import json

from . import bess as B
from . import crm as C
from . import market as M
from . import pricing as P
from . import trends as T
from .config import OUTPUTS, RAW

YEARS = [2027, 2028, 2029]


def run(regenerate: bool = False, n_scenarios: int = 100, reports: bool = True) -> dict:
    if regenerate or not (RAW / "de_hourly_market.csv.gz").exists():
        M.write()
        C.write()
    d = M.load()
    h = T.enrich(d["hourly"])
    yearly = T.yearly(h)
    monthly = T.monthly(h)
    fvol = T.forward_volatility(d["cal27"])
    level_vol = float(fvol.annualised_vol.iloc[-1])

    curve = d["curve"]
    hp = P.hpfc(d["hourly"], 2027, *curve.loc[curve.year == 2027, ["base_eur_mwh", "peak_eur_mwh"]].iloc[0])
    scen = P.scenarios(YEARS, n_scenarios, curve, level_vol)
    stats, offers, struct = {}, {}, {}
    base_offer = curve[curve.year.isin(YEARS)].base_eur_mwh.mean() - 1.5
    for tech in ("solar", "wind"):
        stats[tech] = P.asset_stats(scen, tech, 10.0)
        offers[tech] = P.offer(stats[tech], tech, len(YEARS), "BBB")
        struct[tech] = P.structures(scen, tech, 10.0, offers[tech]["offer_price"], base_offer)

    daily = B.run(d["hourly"])
    bess_y = B.yearly(daily)
    colo = B.solar_plus_storage(d["hourly"])

    opp = C.load()
    crm = {"checks": C.checks(opp), "pipeline": C.pipeline(opp), "forecast": C.forecast(opp), "win_rates": C.win_rates(opp)}

    last = yearly.iloc[-2]                                                 # last full year
    result = {
        "market": {"years": yearly.round(3).to_dict("records"), "last_full_year": int(last.year),
                   "cal27_base": float(curve.base_eur_mwh.iloc[0]), "cal27_vol_annualised": round(level_vol, 3)},
        "ppa": {t: {k: round(float(v), 3) for k, v in o.items()} for t, o in offers.items()},
        "structures": {t: P.summarise_structures(r).to_dict() for t, r in struct.items()},
        "hpfc_check": {"base": round(float(hp.price.mean()), 2), "peak": round(float(hp[hp.is_peak].price.mean()), 2)},
        "bess": bess_y.round(0).to_dict("records"),
        "solar_plus_storage": colo.round(2).to_dict("records"),
        "crm": {"open_deals": int((~opp.Stage.str.startswith("Closed")).sum()),
                "weighted_pipeline_eur": round(float(crm["pipeline"].to_numpy().sum())),
                "data_issues": crm["checks"].set_index("check").opportunities.to_dict()},
        "scenarios": n_scenarios,
    }
    if reports:
        from . import reporting as R
        OUTPUTS.mkdir(exist_ok=True)
        yearly.to_csv(OUTPUTS / "market_yearly.csv", index=False)
        monthly.to_csv(OUTPUTS / "market_monthly.csv", index=False)
        hp.to_csv(OUTPUTS / "hpfc_2027.csv", index=False)
        for t in stats:
            stats[t].to_csv(OUTPUTS / f"ppa_scenarios_{t}.csv", index=False)
            struct[t].to_csv(OUTPUTS / f"structures_{t}.csv", index=False)
        bess_y.to_csv(OUTPUTS / "bess_yearly.csv", index=False)
        colo.to_csv(OUTPUTS / "solar_plus_storage.csv", index=False)
        for k, v in crm.items():
            v.to_csv(OUTPUTS / f"crm_{k}.csv")
        (OUTPUTS / "results.json").write_text(json.dumps(result, indent=2, default=str))
        ctx = dict(h=h, yearly=yearly, monthly=monthly, curve=curve, hp=hp, offers=offers, struct=struct, stats=stats, bess=bess_y, colo=colo,
                   crm=crm, opp=opp, d=d, result=result, fvol=fvol)
        R.figures(ctx)
        R.excel(ctx)
        R.weekly_report(ctx)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--scenarios", type=int, default=100)
    a = ap.parse_args()
    r = run(a.regenerate, a.scenarios)
    print(json.dumps({k: r[k] for k in ("ppa", "hpfc_check", "crm")}, indent=2))
