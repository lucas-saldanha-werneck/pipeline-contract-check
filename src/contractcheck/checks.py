"""Contract checks for a tabular extract. Standard library only."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime

TYPES = {"int", "float", "date", "str"}


@dataclass
class Finding:
    check: str
    column: str | None
    message: str
    rows: list[int]  # 1-based data row numbers (header is not counted)

    def to_dict(self) -> dict:
        return {"check": self.check, "column": self.column,
                "message": self.message, "rows": self.rows[:20],
                "row_count": len(self.rows)}


def load_csv(path: str) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def _parse(value: str, typ: str):
    if typ == "int":
        return int(value)
    if typ == "float":
        return float(value)
    if typ == "date":
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value


def run_checks(columns: list[str], rows: list[dict], contract: dict,
               as_of: date | None = None) -> list[Finding]:
    findings: list[Finding] = []
    specs = contract.get("columns", {})

    for name in specs:
        if name not in columns:
            findings.append(Finding("missing_column", name,
                                    f"column '{name}' is not in the file", []))
    for name in columns:
        if name not in specs:
            findings.append(Finding("unexpected_column", name,
                                    f"column '{name}' is not in the contract", []))

    parsed: dict[str, list] = {}
    for name, spec in specs.items():
        if name not in columns:
            continue
        typ = spec.get("type", "str")
        if typ not in TYPES:
            raise ValueError(f"unknown type '{typ}' for column '{name}'")
        bad_null, bad_type, bad_range, bad_enum = [], [], [], []
        values = []
        for i, row in enumerate(rows, start=1):
            raw = (row.get(name) or "").strip()
            if raw == "":
                values.append(None)
                if not spec.get("nullable", False):
                    bad_null.append(i)
                continue
            try:
                v = _parse(raw, typ)
            except ValueError:
                bad_type.append(i)
                values.append(None)
                continue
            values.append(v)
            if typ in ("int", "float", "date"):
                lo, hi = spec.get("min"), spec.get("max")
                if typ == "date":
                    lo = _parse(lo, "date") if lo else None
                    hi = _parse(hi, "date") if hi else None
                if (lo is not None and v < lo) or (hi is not None and v > hi):
                    bad_range.append(i)
            if "allowed" in spec and raw not in spec["allowed"]:
                bad_enum.append(i)
        parsed[name] = values
        if bad_null:
            findings.append(Finding("null", name, f"{len(bad_null)} empty value(s) in a non-nullable column", bad_null))
        if bad_type:
            findings.append(Finding("type", name, f"{len(bad_type)} value(s) are not valid {typ}", bad_type))
        if bad_range:
            findings.append(Finding("range", name, f"{len(bad_range)} value(s) outside min/max", bad_range))
        if bad_enum:
            findings.append(Finding("allowed", name, f"{len(bad_enum)} value(s) not in the allowed list", bad_enum))

    key = contract.get("unique_key")
    if key and all(k in columns for k in key):
        seen: dict[tuple, int] = {}
        dups: list[int] = []
        for i, row in enumerate(rows, start=1):
            k = tuple((row.get(c) or "").strip() for c in key)
            if k in seen:
                dups.append(i)
            else:
                seen[k] = i
        if dups:
            findings.append(Finding("duplicate_key", ",".join(key),
                                    f"{len(dups)} row(s) repeat an earlier key", dups))

    fresh = contract.get("freshness")
    if fresh and fresh["column"] in parsed:
        dates = [d for d in parsed[fresh["column"]] if d is not None]
        ref = as_of or date.today()
        if dates:
            age = (ref - max(dates)).days
            if age > fresh["max_age_days"]:
                findings.append(Finding("stale", fresh["column"],
                                        f"newest value is {age} days old (limit {fresh['max_age_days']})", []))
        else:
            findings.append(Finding("stale", fresh["column"], "no valid dates to judge freshness", []))

    drift = contract.get("row_count")
    if drift and "expected" in drift:
        exp, tol = drift["expected"], drift.get("tolerance_pct", 20)
        change = abs(len(rows) - exp) / exp * 100 if exp else 100.0
        if change > tol:
            findings.append(Finding("row_count", None,
                                    f"{len(rows)} rows vs expected {exp} ({change:.0f}% change, limit {tol}%)", []))
    return findings


def render_markdown(path: str, nrows: int, findings: list[Finding]) -> str:
    out = [f"# Contract check: {path}", "", f"Rows read: {nrows}", ""]
    if not findings:
        out.append("No problems found.")
    else:
        out += [f"Problems found: {len(findings)}", "", "| Check | Column | What | Rows |", "|---|---|---|---|"]
        for f in findings:
            rows = ", ".join(map(str, f.rows[:10])) + (" ..." if len(f.rows) > 10 else "")
            out.append(f"| {f.check} | {f.column or ''} | {f.message} | {rows} |")
    return "\n".join(out) + "\n"
