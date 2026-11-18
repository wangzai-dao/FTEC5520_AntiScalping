# Anti-Scalping Concert Ticketing System - FTEC5520

> Geth private chain (Clique PoA) + Solidity ERC-721 + Python Web3.py + Streamlit
> This repository contains the complete delivery of **Member 1 (private chain / deployment / Python
> interface)** and **Member 4 (Streamlit pages / QR check-in)**, plus the test, report and slide
> deliverables of **Member 5**.

---

## 1. In one sentence

A ticket is an on-chain ERC-721 token. Purchasing, per-wallet limits, the resale price cap, the resale
counter and check-in are all enforced by `ConcertTicket.sol`. The Streamlit site is only a remote
control and a display: it sends transactions and reads chain state, and it **never makes a rule
decision that could bypass the contract**.

## 2. Repository layout

```text
FTEC5520_AntiScalping/
├── blockchain/                 # Member 1: private chain
│   ├── init_chain.py           #   generates 7 test accounts + genesis.json + .env
│   ├── genesis.json            #   Clique genesis (produced by init_chain.py)
│   ├── start_node.sh           #   start / rebuild with --reset
│   ├── stop_node.sh
│   └── README_lab1_setup.md    #   Lab 1 environment and deployment notes
├── contracts/                  # Members 2 and 3 (sources are not modified here)
│   ├── ConcertTicket.sol
│   ├── Helper.sol
│   ├── build/ConcertTicket.json#   build output: ABI + bytecode
│   └── lib/@openzeppelin/      #   OpenZeppelin 5.0.2 (downloaded by fetch_deps.py)
├── backend/                    # Member 1: Python interface
│   ├── compile.py              #   solc 0.8.20 build
│   ├── deploy.py               #   deploy + write config/network.json
│   ├── chain.py                #   nonce/gas/signing/receipts/exceptions -> TxResult
│   ├── ticket_api.py           #   the only interface the pages may call
│   └── demo_flow.py            #   end-to-end demo and evidence collection
├── app/                        # Member 4: Streamlit
│   ├── app.py                  #   entry point = overview page
│   ├── common.py               #   styling, sidebar navigation, account picker, tx cards
│   ├── qr_utils.py             #   QR signing / verification
│   └── pages/                  #   five further pages (1_activity ... 5_checkin)
├── tests/                      # Member 5: automated suite and charts
│   ├── test_workflow.py        #   48 cases (T01-T18 + extras + bypass tests)
│   └── make_charts.py          #   three report figures
├── report/                     # Member 5: Final Report + its generator
├── presentation/               # Member 5: defence deck + its generator
├── demo/demo_steps.md          # Member 5: live demo script
├── results/                    # evidence: csv, json, charts, screenshots
├── config/network.json         # contract address / chainId / account addresses (from deploy.py)
├── docs/                       # setup, architecture, runbook, experiment guide
├── scripts/
│   ├── bootstrap.sh            # one-command setup
│   └── check_chain.py          # connectivity self-check
└── requirements.txt
```

## 3. Quick start

### Option A - one command (new machine or after unpacking an archive)

```bash
./scripts/bootstrap.sh        # venv, dependencies, Geth, OpenZeppelin, chain, deploy, demo data
.venv/bin/streamlit run app/app.py
```

### Option B - step by step

```bash
# 0) dependencies
python -m venv .venv && .venv/bin/pip install -r requirements.txt
./scripts/get_geth.sh                 # Geth 1.13.15 (last release supporting Clique + mining)
python backend/fetch_deps.py          # OpenZeppelin 5.0.2

# 1) chain
python blockchain/init_chain.py       # accounts + genesis + .env (once)
./blockchain/start_node.sh            # start Geth

# 2) build and deploy
python backend/compile.py
python backend/deploy.py

# 3) demo data (optional, recommended before screenshots)
python backend/demo_flow.py

# 4) site
.venv/bin/streamlit run app/app.py
```

