# LLM 提示词文档

本文档详细列出项目中使用的所有 LLM 提示词，包括其用途、参数和优化建议。

## 提示词目录

| 文件名 | 用途 | 调用位置 |
|--------|------|----------|
| `classify.txt` | 内容分类（闲聊/知识/过渡） | `BaseLLM.classify_content()` |
| `restructure.txt` | 内容重组为结构化 Markdown | `BaseLLM.restructure_content()` |
| `generate_directly.txt` | 直接生成 Markdown 笔记 | `MarkdownGenerator._generate_fast_mode()` |
| `generate_with_pdf_reference.txt` | 结合 PDF 参考生成笔记 | `Pipeline.run()`（带PDF时） |
| `pdf_structure_analysis.txt` | PDF 章节结构分析 | `PDFParser.parse()` |

---

## 1. 内容分类提示词 (classify.txt)

### 用途

将课程字幕内容分类为三类：
- **chat (闲聊)**：问候语、过渡口语、与课程无关的闲聊
- **knowledge (知识)**：概念解释、技术细节、代码示例、原理描述
- **transition (过渡)**：章节转换、话题切换、承上启下

### 提示词内容

```
你是一个内容分类专家。请将输入的文本分类为以下三类之一：

## 分类标准

1. **chat (闲聊)**
   - 问候语（"大家好"、"早上好"）
   - 过渡性口语（"那么"、"接下来"、"我们来看一下"）
   - 与课程内容无关的闲聊
   - 互动性语言（"大家明白了吗"、"对吧"）

2. **knowledge (知识)**
   - 概念解释和定义
   - 技术细节和实现
   - 代码示例和讲解
   - 原理性描述
   - 案例分析

3. **transition (过渡)**
   - 章节转换
   - 话题切换
   - 承上启下的内容
   - 小结和预告

## 输出格式

请以JSON格式返回结果：
{
    "category": "chat/knowledge/transition",
    "confidence": 0.0-1.0,
    "reason": "分类理由（简要说明）"
}

## 示例

输入："大家好，我是张老师，今天我们来学习Python编程。"
输出：
{
    "category": "chat",
    "confidence": 0.9,
    "reason": "主要是问候和自我介绍，属于开场白"
}

输入："Python中的列表推导式是一种简洁的创建列表的方式，语法是 [x for x in iterable]。"
输出：
{
    "category": "knowledge",
    "confidence": 0.95,
    "reason": "包含技术概念解释和代码示例"
}
```

### 调用代码

```python
# backend/src/llm/base.py

def classify_content(self, text: str, temperature: float = 0.3) -> Dict[str, Any]:
    """分类内容类型（闲聊/知识/过渡）"""
    messages = [
        {
            "role": "system",
            "content": self._load_prompt('classify')  # 加载 classify.txt
        },
        {
            "role": "user",
            "content": f"请分类以下文本：\n\n{text}"
        }
    ]
    # ... 调用LLM并解析JSON结果
```

### 优化建议

1. **增加更多示例**：添加更多边界情况的示例，提高分类准确性
2. **细化分类标准**：对于技术课程，可以进一步细分知识类型（概念/代码/案例）
3. **置信度阈值**：建议设置置信度阈值（如 0.6），低于阈值时人工复核
4. **批量分类**：对于短文本，可以批量分类以减少 API 调用次数

---

## 2. 内容重组提示词 (restructure.txt)

### 用途

将课程字幕转换为结构清晰、内容详细的 Markdown 文档。去除口语化，保留核心知识点和数据。

### 提示词内容

