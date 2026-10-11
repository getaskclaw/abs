# ABS — AskClaw VPS 跑分脚本

[English](README.en.md)

租或续一台 Linux VPS 前跑一下，看 CPU 快不快、内存够不够、磁盘能不能真写。跑完给一个分数和一句结论：**保留 / 谨慎保留 / 不建议保留 / 测试不完整**。

<p align="center"><img src="assets/abs-ip172-8vcpu-keep.jpg" width="720" alt="ABS 实跑示例：主机信息 → 各分项指标 → 最终得分和结论"></p>

上图是一次真实跑分：先列机器配置，再逐项打印 CPU/内存/磁盘/fsync 数据，最后给出总分和「保留」结论。

## 跑一下

```bash
curl -fsSL https://askclaw.top/abs.sh | bash
```

默认输出中文，装完依赖后约 3 分钟出结果。脚本可能用 `sudo` 装 `sysbench`、`fio`、`python3`、`curl`。

```bash
curl -fsSL https://askclaw.top/abs.sh | bash -s -- -n         # 不安装缺失工具
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --lang en  # 英文输出
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --quick    # 快速版 ~60 秒
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --full     # 完整版 5–8 分钟
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --json-file result.json
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --help     # 全部选项
```

> `curl | bash` 直接执行下载内容。想先看脚本：
>
> ```bash
> curl -fsSLo abs.sh https://askclaw.top/abs.sh && less abs.sh && bash abs.sh
> ```

## 读结果

```text
得分：完整，得分 1568（仅本地；网络参考分 136）
结论：谨慎保留 — 磁盘性能偏弱
```

- **完整** = 所有核心测试都跑完（不代表快）
- **不完整，不能比较** = 有测试没跑成，分数不能和其他机器比
- **结论** = 按本地分数 + 最弱分项红线给的：分项 <250 直接「不建议保留」，<500 最多「谨慎保留」

## 测了什么、怎么算分

- **CPU** 单线程 + 全线程吞吐
- **内存** 顺序读写
- **磁盘** 顺序读写、4K 随机小 IO（QD1=队列深度 1，接近日常零散读写）、多线程压力
- **fsync** 4K 强制落盘写入（真正写进磁盘的指标，不是只到内存缓存）
- **网络** Cloudflare 简测（下载 10 MB、上传 5 MB 全零数据；仅供参考，**不计分**）

```text
总分 = 40% CPU + 15% 内存 + 30% 4K QD1 磁盘 + 15% fsync
```

公式细节、参考常数和已知局限见 [docs/scoring.md](docs/scoring.md)。

## 比较两台 VPS 的硬条件

两台机器分数**只在以下条件全部一致时可直接比**：ABS 版本、测试模式、`-t` 线程数、`-z` 测试文件大小、`DIRECT` 设置（默认 `1`=跳过系统缓存测真磁盘；`0`=走缓存，数值虚高）。两边都必须是「完整」结果。

## 行为说明

- **依赖装失败**：打印原因 + 修复建议 + 日志路径，继续跑出「不完整」结果，不无声退出。交互式终端里 `sudo` 接 `/dev/tty`，`curl | bash` 也能输密码；无终端用非交互 sudo、失败就跳过。不会自动跑 `dpkg --configure -a`。
- **文件**：日志写 `/tmp/abs.*` 私有目录；磁盘测试文件用独立临时目录、跑完删掉；已有 `abs.test*`、`abs-dd.test` **不会**被删。
- **没有 fio** 时退用 `dd` 粗测，不计入总分。
- **Alpine 最小镜像**：先 `apk add bash`。
- **终端默认中文**，`--lang en` 或 `ABS_LANG=en` 切英文；`results.tsv` / `result.json` 始终英文，方便脚本读。

**国内拉不到 GitHub Raw** 时走 jsDelivr 镜像：

```bash
curl --resolve cdn.jsdelivr.net:443:104.16.175.226 \
  -fsSL https://cdn.jsdelivr.net/gh/getaskclaw/abs@main/abs.sh | bash -s -- -n
```

## License

MIT
