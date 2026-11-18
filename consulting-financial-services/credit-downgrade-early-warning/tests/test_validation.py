from downgrade_ews import config as C, validation


def test_company_name_does_not_change_the_score(run, tables):
    bt = validation.behavioural_tests(run.text_model, tables["issuers"]).set_index("test")
    assert bt.loc["Invariance: 20 company names", "passed"] == "20/20"


def test_negative_topics_score_above_neutral_and_positive(run):
    ts = validation.topic_scores(run.scored, C.TEST_START)
    g = ts.groupby("group")["mean_score"].mean()
    assert g["negative"] > g["neutral"] and g["negative"] > g["positive"]


def test_both_languages_work(run):
    lang = validation.by_language(run.scored, C.TEST_START).set_index("language")
    assert (lang["roc_auc"] > 0.6).all()


def test_highest_scores_have_the_highest_downgrade_rate(run):
    cal = validation.calibration(run.test, run.results["+ NLP news scores"].scores)
    assert cal["observed"].idxmax() == cal.index.max()
