# Report Material (one page each for Member 1 / Member 4)

> Written for Member 5 to consolidate directly. All figures come from real runs in this repository and can be checked against `results/tx_evidence.json`.

---

## 1. Member 1: Private Chain, Deployment and the Web3.py Interface

**Goal**: make the contract actually run on chain and wrap every call into a reusable, observable Python function.

**What was done**

1. Built a Clique PoA private chain with Geth 1.13.15 (chainId 1337, 2-second block time),
   with genesis pre-funding 7 accounts with 1000 ETH each; the miner account is written into `extradata` and unlocked by the node so it produces blocks automatically.
2. Compiled the `ConcertTicket.sol` delivered by Members 2 and 3 (solc 0.8.20, `evmVersion=paris` to avoid PUSH0),
   producing ABI / Bytecode; the deployment transaction used **gas 3,294,415**, and the contract code is 14,339 bytes.
3. Wrote `backend/ticket_api.py`: pages call only business functions (`buy_ticket` / `list_ticket` / `buy_resale` / `check_in` …),
   while nonce handling, `maxFeePerGas = baseFee×2 + 1 gwei`, local signing, waiting for the receipt and turning exceptions into text are all handled centrally inside it.
4. All write operations return the same structure:

   ```python
   TxResult(ok, function, tx_hash, block_number, gas_used, status, error)
   ```

   On failure `error` is the contract's revert reason (`Price exceeds dynamic limit` and so on),
   and **a failed pre-check sends no transaction and costs no gas** — the revert is already caught at the `estimate_gas` stage.

**Key design decisions**

- **Pre-check first, send the transaction second**: `canPurchase` / `estimate_gas` show users "why they cannot buy" right on the page,
  avoiding transactions that are bound to fail yet still cost gas.
- **There is only one source of addresses**: `config/network.json`. Switching chains only requires changing the RPC and chainId; after a redeployment the pages follow automatically,
  with no page code changes needed.
- **POA middleware**: a Clique block's `extraData` is 97 bytes; without injecting `ExtraDataToPOAMiddleware`,
  Web3.py errors out when parsing blocks — this is the biggest implementation difference between a private chain and mainnet.

**Verifiable evidence**

| Item | Value |
|---|---|
| Deployment transaction | `results/tx_evidence.json` → `network.deploy_tx` |
| 27 test cases | 27 PASS / 0 FAIL (`results/demo_report.md`) |
| Typical gas | createEvent 168,332; purchaseTickets 155,012; listForResale 79,891; buyResale 110,677; checkIn 51,851 |
| Rejected direct transfer transaction | `transferFrom` goes on chain but **status=0**, gas 22,558 |

---

## 2. Member 4: Streamlit Pages and the Signed QR Code

**Goal**: turn on-chain capabilities into an operable website where every number on a page can be traced back to one contract read.

**Six pages**

| Page (English UI label) | Key implementation |
|---|---|
| Overview | Chain status, balances of the 6 accounts, recent Transfer logs (scanned from the deployment block to the latest) |
| Events | `createEvent` form + events table + ticket sales/presale toggles + batch whitelist + proceeds settlement (`withdrawProceeds` / `withdrawPlatformFees`) |
| Buy Tickets | `canPurchase` pre-check → `purchaseTickets` → read back `ownerOf` for comparison; plus two "must-fail" demo buttons |
| My Tickets | Holdings rebuilt from Transfer events (the contract has no ERC721Enumerable), every `tickets()` field displayed, QR code generated |
| Resale Market | Active listings table + dynamic cap + list/cancel/buy, and an over-price button that demonstrates rejection by the contract on the spot |
| Staff Check-in | Signature verification → on-chain cross-check → `checkIn`, including the contrast cases of duplicate check-in and unauthorized check-in |

**Why the QR code is not a bare tokenId**

Anyone can screenshot and forward a bare tokenId. The QR code here is a JSON payload:

```json
{"v":1,"token_id":4,"holder":"0x60D7…fC19","nonce":"a3482ceee5b4c5af",
 "issued_at":1794921616,"expires_at":1794921796,"sig":"0x…"}
```

`sig` is an EIP-191 signature made with the ticket holder's private key over canonical text. The verifying side performs 5 checks:

1. Ticket version 2. The address recovered from the signature == `holder` 3. Not expired (180 seconds by default)
4. `holder == ownerOf(tokenId)` 5. On-chain `used == false`

A forwarded screenshot fails check 3 (expiry); after a resale the previous holder fails check 4;
a repeated entry fails check 5 — the three attack surfaces are each covered by a different check instead of being judged from a single tokenId.

**Why on-chain state must be read with Web3.py**

If the pages kept "who owns this ticket and whether it has been checked in" in a local database, then editing the database, logging in as someone else,
or even tweaking the frontend parameters would bypass every rule; on-chain state is the single source of truth shared by everyone and guarded by the contract's `require` statements.
The page's role here is merely to "read `ownerOf` and display it"; the value it reads is exactly the value anyone else reads,
and it does not depend on whether the server is trustworthy.

**The "failure paths" deliberately kept on the pages**

All four categories of operation — over-price listing, duplicate check-in, unauthorized check-in and direct NFT transfer — have a button/script on the pages that triggers them on the spot,
and what you see after clicking is the revert reason returned by the contract. That is more convincing than merely saying "we added restrictions":
the restriction comes from the chain, not from the UI hiding a button.

**Limitations (state these honestly in the report)**

- In the classroom demo the Python backend holds the test private keys and signs on the users' behalf; a real product must be signed by the user's wallet;
- On-chain rules cannot prevent one person using multiple wallets or paying the difference in cash offline;
- The private chain produces blocks from a single node and does not have mainnet's censorship resistance or degree of decentralization.
