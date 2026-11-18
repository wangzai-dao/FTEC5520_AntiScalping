# Test account list (local private chain, chainId 1337)

> This file records **public addresses** only. The private keys live in `.env` at the project root (already excluded by `.gitignore`); never commit or share them.

> ⚠️ **2026-11-18: the chain was rebuilt on this machine (macOS), so both the account addresses and the contract address have changed.**
> The sections below ("generation time / 7 accounts / deployment record") **carry 2026-11-17 timestamps and belong to the old WSL chain; they are kept for historical reference**;
> **the chain that is currently running is defined by `config/network.json` and `results/account_verification.md`** (see the "Current chain" section below).

| Item | Value |
|---|---|
| Generation time | 2026-11-17 (old WSL chain) |
| Generation command | `.venv/bin/python blockchain/init_chain.py` |
| Runtime environment | WSL2 Ubuntu 22.04.5 LTS · Python 3.10.12 · Geth 1.13.15-stable · solc 0.8.20 |
| chainId | 1337 (Clique PoA, 2-second block interval) |
| RPC | http://127.0.0.1:8545 |

---

## Current chain (2026-11-18 · macOS · check addresses here)

| Role | Address | Identity |
|---|---|---|
| deployer | `0x0b1FdF64A664Fe56b6a406A6b8523D991169D568` | Platform operator (contract owner) |
| organizer | `0xa2BB9316aAC722a3D5901B0A341bDa092517B5c6` | Organizer |
| buyerA | `0xf15D113Fc4182919c97561331d590a0A0AaC6964` | Buyer A |
| buyerB | `0xa2dE33d087Fb9D0e217685dc358bf8B33cCad6B9` | Buyer B |
| verifier | `0x4c5E3D4CaBfEE177D9f30c2C56cf537452297c5d` | Verifier |
| attacker | `0x3f00206255641f15c56387628557092654A5fA5E` | Scalper |
| miner | `0x188d4F8d6cBd9147bc4a25db7080cd7d5CDa87A3` | Block-producing node (keystore unlocked by `blockchain/password.txt`) |

| Item | Value |
|---|---|
| Contract address | `0x5182970de64BDb93357aDbCd984F6A4F0484bBB2` |
| Deployment transaction | `0x4113911dced9e247996a0c0cc998cef78bc03b699cadf400fb0d23bb943a5106` (block 6) |
| Data source | `config/network.json` (written automatically by `backend/deploy.py`) |

> Every time the chain is rebuilt with `init_chain.py --force`, **this table must be updated too**, otherwise teammates checking against the old addresses will find that nothing matches.

---

## The 7 accounts (old WSL chain, 2026-11-17)

| Role | Address | Identity | Main responsibilities | Related tests |
|---|---|---|---|---|
| deployer | `0xac58247eD6B94f69762b7eBce072583c1159aD7f` | Platform operator | Deploy the contract → become the contract owner; appoint the verifier; collect the 5% platform fee | T19 / T24 |
| organizer | `0x0aF12A334a38d395117639881915E44fE5d4bBFD` | Organizer (concert promoter) | Create events, open/close the presale, maintain the whitelist, withdraw ticket proceeds | T01 / T02 / T20 |
| buyerA | `0xeE380Abd54DD46C88F26e21424105039198303a3` | Buyer A (on the whitelist) | Buy during the presale, list on the resale market, check in at the gate | T03 / T09b / T13 / T15 |
| buyerB | `0x60D7A41a7DF950756bC63c37698d086C9d35fC19` | Buyer B | The buyer on the receiving end of a resale, used to verify NFT ownership transfer | T14 / T23 |
| verifier | `0x1FbD76615383d87B68bF9686342F3e6F2a0C2CF0` | On-site staff | Scan codes for check-in and mark tickets as "used" | T15 / T16 |
| attacker | `0xDac1050a8de63b9550D0F14ED6deA90389F2EDc2` | Scalper | Deliberate violations: grabbing presale tickets without being whitelisted, buying above the limit, reselling above the cap | T04 / T06 / T08 / T10 |
| miner | `0xdC478e3dCd62762374C582774079e104B5d83E3E` | Block-producing node | Authorised Clique PoA signer, seals one block every 2 seconds | Always resident in the background |

---

## Initial balances

The `alloc` field of the genesis file `blockchain/genesis.json` allocates **1000 ETH** to each of the 7 accounts above.

This is a privilege unique to a private chain: whatever the genesis file says is exactly what the initial on-chain state is.

---

## Deployment record (snapshot of the old WSL chain, 2026-11-17; for the current chain see the top of this document)

| Item | Value |
|---|---|
| Contract address | `0x46335ea6e72DD537A5f18402b440DDdEA824cC1e` |
| Deployment transaction hash | `0x7358e6e196d6dc58da1a8a245eab966ef36cb2ff37492b9dc3b3dae257853424` |
| Deployment block number | 190 |
| Deployment gas used | 3,294,415 |
| Runtime bytecode size | 14,339 bytes (creation bytecode 15,008 bytes) |
| Owner after deployment | `0xac58247eD6B94f69762b7eBce072583c1159aD7f` (= deployer) |
| Initial contract state | `nextEventId = 1`, `nextTokenId = 1` (no events yet, no tickets yet) |

### Reproduction record on this machine (2026-11-17)

| Operation | Result | Evidence |
|---|---|---|
| `backend/demo_flow.py` | **PASS 27 / FAIL 0** | `results/tx_evidence.json`, `results/demo_report.md` |
| `transferFrom` bypass attempt forced on chain | Failed transaction, 22,558 gas actually consumed | `0xef24a9076e73961ace6c26e58609b5ee75a9e549184420f9ccf145b7e2fe3a3a` |
| organizer withdraws 5.5 ETH of ticket proceeds | Balance 999.9993 → 1005.4992, pending proceeds back to zero | `0x117771d2ce8a71f42b482a8e28daab4a9d4e9cdf198010f621254a53ffdf736a` (block 414, gas 32,388) |
| On-chain state after the demo | events 4 / tickets 7 / on sale 2 | `scripts/check_chain.py` |
| Manual demo in the UI (for screenshots) | verifier buys 2 tickets on Buy Tickets (token 8, 9); buyerA lists token 3 at 1.0 ETH; buyerB's token 4 generates a QR code and passes signature verification on Staff Check-in (not checked in) | Screenshots 03/04/05/06, tx `0x33d31905…`, `0x45ee4fd1…` |
| On-chain state when the screenshots were completed | events 4 / tickets 9 / on sale 3 (tokens 3, 6, 7) / checked in 2 (tokens 1, 8) / organizer pendingProceeds 1.0 ETH | `results/screenshots/` |

> **On the difference between the two sets of numbers**: `results/demo_report.md` is a snapshot of the moment `demo_flow.py` finished
> (7 tickets, on sale [6, 7], final block 303); the 6 screenshots were taken afterwards through manual operations in the UI
> (adding token 8 / 9 and the listing of token 3). Both are real on-chain states, just at different points in time.

---

## Notes

- Running `blockchain/init_chain.py --force` **regenerates all accounts** and wipes the chain data; this file must be updated accordingly at that point.
- Every transaction from the `attacker` account is **expected to fail**; the failure itself is evidence that the contract rules are in force, not a bug.
- An identical copy of this list lives at `~/FTEC5520_AntiScalping/docs/ACCOUNTS.md` on WSL.
