# 成员 2 / 3 合约评审：合并版 `ConcertTicket.sol` 的问题清单

> 评审对象：`contracts/ConcertTicket.sol`（`chunyusongyue-creator/FTEC5520-Final`，commit `61665bc`）
> 结论：**功能可以跑通，18 项测试里合约相关的用例全部按预期通过**（见 `results/demo_report.md`）。
> 下面按严重程度列出建议改动，交给成员 3 确认是否采纳。
> 本次成员 1/4 的交付**没有修改合约源码**，只在 Python 层规避了 `getTicket` 缺失等问题。

## 一、建议修复（会影响实际使用）

### 1. `withdrawPlatformFees()` 在 owner 变更后取不出平台费（中）

```solidity
pendingPlatformFees[owner()] += platformFee;      // 记账写死给 owner()
...
uint256 amount = pendingPlatformFees[msg.sender]; // 提现却用 msg.sender
```

`withdrawPlatformFees()` 带 `onlyOwner`，所以只要 owner 没变，两者相等、能取出来。
但一旦 `transferOwnership()` 把 owner 换成别人：

- 旧 owner 名下的手续费再也没人能取（函数只允许新 owner 调用，读的却是新 owner 的余额 = 0）；
- 新 owner 也取不到旧账。

**建议**：记账和提现都用同一个地址来源，例如

```solidity
pendingPlatformFees[owner()] += platformFee;
uint256 amount = pendingPlatformFees[owner()];   // 而不是 msg.sender
```

### 2. `buyResale()` 缺少演出时间/活动状态校验（低-中）

`listForResale()` 要求 `block.timestamp < eventTime`，但 `buyResale()` 只检查 `isListed`。
于是演出开始（甚至结束）后，之前挂的单仍然可以被买走——买家付了钱却进不了场。
同理，活动被 `setEventActive(false)` 下架后，二级市场照常成交。

**建议**：在 `buyResale` 里补

```solidity
require(concert.active, "Event is not active");
require(block.timestamp < concert.eventTime, "Event already started");
```

### 3. `getMaxResalePrice()` 对演出结束后 / 不存在的 tokenId 行为不明确（低）

- 演出时间已过时 `concert.eventTime - block.timestamp` 会 **下溢 revert**，调用方必须先自己判断时间；
- tokenId 不存在时 `tokenToEvent = 0`、原价 0，函数**返回 0 而不是 revert**，容易被误读成"这张票不能卖"。

**建议**：

```solidity
require(tokenToEvent[tokenId] != 0, "Ticket does not exist");
require(block.timestamp < concert.eventTime, "Event already started");
```

（成员 1 的 `ticket_api.get_max_resale_price()` 已经做了异常保护，页面不会崩。）

### 4. 缺少 `getTicket(tokenId)` 只读聚合接口（低，影响前端）

文档第 08 节约定了 `getTicket(tokenId)`，合并版合约里没有。前端要显示"票主 + 活动 + 转售次数 + 是否已用"
得连读 `ownerOf`、`tickets`、`tokenToEvent`、`concertEvents` 四次，而且合约**没继承 ERC721Enumerable**，
"我的门票"页面拿不到持仓列表。

现在的做法：成员 1 在 `backend/ticket_api.py` 里用事件扫描 + 逐个 `ownerOf` 校验补出来
（`tokens_of()` / `get_ticket()`），只读、不改合约。如果后续要优化 Gas/请求数，建议合约加：

```solidity
function getTicket(uint256 tokenId) external view returns (
    address owner, uint256 eventId, uint256 originalPrice,
    bool isListed, uint256 listingPrice, uint256 resaleCount, bool used
) { ... }
```

### 5. `buyResale` 的资金流是"推"给卖家的（低）

```solidity
(bool success, ) = payable(seller).call{value: sellerAmount}("");
require(success, "Payment to seller failed");
```

如果卖家是拒收 ETH 的合约，这张票就永远卖不掉（每次买都会 revert）。
EOA 卖家不受影响。更稳的做法是像 `pendingProceeds` 一样改成拉取式：

```solidity
pendingResaleProceeds[seller] += sellerAmount;   // 卖家自己 withdraw
```

## 二、设计限制（不一定要改，但报告里应该写）

| 现象 | 说明 |
|---|---|
| 一级限购只统计 `purchasedByWallet` | `buyResale` 买入不计入限购，可以靠"买二手"绕过每钱包限购；合约本来就无法阻止一人多钱包，报告里已列为局限 |
| `checkIn` 不校验持票人身份 | 验票员可以对任意未使用的票核销（包括别人持有的）。本项目用"持票人签名二维码"在链下补这一层，合约层只保证"一票只能核销一次" |
| `approve` / `setApprovalForAll` 仍在 | 可以授权，但 `transferFrom` / `safeTransferFrom` 全被 override 成 revert，授权没有实际用途，可理解为无害的残留接口 |
| `purchaseTickets` 要求金额**精确相等** | 多付 1 wei 直接 revert，而不是退款。前端必须按票价算准数额（成员 1 的 `buy_ticket` 已按 `price × quantity` 计算） |
| 合约没有暂停开关 | 出事只能靠 `setEventActive(false)` 停单个活动，没有全局 pause |

## 三、`Helper.sol` 的测试脚本

1. `runAllTests()` 只花 **1 ETH**（买 1 张票），而 README 让你在 Remix 的 Value 里填 `5 ether`。
   填 5 ETH 也能跑（剩余部分最后退回），但文档数字对不上，建议统一成 1 ETH。
2. `Helper` 的构造函数里 `new ConcertTicket()`，所以 **Helper 自己才是 owner**，
   `setVerifier(address(this), true)` 才能成功。如果改成"传入已部署的主合约地址"，这行会直接 revert。
   若要做"对已部署实例做集成测试"，必须让主合约 owner 先授权 Helper。
3. 第 3 步"买 2 张触发限购"实际被 `Wallet limit exceeded` 拦住，
   这是合约里 **先校验限购、后校验金额** 的顺序决定的——顺序若反过来，同样的测试会以
   `Incorrect ETH amount` 失败，测试结论就会误判。建议测试里显式写清预期 revert 原因。

## 四、本次交付对合约的依赖清单

| 页面 / 接口 | 依赖的合约函数 |
|---|---|
| 活动管理 | `createEvent` `setEventActive` `setPresaleActive` `setWhitelistBatch` `concertEvents` `nextEventId` |
| 购票 | `canPurchase` `purchaseTickets` `nextTokenId` `remainingSupply` |
| 我的门票 | `ownerOf` `tickets` `tokenToEvent` `getMaxResalePrice` |
| 二手市场 | `listForResale` `cancelListing` `buyResale` |
| 验票 | `verifiers` `setVerifier` `checkIn` |
| 证据 | `TicketPurchased` `TicketResold` `TicketCheckedIn` `Transfer` 事件 |
