## ADDED Requirements

### Requirement: 六步流水线 DAG 编排与产物契约

系统 MUST 将每个任务编排为一个有向无环图(DAG),按固定顺序执行六个节点:下载 → 提取音频 → ASR 转录 → LLM 整理笔记 → 思维导图 → 清理。除清理节点外,每个节点 MUST 依赖其上一节点的产物作为输入,且每个节点 MUST 产出一类明确的产物(视频 / 音频 / 字幕 SRT / 笔记 Markdown / 思维导图)并登记到该任务记录。节点顺序 MUST NOT 被打乱;系统 SHALL 允许依据媒体来源类型跳过「下载」与/或「提取音频」节点(详见 media-ingest),被跳过节点之后的节点 MUST 仍能从已落盘的上游产物取得输入。清理节点 MUST 作为终止节点执行,无论上游成败。

#### Scenario: 完整六步按序执行并产出全部产物

- **WHEN** 系统对一个「在线视频」来源(如 YouTube 链接)的任务从 pending 开始执行
- **THEN** 该任务 MUST 依次执行「下载 → 提取音频 → ASR 转录 → LLM 整理笔记 → 思维导图 → 清理」六个节点,且前五个节点分别产出视频、音频、字幕(SRT)、笔记(Markdown)、思维导图产物并登记到任务记录

#### Scenario: 本地音频来源跳过下载与提取节点

- **WHEN** 任务来源为「本地音频」(用户上传音频文件)
- **THEN** 系统 MUST 将「下载」与「提取音频」两个节点标记为 skipped 且不执行,直接从「ASR 转录」节点开始,并以用户上传的音频文件作为 ASR 节点的输入产物

#### Scenario: 每个节点产物登记到任务记录

- **WHEN** 任一非清理节点执行完成
- **THEN** 系统 MUST 将其产物类型、绝对路径与字节大小登记到该任务记录,供下游节点消费与历史视图展示

#### Scenario: 清理节点在成功与失败两条路径下都执行

- **WHEN** 任务的全部上游节点成功完成,或任一上游节点失败
- **THEN** 系统 MUST 在两种情况下都执行清理节点(完成产物归档与临时工作文件清理),MUST NOT 在上游失败时跳过清理而残留临时文件

#### Scenario: 节点缺少必需上游产物时报错终止

- **WHEN** 某个非清理节点准备执行,但其必需的上游产物在任务记录中不存在或文件已丢失(例如 ASR 节点找不到音频产物)
- **THEN** 该节点 MUST 立即失败并产出明确错误「缺少上游产物:<节点名>」,MUST NOT 用空输入继续执行并产出空或损坏的下游产物

### Requirement: 任务状态机与各步进度

系统 MUST 为每个任务维护一个总体状态,取值为 pending / running / completed / failed / cancelled 之一,且仅允许既定的状态迁移。当任务处于 running 时,系统 MUST 同时为六个节点各自维护独立的节点状态(pending / running / completed / failed / skipped)与该节点独立的进度(0–100),以便前端逐节点展示进度。总体状态与各节点状态 MUST 被持久化,使后端重启后仍可恢复完整任务视图。

#### Scenario: 新建任务初始为 pending

- **WHEN** 用户提交一个新任务并被系统接受
- **THEN** 该任务的总体状态 MUST 为 pending,六个节点状态均为 pending,各节点进度均为 0

#### Scenario: worker 取起任务后进入 running 并推进首个可执行节点

- **WHEN** 一个 pending 任务获得并发槽位被 worker 取起
- **THEN** 任务总体状态 MUST 迁移为 running,首个非 skipped 节点的节点状态 MUST 迁移为 running

#### Scenario: 全部节点完成后任务转为 completed

- **WHEN** 任务的所有非 skipped 节点(含清理节点)均已迁移为 completed
- **THEN** 任务总体状态 MUST 迁移为 completed,记录完成时间,且总体进度 MUST 为 100

#### Scenario: 任一节点失败将任务转为 failed 并记录失败节点

