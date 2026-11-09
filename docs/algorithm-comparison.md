# 进一步提速方案对照测试

日期：2026-11-09。测试来自同一台 Mac；本轮未测试小米实机。本文件不含真实服务器地址、订阅或凭据。

## 结果与保留决定

正式服务保留原来的 REALITY + TCP BBR + FQ-CoDel。FQ 没有显示出稳定收益，Hybla 明显较慢；Hysteria 2 的吞吐略高、短请求响应更快，但本轮只作隔离测试，没有加入正式订阅，测试服务已经移除。

同一 OVH 下载源的结果如下，单位均为 Mbps：

| 方案 | 单连接 | 四连接合计 | 处理 |
| --- | ---: | ---: | --- |
| REALITY，BBR + FQ-CoDel | 9.996 | 17.656；复测 18.153 | 保留原设置 |
| REALITY，BBR + FQ | 4.273 | 16.661 | 未证明收益，不保留 |
| REALITY，Hybla + FQ | 0.672 | 2.529 | 明显较慢，不保留 |
| Hysteria 2，QUIC BBR | 13.096 | 19.963 | 测试完成后移除 |
| Hysteria 2，Brutal，25Mbps 下载目标 | 14.236 | 20.822；复测 21.240 | 小幅提速，未正式部署 |

这些是短时有效下载吞吐，不是瞬时峰值、全天上限或长期稳定性结论。四连接使用单个 Mac 测试实例，不等于四台真实设备同时使用。Hysteria 的 QUIC BBR 与 Linux TCP BBR 也不能当作完全相同的实现。

## 方法与控制变量

- 沿用独立 Mihomo 测试进程，不改动用户现有 Clash 配置和系统代理。
- TCP 方案维持原协议和设备凭据，每次只改变拥塞控制或发包队列；Hysteria 则作为独立传输方案比较。
- 固定 15 秒接收窗口，比较单连接与四连接。部分文件在窗口结束时仍未完成，超时只表示窗口结束；吞吐使用实际收到的字节计算，不把超时当作完整下载成功。
- 使用 `--expect-cc` 和 `--expect-queue` 核实服务器实际算法及队列后才开始测试，防止把未生效的配置标成候选结果。
- 保留多队列布局，FQ 只替换各发送队列的调度方式。原始算法、队列结构保存到服务器本地，并安排限时自动回退。
- 生产环境可能有其他连接，未为测速而关闭其他设备。

示例命令（不包含真实配置）：

```sh
python3 scripts/probe_throughput.py --seconds 15 --connections 4 \
  --expect-cc bbr --expect-queue fq_codel \
  --url https://proof.ovh.net/files/10Mb.dat
```

## 基线波动及无效样本

开始时原 BBR + FQ-CoDel 对 Cloudflare 的测试为单连接 13.305、四连接 19.779；随后同样配置曾降至 1.373、7.792。这表明时段、路径或测量来源会影响结果，不能只挑最快的一次作为算法收益。

第一次 FQ 切换因自动分配的多队列缺少显式编号而失败，队列没有改变；该轮没有标为 FQ 样本。随后分配显式多队列编号，再验证各子队列实际为 FQ 才继续。

实际 FQ 对 Cloudflare 的样本为 1.826、5.051。后续该测速源返回 HTTP 429，因此 Hybla 的 Cloudflare 请求没有计为速度为零，而是作为无效限流样本排除。之后改用 OVH，对各方案作同源比较。诊断脚本也新增 `valid_http` 和 `rate_limited`，无效 HTTP 响应不再输出一个容易被误读的零吞吐。

切回 BBR + FQ 后，OVH 四连接回到 16.661；恢复原 FQ-CoDel 后为 17.656，最后复测 18.153。短期样本不足以证明 FQ 在所有网络上都更差，但没有证据支持在这台服务器保留它。

## Hysteria 隔离测试

使用官方 Hysteria `app/v2.13.0` Linux 二进制，并核对 GitHub 发布资产提供的 SHA-256。复用现有受信任 IP 证书，没有关闭证书验证。

