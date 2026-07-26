"""
Markdown 生成器
生成标准 Markdown 格式的文档
"""
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarkdownOutput:
    """Markdown 输出"""
    title: str
    content: str
    toc: str
    metadata: Dict


class MarkdownGenerator:
    """Markdown 生成器"""
    
    def __init__(self, include_images: bool = False):
        self.include_images = include_images
    
    def generate(
        self,
        segments: List[Dict],
        title: str = "课程笔记",
        metadata: Optional[Dict] = None
    ) -> MarkdownOutput:
        """
        生成 Markdown 文档
        
        Args:
            segments: 对齐后的段落列表
            title: 文档标题
            metadata: 元数据
            
        Returns:
            Markdown 输出
        """
        if metadata is None:
            metadata = {}
        
        # 生成目录
        toc = self._generate_toc(segments)
        
        # 生成正文
        content_parts = []
        
        for segment in segments:
            section = self._generate_section(segment)
            content_parts.append(section)
        
        content = '\n\n'.join(content_parts)
        
        # 添加元数据头部
        header = self._generate_header(title, metadata)
        
        full_content = f"{header}\n\n{toc}\n\n---\n\n{content}"
        
        return MarkdownOutput(
            title=title,
            content=full_content,
            toc=toc,
            metadata=metadata
        )
    
    def _generate_header(self, title: str, metadata: Dict) -> str:
        """生成文档头部"""
        header_lines = [
            f"# {title}",
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ]
        
        if metadata.get('source'):
            header_lines.append(f"来源: {metadata['source']}")
        
        if metadata.get('model'):
            header_lines.append(f"AI模型: {metadata['model']}")
        
        return '\n'.join(header_lines)
    
    def _generate_toc(self, segments: List[Dict]) -> str:
        """生成目录"""
        toc_lines = ["## 目录", ""]
        
        for i, segment in enumerate(segments, 1):
            title = segment.get('chapter_title', f'章节{i}')
            # 生成锚点链接
            anchor = self._generate_anchor(title)
            toc_lines.append(f"{i}. [{title}](#{anchor})")
        
        return '\n'.join(toc_lines)
    
    def _generate_anchor(self, title: str) -> str:
        """生成锚点ID"""
        # 移除特殊字符，转换为小写
        anchor = re.sub(r'[^\w\s-]', '', title)
        anchor = anchor.strip().lower()
        anchor = re.sub(r'\s+', '-', anchor)
        return anchor
    
    def _generate_section(self, segment: Dict) -> str:
        """生成章节内容"""
        lines = []
        
        # 章节标题
        level = segment.get('chapter_level', 1)
        title = segment.get('chapter_title', '未命名章节')
        heading = '#' * min(level + 1, 6)  # 最多6级标题
        lines.append(f"{heading} {title}")
        lines.append("")
        
        # 时间戳
        start_time = segment.get('start_time', '')
        end_time = segment.get('end_time', '')
        if start_time and end_time:
            lines.append(f"> 时间: {start_time} - {end_time}")
            lines.append("")
        
        # 内容
        content = segment.get('content', '')
        if content:
            # 使用LLM重组后的内容，或者原始内容
            lines.append(content)
        
        return '\n'.join(lines)
    
    def generate_with_llm(
        self,
        segments: List[Dict],
        llm,
        title: str = "课程笔记",
        metadata: Optional[Dict] = None,
        batch_size: int = 5,
        fast_mode: bool = False
    ) -> MarkdownOutput:
        """
        使用 LLM 生成优化的 Markdown（支持快速模式）

        Args:
            segments: 对齐后的段落列表
            llm: LLM 实例
            title: 文档标题
            metadata: 元数据
            batch_size: 每批处理的segment数量，默认5个
            fast_mode: 快速模式，直接整体处理不分段（适合短文件）

        Returns:
            Markdown 输出
        """
        if fast_mode:
            return self._generate_fast_mode(segments, llm, title, metadata)

        processed_segments = []
        total_segments = len(segments)

        # 按批次处理
        for batch_start in range(0, total_segments, batch_size):
            batch_end = min(batch_start + batch_size, total_segments)
            batch_segments = segments[batch_start:batch_end]

            print(f"处理批次 {batch_start//batch_size + 1}/{(total_segments + batch_size - 1)//batch_size} ({batch_start+1}-{batch_end}/{total_segments})...")

            try:
                # 批量处理这一批segments
                batch_results = self._process_batch(batch_segments, llm)
                processed_segments.extend(batch_results)
            except Exception as e:
                print(f"批次处理失败: {e}，降级为单条处理")
                # 降级：逐个处理
                for segment in batch_segments:
                    context = segment.get('chapter_title', '')
                    content = segment.get('content', '')
                    if content and llm:
                        try:
                            restructured = llm.restructure_content(content, context)
                            segment = {**segment, 'content': restructured}
                        except Exception as e2:
                            print(f"单条处理失败: {e2}，保留原始内容")
                    processed_segments.append(segment)

        return self.generate(processed_segments, title, metadata)

    def _generate_fast_mode(self, segments: List[Dict], llm, title: str, metadata: Optional[Dict]) -> MarkdownOutput:
        """
        快速模式：直接将所有内容一次性提交给LLM
        适合短文件（<5000字），速度提升5-10倍
        """
        print("[快速模式] 直接整体处理，不分段...")

        # 合并所有内容
        all_content_parts = []
        for i, seg in enumerate(segments):
            chapter = seg.get('chapter_title', f'第{i+1}节')
            content = seg.get('content', '')
            all_content_parts.append(f"## {chapter}\n\n{content}")

        full_content = "\n\n".join(all_content_parts)

        # 估算token数
        total_chars = len(full_content)
        estimated_tokens = int(total_chars * 0.6)  # 中文字符约占0.6 token
        print(f"总内容长度: {total_chars}字符, 预估 {estimated_tokens} tokens")

        # 直接一次性调用LLM
        system_prompt = """你是一个课程笔记整理专家。请将课程内容转换为结构清晰的Markdown笔记。

要求：
1. 去除口语化内容，保留核心知识点
2. 使用表格、列表、加粗等格式
3. 保持章节结构
4. 添加适当的总结和要点提炼"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请将以下课程内容整理为Markdown笔记：\n\n{full_content}"}
        ]

        try:
            response = llm.chat(
                messages,
                temperature=0.3,
                max_tokens=min(8000, max(4000, estimated_tokens)),
                timeout=180
            )

            # 直接生成输出
            return MarkdownOutput(
                title=title,
                content=f"# {title}\n\n{response}",
                toc=self._extract_toc(response),
                metadata=metadata or {}
            )
        except Exception as e:
            print(f"[快速模式] 失败: {e}，降级为批量模式")
            # 降级为批量模式
            return self.generate_with_llm(segments, llm, title, metadata, fast_mode=False)

    def _extract_toc(self, content: str) -> str:
        """从内容提取目录"""
        toc_lines = ["## 目录", ""]

        # 提取所有 ## 标题
        headers = re.findall(r'##+ (.+)', content)
        for i, header in enumerate(headers[:20], 1):  # 最多20个
            toc_lines.append(f"{i}. {header}")

        return "\n".join(toc_lines)

    def _process_batch(self, segments: List[Dict], llm) -> List[Dict]:
        """
        批量处理多个segments

        策略：将多个segment合并为一次LLM调用，要求LLM返回多个section
        """
        if len(segments) == 1:
            # 单条直接处理
            segment = segments[0]
            context = segment.get('chapter_title', '')
            content = segment.get('content', '')
            if content and llm:
                restructured = llm.restructure_content(content, context)
                return [{**segment, 'content': restructured}]
            return [segment]

        # 多条合并处理
        combined_content = []
        for i, seg in enumerate(segments):
            chapter = seg.get('chapter_title', f'Section {i+1}')
            content = seg.get('content', '')
            combined_content.append(f"## {chapter}\n\n{content}")

        all_content = "\n\n---\n\n".join(combined_content)

        # 调用LLM批量处理
        system_prompt = """你是一个课程笔记整理专家。请将以下多个课程段落转换为结构化的Markdown笔记。

