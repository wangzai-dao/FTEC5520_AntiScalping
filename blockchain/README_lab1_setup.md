# Member 1: Lab 1 Private Chain Environment and Deployment Notes

This document covers items 01–04 and 09 of "05 | Member 1" in the project brief: **set up the chain → verify RPC → prepare test accounts → deploy → write the run instructions**.

> The instructor's original Lab 1 material is in `../lab1/` (`Lab_1_Exercise.pdf`, the HackMD 2026 handout, AWS screenshots).
> This file documents **the exact configuration this project actually ran**, and how to reproduce the same chain locally after the AWS instance is shut down.

---

## 1. Version choice: why Geth is pinned to 1.13.15

| Version | Private chain (Clique / `miner.start()` + custom genesis) |
|---|---|
| Geth ≤ 1.13.x | ✅ Supported |
| Geth ≥ 1.14 | ❌ Fails at startup with `Geth only supports PoS networks`; a private chain with a custom genesis cannot produce blocks |

Lab 1 uses a private chain built from "genesis.json + unlocked accounts + mining", so this project pins **1.13.15** (the last stable release
that supports Clique). `scripts/get_geth.sh` automatically downloads the matching binary for your platform into `tools/geth`:

```bash
./scripts/get_geth.sh          # Downloads into tools/geth, which is already a symlink
./tools/geth version         # Geth Version: 1.13.15-stable
```

> If the course environment has a different Geth version: as long as it supports `--mine` / Clique, the rest of the scripts need no changes;
> if only `--dev` mode is available, just replace `--mine ...` in `start_node.sh` with `--dev --dev.period 2`.

## 2. Generating accounts and genesis with one command

```bash
python blockchain/init_chain.py
```

What it does:

1. Uses `eth-account` to generate 7 accounts: `deployer / organizer / buyerA / buyerB / verifier / attacker / miner`;
2. Writes them into `alloc` in `blockchain/genesis.json`, 1000 ETH each;
3. Writes the `miner` address into `extradata` as the Clique signer;
4. Writes the private keys of the 6 business accounts into **`.env`** (already gitignored, never committed to GitHub);
5. Generates `blockchain/miner.key` / `miner.addr` / `password.txt` so the node can unlock the miner account.

Key fields of `genesis.json`:

```json
{
  "config": {
    "chainId": 1337,
    "londonBlock": 0,
    "clique": { "period": 2, "epoch": 30000 }
  },
  "gasLimit": "0x1c9c380",
  "extradata": "0x<32 bytes of zero> + <miner address, 20 bytes> + <65 bytes of zero>",
  "alloc": { "<account>": { "balance": "0x3635c9adc5dea00000" } }
}
```

| Parameter | Value | Notes |
|---|---|---|
| chainId | 1337 | Matches `CHAIN_ID` in `.env`; Web3.py validates it |
| Consensus | Clique PoA | `period=2`, one block every 2 seconds, transactions confirm in 2–4 seconds |
| gasLimit | 30,000,000 | Deployment uses about 3.3M, leaving ample headroom |
| Pre-funded balance | 1000 ETH / account | The private chain has no faucet, so test coins are pre-funded in genesis |

## 3. Starting / stopping the node

```bash
./blockchain/start_node.sh            # On first run it automatically imports the miner key + inits genesis
./blockchain/start_node.sh --reset    # Wipes the chain data and starts over (common before a demo)
./blockchain/stop_node.sh             # Stops the node
```

Startup arguments (see `start_node.sh`):

```bash
geth --datadir blockchain/data \
     --networkid 1337 \
     --http --http.addr 127.0.0.1 --http.port 8545 \
     --http.api eth,net,web3,personal \
     --mine --miner.etherbase <miner> \
     --unlock <miner> --password blockchain/password.txt --allow-insecure-unlock \
     --nodiscover --port 30304 --ipcdisable
```

- `--http.addr 127.0.0.1`: **listens on the local machine only**. For remote access on AWS, use an SSH tunnel instead of opening 8545 to the public internet:
  ```bash
  ssh -i FTEC5520.pem -L 8545:127.0.0.1:8545 ubuntu@<EC2-IP>
  ```
