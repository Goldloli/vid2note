"""笔记详细程度的附加约束，供两条笔记 prompt 路径复用。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetailProfile:
    """三种非超详细档位的结构化生成预算与质量策略。"""

    level: str
    label: str
    min_chapters: int
    max_chapters: int
    min_key_points: int
    max_key_points: int
    min_chapter_chars: int
    max_chapter_chars: int
    min_evidence: int
    max_evidence: int
    chapters_per_batch: int
    map_max_tokens: int
    draft_max_tokens: int
    audit_max_tokens: int
    repair_max_tokens: int
    audit_mode: str
    allowed_importance: tuple[str, ...]
    coverage_policy: str
    example_policy: str


DETAIL_LEVEL_PROFILES: dict[str, DetailProfile] = {
    "concise": DetailProfile(
        level="concise",
        label="简洁",
        min_chapters=3,
        max_chapters=4,
        min_key_points=2,
        max_key_points=4,
        min_chapter_chars=350,
        max_chapter_chars=650,
        min_evidence=18,
        max_evidence=18,
        chapters_per_batch=4,
        map_max_tokens=5000,
        draft_max_tokens=3500,
        audit_max_tokens=1500,
        repair_max_tokens=2500,
        audit_mode="on_failure",
        allowed_importance=("critical", "high"),
        coverage_policy="只保留决定课程主线的结论、关键数据、必要步骤与风险",
        example_policy="案例仅在没有它就无法理解结论时保留，每个主题最多一个",
    ),
    "balanced": DetailProfile(
        level="balanced",
        label="适中",
        min_chapters=5,
        max_chapters=6,
        min_key_points=3,
        max_key_points=5,
        min_chapter_chars=550,
        max_chapter_chars=900,
        min_evidence=30,
        max_evidence=30,
        chapters_per_batch=3,
        map_max_tokens=6500,
        draft_max_tokens=4500,
        audit_max_tokens=2000,
        repair_max_tokens=3000,
        audit_mode="risk",
        allowed_importance=("critical", "high", "supporting"),
        coverage_policy="保留全部核心与高价值证据，并选择能代表主要分支的补充证据；开头概括核心结论与行动摘要",
        example_policy="每个主要观点保留一个代表性案例或必要解释，推导展开一层",
    ),
    "detailed": DetailProfile(
        level="detailed",
        label="详细",
        min_chapters=6,
        max_chapters=8,
        min_key_points=4,
        max_key_points=7,
        min_chapter_chars=850,
        max_chapter_chars=1400,
        min_evidence=42,
        max_evidence=42,
        chapters_per_batch=3,
        map_max_tokens=9000,
        draft_max_tokens=7000,
        audit_max_tokens=2000,
        repair_max_tokens=4500,
        audit_mode="risk",
        allowed_importance=("critical", "high", "supporting", "context"),
        coverage_policy="保留全部核心、高价值证据、大部分补充证据和影响理解的重要上下文",
        example_policy="保留定义、推导、重要案例、数据、边界、注意事项与易错点",
    ),
}


DETAIL_LEVEL_INSTRUCTIONS: dict[str, str] = {
    "concise": """
【笔记详细程度：简洁】
面向需要快速决策的读者，只保留字幕或讲义中的核心结论、关键概念、关键数据、
必要步骤和实质风险。合并重复论证，省略寒暄、枝节和非必要案例；每个保留观点都要
说明最必要的依据，不写只有结论没有支撑的口号。不得捏造字幕或讲义中不存在的事实。
""".strip(),
    "balanced": """
【笔记详细程度：适中】
面向日常学习和回看，完整保留字幕或讲义中的主要论点、必要解释、代表性案例、
关键数据、方法步骤和结论。每个主要观点展开一层“为什么”，同类案例择一保留，
在信息覆盖与阅读效率之间平衡。开头先给出核心结论与可执行行动摘要；统计、判断和
个案结论保留讲者或材料来源边界。不得捏造字幕或讲义中不存在的事实。
""".strip(),
    "detailed": """
【笔记详细程度：详细】
面向系统学习和后续查阅，在忠实覆盖字幕或讲义主要内容的基础上，保留定义、
重要上下文、完整推导、关键数据、重要案例、反例、适用边界、注意事项和易错点。
删除无新增信息的重复故事与闲聊；原材料没有提供的维度应忠实省略。
数字、单位与比例保持原材料口径；不得捏造字幕或讲义中不存在的事实；
原材料未说明或 ASR 无法确认之处应明确保持空缺或标注不确定。
""".strip(),
    "exhaustive": """
【笔记详细程度：超详细】
先充分理解全部字幕或讲义，再写成事实忠实、全局连贯、论证完整、信息价值高且易读的
深度笔记。围绕课程中心问题组织知识，而不是按字幕顺序改写或堆积更多文字。

必须说明原材料实际提供的核心结论是什么、为什么成立、推导如何展开、关键案例证明什么，并保留重要定义、
步骤、数据、反例、适用边界、注意事项、术语、跨章节关联、易错点和有信息量的问答。
同一主题分散在多个时间段时应合并理解，既去除逐字重复，也保留后来新增的独立信息。

只展开原材料真实提供的维度；没有数据、案例、反例或边界时应忠实省略。只删除寒暄、
口头禅、无信息互动和无新增信息的重复。不得捏造字幕或讲义中不存在的事实，
不得使用外部常识擅自补齐论据；对无法结合上下文可靠纠正的 ASR 专名、数字或语句明确标记
为不确定。质量以事实忠实度、主题覆盖、结构连贯、信息价值和可读性衡量，不以篇幅衡量。
""".strip(),
}


def normalize_detail_level(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "thorough":
        return "exhaustive"
    return normalized if normalized in DETAIL_LEVEL_INSTRUCTIONS else "balanced"


def detail_instruction(value: object) -> str:
    return DETAIL_LEVEL_INSTRUCTIONS[normalize_detail_level(value)]


__all__ = [
    "DetailProfile",
    "DETAIL_LEVEL_INSTRUCTIONS",
    "DETAIL_LEVEL_PROFILES",
    "detail_instruction",
    "normalize_detail_level",
]