```markdown
# 角色定位
你是一位专业的技术文档编辑，将课程字幕转换为结构化Markdown笔记。

## 核心任务
整理课程字幕为结构清晰、内容详细的Markdown文档。去除口语化，保留核心知识点和数据。

## 整理原则

### 1. 结构层次
- **一级标题(#)**：文档主标题
- **二级标题(##)**：主要章节
- **三级标题(###)**：章节细分
- **四级标题(####)**：具体要点（可选）

### 2. 内容要求
- **去除**：问候语、口头禅、重复表述、闲聊
- **保留**：核心概念、关键数据、方法论、案例分析
- **格式**：
  - **加粗**标记关键概念和数据
  - 表格呈现多维度对比（如时间线、数据对比）
  - 列表整理要点
  - `> 引用块`突出关键洞察

### 3. 详细度控制
- 每个主题包含：定义、数据/案例、结论
- 不要过度展开，保留核心信息即可
- 表格和列表优先于大段文字

## 输出示例

### 输入（字幕）
大家好，今天讲AI产品推广。阿福这个产品推广预算大概是5到10亿。覆盖渠道非常全，公交车、地铁、高铁、机场、电梯都有。代言人请的是何炅，大众化，有信任感。

### 输出（整理后）
## 推广策略分析

### 资源投入

**推广预算**：5-10亿人民币

**渠道覆盖**：
| 渠道类型 | 具体场景 | 策略意图 |
|---------|---------|---------|
| 公共交通 | 公交、地铁 | 日常通勤触达 |
| 枢纽场景 | 高铁、机场 | 中高端人群覆盖 |
| 社区场景 | 电梯广告 | 家庭决策者触达 |

**代言人策略**：
- **人选**：何炅
- **选择逻辑**：大众化认知度高、亲和力强、公众形象稳定
- **匹配度**：与产品大众化定位高度契合

> **关键洞察**：阿福的推广是生态位高地争夺战，通过饱和式投放建立用户心智。

## 最终要求
1. 结构清晰（目录+层级标题）
2. 内容详细（数据、案例、方法）
3. 格式规范（表格、加粗、列表）
4. 去除所有口语化和闲聊

## 重要警告
- **严禁使用 ``` 或 ```markdown 包裹输出内容**
- **直接输出纯Markdown格式**
- **不要添加任何代码块标记**
```

### 调用代码

```python
# backend/src/llm/base.py

def restructure_content(self, subtitle: str, context: str = "", temperature: float = 0.3) -> str:
    """重组内容为标准Markdown格式"""
    system_prompt = self._load_prompt('restructure')

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"章节：{context}\n\n字幕：\n{content}\n\n转换为详细且结构清晰的Markdown笔记："}
    ]

    return self.chat(messages, temperature=0.3, max_tokens=3000, timeout=60)
```

### 优化建议

1. **示例多样化**：添加不同类型课程的示例（技术/商业/人文）
2. **输出长度控制**：根据内容长度动态调整 max_tokens
3. **格式一致性**：可以增加更多格式要求，如代码块语言标记
4. **多语言支持**：对于英文课程，调整示例和格式要求

---

## 3. 直接生成提示词 (generate_directly.txt)

### 用途

当没有 PDF 课件参考时，直接将字幕内容整理为结构化的 Markdown 笔记。

### 提示词内容

```
请将以下课程内容整理为结构化的Markdown笔记。

【课程内容】
<course_content>
{subtitle_text}
</course_content>

【要求】
1. 分析内容结构，添加合适的标题层级
2. 去除口语化表达（嗯、啊、这个、那个等）
3. 保留核心知识点，适当总结提炼
4. 使用Markdown格式：标题、列表、表格、加粗等
5. 重要概念和关键词突出显示
6. **重要：直接返回纯Markdown内容，不要包裹在代码块(```markdown)中**
```

### 调用代码

```python
# backend/src/core/generator.py

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

response = llm.chat(messages, temperature=0.3, max_tokens=8000, timeout=180)
```

### 优化建议

1. **动态模板**：根据内容长度和类型动态调整提示词
2. **章节检测**：添加自动章节检测指令，更好地组织内容
3. **关键词提取**：要求 LLM 同时提取关键词，用于后续检索

---

## 4. 带PDF参考生成提示词 (generate_with_pdf_reference.txt)

### 用途

当上传了 PDF 课件时，结合课件结构和内容生成更准确的笔记。

### 提示词内容

```
请根据以下课件结构和内容，将课程字幕整理为结构化的Markdown笔记。

【课件结构分析】
<structure_analysis>
{structure_analysis}
</structure_analysis>

【课件参考内容】
<courseware_reference>
{pdf_content}
</courseware_reference>

【课程字幕】
<subtitle_content>
{subtitle_text}
</subtitle_content>

