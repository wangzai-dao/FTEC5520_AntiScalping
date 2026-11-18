# Per-Account Verification Report (based on the 7-account table from teammates)

> Generated at: 2026-11-18T19:09:46+08:00
> Chain: chainId 1337 · block 530 · contract `0x5182970de64BDb93357aDbCd984F6A4F0484bBB2`
> Automated test cases: 48 → PASS 46 / FAIL 0 / DEVIATION 2
> Account-specific checks: 17 items → PASS 16 / FAIL 0 / skipped 1

## 1. Overview

| Account | Who it is | What it does in the demo | Tests from teammates | Test cases actually covered | Failures | Account-specific checks |
|---|---|---|---|---|---|---|
| `deployer` | Platform side (the one who deploys the contract) | Contract owner; sets the verifier; collects the 5% platform fee | T19 / T24 | 1 case | 0 | 5 items / 0 failures |
| `organizer` | Organizer (the concert company) | Creates events, toggles presale, manages the whitelist, collects ticket proceeds | T01 / T02 / T20 | 1 case | 0 | 3 items / 0 failures |
| `buyerA` | Normal buyer (on the whitelist) | Buys tickets during presale, lists them on the resale market, gets scanned in at the door | T03 / T09b / T13 / T15 | 17 cases | 0 | 1 item / 0 failures |
| `buyerB` | Second normal buyer | The party taking over after a resale, verifying that NFT ownership changed | T14 / T23 | 11 cases | 0 | 2 items / 0 failures |
| `verifier` | On-site staff (verifier) | Scans the code to check the ticket in and marks the ticket as "used" | T15 / T16 | 3 cases | 0 | 3 items / 0 failures |
| `attacker` | Scalper | Deliberately breaks the rules: grabs presale tickets without being whitelisted, exceeds the per-wallet limit, resells above the cap | T04 / T06 / T08 / T10 | 12 cases | 0 | 1 item / 0 failures |
| `miner` | The block producer (authorized Clique node) | Packages one block every 2 seconds | Running in the background the whole time | 0 cases | 0 | 2 items / 0 failures |

## 2. Per-account details

### `deployer` — Platform side (the one who deploys the contract)

**Account-specific checks (real transactions sent / chain reads in this run)**

| Check | Expected | Actual | Result | tx |
|---|---|---|---|---|
| Whether contract owner() == deployer | Yes (the deployer is the owner) | 0x0b1FdF64A664Fe56b6a406A6b8523D991169D568 | PASS | — |
| Resale platform fee = 5% of the sale price | 10000000000000000 wei (5%) | 10000000000000000 wei (token 45, sale price 200000000000000000 wei) | PASS | `0x00e48b1e813c8968…` |
| withdrawPlatformFees withdraws the fee | Succeeds and the balance increases | 0.0100 ETH → balance 1000.6251 → 1000.6351 | PASS | `0x3337c2f8a70f8172…` |
| pendingPlatformFees is zero after withdrawal | 0 | 0.000000 ETH | PASS | — |
| attacker's platform-fee withdrawal is rejected (onlyOwner) | Rejected | Rejected: OwnableUnauthorizedAccount (caller is not the owner) | PASS | — |

**Test cases in the automated suite with actor = deployer**

| Case | Scenario | Expected | Result | tx |
|---|---|---|---|---|
| T15a | Contract owner authorizes a verifier | Succeeds | PASS | `0x42a2bbbcdc9032b8…` |

### `organizer` — Organizer (the concert company)

**Account-specific checks (real transactions sent / chain reads in this run)**

| Check | Expected | Actual | Result | tx |
|---|---|---|---|---|
| withdrawProceeds withdraws the ticket proceeds | Succeeds and the balance increases | 0.2000 ETH → balance 1026.4938 → 1026.6938 | PASS | `0x276772e5bcacace7…` |
| pendingProceeds is zero after withdrawal | 0 | 0.000000 ETH | PASS | — |
| attacker's proceeds withdrawal is rejected (nothing to withdraw) | Rejected: No proceeds available | Rejected: No proceeds available | PASS | — |