Open http://127.0.0.1:8501. Self-check: `python scripts/check_chain.py`.

> `tools/`, `contracts/bin/`, `contracts/lib/`, `.venv/` and `.env` are git-ignored; regenerate them
> with steps 0-2 on a new machine.
>
> **Verified environment:** Ubuntu 22.04 (originally via WSL2) with Python 3.10.12 and
> `streamlit==1.65.0`; also reproduced on macOS with Python 3.12. Differences from the brief's
> assumed environment (AWS EC2, chainId 5520), the reasons and the migration steps are in
> [`docs/DEPLOYMENT_NOTES.md`](docs/DEPLOYMENT_NOTES.md).
>
> **Unpacking a Windows archive on Linux:** `.sh` files lose their executable bit; run
> `chmod +x scripts/*.sh blockchain/*.sh` first, otherwise you get `Permission denied`.

## 4. Six pages (UI is in English)

| Page | What it does | Key on-chain calls |
|---|---|---|
| **Overview** | chain status, contract address, balances, recent ticket transfers | `chainId` `blockNumber` `Transfer` logs |
| **Events** | create events, toggle sale/presale, batch whitelist, settle proceeds | `createEvent` `setEventActive` `setPresaleActive` `setWhitelistBatch` `withdrawProceeds` `withdrawPlatformFees` |
| **Buy Tickets** | on-chain `canPurchase` pre-check -> purchase -> echo tx and `ownerOf` | `canPurchase` `purchaseTickets` `ownerOf` |
| **My Tickets** | holdings, owner, resale count, used flag, signed QR | `ownerOf` `tickets` `getMaxResalePrice` |
| **Resale Market** | listings, list (including a deliberately rejected over-price), buy, cancel | `listForResale` `buyResale` `cancelListing` |
| **Staff Check-in** | verify signature -> cross-check the chain -> check in / duplicate fails | `verifiers` `checkIn` |

Screenshots live in `results/screenshots/` (`01_overview.png` ... `06_staff_checkin.png`).

## 5. Where each rule lives

| Rule | Contract implementation | UI behaviour |
|---|---|---|
| Per-wallet limit | `purchasedByWallet[eventId][wallet]` | shows `Wallet limit exceeded` when exceeded |
| Stock cap | `concert.sold + quantity <= maxSupply` | remaining tickets shown live |
| Presale whitelist | `whitelist[eventId][account]` | non-whitelisted purchases rejected |
| Dynamic price cap | `getMaxResalePrice`: >7 days 120%, <=7 days 100% | listing page shows the live cap; the over-price button demonstrates rejection |
| Resale count <= 3 | `ticket.resaleCount < 3` | My Tickets shows `2/3` |
| No direct transfer | `transferFrom` / `safeTransferFrom` overridden to revert | demo script T11 produces a real status=0 transaction |
| One-time check-in | `ticket.used` | a second check-in reverts with `Ticket already used` |
| Verifier permission | `verifiers[msg.sender]` | unauthorised accounts revert |

## 6. Evidence files

- `results/tx_evidence.json` - 27 operations with `tx_hash / block / gas / result`, including the deployment;
- `results/demo_report.md` - the same evidence as a readable table, ready for the Final Report;
- `results/test_results.csv` - the 48 test cases of Member 5 with expected/actual/verdict;
- `results/test_evidence.json` - full test evidence, environment snapshot and summary;
- `results/charts/*.png` - the three figures used in the report and the slides;
- `results/screenshots/` - six page screenshots (purchase page with a real successful transaction,
  check-in page with the full verification and check-in result).

Regenerate:

```bash
./blockchain/start_node.sh --reset && sleep 5
python backend/deploy.py && python backend/demo_flow.py
python tests/test_workflow.py && python tests/make_charts.py
python report/build_report.py && python presentation/build_pptx.py
.venv/bin/streamlit run app/app.py
```

## 7. Security and limitations

