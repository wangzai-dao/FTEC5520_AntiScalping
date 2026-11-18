# Operations Runbook (RUNBOOK)

> Corresponds to the project brief "Member 1: 09 - prepare operations instructions for restarting the node, redeploying, updating the contract address and restoring the demo accounts".

## 0. The day before the demo / after every boot

```bash
cd FTEC5520_AntiScalping
./blockchain/start_node.sh        # prints the PID if it is already running
python scripts/check_chain.py     # OK once you see connected: True, the contract address and 4 events
.venv/bin/streamlit run app/app.py
```

Open http://127.0.0.1:8501 in a browser; the **Overview** page on the left and the sidebar should show `node online`, `chainId 1337` and `block N` (N keeps growing).

## 1. Three common failures

| Symptom | Cause | Handling |
|---|---|---|
| Red banner at the top of the page: `Cannot reach the private-chain node` | geth not started / crashed | `./blockchain/start_node.sh`, then `tail -50 blockchain/geth.log` to see the error |
| The page reports `No contract deployed yet` | `config/network.json` missing or the address is empty | `python backend/deploy.py` |
| Transactions stay pending and time out after 120 seconds | Mining stopped / data directory corrupted | `./blockchain/stop_node.sh`, `./blockchain/start_node.sh`; if that still fails see section 3 |

## 2. Restart only the node (keeping the on-chain data)

```bash
./blockchain/stop_node.sh
./blockchain/start_node.sh
python scripts/check_chain.py
```

The contract address in `config/network.json` **does not need changing** - the data directory `blockchain/data` is still there and the contract is still on chain.

## 3. Start over completely (chain data lost / a clean state is needed before the demo)

```bash
./blockchain/start_node.sh --reset     # deletes blockchain/data and rebuilds from the same genesis
sleep 5
python backend/deploy.py               # the contract address will change (it often stays the same because the nonce is identical)
python backend/demo_flow.py            # regenerate the demo data + results/tx_evidence.json
```

> Note: after `--reset` all events and tickets on chain disappear and the page data "becomes empty"; this is expected behaviour.
> Run `demo_flow.py` before the demo and you will have 4 events, 7 tickets and 2 listings.

## 4. Switching chains (from local geth back to the AWS private chain)

1. Edit `.env`:
   ```bash
   RPC_URL=http://127.0.0.1:8545     # still a local address when going through an SSH tunnel
   CHAIN_ID=<chainId of the AWS chain>
   PRIVATE_KEY_DEPLOYER=0x...        # replace with the private key of the account on AWS
   ...
   ```
2. `python scripts/check_chain.py` to confirm the AWS blockNumber can be read;
3. `python backend/deploy.py` - it redeploys on the new chain and overwrites `config/network.json`;
4. Restart Streamlit (`Ctrl+C`, then `streamlit run` again); the pages pick up the new address automatically.

**`config/network.json` is the single source of the contract address for the whole project**; it takes effect as soon as `deploy.py` has written it,
and no page code needs changing.

## 5. What to do if the account private keys are lost

If `.env` was deleted or you switched machines, generate a fresh set of accounts and rebuild the chain:

```bash
rm -f config/network.json                  # important: otherwise the old account addresses will override the new .env
python blockchain/init_chain.py --force    # overwrites genesis.json and .env
./blockchain/start_node.sh --reset
python backend/deploy.py
python backend/demo_flow.py
```

> `init_chain.py --force` writes a new `.env`, but `config/network.json` still holds the **previous set of account addresses**;
> when the two conflict, `network.json` wins, and the new accounts show 0 ETH in the UI. Delete it before rebuilding the chain.

`--force` replaces the addresses of all 7 accounts, so every address and Tx Hash previously recorded in the report becomes invalid;
**do not run this command after the screenshots have been taken and before the demo**.

## 6. Port conflicts

| Port | Purpose | How to change it |
|---|---|---|
| 8545 | geth RPC | `RPC_PORT=8546 ./blockchain/start_node.sh`, and change `RPC_URL` in `.env` at the same time |
| 30304 | geth P2P | `P2P_PORT=30305 ./blockchain/start_node.sh` |
| 8501 | Streamlit | `streamlit run app/app.py --server.port 8502` |

## 7. Stop everything

```bash
./blockchain/stop_node.sh
pkill -f "streamlit run app/app.py"
```
