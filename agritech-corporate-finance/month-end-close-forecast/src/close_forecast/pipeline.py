"""Run the whole close: data, checks, adjustments, variance analysis, forecast, reports.

    python -m close_forecast.pipeline              # use data/ if present
    python -m close_forecast.pipeline --regenerate # rebuild the synthetic extract first
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from . import close_checks, config as C, data_generator, forecast, reporting, variance


@dataclass
class CloseRun:
    tables: dict
    checks: list
    checklist: pd.DataFrame
    adjustments: pd.DataFrame
    bva_fa: pd.DataFrame
    comments: pd.DataFrame
    pvm: pd.DataFrame
    income_statement: pd.DataFrame
    backtest: pd.DataFrame
    choice: pd.DataFrame
    cost_forecast: pd.DataFrame
    revenue_forecast: pd.DataFrame
    landing: pd.DataFrame
    capex: pd.DataFrame
    intercompany: pd.DataFrame


def load_tables(regenerate: bool = False, paths: C.Paths | None = None) -> dict:
    paths = paths or C.Paths()
    if regenerate or not (paths.data / "gl_items.csv.gz").exists():
        data_generator.save(data_generator.generate(), paths.data)
    return data_generator.load(paths.data)


def run(tables: dict, month: str = C.CLOSE_PERIOD) -> CloseRun:
    checks = close_checks.run_close_checks(tables, month)
    adjustments = close_checks.proposed_adjustments(tables, checks, month)
    bt = forecast.backtest(tables)
    choice = forecast.choose_methods(bt)
    cost_fc = forecast.forecast_fy(tables, adjustments, choice=choice)
    rev_fc = forecast.revenue_forecast(tables)
    return CloseRun(
        tables=tables, checks=checks, checklist=close_checks.checklist(checks), adjustments=adjustments,
        bva_fa=variance.bva(tables, month), comments=variance.commentary(tables, month, checks),
        pvm=variance.price_volume(tables, month), income_statement=variance.income_statement(tables, month),
        backtest=bt, choice=choice, cost_forecast=cost_fc, revenue_forecast=rev_fc,
        landing=forecast.landing(tables, cost_fc, rev_fc), capex=forecast.capex_forecast(tables, month),
        intercompany=close_checks.intercompany_matrix(tables, month),
    )


def write_outputs(r: CloseRun, paths: C.Paths | None = None) -> dict:
    paths = paths or C.Paths()
    f = paths.figures
    f.mkdir(parents=True, exist_ok=True)
    out = {
        "ebit_bridge": reporting.plot_ebit_bridge(reporting.ebit_bridge(r.pvm, r.income_statement), f / "ebit_bridge.png"),
        "cost_forecast": reporting.plot_cost_forecast(r.tables, r.cost_forecast, f / "cost_forecast.png"),
        "backtest": reporting.plot_backtest(r.backtest, f / "forecast_backtest.png"),
        "capex": reporting.plot_capex(r.capex, f / "capex_eac.png"),
        "pvm": reporting.plot_pvm(r.pvm, f / "revenue_pvm.png"),
        "excel": reporting.write_excel(paths.outputs / "controlling_pack.xlsx", checklist=r.checklist,
                                       adjustments=r.adjustments, bva_fa=r.bva_fa, comments=r.comments, pvm=r.pvm,
                                       landing=r.landing, cost_fc=r.cost_forecast, capex=r.capex, ic=r.intercompany,
                                       choice=r.choice),
        "memo": reporting.close_memo(paths.outputs / "close_memo.md", checklist=r.checklist, adjustments=r.adjustments,
                                     comments=r.comments, pvm=r.pvm, is_ytd=r.income_statement, landing=r.landing,
                                     choice=r.choice, capex=r.capex),
    }
    out["powerbi"] = reporting.export_powerbi(r.tables, r.cost_forecast, r.revenue_forecast, r.adjustments, paths.powerbi)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regenerate", action="store_true")
    args = ap.parse_args()
    r = run(load_tables(args.regenerate))
    out = write_outputs(r)
    print(r.checklist[["check_id", "check", "status", "exceptions", "amount_eur"]].to_string(index=False))
    print()
    print(r.landing.to_string(index=False))
    for k, v in out.items():
        if k != "powerbi":
            print(f"wrote {k}: {v}")


if __name__ == "__main__":
    main()
