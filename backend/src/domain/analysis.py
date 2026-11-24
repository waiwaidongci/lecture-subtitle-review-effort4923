"""Chronological model selection and planning estimates for subtitle review."""

from dataclasses import dataclass
from math import fsum, sqrt
from statistics import fmean, pstdev

from .spec import SPEC


_DURATION = ("video_minutes",)
_TRANSCRIPT = _DURATION + ("low_confidence_pct", "speaker_changes")
_GROUPS = (
    ("时长", _DURATION),
    ("时长与转写", _TRANSCRIPT),
    ("时长、转写与术语", _TRANSCRIPT + ("term_count",)),
)
_LABELS = {field["key"]: field["label"] for field in SPEC["fields"]}


def validate_rows(rows):
    # The shared CSV validator also calls this function after parsing the cells.
    from src.services.validation import cell

    cleaned = []
    seen = set()
    for index, row in enumerate(rows, 1):
        try:
            values = {field["key"]: cell(field, row.get(field["key"])) for field in SPEC["fields"]}
            job_id = values["job_id"]
            if job_id in seen:
                raise ValueError(f"重复工单号 {job_id}")
        except ValueError as error:
            raise ValueError(f"第 {index} 条工单 · {error}") from None
        seen.add(job_id)
        cleaned.append(values)
    if not cleaned:
        raise ValueError("请导入讲座工单")
    return cleaned


