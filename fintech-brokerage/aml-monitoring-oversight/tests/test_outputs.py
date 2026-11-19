from openpyxl import load_workbook

from aml_oversight import config as C, pipeline


def test_outputs(run, tmp_path):
    out = pipeline.write_outputs(run, C.Paths(root=tmp_path))
    for p in out.values():
        assert p.exists() and p.stat().st_size > 1000
    wb = load_workbook(out["excel"])
    assert {"KRI dashboard", "QA", "Findings", "Completeness"} <= set(wb.sheetnames)
    assert str(wb["Rules"]["G2"].value).startswith("=E2/C2")
    report = out["report"].read_text()
    assert "Kurzfassung" in report and "F05" in report