要求：
1. 保持每个段落的独立性（用 ## 分隔）
2. 去除口语化内容，保留核心知识点
3. 使用表格、列表、加粗等格式增强可读性
4. 每个段落处理为独立的笔记章节

请确保输出中每个输入段落都有对应的整理结果，用 ## 分隔。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请将以下内容转换为Markdown笔记：\n\n{all_content}"}
        ]

        response = llm.chat(messages, temperature=0.3, max_tokens=4000, timeout=120)

        # 解析返回结果，按 ## 分割
        sections = self._split_response_by_sections(response)

        # 将处理后的内容映射回原始segments
        results = []
        for i, segment in enumerate(segments):
            if i < len(sections):
                # 使用LLM返回的对应section
                results.append({**segment, 'content': sections[i]})
            else:
                # 如果LLM返回的section数量不够，使用原始内容
                results.append(segment)

        return results

    def _split_response_by_sections(self, response: str) -> List[str]:
        """按 ## 分割LLM返回的内容"""
        # 移除开头的空白和markdown代码块标记
        response = response.strip()
        if response.startswith('```markdown'):
            response = response[11:]
        if response.startswith('```'):
            response = response[3:]
        if response.endswith('```'):
            response = response[:-3]
        response = response.strip()

        # 按 ## 分割（保留 ##）
        sections = re.split(r'\n(?=## )', response)

        # 清理每个section
        cleaned_sections = []
        for section in sections:
            section = section.strip()
            if section and len(section) > 10:  # 过滤太短的片段
                cleaned_sections.append(section)

        return cleaned_sections if cleaned_sections else [response]
    
    def save(self, output: MarkdownOutput, file_path: str):
        """保存 Markdown 到文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(output.content)