- **WHEN** 六个节点中的任一非 skipped 节点执行失败
- **THEN** 任务总体状态 MUST 迁移为 failed,失败节点的节点状态 MUST 为 failed,任务记录 MUST 包含失败节点名与中文错误信息

#### Scenario: 被跳过节点标记为 skipped 不计入失败

- **WHEN** 因来源类型导致某些节点被跳过(如本地音频来源跳过下载与提取)
- **THEN** 这些节点的状态 MUST 为 skipped,且系统 MUST NOT 因 skipped 节点的存在而把任务判为 failed

#### Scenario: 仅允许既定的状态迁移

- **WHEN** 系统或外部请求尝试非法迁移(例如把 completed 任务迁回 running,或把 failed 任务不经重跑直接迁为 completed)
- **THEN** 系统 MUST 拒绝该迁移,任务状态保持不变,并 MUST 记录一次非法迁移尝试

#### Scenario: 后端重启后残留 running 的任务被标记为 failed

- **WHEN** 后端进程重启后,数据库中存在重启前处于 running 的任务
- **THEN** 系统 MUST 将这些任务标记为 failed,并在错误信息中注明「重启中断于 <节点名> 节点」,MUST NOT 让其永久卡在 running 状态

### Requirement: SSE 实时进度与日志推送

系统 MUST 提供基于 SSE(Server-Sent Events)的订阅端点,前端订阅后 MUST 实时收到该任务的进度事件与逐行日志。事件 MUST 至少覆盖:节点进入(node-entered)、节点进度更新(node-progress,含百分比)、实时日志行(log)、节点完成(node-completed)、节点失败(node-failed)、任务终态(task-completed / task-failed / task-cancelled)。每条事件 MUST 携带任务 ID、节点名(日志事件除外)与时间戳。

#### Scenario: 订阅后收到节点进度事件

- **WHEN** 前端对一个 running 任务打开 SSE 订阅
- **THEN** 系统 MUST 在每个节点进入、推进与完成时分别推送 node-entered / node-progress / node-completed 事件,且每条事件 MUST 携带任务 ID、节点名与时间戳

#### Scenario: 实时日志逐行推送而非一次性转储

- **WHEN** 某节点在执行过程中持续产出日志行(例如 yt-dlp 的下载进度行、ASR 的处理日志)
- **THEN** 系统 MUST 通过 log 事件近乎实时地逐行推送这些日志,MUST NOT 等节点结束后才一次性批量返回

#### Scenario: 任务进入终态后 SSE 连接被正常关闭

- **WHEN** 任务迁移到 completed / failed / cancelled 任一终态
- **THEN** 系统 MUST 先推送对应的 task-completed / task-failed / task-cancelled 事件,随后 MUST 主动关闭该 SSE 连接

#### Scenario: 断线重连时先推送当前快照再续推实时事件

- **WHEN** 前端在 SSE 连接中断后重新发起对该任务的订阅
- **THEN** 系统 MUST 先推送一个包含该任务当前总体状态与各节点最新状态的快照事件,使前端能重建完整进度视图,随后继续推送后续实时事件

#### Scenario: 订阅不存在或已终态任务不报错

- **WHEN** 前端对一个不存在的任务 ID,或一个已处于终态的任务发起 SSE 订阅
- **THEN** 系统 MUST NOT 抛出未捕获错误,而是立即推送该任务当前状态(或「任务不存在」)并正常关闭连接

### Requirement: 并发控制与排队

系统 MUST 限制同时处于 running 的任务数(最大并发)。最大并发 MUST 可在 1~3 范围内配置,默认值 MUST 为 1。当已提交任务数超过当前最大并发时,超出任务 MUST 以 pending 状态排队,并按提交时间先后(FIFO)依次获得执行槽位。系统 MUST 对每个排队任务暴露其在队列中的等待位次。

#### Scenario: 默认最大并发为 1

- **WHEN** 用户从未修改并发配置即提交多个任务
- **THEN** 系统 MUST 同时只允许 1 个任务处于 running,其余任务以 pending 状态排队

#### Scenario: 最大并发可配置为 2 或 3