测试服务拥有独立随机认证凭据，只临时允许当前 Mac 的 SSH 来源地址访问 UDP 测试入口。没有端口跳跃，没有更换正式 TCP 节点，没有修改已有设备订阅。

先测试无客户端带宽提示的 QUIC BBR，再以 25Mbps 下载目标测试 Brutal。Brutal 的设定值是请求目标，不是实测保证；不能通过把目标填写得超过链路能力来制造带宽。

测试进程设置最长运行时间，并另设自动清理任务，防止诊断中断后留下服务或防火墙规则。结束时已主动清理，不依赖定时任务等待到期。

以下诊断选项仅适用于已明确建立的临时测试服务；服务移除后不可直接重复执行：

```sh
python3 scripts/probe_throughput.py --transport hysteria2 --seconds 15 \
  --connections 4 --url https://proof.ovh.net/files/10Mb.dat
python3 scripts/probe_throughput.py --transport hysteria2 --hy2-down-mbps 25 \
  --seconds 15 --connections 4 --url https://proof.ovh.net/files/10Mb.dat
```

## 短请求响应检查

每种方案顺序请求同一个 HTTPS 204 页面五次，全部五次成功：

| 方案 | 首字节中位数 | 最大值 | 标准差 |
| --- | ---: | ---: | ---: |
| REALITY + TCP BBR | 1622.7ms | 1805.5ms | 394.7ms |
| Hysteria 2 BBR | 529.0ms | 690.2ms | 110.5ms |
| Hysteria 2 Brutal | 323.9ms | 577.5ms | 112.9ms |

这里是包含代理会话、DNS、TLS 和目标响应等因素的 HTTPS 首字节时间，不是 ICMP ping RTT，也不是负载下排队延迟。Hysteria 预检查建立的 QUIC 会话可复用，属于方案行为差异，不能用这张表声称物理线路延迟降低了同样倍数。五次空闲请求也不足以证明长期稳定。

可重复执行正式节点的检查：

```sh
python3 scripts/probe_throughput.py --latency-only --latency-samples 5 \
  --expect-cc bbr --expect-queue fq_codel
```

## 总发包与有效下载的差距

Brutal 期间服务器网卡的总发送样本为：最高一秒 34.420Mbps、最高五秒平均 32.803Mbps；同阶段应用层下载约 20.8Mbps。FQ 试验的最高五秒平均总发送仅约 10.925Mbps，说明并非所有低速样本都已经用满链路。

网卡数据包含协议开销、重传和所有连接，且与应用测速的窗口并非完全相同，不能直接相减来精确计算丢包率或某一设备的开销。不过可以看出：在较积极的 UDP 发送方案下，总发包已经进入套餐标称速率的量级，继续增加发送量不保证有效下载等比例增加。

## 结束状态

- 正式 TCP BBR 保留，系统默认队列和活动多队列均恢复为原 FQ-CoDel；没有更换内核。
- Hybla 没有写入持久化配置。测试加载的模块可用性不等于正式连接正在使用该算法。
- 临时 Hysteria 服务、二进制、服务器/客户端测试凭据文件、UDP 放行规则和自动清理任务均已移除。
- 没有新增正式节点，没有改变现有地址、订阅或设备凭据。
- Mac 临时测试配置自动删除，保留不含凭据的通用诊断脚本。
- 收尾时正式控制台及健康检查通过，原节点三次短请求全部成功。

短期建议是保留当前 TCP 方案；如后续正式部署 Hysteria，较有价值的收益可能是更快的短请求响应和备用传输路径，而不是保证 30Mbps 净下载。仍需小米 Wi-Fi/手机流量、多设备与长时间视频验证。

参考：[FQ 调度说明](https://man7.org/linux/man-pages/man8/tc-fq.8.html)、[Hysteria 拥塞控制](https://v2.hysteria.network/docs/advanced/Full-Server-Config/#congestion-control-details)、[Mihomo Hysteria 2 配置](https://wiki.metacubex.one/config/proxies/hysteria2/)。
