# 逐账户核验报告（按队友给的 7 个账户表）

> 生成时间：2026-11-18T19:09:46+08:00
> 链：chainId 1337 · 区块 530 · 合约 `0x5182970de64BDb93357aDbCd984F6A4F0484bBB2`
> 自动化用例：48 条 → PASS 46 / FAIL 0 / 偏差 2
> 账户专项核验：17 项 → PASS 16 / FAIL 0 / 跳过 1

## 一、总览

| 账户 | 是谁 | 在演示里干什么 | 队友给的测试 | 实测覆盖用例 | 失败 | 账户专项核验 |
|---|---|---|---|---|---|---|
| `deployer` | 平台方（部署合约的人） | 合约 owner；设置验票员；收 5% 平台手续费 | T19 / T24 | 1 条 | 0 | 5 项 / 失败 0 |
| `organizer` | 主办方（演唱会公司） | 创建活动、开关预售、管白名单、收票款 | T01 / T02 / T20 | 1 条 | 0 | 3 项 / 失败 0 |
| `buyerA` | 正常买家（在白名单里） | 预售期买票、挂二手、被扫码入场 | T03 / T09b / T13 / T15 | 17 条 | 0 | 1 项 / 失败 0 |
| `buyerB` | 第二个正常买家 | 转售后的接盘方，验证 NFT 归属变了 | T14 / T23 | 11 条 | 0 | 2 项 / 失败 0 |
| `verifier` | 现场工作人员（验票员） | 扫码核销，把票标为「已用」 | T15 / T16 | 3 条 | 0 | 3 项 / 失败 0 |
| `attacker` | 黄牛 | 专门违规：非白名单抢预售、超限购、超价转售 | T04 / T06 / T08 / T10 | 12 条 | 0 | 1 项 / 失败 0 |
| `miner` | 出块的人（Clique 授权节点） | 每 2 秒打包一个区块 | 后台一直在跑 | 0 条 | 0 | 2 项 / 失败 0 |

## 二、逐账户明细

### `deployer` — 平台方（部署合约的人）

**账户专项核验（本次真实发交易/读链）**

| 检查项 | 预期 | 实际 | 结果 | tx |
|---|---|---|---|---|
| 合约 owner() 是否 = deployer | 是（部署者即 owner） | 0x0b1FdF64A664Fe56b6a406A6b8523D991169D568 | PASS | — |
| 转售平台费 = 售价 5% | 10000000000000000 wei（5%） | 10000000000000000 wei（token 45，售价 200000000000000000 wei） | PASS | `0x00e48b1e813c8968…` |
| withdrawPlatformFees 提取手续费 | 成功且余额增加 | 0.0100 ETH → 余额 1000.6251 → 1000.6351 | PASS | `0x3337c2f8a70f8172…` |
| 提取后 pendingPlatformFees 归零 | 0 | 0.000000 ETH | PASS | — |
| attacker 提平台费被拒（onlyOwner） | 拒绝 | 拒绝：OwnableUnauthorizedAccount（调用者不是 owner） | PASS | — |

**自动化套件里 actor = deployer 的用例**

| 用例 | 场景 | 预期 | 结果 | tx |
|---|---|---|---|---|
| T15a | 合约 owner 授权验票员 | 成功 | PASS | `0x42a2bbbcdc9032b8…` |

### `organizer` — 主办方（演唱会公司）

**账户专项核验（本次真实发交易/读链）**

| 检查项 | 预期 | 实际 | 结果 | tx |
|---|---|---|---|---|
| withdrawProceeds 提取票款 | 成功且余额增加 | 0.2000 ETH → 余额 1026.4938 → 1026.6938 | PASS | `0x276772e5bcacace7…` |
| 提取后 pendingProceeds 归零 | 0 | 0.000000 ETH | PASS | — |
| attacker 提票款被拒（无待提取额） | 拒绝：No proceeds available | 拒绝：No proceeds available | PASS | — |

