"""
简化版处理器 - 优先处理PDF结构，再处理字幕
"""
import re
from pathlib import Path
from typing import Optional, Dict, Any

from ..prompts import (
    PDF_STRUCTURE_ANALYSIS,
    GENERATE_WITH_PDF_REFERENCE,
    GENERATE_DIRECTLY,
    MINDMAP_OUTLINE,
)
from ..utils.logger import TaskLogger
from ..utils.srt_validator import SRTValidator
from .security_constants import (
    PROMPT_INJECTION_PATTERNS,
    DANGEROUS_CHARACTERS,
    MAX_CONTENT_LENGTH,
    INJECTION_WARNING_MESSAGE,
    CONTENT_TRUNCATED_MESSAGE,
)

# Try to import xmind for XMind format export
XMind_AVAILABLE = False
try:
    import xmind
    XMind_AVAILABLE = True
    print(f"[XMind] xmind module loaded successfully from {xmind.__file__}")
except Exception as e:
    XMind_AVAILABLE = False
    print(f"[XMind] Failed to import xmind: {e}")

# Maximum file size: 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024


class SimpleProcessor:
    """简化处理器"""

    def __init__(self, llm, config: Optional[Dict[str, Any]] = None, logger: Optional[TaskLogger] = None):
        self.llm = llm
        self.config = config or {}
        self.logger = logger or TaskLogger("default")

    def _call_llm(self, messages, max_tokens=4096, timeout=120, operation_name="LLM调用"):
        """
        调用LLM（无重试机制，根据用户需求）

        Args:
            messages: 消息列表
            max_tokens: 最大token数
            timeout: 超时时间（秒）
            operation_name: 操作名称（用于日志）

        Returns:
            LLM返回的内容

        Raises:
            RuntimeError: 当API调用失败时
        """
        try:
            return self.llm.chat(messages, max_tokens=max_tokens, timeout=timeout)
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"{operation_name}失败: {error_msg}")
            raise

    def process(self, subtitle_file: str, pdf_file: Optional[str] = None) -> str:
        """
        处理文件生成Markdown

        流程：
        1. 如果有PDF，先分析PDF结构和内容
        2. 提取字幕/文本内容
        3. 用PDF结构参考（如果有）处理字幕
        4. 返回Markdown
        """
        pdf_structure = None

        self.logger.info("开始处理", subtitle_file=subtitle_file, pdf_file=pdf_file)

        # Step 1: 分析PDF（如果有）
        if pdf_file:
            self.logger.info(f"分析PDF结构: {pdf_file}")
            try:
                pdf_structure = self._analyze_pdf(pdf_file)
                self.logger.info(f"PDF分析完成，共 {pdf_structure.get('page_count', 0)} 页")
            except Exception as e:
                self.logger.error(f"PDF分析失败: {e}")
                raise

        # Step 2: 提取字幕文本
        self.logger.info(f"提取字幕: {subtitle_file}")
        try:
            subtitle_text = self._extract_subtitle_text(subtitle_file)
            self.logger.info(f"字幕提取完成，共 {len(subtitle_text)} 字符")
        except Exception as e:
            self.logger.error(f"字幕提取失败: {e}")
            raise

        # Step 3: 生成Markdown
        if pdf_structure:
            self.logger.info("使用PDF参考生成笔记")
            try:
                result = self._generate_with_pdf_reference(subtitle_text, pdf_structure)
                self.logger.info(f"笔记生成完成，共 {len(result)} 字符")
                return result
            except Exception as e:
                self.logger.error(f"笔记生成失败: {e}")
                raise
        else:
            self.logger.info("直接生成笔记")
            try:
                result = self._generate_directly(subtitle_text)
                self.logger.info(f"笔记生成完成，共 {len(result)} 字符")
                return result
            except Exception as e:
                self.logger.error(f"笔记生成失败: {e}")
                raise

    def generate_mindmap(self, markdown_content: str, output_path: Path, format: str = "xmind") -> Path:
        """
        根据Markdown内容生成思维导图

        Args:
            markdown_content: Markdown笔记内容
            output_path: 输出文件路径
            format: 导出格式，'xmind' 或 'png'

        Returns:
            生成的文件路径
        """
        self.logger.info(f"开始生成思维导图，格式: {format}")

        try:
            # 限制内容长度，避免超出LLM上下文限制
            content_for_mindmap = markdown_content[:15000]

            # 使用新的提示词模板获取大纲
            prompt = MINDMAP_OUTLINE.format(
                content=self._sanitize_content(content_for_mindmap)
            )

            result = self._call_llm([
                {"role": "system", "content": "你是一个专业的思维导图结构分析师，擅长提取内容的层级结构"},
                {"role": "user", "content": prompt}
            ], max_tokens=4000, timeout=120, operation_name="思维导图大纲生成")

            # 解析大纲
            outline = self._parse_outline(result)

            if format == "png":
                # 生成 PNG 格式
                return self._create_png_file(outline, output_path)
            else:
                # 生成 XMind 格式
                self.logger.info(f"XMind_AVAILABLE = {XMind_AVAILABLE}")
                if XMind_AVAILABLE:
                    try:
                        self._create_xmind_file(outline, output_path)
                        self.logger.info(f"XMind思维导图已生成: {output_path}")
                        return output_path
                    except Exception as xmind_error:
                        self.logger.error(f"创建XMind文件失败: {xmind_error}")
                        import traceback
                        self.logger.error(f"XMind错误堆栈: {traceback.format_exc()}")
                        raise  # 让外层 catch 去处理 fallback
                else:
                    # Fallback: 保存为文本大纲
                    output_path = output_path.with_suffix('.txt')
                    output_path.write_text(result, encoding='utf-8')
                    self.logger.info(f"文本大纲已保存: {output_path}")
                    return output_path

        except Exception as e:
            self.logger.error(f"思维导图生成失败: {e}")
            # Fallback: 生成基本的XMind文件
            if format == "png":
                return self._generate_fallback_png(markdown_content, output_path)
            else:
                return self._generate_fallback_xmind(markdown_content, output_path)

    def _parse_outline(self, outline_text: str) -> list:
        """
        解析大纲文本为层级结构

        Returns:
            [(level, text), ...] 的列表
        """
        lines = outline_text.strip().split('\n')
        outline = []

        for line in lines:
            # 跳过空行
            if not line.strip():
                continue

            # 计算缩进层级（2空格 = 1级）
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            level = indent // 2

            # 清理文本
            text = stripped.strip()
            if not text:
                continue

            # 移除可能的列表标记
            text = re.sub(r'^[-*•\d.]+\s*', '', text)

            outline.append((level, text))

        return outline

    def _create_xmind_file(self, outline: list, output_path: Path) -> Path:
        """
        创建XMind文件
        """
        if not XMind_AVAILABLE or not outline:
            raise RuntimeError("XMind not available or empty outline")

        workbook = xmind.load(str(output_path))
        sheet = workbook.getPrimarySheet()

        # 设置根主题
        root_topic = sheet.getRootTopic()
        root_text = outline[0][1] if outline else "思维导图"
        root_topic.setTitle(root_text)

        # 用于追踪当前层级的父主题
        parent_stack = [(0, root_topic)]  # (level, topic)

        for level, text in outline[1:]:  # 跳过根主题
            # 找到正确的父主题
            while parent_stack and parent_stack[-1][0] >= level:
                parent_stack.pop()

            if not parent_stack:
                parent_stack.append((0, root_topic))

            # 创建子主题
            parent_topic = parent_stack[-1][1]
            child_topic = parent_topic.addSubTopic()
            child_topic.setTitle(text)

            # 添加到栈
            parent_stack.append((level, child_topic))

        xmind.save(workbook, str(output_path))
        return output_path

    def _generate_fallback_xmind(self, markdown_content: str, output_path: Path) -> Path:
        """
        生成基本的XMind文件作为fallback
        
        Returns:
            实际生成的文件路径（可能是.xmind或.txt）
        """
        try:
            if XMind_AVAILABLE:
                workbook = xmind.load(str(output_path))
                sheet = workbook.getPrimarySheet()
                root = sheet.getRootTopic()

                # 从markdown提取标题作为根主题
                lines = markdown_content.split('\n')
                root_title = "思维导图"
                for line in lines:
                    if line.startswith('# '):
                        root_title = line[2:].strip()
                        break

                root.setTitle(root_title)

                # 提取各级标题作为子主题
                current_parent = root
                level_stack = [(0, root)]

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith('# '):
                        continue  # 根主题已设置
                    elif line.startswith('## '):
                        title = line[3:].strip()
                        topic = root.addSubTopic()
                        topic.setTitle(title)
                        level_stack = [(0, root), (1, topic)]
                        current_parent = topic
                    elif line.startswith('### '):
                        title = line[4:].strip()
                        if len(level_stack) >= 2:
                            parent = level_stack[1][1]
                        else:
                            parent = root
                        topic = parent.addSubTopic()
                        topic.setTitle(title)

                xmind.save(workbook, str(output_path))
                self.logger.info(f"Fallback XMind文件已生成: {output_path}")
                return output_path  # 明确返回生成的文件路径
            else:
                # 保存为文本
                txt_path = output_path.with_suffix('.txt')
                txt_path.write_text(markdown_content[:5000], encoding='utf-8')
                self.logger.info(f"Fallback文本已保存: {txt_path}")
                return txt_path

        except Exception as e:
            self.logger.error(f"Fallback生成失败: {e}")
            # 创建一个简单的文本文件
            txt_path = output_path.with_suffix('.txt')
            txt_path.write_text("思维导图生成失败，请查看Markdown笔记。", encoding='utf-8')
            return txt_path

    def _outline_to_mermaid(self, outline: list) -> str:
        """
        将大纲转换为 Mermaid 思维导图格式
        """
        if not outline:
            return "%%{init: {'themeVariables': {'fontSize': '18px'}}}%%\nmindmap\n  root((思维导图))"

        lines = ["%%{init: {'themeVariables': {'fontSize': '18px'}}}%%", "mindmap"]
        root_text = outline[0][1] if outline else "思维导图"
        lines.append(f'  root(({root_text}))')

        for level, text in outline[1:]:
            indent = "    " + "  " * (level - 1)
            lines.append(f"{indent}{text}")

        return "\n".join(lines)

    def _create_png_file(self, outline: list, output_path: Path) -> Path:
        """
        使用 Playwright 将思维导图渲染为 PNG 图片
        """
        try:
            from playwright.sync_api import sync_playwright

            # 转换为 Mermaid 格式
            mermaid_code = self._outline_to_mermaid(outline)

            # 创建 HTML 内容
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{ margin: 0; padding: 20px; background: white; }}
        .mermaid {{ display: flex; justify-content: center; }}
    </style>
