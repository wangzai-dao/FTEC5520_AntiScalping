# 部署与运行环境说明

> 本文件用于说明本项目**实际采用的运行环境**、**与任务书约定的差异及原因**，并给出**迁移到 AWS EC2 的可执行方案**。
> 目的是把"环境口径"讲清楚，避免评审时对不上。

---

## 1. 实际运行环境

| 项目 | 实际值 | 说明 |
|---|---|---|
| 主机 | 个人笔记本（Windows 11） | 见第 2 节差异说明 |
| 运行载体 | **WSL2 + Ubuntu 22.04.5 LTS** | 完整 Linux 用户态，非模拟层 |
| Python | 3.10.12 | Ubuntu 22.04 系统自带 |
| 以太坊客户端 | **Geth 1.13.15-stable**（commit c5ba367e，Go 1.21.6，linux/amd64） | 最后一个支持 Clique PoA 私有链的版本 |
| 合约编译器 | solc **0.8.20**（commit a1b79de6），`evmVersion=paris`，optimizer runs=200 | 由 `backend/compile.py` 自动获取 |
| 依赖库 | web3.py 8.0.0、streamlit 1.65.0、eth-account ≥0.13、qrcode ≥7.4 | 见 `requirements.txt` |
| 链类型 | 私有链，共识 **Clique PoA**，出块周期 2 秒 | |
| chainId | **1337** | 本地开发链惯例值 |
| RPC 端点 | `http://127.0.0.1:8545`（仅回环） | 不对外暴露 |
| 智能合约 | `ConcertTicket`，Solidity 0.8.20，依赖 OpenZeppelin 5.0.2 | 见 `docs/ACCOUNTS.md` |

一键复现路径见 `docs/RUNBOOK.md`；账户与部署记录见 `docs/ACCOUNTS.md`。

---

## 2. 与任务书约定的差异及原因

| # | 项目 | 任务书约定 | 实际采用 | 原因 | 对功能的实际影响 |
|---|---|---|---|---|---|
| 1 | 运行主机 | AWS EC2 | 本地 WSL2 Ubuntu 22.04 | 私有链只在本机回环通信，公网部署不带来额外功能验证价值；课程期间 AWS 账号与计费不便利 | **无。** 同为 Linux 用户态，同一份 Geth 二进制、同一套启动脚本、同一份 genesis。迁移步骤见第 3 节，全程无需改代码 |
| 2 | chainId | 5520（早期设想） | **1337** | 1337 是 Ethereum 本地开发链的惯例值，避免与主网 / 公共测试网冲突 | 无。chainId 仅用于签名防重放域隔离，取值本身不影响合约逻辑 |
| 3 | streamlit 版本 | `requirements.txt` 中为 1.67.0 | **1.65.0** | 1.67.0 要求 `Python >= 3.11`；Ubuntu 22.04 默认 Python 3.10.12，pip 会因单个版本不满足而**整体中止安装** | **无。** 页面用到的 API（`st.rerun` / `st.page_link` / `st.metric(help=)` / `st.divider`）自 1.31 起即已提供 |
| 4 | solc 自动下载 | 官方 `binaries.soliditylang.org` | 同样来源，但**修复了 2 处缺陷**后才可用 | ① 站点前置 Cloudflare，会拦截 Python 默认 UA 返回 `403 Forbidden`；② 该站 `list.json` 的 `releases` 键为**纯语义化版本**（`"0.8.20"`），原实现按 `"0.8.20+commit..."` 匹配会抛 `StopIteration` | 无。修复后**全新克隆可一条命令完成编译**，不再需要手工下载 solc |

> 说明：第 3、4 项属于**工程健壮性修复**，已提交到 `backend/compile.py` 与 `requirements.txt`，并在本机通过"删除缓存编译器后重新编译"验证。

---

## 3. 迁移到 AWS EC2 的可执行方案

### 3.1 目标架构

```
本地浏览器 ──localhost:8501──┐
                             ├─ SSH 隧道 ─→ EC2 (Ubuntu 22.04)
本地浏览器 ──localhost:8545──┘                 ├─ Streamlit :8501
                                              ├─ Geth RPC :8545 (仅回环)
                                              └─ Clique 私有链 chainId 1337
```

**关键点：8545 与 8501 都不对公网开放**，一律通过 SSH 端口转发访问。RPC 端口若暴露公网，等于把已解锁的出块账户交给任何人。

### 3.2 实例与网络配置

| 项目 | 建议值 |
|---|---|
| AMI | Ubuntu Server 22.04 LTS (HVM), SSD Volume Type |
| 实例类型 | `t3.small`（2 vCPU / 2 GiB）即可；`t3.micro` 在编译合约时可能 OOM |
| 存储 | 20 GiB gp3 |
| 安全组入站 | **仅 SSH 22**，源地址限定为自己的公网 IP |
| 安全组入站 | **不要开放** 8545、8501、30303 |
| 出站 | 默认全放行（需要下载 geth 与 solc） |

