"""Exercise package grouping, correction retention, and group-level analysis.

Run from the repository root:
    python3 -I /workspace/tools/check_packages.py
The script only uses the standard library and imports the backend package via
sys.path manipulation, so no third-party dependencies are required.
"""

import sys
from pathlib import Path

ROOT = Path("/workspace/backend")
sys.path.insert(0, str(ROOT))

from src.domain.demo import demo_rows
from src.domain.packages import build_groups, observations
from src.domain.analysis import analyze, validate_rows
from src.services.validation import validate_packages


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("ok -", message)


def main():
    rows = demo_rows()
    validate_rows([{k: v for k, v in row.items()} for row in rows])
    validate_packages(rows)
    check(len(rows) == 35, f"demo has 35 rows (got {len(rows)})")

    grouped = build_groups(rows)
    groups = grouped["groups"]
    package_ids = {pid for group in groups for pid in group["package_ids"]}
    check({"PKG-07", "PKG-12", "PKG-13", "PKG-18"} <= package_ids, "all demo packages present")

    merged = [g for g in groups if set(g["package_ids"]) == {"PKG-12", "PKG-13"}]
    check(len(merged) == 1, "PKG-12 and PKG-13 merge through shared work order")
    shared_jobs = {rows[i]["job_id"] for i in merged[0]["row_indexes"]}
    check("QJ-H23" in shared_jobs, "merged group contains the shared work order QJ-H23")

    pkg18 = next(g for g in groups if g["package_ids"] == ["PKG-18"])
    member_dates = {rows[i]["job_date"] for i in pkg18["row_indexes"]}
    check(len(member_dates) == 2, "PKG-18 spans two dates and can straddle a boundary")

    # No package total may be copied onto individual work order rows.
    for row in rows:
        if row["package_id"]:
            check(row["actual_minutes"] is None, "package rows never carry per-row actual minutes")

    result = analyze(rows, {"ridge_penalty": 1, "flag_minutes": 75})
    titles = [table["title"] for table in result["tables"]]
    check("未纳入回测的包" in titles, "results include the excluded-packages table")
    excluded = next(table for table in result["tables"] if table["title"] == "未纳入回测的包")
    excluded_packages = {row["package_id"] for row in excluded["rows"]}
    check(any("PKG-18" in pid for pid in excluded_packages), "PKG-18 excluded for straddling the boundary")
    check(all("分界" in row["reason"] for row in excluded["rows"]), "exclusion reason mentions the boundary")

    grouping_table = next(table for table in result["tables"] if table["title"] == "整包归组与实耗来源")
    check(any("PKG-12、PKG-13" in row["package_id"] for row in grouping_table["rows"]),
          "grouping table shows the merged package ids")

    # Holdout rows expose group-level job ids and never allocate package totals.
    holdout = next(table for table in result["tables"] if table["title"] == "留出集逐组误差")
    check(all(row["actual_minutes"] is not None for row in holdout["rows"]), "holdout groups all have totals")

    # Corrections: append-only, both survive, latest drives the calculation.
    corrections = [
        {"id": 1, "package_id": "PKG-07", "actual_minutes": 200.0, "reason": "第一次更正",
         "author": "analyst", "created_at": "2026-11-10T10:00:00"},
        {"id": 2, "package_id": "PKG-07", "actual_minutes": 188.5, "reason": "并发的第二次更正",
         "author": "admin", "created_at": "2026-11-10T10:00:05"},
    ]
    regrouped = build_groups(rows, corrections)
    pkg07 = next(g for g in regrouped["groups"] if g["package_ids"] == ["PKG-07"])
    check(pkg07["actual_minutes"] == 188.5, "latest correction overrides the package total")
    check(pkg07["correction"]["id"] == 2, "correction metadata is retained on the group")

    corrected = analyze(rows, {"ridge_penalty": 1, "flag_minutes": 75}, corrections=corrections)
    source_table = next(table for table in corrected["tables"] if table["title"] == "整包归组与实耗来源")
    pkg07_row = next(row for row in source_table["rows"] if row["package_id"] == "PKG-07")
    check(pkg07_row["actual_minutes"] == 188.5 and pkg07_row["source"].startswith("更正"),
          "analysis reflects the latest correction and labels its source")

    # Conflicting declared totals block backtesting for that package.
    clash = [dict(row) for row in rows]
    pkg07_rows = [row for row in clash if row["package_id"] == "PKG-07"]
    pkg07_rows[0]["package_actual_minutes"] = pkg07_rows[0]["package_actual_minutes"] + 10
    pkg07_rows[1]["package_actual_minutes"] = pkg07_rows[0]["package_actual_minutes"] - 25
    clash_grouped = build_groups(clash)
    pkg07_clash = next(g for g in clash_grouped["groups"] if g["package_ids"] == ["PKG-07"])
    check(pkg07_clash["has_conflict"] and pkg07_clash["actual_minutes"] is None,
          "clashing package totals yield no usable target")
    clash_result = analyze(clash, {"ridge_penalty": 1, "flag_minutes": 75})
    clash_excluded = next(t for t in clash_result["tables"] if t["title"] == "未纳入回测的包")
    check(any("PKG-07" in row["package_id"] and "冲突" in row["reason"] for row in clash_excluded["rows"]),
          "conflicting package is excluded with a clear reason")

    # Pending estimates still work and include pending packages if present.
    check(any(table["title"] == "待审工时与核排清单" for table in result["tables"]),
          "pending estimate queue is still reported")
    print("\nAll package checks passed.")


if __name__ == "__main__":
    main()
