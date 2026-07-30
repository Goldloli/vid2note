# 安全策略

## 支持范围

安全修复只保证进入最新发布版本和 `main` 分支。使用者应及时更新 Docker 镜像或重新构建。

## 报告漏洞

请不要公开提交包含利用细节、密钥或用户数据的 Issue。

优先使用 GitHub 仓库 Security 页面中的 **Report a vulnerability / Private vulnerability reporting** 私下报告。报告中请包含：

- 受影响版本或 commit
- 复现环境与最小步骤
- 实际影响
- 建议修复（如有）

维护者会尽快确认报告，并在修复可用后协调公开披露。

## 部署边界

vid2note 是无登录的本地单用户应用，默认只绑定 `127.0.0.1:8761`。如果主动改为局域网或公网监听，部署者必须自行增加认证、TLS、访问控制和反向代理限流。

运行时公开设置保存在 `data/config/settings.json`；LLM Key、Bilibili Cookie 和外部 ASR Key 使用 Fernet 认证加密后保存在 `data/config/credentials.enc`，文件权限为 `0600`。默认生成的 `data/config/master.key` 同样为 `0600`。密文和主密钥放在同一数据卷主要防止误提交与明文泄露，并不能抵御已取得数据卷完整读权限的攻击者；生产部署应通过 `VID2NOTE_MASTER_KEY_FILE` 使用 Docker Secret 或外部密钥挂载，并将密文与主密钥分开备份。

密钥查看接口只允许读取单个白名单字段，并返回 `Cache-Control: no-store`；前端默认只显示脱敏状态，用户主动点击眼睛后才短暂显示明文。应用本身没有登录能力，因此 localhost 网络边界仍然是必须条件。

项目会下载用户提供的 URL 并调用外部服务。不要在不可信的多用户环境中直接暴露本应用。