**Test cases in the automated suite with actor = organizer**

| Case | Scenario | Expected | Result | tx |
|---|---|---|---|---|
| T01 | Organizer creates an event (1 ETH / 10 tickets / per-wallet limit 2 / 10 days out) | Succeeds, eventId / inventory  | PASS | — |

### `buyerA` — Normal buyer (on the whitelist)

**Account-specific checks (real transactions sent / chain reads in this run)**

| Check | Expected | Actual | Result | tx |
|---|---|---|---|---|
| The current number of resale listings is readable | ≥0 listings | 2 listings: token 6@0.5ETH, token 7@1.2ETH | PASS | — |

**Test cases in the automated suite with actor = buyerA**

| Case | Scenario | Expected | Result | tx |
|---|---|---|---|---|
| T03 | A whitelisted user buys a ticket during presale | Succeeds, ownerOf updated to b | PASS | `0x6c4311a2243ec707…` |
| T05a | Buys 2 tickets in one go (equal to the per-wallet limit) | Succeeds | PASS | `0xf027c8b63471ef1f…` |
| T05b | Exceeds the per-wallet limit (already bought 2, buys 1 more) | Rejected | PASS | `0x636fba48075eaf89…` |
| T08 | Listing price exceeds the static cap (120%) | Rejected | PASS | `0x02cca066db7758df…` |
| T07a | Holder lists at the 120% cap | Succeeds | PASS | `0xf28f2d8e0feaceee…` |
| E05b | Buying a ticket whose listing was cancelled | Rejected | PASS | `0x5661454b1ec78fa6…` |
| T10a | Consecutive resales up to the 3rd time (the cap) | Succeeds, resaleCount = | PASS | — |
| T11a | Holder calls ERC-721 transferFrom directly to bypass the resale rules | Rejected | PASS | `0x07450a271dcf369f…` |
| T11b | Holder calls safeTransferFrom directly to bypass the resale rules | Rejected | PASS | `0x977baa31c33ba286…` |
| T09d | Price-cap boundary exactly 7 days before the show | Cap switches to 100%: 1.0 can be listed | PASS | `0xed6b3d2f061af989…` |
| T14c | The previous holder's QR code after a successful resale | Rejected | PASS | — |
| E02 | The ticket owner buys their own listing (wash trading) | Rejected | PASS | `0xc96add20fce234fc…` |
| E03a | A whitelisted holder lists during the presale period | Succeeds | PASS | `0xd14feb1308e0d72b…` |
| B01 | Lists directly at 2.0 ETH while bypassing the page (original price 0.6) | Rejected | PASS | `0xc637cb2f29fe8456…` |
| B02 | Calls transferFrom directly while bypassing the page to change the ticket owner | Rejected | PASS | `0xb33e2acbbfcedac5…` |
| E06a | Tickets can be bought normally before the show starts | Succeeds | PASS | `0x249c635fb9cabd7e…` |
| E06c | Listing for resale after the event has started | Rejected | PASS | `0x7b78935f0ece18d1…` |

### `buyerB` — Second normal buyer

**Account-specific checks (real transactions sent / chain reads in this run)**

| Check | Expected | Actual | Result | tx |
|---|---|---|---|---|
| ownerOf of resold token 45 matches the last Transfer | Matches | ownerOf=0xa2dE33d087… (buyerB) / Transfer 0xf15D113F→0xa2dE33d0 @block 522 | PASS | `0x00e48b1e813c8968…` |
| resaleCount of token 45 matches the number of on-chain Transfers | 1 (2 Transfers - 1 mint) | 1 | PASS | — |

**Test cases in the automated suite with actor = buyerB**

