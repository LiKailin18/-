"""AI 结构化输出与判分的纯逻辑测试（不需要数据库、不需要模型）。"""

import pytest

from app.ai.schemas import AdviceOut, AdviceSuggestion, QuizOut, QuizQuestion, SummaryOut
from app.ai.validators import (
    AdviceInvalidError,
    QuizInvalidError,
    SummaryInvalidError,
    apply_advice_overrides,
    normalize_quiz,
    validate_summary,
)
from app.services.quiz_service import judge_question

# --------------------------------------------------------------------- 总结


def test_summary_rejects_refusal():
    out = SummaryOut(
        summary_md="作为 AI，我无法总结这份资料的内容，因为它看起来不完整。",
        key_points=["无法总结"],
    )

    with pytest.raises(SummaryInvalidError):
        validate_summary(out)


def test_summary_dedupes_and_truncates_key_points():
    out = SummaryOut(
        summary_md="极限是高等数学中最基础的概念之一，贯穿后续所有章节。",
        key_points=["极限的定义", " 极限的定义 ", "连续", "   "],
    )

    result = validate_summary(out)

    assert result.key_points == ["极限的定义", "连续"]


# --------------------------------------------------------------------- 测试题


def make_question(**overrides) -> QuizQuestion:
    body = {
        "no": 1,
        "type": "single",
        "stem": "函数在一点连续的充要条件是？",
        "options": ["选项A", "选项B", "选项C", "选项D"],
        "answer": ["选项A"],
        "explanation": "连续性要求左右极限都存在且等于函数值。",
        "difficulty": "medium",
        "knowledge": "函数的连续性",
    }
    body.update(overrides)
    return QuizQuestion(**body)


def test_quiz_renumbers_and_normalizes_judge_options():
    out = QuizOut(
        title="第一章测验",
        questions=[
            make_question(no=7, type="judge", options=[], answer=["正确"]),
            make_question(no=3, stem="第二个题目是什么？"),
        ],
    )

    result = normalize_quiz(out, expected_count=2, expected_types=["judge", "single"])

    assert [q.no for q in result.questions] == [1, 2]
    assert result.questions[0].options == ["正确", "错误"]  # 判断题强制标准选项


def test_quiz_maps_judge_answer_aliases():
    out = QuizOut(
        title="判断题",
        questions=[make_question(type="judge", options=["对", "错"], answer=["T"])],
    )

    result = normalize_quiz(out, expected_count=1, expected_types=["judge"])

    assert result.questions[0].answer == ["正确"]


def test_quiz_rejects_wrong_count():
    out = QuizOut(title="数量不对", questions=[make_question()])

    with pytest.raises(QuizInvalidError):
        normalize_quiz(out, expected_count=3, expected_types=["single"])


def test_quiz_rejects_answer_outside_options():
    out = QuizOut(title="答案非法", questions=[make_question(answer=["E"])])

    with pytest.raises(QuizInvalidError):
        normalize_quiz(out, expected_count=1, expected_types=["single"])


def test_quiz_rejects_duplicate_options():
    out = QuizOut(
        title="选项重复",
        questions=[make_question(options=["A选项", "A选项", "C", "D"])],
    )

    with pytest.raises(QuizInvalidError):
        normalize_quiz(out, expected_count=1, expected_types=["single"])


def test_quiz_rejects_duplicate_stems():
    out = QuizOut(
        title="题干重复",
        questions=[make_question(), make_question(options=["甲", "乙", "丙", "丁"], answer=["B"])],
    )

    with pytest.raises(QuizInvalidError):
        normalize_quiz(out, expected_count=2, expected_types=["single"])


def test_quiz_clears_blank_options():
    out = QuizOut(
        title="填空题",
        questions=[
            make_question(type="blank", options=["误给的选项"], answer=["极限"], knowledge="极限")
        ],
    )

    result = normalize_quiz(out, expected_count=1, expected_types=["blank"])

    assert result.questions[0].options == []


# --------------------------------------------------------------------- 判分规则


def test_judge_single_and_multiple():
    single = {"type": "single", "answer": ["B"]}
    multiple = {"type": "multiple", "answer": ["A", "C"]}

    assert judge_question(single, ["B"]) is True
    assert judge_question(single, ["b"]) is True  # 忽略大小写
    assert judge_question(single, ["A"]) is False
    # 多选：完全一致才算对（少选不得分，契约 §11）
    assert judge_question(multiple, ["A", "C"]) is True
    assert judge_question(multiple, ["C", "A"]) is True  # 顺序无关
    assert judge_question(multiple, ["A"]) is False
    assert judge_question(multiple, ["A", "B", "C"]) is False


def test_judge_blank_is_case_insensitive():
    blank = {"type": "blank", "answer": ["Limit"]}

    assert judge_question(blank, [" limit "]) is True
    assert judge_question(blank, ["LIMIT"]) is True
    assert judge_question(blank, ["limits"]) is False


# --------------------------------------------------------------------- 建议


def suggestion(title: str, priority: str = "high") -> AdviceSuggestion:
    return AdviceSuggestion(
        title=title,
        reason="该知识点正确率最低，需要重点补充",
        action="重做该知识点的测验并整理错题",
        priority=priority,
    )


def test_advice_overrides_backend_data_and_caps_minutes():
    out = AdviceOut(
        summary="近七天学习时长偏少，正确率有待提高。",
        suggestions=[suggestion("补极限"), suggestion("多做题", "medium")],
        weak_points=[{"knowledge": "模型编造的"}],
        next_7_days=[{"date": "2026-01-01", "minutes": 999}],
    )

    result = apply_advice_overrides(
        out,
        weak_points=[{"knowledge": "极限", "accuracy": 0.5}],
        next_7_days=[{"date": "2026-10-20", "minutes": 600, "focus": "极限"}],
        daily_target_minutes=60,
    )

    # 后端数据覆盖模型输出
    assert result.weak_points == [{"knowledge": "极限", "accuracy": 0.5}]
    assert result.next_7_days[0]["date"] == "2026-10-20"
    # 每天时长不超过目标的 1.5 倍
    assert result.next_7_days[0]["minutes"] == 90


def test_advice_requires_high_priority():
    out = AdviceOut(
        summary="近七天学习安排不太合理，需要调整优先级。",
        suggestions=[suggestion("补极限", "medium"), suggestion("多做题", "low")],
    )

    with pytest.raises(AdviceInvalidError):
        apply_advice_overrides(
            out, weak_points=[], next_7_days=[], daily_target_minutes=60
        )


def test_advice_rejects_duplicate_titles():
    out = AdviceOut(
        summary="近七天学习安排不太合理，两条建议重复了。",
        suggestions=[suggestion("一样的标题"), suggestion("一样的标题", "medium")],
    )

    with pytest.raises(AdviceInvalidError):
        apply_advice_overrides(
            out, weak_points=[], next_7_days=[], daily_target_minutes=60
        )