</head>
<body>
    <div class="mermaid">{mermaid_code}</div>
    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
</body>
</html>"""

            output_path = output_path.with_suffix('.png')

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_content)
                # 等待 Mermaid 渲染完成
                page.wait_for_timeout(3000)
                # 截图
                page.screenshot(path=str(output_path), full_page=True)
                browser.close()

            self.logger.info(f"PNG 思维导图已生成: {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"PNG 生成失败: {e}")
            # Fallback: 尝试使用 mermaid.ink 服务
            return self._create_png_via_service(outline, output_path)

    def _create_png_via_service(self, outline: list, output_path: Path) -> Path:
        """
        使用 mermaid.ink 服务生成 PNG（备用方案）
        """
        import base64

        mermaid_code = self._outline_to_mermaid(outline)
        encoded = base64.b64encode(mermaid_code.encode('utf-8')).decode('ascii')
        url = f"https://mermaid.ink/img/{encoded}?type=png&scale=2"

        output_path = output_path.with_suffix('.png')

        try:
            import urllib.request
            urllib.request.urlretrieve(url, str(output_path))
            self.logger.info(f"PNG 思维导图已通过服务生成: {output_path}")
            return output_path
        except Exception as e:
            self.logger.error(f"mermaid.ink 服务也失败了: {e}")
            raise

    def _generate_fallback_png(self, markdown_content: str, output_path: Path) -> Path:
        """
        生成基本的 PNG 文件作为 fallback
        """
        try:
            from playwright.sync_api import sync_playwright

            # 从 markdown 提取标题结构
            lines = markdown_content.split('\n')
            root_title = "思维导图"
            children = []

            for line in lines:
                line = line.strip()
                if line.startswith('# '):
                    root_title = line[2:].strip()
                elif line.startswith('## '):
                    children.append(line[3:].strip())

            # 构建简单的 Mermaid 代码
            mermaid_lines = ["mindmap", f'  root(({root_title}))']
            for child in children[:10]:  # 限制子节点数量
                mermaid_lines.append(f'    {child}')

            mermaid_code = "\n".join(mermaid_lines)

            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{ margin: 0; padding: 20px; background: white; }}
        .mermaid {{ display: flex; justify-content: center; }}
    </style>
</head>
<body>
    <div class="mermaid">{mermaid_code}</div>
    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
</body>
</html>"""

            output_path = output_path.with_suffix('.png')

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_content)
                page.wait_for_timeout(3000)
                page.screenshot(path=str(output_path), full_page=True)
                browser.close()

            self.logger.info(f"Fallback PNG 已生成: {output_path}")
            return output_path

        except Exception as e:
            self.logger.error(f"Fallback PNG 生成失败: {e}")
            # 最终 fallback: 保存为文本
            txt_path = output_path.with_suffix('.txt')
            txt_path.write_text("思维导图图片生成失败，请查看Markdown笔记。", encoding='utf-8')
            return txt_path

    def _validate_file_size(self, file_path: str) -> None:
        """验证文件大小，超过限制则抛出异常"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            raise ValueError(
                f"文件大小超过限制: {file_size} bytes (最大允许: {MAX_FILE_SIZE} bytes)"
            )

    def _sanitize_content(self, content: str) -> str:
        """
        清理用户内容，防止提示词注入攻击
        
        防护层级:
        1. 检测并标记Prompt注入尝试
        2. 转义XML-like标签，防止用户内容被误认为指令
        3. 移除控制字符和危险字符
        4. 限制内容长度
        
        Args:
            content: 原始用户内容
            
        Returns:
            清理后的安全内容
        """
        if not content or not isinstance(content, str):
            return ""
        
        # 层级1: 检测Prompt注入模式
        has_injection_attempt = False
        content_lower = content.lower()
        
        for pattern in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                has_injection_attempt = True
                # 替换匹配的内容，但保留上下文
                content = re.sub(pattern, INJECTION_WARNING_MESSAGE, content, flags=re.IGNORECASE)
        
        # 层级2: 转义XML-like标签，防止用户注入指令
        content = content.replace('<', '&lt;').replace('>', '&gt;')
        
        # 层级3: 移除控制字符和危险字符
        for char, replacement in DANGEROUS_CHARACTERS.items():
            if char not in ['<', '>']:  # 已经处理过了
                content = content.replace(char, replacement)
        
        # 移除其他控制字符 (0x00-0x1f 和 0x7f-0x9f)
        content = ''.join(char for char in content if ord(char) > 31 and ord(char) not in range(127, 160))
        
        # 层级4: 限制内容长度（防止超大内容导致内存问题）
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + CONTENT_TRUNCATED_MESSAGE
        
        return content

    def _analyze_pdf(self, pdf_file: str) -> Dict[str, Any]:
        """分析PDF结构和内容"""
        from pypdf import PdfReader

        # 验证文件大小
        self._validate_file_size(pdf_file)

        reader = PdfReader(pdf_file)
        pages_text = []

        # 从配置读取水印设置
        watermark_patterns = []
        pdf_watermarks = self.config.get('pdf_watermarks', None)
        # 处理 Pydantic 模型或字典两种情况
        if pdf_watermarks is not None:
            # 判断是 Pydantic 模型还是字典
            if hasattr(pdf_watermarks, 'enabled'):
                # Pydantic 模型
                enabled = pdf_watermarks.enabled
                patterns = pdf_watermarks.patterns
            else:
                # 字典（向后兼容）
                enabled = pdf_watermarks.get('enabled', False)
                patterns = pdf_watermarks.get('patterns', [])

            if enabled:
                # 将用户输入的纯文本转换为正则表达式
                for pattern in patterns:
                    if pattern.strip():
                        # 转义特殊字符，添加\s*匹配可能的空白
                        escaped = re.escape(pattern.strip())
                        watermark_patterns.append(escaped + r'\s*')

        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                # 去除水印
                for pattern in watermark_patterns:
                    text = re.sub(pattern, '', text)
                # 清理多余空行
                text = re.sub(r'\n\s*\n+', '\n\n', text)
                text = text.strip()
                if text:
                    pages_text.append(f"=== 第{i+1}页 ===\n{text}")

        full_text = "\n\n".join(pages_text)

        # 使用外部提示词模板，并对内容进行清理
        content_for_analysis = self._sanitize_content(full_text[:30000])
        structure_prompt = PDF_STRUCTURE_ANALYSIS.format(
            content=content_for_analysis
        )

        structure_analysis = self._call_llm([
            {"role": "system", "content": "你是一个课件结构分析专家"},
            {"role": "user", "content": structure_prompt}
        ], max_tokens=4000, timeout=120, operation_name="PDF结构分析")

        return {
            "full_text": full_text,
            "structure_analysis": structure_analysis,
            "page_count": len(reader.pages)
        }

    def _extract_subtitle_text(self, file_path: str) -> str:
        """提取字幕/文本内容"""
        # 验证文件大小
        self._validate_file_size(file_path)
        
        if file_path.endswith('.srt'):
            # 验证SRT文件格式
            validation_result = SRTValidator.validate_file(file_path)
            if not validation_result.is_valid:
                error_msg = f"SRT文件格式无效: {'; '.join(validation_result.errors)}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)
            
            if validation_result.warnings:
                self.logger.warning(f"SRT文件警告: {'; '.join(validation_result.warnings)}")
            
            self.logger.info(f"SRT验证通过: {validation_result.entry_count} 个字幕条目")
            return self._extract_srt_text(file_path)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()

    def _extract_srt_text(self, srt_file: str) -> str:
        """提取SRT纯文本"""
        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 去除时间戳和序号
        lines = content.split('\n')
        text_lines = []

        for line in lines:
            line = line.strip()
            # 跳过序号
            if line.isdigit():
                continue
            # 跳过时间戳行
            if '-->' in line:
                continue
            # 跳过空行
            if not line:
                continue
            # 去除HTML标签
            line = re.sub(r'<[^\u003e]+>', '', line)
            text_lines.append(line)

        return ' '.join(text_lines)

    def _generate_with_pdf_reference(self, subtitle_text: str, pdf_structure: Dict) -> str:
        """用PDF参考生成笔记"""
        # 使用外部提示词模板，并对所有用户内容进行清理
        prompt = GENERATE_WITH_PDF_REFERENCE.format(
            structure_analysis=self._sanitize_content(pdf_structure['structure_analysis']),
            pdf_content=self._sanitize_content(pdf_structure['full_text'][:40000]),
            subtitle_text=self._sanitize_content(subtitle_text)
        )

        result = self._call_llm([
            {"role": "system", "content": "你是一个专业的课程笔记整理专家"},
            {"role": "user", "content": prompt}
        ], max_tokens=8000, timeout=300, operation_name="笔记生成(PDF参考)")

        return self._clean_markdown_output(result)

    def _generate_directly(self, subtitle_text: str) -> str:
        """直接生成笔记（无PDF参考）"""
        # 使用外部提示词模板，并对用户内容进行清理
        prompt = GENERATE_DIRECTLY.format(
            subtitle_text=self._sanitize_content(subtitle_text)
        )

        result = self._call_llm([
            {"role": "system", "content": "你是一个专业的课程笔记整理专家"},
            {"role": "user", "content": prompt}
        ], max_tokens=8000, timeout=300, operation_name="笔记生成(直接)")

        return self._clean_markdown_output(result)

    def _clean_markdown_output(self, content: str) -> str:
        """清理Markdown输出，去除代码块包裹"""
        content = content.strip()

        # 去除开头的 ```markdown 或 ```
        if content.startswith('```markdown'):
            content = content[11:].strip()
        elif content.startswith('```'):
            content = content[3:].strip()

        # 去除结尾的 ```
        if content.endswith('```'):
            content = content[:-3].strip()

        return content