| Case | Scenario | Expected | Result | tx |
|---|---|---|---|---|
| T06a | The last ticket is bought before sell-out | Succeeds | PASS | `0x749b7cfaf83244fb…` |
| T07b | Someone else buys the resold ticket (ownership changes + count +1) | Succeeds, ownerOf changes, re | PASS | `0x9ad38878f7474aa0…` |
| E08 | The same ticket is listed twice | Rejected | PASS | `0x4cc5391941f94ec7…` |
| E05a | The ticket owner cancels the listing | Succeeds | PASS | `0x0c5298dfc03910f1…` |
| T10a | Consecutive resales up to the 3rd time (the cap) | Succeeds, resaleCount = | PASS | — |
| T10b | The 4th listing (the resale cap of 3 has been reached) | Rejected | PASS | `0x7d9dada8303e441c…` |
| T09b | Listing above the dynamic cap close to the show | Rejected | PASS | `0xad1d641d5c5525cb…` |
| T09c | Listing at exactly the cap close to the show (0.5 ETH) | Succeeds | PASS | `0xef79bdb31bb38cdd…` |
| T13 | A legitimate holder generates a short-lived QR code and has it verified | All 5 checks pass | PASS | — |
| T14b | The QR code has expired (screenshot-forwarding scenario) | Rejected | PASS | — |
| E01 | An already checked-in ticket is listed for sale again | Rejected | PASS | `0x32fedbf9129cb92c…` |

### `verifier` — On-site staff (verifier)

**Account-specific checks (real transactions sent / chain reads in this run)**

| Check | Expected | Actual | Result | tx |
|---|---|---|---|---|
| is_verifier(verifier) = true (authorized) | true | true | PASS | — |
| is_verifier(attacker) = false | false | false | PASS | — |
| is_verifier(buyerA) = false (a normal buyer cannot check tickets in) | false | false | PASS | — |

**Test cases in the automated suite with actor = verifier**

| Case | Scenario | Expected | Result | tx |
|---|---|---|---|---|
| T15b | Authorized verifier checks a ticket in for the first time | Succeeds, used = true | PASS | `0x5a601fced1e4c77e…` |
| T16 | The same ticket is checked in a second time | Rejected | PASS | `0x3d4eb57bcda21db9…` |
| E09 | Checking in a listed ticket automatically cancels the listing | Succeeds | PASS | `0x034d87abf83e68b6…` |

### `attacker` — Scalper

**Account-specific checks (real transactions sent / chain reads in this run)**

| Check | Expected | Actual | Result | tx |
|---|---|---|---|---|
| attacker has no check-in permission (precondition for T17) | false | is_verifier(attacker)=false | PASS | — |

**Test cases in the automated suite with actor = attacker**

| Case | Scenario | Expected | Result | tx |
|---|---|---|---|---|
| T02 | A non-organizer changes the ticket sales status of someone else's event | Rejected | PASS | `0xaf43cc23ecce609e…` |
| T02b | A normal account (not the platform organizer) creates an event on its own | Per the project brief: should be rejected | DEVIATION | — |
| T04 | A non-whitelisted user buys a ticket during presale | Rejected | PASS | `0x3d4f2a86dcc553b4…` |
| T06b | Buying continues after the inventory is sold out | Rejected | PASS | `0x92e2ebcd0264963b…` |
| E04 | The payment amount does not match "ticket price × quantity" | Rejected | PASS | `0xb82a9061bd5ef3d2…` |
| T12 | A non-owner lists someone else's ticket | Rejected | PASS | `0x80689950e8f2decb…` |
| T14a | The attacker forges the holder's signature | Rejected | PASS | — |
| T17 | An account without check-in permission calls checkIn | Rejected | PASS | `0xd36ecc3d811c078b…` |
| E03b | A non-whitelisted account buys a resale ticket during presale | Rejected | PASS | `0xf4cfaec28964bc0c…` |
| B03 | Calling checkIn directly while bypassing the check-in page | Rejected | PASS | `0x29c54038593b8eea…` |
| B04 | Paying the wrong amount while bypassing the page (0.1 ETH for a 0.6 ETH ticket) | Rejected | PASS | `0x9a90dcf04f12aaee…` |
| E06b | Buying continues after the event has started | Rejected | PASS | `0xdc11e98a7b904c50…` |

