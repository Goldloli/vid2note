# storage-retention Specification

## Purpose
定义 SQLite 任务数据、外置设置、产物目录、保留策略、容量统计和清理行为。确保容器生命周期变化不会破坏历史记录或跨类型误删文件。
## Requirements
### Requirement: SQLite 任务持久化与外置设置

系统 MUST 使用单个 SQLite 数据库文件持久化任务记录、历史和产物引用，该数据库 MUST 位于持久化 Docker volume 内。用户非敏感设置 MUST 以 `${DATA_ROOT}/config/settings.json` 独立持久化，敏感凭证 MUST 以认证加密文件独立持久化；SQLite MUST NOT 继续作为新设置的权威态。数据库、设置文件和加密凭证在容器重建、镜像升级与重启后均 MUST 保留。

#### Scenario: 任务记录跨容器重启保留

- **WHEN** 创建并完成一个任务，再执行 `docker compose down` 与重新构建
- **THEN** 任务状态、产物引用和时间戳 MUST 仍可从 SQLite 查询且保持一致

#### Scenario: 外置配置跨容器重启保留

- **WHEN** 用户修改 SRT 保留策略和默认 LLM 并保存，再重建容器
- **THEN** `settings.json` MUST 保留新值，应用读取结果 MUST 与重建前一致

#### Scenario: 加密凭证跨容器重启保留

- **WHEN** 用户保存 LLM API Key 并重建容器，同时保留 `./data`
- **THEN** 应用 MUST 仍显示该 Key 已配置，并能使用同一主密钥解密调用

#### Scenario: 历史列表来自 SQLite

- **WHEN** 调用历史列表 API
- **THEN** 返回记录 MUST 来自 SQLite 而非设置 JSON 或进程内存

#### Scenario: 运行中任务重启后不悬空

- **WHEN** 一个任务处于运行中状态时容器被强制重启
- **THEN** 重启后该任务 MUST 被标记为可重跑或失败，MUST NOT 悬空

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

系统 MUST 为视频、音频、SRT、笔记、截图五种产物分别提供「永久 / 7 天 / 30 天」保留策略。各值 MUST 写入独立 `settings.json`，修改任一类 MUST NOT 影响其他类；下一次清理扫描 MUST 读取新权威态并立即生效。

#### Scenario: 五类产物各自独立配置

- **WHEN** 将「视频」设为「7 天」、「笔记」设为「永久」、「截图」设为「30 天」并保存
- **THEN** `settings.json` MUST 分别保存三个值，未修改的音频和 SRT MUST 保持原值

#### Scenario: 首次启动提供合法默认值

- **WHEN** 首次启动且外置设置不存在
- **THEN** 五类产物 MUST 各有一个非空的默认保留策略,且每个默认值 MUST 取自 `permanent / 7d / 30d` 中的合法值

#### Scenario: 非法取值被拒绝

- **WHEN** 请求保存不在合法枚举内的保留策略
- **THEN** 整个设置更新 MUST 被拒绝，现有 `settings.json` MUST 不变

#### Scenario: 配置变更立即对清理生效

- **WHEN** 用户修改某类保留策略并保存
- **THEN** 下一次清理扫描 MUST 按新文件值判断，MUST NOT 继续读取 SQLite 旧副本

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
