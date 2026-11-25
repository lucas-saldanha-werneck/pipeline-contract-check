import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from contractcheck.checks import load_csv, render_markdown, run_checks
from contractcheck.cli import main

EX = Path(__file__).parent.parent / "examples"
CONTRACT = json.loads((EX / "contract.json").read_text())
ASOF = date(2026, 11, 23)


def kinds(findings):
    return {(f.check, f.column) for f in findings}


def test_clean_data_passes():
    cols = ["a", "b"]
    rows = [{"a": "1", "b": "x"}, {"a": "2", "b": "y"}]
    c = {"columns": {"a": {"type": "int"}, "b": {"type": "str"}}, "unique_key": ["a"]}
    assert run_checks(cols, rows, c) == []


def test_missing_and_unexpected_column():
    f = run_checks(["a", "z"], [{"a": "1", "z": "q"}], {"columns": {"a": {"type": "int"}, "b": {"type": "str"}}})
    assert ("missing_column", "b") in kinds(f)
    assert ("unexpected_column", "z") in kinds(f)


def test_null_and_nullable():
    c = {"columns": {"a": {"type": "str"}, "b": {"type": "str", "nullable": True}}}
    f = run_checks(["a", "b"], [{"a": "", "b": ""}], c)
    assert kinds(f) == {("null", "a")}
    assert f[0].rows == [1]


def test_type_and_range():
    c = {"columns": {"n": {"type": "int", "min": 0, "max": 10}}}
    f = run_checks(["n"], [{"n": "5"}, {"n": "x"}, {"n": "11"}, {"n": "-1"}], c)
    assert ("type", "n") in kinds(f)
    assert [x for x in f if x.check == "range"][0].rows == [3, 4]


def test_date_range_and_bad_date():
    c = {"columns": {"d": {"type": "date", "min": "2026-01-01"}}}
    f = run_checks(["d"], [{"d": "2025-12-31"}, {"d": "2026-13-40"}, {"d": "2026-02-01"}], c)
    assert [x for x in f if x.check == "range"][0].rows == [1]
    assert [x for x in f if x.check == "type"][0].rows == [2]


def test_allowed_values():
    c = {"columns": {"s": {"type": "str", "allowed": ["a", "b"]}}}
    f = run_checks(["s"], [{"s": "a"}, {"s": "zzz"}], c)
    assert kinds(f) == {("allowed", "s")}


def test_duplicate_key_reports_later_row():
    c = {"columns": {"k": {"type": "int"}}, "unique_key": ["k"]}
    f = run_checks(["k"], [{"k": "1"}, {"k": "2"}, {"k": "1"}], c)
    assert f[0].check == "duplicate_key" and f[0].rows == [3]


def test_freshness():
    c = {"columns": {"d": {"type": "date"}}, "freshness": {"column": "d", "max_age_days": 2}}
    rows = [{"d": "2026-11-10"}]
    assert ("stale", "d") in kinds(run_checks(["d"], rows, c, ASOF))
    assert run_checks(["d"], [{"d": "2026-11-22"}], c, ASOF) == []


def test_row_count_drift():
    c = {"columns": {}, "row_count": {"expected": 100, "tolerance_pct": 10}}
    assert run_checks([], [{}] * 80, c)[0].check == "row_count"
    assert run_checks([], [{}] * 95, c) == []


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        run_checks(["a"], [{"a": "1"}], {"columns": {"a": {"type": "decimal"}}})


def test_sample_file_findings():
    cols, rows = load_csv(str(EX / "orders_sample.csv"))
    f = run_checks(cols, rows, CONTRACT, ASOF)
    k = kinds(f)
    assert ("duplicate_key", "order_id") in k
    assert ("range", "amount") in k
    assert ("type", "amount") in k
    assert ("null", "customer") in k
    assert ("allowed", "status") in k
    assert ("row_count", None) not in k  # 8 rows vs 10 is inside 30%


def test_markdown_render():
    cols, rows = load_csv(str(EX / "orders_sample.csv"))
    md = render_markdown("x.csv", len(rows), run_checks(cols, rows, CONTRACT, ASOF))
    assert "duplicate_key" in md and "| Check |" in md
    assert "No problems found." in render_markdown("x", 0, [])


def test_cli_exit_codes_and_json(capsys):
    args = [str(EX / "orders_sample.csv"), str(EX / "contract.json"), "--as-of", "2026-11-23", "--json"]
    assert main(args) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["rows"] == 8 and len(data["findings"]) >= 5


def test_cli_clean_exit_zero(tmp_path, capsys):
    (tmp_path / "c.csv").write_text("a\n1\n")
    (tmp_path / "c.json").write_text('{"columns": {"a": {"type": "int"}}}')
    assert main([str(tmp_path / "c.csv"), str(tmp_path / "c.json")]) == 0