**自动化套件里 actor = organizer 的用例**

| 用例 | 场景 | 预期 | 结果 | tx |
|---|---|---|---|---|
| T01 | 主办方创建活动（1 ETH / 10 张 / 限购 2 / 10 天后） | 成功，eventId / 库存  | PASS | — |

### `buyerA` — 正常买家（在白名单里）

**账户专项核验（本次真实发交易/读链）**

| 检查项 | 预期 | 实际 | 结果 | tx |
|---|---|---|---|---|
| 二手市场当前在售数量可读 | ≥0 条 | 2 条在售：token 6@0.5ETH, token 7@1.2ETH | PASS | — |

**自动化套件里 actor = buyerA 的用例**

| 用例 | 场景 | 预期 | 结果 | tx |
|---|---|---|---|---|
| T03 | 白名单用户在预售期购票 | 成功，ownerOf 更新为 b | PASS | `0x6c4311a2243ec707…` |
| T05a | 一次购买 2 张（等于限购上限） | 成功 | PASS | `0xf027c8b63471ef1f…` |
| T05b | 超过每钱包限购（已买 2 张，再买 1 张） | 拒绝 | PASS | `0x636fba48075eaf89…` |
| T08 | 挂牌价超过静态上限（120%） | 拒绝 | PASS | `0x02cca066db7758df…` |
| T07a | 持票人以 120% 上限挂牌 | 成功 | PASS | `0xf28f2d8e0feaceee…` |
| E05b | 购买已取消挂牌的门票 | 拒绝 | PASS | `0x5661454b1ec78fa6…` |
| T10a | 连续转售至第 3 次（上限） | 成功，resaleCount = | PASS | — |
| T11a | 持票人直接调用 ERC-721 transferFrom 绕过转售规则 | 拒绝 | PASS | `0x07450a271dcf369f…` |
| T11b | 持票人直接调用 safeTransferFrom 绕过转售规则 | 拒绝 | PASS | `0x977baa31c33ba286…` |
| T09d | 距演出恰好 7 天的限价边界 | 上限切到 100%：1.0 可挂 | PASS | `0xed6b3d2f061af989…` |
| T14c | 转售成功后旧票主的二维码 | 拒绝 | PASS | — |
| E02 | 票主购买自己挂牌的门票（刷单） | 拒绝 | PASS | `0xc96add20fce234fc…` |
| E03a | 白名单持票人在预售期挂牌 | 成功 | PASS | `0xd14feb1308e0d72b…` |
| B01 | 绕过页面直接以 2.0 ETH 挂牌（原价 0.6） | 拒绝 | PASS | `0xc637cb2f29fe8456…` |
| B02 | 绕过页面直接 transferFrom 改票主 | 拒绝 | PASS | `0xb33e2acbbfcedac5…` |
| E06a | 开场前可以正常购票 | 成功 | PASS | `0x249c635fb9cabd7e…` |
| E06c | 活动开始后挂牌转售 | 拒绝 | PASS | `0x7b78935f0ece18d1…` |

### `buyerB` — 第二个正常买家

**账户专项核验（本次真实发交易/读链）**

| 检查项 | 预期 | 实际 | 结果 | tx |
|---|---|---|---|---|
| 转售票 token 45 的 ownerOf 与最后一条 Transfer 一致 | 一致 | ownerOf=0xa2dE33d087…（buyerB）/ Transfer 0xf15D113F→0xa2dE33d0 @block 522 | PASS | `0x00e48b1e813c8968…` |
| token 45 的 resaleCount 与链上 Transfer 次数一致 | 1（2 条 Transfer - 铸造 1 条） | 1 | PASS | — |

**自动化套件里 actor = buyerB 的用例**

