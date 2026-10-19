"""AI 能力层（功能 7 / 8 / 9 / 10）。

目录分工（CLAUDE.md §5.1、§5.3）：
    llm.py       模型入口（唯一构造 ChatOpenAI 的地方）
    agents.py    create_agent 工厂：按场景组装 prompt + tools + response_format
    tools/       只读工具（不写库、user_id 由闭包注入、返回必须截断）
    runtime.py   调用编排：超时、步数上限、用量累加、异常映射
    schemas.py   结构化输出模型（SummaryOut / QuizOut / AdviceOut）
    validators.py 业务二次校验（能确定性修正的就修正，硬伤才失败）
    usage.py     配额检查与 ai_usage 落库
    prompts/     提示词（Markdown，便于论文截图）
"""
