# 成员 5 实验手册：从零跑通并产出真实测试数据

> 适用对象：负责「测试、数据总汇、Report 与 PPT」的成员 5。
> 本手册里的每一条命令都在 macOS (arm64) 上实际执行过，结果见 `results/`。
> 总原则：**报告里的每个数字都必须来自一次真实运行**，任何"预期结果"都不能当成"已通过"。

---

## 0. 你的任务边界

| 任务书 §07 的 9 件事 | 本仓库对应产物 |
|---|---|
| 01 建测试清单与统一模板 | `tests/test_workflow.py`（表头即模板）、`results/test_results.csv` |
| 02 收集 ABI / 规则 / 成功异常场景 | `contracts/build/ConcertTicket.json`、`docs/EXPERIMENT_GUIDE.md` §4 |
| 03 联调后从 Python 跑完整流程 | `tests/test_workflow.py::test_end_to_end`（T18） |
| 04 收集 tx_hash / 区块 / Gas | `results/test_evidence.json`、`results/test_results.csv`、`results/gas_data.csv` |
| 05 统计通过率与覆盖 | `results/test_evidence.json → summary` |
| 06 至少两张图 | `results/charts/01…`、`02…`、`03…` |
| 07 "为什么必须用区块链" + 局限 | `report/final_report.docx` 第 7、8 章（B01–B04 是实证） |
| 08 收齐成员 1–4 的 1–2 页说明 | `docs/REPORT_MATERIAL.md`（成员 1、4）、两个 GitHub 仓库 README（成员 2、3） |
| 09 统一 PPT 与彩排 | `presentation/final_presentation.pptx`、`demo/demo_steps.md` |

**不要替成员 1–4 写他们各自的代码与技术章节**，你的工作是：把他们的产物跑起来、测出来、记下来、讲清楚。

---

## 1. 环境准备（一次性，约 10 分钟）

### 1.1 已验证的环境

| 组件 | 版本 / 说明 |
|---|---|
| OS | macOS 26.6.2 (arm64) —— 原项目在 Ubuntu 22.04 / WSL2 上跑通，本机同样可复现 |
| 私有链 | Geth **1.13.15**（最后一个支持 Clique PoA + `--mine` 的版本，1.14+ 只支持 PoS） |
| 编译器 | solc **0.8.20**（`evmVersion=paris`，不用 PUSH0），arm64 机器通过 Rosetta 运行 amd64 版 |
| Python | **3.12**（venv 在 `.venv/`） |
| 依赖 | `web3==8.0.0`、`eth-account`、`streamlit==1.65.0`、`qrcode`、`matplotlib`（画图用，任务书未列） |
| 链参数 | `chainId=1337`、Clique 2 秒出块、7 个测试账户各 1000 ETH |

### 1.2 一次性安装

```bash
cd FTEC5520_AntiScalping

# ① 脚本可执行位（从 Windows 压缩包解出来会丢）
chmod +x scripts/*.sh blockchain/*.sh

# ② 下载 Geth 1.13.15（约 40 MB，装到 tools/geth）
bash scripts/get_geth.sh

# ③ Python 虚拟环境 + 依赖
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install matplotlib          # 只有画图需要，任务书没列

# ④ 编译合约依赖（OpenZeppelin 5.0.2）
.venv/bin/python backend/fetch_deps.py
```

> **踩坑记录 1（Python）**：如果你用某个"带签名/加固运行时"的 Python（例如某些 App 内置的解释器），
> `pip install` 后 import `web3` 会报
> `Cannot load native module 'Crypto.Util._cpuid_c' … different Team IDs`。
> 这是 macOS 的库校验拦截了 pip 装的原生扩展，**换一个普通 Python（brew / miniforge / python.org）建 venv 即可**。
>
> **踩坑记录 2（solc）**：`backend/compile.py` 在 Darwin arm64 上会下载 `macosx-amd64` 版 solc，
> 需要 Rosetta（`arch -x86_64 true` 能跑就行）。

### 1.3 建链与部署（只在第一次或换链时做）

```bash
.venv/bin/python blockchain/init_chain.py     # 生成 7 个账户 + genesis.json + .env（含私钥，已 gitignore）
bash blockchain/start_node.sh                 # 启动 Geth（RPC 127.0.0.1:8545）
.venv/bin/python backend/compile.py           # 编译 → contracts/build/*.json（ABI + bytecode）
.venv/bin/python backend/deploy.py            # 部署 → config/network.json（地址/区块/部署哈希）
python scripts/check_chain.py                 # 自检：chainId、区块、合约、余额
```

