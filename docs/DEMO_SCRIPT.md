# 演示脚本（成员 1 + 4 负责的部分）

> 对应任务书「最终 Demo 的 7 个动作」。页面地址都在 http://127.0.0.1:8501 。
> 演示前先跑：`./blockchain/start_node.sh && python backend/demo_flow.py && streamlit run app/app.py`。
> **界面已切换为英文版**，下表的按钮名以「」中的英文为准。

| # | 动作 | 页面 | 怎么点 | 屏幕上看到什么 |
|---|---|---|---|---|
| 1 | 主办方创建活动、发行 NFT 门票 | 「Events」 | 账户选 `organizer`，填名称/1 ETH/100 张/10 天后/限购 2 → 「Create event on-chain」 | 绿色交易卡片：tx 哈希、区块号、Gas；下方 `Existing events` 表新增一行 |
| 2 | 用户买到票，展示 ownerOf | 「Buy Tickets」 | 账户切 `verifier` →「Buy now」 | tx 哈希 + 「tokenId N minted · ownerOf(N) matches the buying account」 |
| 3 | 用户 A 挂牌，用户 B 合法买入 | 「Resale Market」 | 卖家 `buyerA` 选票、价格 1.2 →「List at this price」；右侧买家 `buyerB` →「Buy this ticket」 | 在售表出现该票；买入后 tx 成功，票主变化 |
| 4 | 超价转售被合约拒绝 | 「Resale Market」 | 卖家切 `buyerB`（第 3 步买入后票主已变成 B），选中同一张票 →「Over-price listing (expect rejection)」 | 红色卡片：`Price exceeds dynamic limit`（报价 1.5 > cap 1.2） |
| 5 | 直接转移 NFT 绕过规则被拒绝 | 终端 | `python backend/demo_flow.py` 的 T11，或直接看 `results/demo_report.md` | `transferFrom` 交易上链但 **status=0**，gas 22,558 |
| 6 | 用户 B 出示二维码，验票员首次核销成功 | 「My Tickets」→「Staff Check-in」 | `buyerB` 生成二维码 →「Send to check-in page」→「Verify ticket」→「Check in (first time)」 | 5 项校验全绿；核销 tx 成功；`used` 变 True，按钮置灰 |
| 7 | 再次核销失败，展示测试表与 Gas 图 | 「Staff Check-in」 | 「Check in again (should fail)」 | 红色卡片 `Ticket already used` |
| + | 收尾展示票款结算 | 「Events」底部 `Settlement (Pull Payment)` | 结算账户选 `organizer` →「Withdraw proceeds」 | `Pending proceeds` 由 N 变 0，`Account balance` 增加，绿色卡片「TX SUCCESS」 |
| + | 收尾展示 | —— | 打开 `results/demo_report.md` | 27 条用例的 PASS/FAIL、tx 哈希、Gas 一览 |

> ⚠️ **两个必踩的坑（已避坑）**
> 1. `demo_flow.py` 跑完后 `buyerA` 已买满 2 张（限购 2），再用它点「Buy now」会报
>    `Wallet limit exceeded`。第 2 步要换一个**还没买过票**的账户（`verifier`）。
> 2. 同一张票**已经挂牌**时再挂，报的是 `already listed`，不是限价错误。第 4 步要确保那张票
>    当前未在售（第 3 步被 `buyerB` 买走后正好满足），且卖家账户要切成新的票主 `buyerB`。

## 讲解要点（每页一句）

- **Overview**：链 ID、区块高度、合约地址、6 个账户余额都来自链上；下面列出最近的 Transfer 日志。
- **Events**：活动参数一旦上链，改前端没用；白名单批量写入是一条交易。底部 `Settlement` 展示拉取式结算。
- **Buy Tickets**：先 `canPurchase` 预检（不花 gas），再 `purchaseTickets`；金额由页面按 `price × quantity` 算准，
  多 1 wei 都会被合约拒绝。
- **My Tickets**：合约没有继承 ERC721Enumerable，"我的票"是扫 Transfer 事件 + 逐个 `ownerOf` 校验得到的。
  二维码里是持票人签名 + 180 秒时效，不是裸 tokenId。
- **Resale Market**：限价是合约算的（>7 天 120%，≤7 天 100%），页面只是把上限显示出来。
- **Staff Check-in**：签名 + 链上 ownerOf + used 三者都对才放行；核销权限看的是 `msg.sender`，与票主无关。

## 备用方案（现场网络/节点出问题）

1. `./blockchain/start_node.sh --reset && sleep 5 && python backend/deploy.py && python backend/demo_flow.py`
   重建一条干净链（约 3 分钟）；
2. 直接用 `results/screenshots/` 里的六张截图讲流程（每张都是真实链上数据）；
3. `results/demo_report.md` 里有全部 27 条交易哈希，可在 `geth attach` 里逐条核对。

## 账户与口令

| 角色 | 用途 |
|---|---|
| organizer | 建活动、开关售票、白名单、提取票款 |
| buyerA | 一级购票、首次挂牌 |
| buyerB | 二手买入、被核销的持票人 |
| verifier | 链上核销 |
| attacker | 未授权核销 / 超额购买（演示用） |
| deployer | 合约 owner，提取平台手续费 |

私钥只在本机 `.env` 里，**不要**在演示时投屏 `.env` 或 `blockchain/miner.key`。
