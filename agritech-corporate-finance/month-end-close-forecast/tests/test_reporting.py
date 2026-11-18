from openpyxl import load_workbook

from close_forecast import config as C, pipeline


def test_outputs_are_written(run, tmp_path):
    paths = C.Paths(root=tmp_path)
    out = pipeline.write_outputs(run, paths)
    for key in ["ebit_bridge", "cost_forecast", "backtest", "capex", "pvm", "excel", "memo"]:
        assert out[key].exists() and out[key].stat().st_size > 1000
    assert len(out["powerbi"]) == 7

    wb = load_workbook(out["excel"])
    assert {"Close checklist", "Adjustments", "BvA by function", "Revenue PVM", "Forecast 3+9", "Outlook",
            "Capex", "Intercompany"} <= set(wb.sheetnames)
    bva = wb["BvA by function"]
    assert str(bva["G2"].value).startswith("=E2-F2")
    assert str(wb["Outlook"]["D2"].value) == "=B2+C2"
    assert str(wb["Revenue PVM"]["K2"].value).startswith("=ROUND(")
    memo = out["memo"].read_text()
    assert "Close memo" in memo and "EBIT outlook" in memo
