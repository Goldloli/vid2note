"""Golden Dataset 评估脚本

对 Golden Dataset 真实评估两类指标：
  1. ASR 质量：SRT 转录文本 vs reference-asr.txt 的 CER（字错率）与 WER（词错率）
  2. 笔记质量：LLM 整理出的 Markdown vs reference-note.md 的关键词覆盖率与结构相似度

用法：
  python scripts/eval_golden.py                      # 默认评估
  python scripts/eval_golden.py --fixtures tests/fixtures   # 指定 fixtures
  python scripts/eval_golden.py --use-llm qwen       # 用真实 LLM 整理（需 API Key）

评估结果打印 JSON 到 stdout，同时写入 tests/fixtures/eval-report.json。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# ── 文本指标 ──────────────────────────────────────────────


def _edit_distance(a: list[str], b: list[str]) -> int:
    """标准编辑距离（Levenshtein），a/b 为 token 列表。"""
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[m]


def wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate：基于编辑距离，按空格/字符分词。

    中文无空格分隔，按"词组"（标点/空格分割后的片段）计算；
    若两者都无空格则退化为按字计算 CER。
    """
    ref_tokens = reference.split()
    hyp_tokens = hypothesis.split()
    if not ref_tokens:
        return 0.0
    dist = _edit_distance(ref_tokens, hyp_tokens)
    return dist / len(ref_tokens)


def cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate：按单字计算编辑距离。"""
    ref_chars = list(reference)
    hyp_chars = list(hypothesis)
    if not ref_chars:
        return 0.0
    return _edit_distance(ref_chars, hyp_chars) / len(ref_chars)


def keyword_coverage(reference_note: str, generated_note: str) -> float:
    """关键词覆盖率：参考笔记中的关键词（2字以上名词片段）在生成笔记中的出现比例。"""
    # 提取参考笔记关键词：去标点后，取 2-6 字的连续中文片段
    keywords = set(re.findall(r"[\u4e00-\u9fa5]{2,6}", reference_note))
    if not keywords:
        return 0.0
    hit = sum(1 for kw in keywords if kw in generated_note)
    return hit / len(keywords)


def structure_similarity(reference_note: str, generated_note: str) -> float:
    """结构相似度：标题层级（# 数量）与列表项（- 数量）的匹配度。"""
    ref_headers = reference_note.count("#")
    gen_headers = generated_note.count("#")
    ref_lists = reference_note.count("\n-") + reference_note.count("\n*")
    gen_lists = generated_note.count("\n-") + generated_note.count("\n*")

    def _ratio(a: int, b: int) -> float:
        if a == 0 and b == 0:
            return 1.0
        return 1.0 - abs(a - b) / max(a, b, 1)

    return (_ratio(ref_headers, gen_headers) + _ratio(ref_lists, gen_lists)) / 2


def jaccard_similarity(a: str, b: str) -> float:
    """Jaccard 词集合相似度。"""
    sa = set(a.split())
    sb = set(b.split())
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


# ── 主评估流程 ────────────────────────────────────────────


def evaluate_asr(fixtures: Path) -> dict:
    """评估 ASR 质量：SRT 转录 vs reference-asr.txt。"""
    srt_path = fixtures / "sample-video.srt"
    ref_path = fixtures / "reference-asr.txt"
    if not srt_path.exists() or not ref_path.exists():
        return {"error": "ASR 评估缺少 fixtures（sample-video.srt / reference-asr.txt）"}

    from vid2note_core.parsers.srt_parser import SRTParser

    # merge_gap=0：评估时保留每个原始字幕块，不合并连续短句
    parser = SRTParser(merge_gap=0)
    items = parser.parse(srt_path.read_text(encoding="utf-8"))
    # 把标点和多余空白去掉，便于与参考纯文本对比
    asr_text = re.sub(r"[，。！？、,.!?]", " ", " ".join(item.text for item in items))
    asr_text = re.sub(r"\s+", " ", asr_text).strip()

    reference = re.sub(r"\s+", " ", ref_path.read_text(encoding="utf-8").strip())

    return {
        "sample_count": len(items),
        "asr_text_length": len(asr_text),
        "reference_length": len(reference),
        "cer": round(cer(reference, asr_text), 4),
        "wer": round(wer(reference, asr_text), 4),
    }


def evaluate_note(fixtures: Path, use_llm: str | None = None) -> dict:
    """评估笔记质量：生成 Markdown vs reference-note.md。

    use_llm: 若指定 provider（如 qwen），用真实 LLM 整理；否则用 SRT 直接模拟整理结果。
    """
    srt_path = fixtures / "sample-video.srt"
    ref_note_path = fixtures / "reference-note.md"
    if not srt_path.exists() or not ref_note_path.exists():
        return {"error": "笔记评估缺少 fixtures"}

    from vid2note_core.parsers.srt_parser import SRTParser

    parser = SRTParser()
    items = parser.parse(srt_path.read_text(encoding="utf-8"))
    subtitle = "\n".join(item.text for item in items)
    reference_note = ref_note_path.read_text(encoding="utf-8")

    # 生成笔记
    if use_llm:
        try:
            from vid2note_core.llm.factory import LLMFactory

            llm = LLMFactory.create(use_llm, {})
            generated = llm.restructure_content(subtitle, "", 0.3)
        except Exception as e:  # noqa: BLE001
            return {"error": f"LLM 调用失败: {e}", "llm_provider": use_llm}
    else:
        # 无 LLM 时用模拟整理（SRT 转基础 Markdown）作为基线
        lines = ["# 自动整理笔记\n"]
        for item in items:
            lines.append(f"- {item.text}")
        generated = "\n".join(lines)

    return {
        "llm_provider": use_llm or "baseline",
        "reference_keywords_count": len(set(re.findall(r"[\u4e00-\u9fa5]{2,6}", reference_note))),
        "keyword_coverage": round(keyword_coverage(reference_note, generated), 4),
        "structure_similarity": round(structure_similarity(reference_note, generated), 4),
        "jaccard_similarity": round(jaccard_similarity(reference_note, generated), 4),
        "generated_length": len(generated),
    }


def evaluate_golden_dataset(
    fixtures_dir: Path = Path("tests/fixtures"), use_llm: str | None = None
) -> dict:
    """完整 Golden Dataset 评估。"""
    report = {
        "fixtures_dir": str(fixtures_dir),
        "asr_evaluation": evaluate_asr(fixtures_dir),
        "note_evaluation": evaluate_note(fixtures_dir, use_llm),
    }
    # 综合评分
    asr = report["asr_evaluation"]
    note = report["note_evaluation"]
    if "error" not in asr and "error" not in note:
        # ASR 准确率 = 1 - CER；笔记质量取关键词覆盖与结构相似度均值
        asr_acc = 1 - asr["cer"]
        note_quality = (note["keyword_coverage"] + note["structure_similarity"]) / 2
        report["overall_score"] = round((asr_acc + note_quality) / 2, 4)
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Golden Dataset 评估")
    ap.add_argument("--fixtures", default="tests/fixtures", help="fixtures 目录")
    ap.add_argument("--use-llm", default=None, help="LLM provider（如 qwen）用于真实笔记整理")
    ap.add_argument("--output", default="tests/fixtures/eval-report.json", help="报告输出路径")
    args = ap.parse_args()

    result = evaluate_golden_dataset(Path(args.fixtures), use_llm=args.use_llm)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入: {out}")
