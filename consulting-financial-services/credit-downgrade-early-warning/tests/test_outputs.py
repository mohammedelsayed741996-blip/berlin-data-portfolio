from downgrade_ews import config as C, pipeline


def test_outputs_and_watchlist(run, tmp_path):
    paths = C.Paths(root=tmp_path)
    out = pipeline.write_outputs(run, paths)
    for p in out.values():
        assert p.exists() and p.stat().st_size > 500
    wl = pipeline.watchlist(run)
    assert len(wl) == C.ALERT_THRESHOLD_TOP_K
    assert wl["score"].is_monotonic_decreasing
    assert "Model card" in (paths.outputs / "model_card.md").read_text()
