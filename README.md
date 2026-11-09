# VPS 服务管理与运维

使用上游 3x-ui 管理 Xray，附加一个仅管理员访问的状态页、本地月度备份和证书续期检查。目标环境为 Ubuntu 24.04、Python 3.12、Docker Compose。

本仓库只保存可以公开的代码和说明，不保存真实部署配置、代理凭据、订阅链接、数据库、证书私钥或备份。上游面板源码和镜像不在本仓库复制。

- `scripts/backup.py`：SQLite 一致性备份及配置归档，只写本地，不执行 Git 操作。
- `scripts/health.py`：采集脱敏任务状态、证书到期、端口和磁盘情况。
- `scripts/status_server.py`：回环地址的只读状态页，必须由 HTTPS 反向代理认证后访问。
- `scripts/renew.py`：运行 Certbot 续期并记录结果。
- [操作与恢复说明](docs/operations.md)
- [部署验证记录](docs/verification.md)

实际 Compose、反向代理、运行参数、定时器和凭据由维护者在服务器本地管理，不在公开仓库发布。需要新机重建时，先恢复自己保管的本地备份，再按照版本清单部署。

网页提醒仅在页面打开且可访问时有效。所有备份均为未加密压缩包，含敏感数据，请通过 SSH/SFTP 下载并妥善保管。
