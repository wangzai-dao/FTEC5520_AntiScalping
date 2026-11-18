# 报告素材（成员 1 / 成员 4 各一页）

> 直接给成员 5 汇总用。数据全部来自本仓库的真实运行结果，可对照 `results/tx_evidence.json`。

---

## 一、成员 1：私有链、部署与 Web3.py 接口

**目标**：让合约真的跑在链上，并把每一次调用封装成可复用、可观测的 Python 函数。

**做了什么**

1. 用 Geth 1.13.15 搭建 Clique PoA 私有链（chainId 1337，2 秒出块），
   genesis 预置 7 个账户各 1000 ETH，矿工账户写入 `extradata` 并由节点解锁自动出块。
2. 编译成员 2、3 交付的 `ConcertTicket.sol`（solc 0.8.20，`evmVersion=paris` 避开 PUSH0），
   产出 ABI / Bytecode；部署交易 **gas 3,294,415**，合约代码 14,339 bytes。
3. 写 `backend/ticket_api.py`：页面只调业务函数（`buy_ticket` / `list_ticket` / `buy_resale` / `check_in` …），
   内部统一处理 nonce、`maxFeePerGas = baseFee×2 + 1 gwei`、本地签名、等待回执、异常转文字。
4. 所有写操作返回同一个结构：

   ```python
   TxResult(ok, function, tx_hash, block_number, gas_used, status, error)
   ```

   失败时 `error` 是合约的 revert 原因（`Price exceeds dynamic limit` 等），
   而**失败的预检不会发交易、不花 gas**——`estimate_gas` 阶段就把 revert 捕获了。

**关键设计**

- **先预检、后发交易**：`canPurchase` / `estimate_gas` 让用户在页面上就看到"为什么不能买"，
  避免提交注定失败、仍要付 gas 的交易。
- **地址只有一个来源**：`config/network.json`。换链只需改 RPC 与 chainId，重新部署后页面自动跟随，
  不需要改任何页面代码。
- **POA 中间件**：Clique 区块的 `extraData` 是 97 字节，不注入 `ExtraDataToPOAMiddleware` 时
  Web3.py 解析区块会直接报错——这是私有链与主网最大的实现差异。

**可核验的证据**

| 内容 | 数值 |
|---|---|
| 部署交易 | `results/tx_evidence.json` → `network.deploy_tx` |
| 27 条用例 | 27 PASS / 0 FAIL（`results/demo_report.md`） |
| 典型 Gas | createEvent 168,332；purchaseTickets 155,012；listForResale 79,891；buyResale 110,677；checkIn 51,851 |
| 被拒绝的直转交易 | `transferFrom` 上链但 **status=0**，gas 22,558 |

---

## 二、成员 4：Streamlit 页面与签名二维码

**目标**：把链上能力做成可操作的网站，页面上每个数字都能追到一次合约读取。

**六个页面**

| 页面（界面英文） | 关键实现 |
|---|---|
| Overview（总览） | 链状态、6 个账户余额、最近 Transfer 日志（从部署区块扫到最新） |
| Events（活动管理） | `createEvent` 表单 + 活动表 + 售票/预售开关 + 批量白名单 + 票款结算（`withdrawProceeds` / `withdrawPlatformFees`） |
| Buy Tickets（购票） | `canPurchase` 预检 → `purchaseTickets` → 回读 `ownerOf` 对照；附两个“必失败”演示按钮 |
| My Tickets（我的门票） | 用 Transfer 事件重建持仓（合约无 ERC721Enumerable），展示 `tickets()` 全字段，生成二维码 |
| Resale Market（二手市场） | 在售表 + 动态上限 + 挂牌/取消/买入，超价按钮直接演示被合约拒绝 |
| Staff Check-in（工作人员验票） | 验签 → 链上交叉校验 → `checkIn`，含重复核销、未授权核销的对照 |

**二维码为什么不是裸 tokenId**

裸 tokenId 谁都能截图转发。这里的二维码是一段 JSON：

```json
{"v":1,"token_id":4,"holder":"0x60D7…fC19","nonce":"a3482ceee5b4c5af",
 "issued_at":1794921616,"expires_at":1794921796,"sig":"0x…"}
```

`sig` 是持票人私钥对规范化文本做的 EIP-191 签名。验票端做 5 项检查：

1. 票根版本 2. 签名恢复出的地址 == `holder` 3. 未过期（默认 180 秒）
4. `holder == ownerOf(tokenId)` 5. 链上 `used == false`

截图转发会在第 3 项失败（过期）；转售后旧票主会在第 4 项失败；
重复入场会在第 5 项失败——三种攻击面分别由不同的检查覆盖，而不是靠一个 tokenId 判断。

**为什么必须用 Web3.py 读链上状态**

如果页面用本地数据库记"这张票是谁的、有没有核销"，那么改数据库、换个人登录、
甚至把前端参数改一改就能绕过所有规则；链上状态是所有人共享、且由合约 `require` 守护的唯一事实来源。
页面在这里的角色只是"读 `ownerOf` 并显示"，它读到的值与任何其他人读到的值完全一致，
不依赖服务器是否可信。

**页面上刻意保留的"失败路径"**

超价挂牌、重复核销、未授权核销、直转 NFT 四类操作在页面上都有按钮/脚本可以当场触发，
点下去看到的是合约返回的 revert 原因。这比只说"我们做了限制"更有说服力：
限制来自链上，而不是界面把按钮藏了。

**局限（报告中应如实写）**

- 课堂 Demo 由 Python 服务端持有测试私钥代签，真实产品必须由用户钱包签名；
- 链上规则无法阻止一人多钱包、线下现金补差价；
- 私有链由单节点出块，不具备主网的抗审查性与去中心化程度。
