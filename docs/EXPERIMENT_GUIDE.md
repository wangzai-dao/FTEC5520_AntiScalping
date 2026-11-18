# Member 5 experiment guide: from zero to real test data

> Audience: the member responsible for testing, data aggregation, the report and the slides.
> Every command below was executed on macOS (arm64) and the outputs live in `results/`.
> Rule of thumb: **every number in the report must come from one real run**. Never promote an
> "expected result" into a "passed result".

---

## 0. Your scope

| Item from the brief (section 07) | Artifact in this repository |
|---|---|
| 01 Test list and one template | `tests/test_workflow.py` (its header is the template), `results/test_results.csv` |
| 02 Collect ABI, rules, success/failure scenarios | `contracts/build/ConcertTicket.json`, this guide section 4 |
| 03 End-to-end flow from Python after integration | `tests/test_workflow.py::test_end_to_end` (T18) |
| 04 Collect tx_hash / block / gas | `results/test_evidence.json`, `results/test_results.csv`, `results/gas_data.csv` |
| 05 Pass rate and coverage statistics | `results/test_evidence.json -> summary` |
| 06 At least two charts | `results/charts/01...`, `02...`, `03...` |
| 07 "Why blockchain" argument and limitations | `report/final_report.docx` chapters 7 and 8 (B01-B04 is the evidence) |
| 08 Collect 1-2 pages from Members 1-4 | `docs/REPORT_MATERIAL.md` (Members 1 and 4), the two GitHub repos (Members 2 and 3) |
| 09 Unified slides and rehearsal | `presentation/final_presentation.pptx`, `demo/demo_steps.md` |

**Do not write the other members' code or technical chapters.** Your job is to make their artifacts
run, measure them, record them and explain them.

---

## 1. Environment setup (once, about 10 minutes)

### 1.1 Verified environment

| Component | Version / notes |
|---|---|
| OS | macOS 26.6.2 (arm64). The original project was built on Ubuntu 22.04 / WSL2; both work |
| Chain | Geth **1.13.15** - the last release that still supports Clique PoA with `--mine` (1.14+ is PoS only) |
| Compiler | solc **0.8.20** (`evmVersion=paris`, no PUSH0); on arm64 the amd64 build runs under Rosetta |
| Python | **3.12** in `.venv/` |
| Packages | `web3==8.0.0`, `eth-account`, `streamlit==1.65.0`, `qrcode`, `matplotlib` (charts; not in the brief) |
| Chain parameters | `chainId=1337`, Clique 2 s blocks, seven test accounts with 1000 ETH each |

### 1.2 One-time installation

```bash
cd FTEC5520_AntiScalping

# 1) executable bits (lost when a zip is unpacked on Windows)
chmod +x scripts/*.sh blockchain/*.sh

# 2) Geth 1.13.15 (about 40 MB, installed into tools/geth)
bash scripts/get_geth.sh

# 3) Python virtual environment and dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install matplotlib          # charts only; not required by the brief

# 4) Solidity dependency (OpenZeppelin 5.0.2)
.venv/bin/python backend/fetch_deps.py
```

> **Pitfall 1 (Python).** If your Python is a hardened/signed build (for example the interpreter
> embedded in some apps), importing `web3` after `pip install` fails with
> `Cannot load native module 'Crypto.Util._cpuid_c' ... different Team IDs`. That is macOS library
> validation rejecting pip's native extension. **Create the venv with a normal Python**
> (Homebrew, miniforge or python.org).
>
> **Pitfall 2 (solc).** On Darwin arm64, `backend/compile.py` downloads the `macosx-amd64` solc, which
> needs Rosetta (`arch -x86_64 true` must work).

### 1.3 Chain and deployment (first run, or after switching chains)

```bash
.venv/bin/python blockchain/init_chain.py     # 7 accounts + genesis.json + .env (ignored by git)
bash blockchain/start_node.sh                 # start Geth (RPC 127.0.0.1:8545)
.venv/bin/python backend/compile.py           # compile -> contracts/build/*.json (ABI + bytecode)
.venv/bin/python backend/deploy.py            # deploy -> config/network.json (address, block, tx)
python scripts/check_chain.py                 # self-check: chainId, block, contract, balances
```

