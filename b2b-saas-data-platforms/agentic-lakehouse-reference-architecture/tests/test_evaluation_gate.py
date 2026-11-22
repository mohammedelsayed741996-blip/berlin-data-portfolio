from agentlake import evaluate as E


def test_release_gate(agent):
    t, r, ru = E.run_tasks(agent), E.run_red_team(agent), E.approval_rules()
    s = E.summary(t, r, ru)
    assert E.failed_gates(s) == [], s
    assert s["red_team_runs"] == 3 * len(E.ATTACKS)