### 3.3 部署步骤

```bash
# 1) 登录
ssh -i <key.pem> ubuntu@<EC2_PUBLIC_IP>

# 2) 系统依赖
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git

# 3) 取得代码（二选一）
git clone <repo-url> ~/FTEC5520_AntiScalping
# 或从本地上传（注意排除 .venv / blockchain/data / tools 等大目录）
#   scp -i <key.pem> -r ./FTEC5520_AntiScalping ubuntu@<IP>:~/

# 4) 按 RUNBOOK 执行
cd ~/FTEC5520_AntiScalping
chmod +x scripts/*.sh blockchain/*.sh
rm -f config/network.json          # 清除其他机器遗留的地址清单
python3 -m venv .venv && .venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
./scripts/get_geth.sh && ./tools/geth version    # 必须为 1.13.15-stable
.venv/bin/python backend/fetch_deps.py
.venv/bin/python blockchain/init_chain.py
./blockchain/start_node.sh
.venv/bin/python backend/compile.py
.venv/bin/python backend/deploy.py
.venv/bin/python backend/demo_flow.py            # 期望 PASS 27 / FAIL 0
```

### 3.4 前端访问（SSH 隧道）

```bash
# 在本地机器执行，把云端两个端口映射到本地
ssh -i <key.pem> -N \
    -L 8501:127.0.0.1:8501 \
    -L 8545:127.0.0.1:8545 \
    ubuntu@<EC2_PUBLIC_IP>
```

另开一个 SSH 会话启动前端：

```bash
cd ~/FTEC5520_AntiScalping && .venv/bin/streamlit run app/app.py
```

本地浏览器访问 `http://localhost:8501` 即可；`config/network.json` 中的 `rpc_url` **保持 `http://127.0.0.1:8545` 不变**（因为隧道已把它映射到云端）。

### 3.5 两种迁移方式

| 方式 | 做法 | 结果 | 适用场景 |
|---|---|---|---|
| **A. 全新初始化** | 在 EC2 上直接跑 `init_chain.py` → `start_node.sh` → `deploy.py` → `demo_flow.py` | 生成 7 个**新**账户与新合约地址；`docs/ACCOUNTS.md` 与 `results/` 需重新生成 | 首次云端验证、追求环境干净 |
| **B. 迁移现有链数据** | 把本机 `.env`、`blockchain/genesis.json`、`blockchain/miner.key`、`blockchain/miner.addr`、`blockchain/password.txt`、`blockchain/data/` 一并拷贝到 EC2 同路径，直接 `start_node.sh` | **账户与合约地址完全不变**，历史交易与证据继续有效 | 希望证据链连续的答辩演示 |

> 方式 B 要求两端 Geth 版本一致（均为 1.13.15-stable）。`.env` 含私钥，传输必须用 `scp`/`rsync` 走 SSH，**不得**提交到版本库。

### 3.6 成本（参考价，2026 年）

| 项目 | 单价 | 演示 2 小时 |
|---|---|---|
| t3.small 按需 | 约 $0.0208 / 小时 | 约 $0.04 |
| EBS gp3 20 GiB | 约 $1.60 / 月（按小时折算） | 约 $0.004 |
| 数据传输 | 内网/隧道不计费 | ≈ 0 |
| **合计** | | **不到 $0.05** |

演示结束后 `停止实例`（不是终止），EBS 保留，下次可继续。

### 3.7 安全注意事项

1. **绝不把 8545 暴露到公网。** Geth 启动时使用了 `--unlock` 与 `--allow-insecure-unlock`，端口一旦暴露等同于交出出块私钥。
2. **`.env`、`miner.key`、`password.txt` 不入库。** 已在 `.gitignore` 中排除；上传前请再次确认。
3. 安全组 SSH 源地址请限定为自己的 IP，不要用 `0.0.0.0/0`。
4. 演示用私有链的私钥仅具教学价值，但仍不应公开。
5. 演示完毕后可 `sudo shutdown -h now` 并停止实例。

---

## 4. 证据口径声明

为避免截图、交易记录与文中引用三者不一致，特此声明：

| 证据 | 来源 | 标识 |
|---|---|---|
| `results/tx_evidence.json`、`results/demo_report.md` | 同一次运行（`backend/demo_flow.py` 产出） | 合约地址见 `config/network.json` |
| `results/screenshots/01–06` | 同一条链上的 Streamlit 页面截屏 | 页面左下角显示的合约地址与上表一致 |
| `docs/ACCOUNTS.md` 的 7 个账户与部署记录 | 同一条链（`init_chain.py` / `deploy.py` 产出） | 与 `config/network.json` 一致 |

**校验方式**：页面左侧栏底部显示 `约 0x....`，应等于 `config/network.json` 中的 `contract_address`；若不一致，说明截图来自另一条链，以 `config/network.json` 与 `docs/ACCOUNTS.md` 为准。
