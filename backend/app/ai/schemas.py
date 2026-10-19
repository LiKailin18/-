"""结构化输出模型（契约：docs/agent-tools.md §4）。

这些模型有两重身份：
1. 作为 `create_agent(response_format=...)` 的入参，约束模型输出
2. 作为落库前的校验器（配合 validators.py 做业务二次校验）
"""

from typing import Literal

from pydantic import BaseModel, Field

QuizType = Literal["single", "multiple", "judge", "blank"]
Difficulty = Literal["easy", "medium", "hard"]


class SummaryOut(BaseModel):
    """资料总结（docs/agent-tools.md §4.1）。"""

    summary_md: str = Field(min_length=20, description="Markdown 格式的总结正文")
    key_points: list[str] = Field(min_length=1, max_length=12, description="要点列表")


class QuizQuestion(BaseModel):
    """单道题（docs/agent-tools.md §4.2）。"""

    no: int = Field(ge=1)
    type: QuizType
    stem: str = Field(min_length=5, max_length=500)
    options: list[str] = Field(default_factory=list)
    answer: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    difficulty: Difficulty = "medium"
    # 薄弱知识点统计依赖它，必须非空
    knowledge: str = Field(min_length=1, max_length=64)
    source_hint: str | None = None


class QuizOut(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    questions: list[QuizQuestion] = Field(min_length=1, max_length=20)


class AdviceSuggestion(BaseModel):
    title: str = Field(min_length=2, max_length=100)
    reason: str = Field(min_length=2, max_length=300)
    action: str = Field(min_length=2, max_length=200)
    priority: Literal["high", "medium", "low"]


class AdviceOut(BaseModel):
    """学习建议（docs/agent-tools.md §4.3）。

    weak_points / next_7_days 会由后端计算结果**覆盖**模型输出 ——
    能用 SQL 算出来的东西不交给模型生成。
    """

    summary: str = Field(min_length=10, max_length=500)
    suggestions: list[AdviceSuggestion] = Field(min_length=2, max_length=6)
    weak_points: list[dict] = Field(default_factory=list)
    next_7_days: list[dict] = Field(default_factory=list)
