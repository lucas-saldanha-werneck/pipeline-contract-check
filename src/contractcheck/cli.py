from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .checks import load_csv, render_markdown, run_checks


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="contract-check",
                                description="Check a CSV file against a JSON data contract.")
    p.add_argument("csv")
    p.add_argument("contract", help="JSON contract file")
    p.add_argument("--as-of", help="YYYY-MM-DD used for freshness (default: today)")
    p.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    a = p.parse_args(argv)

    with open(a.contract, encoding="utf-8") as fh:
        contract = json.load(fh)
    cols, rows = load_csv(a.csv)
    as_of = date.fromisoformat(a.as_of) if a.as_of else None
    findings = run_checks(cols, rows, contract, as_of)
    if a.json:
        print(json.dumps({"rows": len(rows), "findings": [f.to_dict() for f in findings]}, indent=2))
    else:
        print(render_markdown(a.csv, len(rows), findings), end="")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
