# 运行手册（RUNBOOK）

> 对应任务书「成员 1：09 准备一份重启节点、重新部署、更新合约地址、恢复演示账户的运行说明」。

## 0. 演示前一天 / 每次开机后

```bash
cd FTEC5520_AntiScalping
./blockchain/start_node.sh        # 已在跑会提示 PID
python scripts/check_chain.py     # 看到 connected: True、合约地址、4 个活动就 OK
.venv/bin/streamlit run app/app.py
```

浏览器打开 http://127.0.0.1:8501 ，左侧 **Overview** 页与侧边栏应显示 `node online`、`chainId 1337`、`block N`（N 会持续增长）。

## 1. 三种常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面顶部红字 `Cannot reach the private-chain node` | geth 没启动 / 崩了 | `./blockchain/start_node.sh`，`tail -50 blockchain/geth.log` 看报错 |
| 页面提示 `No contract deployed yet` | `config/network.json` 缺失或地址为空 | `python backend/deploy.py` |
| 交易一直 pending，120 秒超时 | 挖矿停了 / 数据目录损坏 | `./blockchain/stop_node.sh`，`./blockchain/start_node.sh`；仍不行见第 3 节 |

## 2. 只重启节点（保留链上数据）

```bash
./blockchain/stop_node.sh
./blockchain/start_node.sh
python scripts/check_chain.py
```

`config/network.json` 里的合约地址**不用改**——数据目录 `blockchain/data` 还在，合约还在链上。

## 3. 完全重来（链数据丢了 / 演示前需要干净状态）

```bash
./blockchain/start_node.sh --reset     # 删 blockchain/data，用同一份 genesis 重建
sleep 5
python backend/deploy.py               # 合约地址会变（通常因为 nonce 相同，地址往往还是同一个）
python backend/demo_flow.py            # 重新生成演示数据 + results/tx_evidence.json
```

> 注意：`--reset` 之后链上所有活动、门票都会消失，页面数据会"变空"，这是预期行为。
> 演示前跑完 `demo_flow.py` 就有 4 个活动、7 张票、2 条在售记录。

## 4. 换了链（从本机 geth 切回 AWS 私有链）

1. 修改 `.env`：
   ```bash
   RPC_URL=http://127.0.0.1:8545     # 走 SSH 隧道时仍然是本机地址
   CHAIN_ID=<AWS 链的 chainId>
   PRIVATE_KEY_DEPLOYER=0x...        # 换成 AWS 上的账户私钥
   ...
   ```
2. `python scripts/check_chain.py` 确认能读到 AWS 的 blockNumber；
3. `python backend/deploy.py` —— 会在新链上重新部署并覆盖 `config/network.json`；
4. 重启 Streamlit（`Ctrl+C` 后重新 `streamlit run`），页面会自动读新地址。

**`config/network.json` 是全项目唯一的合约地址来源**，`deploy.py` 写完就生效，
不需要改任何页面代码。

## 5. 账户私钥丢了怎么办

`.env` 被删或换了电脑，就重新生成一套账户并重建链：

```bash
rm -f config/network.json                  # 关键：否则旧账户地址会覆盖新 .env
python blockchain/init_chain.py --force    # 会覆盖 genesis.json 和 .env
./blockchain/start_node.sh --reset
python backend/deploy.py
python backend/demo_flow.py
```

> `init_chain.py --force` 会写入新的 `.env`，但 `config/network.json` 里还留着**上一套账户地址**，
> 两者冲突时以 `network.json` 为准，新账户在界面上会显示 0 ETH。先删掉它再建链。

`--force` 会换掉 7 个账户的地址，之前记录在报告里的地址、Tx Hash 全部作废，
**演示前不要在已经截图之后跑这条命令**。

## 6. 端口冲突

| 端口 | 用途 | 改法 |
|---|---|---|
| 8545 | geth RPC | `RPC_PORT=8546 ./blockchain/start_node.sh`，同时改 `.env` 的 `RPC_URL` |
| 30304 | geth P2P | `P2P_PORT=30305 ./blockchain/start_node.sh` |
| 8501 | Streamlit | `streamlit run app/app.py --server.port 8502` |

## 7. 停止一切

```bash
./blockchain/stop_node.sh
pkill -f "streamlit run app/app.py"
```
