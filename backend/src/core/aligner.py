"""
语义对齐模块
将字幕内容与 PDF 章节进行对齐
"""
import re
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class AlignedSegment:
    """对齐的段落"""
    chapter_title: str
    chapter_level: int
    start_time: str
    end_time: str
    content: str
    keywords: List[str]


class SemanticAligner:
    """语义对齐器"""
    
    def __init__(self):
        self.min_keyword_length = 2
    
    def align(self, subtitles: List[Dict], chapters: List[Dict]) -> List[AlignedSegment]:
        """
        将字幕与章节对齐

        Args:
            subtitles: 字幕分段列表
            chapters: 章节列表

        Returns:
            对齐后的段落列表
        """
        if not chapters:
            # 如果没有章节信息，按时间自动分段（每90分钟一个段落，进一步减少API调用）
            return self._auto_segment_by_time(subtitles, segment_minutes=90)
        
        # 提取章节关键词
        chapter_keywords = self._extract_chapter_keywords(chapters)
        
        # 将字幕分配到章节
        segments = self._assign_subtitles_to_chapters(
            subtitles, chapters, chapter_keywords
        )
        
        return segments
    
    def _extract_chapter_keywords(self, chapters: List[Dict]) -> Dict[str, List[str]]:
        """从章节标题提取关键词"""
        keywords = {}
        
        for chapter in chapters:
            title = chapter['title']
            # 提取中文词汇和英文单词
            words = self._extract_words(title)
            keywords[title] = words
        
        return keywords
    
    def _extract_words(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        words = []
        
        # 提取英文单词
        english_words = re.findall(r'[a-zA-Z]+', text)
        words.extend([w.lower() for w in english_words if len(w) >= self.min_keyword_length])
        
        # 提取中文词汇（简单实现：连续的中文字符）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        for chars in chinese_chars:
            # 对于较短的词组，直接添加
            if len(chars) <= 6:
                words.append(chars)
            else:
                # 对于较长的文本，尝试提取2-4字的词组
                for i in range(len(chars) - 1):
                    for j in range(2, min(5, len(chars) - i + 1)):
                        words.append(chars[i:i+j])
        
        return list(set(words))
    
    def _assign_subtitles_to_chapters(
        self,
        subtitles: List[Dict],
        chapters: List[Dict],
        chapter_keywords: Dict[str, List[str]]
    ) -> List[AlignedSegment]:
        """将字幕分配到对应的章节"""
        segments = []
        current_chapter_idx = 0
        current_content = []
        current_start = None
        
        for subtitle in subtitles:
            if current_start is None:
                current_start = subtitle['start']
            
            # 计算与每个章节的相似度
            subtitle_text = subtitle['text']
            best_chapter_idx = self._find_best_chapter(
                subtitle_text, chapters, chapter_keywords, current_chapter_idx
            )
            
            # 如果章节变化，保存当前段落
            if best_chapter_idx != current_chapter_idx and current_content:
                chapter = chapters[current_chapter_idx]
                segments.append(AlignedSegment(
                    chapter_title=chapter['title'],
                    chapter_level=chapter.get('level', 1),
                    start_time=current_start,
                    end_time=subtitle['start'],
                    content='\n'.join(current_content),
                    keywords=chapter_keywords.get(chapter['title'], [])
                ))
                current_content = []
                current_start = subtitle['start']
                current_chapter_idx = best_chapter_idx
            
            current_content.append(subtitle_text)
        
        # 添加最后一段
        if current_content and current_chapter_idx < len(chapters):
            chapter = chapters[current_chapter_idx]
            segments.append(AlignedSegment(
                chapter_title=chapter['title'],
                chapter_level=chapter.get('level', 1),
                start_time=current_start or "00:00:00,000",
                end_time=subtitles[-1]['end'] if subtitles else "00:00:00,000",
                content='\n'.join(current_content),
                keywords=chapter_keywords.get(chapter['title'], [])
            ))
        
        return segments
    
    def _find_best_chapter(
        self,
        subtitle_text: str,
        chapters: List[Dict],
        chapter_keywords: Dict[str, List[str]],
        current_idx: int
    ) -> int:
        """找到最适合的章节索引"""
        subtitle_words = set(self._extract_words(subtitle_text))
        
        best_idx = current_idx
        best_score = 0
        
        # 只检查当前章节和后续几个章节
        for i in range(current_idx, min(current_idx + 3, len(chapters))):
            chapter_title = chapters[i]['title']
            keywords = set(chapter_keywords.get(chapter_title, []))
            
            # 计算相似度：共同关键词数量
            if keywords:
                common = subtitle_words & keywords
                score = len(common) / len(keywords)
                
                if score > best_score:
                    best_score = score
                    best_idx = i
        
        return best_idx
    
    def _auto_segment_by_time(self, subtitles: List[Dict], segment_minutes: int = 30) -> List[AlignedSegment]:
        """
        按时间自动分段

        Args:
            subtitles: 字幕分段列表
            segment_minutes: 每个段落的时间长度（分钟）

        Returns:
            按时间分段后的段落列表
        """
        if not subtitles:
            return []

        segments = []
        current_content = []
        current_start = None
        segment_index = 1

        # 将segment_minutes转换为毫秒
        segment_ms = segment_minutes * 60 * 1000

        for subtitle in subtitles:
            if current_start is None:
                current_start = subtitle['start']

            # 解析当前字幕的时间戳
            current_time = self._parse_time_to_ms(subtitle['start'])
            start_time_ms = self._parse_time_to_ms(current_start)

            # 如果超出时间段，保存当前段落并开始新段落
            if current_time - start_time_ms > segment_ms and current_content:
                segments.append(AlignedSegment(
                    chapter_title=f"第{segment_index}部分",
                    chapter_level=1,
                    start_time=current_start,
                    end_time=subtitle['start'],
                    content='\n'.join(current_content),
                    keywords=[]
                ))
                current_content = []
                current_start = subtitle['start']
                segment_index += 1

            current_content.append(subtitle['text'])

        # 添加最后一段
        if current_content:
            segments.append(AlignedSegment(
                chapter_title=f"第{segment_index}部分",
                chapter_level=1,
                start_time=current_start,
                end_time=subtitles[-1]['end'],
                content='\n'.join(current_content),
                keywords=[]
            ))

        return segments

    def _parse_time_to_ms(self, time_str: str) -> int:
        """
        将时间字符串转换为毫秒

        Args:
            time_str: 时间字符串 (格式: HH:MM:SS,mmm 或 HH:MM:SS.mmm)

        Returns:
            毫秒数
        """
        try:
            # 标准化时间字符串
            time_str = time_str.replace(',', '.')
            parts = time_str.split(':')

            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])

            return (hours * 3600 + minutes * 60 + seconds) * 1000
        except Exception:
            return 0

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两段文本的相似度
        
        Returns:
            相似度分数 (0-1)
        """
        words1 = set(self._extract_words(text1))
        words2 = set(self._extract_words(text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
