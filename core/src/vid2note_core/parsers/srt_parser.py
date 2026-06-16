"""
SRT 字幕解析器
"""

import re
from dataclasses import dataclass


@dataclass
class SubtitleItem:
    """字幕条目"""

    index: int
    start_time: str  # 00:00:00,000
    end_time: str
    start_seconds: float
    end_seconds: float
    text: str


class SRTParser:
    """SRT 字幕解析器"""

    def __init__(self, min_duration: float = 1.0, merge_gap: float = 2.0):
        """
        初始化解析器

        Args:
            min_duration: 最短持续时间（秒），短于此时间的字幕将被合并
            merge_gap: 合并间隔（秒），间隔小于此值的字幕将被合并
        """
        self.min_duration = min_duration
        self.merge_gap = merge_gap

    def parse(self, content: str) -> list[SubtitleItem]:
        """
        解析 SRT 内容

        Args:
            content: SRT 文件内容

        Returns:
            字幕条目列表
        """
        items = []
        blocks = self._split_blocks(content)

        for block in blocks:
            item = self._parse_block(block)
            if item:
                items.append(item)

        # 合并短句
        items = self._merge_short_sentences(items)

        return items

    def parse_file(self, file_path: str) -> list[SubtitleItem]:
        """
        解析 SRT 文件

        Args:
            file_path: SRT 文件路径

        Returns:
            字幕条目列表
        """
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        return self.parse(content)

    def _split_blocks(self, content: str) -> list[str]:
        """将 SRT 内容分割成块"""
        # 标准化换行符
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        # 按空行分割
        blocks = re.split(r"\n\s*\n", content.strip())
        return [b.strip() for b in blocks if b.strip()]

    def _parse_block(self, block: str) -> SubtitleItem | None:
        """解析单个字幕块"""
        lines = block.split("\n")
        if len(lines) < 2:
            return None

        try:
            # 第一行是序号
            index = int(lines[0].strip())

            # 第二行是时间码
            time_line = lines[1].strip()
            time_match = re.match(
                r"(\d{2}:\d{2}:\d{2},\d{3})\s*--\u003e\s*(\d{2}:\d{2}:\d{2},\d{3})", time_line
            )
            if not time_match:
                return None

            start_time = time_match.group(1)
            end_time = time_match.group(2)
            start_seconds = self._time_to_seconds(start_time)
            end_seconds = self._time_to_seconds(end_time)

            # 剩余行是文本
            text = " ".join(lines[2:]).strip()
            # 移除HTML标签
            text = re.sub(r"\u003c[^\u003e]+\u003e", "", text)

            return SubtitleItem(
                index=index,
                start_time=start_time,
                end_time=end_time,
                start_seconds=start_seconds,
                end_seconds=end_seconds,
                text=text,
            )
        except (ValueError, IndexError):
            return None

    def _time_to_seconds(self, time_str: str) -> float:
        """将时间字符串转换为秒数"""
        # 格式: 00:00:00,000
        parts = time_str.replace(",", ".").split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    def _merge_short_sentences(self, items: list[SubtitleItem]) -> list[SubtitleItem]:
        """合并短句和间隔小的字幕"""
        if not items:
            return items

        merged = []
        current = items[0]

        for i in range(1, len(items)):
            next_item = items[i]
            gap = next_item.start_seconds - current.end_seconds

            # 如果间隔小于阈值，合并
            if gap < self.merge_gap:
                current.text += " " + next_item.text
                current.end_time = next_item.end_time
                current.end_seconds = next_item.end_seconds
            else:
                merged.append(current)
                current = next_item

        merged.append(current)
        return merged

    def get_full_text(self, items: list[SubtitleItem]) -> str:
        """获取完整文本"""
        return "\n".join(item.text for item in items)

    def get_segments(self, items: list[SubtitleItem], segment_duration: float = 60.0) -> list[dict]:
        """
        将字幕分段

        Args:
            items: 字幕条目列表
            segment_duration: 每段时长（秒）

        Returns:
            分段列表
        """
        segments = []
        current_segment: list[SubtitleItem] = []
        current_start = items[0].start_seconds if items else 0

        for item in items:
            if item.start_seconds - current_start > segment_duration:
                if current_segment:
                    segments.append(
                        {
                            "start": current_segment[0].start_time,
                            "end": current_segment[-1].end_time,
                            "text": "\n".join(s.text for s in current_segment),
                        }
                    )
                current_segment = [item]
                current_start = item.start_seconds
            else:
                current_segment.append(item)

        # 添加最后一段
        if current_segment:
            segments.append(
                {
                    "start": current_segment[0].start_time,
                    "end": current_segment[-1].end_time,
                    "text": "\n".join(s.text for s in current_segment),
                }
            )

        return segments
