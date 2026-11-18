# Demo script (the parts owned by Member 1 + Member 4)

> Corresponds to the "7 actions of the final demo" in the project brief. All page addresses are at http://127.0.0.1:8501 .
> Run this before the demo: `./blockchain/start_node.sh && python backend/demo_flow.py && streamlit run app/app.py`.
> **The UI has already been switched to English**, so the button names in the table below are the English labels shown in quotes.

| # | Action | Page | How to click | What you see on screen |
|---|---|---|---|---|
| 1 | Organizer creates an event and issues NFT tickets | "Events" | Select the `organizer` account, enter name / 1 ETH / 100 tickets / 10 days from now / per-wallet limit 2 → "Create event on-chain" | Green transaction card: tx hash, block number, Gas; a new row appears in the `Existing events` table below |
| 2 | A user buys a ticket, ownerOf is displayed | "Buy Tickets" | Switch the account to `verifier` → "Buy now" | tx hash + "tokenId N minted · ownerOf(N) matches the buying account" |
| 3 | User A lists a ticket, user B buys it legitimately | "Resale Market" | As seller `buyerA`, select the ticket, price 1.2 → "List at this price"; on the right, as buyer `buyerB` → "Buy this ticket" | The ticket appears in the listings table; the purchase tx succeeds and the owner changes |
| 4 | An above-cap resale is rejected by the contract | "Resale Market" | Switch the seller to `buyerB` (after the purchase in step 3 the owner has already become B), select the same ticket → "Over-price listing (expect rejection)" | Red card: `Price exceeds dynamic limit` (asking price 1.5 > cap 1.2) |
| 5 | Transferring the NFT directly to bypass the rules is rejected | Terminal | T11 in `python backend/demo_flow.py`, or just look at `results/demo_report.md` | The `transferFrom` transaction is included on chain but **status=0**, gas 22,558 |
| 6 | User B presents the QR code and the verifier checks in successfully for the first time | "My Tickets" → "Staff Check-in" | `buyerB` generates the QR code → "Send to check-in page" → "Verify ticket" → "Check in (first time)" | All 5 checks are green; the check-in tx succeeds; `used` becomes True and the button is greyed out |
| 7 | A second check-in fails, and the test table and Gas chart are shown | "Staff Check-in" | "Check in again (should fail)" | Red card `Ticket already used` |
| + | Wrap-up: show the ticket proceeds settlement | `Settlement (Pull Payment)` at the bottom of "Events" | Select `organizer` as the settlement account → "Withdraw proceeds" | `Pending proceeds` goes from N to 0, `Account balance` increases, green card "TX SUCCESS" |
| + | Wrap-up display | — | Open `results/demo_report.md` | At-a-glance PASS/FAIL, tx hashes and Gas for the 27 test cases |

> ⚠️ **Two pitfalls that are easy to hit (already avoided)**
> 1. After `demo_flow.py` has run, `buyerA` has already bought the full 2 tickets (per-wallet limit 2), so clicking "Buy now" with it again reports
>    `Wallet limit exceeded`. For step 2, switch to an account that **has not bought any ticket yet** (`verifier`).
> 2. Listing the same ticket while it is **already listed** reports `already listed`, not a price-cap error. For step 4, make sure that ticket
>    is currently not on sale (buying it with `buyerB` in step 3 satisfies exactly that), and switch the seller account to the new owner `buyerB`.

## Talking points (one sentence per page)

- **Overview**: the chain ID, block height, contract address and the balances of the 6 accounts all come from the chain; the most recent Transfer logs are listed below.
- **Events**: once the event parameters are on chain, changing the front end has no effect; a batch whitelist write is a single transaction. `Settlement` at the bottom demonstrates pull-payment settlement.
- **Buy Tickets**: first the `canPurchase` pre-check (no gas spent), then `purchaseTickets`; the page computes the amount exactly as `price × quantity`,
  and even 1 wei extra is rejected by the contract.
- **My Tickets**: the contract does not inherit ERC721Enumerable, so "my tickets" are obtained by scanning Transfer events plus an `ownerOf` check on each one.
  The QR code carries a holder signature with a 180-second validity window, not a bare tokenId.
- **Resale Market**: the price cap is computed by the contract (>7 days 120%, ≤7 days 100%); the page only displays the cap.
- **Staff Check-in**: a ticket is only accepted when the signature, the on-chain ownerOf and used all agree; check-in permission depends on `msg.sender` and has nothing to do with the ticket owner.

## Fallback plan (on-site network/node problems)

1. `./blockchain/start_node.sh --reset && sleep 5 && python backend/deploy.py && python backend/demo_flow.py`
   rebuilds a clean chain (about 3 minutes);
2. Walk through the flow with the six screenshots in `results/screenshots/` (each one shows real on-chain data);
3. `results/demo_report.md` contains all 27 transaction hashes, which can be checked one by one in `geth attach`.

## Accounts and credentials

| Role | Purpose |
|---|---|
| organizer | Create events, open/close ticket sales, whitelist, withdraw ticket proceeds |
| buyerA | Primary-market purchase, first listing |
| buyerB | Resale purchase, the holder whose ticket is checked in |
| verifier | On-chain check-in |
| attacker | Unauthorised check-in / over-limit purchase (for the demo) |
| deployer | Contract owner, withdraws the platform fee |

The private keys live only in the local `.env`; **do not** project `.env` or `blockchain/miner.key` on screen during the demo.
