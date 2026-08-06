"""笔记详细程度的 prompt 契约测试。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.simple_processor import SimpleProcessor
from src.prompts.detail_level import (
    DETAIL_LEVEL_INSTRUCTIONS,
    DETAIL_LEVEL_PROFILES,
    normalize_detail_level,
)


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
                f"### E{marker}-001\n"
                f"- 主题：跨段主题 {marker}\n"
                "- 结论：保留本段论证、案例和边界\n"
                "- 原文摘录：\"这是可回查的字幕原句\"\n"
                "- ASR 不确定项：无"
            )
        if "【阶段：全局知识蓝图】" in prompt:
            return self.blueprint_json(prompt)
        if "【阶段：章节深写】" in prompt:
            chapter_id = re.search(r"章节 ID：(C\d+)", prompt).group(1)
            planning = prompt.split("【当前章节规划】", 1)[1].split(
                "【当前章节语义证据】", 1
            )[0]
            evidence_ids = sorted(set(re.findall(r"E\d{2}-\d{3}", planning)))
            return (
                f"## {chapter_id} 初稿\n\n"
                "### 核心论证\n解释结论为什么成立，并综合本章全部证据。\n\n"
                "### 案例与边界\n说明案例作用和适用限制。\n\n"
                f"<!-- COVERED_EVIDENCE_IDS: {', '.join(evidence_ids)} -->"
            )
        if "【阶段：全局质量审计】" in prompt:
            return '{"issues":[]}'
        if "【阶段：问题章节定向修复】" in prompt:
            chapter_id = re.search(r'"chapter_id":"(C\d+)"', prompt).group(1)
            evidence_ids = sorted(set(re.findall(r"E\d{2}-\d{3}", prompt)))
            return (
                f"## {chapter_id} 定向修复终稿\n\n"
                "### 核心论证\n准确解释定义、推导与跨段证据。\n\n"
                "### 案例与边界\n保留独立信息和实践意义。\n\n"
                f"<!-- COVERED_EVIDENCE_IDS: {', '.join(evidence_ids)} -->"
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


def test_four_detail_levels_are_distinct_and_legacy_thorough_maps_to_exhaustive():
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
    assert normalize_detail_level("thorough") == "exhaustive"


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


def test_exhaustive_pipeline_maps_all_evidence_then_runs_one_global_audit():
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
    assert len(llm.calls) == len(expected_chunks) + 1 + chapter_count + 1
    assert progress == [
        ("understand", index, len(expected_chunks))
        for index in range(1, len(expected_chunks) + 1)
    ] + [
        ("blueprint", 1, 1),
        *[
            ("draft", index, chapter_count)
            for index in range(1, chapter_count + 1)
        ],
        *[("review", index, chapter_count) for index in range(1, chapter_count + 1)],
    ]

    prompts = [call[0][-1]["content"] for call in llm.calls]
    blueprint_prompt = prompts[len(expected_chunks)]
    draft_prompts = [
        prompt for prompt in prompts if "【阶段：章节深写】" in prompt
    ]
    audit_prompts = [prompt for prompt in prompts if "【阶段：全局质量审计】" in prompt]
    repair_prompts = [prompt for prompt in prompts if "【阶段：问题章节定向修复】" in prompt]
    for index in range(1, len(expected_chunks) + 1):
        assert f"E{index:02d}-001" in blueprint_prompt
    all_chapter_prompts = "\n".join(draft_prompts)
    assert len(draft_prompts) == chapter_count
    assert len(audit_prompts) == 1
    assert repair_prompts == []
    assert "course_overview" in all_chapter_prompts
    assert "这是可回查的字幕原句" in all_chapter_prompts
    assert "有效内容0000" not in all_chapter_prompts
    assert "有效内容4499" not in all_chapter_prompts
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
            if "【阶段：修复知识蓝图映射】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                missing_match = re.search(r"必须补入的证据 ID[：:]\s*([^\n]+)", prompt)
                assert missing_match is not None
                missing_line = missing_match.group(1)
                missing = sorted(set(re.findall(r"E\d{2}-\d{3}", missing_line)))
                return json.dumps(
                    {"assignments": {item: "C01" for item in missing}, "remove_unknown_ids": []},
                    ensure_ascii=False,
                )
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
    assert sum("【阶段：修复知识蓝图映射】" in prompt for prompt in prompts) == 1
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
def test_exhaustive_draft_keeps_pdf_and_screenshot_semantics(with_pdf):
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
    audit_prompts = [
        prompt for prompt in prompts if "【阶段：全局质量审计】" in prompt
    ]
    assert draft_prompts and len(audit_prompts) == 1
    assert all(
        DETAIL_LEVEL_INSTRUCTIONS["exhaustive"] in prompt
        for prompt in draft_prompts
    )
    assert all("[IMG:HH:MM:SS]" in prompt for prompt in draft_prompts)
    if with_pdf:
        assert all("第一章结构" in prompt for prompt in draft_prompts)
        assert all("讲义参考正文" in prompt for prompt in draft_prompts)
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
        ("audit", "全局质量审计不是有效 JSON"),
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
                "audit": "【阶段：全局质量审计】",
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


def test_exhaustive_targeted_repair_must_return_complete_markdown_structure():
    class InvalidFinalLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：全局质量审计】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return '{"issues":[{"chapter_id":"C01","types":["structure"],"instruction":"修复结构"}]}'
            if "【阶段：问题章节定向修复】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                coverage = re.search(r"<!-- COVERED_EVIDENCE_IDS:.*?-->", prompt).group(0)
                return f"只有一段正文\n{coverage}"
            return super().chat(messages, **kwargs)

    processor = SimpleProcessor(
        InvalidFinalLLM(),
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3000))

    with pytest.raises(RuntimeError, match="终稿章节结构"):
        processor._generate_exhaustive_with_understanding(source)


def test_exhaustive_invalid_initial_structure_is_repaired_locally():
    class InvalidDraftLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：章节深写】" in prompt and "章节 ID：C02" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                planning = prompt.split("【当前章节规划】", 1)[1].split(
                    "【当前章节语义证据】", 1
                )[0]
                evidence_ids = sorted(set(re.findall(r"E\d{2}-\d{3}", planning)))
                return (
                    "## C02 第一部分\n正文\n\n## C02 第二部分\n正文\n\n"
                    f"<!-- COVERED_EVIDENCE_IDS: {', '.join(evidence_ids)} -->"
                )
            return super().chat(messages, **kwargs)

    llm = InvalidDraftLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "exhaustive"})
    result = processor._generate_exhaustive_with_understanding(
        " ".join(f"内容{i:04d}" for i in range(3000))
    )
    repairs = [
        call for call in llm.calls
        if "【阶段：问题章节定向修复】" in call[0][-1]["content"]
    ]
    assert len(repairs) == 1
    assert '"chapter_id":"C02"' in repairs[0][0][-1]["content"]
    assert result.count("## 逻辑章节 2") == 1


def test_exhaustive_missing_coverage_repairs_only_problem_chapter_and_strips_marker():
    class MissingCoverageLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：章节深写】" in prompt and "章节 ID：C01" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return "## C01 初稿\n\n### 核心论证\n有价值正文，但遗漏覆盖声明。"
            return super().chat(messages, **kwargs)

    llm = MissingCoverageLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"内容{i:04d}" for i in range(3000))

    result = processor._generate_exhaustive_with_understanding(source)

    repair_prompts = [call[0][-1]["content"] for call in llm.calls if "【阶段：问题章节定向修复】" in call[0][-1]["content"]]
    assert len(repair_prompts) == 1
    assert "missing_evidence" in repair_prompts[0]
    assert "E01-001" not in result
    assert "COVERED_EVIDENCE_IDS" not in result
    assert "定向修复终稿" not in result


def test_exhaustive_suspicious_asr_terms_get_one_targeted_repair():
    class TerminologyDriftLLM(UnderstandingPipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：章节深写】" in prompt and "章节 ID：C03" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                planning = prompt.split("【当前章节规划】", 1)[1].split("【当前章节语义证据】", 1)[0]
                evidence_ids = sorted(set(re.findall(r"E\d{2}-\d{3}", planning)))
                return (
                    "## C03 初稿\n\nClaude 会创建死丢（Store），使用 FIS5，并持续自我侵化。\n\n"
                    f"<!-- COVERED_EVIDENCE_IDS: {', '.join(evidence_ids)} -->"
                )
            if "【阶段：问题章节定向修复】" in prompt and '"chapter_id":"C03"' in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                evidence_ids = sorted(set(re.findall(r"E\d{2}-\d{3}", prompt)))
                return (
                    "## C03 定向修复终稿\n\n"
                    "Hermes Agent 会创建和更新 Skill，使用 FTS5，"
                    "并持续自我进化。\n\n"
                    f"<!-- COVERED_EVIDENCE_IDS: {', '.join(evidence_ids)} -->"
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
        if "【阶段：问题章节定向修复】" in call[0][-1]["content"]
        and '"chapter_id":"C03"' in call[0][-1]["content"]
    ]
    assert len(fidelity_calls) == 1
    fidelity_instruction = fidelity_calls[0][0][-1]["content"]
    assert "terminology" in fidelity_instruction
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
    evidence_prompt = "\n".join(
        prompt for prompt in prompts if "【阶段：语义证据提取】" in prompt
    )
    draft_prompt = "\n".join(
        prompt for prompt in prompts if "【阶段：章节深写】" in prompt
    )
    assert len(source) > 50000
    assert "最后主题不可丢" in evidence_prompt
    # 章节只消费证据包，不再重复发送完整原始字幕。
    assert "最后主题不可丢" not in draft_prompt


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


def test_exhaustive_global_audit_is_single_compact_call_without_default_rewrites():
    llm = UnderstandingPipelineLLM()
    processor = SimpleProcessor(
        llm,
        config={"note_detail_level": "exhaustive"},
    )
    source = " ".join(f"链式内容{i:04d}" for i in range(1800))

    processor._generate_exhaustive_with_understanding(source)

    audit_calls = [
        call
        for call in llm.calls
        if "【阶段：全局质量审计】" in call[0][-1]["content"]
    ]
    assert len(audit_calls) == 1
    assert [message["role"] for message in audit_calls[0][0]] == ["system", "user"]
    assert not any(
        "【阶段：问题章节定向修复】" in call[0][-1]["content"]
        for call in llm.calls
    )


class ProfilePipelineLLM:
    """三档分层生成桩：严格按 prompt 中的结构契约返回内容。"""

    def __init__(self, *, low_confidence=False, audit_issue=None) -> None:
        self.calls = []
        self.low_confidence = low_confidence
        self.audit_issue = audit_issue

    def chat(self, messages, **kwargs):
        self.calls.append(_snapshot_call(messages, kwargs))
        prompt = messages[-1]["content"]
        if "【阶段：档位内容地图】" in prompt:
            return self._content_map(prompt)
        if "【阶段：修复内容地图 JSON】" in prompt:
            full_prompt = "\n".join(message["content"] for message in messages)
            return self._content_map(full_prompt)
        if "【阶段：档位章节写作】" in prompt:
            return self._draft_batch(prompt)
        if "【阶段：档位全局质量审计】" in prompt:
            if self.audit_issue:
                return json.dumps(
                    {"issues": [self.audit_issue]},
                    ensure_ascii=False,
                )
            return '{"issues":[]}'
        if "【阶段：档位问题章节修复】" in prompt:
            chapter = self._json_between(
                prompt,
                "【问题章节 JSON】",
                "【问题列表 JSON】",
            )
            evidence_ids = chapter["evidence_ids"]
            return (
                f"## {chapter['title']}\n\n"
                "### 修复后的核心论证\n已按证据纠正问题并保留事实边界。\n\n"
                f"<!-- PROFILE_COVERAGE {chapter['chapter_id']}: "
                f"{', '.join(evidence_ids)} -->"
            )
        raise AssertionError(f"未识别的三档 LLM 阶段：{prompt[:80]}")

    def _content_map(self, prompt):
        level = re.search(r"档位标识：([a-z]+)", prompt).group(1)
        min_chapters = int(re.search(r"章节范围：(\d+)-(\d+)", prompt).group(1))
        evidence_target = int(re.search(r"证据数量：恰好 (\d+) 条", prompt).group(1))
        allowed = {
            "concise": ["critical", "high"],
            "balanced": ["critical", "high", "supporting"],
            "detailed": ["critical", "high", "supporting", "context"],
        }[level]
        evidence = []
        chapters = []
        for index in range(1, evidence_target + 1):
            evidence_id = f"N{index:03d}"
            importance = allowed[min((index - 1) % len(allowed), len(allowed) - 1)]
            evidence.append(
                {
                    "evidence_id": evidence_id,
                    "importance": importance,
                    "type": "conclusion" if index == 1 else "method",
                    "topic": f"主题 {index}",
                    "quote": f"可核验原文 {index}",
                    "summary": f"证据结论 {index}",
                    "confidence": (
                        "low" if self.low_confidence and index == 1 else "high"
                    ),
                }
            )
        for index in range(1, min_chapters + 1):
            assigned_ids = [
                f"N{evidence_index:03d}"
                for evidence_index in range(index, evidence_target + 1, min_chapters)
            ]
            chapters.append(
                {
                    "chapter_id": f"C{index:02d}",
                    "title": f"逻辑章节 {index}",
                    "purpose": f"解释主题 {index} 的结论与依据",
                    "key_points": ["核心结论", "成立原因", "实践含义"],
                    "evidence_ids": assigned_ids,
                }
            )
        return json.dumps(
            {
                "title": f"{level} 分层笔记",
                "course_overview": "课程围绕多个主题建立统一论证主线。",
                "terminology": [
                    {
                        "canonical": "OpenClaw",
                        "variants": ["Open Claw"],
                        "confidence": "high",
                    }
                ],
                "evidence": evidence,
                "chapters": chapters,
            },
            ensure_ascii=False,
        )

    @classmethod
    def _draft_batch(cls, prompt):
        chapters = cls._json_between(
            prompt,
            "【当前写作批次 JSON】",
            "【写作要求】",
        )
        parts = []
        for chapter in chapters:
            parts.append(
                f"## {chapter['title']}\n\n"
                "### 核心论证\n完整解释结论、依据和实践意义。\n\n"
                f"<!-- PROFILE_COVERAGE {chapter['chapter_id']}: "
                f"{', '.join(chapter['evidence_ids'])} -->"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _json_between(prompt, start_marker, end_marker):
        raw = prompt.split(start_marker, 1)[1].split(end_marker, 1)[0].strip()
        return json.loads(raw)


def _profile_stage_calls(llm, marker):
    return [
        call for call in llm.calls if marker in call[0][-1]["content"]
    ]


def test_non_exhaustive_profiles_form_strict_quality_and_cost_gradient():
    concise = DETAIL_LEVEL_PROFILES["concise"]
    balanced = DETAIL_LEVEL_PROFILES["balanced"]
    detailed = DETAIL_LEVEL_PROFILES["detailed"]

    assert concise.min_chapters < balanced.min_chapters < detailed.min_chapters
    assert concise.max_chapters < balanced.max_chapters < detailed.max_chapters
    assert concise.chapters_per_batch > balanced.chapters_per_batch
    assert detailed.chapters_per_batch == balanced.chapters_per_batch == 3
    assert len(concise.allowed_importance) < len(balanced.allowed_importance) < len(detailed.allowed_importance)
    assert concise.max_chapter_chars < balanced.max_chapter_chars < detailed.max_chapter_chars
    assert [concise.min_evidence, balanced.min_evidence, detailed.min_evidence] == [
        18,
        30,
        42,
    ]
    assert [concise.audit_mode, balanced.audit_mode, detailed.audit_mode] == [
        "on_failure",
        "risk",
        "risk",
    ]


def test_balanced_keeps_cost_budget_and_adds_decision_ready_overview_contract():
    balanced = DETAIL_LEVEL_PROFILES["balanced"]
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "balanced"})

    prompt = processor._build_profile_content_map_prompt(
        "完整课程字幕",
        profile=balanced,
        pdf_structure=None,
    )

    assert balanced.min_evidence == balanced.max_evidence == 30
    assert balanced.chapters_per_batch == 3
    assert balanced.audit_mode == "risk"
    assert "核心结论" in prompt
    assert "行动摘要" in prompt
    assert "讲者观点" in prompt
    assert "下期预告" in prompt


@pytest.mark.parametrize("level", ["concise", "balanced", "detailed"])
def test_profile_draft_prompt_exposes_tier_specific_chapter_budget(level):
    profile = DETAIL_LEVEL_PROFILES[level]
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": level})
    prompt = processor._build_profile_draft_prompt(
        [
            {
                "chapter_id": "C01",
                "title": "核心主题",
                "purpose": "解释主线",
                "key_points": ["关键结论"],
                "evidence_ids": ["N001"],
                "evidence": [],
            }
        ],
        profile=profile,
        extract_images=False,
    )

    assert f"{profile.min_chapter_chars}-{profile.max_chapter_chars} 字" in prompt


@pytest.mark.parametrize(
    ("level", "expected_chapters", "expected_drafts", "expected_audits"),
    [
        ("concise", 3, 1, 0),
        ("balanced", 5, 2, 0),
        ("detailed", 6, 2, 0),
    ],
)
def test_profiled_long_pipeline_uses_tier_specific_batches_and_audit(
    level,
    expected_chapters,
    expected_drafts,
    expected_audits,
):
    llm = ProfilePipelineLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": level})

    result = processor._generate_profiled_with_understanding(
        " ".join(f"长课程内容{i:04d}" for i in range(2600))
    )

    assert len(_profile_stage_calls(llm, "【阶段：档位内容地图】")) == 1
    assert len(_profile_stage_calls(llm, "【阶段：档位章节写作】")) == expected_drafts
    assert len(_profile_stage_calls(llm, "【阶段：档位全局质量审计】")) == expected_audits
    assert result.count("\n## ") == expected_chapters
    assert result.startswith(f"# {level} 分层笔记")
    assert "PROFILE_COVERAGE" not in result
    assert not re.search(r"\bN\d{3}\b", result)


def test_profile_draft_calls_share_byte_identical_full_context_prefix():
    llm = ProfilePipelineLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "detailed"})
    source = " ".join(f"稳定前缀内容{i:04d}" for i in range(2600))

    processor._generate_profiled_with_understanding(source)

    draft_calls = _profile_stage_calls(llm, "【阶段：档位章节写作】")
    assert len(draft_calls) == 2
    prefix = draft_calls[0][0][:3]
    assert all(call[0][:3] == prefix for call in draft_calls[1:])
    assert source in prefix[1]["content"]
    assert prefix[2]["role"] == "assistant"


def test_profile_content_map_preserves_source_beyond_legacy_50000_limit():
    llm = ProfilePipelineLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "concise"})
    source = ("完整正文" * 13000) + "最后主题不可丢"
    assert len(source) > 50000

    processor._generate_profiled_with_understanding(source)

    map_call = _profile_stage_calls(llm, "【阶段：档位内容地图】")[0]
    assert "最后主题不可丢" in map_call[0][1]["content"]


def test_profile_malformed_map_gets_one_chained_json_repair():
    class MalformedMapLLM(ProfilePipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：档位内容地图】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return '{"title":"未闭合"'
            return super().chat(messages, **kwargs)

    llm = MalformedMapLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "concise"})
    result = processor._generate_profiled_with_understanding("有效课程内容 " * 3000)

    repairs = _profile_stage_calls(llm, "【阶段：修复内容地图 JSON】")
    assert len(repairs) == 1
    assert [message["role"] for message in repairs[0][0]][-2:] == [
        "assistant",
        "user",
    ]
    assert result.startswith("# concise 分层笔记")


def test_profile_valid_map_with_bad_chapter_count_uses_small_mapping_patch():
    class BadChapterCountLLM(ProfilePipelineLLM):
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if "【阶段：修复内容地图章节映射】" in prompt:
                self.calls.append(_snapshot_call(messages, kwargs))
                return json.dumps(
                    {
                        "chapters": [
                            {
                                "id": f"C{index:02d}",
                                "title": f"修复章节 {index}",
                                "purpose": "建立互斥主题结构",
                                "points": ["核心结论"],
                                "evidence": [
                                    f"N{evidence_index:03d}"
                                    for evidence_index in range(index, 31, 5)
                                ],
                            }
                            for index in range(1, 6)
                        ]
                    },
                    ensure_ascii=False,
                )
            return super().chat(messages, **kwargs)

        def _content_map(self, prompt):
            result = json.loads(super()._content_map(prompt))
            result["chapters"] = [
                {
                    "chapter_id": f"C{index:02d}",
                    "title": f"过细章节 {index}",
                    "purpose": "错误的过细结构",
                    "key_points": ["核心结论"],
                    "evidence_ids": [
                        f"N{evidence_index:03d}"
                        for evidence_index in range(index, 31, 7)
                    ],
                }
                for index in range(1, 8)
            ]
            return json.dumps(result, ensure_ascii=False)

    llm = BadChapterCountLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "balanced"})

    result = processor._generate_profiled_with_understanding("有效课程内容 " * 3000)

    patches = _profile_stage_calls(llm, "【阶段：修复内容地图章节映射】")
    assert len(patches) == 1
    assert len(_profile_stage_calls(llm, "【阶段：修复内容地图 JSON】")) == 0
    assert result.count("\n## ") == 5


def test_profile_chapter_patch_normalizes_duplicates_unknowns_and_missing_ids():
    chapters = [
        {"id": "C01", "evidence": ["N001", "N001", "N999"]},
        {"id": "C02", "evidence": ["N002"]},
        {"id": "C03", "evidence": []},
    ]

    normalized = SimpleProcessor._normalize_profile_chapter_patch(
        chapters,
        evidence_ids=["N001", "N002", "N003", "N004"],
    )

    assigned = [
        evidence_id
        for chapter in normalized
        for evidence_id in chapter["evidence"]
    ]
    assert sorted(assigned) == ["N001", "N002", "N003", "N004"]
    assert len(assigned) == len(set(assigned))
    assert "N999" not in assigned


def test_profile_repair_classification_separates_evidence_count_from_chapters():
    assert not SimpleProcessor._profile_error_uses_chapter_patch(
        "详细内容地图需要恰好 42 条证据"
    )
    assert SimpleProcessor._profile_error_uses_chapter_patch(
        "适中内容地图需要 5-6 章"
    )
    assert SimpleProcessor._profile_error_uses_chapter_patch(
        "简洁内容地图遗漏证据映射：N007"
    )


def test_balanced_low_confidence_critical_evidence_triggers_compact_audit():
    llm = ProfilePipelineLLM(low_confidence=True)
    processor = SimpleProcessor(llm, config={"note_detail_level": "balanced"})

    processor._generate_profiled_with_understanding("风险课程内容 " * 3000)

    assert len(_profile_stage_calls(llm, "【阶段：档位全局质量审计】")) == 1


def test_profile_audit_filters_polish_issues_and_caps_paid_repairs():
    raw = json.dumps(
        {
            "issues": [
                {
                    "chapter_id": "C01",
                    "severity": "high",
                    "types": ["style"],
                    "instruction": "润色表达",
                },
                {
                    "chapter_id": "C02",
                    "severity": "high",
                    "types": ["factual"],
                    "instruction": "修正数字",
                },
                {
                    "chapter_id": "C03",
                    "severity": "critical",
                    "types": ["missing_evidence"],
                    "instruction": "补回关键结论",
                },
                {
                    "chapter_id": "C04",
                    "severity": "high",
                    "types": ["terminology"],
                    "instruction": "修正专名",
                },
            ]
        },
        ensure_ascii=False,
    )

    issues = SimpleProcessor._parse_profile_audit(
        raw,
        chapter_ids={"C01", "C02", "C03", "C04"},
    )

    assert [item["chapter_id"] for item in issues] == ["C03", "C02"]
    assert all("style" not in item["types"] for item in issues)


def test_detailed_audit_repairs_only_reported_chapter():
    llm = ProfilePipelineLLM(
        low_confidence=True,
        audit_issue={
            "chapter_id": "C02",
            "types": ["factual"],
            "instruction": "按证据澄清事实边界",
        }
    )
    processor = SimpleProcessor(llm, config={"note_detail_level": "detailed"})

    result = processor._generate_profiled_with_understanding("详细课程内容 " * 3000)

    repairs = _profile_stage_calls(llm, "【阶段：档位问题章节修复】")
    assert len(repairs) == 1
    assert '"chapter_id": "C02"' in repairs[0][0][-1]["content"]
    assert result.count("修复后的核心论证") == 1
    assert "PROFILE_COVERAGE" not in result


@pytest.mark.parametrize("level", ["concise", "balanced", "detailed"])
def test_process_routes_long_non_exhaustive_notes_to_profiled_pipeline(level, monkeypatch):
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": level})
    source = "长字幕" * 5000
    calls = []
    monkeypatch.setattr(processor, "_extract_subtitle_text", lambda *args, **kwargs: source)
    monkeypatch.setattr(
        processor,
        "_generate_profiled_with_understanding",
        lambda text, **kwargs: calls.append((text, kwargs)) or "# 分层笔记",
    )

    result = processor.process("virtual.srt")

    assert result == "# 分层笔记"
    assert calls == [(source, {"extract_images": False})]


def test_profiled_pdf_and_screenshot_semantics_are_kept():
    llm = ProfilePipelineLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "balanced"})

    processor._generate_profiled_with_understanding(
        "带时间戳的完整课程内容 " * 2000,
        pdf_structure={
            "structure_analysis": "讲义分为市场、产品和方法三部分",
            "full_text": "讲义中的规范术语与数据表",
        },
        extract_images=True,
    )

    map_prompt = _profile_stage_calls(llm, "【阶段：档位内容地图】")[0][0][1]["content"]
    draft_prompts = [
        call[0][-1]["content"]
        for call in _profile_stage_calls(llm, "【阶段：档位章节写作】")
    ]
    assert "讲义分为市场、产品和方法三部分" in map_prompt
    assert "讲义中的规范术语与数据表" in map_prompt
    assert draft_prompts and all("[IMG:HH:MM:SS]" in prompt for prompt in draft_prompts)


def test_profiled_input_over_full_context_limit_fails_without_llm_call():
    llm = ProfilePipelineLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "concise"})

    with pytest.raises(ValueError, match="超过全文安全上限"):
        processor._generate_profiled_with_understanding("字" * 500001)

    assert llm.calls == []


def test_short_non_exhaustive_input_keeps_one_call_low_cost_path(monkeypatch):
    llm = RecordingLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "balanced"})
    monkeypatch.setattr(
        processor,
        "_extract_subtitle_text",
        lambda *args, **kwargs: "短课程内容" * 100,
    )

    result = processor.process("virtual.srt")

    assert result == "# 测试笔记"
    assert len(llm.calls) == 1
    assert "【阶段：档位内容地图】" not in llm.calls[0][0][-1]["content"]


def test_concise_missing_coverage_repairs_directly_without_semantic_audit():
    class MissingCoverageLLM(ProfilePipelineLLM):
        @classmethod
        def _draft_batch(cls, prompt):
            result = super()._draft_batch(prompt)
            return re.sub(
                r"<!-- PROFILE_COVERAGE C01:.*?-->",
                "",
                result,
                count=1,
            )

    llm = MissingCoverageLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "concise"})

    result = processor._generate_profiled_with_understanding("简洁课程内容 " * 3000)

    assert len(_profile_stage_calls(llm, "【阶段：档位全局质量审计】")) == 0
    repairs = _profile_stage_calls(llm, "【阶段：档位问题章节修复】")
    assert len(repairs) == 1
    assert '"chapter_id": "C01"' in repairs[0][0][-1]["content"]
    assert result.count("修复后的核心论证") == 1


def test_profile_final_accepts_chapter_titles_after_terminology_normalization():
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "concise"})
    profile = DETAIL_LEVEL_PROFILES["concise"]
    content_map = {
        "title": "术语规范化课程",
        "course_overview": "只规范材料已经确认的专名。",
        "terminology": [
            {
                "canonical": "OpenClaw",
                "variants": ["Open Claw"],
                "confidence": "high",
            }
        ],
        "chapters": [
            {
                "chapter_id": "C01",
                "title": "Open Claw 的核心架构",
                "purpose": "解释架构",
                "key_points": ["结论"],
                "evidence_ids": ["N001"],
            },
            {
                "chapter_id": "C02",
                "title": "应用方式",
                "purpose": "解释应用",
                "key_points": ["方法"],
                "evidence_ids": ["N002"],
            },
            {
                "chapter_id": "C03",
                "title": "风险边界",
                "purpose": "解释风险",
                "key_points": ["风险"],
                "evidence_ids": ["N003"],
            },
        ],
    }
    drafts = [
        "## Open Claw 的核心架构\n\n正文",
        "## 应用方式\n\n正文",
        "## 风险边界\n\n正文",
    ]

    final = processor._assemble_profile_note(content_map, drafts)
    processor._validate_profile_final(
        final,
        content_map=content_map,
        profile=profile,
    )

    assert "## OpenClaw 的核心架构" in final


def test_terminology_normalization_is_idempotent_for_nested_variants():
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "concise"})
    terminology = [
        {
            "canonical": "ChatGPT",
            "variants": ["Chat", "GPT"],
            "confidence": "high",
        },
        {
            "canonical": "腾讯元宝",
            "variants": ["元宝"],
            "confidence": "high",
        },
    ]

    normalized = processor._apply_exhaustive_terminology(
        "ChatGPT、GPT、ChatChatGPTChatGPT；腾讯元宝、元宝、腾讯元宝元宝。",
        terminology,
    )

    assert normalized == "ChatGPT、ChatGPT、ChatGPT；腾讯元宝、腾讯元宝、腾讯元宝。"
    assert processor._apply_exhaustive_terminology(normalized, terminology) == normalized


def test_terminology_normalization_collapses_asr_character_stutter():
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "detailed"})

    normalized = processor._apply_exhaustive_terminology(
        "最复杂的是深爱爱爱爱爱的账号配置。",
        [],
    )

    assert normalized == "最复杂的是深爱的账号配置。"


def test_profile_content_map_uses_and_parses_compact_bounded_schema():
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "balanced"})
    profile = DETAIL_LEVEL_PROFILES["balanced"]

    prompt = processor._build_profile_content_map_prompt(
        "完整课程字幕",
        profile=profile,
        pdf_structure=None,
    )
    compact = {
        "title": "课程标题",
        "course_overview": "中心论证",
        "terminology": [["ChatGPT", ["GPT"], "high"]],
        "evidence": [
            [
                f"N{index:03d}",
                "critical",
                "conclusion",
                "high",
                f"短摘录{index}",
                f"独立信息{index}",
            ]
            for index in range(1, 31)
        ],
        "chapters": [
            {
                "id": f"C{index:02d}",
                "title": f"章节{index}",
                "purpose": "全局作用",
                "points": ["关键结论"],
                "evidence": [
                    f"N{evidence_id:03d}"
                    for evidence_id in range(
                        (index - 1) * 6 + 1,
                        index * 6 + 1,
                    )
                ],
            }
            for index in range(1, 6)
        ],
    }

    parsed = processor._parse_profile_content_map(
        json.dumps(compact, ensure_ascii=False),
        profile=profile,
    )

    assert '"evidence":[["N001"' in prompt
    assert "quote≤36字" in prompt
    assert len(parsed["evidence"]) == 30
    assert parsed["chapters"][0]["chapter_id"] == "C01"
    assert parsed["terminology"][0]["canonical"] == "ChatGPT"


def test_profile_map_uses_source_title_only_as_asr_terminology_clue():
    processor = SimpleProcessor(
        RecordingLLM(),
        config={
            "note_detail_level": "concise",
            "source_title": "一百九十三回：Codex 合并进入 ChatGPT",
        },
    )

    prompt = processor._build_profile_content_map_prompt(
        "字幕把 Codex 错写成扣来死",
        profile=DETAIL_LEVEL_PROFILES["concise"],
        pdf_structure=None,
    )

    assert "一百九十三回：Codex 合并进入 ChatGPT" in prompt
    assert "只用于校正 ASR 专名" in prompt
    assert "不能作为事实证据" in prompt


def test_profile_draft_prompt_requires_numeric_provenance_and_uncertainty():
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "balanced"})
    prompt = processor._build_profile_draft_prompt(
        [
            {
                "chapter_id": "C01",
                "title": "费用与边界",
                "purpose": "解释成本口径",
                "key_points": ["成本结论"],
                "evidence_ids": ["N001"],
                "evidence": [
                    {
                        "evidence_id": "N001",
                        "quote": "讲者说每小时一点五元",
                        "summary": "讲者个案中的小时费率",
                        "confidence": "uncertain",
                    }
                ],
            }
        ],
        profile=DETAIL_LEVEL_PROFILES["balanced"],
        extract_images=False,
    )

    assert "数字、币种、百分比和时间单位" in prompt
    assert "讲者认为" in prompt
    assert "ASR 名称不确定" in prompt


def test_exact_parenthetical_duplicates_are_cleaned_without_semantic_rewrite():
    cleaned = SimpleProcessor._clean_exact_parenthetical_duplicates(
        "推荐使用 vibe coding（vibe coding），也可称为 氛围编程（氛围编程）。"
    )

    assert cleaned == "推荐使用 vibe coding，也可称为 氛围编程。"


@pytest.mark.parametrize(
    ("markdown", "expected_type"),
    [
        (
            "## 费用\n\n这项服务每分钟 0.6 元，也就是每小时 1.5 元。",
            "numeric_consistency",
        ),
        ("## 术语\n\n需要不断进生进生再进生。", "terminology"),
    ],
)
def test_chapter_reliability_gate_detects_numeric_and_asr_failures(
    markdown,
    expected_type,
):
    issues = SimpleProcessor._chapter_reliability_issues(
        markdown,
        chapter_id="C01",
    )

    assert any(expected_type in issue["types"] for issue in issues)


@pytest.mark.parametrize(
    ("markdown", "has_failure"),
    [
        ("159 元可用 600 小时，相当于每分钟 0.4 元。", True),
        ("每分钟 0.6 元，也就是每小时 36 元。", False),
    ],
)
def test_rate_gate_checks_package_math_without_rejecting_valid_conversion(
    markdown,
    has_failure,
):
    assert SimpleProcessor._has_rate_consistency_failure(markdown) is has_failure


def test_profile_reliability_failure_repairs_only_the_problem_chapter():
    class RepeatedAsrLLM(ProfilePipelineLLM):
        @classmethod
        def _draft_batch(cls, prompt):
            result = super()._draft_batch(prompt)
            return result.replace(
                "完整解释结论、依据和实践意义。",
                "完整解释结论，并且进生进生再进生。",
                1,
            )

    llm = RepeatedAsrLLM()
    processor = SimpleProcessor(llm, config={"note_detail_level": "concise"})

    result = processor._generate_profiled_with_understanding("可靠性课程内容 " * 3000)

    repairs = _profile_stage_calls(llm, "【阶段：档位问题章节修复】")
    assert len(repairs) == 1
    assert '"chapter_id": "C01"' in repairs[0][0][-1]["content"]
    assert "进生进生再进生" not in result
    assert result.count("修复后的核心论证") == 1


def _profile_map_for_plan_quality_test():
    llm = ProfilePipelineLLM()
    prompt = "档位标识：balanced\n章节范围：5-6\n证据数量：恰好 30 条"
    return json.loads(llm._content_map(prompt))


@pytest.mark.parametrize(
    ("mutate", "error_pattern"),
    [
        (
            lambda content_map: content_map["chapters"][1].update(
                {
                    "title": content_map["chapters"][0]["title"],
                    "purpose": content_map["chapters"][0]["purpose"],
                    "key_points": content_map["chapters"][0]["key_points"],
                }
            ),
            "章节主题语义重复",
        ),
        (
            lambda content_map: content_map["chapters"][1].update(
                {"title": "下期预告与结束语"}
            ),
            "低价值行政章节",
        ),
    ],
)
def test_profile_content_map_rejects_duplicate_or_administrative_chapters(
    mutate,
    error_pattern,
):
    content_map = _profile_map_for_plan_quality_test()
    mutate(content_map)
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "balanced"})

    with pytest.raises(RuntimeError, match=error_pattern):
        processor._parse_profile_content_map(
            json.dumps(content_map, ensure_ascii=False),
            profile=DETAIL_LEVEL_PROFILES["balanced"],
        )


def _exhaustive_blueprint_for_plan_quality_test():
    return {
        "title": "课程",
        "course_overview": "课程主线",
        "learning_outcomes": ["掌握方法"],
        "terminology": [],
        "chapters": [
            {
                "chapter_id": f"C{index:02d}",
                "title": f"逻辑主题 {index}",
                "purpose": f"解释主题 {index} 的机制与边界",
                "evidence_ids": [f"E01-{index:03d}"],
                "source_chunks": [1],
                "required_points": [f"主题 {index} 的关键方法"],
            }
            for index in range(1, 4)
        ],
    }


@pytest.mark.parametrize(
    ("mutate", "error_pattern"),
    [
        (
            lambda blueprint: blueprint["chapters"][1].update(
                {
                    "title": blueprint["chapters"][0]["title"],
                    "purpose": blueprint["chapters"][0]["purpose"],
                    "required_points": blueprint["chapters"][0]["required_points"],
                }
            ),
            "章节主题语义重复",
        ),
        (
            lambda blueprint: blueprint["chapters"][1].update(
                {"title": "个人事务和下期预告"}
            ),
            "低价值行政章节",
        ),
    ],
)
def test_exhaustive_blueprint_rejects_duplicate_or_administrative_chapters(
    mutate,
    error_pattern,
):
    blueprint = _exhaustive_blueprint_for_plan_quality_test()
    mutate(blueprint)
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "exhaustive"})

    with pytest.raises(RuntimeError, match=error_pattern):
        processor._parse_exhaustive_blueprint(
            json.dumps(blueprint, ensure_ascii=False),
            total_chunks=1,
        )


def test_exhaustive_prompts_filter_admin_noise_and_require_plan_deduplication():
    processor = SimpleProcessor(RecordingLLM(), config={"note_detail_level": "exhaustive"})
    evidence_prompt = processor._build_exhaustive_evidence_prompt(
        "课程正文",
        index=0,
        total=1,
    )
    blueprint_prompt = processor._build_exhaustive_blueprint_prompt(
        "### E01-001\n课程证据"
    )

    assert "下期预告" in evidence_prompt
    assert "会员通知" in evidence_prompt
    assert "语义近重复" in blueprint_prompt
    assert "个人事务" in blueprint_prompt
