## MODIFIED Requirements

### Requirement: 设置页处理选项

设置中心 MUST 在对应页签提供界面语言、背景、输出语言、五档笔记详细程度（简洁 / 适中 / 详细 / 比较详细 / 超详细）、图片提取与质量、PDF 模式、并发任务数（1~3）、分块大小、Temperature、最大重试次数和五类保留策略。截图嵌入 SHALL 继续作为新建任务的逐任务选项，但设置页可提供新任务默认值。PDF 只展示当前稳定的 `pypdf`，MUST NOT 展示未实现的 MinerU 选择。

#### Scenario: 笔记详细程度五档可选

- **WHEN** 用户在笔记生成页签选择「简洁 / 适中 / 详细 / 比较详细 / 超详细」之一并保存
- **THEN** `note.detail_level` MUST 保存为对应合法值，页面 MUST 解释该档位对覆盖率与 token/耗时的影响（其中「比较详细」MUST 说明其为全文常驻深度引擎、质量近「超详细」而成本显著更低），后续新建任务 MUST 使用该默认档位

#### Scenario: 截图嵌入逐任务选择

- **WHEN** 用户在主控台创建任务
- **THEN** 截图开关 MUST 以设置默认值预填且仍可为本次任务覆盖，本次选择 SHALL 只影响本任务

#### Scenario: 并发任务数限定 1~3 且越界被拒

- **WHEN** 用户尝试将并发任务数设为 0 或 4(或范围外的任意值)并保存
- **THEN** 前端 MUST 校验失败并阻止保存；合法值 MUST 保存成功

#### Scenario: 高级数值显示范围与说明

- **WHEN** 用户打开高级设置
- **THEN** chunk size、Temperature 和最大重试次数 MUST 以带最小值/最大值/用途说明的数字字段展示，非法值 MUST 在提交前提示

#### Scenario: 保存反馈不使用阻塞弹窗

- **WHEN** 用户保存任一页签
- **THEN** 页面 MUST 以页内状态或 toast 展示保存中、成功或错误，MUST NOT 使用浏览器原生 `alert`

## ADDED Requirements

### Requirement: 主控台与设置页一致提供五档详细程度

主控台新建任务区的详细程度选择 MUST 与设置页保持一致的五档选项（简洁 / 适中 / 详细 / 比较详细 / 超详细），MUST NOT 出现一处有「比较详细」而另一处缺失的不一致。任务详情页展示任务详细程度时 MUST 通过动态文案键解析「比较详细」的本地化名称，MUST NOT 回退显示原始键字符串。

#### Scenario: 主控台创建任务可选比较详细

- **WHEN** 用户在主控台新建任务区展开详细程度下拉
- **THEN** 下拉 MUST 含「比较详细」选项且选中后随任务提交，其值 MUST 为 `thorough`

#### Scenario: 任务详情页正确显示比较详细档位名

- **WHEN** 一个 `note_detail_level` 为 `thorough` 的任务在详情页展示元信息
- **THEN** 页面 MUST 显示「比较详细」本地化名称，MUST NOT 显示 `thorough` 或 `settings.detail.thorough` 等原始键