- `.env` holds six test private keys, **only for the classroom demo on a local private chain**; it is
  git-ignored and must never be pushed;
- the "current account" on the pages is actually signed server-side with those test keys. A real
  product must sign with the user's own wallet;
- the RPC listens on `127.0.0.1` only; remote demos use an SSH tunnel instead of exposing 8545;
- on-chain rules cannot stop "one person, many wallets" or off-chain cash top-ups; the report states
  this explicitly;
- contract issues and suggestions are in `docs/CONTRACT_REVIEW_FOR_MEMBER3.md` (the contract source is
  not modified in this repository).

## 8. Mapping to the brief

| Brief item | Deliverable |
|---|---|
| Member 1-01..04 chain, RPC, accounts | `blockchain/`, `.env`, `genesis.json` |
| Member 1-05 deploy and record address/hash | `backend/deploy.py`, `config/network.json` |
| Member 1-06 wrap `ticket_api.py` | `backend/ticket_api.py` (six core functions plus helpers) |
| Member 1-07 wrap signing/nonce/gas/exceptions/receipts | `backend/chain.py` `TxResult` |
| Member 1-08 integration with Member 4 | all six pages go through `ticket_api` |
| Member 1-09 restart/redeploy notes | `docs/RUNBOOK.md` |
| Member 4-01..08 five pages plus QR | `app/pages/*`, `app/qr_utils.py`, screenshots |

---

## 9. Member 5 deliverables: testing, data aggregation, report and slides

The 9 items of the brief (section 07) and where they live:

| Deliverable | Description |
|---|---|
| `tests/test_workflow.py` | 48 cases: all of T01-T18 from the brief, 12 extra cases and the B01-B04 front-end bypass tests; repeatable (each case creates its own event) |
| `tests/make_charts.py` | the three report figures (outcomes by module, gas comparison, coverage and cost of rejected calls) |
| `results/test_results.csv` | full table: expected/actual/PASS-FAIL/tx_hash/block/gas/revert reason/screenshot/kind |
| `results/test_evidence.json` | complete evidence, environment snapshot, summary and the T18 sub-steps |
| `results/gas_data.csv`, `results/chart_data.json` | raw data behind the figures |
| `results/charts/*.png` | Figures 1-3 |
| `report/final_report.docx` | Final Report (all five modules, 48 test rows, 3 figures, limitations, conclusion) |
| `presentation/final_presentation.pptx` | defence deck (15 slides) |
| `demo/demo_steps.md` | live demo: seven actions, fallback plan, pre-demo checklist |
| `docs/EXPERIMENT_GUIDE.md` | experiment guide: setup, clean-run protocol, judging rules, troubleshooting |

**One clean reproduction (about 6 minutes)**

```bash
bash blockchain/start_node.sh --reset && sleep 3
.venv/bin/python backend/deploy.py
.venv/bin/python backend/demo_flow.py      # Member 1: 27 demo operations
.venv/bin/python tests/test_workflow.py    # Member 5: 48 test cases
.venv/bin/python tests/make_charts.py      # three figures
```

Result of this run: **48 cases, PASS 46 / FAIL 0 / 2 deviations, pass rate 100%**; 24 transactions
were rejected by the contract and still mined (`status=0`, 782,049 gas in total).

**Problems found while testing**

| Problem | Handling |
|---|---|
| After re-running `init_chain.py`, `config/network.json` kept the old addresses, producing "insufficient funds" or "whitelist not applying" | Fixed in `backend/config.py`: addresses are derived from the private keys |
| `getMaxResalePrice` underflows and reverts after the event starts (E07) | Documented; Member 3 should check the timestamp first, the UI already guards it |
| `createEvent` has no access control, so any address can create an event (T02b) | Documented as a spec deviation; recommend approval or staking in production |

> The page screenshots are Member 4's archive from the previous deployment; on-chain data in this
> report is evidenced by the transaction hashes in the appendices (stated in report sections 4.4 and 5).