| 用例 | 场景 | 预期 | 结果 | tx |
|---|---|---|---|---|
| T06a | 售罄前最后一张被买走 | 成功 | PASS | `0x749b7cfaf83244fb…` |
| T07b | 他人买入转售门票（所有权变更 + 次数 +1） | 成功，ownerOf 改变，re | PASS | `0x9ad38878f7474aa0…` |
| E08 | 同一张票重复挂牌 | 拒绝 | PASS | `0x4cc5391941f94ec7…` |
| E05a | 票主取消挂牌 | 成功 | PASS | `0x0c5298dfc03910f1…` |
| T10a | 连续转售至第 3 次（上限） | 成功，resaleCount = | PASS | — |
| T10b | 第 4 次挂牌（已达转售次数上限 3） | 拒绝 | PASS | `0x7d9dada8303e441c…` |
| T09b | 临近演出时超过动态上限挂牌 | 拒绝 | PASS | `0xad1d641d5c5525cb…` |
| T09c | 临近演出时刚好等于上限（0.5 ETH）挂牌 | 成功 | PASS | `0xef79bdb31bb38cdd…` |
| T13 | 合法持票人生成短时二维码并验签 | 5 项检查全部通过 | PASS | — |
| T14b | 二维码已过期（截图转发场景） | 拒绝 | PASS | — |
| E01 | 已核销门票再次挂牌出售 | 拒绝 | PASS | `0x32fedbf9129cb92c…` |

### `verifier` — 现场工作人员（验票员）

**账户专项核验（本次真实发交易/读链）**

| 检查项 | 预期 | 实际 | 结果 | tx |
|---|---|---|---|---|
| is_verifier(verifier) = true（已授权） | true | true | PASS | — |
| is_verifier(attacker) = false | false | false | PASS | — |
| is_verifier(buyerA) = false（普通买家不能核销） | false | false | PASS | — |

**自动化套件里 actor = verifier 的用例**

| 用例 | 场景 | 预期 | 结果 | tx |
|---|---|---|---|---|
| T15b | 授权 verifier 首次核销 | 成功，used = true | PASS | `0x5a601fced1e4c77e…` |
| T16 | 同一张票第二次核销 | 拒绝 | PASS | `0x3d4eb57bcda21db9…` |
| E09 | 核销已挂牌门票时自动取消挂牌 | 成功 | PASS | `0x034d87abf83e68b6…` |

### `attacker` — 黄牛

**账户专项核验（本次真实发交易/读链）**

| 检查项 | 预期 | 实际 | 结果 | tx |
|---|---|---|---|---|
| attacker 无核销权限（T17 前提） | false | is_verifier(attacker)=false | PASS | — |

**自动化套件里 actor = attacker 的用例**

| 用例 | 场景 | 预期 | 结果 | tx |
|---|---|---|---|---|
| T02 | 非主办方修改他人活动售票状态 | 拒绝 | PASS | `0xaf43cc23ecce609e…` |
| T02b | 普通账户（非平台主办方）自行创建活动 | 按任务书：应被拒绝 | DEVIATION | — |
| T04 | 非白名单用户在预售期购票 | 拒绝 | PASS | `0x3d4f2a86dcc553b4…` |
| T06b | 库存售罄后继续购买 | 拒绝 | PASS | `0x92e2ebcd0264963b…` |
| E04 | 付款金额与「票价 × 数量」不一致 | 拒绝 | PASS | `0xb82a9061bd5ef3d2…` |
| T12 | 非票主给他人门票挂牌 | 拒绝 | PASS | `0x80689950e8f2decb…` |
| T14a | 攻击者伪造持票人签名 | 拒绝 | PASS | — |
| T17 | 无核销权限的账户调用 checkIn | 拒绝 | PASS | `0xd36ecc3d811c078b…` |
| E03b | 非白名单账户在预售期购买二手票 | 拒绝 | PASS | `0xf4cfaec28964bc0c…` |
| B03 | 绕过验票页面直接调用 checkIn | 拒绝 | PASS | `0x29c54038593b8eea…` |
| B04 | 绕过页面付错金额买票（0.1 ETH 买 0.6 ETH 的票） | 拒绝 | PASS | `0x9a90dcf04f12aaee…` |
| E06b | 活动开始后继续购票 | 拒绝 | PASS | `0xdc11e98a7b904c50…` |

