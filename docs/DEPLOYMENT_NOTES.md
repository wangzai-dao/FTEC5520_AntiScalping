# Deployment and Runtime Environment Notes

> This document describes the **runtime environment actually used by this project** and the **differences from the project brief together with the reasons for them**, and provides an **executable plan for migrating to AWS EC2**.
> The purpose is to state the "environment baseline" clearly, so that nothing fails to line up during review.

---

## 1. Actual Runtime Environment

| Item | Actual value | Notes |
|---|---|---|
| Host | Personal laptop (Windows 11) | See the difference notes in Section 2 |
| Runtime platform | **WSL2 + Ubuntu 22.04.5 LTS** | Full Linux user space, not an emulation layer |
| Python | 3.10.12 | Shipped with Ubuntu 22.04 |
| Ethereum client | **Geth 1.13.15-stable** (commit c5ba367e, Go 1.21.6, linux/amd64) | The last version that supports a Clique PoA private chain |
| Contract compiler | solc **0.8.20** (commit a1b79de6), `evmVersion=paris`, optimizer runs=200 | Fetched automatically by `backend/compile.py` |
| Dependencies | web3.py 8.0.0, streamlit 1.65.0, eth-account ≥0.13, qrcode ≥7.4 | See `requirements.txt` |
| Chain type | Private chain, consensus **Clique PoA**, block period 2 seconds | |
| chainId | **1337** | Conventional value for local development chains |
| RPC endpoint | `http://127.0.0.1:8545` (loopback only) | Not exposed externally |
| Smart contract | `ConcertTicket`, Solidity 0.8.20, depends on OpenZeppelin 5.0.2 | See `docs/ACCOUNTS.md` |

For the one-command reproduction path see `docs/RUNBOOK.md`; for accounts and deployment records see `docs/ACCOUNTS.md`.

---

## 2. Differences from the Project Brief and Their Reasons

| # | Item | Project brief | Actual choice | Reason | Actual impact on functionality |
|---|---|---|---|---|---|
| 1 | Host machine | AWS EC2 | Local WSL2 Ubuntu 22.04 | The private chain only communicates over the loopback interface on the local machine, so a public deployment would add no extra functional verification value; AWS accounts and billing were inconvenient during the course | **None.** Both are Linux user space, with the same Geth binary, the same startup scripts and the same genesis. The migration steps are in Section 3, and no code changes are required throughout |
| 2 | chainId | 5520 (early plan) | **1337** | 1337 is the conventional value for Ethereum local development chains and avoids conflicts with mainnet / public testnets | None. chainId is only used for signature replay-protection domain separation; the value itself does not affect contract logic |
| 3 | streamlit version | 1.67.0 in `requirements.txt` | **1.65.0** | 1.67.0 requires `Python >= 3.11`; Ubuntu 22.04 ships Python 3.10.12 by default, so pip **aborts the entire installation** because a single version requirement is unmet | **None.** The APIs used by the pages (`st.rerun` / `st.page_link` / `st.metric(help=)` / `st.divider`) have been available since 1.31 |
| 4 | Automatic solc download | Official `binaries.soliditylang.org` | The same source, but usable only after **two defects were fixed** | ① The site is fronted by Cloudflare, which blocks Python's default UA and returns `403 Forbidden`; ② the `releases` keys in that site's `list.json` are **plain semantic versions** (`"0.8.20"`), so the original implementation, which matched on `"0.8.20+commit..."`, threw `StopIteration` | None. After the fix, **a fresh clone compiles with a single command**, and manual solc downloads are no longer needed |

> Note: Items 3 and 4 are **engineering robustness fixes**, committed to `backend/compile.py` and `requirements.txt`, and verified on the local machine by "deleting the cached compiler and recompiling".

---

## 3. Executable Plan for Migrating to AWS EC2

### 3.1 Target Architecture

```
Local browser ──localhost:8501──┐
                                ├─ SSH tunnel ─→ EC2 (Ubuntu 22.04)
Local browser ──localhost:8545──┘              ├─ Streamlit :8501
                                              ├─ Geth RPC :8545 (loopback only)
                                              └─ Clique private chain chainId 1337
```

**Key point: neither 8545 nor 8501 is opened to the public internet**; both are always accessed through SSH port forwarding. Exposing the RPC port publicly is equivalent to handing an unlocked block-signing account to anyone.

### 3.2 Instance and Network Configuration

| Item | Recommended value |
|---|---|
| AMI | Ubuntu Server 22.04 LTS (HVM), SSD Volume Type |
| Instance type | `t3.small` (2 vCPU / 2 GiB) is sufficient; `t3.micro` may run out of memory when compiling the contract |
| Storage | 20 GiB gp3 |
| Security group inbound | **SSH 22 only**, with the source restricted to your own public IP |
| Security group inbound | **Do not open** 8545, 8501, 30303 |
| Outbound | Allow all by default (needed to download geth and solc) |

