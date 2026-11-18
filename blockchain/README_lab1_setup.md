# 成员 1：Lab 1 私有链环境与部署说明

本文件对应任务书「05｜成员 1」的 01–04、09 项：**搭链 → 验证 RPC → 准备测试账户 → 部署 → 写运行说明**。

> 老师 Lab 1 的原始材料在 `../lab1/`（`Lab_1_Exercise.pdf`、HackMD 2026 版讲义、AWS 截图）。
> 本文件记录的是**本项目实际跑通的那套配置**，以及在 AWS 实例关机后如何在本机复现同一条链。

---

## 1. 版本选择：为什么锁 Geth 1.13.15

| 版本 | 私有链（Clique / `miner.start()` + 自定义 genesis） |
|---|---|
| Geth ≤ 1.13.x | ✅ 支持 |
| Geth ≥ 1.14 | ❌ 启动即报 `Geth only supports PoS networks`，自定义 genesis 私有链无法出块 |

Lab 1 用的是「genesis.json + 解锁账户 + 挖矿」的私有链，因此本项目锁定 **1.13.15**（最后一个支持 Clique
的稳定版）。`scripts/get_geth.sh` 会自动按平台下载对应二进制到 `tools/geth`：

```bash
./scripts/get_geth.sh          # 下载到 tools/geth，已是符号链接
./tools/geth version         # Geth Version: 1.13.15-stable
```

> 如果课程环境里的 Geth 版本不同：只要它支持 `--mine` / Clique，脚本其余部分不用改；
> 若只能用 `--dev` 模式，把 `start_node.sh` 里的 `--mine ...` 换成 `--dev --dev.period 2` 即可。

## 2. 一条命令生成账户与 genesis

```bash
python blockchain/init_chain.py
```

做的事：

1. 用 `eth-account` 生成 7 个账户：`deployer / organizer / buyerA / buyerB / verifier / attacker / miner`；
2. 把它们写进 `blockchain/genesis.json` 的 `alloc`，每个 1000 ETH；
3. 把 `miner` 的地址写进 `extradata`，作为 Clique 的签名者；
4. 把 6 个业务账户的私钥写进 **`.env`**（已 gitignore，绝不进 GitHub）；
5. 生成 `blockchain/miner.key` / `miner.addr` / `password.txt` 供节点解锁矿工账户。

`genesis.json` 关键字段：

```json
{
  "config": {
    "chainId": 1337,
    "londonBlock": 0,
    "clique": { "period": 2, "epoch": 30000 }
  },
  "gasLimit": "0x1c9c380",
  "extradata": "0x<32字节0> + <矿工地址20字节> + <65字节0>",
  "alloc": { "<账户>": { "balance": "0x3635c9adc5dea00000" } }
}
```

| 参数 | 取值 | 说明 |
|---|---|---|
| chainId | 1337 | 与 `.env` 的 `CHAIN_ID` 一致，Web3.py 会校验 |
| 共识 | Clique PoA | `period=2`，每 2 秒出一个块，交易 2–4 秒确认 |
| gasLimit | 30,000,000 | 部署合约约用 3.3M，留足余量 |
| 预置余额 | 1000 ETH / 账户 | 私有链没有水龙头，测试币靠 genesis 预置 |

## 3. 启动 / 停止节点

```bash
./blockchain/start_node.sh            # 首次会自动 import 矿工私钥 + init genesis
./blockchain/start_node.sh --reset    # 清空链数据重新开始（演示前常用）
./blockchain/stop_node.sh             # 停止
```

启动参数（见 `start_node.sh`）：

```bash
geth --datadir blockchain/data \
     --networkid 1337 \
     --http --http.addr 127.0.0.1 --http.port 8545 \
     --http.api eth,net,web3,personal \
     --mine --miner.etherbase <miner> \
     --unlock <miner> --password blockchain/password.txt --allow-insecure-unlock \
     --nodiscover --port 30304 --ipcdisable
```

