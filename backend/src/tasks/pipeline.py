"""
处理管道
整合整个处理流程
"""
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from ..config import config_manager
from ..llm import LLMFactory, BaseLLM
from ..parsers import SRTParser, PDFParser
from ..core import SemanticAligner, ContentFilter, MarkdownGenerator


@dataclass
class PipelineResult:
    """管道处理结果"""
    success: bool
    markdown_content: str = ""
    output_path: str = ""
    error_message: str = ""
    processing_time: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineProgress:
    """管道处理进度"""
    step: str
    progress: int  # 0-100
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


class Pipeline:
    """处理管道"""
    
    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        config: Optional[dict] = None,
        progress_callback: Optional[Callable[[PipelineProgress], None]] = None
    ):
        """
        初始化管道
        
        Args:
            llm: LLM 实例，如果为None则从配置创建
            config: 配置字典，如果为None则加载默认配置
            progress_callback: 进度回调函数
        """
        self.config = config or config_manager.load()
        self.llm = llm or self._create_llm()
        self.progress_callback = progress_callback
        
        # 初始化组件
        self.srt_parser = SRTParser()
        self.pdf_parser = PDFParser()
        self.aligner = SemanticAligner()
        self.filter = ContentFilter(llm=self.llm, use_llm=True)
        self.generator = MarkdownGenerator()
    
    def _create_llm(self) -> BaseLLM:
        """从配置创建LLM实例"""
        llm_config = config_manager.get_llm_config()
        provider = llm_config.pop('provider')
        return LLMFactory.create(provider, llm_config)
    
    def _report_progress(self, step: str, progress: int, message: str):
        """报告进度"""
        if self.progress_callback:
            self.progress_callback(PipelineProgress(
                step=step,
                progress=progress,
                message=message
            ))
    
    def run(
        self,
        srt_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
        output_path: Optional[str] = None,
        title: str = "课程笔记"
    ) -> PipelineResult:
        """
        运行处理管道
        
        Args:
            srt_path: SRT 文件路径
            pdf_path: PDF 文件路径
            output_path: 输出文件路径
            title: 文档标题
            
        Returns:
            处理结果
        """
        import time
        start_time = time.time()
        
        try:
            # 1. 解析字幕
            self._report_progress("parse_srt", 10, "正在解析字幕文件...")
            subtitles = []
            if srt_path:
                subtitle_items = self.srt_parser.parse_file(srt_path)
                subtitles = self.srt_parser.get_segments(subtitle_items)
            
            # 2. 解析PDF
            self._report_progress("parse_pdf", 30, "正在解析PDF课件...")
            chapters = []
            if pdf_path:
                pdf_result = self.pdf_parser.parse(
                    pdf_path,
                    extract_images=self.config.processing.extract_images
                )
                chapters = [
                    {'title': c.title, 'level': c.level, 'page_num': c.page_num}
                    for c in pdf_result['chapters']
                ]
            
            # 3. 内容对齐
            self._report_progress("align", 50, "正在对齐内容...")
            segments = self.aligner.align(subtitles, chapters)
            
            # 4. 过滤和优化
            self._report_progress("filter", 70, "正在过滤和优化内容...")
            segment_dicts = []
            for segment in segments:
                filter_result = self.filter.filter(segment.content)
                if filter_result.should_keep:
                    segment_dicts.append({
                        'chapter_title': segment.chapter_title,
                        'chapter_level': segment.chapter_level,
                        'start_time': segment.start_time,
                        'end_time': segment.end_time,
                        'content': filter_result.filtered_text or segment.content
                    })
            
            # 5. 生成Markdown
            self._report_progress("generate", 90, "正在生成Markdown文档...")
            output = self.generator.generate_with_llm(
                segment_dicts,
                self.llm,
                title=title,
                metadata={'model': self.config.llm_provider}
            )
            
            # 6. 保存结果
            if output_path:
                self.generator.save(output, output_path)
            
            processing_time = time.time() - start_time
            
            self._report_progress("complete", 100, "处理完成！")
            
            return PipelineResult(
                success=True,
                markdown_content=output.content,
                output_path=output_path or "",
                processing_time=processing_time,
                metadata={
                    'segments_count': len(segment_dicts),
                    'chapters_count': len(chapters),
                    'subtitle_segments': len(subtitles)
                }
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            self._report_progress("error", 0, f"处理失败: {str(e)}")
            
            return PipelineResult(
                success=False,
                error_message=str(e),
                processing_time=processing_time
            )
    
    def run_async(
        self,
        srt_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
        output_path: Optional[str] = None,
        title: str = "课程笔记"
    ):
        """异步运行管道（返回协程）"""
        import asyncio
        return asyncio.to_thread(self.run, srt_path, pdf_path, output_path, title)
