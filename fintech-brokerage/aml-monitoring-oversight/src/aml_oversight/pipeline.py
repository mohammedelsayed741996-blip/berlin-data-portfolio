"""Run the oversight programme end to end.

    PYTHONPATH=src python -m aml_oversight.pipeline              # uses data/ if present
    PYTHONPATH=src python -m aml_oversight.pipeline --regenerate # rebuild the synthetic data first
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass

import pandas as pd

from . import config as C, data, oversight as O, reporting


@dataclass
class Run:
    tables: dict
    completeness: pd.DataFrame
    kpis: pd.DataFrame
    qa: pd.DataFrame
    qa_by_analyst: pd.DataFrame
    lookback: pd.DataFrame
    rules: pd.DataFrame
    coverage: pd.DataFrame
    volume_change: dict
    below_the_line: pd.DataFrame
    networks: pd.DataFrame
    screening: dict
    screening_qa: pd.DataFrame
    reviews: pd.DataFrame
    kri: pd.DataFrame
    findings: pd.DataFrame


def load_tables(regenerate: bool = False, paths: C.Paths | None = None) -> dict:
    paths = paths or C.Paths()
    if regenerate or not (paths.data / "alerts.csv").exists():
        data.save(data.generate(), paths.data)
    return data.load(paths.data)


def run(t: dict) -> Run:
    tx, alerts = t["transactions"], t["alerts"]
    feed = tx[tx["tx_id"].isin(t["tm_feed_ids"]["tx_id"])]
    comp = O.completeness(tx, t["tm_feed_ids"])
    kpis = O.alert_kpis(alerts)
    qa = O.qa_programme(alerts)
    qa_an = O.qa_by(qa, "analyst")
    worst = qa_an[qa_an["error_type"] == "decision_error"].sort_values("ci_low", ascending=False)["analyst"].iloc[0]
    lookback = O.targeted_lookback(alerts, worst)
    cov = O.typology_coverage(alerts, t["typology_truth"])
    vc = O.volume_change(alerts, "R02", C.R02_CHANGE_DATE[:7])
    btl = O.below_the_line(feed, alerts, t["typology_truth"])
    nets = O.shared_attribute_networks(t["clients"], tx)
    scr = O.screening_kpis(t["screening_hits"], t["screening_log"])
    sqa = O.screening_qa(t["screening_hits"])
    reviews = O.overdue_reviews(t["clients"])
    kri = O.kri_table(kpis, comp, qa, t["screening_log"], reviews)
    findings = O.findings_register(comp=comp, vc=vc, cov=cov, lookback=lookback, sqa=sqa, kpis=kpis, nets=nets,
                                   reviews=reviews, log=t["screening_log"])
    return Run(t, comp, kpis, qa, qa_an, lookback, O.rule_effectiveness(alerts), cov, vc, btl, nets, scr, sqa,
               reviews, kri, findings)


def write_outputs(r: Run, paths: C.Paths | None = None) -> dict:
    paths = paths or C.Paths()
    f = paths.figures
    t = r.tables
    out = {
        "kri_heatmap": reporting.plot_kri_heatmap(r.kri, f / "kri_heatmap.png"),
        "feed_gap": reporting.plot_feed_gap(t["transactions"], t["tm_feed_ids"], f / "feed_gap.png"),
        "rule_volume": reporting.plot_rule_volume(t["alerts"], "R02", f / "r02_volume.png"),
        "qa": reporting.plot_qa(r.qa_by_analyst, f / "qa_by_analyst.png"),
        "coverage": reporting.plot_coverage(r.coverage, f / "typology_coverage.png"),
        "networks": reporting.plot_networks(t["clients"], r.networks, f / "mule_networks.png"),
        "excel": reporting.write_excel(paths.outputs / "aml_oversight_mi.xlsx", kri=r.kri, kpis=r.kpis, rules=r.rules,
                                       cov=r.coverage, qa_an=r.qa_by_analyst, findings=r.findings, comp=r.completeness,
                                       screening=r.screening, reviews=r.reviews),
        "report": reporting.management_report(paths.outputs / "oversight_report.md", findings=r.findings, kri=r.kri,
                                              kpis=r.kpis, rules=r.rules, cov=r.coverage, screening=r.screening,
                                              comp=r.completeness, qa_an=r.qa_by_analyst, nets=r.networks,
                                              btl=r.below_the_line, vc=r.volume_change),
    }
    r.findings.to_csv(paths.outputs / "findings_register.csv", index=False)
    summary = {"findings": r.findings[["finding_id", "severity", "area"]].to_dict("records"),
               "alerts": len(t["alerts"]), "transactions": len(t["transactions"]), "clients": len(t["clients"]),
               "missing_from_feed": int(r.completeness["missing_count"].sum()), "networks": len(r.networks),
               "lookback_cases": len(r.lookback), "r02_change_pct": r.volume_change["change_pct"], "screening": r.screening}
    (paths.outputs / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regenerate", action="store_true")
    args = ap.parse_args()
    r = run(load_tables(args.regenerate))
    out = write_outputs(r)
    print(r.findings[["finding_id", "severity", "area"]].to_string(index=False))
    for k, v in out.items():
        print(f"wrote {k}: {v}")


if __name__ == "__main__":
    main()
