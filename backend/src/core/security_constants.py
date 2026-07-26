"""
安全常量定义
包含Prompt注入防护的危险模式、敏感关键词等安全相关常量
"""

# Prompt注入危险模式
# 用于检测和防护用户输入中可能包含的Prompt注入攻击
PROMPT_INJECTION_PATTERNS = [
    # 角色扮演/系统指令覆盖
    r'(?i)ignore\s+(?:all\s+)?previous\s+instructions',
    r'(?i)ignore\s+(?:the\s+)?above\s+instructions',
    r'(?i)disregard\s+(?:all\s+)?(?:previous\s+)?instructions',
    r'(?i)you\s+are\s+now\s+(?:a\s+)?',
    r'(?i)system\s*:\s*you\s+are',
    r'(?i)system\s*:\s*ignore',
    r'(?i)new\s+role\s*:\s*',
    r'(?i)act\s+as\s+(?:if\s+)?you\s+(?:are\s+)?',
    r'(?i)pretend\s+(?:to\s+be\s+)?',
    r'(?i)roleplay\s+(?:as\s+)?',
    
    # 指令分隔符和标记
    r'(?i)\[\s*system\s*\]',
    r'(?i)\[\s*instructions\s*\]',
    r'(?i)\[\s*end\s+system\s*\]',
    r'(?i)\[\s*end\s+instructions\s*\]',
    r'(?i)\{\{\s*system\s*\}\}',
    r'(?i)\{\{\s*instructions\s*\}\}',
    r'(?i)\<\s*system\s*\>',
    r'(?i)\<\s*instructions\s*\>',
    r'(?i)\<\s*/\s*system\s*\>',
    r'(?i)\<\s*/\s*instructions\s*\>',
    
    # 提示词结束标记
    r'(?i)(?:user|human)\s*:\s*$',
    r'(?i)(?:assistant|ai|bot)\s*:\s*$',
    
    # 敏感操作指令
    r'(?i)delete\s+(?:all\s+)?(?:files?|data)',
    r'(?i)remove\s+(?:all\s+)?(?:files?|data)',
    r'(?i)exec\s*\(',
    r'(?i)execute\s*\(',
    r'(?i)eval\s*\(',
    r'(?i)system\s*\(',
    r'(?i)subprocess',
    r'(?i)os\.system',
    r'(?i)__import__',
    
    # 数据提取指令
    r'(?i)print\s+(?:all\s+)?(?:previous\s+)?(?:prompts?|instructions?|system)',
    r'(?i)show\s+(?:all\s+)?(?:previous\s+)?(?:prompts?|instructions?|system)',
    r'(?i)reveal\s+(?:all\s+)?(?:previous\s+)?(?:prompts?|instructions?|system)',
    r'(?i)repeat\s+(?:all\s+)?(?:previous\s+)?(?:words?|text|prompts?)',
    r'(?i)output\s+(?:all\s+)?(?:previous\s+)?(?:prompts?|instructions?|system)',
    
    # 混淆技术
    r'(?i)b64decode',
    r'(?i)base64',
    r'(?i)decode\s+as',
    r'(?i)convert\s+from\s+(?:base64|hex)',
]

# 需要转义的特殊字符
# 这些字符可能被用于注入HTML/XML标签或Markdown格式
DANGEROUS_CHARACTERS = {
    '<': '<',   # HTML/XML标签开始
    '>': '>',   # HTML/XML标签结束
    '\x00': '',     # 空字节（字符串终止符）
    '\x1b': '',     # ESC字符（ANSI转义序列）
}

# Markdown特殊语法，可能被用于混淆或注入
MARKDOWN_INJECTION_PATTERNS = [
    r'```\s*system',  # 代码块伪装系统指令
    r'```\s*instructions',
    r'\[system\]\(',
    r'\[instructions\]\(',
]

# 最大内容长度限制
MAX_CONTENT_LENGTH = 50000  # 字符数
MAX_PDF_CONTENT_LENGTH = 30000  # PDF分析时的内容长度
MAX_SUBTITLE_CONTENT_LENGTH = 40000  # 字幕处理时的内容长度

# 敏感信息模式（用于检测可能的敏感数据泄露）
SENSITIVE_DATA_PATTERNS = [
    r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # 信用卡号
    r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
    r'(?i)password\s*[=:]\s*\S+',
    r'(?i)api[_-]?key\s*[=:]\s*\S+',
    r'(?i)secret\s*[=:]\s*\S+',
    r'(?i)token\s*[=:]\s*\S+',
    r'sk-[a-zA-Z0-9]{20,}',  # OpenAI API Key
    r'ghp_[a-zA-Z0-9]{36}',  # GitHub Personal Access Token
    r'AKIA[0-9A-Z]{16}',  # AWS Access Key ID
]

# 替换提示（当检测到注入尝试时）
INJECTION_WARNING_MESSAGE = "[检测到潜在的Prompt注入内容，已清理]"
SENSITIVE_DATA_WARNING = "[可能包含敏感信息，已清理]"
CONTENT_TRUNCATED_MESSAGE = "\n\n[内容已截断，超过最大长度限制]"
