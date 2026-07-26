# mindmap-export Specification

## Purpose
TBD - created by archiving change build-vid2note-v1. Update Purpose after archive.
## Requirements
### Requirement: 思维导图大纲以已生成笔记为唯一输入来源

该 capability 的输入 MUST 为 note-generation 步骤产出的最终 Markdown 笔记(而非 ASR 字幕、原始音频或视频源)。系统 SHALL 解析该笔记的标题层级(`#` / `##` / `###` …),据此构建思维导图大纲。当笔记产物不存在或内容为空时,MUST NOT 产出思维导图,SHALL 返回明确错误。

#### Scenario: 从已生成笔记产出大纲

- **WHEN** note-generation 步骤已产出一份含多级标题的 Markdown 笔记,流水线请求生成思维导图
- **THEN** 该 capability MUST 接受该笔记作为输入,据此构建并产出思维导图大纲,不得要求调用方另行提供字幕或音频

#### Scenario: 不直接消费 ASR 字幕或原始媒体

- **WHEN** 上游仅提供了 SRT 字幕或音频/视频产物,而笔记尚未生成完成
- **THEN** 该 capability MUST NOT 直接基于字幕或原始媒体产出大纲,SHALL 以「笔记尚未就绪」为由等待或报错,不得绕过笔记产物自行推导

#### Scenario: 笔记缺失或为空时报错

- **WHEN** 触发思维导图导出时,笔记产物文件不存在或内容为空
- **THEN** 该 capability MUST 返回明确的「笔记缺失、无法生成思维导图」错误,且 MUST NOT 产出空的大纲文件冒充成功

### Requirement: 大纲为单根树状结构且层级映射笔记标题

思维导图大纲 MUST 为单根的树状结构:根节点 SHALL 取自笔记的主标题(`#` H1)或任务/视频标题;笔记的二级标题(`##` H2)映射为根下的一级子节点,三级标题(`###` H3)映射为更深层级,依此类推。每个节点 MUST 携带来自笔记对应标题的文本。大纲层级与笔记标题层级 MUST 严格对应,不得错位或丢失层级。

#### Scenario: 根节点取自笔记主标题

- **WHEN** 一份笔记含一个 `#` 主标题(或任务/视频标题)被用于生成大纲
- **THEN** 大纲的根节点文本 SHALL 为该主标题(或任务/视频标题)的文本,且整份大纲仅有这一个根节点

#### Scenario: 标题层级映射为树深度

- **WHEN** 一份笔记含 `#` > `##` > `###` 的嵌套标题结构
- **THEN** 大纲中 `##` 必须为根节点的一级子节点、`###` 必须为对应 `##` 的子节点,节点深度与笔记标题层级一一对应

#### Scenario: 多个同级标题在父节点下并列

- **WHEN** 笔记在同一父标题下出现多个同级标题(如同一 `##` 下有多个 `###`)
- **THEN** 这些同级标题 MUST 在同一父节点之下作为并列的兄弟子节点出现,顺序与笔记中出现的先后一致

### Requirement: 三种导出格式可选

该 capability MUST 支持三种思维导图导出格式:XMind(`.xmind`)、PNG 位图(`.png`)、Markdown 大纲(`.md`)。用户 SHALL 能在导出时选择一种或多种格式,系统 MUST 对所选的每一种格式各自产出一份独立的导出文件。v1 MUST NOT 支持上述三种以外的导出格式。

#### Scenario: 选择单一格式导出

- **WHEN** 用户在导出时仅选择 PNG 一种格式
- **THEN** 系统 MUST 产出一份 `.png` 文件,且 MUST NOT 强制附带产出 xmind 或 md 文件

#### Scenario: 同时选择多种格式各自独立产出

- **WHEN** 用户在导出时同时勾选 xmind、png、md 三种格式
- **THEN** 系统 MUST 对三种格式各产出一份独立的导出文件,三份文件各自完整、互不覆盖

#### Scenario: 请求不支持的格式被拒绝

- **WHEN** 用户请求一种 v1 不支持的导出格式(如 `svg` / `pdf` / `mm`)
- **THEN** 系统 MUST 拒绝该请求并返回明确提示「v1 仅支持 xmind / png / md 三种格式」,不得产出该不支持格式的文件

### Requirement: XMind 格式导出

XMind 导出(复用基底 ai_srt2md 的 XMind 导出能力)MUST 产出符合 XMind 文件规范的 `.xmind` 文件(本质为含 `content.json` 等资源的 zip 包),其内部主题树 SHALL 与大纲结构一一对应,根节点作为中心主题(central topic)、其子节点作为分支主题。该文件 MUST 能被 XMind 官方客户端正常打开并显示完整层级。

#### Scenario: xmind 文件结构合法

- **WHEN** 系统执行 XMind 格式导出
- **THEN** 产出的 `.xmind` 文件 MUST 为合法 zip 包,解包后 SHALL 含 `content.json`,其主题树节点与大纲层级一一对应、无节点丢失

#### Scenario: 大纲根节点作为中心主题

- **WHEN** 一份单根大纲被导出为 xmind
- **THEN** xmind 中大纲根节点 MUST 作为中心主题(central topic),根下的子节点 MUST 作为一级分支主题,深层节点作为各级子主题

#### Scenario: 可被 XMind 官方客户端打开

- **WHEN** 用 XMind 官方客户端打开导出的 `.xmind` 文件
- **THEN** 客户端 MUST 能正常加载该文件并显示中心主题及全部子节点,层级与导出大纲一致,不报损坏或格式错误