- Logs are in `blockchain/geth.log`, the PID in `blockchain/geth.pid`.

### Verifying that the node really is producing blocks

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}' \
  http://127.0.0.1:8545
# {"jsonrpc":"2.0","id":1,"result":"0x1a"}   ← the value keeps increasing
```

```bash
python - <<'PY'
from web3 import Web3
w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))
print("connected:", w3.is_connected(), "chainId:", w3.eth.chain_id, "block:", w3.eth.block_number)
print("balance:", w3.from_wei(w3.eth.get_balance(w3.eth.accounts[0] if w3.eth.accounts else "0x0000000000000000000000000000000000000000"), "ether"))
PY
```

> Note: a Clique chain's `extraData` is 97 bytes, so the POA middleware **must** be injected, otherwise web3 errors out when parsing blocks.
> This is already wrapped in `backend/chain.py`:
> `w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)`.

## 4. Deploying the contract

```bash
python backend/fetch_deps.py      # First run: downloads OpenZeppelin 5.0.2 into contracts/lib
python backend/compile.py         # Compiles and produces contracts/build/ConcertTicket.json (ABI + bytecode)
python backend/deploy.py          # Deploys and writes config/network.json
```

`deploy.py` prints and persists:

```
[deploy] contract address 0x46335ea6e72DD537A5f18402b440DDdEA824cC1e
[deploy] block 190, gas 3294415, code 14339 bytes
[deploy] config written to config/network.json
[deploy] self-check: nextEventId=1 nextTokenId=1 owner=0xac58...
```

`config/network.json` is the **only** source of the contract address; both the pages and the API read it from there, so switching chains requires changing just this one file.

## 5. Mapping to the project brief requirements

| Project brief requirement | Where it lives in this repository |
|---|---|
| 01 Configure AWS/Linux, genesis, Geth, accounts and node startup per Lab 1 | This document + `blockchain/init_chain.py` + `start_node.sh` |
| 02 Verify the node accepts test transactions and writes them into blocks | `scripts/check_chain.py` and the RPC verification commands in this document |
| 03 Enable controlled HTTP RPC so Web3.py can read block_number / chain_id | `backend/chain.py: Chain.chain_status()` |
| 04 Prepare organizer / buyerA / buyerB / verifier / attacker | `blockchain/init_chain.py` (7 accounts, including deployer/miner) |
| 05 Receive the .sol/ABI/Bytecode, deploy, and record the address and hash | `backend/compile.py`, `backend/deploy.py`, `config/network.json` |
| 06 Wrap `ticket_api.py` | `backend/ticket_api.py` |
| 07 Encapsulate signing/nonce/gas/exceptions/receipts inside the API | `backend/chain.py: Chain.send()` + `TxResult` |
| 08 Integrate with Member 4 | All five Streamlit pages go through `ticket_api` |
| 09 Run instructions for restarting the node, redeploying and updating the address | `docs/RUNBOOK.md` |

## 6. Returning to the AWS private chain (after the instance is started again)

1. Start the EC2 instance, confirm the geth process is running, and make sure the security group does **not** allow 8545;
2. Open a tunnel from the local machine: `ssh -i FTEC5520.pem -L 8545:127.0.0.1:8545 ubuntu@<EC2-IP>`;
3. Edit `.env`: `RPC_URL=http://127.0.0.1:8545`, `CHAIN_ID=<chainId of the AWS chain>`;
4. Put the private keys of those 6 test accounts on AWS into `.env` (otherwise the delegated signing fails);
5. Run `python backend/deploy.py` to redeploy; `config/network.json` updates automatically;
6. Restart Streamlit.

> **Security requirements (quoted from the project brief)**: do not push AWS credentials or test account private keys to GitHub; do not expose 8545 directly to the public internet.
> This repository's `.gitignore` already excludes `.env`, `blockchain/miner.key` and `blockchain/data/`.
