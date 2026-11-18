# FTEC5520 防黄牛票务系统 — 链上运行证据

- 生成时间：2026-11-18T10:45:59+00:00
- 网络：私有链 chainId `1337`，RPC `http://127.0.0.1:8545`
- 合约地址：`0x5182970de64BDb93357aDbCd984F6A4F0484bBB2`
- 部署交易：`0x4113911dced9e247996a0c0cc998cef78bc03b699cadf400fb0d23bb943a5106`（区块 6）

## 测试明细

| ID | 场景 | 操作账户 | 预期 | 实际 | 结果 | Tx Hash | 区块 | Gas |
|---|---|---|---|---|---|---|---|---|
| T01 | 创建活动（原价1 ETH / 限量100 / 限购2） | organizer | 成功 | 成功 | ✅ PASS | `0xb80a562471a84ec58c5287b5e61803a223f26336f1cc535af142722bbd1b4576` | 8 | 168344 |
| T01b | 创建临近演出活动（0.5 ETH / 3 天后） | organizer | 成功 | 成功 | ✅ PASS | `0x8969aba82bdb53d70f009edeeaaaf4cd3dc71bc4f6718791a683239f6146d54a` | 10 | 168356 |
| T01c | 创建预售活动（presaleActive=true） | organizer | 成功 | 成功 | ✅ PASS | `0xb0dbf7cec434bc4c6eae8093ee193eb849a4f5d39bf66396def5cc5959e021ca` | 12 | 168260 |
| T02 | 白名单批量写入 buyerA / buyerB | organizer | 成功 | 成功 | ✅ PASS | `0x52e5433985775277da5664ac3ba1d2de2b63776cd5dceb4ed1dad371dcd5076c` | 14 | 75385 |
| T03 | buyerA 在预售期购票 1 张 | buyerA | 成功 | 成功 | ✅ PASS | `0xf9fd3edfde69821a3f7ef046709e63ba9cbfd7d50d3a36d896b3e51b910e321d` | 16 | 191471 |
| T04 | attacker（非白名单）在预售期购票 | attacker | 失败 | 拒绝：Wallet is not whitelisted | ✅ PASS | `—` | — | — |
| T05a | buyerA 一级购票 1 张（活动1） | buyerA | 成功 | 成功 | ✅ PASS | `0x88720cc1a487fe8a312c5d9376b79689f9a1a5ecc78739b8f2e35940a77d609f` | 18 | 155012 |
| T05b | buyerA 再购 1 张（达限购 2） | buyerA | 成功 | 成功 | ✅ PASS | `0xf48aafd18bdfb8a44e28ee89bcb70602ab8c5c9c952ea82ad0ffb3e1bd19eef4` | 20 | 120812 |
| T05c | buyerB 一级购票 1 张（活动1） | buyerB | 成功 | 成功 | ✅ PASS | `0xed1a219d8e711418655f386fef0742158ab8437697fd821b3acb6ad5716e3d08` | 22 | 155012 |
| T06 | attacker 超额购买 3 张（限购 2） | attacker | 失败 | 拒绝：Wallet limit exceeded | ✅ PASS | `—` | — | — |
| T06b | attacker 买下唯一一张票 | attacker | 成功 | 成功 | ✅ PASS | `0xc80b8fce4d9066592cebce5fcd370a713c040722f119bcb190694be55307f01c` | 26 | 172112 |
| T06c | buyerB 在售罄后继续购买 | buyerB | 失败 | 拒绝：Not enough tickets | ✅ PASS | `—` | — | — |
| T11 | holder 直接调用 transferFrom 转票 | buyerA | 失败 | 拒绝：execution reverted（status=0） | ✅ PASS | `0xde9c1356f55d0f2c8b8ced0ebb2e4243bcc2e30ac0fba23565edcdfd1bf2fb37` | 28 | 22546 |
| T08 | buyerA 以 1.5 ETH 挂牌（原价 1 ETH） | buyerA | 失败 | 拒绝：Price exceeds dynamic limit | ✅ PASS | `—` | — | — |
| T12 | 非票主 attacker 给 token 挂牌 | attacker | 失败 | 拒绝：Not the owner | ✅ PASS | `—` | — | — |
| T09a | buyerB 买下活动2 的票 | buyerB | 成功 | 成功 | ✅ PASS | `0xe8fca4c08eb7f5bc7c7fd23397d7e01c5efcddd525479bd2f4046c75f8537213` | 30 | 155012 |
| T09 | 距演出 3 天，以 0.6 ETH 挂牌（上限 0.5） | buyerB | 失败 | 拒绝：Price exceeds dynamic limit | ✅ PASS | `—` | — | — |
| T09b | 距演出 3 天，以 0.5 ETH（=100%）挂牌 | buyerB | 成功 | 成功 | ✅ PASS | `0x36562144498543aafbbc4837ef1d0fa1bb9799694fb78b681eb68cd469a37cec` | 32 | 79734 |
| T07a | buyerA 以 1.2 ETH（=120%）挂牌 | buyerA | 成功 | 成功 | ✅ PASS | `0x3274b38cd77d8ab7ac5e891e9e29109c4d931d4f00a77bb4096d10193d6666e8` | 34 | 79891 |
| T07 | buyerB 买入转售门票 | buyerB | 成功 | 成功 | ✅ PASS | `0x5032fb9eb3ca5f934d5359377f809903f7422a35fe48a0e300656a0f3d803a35` | 36 | 110677 |
| T10 | 第 4 次挂牌（resaleCount 已达 3） | buyerB | 失败 | 拒绝：Max resale limit reached | ✅ PASS | `—` | — | — |
| T17 | attacker（未授权）执行 checkIn | attacker | 失败 | 拒绝：Not an authorized verifier | ✅ PASS | `—` | — | — |
| T13 | owner 授权 verifier | deployer | 成功 | 成功 | ✅ PASS | `0x2cf2d471890909cdb0edf2e37e8b8dbd3eaa287397543248c8494a31880fc8bb` | 46 | 47923 |
| T15 | verifier 首次核销 token | verifier | 成功 | 成功 | ✅ PASS | `0x245969f545ef3126e74b15d445e9736780d41cb00a09d480570617e88aa5fd0a` | 48 | 51851 |
| T16 | 同一张票再次核销 | verifier | 失败 | 拒绝：Ticket already used | ✅ PASS | `—` | — | — |
| T07c | attacker 为活动1买 1 张作为页面展示品 | attacker | 成功 | 成功 | ✅ PASS | `0x992ece4c0b149570a9813645b5218ba8646816feb5eb08f0120a14b8b5d17520` | 50 | 137912 |
| T07d | 该票以 1.2 ETH 挂牌（留作页面演示） | attacker | 成功 | 成功 | ✅ PASS | `0x36fb13089a3bba44928ba5f99df3170fa5771effd88269e338d1b503c4497ab9` | 52 | 79891 |

## 汇总

- 用例总数：27，通过 27，失败 0
- 最终区块高度：52
- 门票总数：7，当前在售：[6, 7]

> 说明：`pass` 的判定同时考虑预期方向——预期「失败」的用例必须真的被合约拒绝才算 PASS。