- **WHEN** 用户在设置中将最大并发配置为 2(或 3)且提交了相应数量的任务
- **THEN** 系统 MUST 允许至多 2(或 3)个任务同时处于 running

#### Scenario: 超出并发上限的任务进入排队并可见位次

- **WHEN** 当前处于 running 的任务数已达最大并发,且有新任务被提交
- **THEN** 新任务 MUST 以 pending 状态进入队列,系统 MUST 在其任务记录或队列视图中给出它在队列中的等待位次

#### Scenario: 槽位释放后队首任务按 FIFO 被取起

- **WHEN** 一个 running 任务进入终态释放出并发槽位
- **THEN** 系统 MUST 按提交时间先后,从 pending 队列中取起最早提交的任务投入执行

#### Scenario: 最大并发仅接受 1~3 的越界拦截

- **WHEN** 用户尝试将最大并发设置为 0、负数、4 或更大的越界值
- **THEN** 系统 MUST 拒绝该设置,保留上一次的有效值(或回落到默认 1),并返回明确提示

#### Scenario: 队列深度有上限以防资源耗尽

- **WHEN** pending 与 running 任务总数已达到队列容量上限,且有新任务被提交
- **THEN** 系统 MUST 拒绝创建该新任务并返回明确提示「队列已满,请稍后再试」,MUST NOT 无限制堆积任务导致内存耗尽

### Requirement: 节点级失败重跑

系统 MUST 支持对失败任务从指定节点重新执行,而非从头重跑。重跑时,所有在指定节点之前已 completed 的节点产物 MUST 被复用且不得重新执行;指定节点及其全部下游节点 MUST 在干净的工作上下文中重新执行,MUST NOT 复用上次失败节点的半成品。系统 MUST 在复用上游产物前校验其仍然存在且完整,若缺失则 MUST 回退到从缺失节点起重跑。

#### Scenario: 从失败节点重跑复用上游产物

- **WHEN** 一个此前在「ASR 转录」节点失败的任务,用户发起从「ASR 转录」节点的重跑
- **THEN** 系统 MUST 复用「下载」与「提取音频」节点已 completed 的产物且不重新执行这两个节点,仅重新执行「ASR 转录」及其下游全部节点

#### Scenario: 重跑不复用失败节点的半成品

- **WHEN** 上次失败节点(或其下游任一节点)在失败时留下了不完整的中间产物
- **THEN** 重跑 MUST 在干净的工作上下文中重新生成这些节点的产物,MUST NOT 拼接或复用上次失败遗留的半成品文件

#### Scenario: 上游产物缺失时回退到缺失节点起重跑

- **WHEN** 用户发起从「LLM 整理笔记」节点的重跑,但该任务此前 completed 的「ASR 转录」字幕产物已被清理或丢失
- **THEN** 系统 MUST 检测到上游产物缺失,自动回退到从缺失的「ASR 转录」节点(及其依赖链)开始重跑,并 MUST 向用户说明回退原因

#### Scenario: 用户可手动选择从更早节点重跑

- **WHEN** 用户对一个已 completed 的任务,选择从「LLM 整理笔记」节点重新执行(例如想更换 prompt 重新生成笔记)
- **THEN** 系统 MUST 复用该节点之前已 completed 节点的产物,重新执行「LLM 整理笔记」「思维导图」「清理」及其之后所有下游节点

#### Scenario: 重跑成功后清除失败记录

- **WHEN** 一个此前 failed 的任务,经从失败节点重跑后全部节点成功完成
- **THEN** 任务总体状态 MUST 迁移为 completed,任务记录中的失败节点与错误信息 MUST 被清除或归档为历史错误,不再表现为失败任务

### Requirement: 任务取消

系统 MUST 允许用户取消处于 pending 或 running 的任务。取消 pending 任务 MUST 将其移出队列且永不执行;取消 running 任务 MUST 向当前执行节点发送取消信号,使其尽快停止,丢弃被中断节点的半成品,同时保留已 completed 节点的产物以备重跑。已处于终态(completed / failed / cancelled)的任务 MUST NOT 再次发生状态迁移。

#### Scenario: 取消 pending 任务使其永不执行

