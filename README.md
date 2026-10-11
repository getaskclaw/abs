# ABS — AskClaw VPS 跑分脚本

[English](README.en.md)

在租一台 Linux VPS（或续费）之前跑一下，就能知道这机器 CPU 快不快、内存够不够、磁盘写起来稳不稳。ABS 把这些测一遍，给一个分数和一个结论：**保留、谨慎保留、不建议保留**，或者**测试不完整**（某些测试没跑成，别拿这个分数下结论）。

## 跑一下

```bash
curl -fsSL https://askclaw.top/abs.sh | bash
```

默认输出中文，装完依赖后 3 分钟内出结果。脚本可能用 `sudo` 装 `sysbench`、`fio`、`python3`、`curl`。

```bash
# 不安装缺失工具
curl -fsSL https://askclaw.top/abs.sh | bash -s -- -n

# 英文输出
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --lang en
```

> `curl | bash` 会直接执行下载内容。想先看看脚本内容：
>
> ```bash
> curl -fsSLo abs.sh https://askclaw.top/abs.sh
> less abs.sh
> bash abs.sh
> ```

## 读结果

```text
===================== ABS 结果 =====================
得分：完整，得分 1568（仅本地；网络参考分 136）
结论：谨慎保留 — 磁盘性能偏弱
本地：完整，得分 1568（仅本地；网络不计分）
网络：参考分 136（Cloudflare HTTP，仅供参考，不计分）
====================================================
```

- **完整** = 所有核心测试都跑完了（不代表快）
- **不完整，不能比较** = 有测试没跑成，分数不能和其他机器直接比
- **保留 / 谨慎保留 / 不建议保留** = 按本地分数和一个“最弱分项”红线给出的建议
- **测试不完整** = CPU、内存、磁盘或 fsync 有缺项

## 测了什么

- **CPU**：单线程、全线程吞吐
- **内存**：顺序读写
- **磁盘**：顺序读写、4K 随机小 IO（QD1=队列深度 1，接近日常零散读写）、多线程压力
- **fsync**：4K 强制落盘写入（数据库/文件真正写完的指标，比“看起来写完了”更接近真实持久化）
- **网络**：Cloudflare 简单测速，仅供参考，**不计分**

```text
总分 = 40% CPU + 15% 内存 + 30% 4K QD1 磁盘 + 15% fsync
```

另外有一条底线规则：任一分项分数低于 250 直接「不建议保留」；低于 500 时最多只能到「谨慎保留」。也就是说，一个很弱的短板会拖累整体评价。

评分公式、参考常数、适用边界和已知局限见 [docs/scoring.md](docs/scoring.md)。

## 常用命令

```bash
# 快速检查，约 60 秒
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --quick

# 完整测试，约 5–8 分钟
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --full

# 跳过网络测速（本地分数仍有效）
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --no-network

# 结果存成 JSON
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --json-file result.json

# 网络测试加强版：Cloudflare + 3 个公共 iperf3 节点
curl -fsSL https://askclaw.top/abs.sh | bash -s -- --network-full
```

全部选项：`bash abs.sh --help`

## 比较两台 VPS

两台机器**只有在以下条件全部一致时，分数才能直接比**：

- ABS 版本相同
- 用的测试模式相同（`--quick` / 默认 / `--full`）
- 线程数 `-t` 相同
- fio 测试文件大小 `-z` 相同
- `DIRECT` 设置相同——`DIRECT=1`（默认）跳过文件系统缓存，直接测磁盘；`DIRECT=0` 走缓存，结果会虚高且**不能和 DIRECT=1 的结果比**
- 两边都是「完整」结果；任意一边是「不完整，不能比较」就不要比

## 终端语言 vs. 机器输出

- 终端显示默认中文，`--lang en` 或 `ABS_LANG=en` 切英文
- `results.tsv` 的指标名、`result.json` 的字段和值始终是英文，方便脚本读取
- 切语言不会改变分数和文件格式

## 依赖安装失败怎么办

ABS 会打印一个简短原因、一条修复建议和日志路径，然后继续跑出一个「不完整」结果，而不是无声退出。在交互式终端里，它把 `sudo` 接到 `/dev/tty`，所以 `curl | bash` 也能正常输密码；无人值守环境用非交互 sudo、失败就跳过。ABS 不会自动执行 `dpkg --configure -a` 这种系统级修复命令。

## 网络检查做了什么

默认只做 Cloudflare 简测：

- 从 Cloudflare 下载 10 MB
- 上传 5 MB 全零数据（测速用，不传真实文件）
- 单次超时 45 秒，失败自动重试一次

想要更完整的网络画像，用 `--network-full` 或 `--network-yabs` 加公共 iperf3 节点。

## 安全和文件位置

- ABS **不会上传跑分结果**
- 日志写在 `/tmp/abs.*` 随机私有目录
- 磁盘测试文件放在一个单独的临时目录，跑完删掉
- 已存在的 `abs.test*`、`abs-dd.test` 文件**不会**被删除
- 没有 `fio` 时退而用 `dd` 粗略测一下，但**不计入总分**
- Alpine 最小镜像要先装 bash：`apk add bash`

**中国网络拉不到 GitHub Raw 时**，用 jsDelivr 镜像：

```bash
curl --resolve cdn.jsdelivr.net:443:104.16.175.226 \
  -fsSL https://cdn.jsdelivr.net/gh/getaskclaw/abs@main/abs.sh | bash -s -- -n
```

## 术语速查

| 词 | 通俗意思 |
|---|---|
| `fsync` | 强制把数据真正写入磁盘（不是只写到内存缓存）。数据库、文件保存靠它才算写完 |
| `QD1` | 队列深度 1：一次只发一个 IO 请求，接近日常零散小读写 |
| `p95` | 95 分位延迟：95% 的请求比这个数快，反映“最坏那一批”的速度 |
| `DIRECT` | fio 的直连模式：1=跳过系统缓存测真实磁盘，0=走缓存（数值会虚高） |
| `OpenVZ` | 一种虚拟化方式；它的磁盘结果可能被缓存影响，建议再用 `--full` 验证 |

## 开发

```bash
python3 -m unittest -v tests/test_abs.py
```

push 和 PR 都会触发 GitHub Actions 跑这套测试。

## License

MIT
