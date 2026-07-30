"""笔记详细程度的 prompt 契约测试。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.simple_processor import SimpleProcessor
from src.prompts.detail_level import DETAIL_LEVEL_INSTRUCTIONS, normalize_detail_level


def _snapshot_call(messages, kwargs):
    """记录调用时的消息快照；链式调用会原地追加消息，必须拷贝，否则历史记录被后续追加污染。"""
    return ([dict(message) for message in messages], kwargs)


class RecordingLLM:
    def __init__(self) -> None:
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(_snapshot_call(messages, kwargs))
        return "# 测试笔记"


class UnderstandingPipelineLLM:
    def __init__(self) -> None:
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(_snapshot_call(messages, kwargs))
        prompt = messages[-1]["content"]
        if "【阶段：语义证据提取】" in prompt:
            marker = prompt.split("证据命名空间：E", 1)[1].split("-", 1)[0]
            return (
                f"## 语义证据 E{marker}-001\n"
                f"- 主题：跨段主题 {marker}\n"
                "- 结论：保留本段论证、案例和边界\n"
                "- ASR 不确定项：无"
            )
        if "【阶段：全局知识蓝图】" in prompt:
            return self.blueprint_json(prompt)
        if "【阶段：章节深写】" in prompt:
            chapter_id = re.search(r"章节 ID：(C\d+)", prompt).group(1)
            return (
                f"## {chapter_id} 初稿\n\n"
                "### 核心论证\n解释结论为什么成立，并综合本章全部证据。\n\n"
                "### 案例与边界\n说明案例作用和适用限制。"
            )
        if "【阶段：章节编辑审校】" in prompt:
            chapter_id = re.search(r"章节 ID：(C\d+)", prompt).group(1)
            return (
                f"## {chapter_id} 审校终稿\n\n"
                "### 核心论证\n准确解释定义、推导与跨段证据。\n\n"
                "### 案例、反例与边界\n保留独立信息和实践意义。"
            )
        raise AssertionError("出现未识别的 LLM 阶段")

    @staticmethod
    def blueprint_json(prompt):
        evidence_ids = sorted(set(re.findall(r"E\d{2}-\d{3}", prompt)))
        source_chunks = sorted({int(item[1:3]) for item in evidence_ids})
        chapters = []
        for index in range(3):
            assigned_ids = evidence_ids[index::3]
            assigned_chunks = sorted(
                {int(item[1:3]) for item in assigned_ids}
            )
            chapters.append(
                {
                    "chapter_id": f"C{index + 1:02d}",
                    "title": f"逻辑章节 {index + 1}",
                    "purpose": "深入解释本章结论、论证、案例与边界",
                    "evidence_ids": assigned_ids,
                    "source_chunks": assigned_chunks or source_chunks[:1],
                    "required_points": ["结论", "推导", "案例", "适用边界"],
                }
            )
        return json.dumps(
            {
                "title": "最终高质量笔记",
                "course_overview": "统一理解课程主线和跨段主题。",
                "learning_outcomes": ["理解核心命题", "掌握实践方法"],
                "terminology": [
                    {
                        "canonical": "Harness Engineering",
                        "variants": ["哈尼斯工程"],
                        "confidence": "high",
                        "kind": "概念",
                        "note": "只统一拼写，不补充外部事实",
                    }
                ],
                "chapters": chapters,
            },
            ensure_ascii=False,
        )


def test_four_detail_levels_are_distinct_and_share_grounding_guard():
    assert list(DETAIL_LEVEL_INSTRUCTIONS) == [
        "concise",
        "balanced",
        "detailed",
        "exhaustive",
    ]
    assert len(set(DETAIL_LEVEL_INSTRUCTIONS.values())) == 4
    for instruction in DETAIL_LEVEL_INSTRUCTIONS.values():
        assert "不得捏造" in instruction
        assert "字幕" in instruction
    assert normalize_detail_level("invalid") == "balanced"


@pytest.mark.parametrize("level", list(DETAIL_LEVEL_INSTRUCTIONS))
@pytest.mark.parametrize("with_pdf", [False, True])
def test_detail_instruction_is_injected_into_both_note_prompt_paths(level, with_pdf):
    llm = RecordingLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": level})

    if with_pdf:
        processor._generate_with_pdf_reference(
            "字幕正文",
            {"structure_analysis": "讲义结构", "full_text": "讲义正文"},
        )
    else:
        processor._generate_directly("字幕正文")

    user_prompt = llm.calls[0][0][1]["content"]
    assert DETAIL_LEVEL_INSTRUCTIONS[level] in user_prompt
    assert "不得捏造" in user_prompt


def test_exhaustive_instruction_prioritizes_understanding_quality_without_length_ratio():
    instruction = DETAIL_LEVEL_INSTRUCTIONS["exhaustive"]
    for expected in ("充分理解", "事实忠实", "全局", "论证", "可读性"):
        assert expected in instruction
    assert "30%-60%" not in instruction
    assert "字符比例" not in instruction
    assert "不得捏造" in instruction


def test_exhaustive_split_covers_all_non_whitespace_content_once():
    processor = SimpleProcessor(
        RecordingLLM(),
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"字幕条目{i:04d}" for i in range(2600))
    chunks = processor._split_exhaustive_chunks(source, target_chars=1000)

    assert len(chunks) > 2
    assert all(0 < len(chunk) <= 1000 for chunk in chunks)
    assert "".join("".join(chunks).split()) == "".join(source.split())


def test_exhaustive_pipeline_maps_all_evidence_then_drafts_and_reviews_each_chapter():
    llm = UnderstandingPipelineLLM()
    progress = []
    processor = SimpleProcessor(
        llm,
        config={
            "note_detail_level": "exhaustive",
            "progress_callback": lambda phase, completed, total: progress.append(
                (phase, completed, total)
            ),
        },
    )
    source = " ".join(f"有效内容{i:04d}" for i in range(4500))
    expected_chunks = processor._split_exhaustive_chunks(source)

    result = processor._generate_exhaustive_with_understanding(source)

    chapter_count = 3
    assert len(llm.calls) == len(expected_chunks) + 1 + chapter_count * 2
    assert progress == [
        ("understand", index, len(expected_chunks))
        for index in range(1, len(expected_chunks) + 1)
    ] + [
        ("blueprint", 1, 1),
        *[
            ("draft", index, chapter_count)
            for index in range(1, chapter_count + 1)
        ],
        *[
            ("review", index, chapter_count)
            for index in range(1, chapter_count + 1)
        ],
    ]

    prompts = [call[0][-1]["content"] for call in llm.calls]
    blueprint_prompt = prompts[len(expected_chunks)]
    draft_prompts = [
        prompt for prompt in prompts if "【阶段：章节深写】" in prompt
    ]
    review_prompts = [
        prompt for prompt in prompts if "【阶段：章节编辑审校】" in prompt
    ]
    for index in range(1, len(expected_chunks) + 1):
        assert f"E{index:02d}-001" in blueprint_prompt
    all_chapter_prompts = "\n".join(draft_prompts + review_prompts)
    assert len(draft_prompts) == len(review_prompts) == chapter_count
    assert "course_overview" in all_chapter_prompts
    assert "有效内容0000" in all_chapter_prompts
    assert "有效内容4499" in all_chapter_prompts
    assert "Harness Engineering" in all_chapter_prompts
    assert result.startswith("# 最终高质量笔记")
    assert "## 课程主线与学习目标" in result
    assert "## 逻辑章节 1" in result
    assert "## 逻辑章节 2" in result
    assert "## 逻辑章节 3" in result
    assert "## C01" not in result
    assert "C01 初稿" not in result
    assert "语义证据 E" not in result


def test_exhaustive_blueprint_repairs_missing_evidence_mapping_before_drafting():
    class IncompleteBlueprintLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if (
                "【阶段：全局知识蓝图】" in prompt
                and "【阶段：修复知识蓝图】" not in prompt
            ):
                self.calls.append(_snapshot_call(messages, kwargs))
                blueprint = json.loads(self.blueprint_json(prompt))
                all_ids = [
                    evidence_id
                    for chapter in blueprint["chapters"]
                    for evidence_id in chapter["evidence_ids"]
                ]
                blueprint["chapters"][0]["evidence_ids"] = all_ids[:1]
                for chapter in blueprint["chapters"][1:]:
                    chapter["evidence_ids"] = []
                return json.dumps(blueprint, ensure_ascii=False)
            if "【阶段：修复知识蓝图】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                # 链式修复：证据 ID 在链内前缀中，需从完整消息提取
                full_prompt = "\n".join(m["content"] for m in messages)
                return self.blueprint_json(full_prompt)
            return super().chat(messages, **kwargs)

    llm = IncompleteBlueprintLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3200))

    result = processor._generate_exhaustive_with_understanding(source)

    prompts = [call[0][-1]["content"] for call in llm.calls]
    assert sum("【阶段：全局知识蓝图】" in prompt for prompt in prompts) == 1
    assert sum("【阶段：修复知识蓝图】" in prompt for prompt in prompts) == 1
    assert result.startswith("# 最终高质量笔记")


def test_exhaustive_blueprint_repairs_malformed_json_before_validation():
    class MalformedBlueprintLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if (
                "【阶段：全局知识蓝图】" in prompt
                and "【阶段：修复蓝图 JSON】" not in prompt
            ):
                self.calls.append(_snapshot_call(messages, kwargs))
                return '{"title": "未闭合蓝图"'
            if "【阶段：修复蓝图 JSON】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                # 链式修复：证据 ID 在链内前缀中，需从完整消息提取
                full_prompt = "\n".join(m["content"] for m in messages)
                return self.blueprint_json(full_prompt)
            return super().chat(messages, **kwargs)

    llm = MalformedBlueprintLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3000))

    result = processor._generate_exhaustive_with_understanding(source)

    repair_prompts = [
        call[0][-1]["content"]
        for call in llm.calls
        if "【阶段：修复蓝图 JSON】" in call[0][-1]["content"]
    ]
    assert len(repair_prompts) == 1
    assert "不得遗漏任何真实证据 ID" in repair_prompts[0]
    assert result.startswith("# 最终高质量笔记")


@pytest.mark.parametrize("with_pdf", [False, True])
def test_exhaustive_draft_and_review_keep_pdf_and_screenshot_semantics(with_pdf):
    llm = UnderstandingPipelineLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    pdf = (
        {"structure_analysis": "第一章结构", "full_text": "讲义参考正文"}
        if with_pdf
        else None
    )
    source = " ".join(f"[00:00:{i % 60:02d}] 字幕正文{i:04d}" for i in range(1800))

    processor._generate_exhaustive_with_understanding(
        source,
        pdf_structure=pdf,
        extract_images=True,
    )

    prompts = [call[0][-1]["content"] for call in llm.calls]
    draft_prompts = [
        prompt for prompt in prompts if "【阶段：章节深写】" in prompt
    ]
    review_prompts = [
        prompt for prompt in prompts if "【阶段：章节编辑审校】" in prompt
    ]
    review_full_messages = [
        "\n".join(message["content"] for message in call[0])
        for call in llm.calls
        if "【阶段：章节编辑审校】" in call[0][-1]["content"]
    ]
    assert draft_prompts and review_prompts
    assert all(
        DETAIL_LEVEL_INSTRUCTIONS["exhaustive"] in prompt
        for prompt in draft_prompts
    )
    assert all("[IMG:HH:MM:SS]" in prompt for prompt in draft_prompts)
    assert all("[IMG:HH:MM:SS]" in prompt for prompt in review_prompts)
    if with_pdf:
        assert all("第一章结构" in prompt for prompt in draft_prompts)
        assert all("讲义参考正文" in prompt for prompt in draft_prompts)
        # 审校改为链尾增量指令：讲义不再出现在指令本身，但必须在链内前缀中
        assert all("第一章结构" not in prompt for prompt in review_prompts)
        assert all("第一章结构" in full for full in review_full_messages)
    else:
        assert all("第一章结构" not in prompt for prompt in draft_prompts)


def test_exhaustive_evidence_prompt_has_stable_ids_and_boundary_context():
    processor = SimpleProcessor(
        RecordingLLM(),
        config={"note_detail_level": "exhaustive"},
    )
    prompt = processor._build_exhaustive_evidence_prompt(
        "本段完整正文",
        index=1,
        total=3,
        previous_context="上一段结尾",
        next_context="下一段开头",
    )

    assert "第 2/3 段" in prompt
    assert "证据命名空间：E02-" in prompt
    assert "上一段结尾" in prompt
    assert "下一段开头" in prompt
    assert "跨段线索" in prompt
    assert "ASR 不确定项" in prompt


def test_exhaustive_evidence_missing_ids_gets_one_structural_repair():
    class MissingEvidenceIdLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if (
                "【阶段：语义证据提取】" in prompt
                and "【阶段：修复语义证据 ID】" not in prompt
                and "证据命名空间：E01-" in prompt
            ):
                self.calls.append(_snapshot_call(messages, kwargs))
                return "## 本段证据\n- 主题：有内容但遗漏稳定 ID"
            if "【阶段：修复语义证据 ID】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return "## 语义证据 E01-001\n- 主题：修复后保留原内容"
            return super().chat(messages, **kwargs)

    llm = MissingEvidenceIdLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3000))

    result = processor._generate_exhaustive_with_understanding(source)

    repair_prompts = [
        call[0][-1]["content"]
        for call in llm.calls
        if "【阶段：修复语义证据 ID】" in call[0][-1]["content"]
    ]
    assert len(repair_prompts) == 1
    assert "不得删除原输出中的事实" in repair_prompts[0]
    assert "E01-" in repair_prompts[0]
    assert result.startswith("# 最终高质量笔记")


def test_exhaustive_blueprint_builds_a_grounded_terminology_glossary():
    processor = SimpleProcessor(
        RecordingLLM(),
        config={"note_detail_level": "exhaustive"},
    )

    prompt = processor._build_exhaustive_blueprint_prompt(
        "E01-001 哈尼斯工程；E01-002 Harmance；E01-003 死丢文件"
    )

    assert '"terminology"' in prompt
    assert "Harness Engineering" in prompt
    assert "Hermes Agent" in prompt
    assert "OpenClaw" in prompt
    assert "不得把 Hermes Agent 猜成 Claude" in prompt
    assert "只用于拼写校对" in prompt


@pytest.mark.parametrize(
    ("empty_stage", "error_pattern"),
    [
        ("evidence", "语义证据.*输出为空"),
        ("blueprint", "全局知识蓝图输出为空"),
        ("draft", "章节初稿.*输出为空"),
        ("review", "章节审校.*输出为空"),
    ],
)
def test_exhaustive_empty_stage_output_fails(empty_stage, error_pattern):
    class EmptyStageLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            stage_markers = {
                "evidence": "【阶段：语义证据提取】",
                "blueprint": "【阶段：全局知识蓝图】",
                "draft": "【阶段：章节深写】",
                "review": "【阶段：章节编辑审校】",
            }
            if stage_markers[empty_stage] in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return "   "
            return super().chat(messages, **kwargs)

    processor = SimpleProcessor(
        EmptyStageLLM(),
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3000))

    with pytest.raises(RuntimeError, match=error_pattern):
        processor._generate_exhaustive_with_understanding(source)


def test_exhaustive_review_must_return_complete_markdown_structure():
    class InvalidFinalLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：章节编辑审校】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return "只有一段正文"
            return super().chat(messages, **kwargs)

    processor = SimpleProcessor(
        InvalidFinalLLM(),
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3000))

    with pytest.raises(RuntimeError, match="终稿章节结构"):
        processor._generate_exhaustive_with_understanding(source)


def test_exhaustive_internal_evidence_id_leak_gets_one_lossless_repair():
    class InternalLeakLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：章节编辑审校】" in prompt and "章节 ID：C03" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return "## C03 审校终稿\n\n核心论证完整。（依据 E01-001）"
            if "【阶段：章节格式修复】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return "## C03 审校终稿\n\n核心论证完整，且正文内容原样保留。"
            return super().chat(messages, **kwargs)

    llm = InternalLeakLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3000))

    result = processor._generate_exhaustive_with_understanding(source)

    repair_prompts = [
        call[0][-1]["content"]
        for call in llm.calls
        if "【阶段：章节格式修复】" in call[0][-1]["content"]
    ]
    assert len(repair_prompts) == 1
    assert "不得概括、压缩或删除正文信息" in repair_prompts[0]
    assert "E01-001" in repair_prompts[0]
    assert "E01-001" not in result
    assert "正文内容原样保留" in result


def test_exhaustive_suspicious_asr_terms_get_a_fidelity_review():
    class TerminologyDriftLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：章节编辑审校】" in prompt and "章节 ID：C03" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return (
                    "## C03 审校终稿\n\n"
                    "Claude 会创建死丢（Store），使用 FIS5，并持续自我侵化。"
                )
            if "【阶段：术语保真审校】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return (
                    "## C03 审校终稿\n\n"
                    "Hermes Agent 会创建和更新 Skill，使用 FTS5，"
                    "并持续自我进化。"
                )
            return super().chat(messages, **kwargs)

    llm = TerminologyDriftLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3000))

    result = processor._generate_exhaustive_with_understanding(source)

    fidelity_calls = [
        call
        for call in llm.calls
        if "【阶段：术语保真审校】" in call[0][-1]["content"]
    ]
    assert len(fidelity_calls) == 1
    fidelity_instruction = fidelity_calls[0][0][-1]["content"]
    assert "不得概括、删减或扩写正文事实" in fidelity_instruction
    # 待校对章节不再重发于指令，而是链内的上一条 assistant 回复
    fidelity_full = "\n".join(m["content"] for m in fidelity_calls[0][0])
    assert "死丢（Store）" in fidelity_full
    assert fidelity_calls[0][0][-2]["role"] == "assistant"
    assert "死丢（Store）" in fidelity_calls[0][0][-2]["content"]
    assert "Hermes Agent 会创建和更新 Skill" in result
    assert "死丢" not in result
    assert "FIS5" not in result
    assert "自我侵化" not in result


def test_exhaustive_product_term_safeguards_fix_confirmed_spellings_and_dates():
    processor = SimpleProcessor(
        RecordingLLM(),
        config={"note_detail_level": "exhaustive"},
    )
    chapter = {"title": "产品对比：OpenClaw vs Hermes Agent"}

    result = processor._apply_exhaustive_ai_term_safeguards(
        (
            "2023 年 2 月 OpenClow 爆发。Hermes Agent（Harness Engineering）"
            "将流程保存为 Studio，写入 CRI 库并建立 FTS5；"
            "安全层包含神秘系统、平正过律、SIF 与沙箱（杀乡）。"
        ),
        chapter=chapter,
    )

    assert "2026 年 2 月" in result
    assert "OpenClow" not in result
    assert "Hermes Agent（Harness Engineering）" not in result
    assert "保存为 Skill" in result
    assert "SQLite 数据库" in result
    assert "神秘系统" not in result
    assert "平正过律" not in result
    assert "沙箱（Sandbox）" in result
    assert "ASR 名称不确定" in result


def test_exhaustive_full_source_is_not_cut_at_legacy_50000_character_limit():
    llm = UnderstandingPipelineLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"完整原文{i:05d}" for i in range(7000)) + " 最后主题不可丢"

    processor._generate_exhaustive_with_understanding(source)

    prompts = [call[0][-1]["content"] for call in llm.calls]
    draft_prompt = "\n".join(
        prompt for prompt in prompts if "【阶段：章节深写】" in prompt
    )
    # 审校为链尾增量指令：完整原文经深写 prompt 进入链内前缀
    review_full = "\n".join(
        message["content"]
        for call in llm.calls
        if "【阶段：章节编辑审校】" in call[0][-1]["content"]
        for message in call[0]
    )
    assert len(source) > 50000
    assert "最后主题不可丢" in draft_prompt
    assert "最后主题不可丢" in review_full


def test_sanitizer_preserves_structured_line_breaks_but_removes_control_bytes():
    processor = SimpleProcessor(RecordingLLM())

    result = processor._sanitize_content(
        "## 主题\n- 证据 A\t补充\x00内容\n- 证据 B",
        max_length=None,
    )

    assert "## 主题\n- 证据 A\t补充内容\n- 证据 B" == result


def test_exhaustive_chapter_prompts_share_byte_identical_prefix_through_blueprint():
    """跨章深写 prompt 到变量区前必须逐字节相同（前缀缓存友好）。"""
    processor = SimpleProcessor(
        RecordingLLM(),
        config={"note_detail_level": "exhaustive"},
    )
    blueprint = {
        "title": "课程",
        "course_overview": "主线",
        "learning_outcomes": ["目标"],
        "terminology": [
            {"canonical": "Skill", "variants": ["死丢"], "confidence": "high", "kind": "概念", "note": ""}
        ],
        "chapters": [],
    }

    def chapter(cid):
        return {
            "chapter_id": cid,
            "title": f"章节 {cid}",
            "purpose": "论证",
            "evidence_ids": ["E01-001"],
            "source_chunks": [1],
            "required_points": ["结论"],
        }

    prompt_c01 = processor._build_exhaustive_chapter_prompt(
        chapter("C01"),
        blueprint=blueprint,
        source_text="第一章原始字幕",
        evidence_text="第一章证据",
        pdf_structure=None,
        extract_images=False,
    )
    prompt_c02 = processor._build_exhaustive_chapter_prompt(
        chapter("C02"),
        blueprint=blueprint,
        source_text="完全不同的第二章原始字幕",
        evidence_text="完全不同的第二章证据",
        pdf_structure=None,
        extract_images=False,
    )

    boundary = "【当前章节】"
    assert prompt_c01.split(boundary)[0] == prompt_c02.split(boundary)[0]
    # 蓝图 JSON 必须出现在变量区之前
    assert prompt_c01.index("【全局蓝图 JSON】") < prompt_c01.index(boundary)


def test_exhaustive_evidence_prompts_share_byte_identical_fixed_prefix():
    """跨段证据 prompt 的固定说明部分必须逐字节相同（前缀缓存友好）。"""
    processor = SimpleProcessor(
        RecordingLLM(),
        config={"note_detail_level": "exhaustive"},
    )
    prompt_first = processor._build_exhaustive_evidence_prompt(
        "第一段正文",
        index=0,
        total=2,
        previous_context="",
        next_context="第一段结尾",
    )
    prompt_second = processor._build_exhaustive_evidence_prompt(
        "完全不同的第二段正文",
        index=1,
        total=2,
        previous_context="第二段开头",
        next_context="",
    )

    boundary = "【本段定位】"
    assert prompt_first.split(boundary)[0] == prompt_second.split(boundary)[0]
    assert "第 1/2 段" in prompt_first
    assert "第 2/2 段" in prompt_second
    assert "证据命名空间：E01-" in prompt_first
    assert "证据命名空间：E02-" in prompt_second


def test_exhaustive_review_uses_chapter_message_chain_without_resending_material():
    """审校必须以深写消息为前缀发起，且增量指令不重发蓝图与原文。"""
    llm = UnderstandingPipelineLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"链式内容{i:04d}" for i in range(1800))

    processor._generate_exhaustive_with_understanding(source)

    review_calls = [
        call
        for call in llm.calls
        if "【阶段：章节编辑审校】" in call[0][-1]["content"]
    ]
    assert review_calls
    for messages, _kwargs in review_calls:
        roles = [message["role"] for message in messages]
        # 链结构：system + user(深写 prompt) + assistant(初稿) + user(审校指令)
        assert roles == ["system", "user", "assistant", "user"]
        assert "【阶段：章节深写】" in messages[1]["content"]
        review_instruction = messages[-1]["content"]
        assert "【全局蓝图 JSON】" not in review_instruction
        assert "【当前章节全部原始字幕】" not in review_instruction
