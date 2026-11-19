# AML oversight report, October 2025 to September 2026

For senior management and the Risk & Compliance Committee. Synthetic data; the broker, clients and analysts are fictional.

## Summary

Oversight raised 9 findings: 1 critical, 4 high and 4 medium. In September 3 of 7 measured KRIs were red.

| ID | Severity | Area | Observation | Owner | Due |
|---|---|---|---|---|---|
| F05 | Critical | Sanctions screening | 1 sanctions hit with match score 0.93 was closed as a false positive; reviewer judges it a true match (spelling variant). | MLRO | immediately |
| F01 | High | TM data completeness | 1016 card deposits (EUR 443,188) from PSP-B never reached transaction monitoring between 2026-06-10 and 2026-07-05. | Head of TM / IT | 2026-11-30 |
| F03 | High | Typology coverage | No rule covers T4 mule ring: 6 networks of six clients share a payout account or device; only 1 of 36 members alerted, for an unrelated reason. | MLRO | 2026-11-30 |
| F02 | High | Rule governance | R02 alert volume fell 80% from April 2026 (p = 0.000); the vendor raised the deposit count from 3 to 5 without an approved change request. | MLRO / TM vendor manager | 2026-11-30 |
| F04 | High | Alert decision quality | QA found decision errors concentrated in analyst A06; a full lookback of the analyst's closures found 46 cases that should have been escalated. | Head of FCC operations | 2026-11-30 |
| F06 | Medium | Alert timeliness | Alerts closed after more than 30 days reached 35% in 2026-08, 2026-09 (summer staffing). | Head of FCC operations | 2026-12-31 |
| F07 | Medium | Documentation | Closed alerts without a rationale peaked at 6.0%; most come from analyst A03. | Head of FCC operations | 2026-12-31 |
| F08 | Medium | Screening timeliness | 62 new clients were screened 4 to 7 days after onboarding during a batch outage (2026-03-09 to 2026-03-13). | Head of Onboarding / IT | 2026-12-31 |
| F09 | Medium | Periodic reviews | 43 high-risk clients are past their annual review date. | Head of KYC | 2026-12-31 |

## Monitoring coverage

- 1016 card deposits never reached transaction monitoring, so none of the rules saw them.
- R02 alert volume fell 80% after April. Re-running the rule with the approved setting (3 deposits) shows 14 structuring clients would have alerted; the current setting still catches 7, but the approved threshold must be restored and the gap looked back on.
- 6 groups of six clients share a payout account or device. No rule looks at that, and the rules alerted on just 1 of the 36 members, for an unrelated deposit.

## Alert handling

- QA re-reviewed 237 closed alerts over four quarters. Analyst A06 wrongly closed 22% of sampled cases (95% interval 10% to 39%); the other analysts together 2.0%.
- Summer staffing pushed alerts closed after 30 days to 35% in August, and the median time from alert to SAR to 53 days in September.

## Screening

- 1,228 hits, 95% closed as false positives. One sanctions hit was closed wrongly (finding F05).
- 62 new clients were screened late during a batch outage.

## Kurzfassung für die Geschäftsleitung

Die Überwachung hat 9 Feststellungen ergeben, davon 1 kritisch und 4 hoch:

- Ein Sanktionstreffer wurde fälschlich als Fehltreffer geschlossen. Konto sperren, Geldwäschebeauftragten sofort informieren.
- 1016 Kartenzahlungen eines Zahlungsdienstleisters sind nicht im Monitoring angekommen. Nachladen und Regeln erneut laufen lassen.
- Ein Regelschwellenwert wurde ohne Freigabe geändert. Genehmigten Wert wiederherstellen.
- 6 Kundengruppen teilen sich ein Auszahlungskonto oder ein Gerät (mögliche Finanzagenten). Keine Regel deckt das ab.
- Ein Analyst schließt zu viele echte Verdachtsfälle. Alle seine Schließungen werden nachgeprüft.
