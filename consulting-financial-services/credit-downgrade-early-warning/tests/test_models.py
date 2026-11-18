from downgrade_ews import config as C, models


def test_train_and_test_are_separated_by_the_horizon(run):
    assert run.train["month"].max() == "2025-03"
    assert run.test["month"].min() == C.TEST_START


def test_news_beats_keywords_and_keywords_beat_financials(run):
    ev = run.evaluation.set_index("model")
    assert ev.loc["+ NLP news scores", "pr_auc"] > ev.loc["+ keyword rules", "pr_auc"] > ev.loc["Ratings + financials", "pr_auc"]
    assert ev.loc["+ NLP news scores", "alert_precision"] > ev.loc["+ keyword rules", "alert_precision"]
    assert ev.loc["+ NLP news scores", "event_recall"] >= ev.loc["+ keyword rules", "event_recall"]


def test_every_model_beats_the_base_rate(run):
    base = models.base_rate(run.test)
    assert (run.evaluation["pr_auc"] > base).all()


def test_alert_list_has_fixed_budget(run):
    al = models.alerts(run.test, run.results[models.FULL].scores)
    assert (al.groupby("month").size() == C.ALERT_THRESHOLD_TOP_K).all()


def test_event_metrics_are_consistent(run):
    ev = run.evaluation
    assert (ev["caught"] <= ev["downgrades"]).all()
    assert ev["median_lead_months"].between(1, C.HORIZON_MONTHS).all()