Relationship between the files: **private keys live in `.env`, the contract address in
`config/network.json`**. After `init_chain.py --force` you must delete the old
`config/network.json` and redeploy, otherwise transactions are signed with the new keys while the
code still believes the old addresses existed (see pitfall 3 in section 9; this repository now
derives addresses from the keys, so the failure is fixed).

---

## 2. The fixed sequence for every experiment (clean run, about 6 minutes)

Report data must come from **one chain and one contract address** in a single continuous run:

```bash
cd FTEC5520_AntiScalping

# step 1: wipe chain data and restart the node (blocks start at 0 again)
bash blockchain/start_node.sh --reset
sleep 3

# step 2: deploy (record the new address / deploy hash / deploy gas)
.venv/bin/python backend/deploy.py

# step 3: Member 1's demo script (27 operations -> results/tx_evidence.json)
.venv/bin/python backend/demo_flow.py

# step 4: Member 5's suite (T01-T18 + extras -> results/test_results.csv)
.venv/bin/python tests/test_workflow.py

# step 5: charts (reads the two CSVs, writes results/charts/*.png)
.venv/bin/python tests/make_charts.py
```

What success looks like:

| Step | Expected output |
|---|---|
| 1 | `[node] RPC ready (PID ...)`; `blockchain/geth.log` shows a sealed block every 2 seconds |
| 2 | `[deploy] contract address 0x...`, `gas 3294415`, `self-check: nextEventId=1 nextTokenId=1` |
| 3 | `27 operations, PASS 27, FAIL 0` |
| 4 | `48 cases: PASS 46 / FAIL 0 / DEVIATION 2, pass rate 100.0%` plus per-operation gas medians |
| 5 | three PNG files plus `results/chart_data.json` |

> Steps 3 and 4 both create events but never collide (each creates new event ids). **Keep the order**:
> the demo script's "fourth listing is rejected" depends on the ticket it just created.

You can also run only the suite on an already deployed contract; block numbers then continue from the
previous run, so state in the report that it is "run N".

---

## 3. Running a single module

The seven functions in `main()` of `tests/test_workflow.py` are the seven modules; comment out the
ones you do not need:

