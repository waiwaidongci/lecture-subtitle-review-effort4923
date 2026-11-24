"""青阶讲堂的确定性完工记录和待审工单。

除单笔工单外，演示数据包含三种整包场景：
- PKG-07：两场同日合审讲座，只记录整包实耗，不向单笔摊填；
- PKG-12 与 PKG-13：共享工单号 QJ-H23，归组时传递合并为一组；
- PKG-18：成员工单日期跨越自动切分界，回测时整组排除并在结果页列明原因。
"""

from datetime import date, timedelta


_SERIES = ("城市更新案例", "古籍数字化", "开放课程工作坊", "材料科学午间讲座", "纪录片声音设计")

# 工单号（零基序号）→ 整包包号；同一包号的行合成一条组观测。
_PACKAGE_BY_INDEX = {
    7: "PKG-07", 8: "PKG-07",
    12: "PKG-12",
    18: "PKG-18",
    22: "PKG-12",
    23: "PKG-13",  # 与第 22 行共享工单号，合并 PKG-12 / PKG-13
}
# 共享工单号：序号 22 与 23 使用同一个 job_id，分属两个包。
_SHARED_JOB = {23: 22}
# 序号 23 的日期向后顺延，使合并组同时展示成员日期范围。
_SPAN_DAYS = {23: 3}


def _features(index):
    duration = 24 + (index * 19) % 72
    low_confidence = 4 + (index * 7) % 26
    changes = 2 + (index * 13) % 34
    terms = 3 + (index * 17) % 43
    noise = (index * 11) % 9 - 4
    minutes = 7 + 0.52 * duration + 0.84 * low_confidence + 0.36 * changes + 0.65 * terms + noise
    return duration, low_confidence, changes, terms, round(minutes, 2)


def demo_rows() -> list[dict]:
    start = date(2026, 10, 26)
    rows = []
    package_totals = {}

    for index in range(30):
        duration, low_confidence, changes, terms, minutes = _features(index)
        day = start + timedelta(days=index // 2 + _SPAN_DAYS.get(index, 0))
        shared_with = _SHARED_JOB.get(index)
        job_id = f"QJ-H{shared_with + 1:02d}" if shared_with is not None else f"QJ-H{index + 1:02d}"
        package_id = _PACKAGE_BY_INDEX.get(index)
        row = {
            "job_id": job_id,
            "job_date": day.isoformat(),
            "title": f"{_SERIES[index % len(_SERIES)]} · 第 {index // len(_SERIES) + 1} 场",
            "video_minutes": duration,
            "low_confidence_pct": low_confidence,
            "speaker_changes": changes,
            "term_count": terms,
            "actual_minutes": None if package_id else minutes,
            "package_id": package_id,
            "package_actual_minutes": None,
        }
        if package_id:
            package_totals[package_id] = round(package_totals.get(package_id, 0.0) + minutes, 2)
        rows.append(row)

    # PKG-18 需要跨分界：为它追加一个晚六天的同包加场工单。
    anchor = next(row for row in rows if row["package_id"] == "PKG-18")
    extra = dict(anchor)
    extra["job_id"] = "QJ-H19B"
    extra["job_date"] = (date.fromisoformat(anchor["job_date"]) + timedelta(days=6)).isoformat()
    extra["title"] = anchor["title"] + "（合审加场）"
    extra_duration, extra_low, extra_changes, extra_terms, extra_minutes = _features(31)
    extra.update({"video_minutes": extra_duration, "low_confidence_pct": extra_low,
                  "speaker_changes": extra_changes, "term_count": extra_terms})
    package_totals["PKG-18"] = round(package_totals["PKG-18"] + extra_minutes, 2)
    rows.append(extra)

    # 整包实耗只写在每个包首次出现的行，其余包行留空，绝不摊填到单笔。
    # 共享工单号合并后的组只有一个整包实耗：PKG-13 的声明与 PKG-12 保持一致。
    first_seen = set()
    shared_total = package_totals["PKG-12"]
    for row in rows:
        package_id = row["package_id"]
        if package_id and package_id not in first_seen:
            row["package_actual_minutes"] = shared_total if package_id == "PKG-13" else package_totals[package_id]
            first_seen.add(package_id)

    pending = (
        ("2026-11-10", "修复纸张的水分控制", 31, 6, 4, 7),
        ("2026-11-10", "校园口述史访谈", 76, 23, 30, 16),
        ("2026-11-11", "剪辑台上的无障碍叙事", 48, 13, 12, 22),
        ("2026-11-11", "非线性光学与量子测量", 106, 38, 24, 67),
    )
    for index, (day, title, duration, low_confidence, changes, terms) in enumerate(pending, 1):
        rows.append({
            "job_id": f"QJ-N{index:02d}",
            "job_date": day,
            "title": title,
            "video_minutes": duration,
            "low_confidence_pct": low_confidence,
            "speaker_changes": changes,
            "term_count": terms,
            "actual_minutes": None,
            "package_id": None,
            "package_actual_minutes": None,
        })
    return rows