- **WHEN** 用户对一个处于 pending(排队中)的任务发起取消
- **THEN** 该任务 MUST 立即迁移为 cancelled 并移出队列,MUST NOT 在后续被调度执行

#### Scenario: 取消 running 任务使当前节点尽快停止

- **WHEN** 用户对一个处于 running 的任务发起取消
- **THEN** 系统 MUST 向当前正在执行的节点发送取消信号,使该节点在尽可能短的时间内停止,任务总体状态 MUST 迁移为 cancelled

#### Scenario: 取消 running 任务时保留已完成节点产物

- **WHEN** 一个 running 任务在被取消时已有部分节点 completed(例如下载、提取音频已完成,ASR 进行中被取消)
- **THEN** 系统 MUST 保留这些已 completed 节点的产物,丢弃被中断节点的半成品,以供用户后续从被中断节点重跑

#### Scenario: 对终态任务发起取消为无效操作

- **WHEN** 用户对一个已处于 completed / failed / cancelled 的任务发起取消
- **THEN** 系统 MUST NOT 改变该任务的状态,MUST NOT 重新执行任何节点,并 MUST 返回提示表明该任务已处于终态

#### Scenario: 已取消任务不自动恢复且可显式重跑

- **WHEN** 一个任务被取消后,系统继续运行并陆续释放并发槽位
- **THEN** 该 cancelled 任务 MUST NOT 被自动重新投入执行;仅当用户显式发起从某节点的重跑时,系统才重新执行相应节点

### Requirement: 历史任务筛选、分页与批量操作

系统 MUST 提供历史任务列表,支持按状态、媒体来源(在线视频平台 / 本地视频 / 本地音频)与关键词(匹配标题、源链接或来源标识)进行筛选,并 MUST 支持分页(页码 + 每页条数,响应中返回总条数)。系统 MUST 支持对历史任务的批量导出(将选中任务的最终 Markdown 笔记打包为单一归档下载)与批量重跑(为每个选中任务提交一个复用其输入与配置的全新任务并入队)。

#### Scenario: 按状态筛选历史任务

- **WHEN** 用户在历史页选择状态筛选条件为「failed」
- **THEN** 系统 MUST 仅返回状态为 failed 的任务列表,completed / pending / running / cancelled 的任务 MUST NOT 出现在结果中

#### Scenario: 按媒体来源筛选历史任务

- **WHEN** 用户选择媒体来源筛选为「Bilibili」(或「本地音频」)
- **THEN** 系统 MUST 仅返回来源匹配该筛选的任务,其他来源的任务 MUST NOT 出现

#### Scenario: 按关键词筛选历史任务

- **WHEN** 用户输入关键词(如某视频标题片段或源链接的一部分)
- **THEN** 系统 MUST 返回标题、源链接或来源标识中包含该关键词的任务,大小写不敏感

#### Scenario: 分页返回指定页与总条数

- **WHEN** 用户在当前筛选条件下请求第 2 页、每页 20 条
- **THEN** 系统 MUST 返回第 21~40 条结果,并在响应中给出符合条件的任务总条数,供前端渲染分页器

#### Scenario: 批量导出选中任务的笔记为单一归档

- **WHEN** 用户在历史页勾选多个已 completed 的任务并点击「批量导出」
- **THEN** 系统 MUST 将这些任务的最终 Markdown 笔记打包为一个单一归档(如 zip)供下载,归档内 MUST 能区分每篇笔记对应的任务

#### Scenario: 批量重跑选中任务创建新任务并入队

- **WHEN** 用户勾选多个历史任务并点击「批量重跑」
- **THEN** 系统 MUST 为每个被选中的历史任务创建一个复用其输入(源链接或文件)与配置的全新任务并入队,原历史任务记录 MUST NOT 被修改或删除

#### Scenario: 状态、来源与关键词筛选可组合

- **WHEN** 用户同时设置状态为「completed」、来源为「YouTube」、关键词为「机器学习」
- **THEN** 系统 MUST 返回同时满足这三个条件的任务列表(三者取交集),MUST NOT 仅按其中任一条件过滤
