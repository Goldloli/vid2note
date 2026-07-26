"""
TXT 文本解析器
支持纯文本文件解析，比 SRT 更省 token（无时间戳）
"""
from typing import List, Dict
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TextSegment:
    """文本段落"""
    index: int
    text: str
    start_line: int
    end_line: int


class TXTParser:
    """TXT 文本解析器"""

    def __init__(self, max_segment_length: int = 500):
        """
        初始化解析器

        Args:
            max_segment_length: 每个分段的最大字符数（默认500字符）
        """
        self.max_segment_length = max_segment_length

    def parse_file(self, file_path: str) -> List[TextSegment]:
        """
        解析 TXT 文件

        Args:
            file_path: TXT 文件路径

        Returns:
            文本段落列表
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        return self.parse(content)

    def parse(self, content: str) -> List[TextSegment]:
        """
        解析 TXT 内容

        策略:
        1. 首先尝试按空行分段（段落）
        2. 如果段落过长，再按句子分割
        3. 确保每个分段不超过 max_segment_length

        Args:
            content: 文本内容

        Returns:
            文本段落列表
        """
        # 标准化换行符
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # 首先按空行分段
        raw_paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]

        segments = []
        line_number = 1

        for para in raw_paragraphs:
            lines_in_para = para.count('\n') + 1

            # 如果段落太长，需要分割
            if len(para) > self.max_segment_length:
                sub_segments = self._split_long_paragraph(para, len(segments) + 1, line_number)
                segments.extend(sub_segments)
            else:
                segments.append(TextSegment(
                    index=len(segments) + 1,
                    text=para,
                    start_line=line_number,
                    end_line=line_number + lines_in_para - 1
                ))

            line_number += lines_in_para

        return segments

    def _split_long_paragraph(self, paragraph: str, start_index: int, start_line: int) -> List[TextSegment]:
        """
        将长段落按句子分割

        Args:
            paragraph: 段落文本
            start_index: 起始索引
            start_line: 起始行号

        Returns:
            分割后的段落列表
        """
        # 按句子分割（使用中文和英文的句尾符号）
        import re

        # 匹配句子结束符号（。！？.!?）后面跟着空格或换行或结束
        sentences = re.split(r'([。！？\.\?!]+)', paragraph)

        # 重新组合句子（将分隔符加回）
        combined = []
        for i in range(0, len(sentences), 2):
            if i < len(sentences):
                sentence = sentences[i]
                if i + 1 < len(sentences):
                    sentence += sentences[i + 1]
                if sentence.strip():
                    combined.append(sentence.strip())

        segments = []
        current_text = ""
        current_line = start_line

        for sentence in combined:
            # 如果加上这个句子会超出限制，先保存当前内容
            if current_text and len(current_text) + len(sentence) > self.max_segment_length:
                segments.append(TextSegment(
                    index=start_index + len(segments),
                    text=current_text,
                    start_line=current_line,
                    end_line=current_line  # 简化处理
                ))
                current_text = sentence
            else:
                if current_text:
                    current_text += " "
                current_text += sentence

        # 保存最后一段
        if current_text:
            segments.append(TextSegment(
                index=start_index + len(segments),
                text=current_text,
                start_line=current_line,
                end_line=current_line
            ))

        return segments

    def get_segments_for_aligner(self, segments: List[TextSegment]) -> List[Dict]:
        """
        转换为对齐器所需的格式

        Args:
            segments: 文本段落列表

        Returns:
            对齐器可用的段落列表
        """
        result = []
        for seg in segments:
            result.append({
                'index': seg.index,
                'text': seg.text,
                'start_line': seg.start_line,
                'end_line': seg.end_line
            })
        return result
