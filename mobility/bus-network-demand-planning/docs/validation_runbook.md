# Validation runbook

Run before every KPI refresh and before any timetable change is planned:

```bash
PYTHONPATH=src python -m bus_network.pipeline
```

The issue log lands in `outputs/issue_log.csv` and on the first sheet of
`outputs/network_planning_report.xlsx`. A planner ticks the "Fixed" column once the source system
is corrected; the open-issue counter at the bottom updates by formula.

| Check | What it tests | Owner | What to do when it fails |
|---|---|---|---|
| V01 | Stop coordinates fall inside Europe | Network data | Correct the stop in the planning tool. Swapped latitude and longitude is the usual cause |
| V02 | No two stop records within 1 km | Network data | Merge the duplicate into the main stop and move the lines that use it |
| V03 | Every trip with passengers is in the operations log | Operations, partner management | Ask the partner for the missing records. Partner payments come from the log |
| V04 | Every booking belongs to a timetabled departure | Ticketing, data | Trace where the extra departures come from and fix the ticketing mapping |
| V05 | The bus that ran has the seats that were sold | Partner management, revenue management | Align ticketing capacity with the bus in service, or get the partner back on the contracted bus |
| V06 | Partners run only under a valid contract | Partner management | Renew the contract or move the lines to another partner |
| V07 | Cancelled trips carry no passengers | Operations | Rebook or refund the passengers and correct the trip status |
| V08 | Trip bookings add up to the origin-destination totals | Data | Find the source of the difference before using either table for planning |

The same checks for V03, V05 and V06 also exist as SQL in `sql/`, so they can run directly on a
warehouse. `tests/test_analysis_planning.py` confirms the SQL and Python versions agree.

## What the current data shows

Seven of eight checks fail. Six problems were planted when the data was generated, and V08 fails
as a knock-on of V04: the extra bookings are in the trip table but not in the monthly totals.
`tests/test_validation.py` checks that every planted problem is found with the exact count.

| Check | Finding |
|---|---|
| V01 | Regensburg stop with latitude and longitude swapped |
| V02 | Munich stored twice, 0.3 km apart, one record used by L031 |
| V03 | 140 trips with passengers missing from the operations log |
| V04 | 60 bookings on a 05:45 departure that is not in the timetable |
| V05 | L017 runs single-deckers since 1 April 2026 while 79 seats are sold; 314 of 362 trips were overbooked, by up to 30 seats |
| V06 | Partner P07 kept running 1,279 trips after its contract ended on 30 June 2026 |
| V08 | 55 line-months where trip bookings and origin-destination totals differ, all explained by V04 |
