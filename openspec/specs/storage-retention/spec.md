# storage-retention Specification

## Purpose
TBD - created by archiving change build-vid2note-v1. Update Purpose after archive.
## Requirements
### Requirement: SQLite 持久化存储

系统 MUST 使用单个 SQLite 数据库文件持久化全部任务记录、历史与配置数据,且该数据库文件 MUST 存放于持久化 Docker volume 内,使其在容器重建、镜像升级与重启后仍然存在。任务记录、历史条目与用户配置(含各产物类型的保留策略)MUST 在该数据库中持久化,而非仅存于内存。

#### Scenario: 任务记录跨容器重启保留

- **WHEN** 创建一个任务并使其进入已完成状态,然后执行 `docker compose down` 与 `docker compose up` 重建容器
- **THEN** 重建后该任务记录 MUST 仍可通过 API 查询到,且其状态、产物引用与时间戳 MUST 与重启前一致

#### Scenario: 配置跨容器重启保留

- **WHEN** 在设置页将「SRT 保留策略」改为「7 天」并保存,然后重建容器
- **THEN** 重启后从数据库读取的「SRT 保留策略」MUST 仍为「7 天」,且后续新建任务 MUST 按该值生效

#### Scenario: 历史列表来自 SQLite

- **WHEN** 调用历史列表 API
- **THEN** 返回的记录 MUST 来自 SQLite 数据库而非进程内存,且每条 MUST 包含标题、创建时间、状态与产物引用

#### Scenario: 运行中任务重启后不悬空

- **WHEN** 一个任务处于运行中状态时容器被强制重启
- **THEN** 重启后该任务在数据库中的状态 MUST 被标记为可重跑或失败,MUST NOT 出现「界面仍显示运行中但后端实际无对应进程」的悬空状态

### Requirement: 文件产物目录结构

所有文件产物(视频、音频、SRT、笔记、截图)MUST 存放于持久化 Docker volume 内,并按产物类型组织清晰的目录结构,使每一类产物可被独立定位、统计与清理。流水线运行中产生的临时/中间文件 MUST 写入与最终产物目录分离的临时目录,MUST NOT 污染最终产物目录。

#### Scenario: 产物按类型分目录存放

- **WHEN** 一条流水线完整跑完并产出视频、音频、SRT、笔记、截图五类文件
- **THEN** 每类产物 MUST 分别落在 volume 内各自独立的类型子目录下(例如 `videos/`、`audio/`、`srt/`、`notes/`、`screenshots/`),任一类别的文件 MUST NOT 出现在另一类别的目录中

#### Scenario: 产物可通过任务 ID 关联

- **WHEN** 给定一个任务 ID 并查找其全部产物
- **THEN** 该任务的每一类产物 MUST 能借由任务 ID 在对应类型目录下定位到,且 SQLite 中该任务记录 MUST 引用这些产物的相对路径

#### Scenario: volume 持久化跨容器保留

- **WHEN** 创建任务使其产出文件后,执行 `docker compose down` 与 `docker compose up`
- **THEN** volume 内所有产物文件与 SQLite 数据库 MUST 完整保留,文件数量与路径 MUST 与重启前一致

#### Scenario: 临时中间文件隔离

- **WHEN** 流水线运行过程中产生下载分片、音频切片、ASR 中间结果等临时文件
- **THEN** 这些临时文件 MUST 写入独立的临时目录(例如 `temp/`),MUST NOT 写入最终的五类产物目录

### Requirement: 分类型独立保留策略

系统 MUST 为五种产物类型(视频、音频、SRT、笔记、截图)各自提供独立可配的保留策略,每一类的取值 MUST 限定为「永久(permanent)」「7 天(7d)」「30 天(30d)」三者之一。修改任意一类的策略 MUST NOT 影响其他四类的策略。

#### Scenario: 五类产物各自独立配置

- **WHEN** 将「视频」设为「7 天」、「笔记」设为「永久」、「截图」设为「30 天」并保存
- **THEN** 三类 MUST 分别保存为各自被设置的值;读取配置时三类返回值 MUST 互不相同且与设置一致;未修改的「音频」「SRT」MUST 保持原值不变

