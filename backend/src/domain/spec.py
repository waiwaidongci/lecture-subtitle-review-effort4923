"""讲座字幕审校工时估算的工作台配置。"""


SPEC = {
    "title": "讲座字幕审校工时估算",
    "short_name": "caption-ridge",
    "subtitle": "用已完工讲座验证估算口径，为待审字幕预留人手。",
    "organization": "青阶讲堂媒制组，四名字幕审校员每周处理校内公开课和行业讲座。",
    "workflow": (
        "媒制组从转写系统导出视频时长、低置信片段占比、发言切换与待核术语数，"
        "再合并审校员记录的实际净工时。排班员把已完工讲座与待审工单放在同一份 CSV，"
        "按日期回测特征和惩罚力度，最后把预计分钟数与需人工核排的工单交给值班组长。"
    ),
    "pains": [
        "按视频长短分工容易低估术语密集和多人问答的讲座。",
        "同一批工单既用于调参又用于验收时，排班员看不到模型在较新讲座上的误差。",
        "超出历史样本范围的待审工单，需要在排班表里明确标出。",
    ],
    "steps": [
        "11 月 10 日 09:00，合并 10 月 26 日至 11 月 9 日的 30 条已完工讲座和 4 条待审工单。",
        "在「讲座工单」导入「青阶讲堂字幕工时_20261110.csv」，待审工单的实耗分钟留空。",
        "在「日期切分与选模」沿用自动切分或指定 11 月 4 日开始选型、11 月 7 日开始留出。",
        "以 1 为惩罚中心运行，在「估算误差与队列」比较三个特征组与三个惩罚值的选型误差。",
        "查看 11 月 7 至 9 日的留出误差和时长、转写、术语系数，核对待审工单 QJ-N04 的标记。",
        "在「排班复核」记录需人工核排的标记原因，然后从「工时清单导出」下载 CSV 给值班组长。",
    ],
    "methodology": [
        "只有已填实耗分钟的工单参与回测。按工单日期从旧到新分训练、选型和留出三段，同日工单始终在同一段。自动切分以有实耗的日期数按约 60%／20%／20% 分段。",
        "三个特征组分别使用视频时长、时长加转写质量、时长加转写质量和术语数。每组比较惩罚中心的 0.1、1、10 倍。",
        "用拟合窗口的均值及总体标准差标准化特征。恒定列按零处理。岭回归最小化残差平方和加 λ 乘标准化系数平方和，截距为拟合窗口平均实耗。",
        "用选型集 MAE 选参数，依次以 RMSE、较少特征和较强惩罚打破并列。选出后用训练与选型合并重拟合，留出再计算 MAE、RMSE、平均偏差和常数基线 MAE。",
        "估算值最低为零，负预测、超出拟合特征范围、工单日期早于或等于最后已完工日期、达到工时阈值均会在队列标记。标准化系数表示其他特征相同时增加一个标准差关联的工时变化。",
    ],
    "sample_name": "青阶讲堂字幕工时_20261110.csv",
    "default_dataset": "青阶讲堂 10 月 26 日至 11 月 11 日字幕工单",
    "entity": "讲座字幕工单",
    "run": "工时估算",
    "decision": "排班处置",
    "action": "提交排班复核",
    "modes": ["按估算排班", "人工核排", "补录实耗后重跑"],
    "pages": ["字幕排班台", "讲座工单", "日期切分与选模", "估算误差与队列", "排班复核", "工时清单导出"],
    "fields": [
        {"key": "job_id", "label": "工单号", "type": "string", "required": True},
        {"key": "job_date", "label": "工单日期", "type": "date", "required": True},
        {"key": "title", "label": "讲座标题", "type": "string", "required": True},
        {"key": "video_minutes", "label": "视频时长（分钟）", "type": "number", "required": True, "min": 0.01, "max": 1440},
        {"key": "low_confidence_pct", "label": "低置信字幕占比（%）", "type": "number", "required": True, "min": 0, "max": 100},
        {"key": "speaker_changes", "label": "发言人切换（次）", "type": "int", "required": True, "min": 0, "max": 10000},
        {"key": "term_count", "label": "待核术语（个）", "type": "int", "required": True, "min": 0, "max": 10000},
        {"key": "actual_minutes", "label": "实耗审校（分钟）", "type": "number", "required": False, "min": 0, "max": 10080},
    ],
    "params": [
        {"key": "selection_start", "label": "选型起始日", "type": "date", "required": False, "default": None,
         "help": "两处日期均留空时自动切分。手动切分时两个日期都需填写，起始日计入新阶段。"},
        {"key": "holdout_start", "label": "留出起始日", "type": "date", "required": False, "default": None,
         "help": "从此日起的已完工记录只用于留出评估。"},
        {"key": "ridge_penalty", "label": "岭惩罚中心 λ", "type": "number", "required": True, "min": 0.001, "max": 1000, "default": 1,
         "help": "对每个特征组比较该数值及其十分之一、十倍。"},
        {"key": "flag_minutes", "label": "人工核排阈值（分钟）", "type": "number", "required": True, "min": 1, "max": 10080, "default": 75,
         "help": "估算分钟（保留两位小数）达到阈值的待审工单会被标记。"},
    ],
    "fixture": {"selection_start": "2026-11-04", "holdout_start": "2026-11-07", "flag_minutes": 75},
    "axes": "选型误差图的横轴是特征组与 λ 的组合，纵轴是选型集 MAE（分钟）。",
}