`.env` 与 `config/network.json` 的关系：**私钥在 `.env`，合约地址在 `network.json`**。
重跑 `init_chain.py --force` 后必须删掉旧的 `config/network.json` 再 `deploy.py`，
否则会出现"用新私钥签名、却以为自己是旧地址"的假失败（详见 §9 故障 3，本仓库已修复 `backend/config.py`）。

---

## 2. 每次实验的固定流程（干净复现，约 6 分钟）

实验报告的数据必须来自**同一条链、同一个合约地址**的一次连续运行。固定按这个顺序：

```bash
cd FTEC5520_AntiScalping

# 第 1 步：清空链数据并重启节点（区块从 0 开始，报告里的区块号才连得起来）
bash blockchain/start_node.sh --reset
sleep 3

# 第 2 步：重新部署合约（记录新的合约地址 / 部署哈希 / 部署 gas）
.venv/bin/python backend/deploy.py

# 第 3 步：跑成员 1 的演示脚本（27 条操作，产出 results/tx_evidence.json）
.venv/bin/python backend/demo_flow.py

# 第 4 步：跑成员 5 的测试套件（T01–T18 + 扩展用例，产出 results/test_results.csv）
.venv/bin/python tests/test_workflow.py

# 第 5 步：出图（读上面两个 CSV，产出 results/charts/*.png）
.venv/bin/python tests/make_charts.py
```

每步的"成功长什么样"：

| 步骤 | 预期输出 |
|---|---|
| 第 1 步 | `[node] RPC 就绪（PID …）`；`blockchain/geth.log` 里每 2 秒出现一行 `Commit new sealing work` |
| 第 2 步 | `[deploy] 合约地址 0x…`、`gas 3294415`、`self-check: nextEventId=1 nextTokenId=1` |
| 第 3 步 | 末尾 `共 27 条，PASS 27，FAIL 0` |
| 第 4 步 | 末尾 `用例 N 条：PASS … / FAIL 0 / 偏差 …`，以及各操作 gas 中位数 |
| 第 5 步 | 三张 PNG + `results/chart_data.json` |

> 第 3 步与第 4 步都会新建活动，互不冲突（每步都用新的 eventId）。**顺序不要反**：
> 先演示后测试，演示脚本里"第 4 次挂牌被拒"依赖的是它自己刚建的票。

只跑测试、不重建链也可以（合约已部署时），此时区块号会接在历史后面，报告里注明"第 N 轮"即可。

---

## 3. 只想看某个模块时怎么办

`tests/test_workflow.py` 的 `main()` 里 7 个函数就是 7 个模块，注释掉不需要的即可：

| 函数 | 覆盖 |
|---|---|
| `test_primary_market()` | T01–T06、E04（成员 2 的一级市场规则） |
| `test_anti_scalping()` | T07–T12、E01/E02/E05/E08（成员 3 的限价与转售） |
| `test_qr_and_checkin()` | T13–T17、E01/E09（成员 4 的二维码 + 成员 3 的核销） |
| `test_presale_resale_whitelist()` | E03（预售期二手市场的白名单） |
| `test_bypass_frontend()` | B01–B04（**绕过网站**直打合约，答辩重点） |
| `test_end_to_end()` | T18（7 个动作的完整流程） |
| `test_time_rules()` | E06/E07（活动开始后停止售卖；`getMaxResalePrice` 的下溢缺陷） |

注意：`T15` 之前必须先有 `setVerifier`；`T13–T17` 依赖 `test_qr_and_checkin()` 内部的授权步骤，因此不要单独只跑后半段。

---

## 4. 测试矩阵：任务书的 18 项 → 脚本里的用例