#### Scenario: 首次启动提供合法默认值

- **WHEN** 首次启动应用且数据库无任何配置
- **THEN** 五类产物 MUST 各有一个非空的默认保留策略,且每个默认值 MUST 取自 `permanent / 7d / 30d` 中的合法值

#### Scenario: 非法取值被拒绝

- **WHEN** 尝试将某类保留策略设为 `permanent / 7d / 30d` 以外的值(例如 `3 天`、`0` 或空字符串)
- **THEN** 配置接口 MUST 拒绝该请求并返回校验错误,数据库中该类的原值 MUST NOT 被改动

#### Scenario: 配置变更立即持久化并对清理生效

- **WHEN** 修改某类保留策略并保存
- **THEN** 该变更 MUST 立即写入 SQLite,且下一次清理扫描 MUST 按新策略判定该类产物的去留

### Requirement: 自动清理过期产物

系统 MUST 自动、周期性地按各产物类型当前的保留策略清理过期产物,MUST NOT 依赖用户手动点击「清理」。策略为「永久」的产物 MUST 永不被自动清理。清理 MUST 同步更新 SQLite 中的产物记录,且 MUST NOT 删除属于未达终态(排队中 / 运行中)任务的产物。

#### Scenario: 过期产物被自动删除

- **WHEN** 某视频产物的策略为「7 天」,且该产物已存在 7 天以上(测试可借助可注入的系统时钟模拟经过时长),清理扫描运行
- **THEN** 该视频文件 MUST 被删除,其所在类型目录中 MUST NOT 再包含该文件

#### Scenario: 永久保留的产物不被删除

- **WHEN** 某笔记产物的策略为「永久」,且经过超过 30 天的时长(测试可借助可注入的系统时钟模拟),清理扫描运行
- **THEN** 该笔记文件 MUST NOT 被删除

#### Scenario: 清理后同步更新数据库记录

- **WHEN** 清理删除了一批过期产物文件
- **THEN** SQLite 中对应任务的产物引用 MUST 被更新(标记为已清理或移除路径),使历史列表 MUST NOT 再指向已不存在的文件

#### Scenario: 不清理未达终态任务的产物

- **WHEN** 一个任务尚处于排队中或运行中状态,且其已产生的临时/中间产物按时间年龄已超过保留期
- **THEN** 清理扫描 MUST 跳过该任务的产物,直到该任务达到终态(完成或失败)

#### Scenario: 清理无需用户干预

- **WHEN** 应用持续运行且无人手动操作
- **THEN** 系统 MUST 自动周期性触发清理扫描(定时任务或启动时 + 定期相结合),界面上 MUST NOT 存在为使清理生效而必须用户点击的按钮

### Requirement: 存储用量统计与展示

系统 MUST 统计 Docker volume 内各产物类型与各任务的存储占用,并 MUST 在 Web 界面中向用户展示存储用量,使本地自用场景下磁盘占用可见、可控。

#### Scenario: 总用量可查询

- **WHEN** 调用存储统计接口
- **THEN** 返回结果 MUST 包含 volume 内产物目录的总占用字节数,且 MUST 提供人类可读的单位换算

#### Scenario: 按类型与任务粒度统计

- **WHEN** 调用存储统计接口
- **THEN** 返回结果 MUST 提供按五种产物类型(视频/音频/SRT/笔记/截图)分别统计的占用,且 MUST 至少能定位到占用最高的若干任务

#### Scenario: 界面展示存储用量

- **WHEN** 用户在浏览器中打开设置页或存储页
- **THEN** 页面 MUST 展示当前存储用量(总量与各类型占用),且展示的数据 MUST 来自后端统计接口,MUST NOT 为前端硬编码

#### Scenario: 统计反映清理结果

- **WHEN** 清理删除了一批过期产物后再次查询存储统计
- **THEN** 总用量与对应类型的占用 MUST 较清理前下降,且下降的幅度 MUST 与被删除文件的实际大小一致