【要求】
1. 按照课件的章节结构组织笔记
2. 结合课件知识点，将字幕整理为完整的笔记
3. 去除口语化表达，保留核心知识
4. 使用Markdown格式：标题、列表、表格、加粗等
5. 重要概念和定义突出显示
6. **重要：直接返回纯Markdown内容，不要包裹在代码块(```markdown)中**
```

### 调用代码

```python
# backend/src/tasks/pipeline.py

# 在 Pipeline.run() 中，当 pdf_path 存在时使用此提示词
pdf_result = self.pdf_parser.parse(pdf_path, extract_images=self.config.processing.extract_images)
chapters = [
    {'title': c.title, 'level': c.level, 'page_num': c.page_num}
    for c in pdf_result['chapters']
]

# 生成时使用 PDF 结构作为参考
output = self.generator.generate_with_llm(
    segment_dicts,
    self.llm,
    title=title,
    metadata={'model': self.config.llm_provider}
)
```

### 优化建议

1. **权重调整**：可以调整课件内容和字幕内容的权重
2. **图片引用**：如果提取了图片，在提示词中添加图片引用说明
3. **页码对应**：添加页码信息，方便对照原课件

---

## 5. PDF结构分析提示词 (pdf_structure_analysis.txt)

### 用途

分析 PDF 课件的结构，提取章节标题、层级和核心知识点。

### 提示词内容

```
分析以下课件的结构，提取：
1. 课程标题
2. 章节结构（层级）
3. 核心知识点列表
4. 关键术语定义

课件内容：
<courseware_content>
{content}
</courseware_content>

请用简洁的方式返回分析结果。
```

### 调用代码

```python
# backend/src/parsers/pdf_parser.py

def _analyze_structure_with_llm(self, text_content: str) -> List[Dict]:
    """使用LLM分析文档结构"""
    prompt = self._load_prompt('pdf_structure_analysis')
    prompt = prompt.format(content=text_content[:8000])  # 限制长度

    messages = [
        {"role": "system", "content": "你是一个文档结构分析专家。"},
        {"role": "user", "content": prompt}
    ]

    response = self.llm.chat(messages, temperature=0.3)
    # 解析返回的结构化数据
    # ...
```

### 优化建议

1. **输出格式**：要求返回 JSON 格式，便于程序解析
2. **层级限制**：限制最大层级深度（如最多 4 级）
3. **内容长度**：根据 PDF 大小动态调整输入长度

---

## 提示词优化建议汇总

### 通用优化原则

1. **明确角色定位**
   - 在提示词开头明确指定 AI 角色
   - 描述角色的专业背景和任务目标

2. **结构化输出要求**
   - 使用标记语言（XML标签）包裹输入内容
   - 明确要求输出格式（Markdown/JSON）

3. **示例驱动**
   - 提供输入输出示例
   - 覆盖常见场景和边界情况

4. **约束条件**
   - 明确禁止的行为（如不使用代码块包裹）
   - 格式要求（标题层级、列表类型等）

5. **质量控制**
   - 要求保留核心知识点
   - 要求去除口语化内容

### 性能优化

1. **Token 控制**
   - 合理设置 max_tokens
   - 对于长内容使用分块处理

2. **Temperature 调整**
   - 内容整理：0.3（稳定输出）
   - 创意生成：0.7-0.9（更多变化）

3. **批量处理**
   - 将多个短文本合并为一次调用
   - 使用分隔符区分不同段落

### 针对不同 LLM 的优化

| LLM | 特点 | 优化建议 |
|-----|------|----------|
| Qwen | 中文能力强 | 可以使用更复杂的中文指令 |
| GLM | 性价比高 | 适合大批量处理 |
| DeepSeek | 代码能力强 | 技术类课程表现更好 |
| Kimi | 长文本优秀 | 可以输入更长的上下文 |
| 文心一言 | 百度生态 | 适合中文知识类内容 |

### 版本管理建议

1. **提示词版本化**
   ```
   prompts/
   ├── v1/
   │   ├── classify.txt
   │   └── restructure.txt
   └── v2/
       ├── classify.txt
       └── restructure.txt
   ```

2. **A/B 测试**
   - 同时运行多个版本的提示词
   - 对比输出质量，选择最优版本

3. **效果评估**
   - 建立评估指标（准确率、完整性、格式规范）
   - 定期评估提示词效果

---

## 提示词调试技巧

### 1. 逐步调试

```python
# 打印最终发送给 LLM 的完整提示词
print("=== System Prompt ===")
print(system_prompt)
print("\n=== User Prompt ===")
print(user_prompt)
```

### 2. 保存输入输出

```python
# 保存每次调用的输入和输出，便于分析
import json
from datetime import datetime

def log_llm_call(prompt_name: str, messages: list, response: str):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "prompt_name": prompt_name,
        "messages": messages,
        "response": response
    }
    with open("llm_calls.jsonl", "a") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
```

### 3. 对比测试

```python
# 同时测试多个提示词版本
prompts = {
    "v1": load_prompt("restructure_v1"),
    "v2": load_prompt("restructure_v2")
}

test_content = "测试字幕内容..."

for version, prompt in prompts.items():
    result = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": test_content}])
    print(f"=== {version} ===")
    print(result)
    print()
```

---

## 相关文件

- 提示词目录：`/backend/src/prompts/`
- 基类实现：`/backend/src/llm/base.py`
- 生成器：`/backend/src/core/generator.py`
- 解析器：`/backend/src/parsers/pdf_parser.py`
