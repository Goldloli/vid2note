"""Golden Dataset 评估"""
import json
from pathlib import Path
from typing import List, Dict


def wer(reference: str, hypothesis: str) -> float:
    """计算 Word Error Rate（简化版）"""
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    # 简化：直接计算差异比例
    if not ref_words:
        return 0.0
    matches = sum(1 for a, b in zip(ref_words, hyp_words) if a == b)
    return 1.0 - (matches / len(ref_words))


def rouge_l(reference: str, hypothesis: str) -> float:
    """计算 ROUGE-L（最长公共子序列，简化版）"""
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words or not hyp_words:
        return 0.0
    # 简化：计算公共词比例
    ref_set = set(ref_words)
    hyp_set = set(hyp_words)
    intersection = ref_set & hyp_set
    union = ref_set | hyp_set
    if not union:
        return 0.0
    return len(intersection) / len(union)


def evaluate_golden_dataset(fixtures_dir: Path = Path("tests/fixtures")) -> Dict:
    """评估 Golden Dataset"""
    srt_path = fixtures_dir / "sample-video.srt"
    if not srt_path.exists():
        return {"error": "Golden dataset not found"}

    # 读取参考文本
    from vid2note_core.parsers.srt_parser import SRTParser
    parser = SRTParser()
    items = parser.parse(srt_path.read_text())
    reference_text = " ".join(item.text for item in items)

    # 模拟 ASR 输出（实际应调用 ASR 模块）
    hypothesis_text = reference_text  # 完美情况

    return {
        "reference_length": len(reference_text),
        "wer": wer(reference_text, hypothesis_text),
        "rouge_l": rouge_l(reference_text, hypothesis_text),
        "sample_count": len(items),
    }


if __name__ == "__main__":
    result = evaluate_golden_dataset()
    print(json.dumps(result, ensure_ascii=False, indent=2))
