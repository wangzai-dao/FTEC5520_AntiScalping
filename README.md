# 区块链防黄牛票务系统 · FTEC5520

> Anti-Scalping Concert Ticketing System
> Geth 私有链（Clique PoA）+ Solidity ERC-721 + Python Web3.py + Streamlit
> 本仓库包含**成员 1（私有链 / 部署 / Python 接口）**与**成员 4（Streamlit 页面 / 二维码验票）**的完整交付。

---

## 1. 一句话说明

门票是链上的 ERC-721；买票、限购、转售限价、转售次数、核销全部由 `ConcertTicket.sol` 强制执行。
Streamlit 网站只是"遥控器 + 显示器"：它发交易、读链上状态，**不做任何可以绕过合约的规则判断**。

## 2. 目录结构

```text
FTEC5520_AntiScalping/
├── blockchain/                 # 成员 1：私有链
│   ├── init_chain.py           #   生成 7 个测试账户 + genesis.json + .env
│   ├── genesis.json            #   Clique 创世块（init_chain.py 生成）
│   ├── start_node.sh           #   启动 / --reset 重建
│   ├── stop_node.sh
│   └── README_lab1_setup.md    #   Lab 1 环境与部署说明
├── contracts/                  # 成员 2、3 交付（本仓库未修改源码）
│   ├── ConcertTicket.sol
│   ├── Helper.sol
│   ├── build/ConcertTicket.json#   编译产物：ABI + bytecode
│   └── lib/@openzeppelin/      #   OpenZeppelin 5.0.2（fetch_deps.py 下载）
├── backend/                    # 成员 1：Python 接口
│   ├── compile.py              #   solc 0.8.20 编译
│   ├── deploy.py               #   部署 + 写 config/network.json
│   ├── chain.py                #   nonce/gas/签名/回执/异常 → TxResult
│   ├── ticket_api.py           #   页面唯一调用的接口层
│   └── demo_flow.py            #   端到端演示 + 证据采集
├── app/                        # 成员 4：Streamlit
│   ├── app.py                  #   入口 = 总览页
│   ├── common.py               #   样式、侧边栏导航、账户选择、交易结果卡片
│   ├── qr_utils.py             #   二维码签名 / 验签
│   └── pages/                  #   另外五个页面（1_activity … 5_checkin）
├── config/network.json         # 合约地址 / chainId / 账户地址（deploy.py 生成）
├── results/
│   ├── tx_evidence.json        # 27 条真实交易证据
│   ├── demo_report.md          # 可直接贴进报告的表格
│   └── screenshots/            # 六个页面截图
├── docs/
│   ├── ACCOUNTS.md             # 7 个测试账户地址、部署记录、本机复现记录
│   ├── ARCHITECTURE.md         # 架构图与数据流
│   ├── DEMO_SCRIPT.md          # 演示脚本（英文界面逐条操作）
│   ├── DEPLOYMENT_NOTES.md     # 实际运行环境、与任务书的差异、AWS 迁移方案
│   ├── HANDOFF_1_TO_4.md       # 1→4 交接单
│   ├── PUSH_TO_GITHUB.md       # 推送到 GitHub 的检查清单
│   ├── REPORT_MATERIAL.md      # 报告可直接引用的数据
│   ├── RUNBOOK.md              # 重启 / 重部署 / 换链
│   └── CONTRACT_REVIEW_FOR_MEMBER3.md  # 交给成员 3 的合约问题清单
├── scripts/
│   ├── check_chain.py          # 连通性自检
│   └── capture_screenshots.py  # 遗留：CDP 自动截图（macOS 专用，已停用）
└── requirements.txt
```

## 3. 快速开始

### 方式 A：一条命令（新机器 / 拿到压缩包后）

```bash
./scripts/bootstrap.sh        # 建 venv、装依赖、下 Geth 与 OpenZeppelin、建链、部署、造演示数据
.venv/bin/streamlit run app/app.py
```

### 方式 B：分步执行（想看每一步做了什么）

```bash
# 0) 依赖
python -m venv .venv && .venv/bin/pip install -r requirements.txt
./scripts/get_geth.sh                 # Geth 1.13.15（最后一个支持 Clique 私有链的版本）
python backend/fetch_deps.py        # OpenZeppelin 5.0.2

# 1) 建链
python blockchain/init_chain.py     # 生成账户 + genesis + .env（只需一次）
./blockchain/start_node.sh          # 启动 Geth

# 2) 编译 + 部署
python backend/compile.py
python backend/deploy.py

# 3) 造演示数据（可选，但截图/演示建议有）
python backend/demo_flow.py

# 4) 起网站
.venv/bin/streamlit run app/app.py
```

打开 http://127.0.0.1:8501 。自检：`python scripts/check_chain.py`。

