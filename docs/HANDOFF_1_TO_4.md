# 交接单：成员 1 → 成员 4

> 对应任务书「1 → 4：RPC 安全访问方式、Chain ID、合约地址、ABI、Python 接口、测试角色，
> 验收标准：成员 4 能 import 接口并在页面显示真实链上结果」。

## 1. 连接信息

| 项目 | 值 | 说明 |
|---|---|---|
| RPC URL | `http://127.0.0.1:8545` | 由 `config/network.json` 的 `rpc_url` 决定 |
| Chain ID | `1337` | 链上 `eth_chainId`，与 `.env` 的 `CHAIN_ID` 必须一致 |
| 合约地址 | 见 `config/network.json` 的 `contract_address` | 每次 `deploy.py` 会更新 |
| 部署区块 | 见 `deploy_block` | 扫事件时作为 `fromBlock` 起点 |
| 合约源码 | `contracts/ConcertTicket.sol` | 成员 2、3 交付，未修改 |
| ABI | `contracts/build/ConcertTicket.json` 的 `abi` 字段 | `compile.py` 生成 |
| Bytecode | 同文件 `bytecode` 字段 | 用于重新部署 |

> RPC 安全：节点只监听 `127.0.0.1`。**不要**把 8545 暴露到公网；远程演示走 SSH 隧道
> `ssh -i FTEC5520.pem -L 8545:127.0.0.1:8545 ubuntu@<EC2-IP>`。

## 2. 页面只需要这一个 import

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # 项目根目录
from backend import ticket_api as api
```

`ticket_api` 内部已经处理：连接、POA 中间件、nonce、gas、本地签名、等待回执、异常转文字。
页面**不要**自己 new Web3、不要自己拼交易。

## 3. 接口清单（6 个核心 + 常用辅助）

| 函数 | 返回 | 用途 |
|---|---|---|
| `get_ticket_owner(token_id)` | `str` 地址 | 门票当前票主 |
| `buy_ticket(event_id, buyer="buyerA", quantity=1)` | `TxResult` | 一级购票，`extra` 里有 `first_token_id` |
| `list_ticket(token_id, price_eth, seller="buyerA")` | `TxResult` | 挂牌，超过动态上限会被合约拒绝 |
| `buy_resale(token_id, buyer="buyerB")` | `TxResult` | 买二手票 |
| `check_in(token_id, verifier="verifier")` | `TxResult` | 链上核销 |
| `get_receipt(tx_hash)` | `dict` | 回执：block / gas / status / timestamp |

辅助：`get_event` `list_events` `get_ticket` `get_max_resale_price` `can_purchase`
`purchased_count` `remaining_supply` `tokens_of` `listed_tickets` `transfer_history`
`create_event` `set_whitelist` `set_event_active` `set_presale_active` `set_verifier`
`is_verifier` `get_chain_status` `signing_key` `pending_proceeds` `pending_platform_fees`
`withdraw_proceeds` `withdraw_platform_fees`。

`TxResult` 统一结构：

```python
TxResult(ok=True, function="purchaseTickets", tx_hash="0x…",
         block_number=44, gas_used=155012, status=1, from_address="0x…", error=None)
```

失败时 `ok=False`，`error` 是合约 revert 的原因（已去掉 ABI 编码的十六进制串）：

```
Not an authorized verifier
Price exceeds dynamic limit
Ticket already used
Wallet limit exceeded
```

## 4. 测试角色

| 角色 | 用途 | 页面上怎么选 |
|---|---|---|
| `deployer` | 合约 owner，授权验票员、提平台费 | 账户下拉框 |
| `organizer` | 创建活动、开关售票、设白名单 | 账户下拉框 |
| `buyerA` | 一级购票、首次转售的卖家 | 账户下拉框 |
| `buyerB` | 二手买家 | 账户下拉框 |
| `verifier` | 链上核销 | 账户下拉框 |
| `attacker` | 未授权核销 / 超额购买等异常用例 | 账户下拉框 |

URL 支持 `?account=buyerB` 直接预选账户，方便演示和截图。

## 5. 联调检查清单（已完成）

- [x] Streamlit 能 `import backend.ticket_api` 并显示真实链上数据（总览页）
- [x] 购票按钮产生真实交易，页面回显 tx 哈希、区块号、Gas（截图 03）
- [x] 我的门票页读 `ownerOf` / `tickets`，并能生成签名二维码（截图 04）
- [x] 验票页完成「验签 → 链上交叉校验 → checkIn」全流程（截图 06）
- [x] 失败场景能显示合约 revert 原因（超价、重复核销、未授权）
- [x] 交易证据落盘：`results/tx_evidence.json`、`results/demo_report.md`

## 6. 给成员 4 的两个注意点

1. **不要在页面里做规则判断**（比如自己算价格上限）。上限由 `get_max_resale_price()` 读链上结果，
   真正拦截的是合约；页面算错了只会误导用户。
2. **账户私钥只用于课堂 Demo 的"服务端代签"**。报告里要写明：真实产品应由用户自己的钱包签名，
   服务端不应持有用户私钥。页面上已有这句提示。