### `miner` — The block producer (authorized Clique node)

**Account-specific checks (real transactions sent / chain reads in this run)**

| Check | Expected | Actual | Result | tx |
|---|---|---|---|---|
| Number of new blocks within 6 seconds | ≥2 (2s/block) | 3 (blocks 523 → 526, 6.5s) | PASS | — |
| Whether the miner account is in .env / genesis | Present | Not in the test account list (only the genesis alloc has 1000 ETH) | SKIP | — |

## 3. Differences from the teammates' table (two points to align on with them)

### 1) These four ids, `T19 / T20 / T23 / T24`, do not exist in this repository

The ids in `tests/test_workflow.py` are T01–T18 + E01–E09 + B01–B04, while `backend/demo_flow.py` uses another numbering, T01–T17; neither goes beyond T18. The ids in the teammates' table probably come from the course project brief; the behaviour itself is covered, and the mapping is as follows:

| Teammate's id | Behaviour | Actual evidence in this repository |
|---|---|---|
| T19 (deployer) | Collects the 5% platform fee | The deployer section of this report: reads `TicketResold.platformFee` and checks it = sale price × 5%, then actually withdraws it |
| T20 (organizer) | Withdraws the ticket proceeds | The organizer section of this report: `withdrawProceeds` sends a real transaction, the balance increases, pending proceeds go to zero |
| T23 (buyerB) | NFT ownership changes after taking over a resale | The buyerB section of this report (`ownerOf` vs `Transfer.to`) + suite cases T07b / T10a / T18 |
| T24 (deployer) | Sets the verifier | Suite case T15a (`setVerifier`); the verifier section of this report re-checks the `is_verifier` state |

### 2) The addresses in `docs/ACCOUNTS.md` do not match the current chain (out of date)

That file records the accounts and contract address from the chain built on WSL on 2026-11-17; on this machine `blockchain/init_chain.py` has regenerated the accounts since then, so all the addresses changed. Use `config/network.json` as the reference:

| Role | `config/network.json` (current chain, use this as the reference) | `docs/ACCOUNTS.md` (old WSL chain, out of date) |
|---|---|---|
| deployer | `0x0b1FdF64A664Fe56b6a406A6b8523D991169D568` | `0xac58247eD6B94f69762b7eBce072583c1159aD7f` |
| organizer | `0xa2BB9316aAC722a3D5901B0A341bDa092517B5c6` | `0x0aF12A334a38d395117639881915E44fE5d4bBFD` |
| buyerA | `0xf15D113Fc4182919c97561331d590a0A0AaC6964` | `0xeE380Abd54DD46C88F26e21424105039198303a3` |
| buyerB | `0xa2dE33d087Fb9D0e217685dc358bf8B33cCad6B9` | `0x60D7A41a7DF950756bC63c37698d086C9d35fC19` |
| verifier | `0x4c5E3D4CaBfEE177D9f30c2C56cf537452297c5d` | `0x1FbD76615383d87B68bF9686342F3e6F2a0C2CF0` |
| attacker | `0x3f00206255641f15c56387628557092654A5fA5E` | `0xDac1050a8de63b9550D0F14ED6deA90389F2EDc2` |

> If teammates use the addresses from `ACCOUNTS.md` to check against the chain, none of them will match — the chain is not wrong, the document simply was not regenerated along with it. Either regenerate `docs/ACCOUNTS.md` once (it updates as soon as `init_chain.py` finishes), or tell everyone clearly to "use `config/network.json` as the reference".

## 4. Conclusion

**All passed**: the demo responsibilities, violation blocking and permission control for all 7 accounts were reproduced successfully on the current chain, with no FAIL cases; the 2 DEVIATION entries are differences in wording between the project brief and the implementation (noted in `results/test_evidence.json`), not defects.