> `tools/`、`contracts/bin/`、`contracts/lib/`、`.venv/`、`.env` 都在 `.gitignore` 里，
> 换机器按上面 0–2 步重新生成即可。
>
> **实际运行环境**：Ubuntu 22.04（本项目在 WSL2 中跑通）+ Python 3.10.12 + `streamlit==1.65.0`
> + Geth 1.13.15。与任务书约定环境（AWS EC2、chainId 5520）的差异、原因与 AWS 迁移步骤见
> [`docs/DEPLOYMENT_NOTES.md`](docs/DEPLOYMENT_NOTES.md)。
>
> **从 Windows 压缩包解到 Linux 时**：`.sh` 会丢失可执行位，先跑一次
> `chmod +x scripts/*.sh blockchain/*.sh`，否则报 `Permission denied`。

## 4. 六个页面（界面为英文）

| 页面 | 做什么 | 关键链上调用 |
|---|---|---|
| **Overview**（总览） | 链状态、合约地址、账户余额、最近门票流转 | `chainId` `blockNumber` `Transfer` 日志 |
| **Events**（活动管理） | 主办方建活动、开关售票/预售、批量白名单、结算票款 | `createEvent` `setEventActive` `setPresaleActive` `setWhitelistBatch` `withdrawProceeds` `withdrawPlatformFees` |
| **Buy Tickets**（购票） | 链上预检 `canPurchase` → 买票 → 回显 tx 与 `ownerOf` | `canPurchase` `purchaseTickets` `ownerOf` |
| **My Tickets**（我的门票） | 持仓、票主、转售次数、used、生成签名二维码 | `ownerOf` `tickets` `getMaxResalePrice` |
| **Resale Market**（二手市场） | 在售列表、挂牌（含超价被拒演示）、买入、取消 | `listForResale` `buyResale` `cancelListing` |
| **Staff Check-in**（工作人员验票） | 验签 → 链上交叉校验 → 核销 / 重复核销失败 | `verifiers` `checkIn` |

截图在 `results/screenshots/`（`01_overview.png` … `06_staff_checkin.png`）。

## 5. 规则落点

| 规则 | 合约实现 | 页面表现 |
|---|---|---|
| 每钱包限购 | `purchasedByWallet[eventId][wallet]` | 超限时显示 `Wallet limit exceeded` |
| 库存上限 | `concert.sold + quantity <= maxSupply` | 剩余票数实时显示 |
| 预售白名单 | `whitelist[eventId][account]` | 非白名单购买被拒 |
| 动态限价 | `getMaxResalePrice`：>7 天 120%，≤7 天 100% | 挂牌页显示当前上限，超价按钮演示被拒 |
| 转售次数 ≤ 3 | `ticket.resaleCount < 3` | 我的门票显示 `2/3` |
| 禁止直转 | `transferFrom` / `safeTransferFrom` 被 override 成 revert | 演示脚本 T11 生成一笔 status=0 的真实交易 |
| 一票一核销 | `ticket.used` | 第二次核销 revert `Ticket already used` |
| 验票权限 | `verifiers[msg.sender]` | 未授权账户核销 revert |

## 6. 证据文件

- `results/tx_evidence.json` — 27 条操作的 `tx_hash / block / gas / 结果`，含部署交易；
- `results/demo_report.md` — 同样内容的中文表格，可直接贴进 Final Report；
- `results/screenshots/` — 六个页面截图，其中购票页带真实成功交易、验票页带完整核验 + 核销结果。

重新生成：

```bash
./blockchain/start_node.sh --reset && sleep 5
python backend/deploy.py && python backend/demo_flow.py
.venv/bin/streamlit run app/app.py
```

截图目前是**手工截取**的（逐步操作见 [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)）；
`scripts/capture_screenshots.py` 是界面汉化时期的遗留脚本，已停用。

## 7. 安全与局限

- `.env` 保存 6 个测试账户私钥，**只用于本地私有链的课堂 Demo**，已 gitignore，不进 GitHub；
- 页面上的"当前登录账户"实际是用服务端持有的测试私钥代签。真实产品必须由用户自己的钱包签名；
- RPC 只监听 `127.0.0.1`，远程演示走 SSH 隧道，不把 8545 暴露到公网；
- 链上规则挡不住"一人多钱包"和"线下现金补差价"，报告里应如实说明；
- 合约本身的问题与建议见 `docs/CONTRACT_REVIEW_FOR_MEMBER3.md`（本仓库未改合约源码）。

## 8. 分工对照

| 任务书条目 | 交付物 |
|---|---|
| 成员 1-01~04 搭链、验证 RPC、准备账户 | `blockchain/`、`.env`、`genesis.json` |
| 成员 1-05 部署并记录地址/哈希 | `backend/deploy.py`、`config/network.json` |
| 成员 1-06 封装 `ticket_api.py` | `backend/ticket_api.py`（6 个核心接口 + 辅助） |
| 成员 1-07 封装签名/nonce/gas/异常/回执 | `backend/chain.py` `TxResult` |
| 成员 1-08 与成员 4 联调 | 六个页面全部走 `ticket_api` |
| 成员 1-09 重启/重部署说明 | `docs/RUNBOOK.md` |
| 成员 4-01~08 五个页面 + 二维码 | `app/pages/*`、`app/qr_utils.py`、截图 |