### Requirement: PNG 位图导出

PNG 导出(复用基底 ai_srt2md 的 PNG 渲染能力)MUST 将大纲渲染为可读的位图 `.png` 图片:节点 SHALL 以文字标签可见、父子节点间以连线表达从属关系、整体布局可辨识为思维导图。图片 MUST 为合法 PNG,可被任意图片查看器打开;对节点较多的大纲,渲染 MUST 完整呈现全部节点,不得截断或省略分支。

#### Scenario: PNG 合法且结构可读

- **WHEN** 系统执行 PNG 格式导出
- **THEN** 产出的 `.png` MUST 为合法 PNG 图片,任意图片查看器可打开,画面中节点文字可辨、父子节点间存在连线,整体可辨识为思维导图

#### Scenario: 大型大纲完整渲染不截断

- **WHEN** 被导出的大纲节点数量较多(如超过 50 个节点)
- **THEN** 导出的 PNG MUST 完整呈现全部节点,不得因画布尺寸或内存限制截断、省略或裁剪任何分支

#### Scenario: PNG 渲染失败时报错

- **WHEN** PNG 渲染过程发生异常(如渲染库崩溃、内存不足或字体缺失导致渲染失败)
- **THEN** 系统 MUST 返回明确的「PNG 渲染失败」错误并归因到思维导图导出步骤,MUST NOT 产出损坏或空白的 png 文件冒充成功

### Requirement: Markdown 大纲导出

Markdown 大纲导出 MUST 产出一份以缩进列表表达层级的纯文本 `.md` 大纲文件:根为顶层列表条目,子节点逐级缩进,层级深度与大纲一致。该文件 MUST 为合法 Markdown,可被任意 Markdown 编辑器或 Obsidian 等工具直接阅读,且 SHALL 与笔记原文件相互独立 —— 导出 MUST NOT 覆盖或修改 note-generation 产出的原始笔记文件。

#### Scenario: md 大纲为缩进列表

- **WHEN** 系统执行 Markdown 大纲格式导出
- **THEN** 产出的 `.md` 文件内容 MUST 为合法的无序列表,层级通过列表缩进表达,根节点为顶层条目、子节点逐级缩进,深度与大纲层级一致

#### Scenario: 节点文本与大纲一致

- **WHEN** 大纲中某节点的文本为 X(无论根、分支或叶节点)
- **THEN** 该文本 MUST 出现在导出的 md 大纲中对应层级位置的列表条目里,不得丢失或改写

#### Scenario: 导出大纲不覆盖原始笔记

- **WHEN** 同一任务下同时存在 note-generation 产出的笔记文件与导出的 md 大纲文件
- **THEN** 二者 MUST 为相互独立的文件,导出 md 大纲 MUST NOT 覆盖、改名或修改原始笔记文件的内容

### Requirement: 导出失败的明确错误处理

思维导图导出过程中发生的任何失败(笔记缺失、大纲解析失败、XMind 打包异常、PNG 渲染崩溃等)MUST 被归因到思维导图导出步骤并产出明确、可定位的中文错误信息,SHALL 通过任务状态暴露给用户,不得静默失败(silent fail)或以空文件冒充成功。多种格式同时导出时,某一种格式失败 MUST NOT 影响其他已成功格式的产物。

#### Scenario: 笔记无法解析出标题层级时的处理

- **WHEN** 笔记产物存在但完全不包含可识别的标题层级(如纯无标题正文段落),无法构建多层大纲
- **THEN** 系统 SHALL 产出仅含根节点(取自任务/视频标题或笔记首行)的极简大纲并正常导出,或返回明确的「笔记无可识别结构、无法生成思维导图」错误;无论哪种路径 MUST NOT 静默崩溃或产出内容错乱的大纲

#### Scenario: 单种格式失败不拖累其他格式

- **WHEN** 用户同时请求导出 xmind + png + md,其中 PNG 渲染失败但 xmind 与 md 均成功
- **THEN** 系统 MUST 保留已成功的 xmind 与 md 产物,并对失败的 png 单独返回明确错误,不得因 png 失败而删除或丢弃已成功的 xmind / md 文件

#### Scenario: XMind 打包异常时报错

- **WHEN** XMind 导出过程中 zip 打包或 `content.json` 序列化发生异常
- **THEN** 系统 MUST 返回明确的「XMind 导出失败」错误(含可定位原因)并归因到思维导图导出步骤,MUST NOT 产出结构损坏、无法被官方客户端打开的 `.xmind` 文件冒充成功

### Requirement: v1 仅导出文件不提供交互式导图画布(Non-goal)

v1 的思维导图能力 MUST 限定为文件导出(xmind / png / md)。系统 MUST NOT 提供交互式思维导图画布 —— 即在页面上对节点进行拖拽、缩放、新增、删除、改写或连线编辑等交互式编辑能力。用户与思维导图的交互 SHALL 限于:查看导出入口、选择导出格式、下载导出文件。文件导出 MUST 可重复触发,不因「无画布」而受限。

#### Scenario: 不提供画布交互编辑能力

- **WHEN** 用户在思维导图相关页面进行操作
- **THEN** 页面 MUST NOT 提供节点拖拽、缩放、增删改、连线编辑等交互式画布,MUST 仅提供导出格式选择与文件下载入口

#### Scenario: 文件导出可重复触发

- **WHEN** 用户对同一任务多次点击导出同一格式(或不同格式组合)
- **THEN** 系统 SHALL 每次请求都重新产出对应的导出文件供下载,不得因未提供画布而限制导出次数或要求额外的交互状态

