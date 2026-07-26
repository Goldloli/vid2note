"""
内容过滤模块
三层过滤：规则过滤 + LLM分类 + 精修
"""
import re
from typing import List
from dataclasses import dataclass


@dataclass
class FilterResult:
    """过滤结果"""
    original_text: str
    filtered_text: str
    category: str  # chat/knowledge/transition
    confidence: float
    should_keep: bool


class ContentFilter:
    """内容过滤器"""
    
    # 口语填充词
    FILLER_WORDS = [
        '嗯', '啊', '哦', '呃', '哎', '哟', '哈', '嘿',
        '那么', '那个', '这个', '就是', '对吧', '是吧', '好吗',
        '可以说', '怎么说呢', '大家知道', '我们可以看到',
        '啊这个', '那个这个', '嗯嗯', '啊啊'
    ]
    
    # 闲聊模式
    CHAT_PATTERNS = [
        r'大家好',
        r'我是.+老师',
        r'欢迎.*课程',
        r'今天.*讲',
        r'我们.*开始',
        r'谢谢.*观看',
        r'下节课.*见',
        r'有问题.*留言',
        r'记得.*点赞',
        r'关注.*频道',
    ]
    
    def __init__(self, llm=None, use_llm: bool = True):
        """
        初始化过滤器
        
        Args:
            llm: LLM 实例，用于分类
            use_llm: 是否使用LLM进行分类
        """
        self.llm = llm
        self.use_llm = use_llm
        self.chat_patterns = [re.compile(p) for p in self.CHAT_PATTERNS]
    
    def filter(self, text: str, context: str = "") -> FilterResult:
        """
        过滤内容
        
        Args:
            text: 原始文本
            context: 上下文信息
            
        Returns:
            过滤结果
        """
        # 第一层：规则过滤
        cleaned_text = self._rule_filter(text)
        
        # 第二层：LLM分类
        if self.use_llm and self.llm:
            category_result = self.llm.classify_content(cleaned_text)
            category = category_result.get('category', 'knowledge')
            confidence = category_result.get('confidence', 0.5)
        else:
            # 使用启发式规则分类
            category, confidence = self._heuristic_classify(cleaned_text)
        
        # 第三层：精修
        if category == 'knowledge':
            final_text = self._refine(cleaned_text)
            should_keep = True
        elif category == 'transition':
            final_text = cleaned_text
            should_keep = True
        else:  # chat
            final_text = ""
            should_keep = False
        
        return FilterResult(
            original_text=text,
            filtered_text=final_text,
            category=category,
            confidence=confidence,
            should_keep=should_keep
        )
    
    def filter_batch(self, texts: List[str], context: str = "") -> List[FilterResult]:
        """批量过滤"""
        return [self.filter(text, context) for text in texts]
    
    def _rule_filter(self, text: str) -> str:
        """规则过滤：去除填充词和无用内容"""
        # 去除填充词
        for word in self.FILLER_WORDS:
            text = text.replace(word, '')
        
        # 去除多余空格
        text = re.sub(r'\s+', ' ', text)
        
        # 去除重复标点
        text = re.sub(r'([。，！？])\1+', r'\1', text)
        
        return text.strip()
    
    def _heuristic_classify(self, text: str) -> tuple[str, float]:
        """启发式分类"""
        # 检查闲聊模式
        chat_score = 0
        for pattern in self.chat_patterns:
            if pattern.search(text):
                chat_score += 1
        
        # 如果匹配多个闲聊模式，判定为闲聊
        if chat_score >= 2:
            return 'chat', 0.7
        
        # 检查是否有过渡词
        transition_words = ['首先', '其次', '然后', '接下来', '最后', '总结一下']
        if any(w in text for w in transition_words):
            return 'transition', 0.6
        
        # 检查是否有技术内容特征
        tech_indicators = [
            r'[\w\-]+\([^)]*\)',  # 函数调用
            r'`[^`]+`',  # 代码
            r'[A-Z][a-z]+[A-Z]',  # 驼峰命名
            r'\b\d+\.\d+\b',  # 版本号
        ]
        
        tech_score = sum(1 for p in tech_indicators if re.search(p, text))
        
        if tech_score >= 2:
            return 'knowledge', 0.8
        
        # 默认判定为知识内容
        return 'knowledge', 0.5
    
    def _refine(self, text: str) -> str:
        """精修内容"""
        # 确保句子以标点结尾
        if text and text[-1] not in '。，！？；：':
            text += '。'
        
        # 规范化空格
        text = re.sub(r'\s*([，。！？；：])\s*', r'\1', text)
        
        return text.strip()
    
    def extract_key_sentences(self, text: str, max_sentences: int = 3) -> List[str]:
        """提取关键句子"""
        # 简单实现：按句子分割，返回前N个
        sentences = re.split(r'[。！？]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 过滤掉太短的句子
        sentences = [s for s in sentences if len(s) >= 10]
        
        return sentences[:max_sentences]
