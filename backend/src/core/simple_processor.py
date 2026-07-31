"""
简化版处理器 - 优先处理PDF结构，再处理字幕
"""
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from ..prompts import (
    PDF_STRUCTURE_ANALYSIS,
    GENERATE_WITH_PDF_REFERENCE,
    GENERATE_DIRECTLY,
    MINDMAP_OUTLINE,
)
from ..utils.logger import TaskLogger
from ..utils.srt_validator import SRTValidator
from ..prompts.detail_level import detail_instruction, normalize_detail_level
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

# 超详细长笔记的单块目标字符数。显著低于全局 50k 安全清洗上限，给 prompt、
# PDF 结构参考与模型输出预留足够上下文；只影响 exhaustive 长文本。
EXHAUSTIVE_CHUNK_SIZE = 12000
EXHAUSTIVE_BOUNDARY_CONTEXT = 600
EXHAUSTIVE_EVIDENCE_MAX_TOKENS = 6000
EXHAUSTIVE_BLUEPRINT_MAX_TOKENS = 24000
EXHAUSTIVE_DRAFT_MAX_TOKENS = 32000
EXHAUSTIVE_REVIEW_MAX_TOKENS = 32000

# thorough 档（比较详细）：全文常驻上下文的双钴引擎（理解→分章深写→机械组装）。
# 2-3 小时课程字幕约 2.5 万 token，远低于 DeepSeek-v4 的 1M 上下文；超过此字符阈值
# 则退回 exhaustive 分段引擎，避免单次上下文装不下导致静默截断丢内容。
THOROUGH_FULLCONTEXT_MAX_CHARS = 500000
THOROUGH_OUTLINE_MAX_TOKENS = 6000
THOROUGH_CHAPTER_MAX_TOKENS = 6000
THOROUGH_MIN_CHAPTERS = 6
THOROUGH_MAX_CHAPTERS = 8

# 截图嵌入 prompt 指令(extract_images=True 时追加到笔记 prompt;openspec 截图 bug 修复)
SCREENSHOT_INSTRUCTION = """
【关键帧截图(已开启)】
字幕已带 [HH:MM:SS] 时间戳。请在重点画面 / 图表 / 演示 / 需图解处,在笔记中插入标记 [IMG:HH:MM:SS](使用该处字幕的时间戳),后端会自动截取视频该时刻的帧替换为图片。
- 全篇 3-6 处即可,选最有信息量的画面,不要每段都加
- 标记单独成行,格式严格 [IMG:HH:MM:SS]
- 只用字幕中出现过的真实时间戳,不要编造
"""

# 仅作为长字幕 ASR 专名校对候选，不作为笔记事实来源。最终是否采用仍由全局证据
# 上下文裁决；这组高频 AI 术语用于避免把概念、产品和音译相近的普通词混为一谈。
EXHAUSTIVE_AI_TERM_HINTS = (
    "Harness Engineering（驾驭工程，概念）",
    "OpenClaw（产品）",
    "Hermes Agent（产品）",
    "Prompt Engineering",
    "Context Engineering",
    "Skill",
    "Open Source",
    "Sandbox",
    "Shell",
    "MCP",
    "Agent",
)

EXHAUSTIVE_SUSPICIOUS_ASR_TERMS = re.compile(
    r"死丢|FIS5|自我侵化|河曼斯|Harmance|Hailuo|"
    r"哈尼斯工程|哈利斯工程|杀箱|Studio|CRI\s*库|"
    r"神秘系统|平正过律|\bSIF\b|202[35]\s*年\s*2\s*月|"
    r"OpenClow|杀乡|Hermes Agent（Harness Engineering）"
)

EXHAUSTIVE_HIGH_CONFIDENCE_TERM_REPLACEMENTS = (
    ("Hermes Agent（Harness Engineering）", "Hermes Agent"),
    ("沙箱（杀乡）", "沙箱（Sandbox）"),
    ("OpenClow", "OpenClaw"),
    ("死丢（Store）", "Skill"),
    ("死丢（Studio）", "Skill"),
    ("死丢(Store)", "Skill"),
    ("死丢(Studio)", "Skill"),
    ("死丢文件", "Skill 文件"),
    ("死丢", "Skill"),
    ("FIS5", "FTS5"),
    ("自我侵化", "自我进化"),
    ("河曼斯", "Hermes Agent"),
    ("Harmance", "Hermes Agent"),
    ("哈尼斯工程", "Harness Engineering"),
    ("哈利斯工程", "Harness Engineering"),
    ("杀箱", "Sandbox"),
    ("杀乡", "Sandbox"),
)