### `miner` — 出块的人（Clique 授权节点）

**账户专项核验（本次真实发交易/读链）**

| 检查项 | 预期 | 实际 | 结果 | tx |
|---|---|---|---|---|
| 6 秒内新增区块数 | ≥2 个（2s/块） | 3 个（区块 523 → 526，6.5s） | PASS | — |
| miner 账户是否在 .env / genesis 中 | 存在 | 未在测试账户列表中（仅 genesis alloc 有 1000 ETH） | SKIP | — |

## 三、和队友那张表的差异（要跟队友对齐的两点）

### 1）`T19 / T20 / T23 / T24` 这四个编号在本仓库里不存在

`tests/test_workflow.py` 的编号是 T01–T18 + E01–E09 + B01–B04，`backend/demo_flow.py` 是 T01–T17 的另一套编号；两边都没有 T19 以后。队友那张表的编号应该来自课程任务书，行为本身是覆盖了的，对应关系如下：

| 队友的编号 | 行为 | 本仓库的实际证据 |
|---|---|---|
| T19（deployer） | 收 5% 平台手续费 | 本报告 deployer 段：读 `TicketResold.platformFee` 校验 = 售价×5%，并真实提取 |
| T20（organizer） | 提取票款 | 本报告 organizer 段：`withdrawProceeds` 真实发交易、余额增加、待提取归零 |
| T23（buyerB） | 转售接盘后 NFT 归属变化 | 本报告 buyerB 段（`ownerOf` vs `Transfer.to`）+ 套件 T07b / T10a / T18 |
| T24（deployer） | 设置验票员 | 套件 T15a（`setVerifier`），本报告 verifier 段复核 `is_verifier` 状态 |

### 2）`docs/ACCOUNTS.md` 里的地址和当前链不一致（过期）

该文件记录的是 2026-11-17 在 WSL 上那次建链的账户与合约地址；现在这台机器上`blockchain/init_chain.py` 重新生成过账户，所以地址全变了。以 `config/network.json` 为准：

| 角色 | `config/network.json`（当前链，以这个为准） | `docs/ACCOUNTS.md`（旧 WSL 链，已过期） |
|---|---|---|
| deployer | `0x0b1FdF64A664Fe56b6a406A6b8523D991169D568` | `0xac58247eD6B94f69762b7eBce072583c1159aD7f` |
| organizer | `0xa2BB9316aAC722a3D5901B0A341bDa092517B5c6` | `0x0aF12A334a38d395117639881915E44fE5d4bBFD` |
| buyerA | `0xf15D113Fc4182919c97561331d590a0A0AaC6964` | `0xeE380Abd54DD46C88F26e21424105039198303a3` |
| buyerB | `0xa2dE33d087Fb9D0e217685dc358bf8B33cCad6B9` | `0x60D7A41a7DF950756bC63c37698d086C9d35fC19` |
| verifier | `0x4c5E3D4CaBfEE177D9f30c2C56cf537452297c5d` | `0x1FbD76615383d87B68bF9686342F3e6F2a0C2CF0` |
| attacker | `0x3f00206255641f15c56387628557092654A5fA5E` | `0xDac1050a8de63b9550D0F14ED6deA90389F2EDc2` |

> 队友如果拿 `ACCOUNTS.md` 的地址去链上核对，会全部对不上——不是链错了，是文档没跟着重新生成。要么让 `docs/ACCOUNTS.md` 重新生成一次（`init_chain.py` 跑完就更新），要么明确告诉大家「以 `config/network.json` 为准」。

## 四、结论

**全部通过**：7 个账户的演示职责、违规拦截、权限控制均在当前链上复现成功，无 FAIL 用例；2 条 DEVIATION 是任务书与实现的口径差异（已在 `results/test_evidence.json` 注明），不是缺陷。
