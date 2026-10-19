"""结构化输出的业务二次校验（契约：docs/agent-tools.md §4）。

设计取向：**能确定性修正的就修正，只有结构/语义硬伤才失败** ——
重试的代价是一次完整的模型调用，很贵。
"""

from app.ai.schemas import AdviceOut, QuizOut, QuizQuestion, SummaryOut

# 命中这些词说明模型在拒答或说教，不是有效内容
REFUSAL_MARKERS = ("作为 AI", "作为人工智能", "我无法", "抱歉，我不能", "作为一个AI")

JUDGE_OPTIONS = ["正确", "错误"]

# 判断题答案的常见变体，统一映射成标准选项
_JUDGE_ALIASES = {
    "正确": "正确",
    "对": "正确",
    "true": "正确",
    "t": "正确",
    "yes": "正确",
    "错误": "错误",
    "错": "错误",
    "false": "错误",
    "f": "错误",
    "no": "错误",
}


class QuizInvalidError(Exception):
    """题目存在硬伤，需要重试生成。"""


class SummaryInvalidError(Exception):
    """总结无效（拒答、过短等）。"""


class AdviceInvalidError(Exception):
    """建议无效（重复、缺少高优先级等）。"""


# --------------------------------------------------------------------- 总结


def validate_summary(out: SummaryOut, *, max_chars: int = 20000) -> SummaryOut:
    if any(marker in out.summary_md for marker in REFUSAL_MARKERS):
        raise SummaryInvalidError("模型拒答")

    out.summary_md = out.summary_md.strip()[:max_chars]

    points: list[str] = []
    seen: set[str] = set()
    for raw in out.key_points:
        point = raw.strip()[:80]
        if point and point not in seen:
            seen.add(point)
            points.append(point)
    if not points:
        raise SummaryInvalidError("要点为空")
    out.key_points = points[:12]
    return out


# --------------------------------------------------------------------- 测试题


def normalize_quiz(
    out: QuizOut, *, expected_count: int, expected_types: list[str]
) -> QuizOut:
    """校验并尽可能修正题目；硬伤抛 QuizInvalidError。

    修正项：编号重排、判断题强制标准选项、填空题清空选项、难度非法降级、出处截断。
    硬伤：数量不符、题型不符、选项为空/重复、答案不在选项内、题干重复。
    """
    if len(out.questions) != expected_count:
        raise QuizInvalidError(f"题目数量不符：期望 {expected_count}，实际 {len(out.questions)}")

    stems: set[str] = set()
    fixed: list[QuizQuestion] = []

    for index, question in enumerate(out.questions, start=1):
        question.no = index  # 缺号 / 乱号自动重排
        question.stem = question.stem.strip()

        if question.type not in expected_types:
            raise QuizInvalidError(f"题型不符：{question.type}")

        if question.type == "judge":
            question.options = list(JUDGE_OPTIONS)
            mapped = [_JUDGE_ALIASES.get(a.strip().lower(), "") for a in question.answer]
            if not mapped or not mapped[0]:
                raise QuizInvalidError("判断题答案必须是「正确」或「错误」")
            question.answer = [mapped[0]]
        elif question.type == "blank":
            question.options = []
            question.answer = [a.strip() for a in question.answer if a.strip()]
            if not question.answer:
                raise QuizInvalidError("填空题答案为空")
        else:
            options = [option.strip() for option in question.options]
            if len(options) != 4:
                raise QuizInvalidError("选择题必须提供 4 个选项")
            if any(not option for option in options) or len(set(options)) != 4:
                raise QuizInvalidError("选项为空或重复")
            question.options = options

            answers = [answer.strip() for answer in question.answer]
            if not answers or not set(answers) <= set(options):
                raise QuizInvalidError("答案不在选项内")
            if question.type == "single" and len(answers) != 1:
                raise QuizInvalidError("单选题只能有一个答案")
            question.answer = answers

        key = " ".join(question.stem.split())
        if key in stems:
            raise QuizInvalidError("题干重复")
        stems.add(key)

        if question.source_hint and len(question.source_hint) > 60:
            question.source_hint = question.source_hint[:60]

        fixed.append(question)

    out.questions = fixed
    return out


# --------------------------------------------------------------------- 建议


def apply_advice_overrides(
    out: AdviceOut,
    *,
    weak_points: list[dict],
    next_7_days: list[dict],
    daily_target_minutes: int,
) -> AdviceOut:
    """用后端算出来的数据覆盖模型输出，并做合理性校验。

    理由（docs/agent-tools.md §4.3）：能用 SQL 算的东西不交给模型生成，
    否则它可能编造不存在的知识点或日期。
    """
    titles = [suggestion.title.strip() for suggestion in out.suggestions]
    if len(set(titles)) != len(titles):
        raise AdviceInvalidError("建议标题重复")
    if not any(suggestion.priority == "high" for suggestion in out.suggestions):
        raise AdviceInvalidError("至少需要一条高优先级建议")

    # 每天时长不许离谱：不超过用户目标的 1.5 倍
    cap = max(1, int(daily_target_minutes * 1.5))
    out.next_7_days = [
        {**item, "minutes": min(int(item.get("minutes", daily_target_minutes)), cap)}
        for item in next_7_days
    ]
    out.weak_points = weak_points
    out.summary = out.summary.strip()
    return out