class SimpleProcessor:
    """简化处理器"""

    def __init__(self, llm, config: Optional[Dict[str, Any]] = None, logger: Optional[TaskLogger] = None):
        self.llm = llm
        self.config = config or {}
        self.note_detail_level = normalize_detail_level(
            self.config.get("note_detail_level", "balanced")
        )
        progress_callback = self.config.get("progress_callback")
        self.progress_callback: Optional[Callable[..., None]] = (
            progress_callback if callable(progress_callback) else None
        )
        usage_callback = self.config.get("usage_callback")
        self.usage_callback: Optional[Callable[..., None]] = (
            usage_callback if callable(usage_callback) else None
        )
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
            result = self.llm.chat(messages, max_tokens=max_tokens, timeout=timeout)
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"{operation_name}失败: {error_msg}")
            raise
        self._report_usage(operation_name)
        return result

    def _report_usage(self, operation_name: str) -> None:
        """上报一次 LLM 调用的归一化用量(openspec「LLM 用量观测」)。

        适配器无 ``last_usage``(mock / 本地模型)或未注入回调时静默跳过;
        回调抛异常只记日志,不得中断笔记生成(同 progress_callback 容错语义)。
        """
        if self.usage_callback is None:
            return
        usage = getattr(self.llm, "last_usage", None)
        if not usage:
            return
        try:
            self.usage_callback(operation_name, usage)
        except Exception as exc:  # noqa: BLE001 - 用量采集失败不得中断生成
            self.logger.warning(f"LLM 用量上报失败({operation_name}): {exc}")

    def process(self, subtitle_file: str, pdf_file: Optional[str] = None, extract_images: bool = False) -> str:
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
            subtitle_text = self._extract_subtitle_text(subtitle_file, keep_timestamp=extract_images)
            self.logger.info(f"字幕提取完成，共 {len(subtitle_text)} 字符")
        except Exception as e:
            self.logger.error(f"字幕提取失败: {e}")
            raise

        # Step 3: 生成Markdown
        if pdf_structure:
            self.logger.info("使用PDF参考生成笔记")
            try:
                if self.note_detail_level == "thorough":
                    result = self._generate_thorough_with_fullcontext(
                        subtitle_text,
                        pdf_structure=pdf_structure,
                        extract_images=extract_images,
                    )
                elif self._requires_exhaustive_chunking(subtitle_text):
                    result = self._generate_exhaustive_with_understanding(
                        subtitle_text,
                        pdf_structure=pdf_structure,
                        extract_images=extract_images,
                    )
                else:
                    result = self._generate_with_pdf_reference(subtitle_text, pdf_structure, extract_images)
                self.logger.info(f"笔记生成完成，共 {len(result)} 字符")
                return result
            except Exception as e:
                self.logger.error(f"笔记生成失败: {e}")
                raise
        else:
            self.logger.info("直接生成笔记")
            try:
                if self.note_detail_level == "thorough":
                    result = self._generate_thorough_with_fullcontext(
                        subtitle_text,
                        extract_images=extract_images,
                    )
                elif self._requires_exhaustive_chunking(subtitle_text):
                    result = self._generate_exhaustive_with_understanding(
                        subtitle_text,
                        extract_images=extract_images,
                    )
                else:
                    result = self._generate_directly(subtitle_text, extract_images)
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

    def _sanitize_content(
        self,
        content: str,
        *,
        max_length: Optional[int] = MAX_CONTENT_LENGTH,
    ) -> str:
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
        
        # 移除其他控制字符；保留换行与制表符，使字幕、证据包和 Markdown
        # 蓝图的结构不在提示词中坍缩成一条长文本。
        content = "".join(
            char
            for char in content
            if char in {"\n", "\r", "\t"}
            or (ord(char) > 31 and ord(char) not in range(127, 160))
        )
        
        # 层级4: 普通调用继续使用原有长度保护。超详细分层流程已经先按安全块
        # 完成语义理解，初稿 / 审校需要完整原文时显式传 max_length=None，
        # 避免历史 50k 截断再次丢掉后半段课程。
        if max_length is not None and len(content) > max_length:
            content = content[:max_length] + CONTENT_TRUNCATED_MESSAGE
        
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

    def _extract_subtitle_text(self, file_path: str, keep_timestamp: bool = False) -> str:
        """提取字幕/文本内容(keep_timestamp 透传 SRT 提取,截图嵌入用)"""
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
            return self._extract_srt_text(file_path, keep_timestamp=keep_timestamp)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()

    def _extract_srt_text(self, srt_file: str, keep_timestamp: bool = False) -> str:
        """提取SRT纯文本(keep_timestamp=True 时每条字幕前缀 [HH:MM:SS],供截图嵌入用)"""
        with open(srt_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 去除时间戳和序号(keep_timestamp 时保留时间戳供截图嵌入)
        lines = content.split('\n')
        text_lines = []
        current_ts = None

        for line in lines:
            line = line.strip()
            # 跳过序号
            if line.isdigit():
                continue
            # 时间戳行:keep_timestamp 时记起始 HH:MM:SS(去毫秒)
            if '-->' in line:
                if keep_timestamp:
                    current_ts = line.split('-->')[0].strip().split(',')[0]
                continue
            # 跳过空行
            if not line:
                continue
            # 去除HTML标签
            line = re.sub(r'<[^\u003e]+>', '', line)
            if keep_timestamp and current_ts:
                text_lines.append(f'[{current_ts}] {line}')
                current_ts = None
            else:
                text_lines.append(line)

        return ' '.join(text_lines)

    def _requires_exhaustive_chunking(self, subtitle_text: str) -> bool:
        """仅对超过安全单块阈值的超详细任务启用多次 LLM 整理。"""
        return (
            self.note_detail_level == "exhaustive"
            and len(subtitle_text or "") > EXHAUSTIVE_CHUNK_SIZE
        )

    def _split_exhaustive_chunks(
        self,
        subtitle_text: str,
        target_chars: int = EXHAUSTIVE_CHUNK_SIZE,
    ) -> list[str]:
        """按字幕条目间空格切块，保证全部非空文本恰好进入一个 chunk。

        :meth:`_extract_srt_text` 会用单个空格拼接字幕条目，因此空格就是天然边界；
        对普通文本同样优先在词/段边界切分。极端超长单条字幕才按字符硬切。
        """
        text = str(subtitle_text or "").strip()
        if not text:
            return []
        target = max(1000, min(int(target_chars or EXHAUSTIVE_CHUNK_SIZE), 30000))
        units = text.split(" ")
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        def flush() -> None:
            nonlocal current, current_len
            if current:
                chunks.append(" ".join(current))
                current = []
                current_len = 0

        for unit in units:
            if not unit:
                continue
            # 单个条目异常超长时先结束当前块，再机械切开；不丢有效字符。
            if len(unit) > target:
                flush()
                chunks.extend(
                    unit[start:start + target]
                    for start in range(0, len(unit), target)
                    if unit[start:start + target]
                )
                continue
            added_len = len(unit) + (1 if current else 0)
            if current and current_len + added_len > target:
                flush()
                added_len = len(unit)
            current.append(unit)
            current_len += added_len
        flush()
        return chunks

    def _generate_exhaustive_with_understanding(
        self,
        subtitle_text: str,
        *,
        pdf_structure: Optional[Dict[str, Any]] = None,
        extract_images: bool = False,
    ) -> str:
        """以全量证据映射、逐章深写和逐章审校生成超详细笔记。

        最终结果只做机械组装，不再交给 LLM 进行全篇重写，避免模型在最后一步
        主动压缩已经覆盖的后半段主题、案例和机制细节。
        """
        chunks = self._split_exhaustive_chunks(subtitle_text)
        if not chunks:
            raise ValueError("超详细笔记生成失败：字幕正文为空")

        total = len(chunks)
        evidence_packets: list[str] = []
        self.logger.info(
            f"超详细笔记启用分层理解：{total} 个字幕段，输入 {len(subtitle_text)} 字符"
        )

        for index, chunk in enumerate(chunks):
            previous_context = (
                chunks[index - 1][-EXHAUSTIVE_BOUNDARY_CONTEXT:]
                if index > 0
                else ""
            )
            next_context = (
                chunks[index + 1][:EXHAUSTIVE_BOUNDARY_CONTEXT]
                if index + 1 < total
                else ""
            )
            evidence_prompt = self._build_exhaustive_evidence_prompt(
                chunk,
                index=index,
                total=total,
                previous_context=previous_context,
                next_context=next_context,
            )
            # 每段独立消息链：首调 + 按需 ID 修复接链尾，使首调的输入与输出
            # 成为可命中的缓存前缀单元(openspec「超详细 prompt 前缀缓存优化」)。
            evidence_messages = [
                {
                    "role": "system",
                    "content": (
                        "你是严谨的课程内容分析师。只从给定字幕提取可追溯语义证据，"
                        "不撰写最终笔记，不补充外部知识。"
                    ),
                },
                {"role": "user", "content": evidence_prompt},
            ]
            evidence = self._call_llm(
                evidence_messages,
                max_tokens=EXHAUSTIVE_EVIDENCE_MAX_TOKENS,
                timeout=300,
                operation_name=f"超详细字幕理解({index + 1}/{total})",
            ).strip()
            if not evidence:
                raise RuntimeError(
                    f"超详细语义证据第 {index + 1}/{total} 段输出为空"
                )
            expected_namespace = rf"\bE{index + 1:02d}-\d{{3}}\b"
            if not re.search(expected_namespace, evidence):
                evidence_messages.append({"role": "assistant", "content": evidence})
                evidence_messages.append(
                    {
                        "role": "user",
                        "content": self._build_exhaustive_evidence_id_repair_instruction(
                            index=index,
                            total=total,
                        ),
                    }
                )
                repaired_evidence = self._call_llm(
                    evidence_messages,
                    max_tokens=EXHAUSTIVE_EVIDENCE_MAX_TOKENS,
                    timeout=300,
                    operation_name=(
                        f"超详细语义证据 ID 修复({index + 1}/{total})"
                    ),
                ).strip()
                if not repaired_evidence or not re.search(
                    expected_namespace,
                    repaired_evidence,
                ):
                    raise RuntimeError(
                        f"超详细语义证据第 {index + 1}/{total} 段"
                        "缺少稳定证据 ID"
                    )
                evidence = repaired_evidence
            evidence_packets.append(evidence)
            self._report_exhaustive_progress("understand", index + 1, total)

        evidence_text = "\n\n".join(
            f"<!-- SOURCE-CHUNK {index + 1}/{total} -->\n{packet}"
            for index, packet in enumerate(evidence_packets)
        )
        blueprint_prompt = self._build_exhaustive_blueprint_prompt(evidence_text)
        # 蓝图独立消息链：JSON 修复、覆盖修复按需接链尾，不重发全部证据
        # (openspec「超详细 prompt 前缀缓存优化」)。
        blueprint_messages = [
            {
                "role": "system",
                "content": (
                    "你是资深课程架构师，负责把全部语义证据综合为一份全局知识蓝图。"
                    "必须合并跨时段主题并保留证据映射。"
                ),
            },
            {"role": "user", "content": blueprint_prompt},
        ]
        blueprint = self._call_llm(
            blueprint_messages,
            max_tokens=EXHAUSTIVE_BLUEPRINT_MAX_TOKENS,
            timeout=420,
            operation_name="超详细课程知识蓝图",
        ).strip()
        if not blueprint:
            raise RuntimeError("超详细全局知识蓝图输出为空")
        expected_evidence_ids = set(
            re.findall(r"\bE\d{2}-\d{3}\b", evidence_text)
        )
        try:
            blueprint_data = self._parse_exhaustive_blueprint(blueprint, total)
        except RuntimeError as parse_error:
            blueprint_messages.append({"role": "assistant", "content": blueprint})
            blueprint_messages.append(
                {
                    "role": "user",
                    "content": self._build_exhaustive_blueprint_json_repair_instruction(
                        parse_error=str(parse_error),
                    ),
                }
            )
            repaired_json = self._call_llm(
                blueprint_messages,
                max_tokens=EXHAUSTIVE_BLUEPRINT_MAX_TOKENS,
                timeout=420,
                operation_name="超详细课程知识蓝图 JSON 修复",
            ).strip()
            if not repaired_json:
                raise RuntimeError("超详细全局知识蓝图 JSON 修复输出为空")
            blueprint_data = self._parse_exhaustive_blueprint(
                repaired_json,
                total,
            )
            blueprint = repaired_json
        missing_ids, unknown_ids = self._exhaustive_blueprint_coverage(
            blueprint_data,
            expected_evidence_ids,
        )
        if missing_ids or unknown_ids:
            blueprint_messages.append({"role": "assistant", "content": blueprint})
            blueprint_messages.append(
                {
                    "role": "user",
                    "content": self._build_exhaustive_blueprint_repair_instruction(
                        missing_ids=missing_ids,
                        unknown_ids=unknown_ids,
                    ),
                }
            )
            repaired_blueprint = self._call_llm(
                blueprint_messages,
                max_tokens=EXHAUSTIVE_BLUEPRINT_MAX_TOKENS,
                timeout=420,
                operation_name="超详细课程知识蓝图修复",
            ).strip()
            if not repaired_blueprint:
                raise RuntimeError("超详细全局知识蓝图修复输出为空")
            blueprint_data = self._parse_exhaustive_blueprint(
                repaired_blueprint,
                total,
            )
            missing_ids, unknown_ids = self._exhaustive_blueprint_coverage(
                blueprint_data,
                expected_evidence_ids,
            )
            if missing_ids or unknown_ids:
                detail = []
                if missing_ids:
                    detail.append(f"遗漏 {', '.join(sorted(missing_ids))}")
                if unknown_ids:
                    detail.append(f"未知 {', '.join(sorted(unknown_ids))}")
                raise RuntimeError(
                    "超详细全局知识蓝图证据映射不完整：" + "；".join(detail)
                )
        self._report_exhaustive_progress("blueprint", 1, 1)

        chapters = blueprint_data["chapters"]
        chapter_total = len(chapters)
        chapter_drafts: list[Dict[str, Any]] = []
        for chapter_index, chapter in enumerate(chapters, start=1):
            chapter_source, chapter_evidence = self._exhaustive_chapter_material(
                chapter,
                chunks=chunks,
                evidence_packets=evidence_packets,
            )
            draft_prompt = self._build_exhaustive_chapter_prompt(
                chapter,
                blueprint=blueprint_data,
                source_text=chapter_source,
                evidence_text=chapter_evidence,
                pdf_structure=pdf_structure,
                extract_images=extract_images,
            )
            # 每章一条独立消息链：审校、格式修复、术语保真依次接链尾，
            # 深写输入与初稿整体成为可命中的缓存前缀单元
            # (openspec「超详细 prompt 前缀缓存优化」)。不跨章累积历史。
            chapter_messages = [
                {
                    "role": "system",
                    "content": (
                        "你是资深课程作者。只写当前逻辑章节，充分使用分配给"
                        "本章的原始字幕和语义证据，输出可直接进入终稿的 Markdown。"
                    ),
                },
                {"role": "user", "content": draft_prompt},
            ]
            draft = self._clean_markdown_output(
                self._call_llm(
                    chapter_messages,
                    max_tokens=EXHAUSTIVE_DRAFT_MAX_TOKENS,
                    timeout=600,
                    operation_name=(
                        f"超详细章节初稿({chapter_index}/{chapter_total})"
                    ),
                )
            )
            if not draft:
                raise RuntimeError(
                    f"超详细章节初稿 {chapter['chapter_id']} 输出为空"
                )
            chapter_messages.append({"role": "assistant", "content": draft})
            chapter_drafts.append(
                {
                    "chapter": chapter,
                    "messages": chapter_messages,
                    "draft": draft,
                }
            )
            self._report_exhaustive_progress(
                "draft",
                chapter_index,
                chapter_total,
            )

        reviewed_chapters: list[str] = []
        for chapter_index, item in enumerate(chapter_drafts, start=1):
            chapter = item["chapter"]
            chain = item["messages"]
            chain.append(
                {
                    "role": "user",
                    "content": self._build_exhaustive_chapter_review_instruction(
                        chapter,
                        extract_images=extract_images,
                    ),
                }
            )
            reviewed = self._clean_markdown_output(
                self._call_llm(
                    chain,
                    max_tokens=EXHAUSTIVE_REVIEW_MAX_TOKENS,
                    timeout=600,
                    operation_name=(
                        f"超详细章节审校({chapter_index}/{chapter_total})"
                    ),
                )
            )
            if not reviewed:
                raise RuntimeError(
                    f"超详细章节审校 {chapter['chapter_id']} 输出为空"
                )
            reviewed = self._normalize_exhaustive_chapter(reviewed)
            reviewed = self._set_exhaustive_chapter_title(
                reviewed,
                chapter["title"],
            )
            try:
                self._validate_exhaustive_chapter(
                    reviewed,
                    chapter_id=chapter["chapter_id"],
                )
            except RuntimeError as validation_error:
                # 章节内容完整但模型偶发泄露 evidence ID 时，执行一次定向清理。
                # 不对普通结构缺失自动“兜底”，避免把不合格章节悄悄发布。
                if "包含内部分析模板" not in str(validation_error):
                    raise
                chain.append({"role": "assistant", "content": reviewed})
                chain.append(
                    {
                        "role": "user",
                        "content": self._build_exhaustive_chapter_format_repair_instruction(
                            chapter,
                        ),
                    }
                )
                repaired = self._clean_markdown_output(
                    self._call_llm(
                        chain,
                        max_tokens=EXHAUSTIVE_REVIEW_MAX_TOKENS,
                        timeout=600,
                        operation_name=(
                            f"超详细章节格式修复"
                            f"({chapter_index}/{chapter_total})"
                        ),
                    )
                )
                if not repaired:
                    raise RuntimeError(
                        f"超详细章节格式修复 {chapter['chapter_id']} 输出为空"
                    )
                reviewed = self._normalize_exhaustive_chapter(repaired)
                reviewed = self._set_exhaustive_chapter_title(
                    reviewed,
                    chapter["title"],
                )
                self._validate_exhaustive_chapter(
                    reviewed,
                    chapter_id=chapter["chapter_id"],
                )
            if EXHAUSTIVE_SUSPICIOUS_ASR_TERMS.search(reviewed):
                chain.append({"role": "assistant", "content": reviewed})
                chain.append(
                    {
                        "role": "user",
                        "content": self._build_exhaustive_terminology_fidelity_instruction(
                            chapter,
                        ),
                    }
                )
                terminology_checked = self._clean_markdown_output(
                    self._call_llm(
                        chain,
                        max_tokens=EXHAUSTIVE_REVIEW_MAX_TOKENS,
                        timeout=600,
                        operation_name=(
                            f"超详细章节术语保真"
                            f"({chapter_index}/{chapter_total})"
                        ),
                    )
                )
                if not terminology_checked:
                    raise RuntimeError(
                        f"超详细章节术语保真 {chapter['chapter_id']} 输出为空"
                    )
                reviewed = self._normalize_exhaustive_chapter(
                    terminology_checked
                )
                reviewed = self._set_exhaustive_chapter_title(
                    reviewed,
                    chapter["title"],
                )
                self._validate_exhaustive_chapter(
                    reviewed,
                    chapter_id=chapter["chapter_id"],
                )
            reviewed = self._apply_exhaustive_ai_term_safeguards(
                reviewed,
                chapter=chapter,
            )
            reviewed_chapters.append(reviewed)
            self._report_exhaustive_progress(
                "review",
                chapter_index,
                chapter_total,
            )

        final_markdown = self._assemble_exhaustive_note(
            blueprint_data,
            reviewed_chapters,
        )
        self._validate_exhaustive_final(final_markdown)
        self.logger.info(
            f"超详细笔记逐章审校完成：输入 {len(subtitle_text)} 字符，"
            f"证据 {len(evidence_text)} 字符，章节 {chapter_total} 个，"
            f"终稿 {len(final_markdown)} 字符"
        )
        return final_markdown

    def _parse_exhaustive_blueprint(
        self,
        content: str,
        total_chunks: int,
    ) -> Dict[str, Any]:
        """解析并规范全局蓝图 JSON，拒绝无法机械验证的自由文本。"""
        raw = str(content or "").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines.pop()
            raw = "\n".join(lines).strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("超详细全局知识蓝图不是有效 JSON")
        try:
            parsed = json.loads(raw[start:end + 1])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"超详细全局知识蓝图 JSON 解析失败：{exc}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("超详细全局知识蓝图必须是 JSON 对象")

        title = str(parsed.get("title") or "").strip()
        overview = str(parsed.get("course_overview") or "").strip()
        learning_outcomes = [
            str(item).strip()
            for item in (parsed.get("learning_outcomes") or [])
            if str(item).strip()
        ]
        raw_chapters = parsed.get("chapters")
        if not title or not overview or not learning_outcomes:
            raise RuntimeError("超详细全局知识蓝图缺少标题、课程主线或学习目标")
        if not isinstance(raw_chapters, list) or len(raw_chapters) < 3:
            raise RuntimeError("超详细全局知识蓝图至少需要三个逻辑章节")

        terminology: list[Dict[str, Any]] = []
        for raw_term in parsed.get("terminology") or []:
            if not isinstance(raw_term, dict):
                continue
            canonical = str(raw_term.get("canonical") or "").strip()
            variants = [
                str(item).strip()
                for item in (raw_term.get("variants") or [])
                if str(item).strip()
            ]
            confidence = str(
                raw_term.get("confidence") or "uncertain"
            ).strip().lower()
            if not canonical or not variants:
                continue
            terminology.append(
                {
                    "canonical": canonical,
                    "variants": list(dict.fromkeys(variants)),
                    "confidence": confidence,
                    "kind": str(raw_term.get("kind") or "").strip(),
                    "note": str(raw_term.get("note") or "").strip(),
                }
            )

        chapters: list[Dict[str, Any]] = []
        seen_chapter_ids: set[str] = set()
        for index, raw_chapter in enumerate(raw_chapters, start=1):
            if not isinstance(raw_chapter, dict):
                raise RuntimeError("超详细全局知识蓝图包含无效章节")
            chapter_id = str(
                raw_chapter.get("chapter_id") or f"C{index:02d}"
            ).strip()
            chapter_title = str(raw_chapter.get("title") or "").strip()
            purpose = str(raw_chapter.get("purpose") or "").strip()
            if (
                not re.fullmatch(r"C\d{2,}", chapter_id)
                or chapter_id in seen_chapter_ids
                or not chapter_title
                or not purpose
            ):
                raise RuntimeError("超详细全局知识蓝图章节 ID、标题或目的无效")
            seen_chapter_ids.add(chapter_id)

            evidence_ids = list(dict.fromkeys(
                evidence_id
                for evidence_id in (
                    str(item).strip()
                    for item in (raw_chapter.get("evidence_ids") or [])
                )
                if re.fullmatch(r"E\d{2}-\d{3}", evidence_id)
            ))
            source_chunks: list[int] = []
            for item in raw_chapter.get("source_chunks") or []:
                try:
                    source_index = int(item)
                except (TypeError, ValueError):
                    continue
                if 1 <= source_index <= total_chunks:
                    source_chunks.append(source_index)
            # 证据 ID 的前缀就是来源 chunk，机械补全可防止蓝图漏传原始字幕。
            source_chunks.extend(
                int(evidence_id[1:3])
                for evidence_id in evidence_ids
                if 1 <= int(evidence_id[1:3]) <= total_chunks
            )
            source_chunks = sorted(set(source_chunks))
            if not source_chunks:
                raise RuntimeError(
                    f"超详细全局知识蓝图章节 {chapter_id} 缺少原始字幕来源"
                )
            required_points = [
                str(item).strip()
                for item in (raw_chapter.get("required_points") or [])
                if str(item).strip()
            ]
            chapters.append(
                {
                    "chapter_id": chapter_id,
                    "title": chapter_title,
                    "purpose": purpose,
                    "evidence_ids": evidence_ids,
                    "source_chunks": source_chunks,
                    "required_points": required_points,
                }
            )
        return {
            "title": title,
            "course_overview": overview,
            "learning_outcomes": learning_outcomes,
            "terminology": terminology,
            "chapters": chapters,
        }

    def _exhaustive_blueprint_coverage(
        self,
        blueprint: Dict[str, Any],
        expected_evidence_ids: set[str],
    ) -> tuple[set[str], set[str]]:
        mapped_ids = {
            evidence_id
            for chapter in blueprint["chapters"]
            for evidence_id in chapter["evidence_ids"]
        }
        return (
            expected_evidence_ids - mapped_ids,
            mapped_ids - expected_evidence_ids,
        )

    def _build_exhaustive_blueprint_repair_instruction(
        self,
        *,
        missing_ids: set[str],
        unknown_ids: set[str],
    ) -> str:
        """蓝图覆盖修复的链尾增量指令；全部证据与上一版蓝图已在链内前缀中。"""
        return f"""
【阶段：修复知识蓝图】
你上一则回复的蓝图未通过机械证据覆盖校验。请修复章节规划并重新返回完整严格 JSON。

必须补入的证据 ID：{", ".join(sorted(missing_ids)) or "无"}
必须移除的未知证据 ID：{", ".join(sorted(unknown_ids)) or "无"}

沿用原 schema；每个真实证据 ID 恰好分配给最合适的章节，必要时可调整章节，
并确保每章 source_chunks 覆盖其证据来源。只返回 JSON。
""".strip()

    def _build_exhaustive_blueprint_json_repair_instruction(
        self,
        *,
        parse_error: str,
    ) -> str:
        """蓝图 JSON 修复的链尾增量指令；全部证据与首次输出已在链内前缀中。"""
        return f"""
【阶段：修复蓝图 JSON】
你上一则回复包含有价值的规划内容，但 JSON 语法或完整性未通过严格解析。
请依据全部语义证据返回一份完整、可解析的蓝图 JSON。

解析错误：{self._sanitize_content(parse_error, max_length=None)}

修复要求：
- 沿用首次蓝图 schema，必须包含 title、course_overview、learning_outcomes、
  terminology 和至少三个 chapters
- 不得遗漏任何真实证据 ID；每个 evidence ID 都要进入最合适章节
- source_chunks 必须覆盖章节证据来源
- 高置信术语只做拼写校对，概念与产品不得混淆；无法确认时标 uncertain
- 如果上一则回复在中途截断，必须根据全部证据补齐，而不是只闭合残缺括号
- 只返回严格 JSON，不要 Markdown 围栏或说明文字
""".strip()

    def _exhaustive_chapter_material(
        self,
        chapter: Dict[str, Any],
        *,
        chunks: list[str],
        evidence_packets: list[str],
    ) -> tuple[str, str]:
        source_parts = []
        evidence_parts = []
        for source_index in chapter["source_chunks"]:
            source_parts.append(
                f"【原始字幕第 {source_index}/{len(chunks)} 段】\n"
                f"{self._sanitize_content(chunks[source_index - 1], max_length=None)}"
            )
            evidence_parts.append(
                f"【语义证据第 {source_index}/{len(chunks)} 段】\n"
                f"{self._sanitize_content(evidence_packets[source_index - 1], max_length=None)}"
            )
        return "\n\n".join(source_parts), "\n\n".join(evidence_parts)

    def _build_exhaustive_chapter_prompt(
        self,
        chapter: Dict[str, Any],
        *,
        blueprint: Dict[str, Any],
        source_text: str,
        evidence_text: str,
        pdf_structure: Optional[Dict[str, Any]],
        extract_images: bool,
    ) -> str:
        # 前缀稳定化：固定指令、全局蓝图与讲义参考（跨章逐字节相同）在前，
        # 章节 ID / 规划 / 证据 / 原文等变量压到末尾，使跨章公共前缀可命中缓存
        # (openspec「超详细 prompt 前缀缓存优化」)。
        prompt = f"""
【阶段：章节深写】
请只撰写蓝图指定的当前章节（章节 ID 见文末），输出一个以 `##` 开头、可直接拼入终稿的完整章节。

{detail_instruction("exhaustive")}

章节写作要求：
- 充分理解当前章节对应的全部原始字幕，而不是把证据列表逐项改写
- 完成定义、结论、推导、因果 / 对比关系、案例证明作用、反例、限制和实践意义
- 跨字幕段的同一主题要综合为一条连贯论证；不得遗漏 required_points
- 严格使用全局蓝图 terminology 中的高置信 canonical 专名，不得重新猜测或混淆概念与产品
- 只使用字幕和讲义可支持的内容；专名或数字无法确认时明确标记不确定
- 不输出 H1，不展示 evidence ID、source chunk、蓝图字段或写作过程
- 章节内部使用必要的 H3、列表、表格与时间戳，让读者能独立学习和复用
"""
        if extract_images:
            prompt += (
                "\n"
                + SCREENSHOT_INSTRUCTION.strip()
                + "\n这是逐章写作：本章仅在确有高信息量画面时保留 0-1 个标记，"
                "避免全篇截图过密。\n"
            )
        prompt += f"""
直接返回当前章节的纯 Markdown，不要包裹代码块。

【全局蓝图 JSON】
{json.dumps(blueprint, ensure_ascii=False, indent=2)}

{self._exhaustive_reference_context(pdf_structure)}

【当前章节】
章节 ID：{chapter["chapter_id"]}

【当前章节规划】
{json.dumps(chapter, ensure_ascii=False, indent=2)}

【当前章节语义证据】
{self._sanitize_content(evidence_text, max_length=None)}

【当前章节全部原始字幕】
{self._sanitize_content(source_text, max_length=None)}
""".strip()
        return prompt

    def _build_exhaustive_chapter_review_instruction(
        self,
        chapter: Dict[str, Any],
        *,
        extract_images: bool,
    ) -> str:
        """章节审校的链尾增量指令；蓝图、规划、证据、原文与初稿已在链内前缀中。"""
        instruction = f"""
【阶段：章节编辑审校】
现在你是课程笔记章节编辑和事实审校员。以上是你要审校的章节初稿
（章节 ID：{chapter["chapter_id"]}，全局蓝图、章节规划、语义证据与原始字幕见对话前文）。
请对照前文全部原始材料对它执行最终事实核验和深度编辑，直接输出一个以 `##` 开头的终稿章节。

内部逐项审查但不展示评分或过程：
1. 事实忠实度：结论、数字、专名和因果是否有原始材料支持
2. 主题覆盖：当前章节的每项证据和 required_points 是否得到有意义的表达
3. 结构连贯：定义、机制、论证、案例、边界和行动启示是否自然衔接
4. 信息价值：是否解释“为什么、如何成立、例子证明什么”，而非字幕复述
5. 可读性：是否具体、清晰、深入且适合学习复用

编辑规则：
- 补回初稿遗漏的事实、论证、案例、反例、限制、注意事项和有效问答
- 可以去除无信息重复，但不得为了简短删除任何具有独立信息价值的内容
- 对照全局 terminology 统一高置信专名；不得把 Hermes Agent 写成 Claude / Hailuo，
  不得把 Harness Engineering 概念写成产品名，也不得保留已裁决的 ASR 音译
- 不得引入外部事实；ASR 无法确认的内容保留不确定性，不得擅自猜测映射
- 只输出当前章节，恰好一个 H2，不输出 H1、证据 ID、source chunk 或内部指令

直接返回当前章节的最终纯 Markdown，不要包裹代码块。
""".strip()
        if extract_images:
            instruction += (
                "\n\n"
                + SCREENSHOT_INSTRUCTION.strip()
                + "\n这是逐章审校：仅保留本章 0-1 个真正有教学价值且时间戳可靠的"
                "截图标记，不得把已有有效标记全部删除。"
            )
        return instruction

    def _normalize_exhaustive_chapter(self, content: str) -> str:
        """把模型偶发的章节 H1 降为 H2，不改写章节正文。"""
        normalized = re.sub(r"(?m)^#\s+", "## ", str(content or "").strip())
        return normalized.strip()

    def _set_exhaustive_chapter_title(
        self,
        content: str,
        chapter_title: str,
    ) -> str:
        """用已校验蓝图标题替换首个 H2，避免 C06 等内部章节 ID 泄露。"""
        title = re.sub(r"^#+\s*", "", str(chapter_title or "")).strip()
        if not title or not re.match(r"^##\s+\S", content):
            return content
        return re.sub(
            r"^##\s+.*$",
            f"## {title}",
            content,
            count=1,
            flags=re.MULTILINE,
        )

    def _apply_exhaustive_terminology(
        self,
        content: str,
        terminology: list[Dict[str, Any]],
    ) -> str:
        """机械应用蓝图中高置信术语，只统一拼写，不生成新事实。"""
        normalized = str(content or "")
        for term in terminology:
            confidence = str(term.get("confidence") or "").lower()
            if confidence not in {"high", "confirmed", "高", "高置信"}:
                continue
            canonical = str(term.get("canonical") or "").strip()
            if not canonical:
                continue
            variants = sorted(
                {
                    str(item).strip()
                    for item in (term.get("variants") or [])
                    if str(item).strip() and str(item).strip() != canonical
                },
                key=len,
                reverse=True,
            )
            for variant in variants:
                normalized = normalized.replace(variant, canonical)
        return normalized

    def _build_exhaustive_chapter_format_repair_instruction(
        self,
        chapter: Dict[str, Any],
    ) -> str:
        """章节格式修复的链尾增量指令；待清理章节是链内上一则 assistant 回复。"""
        return f"""
【阶段：章节格式修复】
章节 ID：{chapter["chapter_id"]}
你上一则回复的章节内容已经完成事实审校，但混入了 evidence ID、source chunk、
证据命名空间或内部阶段标签。请只删除这些内部分析标记及其无意义连接词，重新输出完整章节。

严格要求：
- 不得概括、压缩或删除正文信息
- 不得改写事实、专名、数字、论证、案例、边界、时间戳和截图标记
- 保持原有 Markdown 层级，输出恰好一个 H2，不输出 H1
- 不得保留 `E01-001` 这类证据 ID、source chunk 或内部阶段标签
- 只返回清理后的完整章节，不解释修改过程
""".strip()

    def _build_exhaustive_terminology_fidelity_instruction(
        self,
        chapter: Dict[str, Any],
    ) -> str:
        """术语保真的链尾增量指令；术语表、字幕、证据与待校对章节均在链内前缀中。"""
        return f"""
【阶段：术语保真审校】
章节 ID：{chapter["chapter_id"]}
你上一则回复的章节内容和结构已经完成审校，但仍含疑似 ASR 音译、错拼、年份或
概念 / 产品 / 机制归属混淆。请对照对话前文的全局术语表、原始字幕上下文和语义证据，
执行实体保真，重新输出完整章节。

严格要求：
- 不得概括、删减或扩写正文事实，不得改变论证、案例、可靠数字、时间戳和截图标记
- 优先使用 terminology 中 confidence=high 的 canonical；uncertain 项必须保留不确定标记
- Harness Engineering 是概念，OpenClaw 与 Hermes Agent 是产品，三者不得混淆
- OpenClaw 的市场爆发、政策和资本类比与 Hermes Agent 的安装、SQLite/FTS5 记忆、
  Memory、Skill 自我改进和安全机制必须归入各自产品，不能张冠李戴
- Hermes Agent 的可持续学习流程使用 Memory 与 Skill；不得把 Skill 音译成 Store / Studio
- 不得把 Hermes Agent 的机制改写成 Claude / Hailuo；但其他上下文真实提及 Claude 时保留
- `FIS5` 等高置信错拼应按上下文校为 `FTS5`；无法确认的安全层名称不要强行猜测
- 原字幕没有明确年份时不得编造；本课程与任务时间能确认的 OpenClaw 事件发生在 2026 年，
  不得写成 2023 或 2025 年
- 可以在当前章内移动直接归错产品的小节，但不得删除其中任何事实或改变原有论证作用
- 只返回完整章节，恰好一个 H2，不输出 H1、证据 ID 或校对说明
""".strip()

    def _validate_exhaustive_chapter(
        self,
        content: str,
        *,
        chapter_id: str,
    ) -> None:
        h1_count = len(re.findall(r"(?m)^#\s+\S", content))
        h2_count = len(re.findall(r"(?m)^##\s+\S", content))
        if h1_count or h2_count != 1 or not re.match(r"^##\s+\S", content):
            raise RuntimeError(
                f"超详细终稿章节结构不完整：{chapter_id} 必须恰好包含一个 H2"
            )
        if re.search(
            r"(?i)\bE\d{2}-\d{3}\b|SOURCE-CHUNK|证据命名空间|【阶段：",
            content,
        ):
            raise RuntimeError(
                f"超详细终稿章节结构不完整：{chapter_id} 包含内部分析模板"
            )

    def _assemble_exhaustive_note(
        self,
        blueprint: Dict[str, Any],
        reviewed_chapters: list[str],
    ) -> str:
        """按蓝图机械组装终稿；此处不再调用模型或压缩章节。"""
        title = re.sub(r"^#+\s*", "", blueprint["title"]).strip()
        overview = blueprint["course_overview"].strip()
        outcomes = "\n".join(
            f"- {item}" for item in blueprint["learning_outcomes"]
        )
        front_matter = (
            f"# {title}\n\n"
            "## 课程主线与学习目标\n\n"
            f"{overview}\n\n"
            "### 学完后你应该能够\n\n"
            f"{outcomes}"
        )
        assembled = "\n\n".join([front_matter, *reviewed_chapters]).strip()
        assembled = self._apply_exhaustive_terminology(
            assembled,
            blueprint.get("terminology") or [],
        )
        return self._apply_exhaustive_ai_term_safeguards(
            assembled,
            chapter={},
        )

    def _apply_exhaustive_ai_term_safeguards(
        self,
        content: str,
        *,
        chapter: Dict[str, Any],
    ) -> str:
        """对已审校章节应用极窄的高置信 AI 专名兜底。"""
        normalized = str(content or "")
        for variant, canonical in EXHAUSTIVE_HIGH_CONFIDENCE_TERM_REPLACEMENTS:
            normalized = normalized.replace(variant, canonical)
        chapter_title = str(chapter.get("title") or "")
        if "Hermes Agent" in chapter_title:
            normalized = re.sub(r"\bStudio\b", "Skill", normalized)
            normalized = re.sub(
                r"\bCRI\s*库",
                "SQLite 数据库",
                normalized,
            )
            normalized = normalized.replace(
                "神秘系统",
                "某系统安全层（ASR 名称不确定）",
            )
            normalized = normalized.replace(
                "平正过律",
                "某过滤安全层（ASR 名称不确定）",
            )
            normalized = re.sub(
                r"\bSIF\b(?!（ASR 名称不确定）)",
                "SIF（ASR 名称不确定）",
                normalized,
            )
        if "OpenClaw" in chapter_title:
            normalized = re.sub(
                r"202[35]\s*年\s*2\s*月",
                "2026 年 2 月",
                normalized,
            )
            normalized = normalized.replace(
                "OpenClaw 及 OpenClaw 发展的",
                "OpenClaw 及 OPC 发展的",
            )
        if (
            "Hermes Agent" in chapter_title
            and "Claude" in normalized
            and re.search(r"Skill|FTS5|自更新|安全防线", normalized)
        ):
            normalized = normalized.replace("Claude", "Hermes Agent")
        return normalized

    def _generate_exhaustive_in_chunks(
        self,
        subtitle_text: str,
        *,
        pdf_structure: Optional[Dict[str, Any]] = None,
        extract_images: bool = False,
    ) -> str:
        """兼容旧内部调用名，实际执行理解驱动的超详细生成。"""
        return self._generate_exhaustive_with_understanding(
            subtitle_text,
            pdf_structure=pdf_structure,
            extract_images=extract_images,
        )

    # ------------------------------------------------------------------ #
    # thorough 档（比较详细）：全文常驻上下文的双钴引擎
    # ------------------------------------------------------------------ #
    def _generate_thorough_with_fullcontext(
        self,
        subtitle_text: str,
        *,
        pdf_structure: Optional[Dict[str, Any]] = None,
        extract_images: bool = False,
    ) -> str:
        """比较详细档：全文常驻上下文的双钴引擎。

        依赖 LLM 长上下文把全部字幕常驻于每次调用，消灭 map-reduce 的重复发送；
        跨章稳定前缀命中前缀缓存。流程：全局理解(1 次) → 分章深写(M 次) → 机械组装。
        字幕超长时退回 exhaustive 分段引擎兜底，MUST NOT 静默截断。
        """
        body = str(subtitle_text or "").strip()
        if not body:
            raise ValueError("比较详细笔记生成失败：字幕正文为空")
        if len(body) > THOROUGH_FULLCONTEXT_MAX_CHARS:
            self.logger.warning(
                f"比较详细字幕超长({len(body)} 字符 > {THOROUGH_FULLCONTEXT_MAX_CHARS})，"
                "退回 exhaustive 分段引擎"
            )
            return self._generate_exhaustive_with_understanding(
                body,
                pdf_structure=pdf_structure,
                extract_images=extract_images,
            )

        self.logger.info(f"比较详细启用全文常驻引擎：输入 {len(body)} 字符")
        system_message = (
            "你是资深课程笔记专家。先充分理解全文并规划结构，再据此撰写高质量深度笔记。"
        )
        # outline_prompt 在阶段 1 与阶段 2 复用同一字符串，保证跨章前缀逐字节稳定以命中缓存
        outline_prompt = self._build_thorough_outline_prompt(
            body, pdf_structure=pdf_structure
        )
        outline_messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": outline_prompt},
        ]
        outline = self._call_llm(
            outline_messages,
            max_tokens=THOROUGH_OUTLINE_MAX_TOKENS,
            timeout=300,
            operation_name="比较详细字幕理解(1/1)",
        ).strip()
        if not outline:
            raise RuntimeError("比较详细全局理解输出为空")
        try:
            outline_data = self._parse_thorough_outline(outline)
        except RuntimeError as parse_error:
            # JSON 修复接在理解链尾，不重发全文（全文已在链内前缀中）
            outline_messages.append({"role": "assistant", "content": outline})
            outline_messages.append(
                {
                    "role": "user",
                    "content": self._build_thorough_outline_repair_instruction(
                        str(parse_error)
                    ),
                }
            )
            outline = self._call_llm(
                outline_messages,
                max_tokens=THOROUGH_OUTLINE_MAX_TOKENS,
                timeout=300,
                operation_name="比较详细字幕理解(1/1)",
            ).strip()
            if not outline:
                raise RuntimeError("比较详细全局理解修复输出为空")
            outline_data = self._parse_thorough_outline(outline)

        chapters = outline_data["chapters"]
        chapter_total = len(chapters)
        # 复用通用进度上报（understand/draft phase 与现有 _note_stage_progress 对齐）
        self._report_exhaustive_progress("understand", 1, 1)

        chapter_notes: list[str] = []
        for idx, chapter in enumerate(chapters, start=1):
            instruction = self._build_thorough_chapter_instruction(
                chapter, idx=idx, total=chapter_total, extract_images=extract_images
            )
            chapter_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": outline_prompt},      # 命中阶段 1 前缀
                {"role": "assistant", "content": outline},         # 命中阶段 1 输出
                {"role": "user", "content": instruction},
            ]
            chapter_md = self._clean_markdown_output(
                self._call_llm(
                    chapter_messages,
                    max_tokens=THOROUGH_CHAPTER_MAX_TOKENS,
                    timeout=600,
                    operation_name=f"比较详细章节初稿({idx}/{chapter_total})",
                )
            )
            if not chapter_md:
                raise RuntimeError(
                    f"比较详细章节初稿 {idx}/{chapter_total} 输出为空"
                )
            chapter_notes.append(chapter_md)
            self._report_exhaustive_progress("draft", idx, chapter_total)

        final_markdown = self._assemble_thorough_note(outline_data, chapter_notes)
        self.logger.info(
            f"比较详细笔记完成：输入 {len(body)} 字符，章节 {chapter_total} 个，"
            f"终稿 {len(final_markdown)} 字符"
        )
        return final_markdown

    def _build_thorough_outline_prompt(
        self,
        body: str,
        *,
        pdf_structure: Optional[Dict[str, Any]],
    ) -> str:
        """阶段 1 全局理解 prompt：全文 → 大纲 JSON + 术语表。

        该字符串在阶段 1 与阶段 2（分章深写前缀）逐字节复用，故不得包含每次调用
        变化的字段；正文与讲义参考经确定性清洗，跨调用稳定。
        """
        pdf_context = self._exhaustive_reference_context(pdf_structure)
        return f"""
{detail_instruction("thorough")}

以下是一份课程字幕的完整正文（可能来自直播，含寒暄、点名、口头禅等噪声）。请充分理解全文，只输出一个严格 JSON 对象（不要 ``` 代码块围栏）：
{{
  "title": "准确、具体的课程标题",
  "course_overview": "中心问题、核心论点链与最终结论",
  "terminology": [{{"canonical": "规范专名", "variants": ["字幕中的音译或错拼"], "confidence": "high 或 uncertain", "note": "裁决依据"}}],
  "chapters": [{{"title": "逻辑章节标题", "purpose": "本章在全局论证中的作用", "key_points": ["必须深入展开的细分要点（含数据/案例/边界）"]}}]
}}

规划要求：
- 合并跨时段重复主题；区分概念与产品；ASR 无法确认的专名标 uncertain；不得捏造外部事实
- 设计 {THOROUGH_MIN_CHAPTERS}-{THOROUGH_MAX_CHAPTERS} 个逻辑章节（不要少于 {THOROUGH_MIN_CHAPTERS}），每章 key_points 列出 5-8 个必须展开的细分要点
- 章节顺序服从理解和教学逻辑，不服从字幕时间顺序；术语只做高置信拼写校对

{pdf_context}

【课程字幕全文】
{self._sanitize_content(body, max_length=None)}
""".strip()

    def _build_thorough_outline_repair_instruction(self, parse_error: str) -> str:
        """阶段 1 JSON 修复的链尾增量指令；全文已在链内前缀中。"""
        return f"""
【阶段：修复大纲 JSON】
你上一则回复包含有价值的规划内容，但 JSON 语法或完整性未通过严格解析。请依据全文返回一份完整、可解析的大纲 JSON。

解析错误：{self._sanitize_content(parse_error, max_length=None)}

要求：
- 沿用原 schema（title / course_overview / terminology / chapters），chapters 含 {THOROUGH_MIN_CHAPTERS}-{THOROUGH_MAX_CHAPTERS} 章，每章含 purpose 与 key_points
- 不得遗漏术语裁决；不得捏造字幕中不存在的事实
- 只返回严格 JSON，不要 Markdown 围栏或说明文字
""".strip()

    def _parse_thorough_outline(self, content: str) -> Dict[str, Any]:
        """解析并校验全局理解大纲 JSON，拒绝无法机械验证的自由文本。"""
        raw = str(content or "").strip()
        if raw.startswith("```"):
            lines = raw.splitlines()[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines.pop()
            raw = "\n".join(lines).strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < 0 or end <= start:
            raise RuntimeError("比较详细大纲未找到 JSON 对象")
        try:
            data = json.loads(raw[start : end + 1])
        except Exception as exc:  # noqa: BLE001 - 统一抛 RuntimeError 由上层修复
            raise RuntimeError(f"比较详细大纲 JSON 解析失败：{exc}") from exc
        for field in ("title", "course_overview", "chapters"):
            if not data.get(field):
                raise RuntimeError(f"比较详细大纲缺少字段：{field}")
        chapters = data["chapters"]
        if not isinstance(chapters, list) or len(chapters) < THOROUGH_MIN_CHAPTERS:
            raise RuntimeError(
                f"比较详细大纲章节数不足（需至少 {THOROUGH_MIN_CHAPTERS} 章）"
            )
        for chapter in chapters:
            if not chapter.get("title") or not chapter.get("key_points"):
                raise RuntimeError("比较详细大纲章节缺少 title 或 key_points")
        return data

    def _build_thorough_chapter_instruction(
        self,
        chapter: Dict[str, Any],
        *,
        idx: int,
        total: int,
        extract_images: bool,
    ) -> str:
        """阶段 2 分章深写的增量指令；全文与大纲已在链内前缀中。"""
        title = str(chapter.get("title") or "").strip()
        purpose = str(chapter.get("purpose") or "").strip()
        points = chapter.get("key_points") or []
        point_lines = "\n".join(f"- {p}" for p in points) or (
            "-（大纲未给出要点，请据本章主题自行展开）"
        )
        instruction = f"""
现在请只撰写第 {idx}/{total} 章：「{title}」。

本章在全局论证中的作用：{purpose}

必须深入展开的要点（每一项都要写成完整段落，含具体数据、案例、推导、反例与边界，不得概述）：
{point_lines}

硬性要求：
- 这是「比较详细」深度笔记，务必充分展开；保留字幕中所有具体数字、产品名、价格、案例与时间点
- 围绕论点组织，合并跨时段同主题为连贯论证，不按字幕时间流水账
- 必须使用全局 terminology 中 confidence=high 的 canonical 专名，不得保留已裁决的 ASR 音译，不得混淆概念与产品
- 只使用字幕和讲义可支持的内容；专名或数字无法确认时明确标记不确定
- 规范 Markdown：以 `## ` 开头（本章标题），其下用必要的 `### ` 子节、列表、表格、加粗
- 只输出本章内容，不要 H1、不要代码块围栏、不要解释
""".strip()
        if extract_images:
            instruction += (
                "\n\n"
                + SCREENSHOT_INSTRUCTION.strip()
                + "\n这是逐章写作：本章仅在确有高信息量画面时保留 0-1 个标记，避免全篇截图过密。\n"
            )
        return instruction

    def _assemble_thorough_note(
        self,
        outline: Dict[str, Any],
        chapter_notes: list[str],
    ) -> str:
        """按大纲机械组装终稿；此处不再调用模型或压缩章节。"""
        title = re.sub(r"^#+\s*", "", str(outline.get("title") or "")).strip()
        if not title:
            title = "课程笔记"
        overview = str(outline.get("course_overview") or "").strip()
        parts = [f"# {title}\n"]
        if overview:
            parts.append(f"> {overview}\n")
        parts.append("---\n")
        for note in chapter_notes:
            parts.append(note.strip() + "\n\n---\n")
        return "\n".join(parts).rstrip() + "\n"

    def _build_exhaustive_evidence_prompt(
        self,
        chunk: str,
        *,
        index: int,
        total: int,
        previous_context: str = "",
        next_context: str = "",
    ) -> str:
        namespace = f"E{index + 1:02d}-"
        # 前缀稳定化：固定提取要求在前（跨段逐字节相同），段序号、命名空间、
        # 边界上下文与正文压到末尾 (openspec「超详细 prompt 前缀缓存优化」)。
        return f"""
【阶段：语义证据提取】
你的任务不是写笔记，而是充分理解给定的一段课程字幕，为后续全局建模提供可追溯证据。
本段的定位信息与证据命名空间见文末。

证据提取要求：
- 使用文末给定的证据命名空间，每个独立知识单元从 `命名空间001` 起递增编号
  （例如命名空间为 E01- 时，编号为 E01-001、E01-002）
- 记录主题与中心结论
- 记录定义、解释和完整论证链
- 记录数据、步骤、案例、反例，以及它们证明或限制了什么
- 记录适用边界、注意事项、术语、易错点和有价值问答
- 记录与前后内容可能存在的跨段线索
- 记录时间戳或时间范围（原文存在时）
- ASR 不确定项：只做高置信纠正，无法确认的专名、数字或语句原样标记

不要写课程总标题，不要把寒暄和逐字重复创建为证据，不要使用外部知识。
边界上下文只用于理解衔接，不得重复提取为本段证据。

直接返回结构化 Markdown 证据包，不要解释工作过程。

【本段定位】
当前是完整课程字幕的第 {index + 1}/{total} 段。
证据命名空间：{namespace}

【上一段结尾上下文】
{self._sanitize_content(previous_context)}

【本段完整正文】
{self._sanitize_content(chunk)}

【下一段开头上下文】
{self._sanitize_content(next_context)}
""".strip()

    def _build_exhaustive_evidence_id_repair_instruction(
        self,
        *,
        index: int,
        total: int,
    ) -> str:
        """证据 ID 修复的链尾增量指令；原任务、字幕与首次输出均在链内前缀中。"""
        namespace = f"E{index + 1:02d}-"
        return f"""
【阶段：修复语义证据 ID】
你上一则回复（第 {index + 1}/{total} 段）有内容，但没有使用规定的稳定证据 ID。

修复要求：
- 每个独立知识单元按 `{namespace}001`、`{namespace}002` 递增编号
- 不得删除原输出中的事实、论证、案例、边界、时间戳或 ASR 不确定项
- 不得概括原输出，不得补充原字幕没有的新事实
- 只返回修复后的完整结构化 Markdown 证据包
""".strip()

    def _build_exhaustive_blueprint_prompt(self, evidence_text: str) -> str:
        return f"""
【阶段：全局知识蓝图】
以下是按完整课程字幕提取的全部语义证据包。请先形成全局理解，再设计最终笔记。

只返回一个可解析的严格 JSON 对象，不要 Markdown 围栏或解释，schema 如下：
{{
  "title": "准确、具体的课程标题",
  "course_overview": "课程中心问题、核心命题、主论证链与最终结论",
  "learning_outcomes": ["可验证的学习目标"],
  "terminology": [
    {{
      "canonical": "从全文上下文确认的规范专名",
      "variants": ["字幕中的音译、错拼或简称"],
      "confidence": "high 或 uncertain",
      "kind": "概念 / 产品 / 组织 / 人名 / 技术",
      "note": "裁决依据或仍不确定的原因"
    }}
  ],
  "chapters": [
    {{
      "chapter_id": "C01",
      "title": "逻辑章节标题",
      "purpose": "本章在全局论证中的作用",
      "evidence_ids": ["E01-001"],
      "source_chunks": [1],
      "required_points": ["必须深入表达的定义、机制、案例、边界或行动方法"]
    }}
  ]
}}

规划要求：
- 先建立全局术语表：综合所有分段里的重复发音、功能描述和上下文，只统一拼写，
  不得把候选词附带的外部事实写进笔记
- 以下仅是本类课程的拼写候选清单（只用于拼写校对，证据不支持就忽略）：
  {", ".join(EXHAUSTIVE_AI_TERM_HINTS)}
- 必须区分 Harness Engineering（概念）、OpenClaw（产品）和 Hermes Agent（产品）；
  不得把 Hermes Agent 猜成 Claude / Hailuo，不得把 Skill 的 ASR 音译猜成 Store / Studio
- 只有跨段上下文足以确认时 confidence 才能为 high；否则保留原音译并标 uncertain，
  禁止用熟悉但无证据的品牌名强行补全
- 根据内容复杂度设计约 6-12 个逻辑章节；章节顺序服从理解和教学逻辑，不服从分块边界
- 合并跨时段同一主题，但不能以合并为由删除后续新增的机制、案例、边界或反例
- 每个真实证据 ID 必须分配给最合适的章节，不能遗漏，不能编造不存在的 ID
- source_chunks 必须覆盖该章 evidence_ids 的来源段，确保写作时能回看完整原始字幕
- required_points 要具体列出论证链、重要案例 / 反例作用、适用边界、行动方法和 ASR 不确定项

这只是写作蓝图，不要撰写最终笔记，也不要按分块逐段摘要。

【全部语义证据】
{self._sanitize_content(evidence_text, max_length=None)}
""".strip()

    def _exhaustive_reference_context(
        self,
        pdf_structure: Optional[Dict[str, Any]],
    ) -> str:
        if not pdf_structure:
            return "未提供 PDF 讲义。"
        structure = self._sanitize_content(
            str(pdf_structure.get("structure_analysis") or ""),
            max_length=None,
        )
        full_text = self._sanitize_content(
            str(pdf_structure.get("full_text") or ""),
            max_length=None,
        )
        return f"【讲义结构参考】\n{structure}\n\n【讲义完整正文】\n{full_text}"

    def _validate_exhaustive_final(self, content: str) -> None:
        h1_count = len(re.findall(r"(?m)^#\s+\S", content))
        h2_count = len(re.findall(r"(?m)^##\s+\S", content))
        if h1_count != 1 or h2_count < 3:
            raise RuntimeError(
                "超详细终稿结构不完整：必须包含唯一 H1 和至少三个有效 H2 章节"
            )
        if re.search(r"(?i)SOURCE-CHUNK|证据命名空间|【阶段：", content):
            raise RuntimeError("超详细终稿结构不完整：包含内部分析模板")

    def _report_exhaustive_progress(
        self,
        phase: str,
        completed: int,
        total: int,
    ) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(phase, completed, total)
        except TypeError:
            # 兼容旧的双参数回调，避免外部调用方因内部阶段升级而中断。
            try:
                self.progress_callback(completed, total)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(f"超详细阶段进度回调失败：{exc}")
        except Exception as exc:  # noqa: BLE001 - 进度失败不得中断生成
            self.logger.warning(f"超详细阶段进度回调失败：{exc}")

    def _generate_with_pdf_reference(self, subtitle_text: str, pdf_structure: Dict, extract_images: bool = False) -> str:
        """用PDF参考生成笔记"""
        # 使用外部提示词模板，并对所有用户内容进行清理
        prompt = GENERATE_WITH_PDF_REFERENCE.format(
            structure_analysis=self._sanitize_content(pdf_structure['structure_analysis']),
            pdf_content=self._sanitize_content(pdf_structure['full_text'][:40000]),
            subtitle_text=self._sanitize_content(subtitle_text)
        )
        prompt += "\n\n" + detail_instruction(self.note_detail_level)
        if extract_images:
            prompt += SCREENSHOT_INSTRUCTION

        result = self._call_llm([
            {"role": "system", "content": "你是一个专业的课程笔记整理专家"},
            {"role": "user", "content": prompt}
        ], max_tokens=8000, timeout=300, operation_name="笔记生成(PDF参考)")

        return self._clean_markdown_output(result)

    def _generate_directly(self, subtitle_text: str, extract_images: bool = False) -> str:
        """直接生成笔记（无PDF参考）"""
        # 使用外部提示词模板，并对用户内容进行清理
        prompt = GENERATE_DIRECTLY.format(
            subtitle_text=self._sanitize_content(subtitle_text)
        )
        prompt += "\n\n" + detail_instruction(self.note_detail_level)
        if extract_images:
            prompt += SCREENSHOT_INSTRUCTION

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