| 任务书 | 本仓库用例 ID | 场景 | 预期 | 证据 |
|---|---|---|---|---|
| T01 | T01 | 主办方建活动（1 ETH / 10 张 / 限购 2） | 成功，字段可读 | tx + `concertEvents` 回读 |
| T02 | T02 / **T02b** | 非主办方改活动状态 / 建活动 | 拒绝 / **偏差** | `Not event manager`；T02b 见 §8 |
| T03 | T03 | 白名单用户预售期购票 | 成功，`ownerOf` 更新 | tx + `ownerOf` |
| T04 | T04 | 非白名单预售期购票 | 拒绝 | `Wallet is not whitelisted` + status=0 回执 |
| T05 | T05a / T05b | 买到上限 2 张 / 再买 1 张 | 成功 / 拒绝 | `Wallet limit exceeded` |
| T06 | T06a / T06b | 买最后一张 / 售罄后再买 | 成功 / 拒绝 | `Not enough tickets` |
| T07 | T07a / T07b | 120% 挂牌 / 他人买入 | 成功，`ownerOf` 变、次数 +1 | tx + `tickets()` |
| T08 | T08 / T08b | 1.3 ETH 超价 / 读上限 | 拒绝 / 返回 1.2 ETH | `Price exceeds dynamic limit` |
| T09 | T09a–T09d | 3 天内 100% 上限、恰好 7 天边界 | 拒绝 / 允许 | 两组对照 |
| T10 | T10a / T10b | 转满 3 次 / 第 4 次挂牌 | 成功 / 拒绝 | `Max resale limit reached` |
| T11 | T11a / T11b / B02 | 直调 `transferFrom` / `safeTransferFrom` | 拒绝（status=0） | 真实失败交易 + gas |
| T12 | T12 | 非票主挂牌 | 拒绝 | `Not the owner` |
| T13 | T13 | 合法 QR + 验签 | 5 项检查全过 | payload + 逐项结果 |
| T14 | T14a / T14b / T14c | 伪签 / 过期 / 旧票主 | 全部拒绝 | 三项各自失败的检查项 |
| T15 | T15a / T15b | 授权验票员 / 首次核销 | 成功，`used=true` | tx |
| T16 | T16 | 二次核销 | 拒绝 | `Ticket already used` |
| T17 | T17 / B03 | 未授权核销 | 拒绝 | `Not an authorized verifier` |
| T18 | T18 | 创建→购票→转售→入场 | 7 步全对 | 7 条 tx 汇总 |

扩展用例（写进报告的"额外覆盖"）：`E01` 已核销再挂牌、`E02` 自买自卖、`E03` 预售期二手白名单、
`E04`/`B04` 付款金额错误、`E05` 取消挂牌后购买、`E06` 活动开始后购票/挂牌、`E07` 限价函数下溢、
`E08` 重复挂牌、`E09` 核销自动撤销挂牌、`B01` 绕过页面超价挂牌。

---

## 5. 判定口径（别把 PASS/FAIL 搞反）

1. **正向用例**：交易成功 **且** 链上状态断言成立 → PASS。
   例：T07b 不只看 `ok=True`，还要 `ownerOf == buyerB`、`resaleCount == 1`、平台费 = 0.06 ETH。
2. **负向用例**：交易必须被拒绝，**并且** revert 原因命中预期字符串 → PASS。
   `T08`（超价）被拒绝才是 PASS；如果超价挂牌成功，才是 FAIL。
3. **偏差（DEVIATION）**：合约实际行为与任务书假设不同，但不是 bug。例如 T02b——合约允许任何地址创建活动。
   这类不要算进通过率分母，单独列一节说明。
4. 每条负向用例都留两种证据：
   - **预检路径**：`estimate_gas` 直接捕获 revert，不发交易、不花 gas（页面上就是这么提示用户的）；
   - **强制上链路径**：固定 gas 发交易，拿到 `status=0` 的真实回执——**证明规则来自合约，而不是来自我们的脚本**。

---

## 6. 证据产物：哪个文件对应报告哪一节

| 文件 | 内容 | 用在 |
|---|---|---|
| `results/test_results.csv` | 每条用例：ID / 模块 / 场景 / 输入 / 预期 / 实际 / PASS-FAIL / tx / 区块 / gas / revert 原因 / 截图 | 报告第 5 章测试表 |
| `results/test_evidence.json` | 同上 + 环境快照 + 汇总统计 + T18 的 7 个子步骤 | 报告数据来源、答辩备用 |
| `results/gas_data.csv` | 每次成功 / 失败交易的 gas | 图 2、图 3-b |
| `results/test_environment.json` | 链 / 合约 / 编译器 / 账户 / 余额 | 报告第 4 章环境表 |
| `results/charts/01…png` | 各模块 PASS/偏差/FAIL | 报告图 1、PPT |
| `results/charts/02…png` | 关键操作 gas 对比 | 报告图 2、PPT |
| `results/charts/03…png` | 正常/异常覆盖 + 失败交易的 gas 成本 | 报告图 3 |
| `results/tx_evidence.json`、`demo_report.md` | 成员 1 的 27 条演示证据 | 报告第 3 章、附录 |
| `results/screenshots/*.png` | 成员 4 的 6 张页面截图 | 报告第 3 章、PPT |

> 截图是成员 4 在**上一轮部署**时手工截的，合约地址与本轮不同。
> 报告里必须写"截图为历史留档，链上数据以附录哈希为准"，不要假装是同一轮。

---

## 7. 数据汇总要算哪几个数