- `--http.addr 127.0.0.1`：**只监听本机**。在 AWS 上要远程访问时，用 SSH 隧道而不是把 8545 开到公网：
  ```bash
  ssh -i FTEC5520.pem -L 8545:127.0.0.1:8545 ubuntu@<EC2-IP>
  ```
- 日志在 `blockchain/geth.log`，PID 在 `blockchain/geth.pid`。

### 验证节点真的在出块

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}' \
  http://127.0.0.1:8545
# {"jsonrpc":"2.0","id":1,"result":"0x1a"}   ← 数值持续增长
```

```bash
python - <<'PY'
from web3 import Web3
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
print("connected:", w3.is_connected(), "chainId:", w3.eth.chain_id, "block:", w3.eth.block_number)
print("balance:", w3.from_wei(w3.eth.get_balance(w3.eth.accounts[0] if w3.eth.accounts else "0x0000000000000000000000000000000000000000"), "ether"))
PY
```

> 注意：Clique 链的 `extraData` 是 97 字节，**必须**注入 POA 中间件，否则 web3 解析区块会报错。
> 这一点已经封装在 `backend/chain.py`：
> `w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)`。

## 4. 部署合约

```bash
python backend/fetch_deps.py      # 首次：下载 OpenZeppelin 5.0.2 到 contracts/lib
python backend/compile.py         # 编译，产出 contracts/build/ConcertTicket.json（ABI + bytecode）
python backend/deploy.py          # 部署，写 config/network.json
```

`deploy.py` 会打印并落盘：

```
[deploy] 合约地址 0x46335ea6e72DD537A5f18402b440DDdEA824cC1e
[deploy] 区块 190，gas 3294415，代码 14339 bytes
[deploy] 配置已写入 config/network.json
[deploy] self-check: nextEventId=1 nextTokenId=1 owner=0xac58...
```

`config/network.json` 是**唯一**的合约地址来源，页面和接口都从这里读，换链只需改这一个文件。

## 5. 映射到任务书的要求

| 任务书要求 | 本仓库对应 |
|---|---|
| 01 按 Lab 1 配置 AWS/Linux、genesis、Geth、账户、节点启动 | 本文档 + `blockchain/init_chain.py` + `start_node.sh` |
| 02 验证节点能收测试交易并写入区块 | `scripts/check_chain.py` 与本文 RPC 验证命令 |
| 03 启用受控 HTTP RPC，Web3.py 能读 block_number / chain_id | `backend/chain.py: Chain.chain_status()` |
| 04 准备 organizer / buyerA / buyerB / verifier / attacker | `blockchain/init_chain.py`（7 个账户，含 deployer/miner） |
| 05 接收 .sol/ABI/Bytecode，部署并记录地址与哈希 | `backend/compile.py`、`backend/deploy.py`、`config/network.json` |
| 06 封装 `ticket_api.py` | `backend/ticket_api.py` |
| 07 把签名/nonce/gas/异常/回执封装在接口内部 | `backend/chain.py: Chain.send()` + `TxResult` |
| 08 与成员 4 联调 | 五个 Streamlit 页面全部走 `ticket_api` |
| 09 重启节点、重新部署、更新地址的运行说明 | `docs/RUNBOOK.md` |

## 6. 回到 AWS 私有链（实例重新开机后）

1. 启动 EC2，确认 geth 进程在跑、安全组**不要**放行 8545；
2. 本机开隧道：`ssh -i FTEC5520.pem -L 8545:127.0.0.1:8545 ubuntu@<EC2-IP>`；
3. 编辑 `.env`：`RPC_URL=http://127.0.0.1:8545`、`CHAIN_ID=<AWS 链的 chainId>`；
4. 把 AWS 上那 6 个测试账户的私钥填进 `.env`（否则代签失败）；
5. `python backend/deploy.py` 重新部署，`config/network.json` 会自动更新；
6. 重启 Streamlit。

> **安全要求（任务书原文）**：不要把 AWS 密钥或测试账户私钥传进 GitHub；不要直接把 8545 暴露到公网。
> 本仓库的 `.gitignore` 已排除 `.env`、`blockchain/miner.key`、`blockchain/data/`。
