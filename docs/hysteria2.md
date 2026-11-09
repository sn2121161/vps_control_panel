# Hysteria 2 + Brutal 正式部署

2026-11-09，在前一轮隔离对照测试后，按用户要求正式启用 Hysteria 2。实现使用现有 3x-ui v3.11.0 和 Xray 26.10.21 原生支持，没有保留临时官方 Hysteria 测试服务。

## 部署结构

- Hysteria 2 使用 UDP 443；原 REALITY 使用 TCP 443，继续作为备用。
- 三个现有设备记录通过面板 API 关联到新入站，各自持有不同的 Hysteria auth。原 UUID、订阅令牌、设备启用状态和 Vision 流控保留。
- Xray 使用 hysteria 入站和同名传输、TLS 1.3、h3，以及 finalmask.quicParams 的 brutal 协商模式。服务器发送目标 25 Mbps、接收目标 10 Mbps；客户端对应下载 25 Mbps、上传 10 Mbps。多台设备仍共享套餐总带宽，这些数值不是每台独享带宽，也不是流量配额。
- 复用免费的公网 IP 证书，容器只读挂载整个证书目录，使 live/archive 符号链接有效。证书设 oneTimeLoading=false，沿用已有自动续期任务。客户端开启证书校验，不使用跳过验证。

## 订阅转换服务

该版本面板原生 Clash 导出器不输出 Hysteria 带宽提示；只有节点类型并不能确保启用 Brutal。因此增加 `scripts/clash_subscription.py`：仅监听本机 9101，从固定本机面板订阅端口读取 YAML，给 hysteria2 节点补充 up/down，保留设备认证、规则、分组和原 REALITY 节点。Nginx 仅将原 Clash 订阅路径转交该服务，原链接和原始订阅入口继续有效。

转换器依赖系统 `python3-yaml`，以 www-data 运行，不持久化订阅、不记录 URL 或响应内容。上游 Host 使用部署环境中的固定公网地址，避免本机上游生成 localhost 节点。通用单元模板在 `deploy/`，实际单元包含部署参数，只保存在服务器系统目录和本地备份白名单目录。

设备管理与统计继续由 3x-ui 处理。停用或重置凭据后，应更新对应设备订阅。设备名与独立凭据不是硬件绑定，不应转发配置。

## 客户端操作

Mac Clash Verge 和小米 Clash Meta 更新现有设备专属订阅，在规则模式的 PROXY 分组选择 `HY2-Brutal`。已有客户端可能保留旧节点选择，需要手动切换一次。备用 REALITY 节点仍在同一分组，可按需手动切回；DIRECT 也是原有手动选择，不声称已添加自动节点切换。

不要将原始 Base64 节点列表当成 Clash YAML，也不要手动删除带宽参数或关闭证书校验。

## 运行、备份与恢复

`panel-clash-subscription.service` 开机自动启动，失败自动重启；Docker 保持原自动恢复设置。健康采集新增转换器 TCP 监听和 Hysteria UDP 监听检查；监听正常仍不能证明公网 UDP 或视频平台可用。

现有月度备份白名单已覆盖数据库、新 Compose 挂载、Nginx 路由、runtime 和 local/deploy-hooks 内的实际转换器服务单元。预变更数据库和配置另存于服务器受限 local 目录，未上传。当天已有初始备份保持不覆写，不能当成部署后的快照；后续月度备份才包含新入站。

恢复时从 Git 取得脚本、安装 python3-yaml、恢复应用快照，重建/签发 IP 证书，核实证书只读挂载；将备份中的转换器单元安装到 systemd，daemon-reload 后 enable --now；检查 Nginx Clash 路由和 UDP 443 防火墙规则。先验证本机订阅，再验证公网连接。

回退可先在客户端选择 REALITY。若撤销正式部署，应在面板停用 Hysteria 入站、撤销对应 UDP 防火墙规则，恢复 Clash 路由直达原订阅后再停转换器，并从 runtime 移除 Hysteria 监控标志；保留原设备和管理入口。

## 实测结果与边界

Mac 使用独立临时 Mihomo 实例读取正式订阅，不覆盖正在使用的客户端配置。测速源 OVH，四连接窗口 15 秒，HTTP 200 的实际接收字节计速；定时中止的部分下载不算完整文件下载成功。

| 检查 | 结果 |
| --- | --- |
| 正式 HY2 + Brutal，四个并行下载 | 合计 21.523 Mbps |
| 容器和转换器重启后，HY2 单连接完整 10 MiB 下载 | 约 15.5 Mbps |
| HY2 YouTube HTTPS 204 | 两轮各 3/3 成功，中位首字节约 332 / 514 ms |
| 备用 REALITY YouTube HTTPS 204 | 2/2 成功 |
| 故意错误的 HY2 凭据 | 不能代理请求 |
| 三份订阅、各设备独立认证 | 输出正确；凭据互不相同 |
| 全部监听、状态页采集、自动启动 | 正常，无当前告警 |
| 合成回归测试 | 4 项通过，覆盖备份安全性及订阅转换后保留设备凭据、备用节点和分流规则 |

四个下载使用同一个设备的 QUIC 会话，不等于四台设备并发验收。首字节时间不等于 ICMP RTT。仍需小米在真实家庭宽带及手机流量下验证、两台各三小时 1080p、五台高峰与 Netflix 实际账号播放。短测不能证明长期稳定、永不封锁或总能跑满 30 Mbps。

实现依据：[Xray Hysteria 入站](https://xtls.github.io/config/inbounds/hysteria.html)、[Hysteria 传输](https://xtls.github.io/config/transports/hysteria.html)、[所用版本 QUIC 参数解析](https://github.com/XTLS/Xray-core/blob/v26.10.21/infra/conf/transport_finalmask.go)、[服务端 Brutal 协商](https://github.com/XTLS/Xray-core/blob/v26.10.21/transport/internet/hysteria/hub.go)、[3x-ui Clash 导出器](https://github.com/MHSanaei/3x-ui/blob/v3.11.0/internal/sub/clash_service.go)、[Mihomo Hysteria 2 参数](https://wiki.metacubex.one/config/proxies/hysteria2/)。
