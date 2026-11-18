# 测试账户清单（本地私有链 chainId 1337）

> 本文件只记录**公开地址**。私钥在项目根目录 `.env`（已被 `.gitignore` 排除），切勿提交或外发。

| 项目 | 值 |
|---|---|
| 生成时间 | 2026-11-17 |
| 生成命令 | `.venv/bin/python blockchain/init_chain.py` |
| 运行环境 | WSL2 Ubuntu 22.04.5 LTS · Python 3.10.12 · Geth 1.13.15-stable · solc 0.8.20 |
| chainId | 1337（Clique PoA，出块间隔 2 秒） |
| RPC | http://127.0.0.1:8545 |

---

## 7 个账户

| 角色 | 地址 | 身份 | 主要职责 | 相关测试 |
|---|---|---|---|---|
| deployer | `0xac58247eD6B94f69762b7eBce072583c1159aD7f` | 平台方 | 部署合约 → 成为合约 owner；指定验票员；收取 5% 平台手续费 | T19 / T24 |
| organizer | `0x0aF12A334a38d395117639881915E44fE5d4bBFD` | 主办方（演唱会公司） | 创建活动、开关预售、维护白名单、提取票款 | T01 / T02 / T20 |
| buyerA | `0xeE380Abd54DD46C88F26e21424105039198303a3` | 买家 A（白名单内） | 预售期购票、挂二手市场、入场验票 | T03 / T09b / T13 / T15 |
| buyerB | `0x60D7A41a7DF950756bC63c37698d086C9d35fC19` | 买家 B | 转售后的接盘方，用于验证 NFT 所有权转移 | T14 / T23 |
| verifier | `0x1FbD76615383d87B68bF9686342F3e6F2a0C2CF0` | 现场工作人员 | 扫码核销，把门票标记为「已使用」 | T15 / T16 |
| attacker | `0xDac1050a8de63b9550D0F14ED6deA90389F2EDc2` | 黄牛 | 故意违规：非白名单抢预售票、超额购票、超价转售 | T04 / T06 / T08 / T10 |
| miner | `0xdC478e3dCd62762374C582774079e104B5d83E3E` | 出块节点 | Clique PoA 授权签名者，每 2 秒封装一个区块 | 后台常驻 |

---

## 初始余额

创世文件 `blockchain/genesis.json` 的 `alloc` 字段为以上 7 个账户各分配 **1000 ETH**。

这是私有链独有的特权：创世文件写什么，链上初始状态就是什么。

---

## 部署记录（已核对）

| 项目 | 值 |
|---|---|
| 合约地址 | `0x46335ea6e72DD537A5f18402b440DDdEA824cC1e` |
| 部署交易 hash | `0x7358e6e196d6dc58da1a8a245eab966ef36cb2ff37492b9dc3b3dae257853424` |
| 部署区块号 | 190 |
| 部署 gas 用量 | 3,294,415 |
| 运行时字节码大小 | 14,339 bytes（创建字节码 15,008 bytes） |
| 部署后 owner | `0xac58247eD6B94f69762b7eBce072583c1159aD7f`（= deployer） |
| 合约初始状态 | `nextEventId = 1`、`nextTokenId = 1`（尚无活动、尚无门票） |

### 本机复现记录（2026-11-17）

| 操作 | 结果 | 证据 |
|---|---|---|
| `backend/demo_flow.py` | **PASS 27 / FAIL 0** | `results/tx_evidence.json`、`results/demo_report.md` |
| `transferFrom` 绕过模拟强制上链 | 失败交易，gas 22,558 真实消耗 | `0xef24a9076e73961ace6c26e58609b5ee75a9e549184420f9ccf145b7e2fe3a3a` |
| organizer 提取票款 5.5 ETH | 余额 999.9993 → 1005.4992，待提取归零 | `0x117771d2ce8a71f42b482a8e28daab4a9d4e9cdf198010f621254a53ffdf736a`（block 414，gas 32,388） |
| demo 后链上状态 | events 4 / tickets 7 / 在售 2 | `scripts/check_chain.py` |
| 界面手工演示（截图用） | verifier 在 Buy Tickets 买 2 张（token 8、9）；buyerA 把 token 3 以 1.0 ETH 挂牌；buyerB 的 token 4 生成二维码并在 Staff Check-in 验签通过（未核销） | 截图 03/04/05/06，tx `0x33d31905…`、`0x45ee4fd1…` |
| 截图完成时链上状态 | events 4 / tickets 9 / 在售 3（token 3、6、7）/ 已核销 2（token 1、8）/ organizer pendingProceeds 1.0 ETH | `results/screenshots/` |

> **关于两组数字的差异**：`results/demo_report.md` 是 `demo_flow.py` 跑完那一刻的快照
> （门票 7 张、在售 [6, 7]、最终区块 303）；6 张截图是在此之后用界面手工操作拍的
> （多出 token 8 / 9，多出 token 3 的在售）。两者都是真实链上状态，只是时间点不同。

---

## 注意

- 执行 `blockchain/init_chain.py --force` 会**重新生成全部账户**并清空链数据，届时本文件必须同步更新。
- `attacker` 账户的所有交易都是**预期失败**的；失败本身就是合约规则生效的证据，不是 bug。
- 同一份清单位于 WSL 的 `~/FTEC5520_AntiScalping/docs/ACCOUNTS.md`。
