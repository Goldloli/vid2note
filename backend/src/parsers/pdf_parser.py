"""
PDF 课件解析器
"""
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
import fitz  # PyMuPDF


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
        doc = fitz.open(file_path)
        
        pages = []
        all_text = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # 提取文本
            text = page.get_text()
            all_text.append(text)
            
            # 提取图片
            images = []
            if extract_images:
                images = self._extract_images_from_page(page, page_num)
            
            pages.append(PDFPage(
                page_num=page_num + 1,
                text=text,
                images=images
            ))
        
        # 识别章节结构
        chapters = self._extract_chapters(pages)
        
        doc.close()
        
        return {
            'total_pages': len(pages),
            'pages': pages,
            'chapters': chapters,
            'full_text': '\n'.join(all_text)
        }
    
    def _extract_images_from_page(self, page: fitz.Page, page_num: int) -> List[Dict]:
        """从页面提取图片"""
        images = []
        image_list = page.get_images()
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = page.parent.extract_image(xref)
            
            if base_image:
                images.append({
                    'xref': xref,
                    'page_num': page_num + 1,
                    'index': img_index,
                    'ext': base_image['ext'],
                    'width': base_image['width'],
                    'height': base_image['height'],
                    'image_data': base_image['image']
                })
        
        return images
    
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
        doc = fitz.open(file_path)
        outline = doc.get_toc()
        doc.close()
        
        return [
            {
                'level': item[0],
                'title': item[1],
                'page': item[2]
            }
            for item in outline
        ]
    
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
        doc = fitz.open(file_path)
        end_page = end_page or len(doc)
        
        texts = []
        for page_num in range(start_page, min(end_page, len(doc))):
            texts.append(doc[page_num].get_text())
        
        doc.close()
        return '\n'.join(texts)
