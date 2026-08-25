"""CLI for read-only Bulk Draft + Automated QA runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from utils.bulk_expansion_v3 import load_bulk_draft, run_bulk_qa


def main() -> None:
    parser = argparse.ArgumentParser(description="AOMatch v3.2 Bulk Draft QA")
    parser.add_argument("draft", type=Path)
    parser.add_argument("--characters", type=Path, default=Path("data/characters_v2_candidate.csv"))
    parser.add_argument("--json", action="store_true", help="输出 machine-readable JSON")
    args = parser.parse_args()
    with args.characters.open(encoding="utf-8-sig", newline="") as handle:
        existing = list(csv.DictReader(handle))
    report = run_bulk_qa(load_bulk_draft(args.draft), existing)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    counts = report["status_counts"]
    print(f"Bulk {report['batch_id']}: total={report['total']} "
          f"AUTO_PASS={counts.get('AUTO_PASS', 0)} "
          f"REVIEW_REQUIRED={counts.get('REVIEW_REQUIRED', 0)} "
          f"BLOCKED={counts.get('BLOCKED', 0)}")
    for item in report["exceptions"]:
        print(" | ".join(str(item[key]) for key in (
            "character", "game", "field", "candidate_value", "confidence",
            "exception_type", "severity", "reason", "suggested_action",
        )))


if __name__ == "__main__":
    main()