```bash
.venv/bin/python - <<'EOF'
import json
d = json.load(open("results/test_evidence.json"))
s = d["summary"]
print("用例总数", s["total_cases"], "PASS", s["pass"], "FAIL", s["fail"],
      "偏差", s["deviation"], "通过率", s["pass_rate"], "%")
print("正常路径", s["normal_cases"], "异常路径", s["negative_cases"])
print("真实失败交易", s["on_chain_failed_txs"], "笔，gas 合计", s["on_chain_failed_gas_total"])
for m, v in s["by_module"].items():
    print(f"{m:<14} 共 {v['total']:>2} 条  PASS {v['PASS']:>2}  偏差 {v['DEVIATION']}")
print("区块区间", d["environment"]["contract"]["deploy_block"], "→", s["final_block"])
EOF
```

报告里建议给出的 4 个汇总量：

1. **通过率** = PASS ÷ (PASS + FAIL)，偏差单独说明（本仓库为 100%，偏差 2 条）；
2. **覆盖** = 正常路径 vs 异常路径的条数，以及 T01–T18 是否全覆盖；
3. **Gas** = createEvent / purchaseTickets(1,2) / listForResale / buyResale / checkIn 的中位数；
4. **失败成本** = status=0 的交易笔数与 gas——这是"为什么规则要放在链上"的成本论据。

---

## 8. 报告与 PPT 的组织顺序

**报告（`report/final_report.docx`）**：摘要 → 问题与目标 → 系统设计 → 各成员模块实现 →
测试方法与环境 → 测试结果（表 + 3 张图） → 链上数据分析 → 为什么必须用区块链 → 局限 → 结论 → 附录（哈希、复现命令）。

**PPT（`presentation/final_presentation.pptx`，12–15 页）**：
封面 → 问题 → 方案架构 → 规则落点 → 角色与流程 → 测试方法 → 测试结果图 → Gas 图 →
绕过前端对抗演示（B01–B04）→ 局限 → 结论 → 现场 Demo 步骤。

**现场 Demo（`demo/demo_steps.md`）**：7 个动作固定顺序，每步都准备好"成功"与"失败"两种截图，
节点挂了就切到 `results/screenshots/` + `results/demo_report.md` 的备用证据。

---

## 9. 故障排查速查表

| 现象 | 原因 | 处理 |
|---|---|---|
| `连不上节点 http://127.0.0.1:8545` | 节点没起 / 端口被占 | `bash blockchain/start_node.sh`；`lsof -i :8545` |
| `尚未部署合约` | 没有 `config/network.json` | `.venv/bin/python backend/deploy.py` |
| 交易一直 pending，120s 超时 | 矿工没解锁 / 没在出块 | 看 `blockchain/geth.log`；`bash blockchain/start_node.sh --reset` |
| `insufficient funds for gas * price + value`（地址余额 0） | `network.json` 里的地址与 `.env` 私钥不匹配 | 删 `config/network.json` 重新 `deploy.py`（`backend/config.py` 已修为以私钥推导地址为准） |
| `Wallet is not whitelisted` 但 `canPurchase` 说可以 | 同上：`msg.sender` 与白名单地址不是同一个 | 同上 |
| `Cannot load native module 'Crypto…'` | Python 加固运行时拦截原生扩展 | 换普通 Python 建 venv |
| `solc: Bad CPU type in executable` | 没有 Rosetta | `softwareupdate --install-rosetta` |
| `Permission denied` 跑 `.sh` | 压缩包丢了可执行位 | `chmod +x scripts/*.sh blockchain/*.sh` |
| 图上中文变方块 | matplotlib 没注册中文字体 | `tests/make_charts.py` 会自动找 `Arial Unicode.ttf`；找不到就手动指定 `font.family` |
| `init_chain.py` 拒绝执行 | `.env` / `genesis.json` 已存在 | 确需重建加 `--force`（会清空链数据） |

---

## 10. 提交前检查清单

- [ ] `.env`、`blockchain/data/`、`blockchain/miner.key`、`.venv/`、`contracts/lib/`、`tools/` 都不在 Git 里（见 `.gitignore`）
- [ ] `results/test_results.csv`、`results/test_evidence.json`、`results/charts/*.png` 是**同一次运行**的产物
- [ ] 报告里的每个 tx_hash 都能在 `results/test_evidence.json` 里搜到
- [ ] 报告、PPT、Demo 用的是同一个合约地址与同一批数字
- [ ] 失败用例没有被改写成"通过"；偏差（T02b、E07）在报告里如实说明
- [ ] 截图与链上数据的"不同轮次"已在报告中标注