### 3.3 Deployment Steps

```bash
# 1) Log in
ssh -i <key.pem> ubuntu@<EC2_PUBLIC_IP>

# 2) System dependencies
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git

# 3) Get the code (choose one)
git clone <repo-url> ~/FTEC5520_AntiScalping
# or upload from local (exclude large directories such as .venv / blockchain/data / tools)
#   scp -i <key.pem> -r ./FTEC5520_AntiScalping ubuntu@<IP>:~/

# 4) Follow the RUNBOOK
cd ~/FTEC5520_AntiScalping
chmod +x scripts/*.sh blockchain/*.sh
rm -f config/network.json          # clear the address list left over from another machine
python3 -m venv .venv && .venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
./scripts/get_geth.sh && ./tools/geth version    # must be 1.13.15-stable
.venv/bin/python backend/fetch_deps.py
.venv/bin/python blockchain/init_chain.py
./blockchain/start_node.sh
.venv/bin/python backend/compile.py
.venv/bin/python backend/deploy.py
.venv/bin/python backend/demo_flow.py            # expect PASS 27 / FAIL 0
```

### 3.4 Frontend Access (SSH Tunnel)

```bash
# Run on the local machine to map the two cloud ports to local ports
ssh -i <key.pem> -N \
    -L 8501:127.0.0.1:8501 \
    -L 8545:127.0.0.1:8545 \
    ubuntu@<EC2_PUBLIC_IP>
```

Open another SSH session and start the frontend:

```bash
cd ~/FTEC5520_AntiScalping && .venv/bin/streamlit run app/app.py
```

Then open `http://localhost:8501` in the local browser; keep `rpc_url` in `config/network.json` **as `http://127.0.0.1:8545` unchanged** (because the tunnel has already mapped it to the cloud).

### 3.5 Two Migration Approaches

| Approach | Procedure | Result | When it applies |
|---|---|---|---|
| **A. Fresh initialization** | On EC2, run `init_chain.py` → `start_node.sh` → `deploy.py` → `demo_flow.py` directly | Generates 7 **new** accounts and a new contract address; `docs/ACCOUNTS.md` and `results/` must be regenerated | First cloud verification, when a clean environment is wanted |
| **B. Migrate existing chain data** | Copy the local `.env`, `blockchain/genesis.json`, `blockchain/miner.key`, `blockchain/miner.addr`, `blockchain/password.txt` and `blockchain/data/` to the same paths on EC2, then run `start_node.sh` directly | **Accounts and contract address stay completely unchanged**, and historical transactions and evidence remain valid | Defense demos that need a continuous evidence chain |

> Approach B requires the same Geth version on both ends (both 1.13.15-stable). `.env` contains private keys, so it must be transferred with `scp`/`rsync` over SSH and **must not** be committed to the repository.

### 3.6 Cost (Reference Prices, 2026)

| Item | Unit price | 2-hour demo |
|---|---|---|
| t3.small on-demand | About $0.0208 / hour | About $0.04 |
| EBS gp3 20 GiB | About $1.60 / month (prorated hourly) | About $0.004 |
| Data transfer | Internal network / tunnel traffic is not billed | ≈ 0 |
| **Total** | | **Under $0.05** |

After the demo, `stop the instance` (not terminate it); the EBS volume is retained and can be used again next time.

### 3.7 Security Considerations

1. **Never expose 8545 to the public internet.** Geth is started with `--unlock` and `--allow-insecure-unlock`, so once the port is exposed it is equivalent to handing over the block-signing private key.
2. **`.env`, `miner.key` and `password.txt` must not be committed.** They are already excluded in `.gitignore`; please confirm again before uploading.
3. Restrict the security group's SSH source address to your own IP; do not use `0.0.0.0/0`.
4. The private keys of the demo private chain have teaching value only, but they still must not be made public.
5. After the demo, you can run `sudo shutdown -h now` and stop the instance.

---

## 4. Evidence Baseline Statement

To prevent the screenshots, transaction records and citations in this document from being inconsistent with one another, the following is stated:

| Evidence | Source | Identifier |
|---|---|---|
| `results/tx_evidence.json`, `results/demo_report.md` | The same run (produced by `backend/demo_flow.py`) | Contract address: see `config/network.json` |
| `results/screenshots/01–06` | Screenshots of the Streamlit pages on the same chain | The contract address shown at the bottom of the page's left sidebar matches the row above |
| The 7 accounts and deployment records in `docs/ACCOUNTS.md` | The same chain (produced by `init_chain.py` / `deploy.py`) | Consistent with `config/network.json` |

**How to verify**: the bottom of the page's left sidebar shows `≈ 0x....`, which should equal `contract_address` in `config/network.json`; if it does not, the screenshots came from another chain, and `config/network.json` and `docs/ACCOUNTS.md` are authoritative.
