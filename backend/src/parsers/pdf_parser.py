"""PDF 课件解析器（稳定基础模式使用 pypdf，不包含 OCR）。"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError


@dataclass
class PDFPage:
    """PDF页面"""
    page_num: int
    text: str
    images: List[Dict]


@dataclass
class Chapter:
    """章节信息"""
    title: str
    level: int  # 标题层级（1, 2, 3...）
    page_num: int
    content: str = ""


class PDFParser:
    """PDF 课件解析器"""
    
    def __init__(self):
        self.chapter_patterns = [
            # 第X章
            re.compile(r'第[一二三四五六七八九十\d]+章'),
            # 第X节
            re.compile(r'第[一二三四五六七八九十\d]+节'),
            # 数字编号
            re.compile(r'^\d+[\.\s]'),
            # 中文数字编号
            re.compile(r'^[一二三四五六七八九十]+[、\s]'),
        ]
    
    def parse(self, file_path: str, extract_images: bool = False) -> Dict:
        """
        解析 PDF 文件
        
        Args:
            file_path: PDF 文件路径
            extract_images: 是否提取图片
            
        Returns:
            解析结果字典
        """
        with open(file_path, "rb") as stream:
            reader = PdfReader(stream)
            self._reject_encrypted(reader)
            pages = [
                PDFPage(
                    page_num=page_num,
                    text=page.extract_text() or "",
                    # 基础 pypdf 模式只承诺文本参考，不提取图片。
                    images=[],
                )
                for page_num, page in enumerate(reader.pages, start=1)
            ]
        all_text = [page.text for page in pages]
        chapters = self._extract_chapters(pages)
        return {
            'total_pages': len(pages),
            'pages': pages,
            'chapters': chapters,
            'full_text': '\n'.join(all_text)
        }

    @staticmethod
    def _reject_encrypted(reader: PdfReader) -> None:
        if reader.is_encrypted:
            raise FileNotDecryptedError("暂不支持加密 PDF")
    
    def _extract_chapters(self, pages: List[PDFPage]) -> List[Chapter]:
        """从页面中提取章节结构"""
        chapters = []
        
        for page in pages:
            lines = page.text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 检测章节标题
                level = self._detect_chapter_level(line)
                if level > 0:
                    chapters.append(Chapter(
                        title=line,
                        level=level,
                        page_num=page.page_num
                    ))
        
        return chapters
    
    def _detect_chapter_level(self, text: str) -> int:
        """
        检测文本是否为章节标题，返回层级（0表示不是标题）
        """
        # 第X章
        if re.match(r'第[一二三四五六七八九十\d]+章', text):
            return 1
        
        # 第X节
        if re.match(r'第[一二三四五六七八九十\d]+节', text):
            return 2
        
        # 数字编号（如 1. 1.1 1.1.1）
        if re.match(r'^\d+\.\d+\.\d+', text):
            return 3
        if re.match(r'^\d+\.\d+', text):
            return 2
        if re.match(r'^\d+[\.\s]', text):
            return 3
        
        # 中文编号
        if re.match(r'^[一二三四五六七八九十]+[、\s]', text):
            return 2
        
        return 0
    
    def get_outline(self, file_path: str) -> List[Dict]:
        """
        获取 PDF 大纲（目录）
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            大纲列表
        """
        with open(file_path, "rb") as stream:
            reader = PdfReader(stream)
            self._reject_encrypted(reader)
            result: List[Dict] = []

            def visit(items, level: int) -> None:
                for item in items:
                    if isinstance(item, list):
                        visit(item, level + 1)
                        continue
                    try:
                        page = reader.get_destination_page_number(item) + 1
                    except Exception:  # noqa: BLE001 - 跳过无可定位页码的异常书签
                        continue
                    result.append({
                        'level': level,
                        'title': getattr(item, 'title', str(item)),
                        'page': page,
                    })

            visit(reader.outline, 1)
            return result
    
    def extract_text_by_pages(self, file_path: str, start_page: int = 0, end_page: Optional[int] = None) -> str:
        """
        提取指定页面的文本
        
        Args:
            file_path: PDF 文件路径
            start_page: 起始页（从0开始）
            end_page: 结束页（不包含，None表示到最后）
            
        Returns:
            文本内容
        """
        with open(file_path, "rb") as stream:
            reader = PdfReader(stream)
            self._reject_encrypted(reader)
            stop = len(reader.pages) if end_page is None else min(end_page, len(reader.pages))
            start = max(0, start_page)
            return '\n'.join(
                reader.pages[page_num].extract_text() or ""
                for page_num in range(start, max(start, stop))
            )