| Function | Coverage |
|---|---|
| `test_primary_market()` | T01-T06, E04 (Member 2's primary-market rules) |
| `test_anti_scalping()` | T07-T12, E01/E02/E05/E08 (Member 3's price cap and resale) |
| `test_qr_and_checkin()` | T13-T17, E01/E09 (Member 4's QR plus Member 3's check-in) |
| `test_presale_resale_whitelist()` | E03 (whitelist on the resale market during presale) |
| `test_bypass_frontend()` | B01-B04 (**bypass the website**, the key demo evidence) |
| `test_end_to_end()` | T18 (the seven-action flow) |
| `test_time_rules()` | E06/E07 (sales stop at event time; the `getMaxResalePrice` underflow) |

Note that `T15` needs `setVerifier` first, and the check-in cases depend on the authorisation step
inside `test_qr_and_checkin()`, so do not run only the second half.

---

## 4. Test matrix: the 18 scenarios of the brief mapped to cases

| Brief | Case ids | Scenario | Expected | Evidence |
|---|---|---|---|---|
| T01 | T01 | Organizer creates an event (1 ETH / 10 tickets / limit 2) | success, fields readable | tx + `concertEvents` read-back |
| T02 | T02 / **T02b** | Non-organizer changes an event / any account creates one | rejected / **deviation** | `Not event manager`; see section 8 |
| T03 | T03 | Whitelisted wallet buys in presale | success, `ownerOf` updated | tx + `ownerOf` |
| T04 | T04 | Non-whitelisted wallet buys in presale | rejected | `Wallet is not whitelisted` + status=0 receipt |
| T05 | T05a / T05b | Buy to the limit / one more | success / rejected | `Wallet limit exceeded` |
| T06 | T06a / T06b | Buy the last ticket / buy after sell-out | success / rejected | `Not enough tickets` |
| T07 | T07a / T07b | List at 120% / another wallet buys | success, owner changes, counter +1 | tx + `tickets()` |
| T08 | T08 / T08b | 1.3 ETH over-price / read the cap | rejected / returns 1.2 ETH | `Price exceeds dynamic limit` |
| T09 | T09a-T09d | 100% cap inside 7 days, exact 7-day boundary | rejected / allowed | paired cases |
| T10 | T10a / T10b | Three resales / fourth listing | success / rejected | `Max resale limit reached` |
| T11 | T11a / T11b / B02 | Direct `transferFrom` / `safeTransferFrom` | rejected (status=0) | real failed tx plus gas |
| T12 | T12 | Non-owner lists a ticket | rejected | `Not the owner` |
| T13 | T13 | Valid QR and five checks | all checks pass | payload plus per-check results |
| T14 | T14a / T14b / T14c | Forged / expired / previous-owner QR | all rejected | the failing check in each case |
| T15 | T15a / T15b | Authorise verifier / first check-in | success, `used=true` | tx |
| T16 | T16 | Second check-in | rejected | `Ticket already used` |
| T17 | T17 / B03 | Unauthorised check-in | rejected | `Not an authorized verifier` |
| T18 | T18 | Create -> buy -> resell -> enter | all seven steps correct | seven transactions |

Extra cases (quote them as "additional coverage"): `E01` re-listing a used ticket, `E02`
self-dealing, `E03` whitelist on resale during presale, `E04`/`B04` wrong payment amount, `E05`
buying a cancelled listing, `E06` purchase and listing after the event starts, `E07` the price-cap
underflow, `E08` duplicate listing, `E09` check-in clearing a listing, `B01` over-priced listing sent
straight from Web3.py.

---

## 5. Judging rules (do not invert PASS and FAIL)

1. **Positive case:** the transaction succeeds **and** the on-chain assertions hold. T07b, for
   example, also requires `ownerOf == buyerB`, `resaleCount == 1` and a 0.06 ETH platform fee.
2. **Negative case:** the call must be rejected **and** the revert reason must match the expected
   string. T08 (over-pricing) is a PASS when rejected; it would be a FAIL if the listing succeeded.
3. **Deviation:** the contract behaves differently from an assumption in the brief but it is not a
   bug, for example T02b where anyone may create an event. Do not count deviations in the pass-rate
   denominator; give them their own section.
4. Every negative case keeps two pieces of evidence:
   - **pre-check**: `estimate_gas` catches the revert, no transaction, no gas (this is what the UI shows);
   - **forced on-chain**: a fixed-gas transaction that yields a status=0 receipt, proving the
     rejection came from the contract and that gas was charged.

---

## 6. Evidence files and where they are used

| File | Content | Used in |
|---|---|---|
| `results/test_results.csv` | per case: id / module / scenario / input / expected / actual / PASS-FAIL / tx / block / gas / revert reason / screenshot | report chapter 5 |
| `results/test_evidence.json` | the same plus environment, summary and the T18 sub-steps | report data source, demo fallback |
| `results/gas_data.csv` | gas of every successful and rejected transaction | Figure 2, Figure 3-b |
| `results/test_environment.json` | chain / contract / compiler / accounts / balances | report chapter 4 |
| `results/charts/01...png` | PASS/FAIL by module | report Figure 1, slides |
| `results/charts/02...png` | gas comparison | report Figure 2, slides |
| `results/charts/03...png` | coverage plus cost of rejected calls | report Figure 3 |
| `results/tx_evidence.json`, `demo_report.md` | Member 1's 27 demo operations | report chapter 3, appendix |
| `results/screenshots/*.png` | Member 4's six page screenshots | report chapter 3, slides |

> The screenshots were taken by Member 4 during the **previous** deployment, so the contract address
> differs. The report must say "screenshots are an earlier archive; on-chain data is evidence for
> this run" instead of pretending they are the same run.

---

## 7. The four numbers to aggregate

```bash
.venv/bin/python - <<'EOF'
import json
d = json.load(open("results/test_evidence.json"))
s = d["summary"]
print("cases", s["total_cases"], "PASS", s["pass"], "FAIL", s["fail"],
      "deviation", s["deviation"], "pass rate", s["pass_rate"], "%")
print("normal", s["normal_cases"], "negative", s["negative_cases"])
print("failed txs", s["on_chain_failed_txs"], "gas", s["on_chain_failed_gas_total"])
for m, v in s["by_module"].items():
    print(f"{m:<16} cases {v['total']:>2}  PASS {v['PASS']:>2}  deviation {v['DEVIATION']}")
print("blocks", d["environment"]["contract"]["deploy_block"], "->", s["final_block"])
EOF
```

Report these four:

1. **Pass rate** = PASS / (PASS + FAIL), with deviations explained separately (100% here, 2 deviations);
2. **Coverage** = normal vs negative counts, and whether T01-T18 is fully covered;
3. **Gas** = medians for createEvent / purchaseTickets(1, 2) / listForResale / buyResale / checkIn;
4. **Cost of failure** = number of status=0 transactions and their gas - the cost argument for
   putting rules on chain.

---

## 8. Report and slide structure

**Report (`report/final_report.docx`):** abstract, problem and goals, system design, module
implementation, test method and environment, results (table plus three figures), analysis of on-chain
data, why the rules must live on chain, limitations, conclusion, appendices (hashes, commands).

**Slides (`presentation/final_presentation.pptx`, 12-15 pages):** cover, problem, architecture, where
each rule lives, roles and flow, test method, results figure, gas figure, front-end bypass evidence,
limitations, conclusion, live demo steps.

**Live demo (`demo/demo_steps.md`):** seven actions in a fixed order, each with a success and a
failure variant; if the node fails, switch to `results/screenshots/` and `results/demo_report.md`.

Regenerate the report and slides from the same data with:

```bash
python report/build_report.py
python presentation/build_pptx.py
```

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `cannot connect to http://127.0.0.1:8545` | node not started / port taken | `bash blockchain/start_node.sh`; `lsof -i :8545` |
| `contract not deployed` | no `config/network.json` | `.venv/bin/python backend/deploy.py` |
| transaction pending, 120 s timeout | signer not unlocked / not mining | check `blockchain/geth.log`; `start_node.sh --reset` |
| `insufficient funds for gas * price + value` (balance 0) | addresses in `network.json` do not match the keys in `.env` | delete `config/network.json` and redeploy (now auto-corrected by `backend/config.py`) |
| `Wallet is not whitelisted` although `canPurchase` allows it | same address/key mismatch as above | same fix |
| `Cannot load native module 'Crypto...'` | hardened Python blocks native extensions | rebuild the venv with a normal Python |
| `solc: Bad CPU type in executable` | Rosetta missing | `softwareupdate --install-rosetta` |
| `Permission denied` running `.sh` | executable bit lost | `chmod +x scripts/*.sh blockchain/*.sh` |
| text shows as boxes in charts | no suitable font registered | `tests/make_charts.py` looks for Arial Unicode automatically |
| `init_chain.py` refuses to run | `.env` or `genesis.json` exists | use `--force` only if you intend to wipe chain data |

---

## 10. Pre-submission checklist

- [ ] `.env`, `blockchain/data/`, `blockchain/miner.key`, `.venv/`, `contracts/lib/`, `tools/` are not in git
- [ ] `results/test_results.csv`, `results/test_evidence.json` and `results/charts/*.png` come from the same run
- [ ] every tx_hash quoted in the report can be found in `results/test_evidence.json`
- [ ] the report, the slides and the demo use the same contract address and the same numbers
- [ ] no failed case was rewritten as a pass; deviations (T02b, E07) are explained honestly
- [ ] the "screenshots come from an earlier deployment" note is present