def _split(history, selection_start, holdout_start):
    if bool(selection_start) != bool(holdout_start):
        raise ValueError("手动切分时请同时填写选型与留出起始日")
    if not selection_start:
        days = sorted({row["job_date"] for row in history})
        if len(days) < 3:
            raise ValueError("按日期切分至少需要三个不同日期的已完工工单")
        first = min(len(days) - 2, len(days) * 3 // 5)
        second = min(len(days) - 1, max(first + 1, len(days) * 4 // 5))
        selection_start, holdout_start = days[first], days[second]
    if selection_start >= holdout_start:
        raise ValueError("留出起始日必须晚于选型起始日")

    training = [row for row in history if row["job_date"] < selection_start]
    selection = [row for row in history if selection_start <= row["job_date"] < holdout_start]
    holdout = [row for row in history if row["job_date"] >= holdout_start]
    if len(training) < 2 or not selection or not holdout:
        raise ValueError("切分后训练集至少需要两条，选型集与留出集各至少需要一条已完工工单")
    return training, selection, holdout


def _solve_ridge(matrix, target):
    """Solve a positive definite system by Cholesky and triangular substitution."""
    size = len(target)
    lower = [[0.0] * size for _ in target]
    for i in range(size):
        for j in range(i + 1):
            remainder = matrix[i][j] - fsum(lower[i][k] * lower[j][k] for k in range(j))
            lower[i][j] = sqrt(remainder) if i == j else remainder / lower[j][j]

    forward = []
    for i in range(size):
        known = fsum(lower[i][k] * forward[k] for k in range(i))
        forward.append((target[i] - known) / lower[i][i])
    weights = [0.0] * size
    for i in reversed(range(size)):
        known = fsum(lower[k][i] * weights[k] for k in range(i + 1, size))
        weights[i] = (forward[i] - known) / lower[i][i]
    return weights


@dataclass(frozen=True)
class _Model:
    features: tuple[str, ...]
    means: list[float]
    scales: list[float]
    weights: list[float]
    bounds: list[tuple[float, float]]
    intercept: float

    def predict(self, row):
        return self.intercept + fsum(
            ((row[key] - mean) / scale) * weight
            for key, mean, scale, weight in zip(self.features, self.means, self.scales, self.weights)
            if scale
        )


def _fit(rows, features, penalty):
    columns = [[row[key] for row in rows] for key in features]
    means = [fmean(column) for column in columns]
    scales = [pstdev(column) for column in columns]
    scales = [scale if scale >= 1e-12 else 0.0 for scale in scales]
    standardized = [
        [(value - mean) / scale for value in column] if scale else [0.0] * len(rows)
        for column, mean, scale in zip(columns, means, scales)
    ]
    actual = [row["actual_minutes"] for row in rows]
    intercept = fmean(actual)
    centered = [value - intercept for value in actual]
    gram = [
        [fsum(a * b for a, b in zip(left, right)) + (penalty if i == j else 0)
         for j, right in enumerate(standardized)]
        for i, left in enumerate(standardized)
    ]
    target = [fsum(x * y for x, y in zip(col, centered)) for col in standardized]
    return _Model(features, means, scales, _solve_ridge(gram, target),
                  [(min(column), max(column)) for column in columns], intercept)


def _errors(model, rows):
    errors = [max(0.0, model.predict(row)) - row["actual_minutes"] for row in rows]
    return fmean(abs(error) for error in errors), sqrt(fmean(error * error for error in errors)), fmean(errors)


def _candidates(training, selection, center):
    scores = []
    for name, features in _GROUPS:
        for penalty in (center / 10, center, center * 10):
            model = _fit(training, features, penalty)
            mae, rmse, _ = _errors(model, selection)
            scores.append((mae, rmse, name, features, penalty))
    return sorted(scores, key=lambda item: (item[0], item[1], len(item[3]), -item[4]))


def _pending_estimates(model, pending, last_history_date, threshold):
    queue = []
    for row in pending:
        prediction = model.predict(row)
        estimate = round(max(0.0, prediction), 2)
        outside = [
            _LABELS[key] for key, (low, high) in zip(model.features, model.bounds)
            if not low <= row[key] <= high
        ]
        reasons = []
        if estimate >= threshold:
            reasons.append("达到核排工时阈值")
        if outside:
            reasons.append("超出拟合范围的特征有" + "、".join(outside))
        if prediction < 0:
            reasons.append("线性估算为负，已按零列示")
        if row["job_date"] <= last_history_date:
            reasons.append("工单日期未晚于最后已完工日期")
        queue.append({
            "job_id": row["job_id"], "job_date": row["job_date"], "title": row["title"],
            "estimated_minutes": estimate, "flagged": "需核排" if reasons else "常规",
            "reason": "。".join(reasons) if reasons else "—",
        })
    return sorted(queue, key=lambda row: (row["flagged"] != "需核排", -row["estimated_minutes"], row["job_date"], row["job_id"]))


def _table(title, columns, rows):
    return {"title": title, "columns": [{"key": key, "label": label} for key, label in columns], "rows": rows}


def analyze(rows, normalized_params):
    from src.services.validation import normalize_params

    ordered = sorted(validate_rows(rows), key=lambda row: (row["job_date"], row["job_id"]))
    params = normalize_params(normalized_params)
    history = [row for row in ordered if row["actual_minutes"] is not None]
    pending = [row for row in ordered if row["actual_minutes"] is None]
    training, selection, holdout = _split(history, params["selection_start"], params["holdout_start"])
    scores = _candidates(training, selection, params["ridge_penalty"])
    selection_mae, _, group, features, penalty = scores[0]
    model = _fit(training + selection, features, penalty)
    mae, rmse, bias = _errors(model, holdout)
    baseline = fmean(abs(row["actual_minutes"] - model.intercept) for row in holdout)
    queue = _pending_estimates(model, pending, history[-1]["job_date"], params["flag_minutes"])
    flagged = sum(row["flagged"] == "需核排" for row in queue)

    comparison = [
        {"group": name, "penalty": strength, "mae": round(error, 4), "rmse": round(rms, 4),
         "selected": "入选" if index == 0 else "—"}
        for index, (error, rms, name, _, strength) in enumerate(scores)
    ]
    coefficients = [
        {"feature": _LABELS[key], "mean": round(mean, 6), "scale": round(scale, 6),
         "weight": round(weight, 6), "slope": round(weight / scale, 6) if scale else None,
         "interpretation": "恒定列" if not scale else "每增加一个标准差的关联分钟数"}
        for key, mean, scale, weight in zip(model.features, model.means, model.scales, model.weights)
    ]
    evaluated = []
    for row in holdout:
        estimate = max(0.0, model.predict(row))
        evaluated.append({
            "job_id": row["job_id"], "job_date": row["job_date"], "title": row["title"],
            "estimated_minutes": round(estimate, 2), "actual_minutes": row["actual_minutes"],
            "error": round(estimate - row["actual_minutes"], 2),
        })
    stages = [
        {"stage": stage, "first": subset[0]["job_date"], "last": subset[-1]["job_date"], "count": len(subset)}
        for stage, subset in (("训练", training), ("选型", selection), ("留出", holdout))
    ]
    identifiers = (("job_id", "工单号"), ("job_date", "工单日期"), ("title", "讲座标题"))
    tables = [
        _table("待审工时与核排清单", identifiers + (
            ("estimated_minutes", "估算分钟"), ("flagged", "排班标记"), ("reason", "标记原因")), queue),
        _table("选型集候选比较", (("group", "特征组"), ("penalty", "λ"), ("mae", "MAE（分钟）"),
                                ("rmse", "RMSE（分钟）"), ("selected", "选型结论")), comparison),
        _table("留出集逐单误差", identifiers + (("estimated_minutes", "估算分钟"), ("actual_minutes", "实耗分钟"),
                                              ("error", "估算减实耗（分钟）")), evaluated),
        _table("模型系数与特征尺度", (("feature", "特征"), ("mean", "拟合均值"), ("scale", "拟合标准差"),
                                    ("weight", "标准化系数（分钟）"), ("slope", "每原始单位（分钟）"),
                                    ("interpretation", "系数口径")), coefficients),
        _table("已完工日期切分", (("stage", "阶段"), ("first", "首个日期"), ("last", "最后日期"),
                                ("count", "已完工工单")), stages),
    ]
    return {
        "state": "warning" if flagged else "ok",
        "headline": f"选定「{group}」λ={penalty:g}，已估算 {len(queue)} 条待审工单，其中 {flagged} 条需核排。",
        "note": (f"训练 {len(training)} 条，选型 {len(selection)} 条，留出 {len(holdout)} 条。"
                 "最后一段独立评估，待审工时沿用同一个模型。"),
        "metrics": [
            {"label": "选型 MAE（分钟）", "value": round(selection_mae, 4), "detail": "入选模型在选型集上的平均绝对误差"},
            {"label": "留出 MAE（分钟）", "value": round(mae, 4), "detail": "平均绝对误差"},
            {"label": "留出 RMSE（分钟）", "value": round(rmse, 4), "detail": "较大的误差对该指标影响更大"},
            {"label": "留出平均偏差（分钟）", "value": round(bias, 4), "detail": "平均估算减实耗，正值表示总体高估"},
            {"label": "留出常数基线 MAE（分钟）", "value": round(baseline, 4), "detail": "用训练与选型合并后的平均实耗做恒定估算"},
            {"label": "待核排工单", "value": flagged, "detail": f"待审 {len(queue)} 条 · 工时阈值 {params['flag_minutes']:g} 分钟"},
        ],
        "tables": tables,
        "charts": [{"title": "各候选的选型 MAE（分钟）", "kind": "bar", "series": [
            {"label": f"{item['group']} · λ={item['penalty']:g}", "value": item["mae"]} for item in comparison
        ]}],
        "sections": [{
            "title": "系数与核排口径",
            "text": (f"拟合模型的截距为 {model.intercept:.4f} 分钟，对应各特征位于拟合均值时的估算。"
                     "标准化系数的正负表示条件关联方向，相关特征的系数应一起看。"
                     "标准差小于 10⁻¹² 的列按恒定列处理。核排时优先查看标记原因和原始工单。"),
        }],
    }
