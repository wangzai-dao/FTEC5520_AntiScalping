# Member 2 / 3 Contract Review: Issue List for the Merged `ConcertTicket.sol`

> Review target: `contracts/ConcertTicket.sol` (`chunyusongyue-creator/FTEC5520-Final`, commit `61665bc`)
> Conclusion: **the functionality works end to end, and all contract-related cases among the 18 tests pass as expected** (see `results/demo_report.md`).
> The suggested changes are listed below in order of severity, for Member 3 to confirm whether to adopt them.
> This delivery by Members 1/4 **did not modify the contract source code**; it only worked around issues such as the missing `getTicket` at the Python layer.

## I. Recommended Fixes (Affecting Actual Use)

### 1. `withdrawPlatformFees()` cannot withdraw platform fees after the owner changes (Medium)

```solidity
pendingPlatformFees[owner()] += platformFee;      // bookkeeping is hard-coded to owner()
...
uint256 amount = pendingPlatformFees[msg.sender]; // but withdrawal uses msg.sender
```

`withdrawPlatformFees()` carries `onlyOwner`, so as long as the owner has not changed, the two are equal and the fees can be withdrawn.
But once `transferOwnership()` replaces the owner with someone else:

- The fees recorded under the old owner can no longer be withdrawn by anyone (the function only allows the new owner to call it, yet it reads the new owner's balance = 0);
- The new owner cannot access the old balance either.

**Recommendation**: use the same address source for both bookkeeping and withdrawal, for example

```solidity
pendingPlatformFees[owner()] += platformFee;
uint256 amount = pendingPlatformFees[owner()];   // instead of msg.sender
```

### 2. `buyResale()` lacks validation of event time / event status (Low-Medium)

`listForResale()` requires `block.timestamp < eventTime`, but `buyResale()` only checks `isListed`.
As a result, after the event starts (or even ends), an earlier listing can still be bought — the buyer pays but cannot enter.
Likewise, after an event is taken down with `setEventActive(false)`, the secondary market still completes trades.

**Recommendation**: add the following inside `buyResale`

```solidity
require(concert.active, "Event is not active");
require(block.timestamp < concert.eventTime, "Event already started");
```

### 3. `getMaxResalePrice()` behaves ambiguously for a finished event / a nonexistent tokenId (Low)

- Once the event time has passed, `concert.eventTime - block.timestamp` **underflows and reverts**, so the caller must check the time itself first;
- When the tokenId does not exist, `tokenToEvent = 0` and the original price is 0, so the function **returns 0 instead of reverting**, which is easily misread as "this ticket cannot be sold".

**Recommendation**:

```solidity
require(tokenToEvent[tokenId] != 0, "Ticket does not exist");
require(block.timestamp < concert.eventTime, "Event already started");
```

(Member 1's `ticket_api.get_max_resale_price()` already performs exception protection, so the page will not crash.)

### 4. Missing the read-only aggregate interface `getTicket(tokenId)` (Low, affects the frontend)

Section 08 of the documentation specifies `getTicket(tokenId)`, but the merged contract does not have it. To display "ticket owner + event + resale count + whether used", the frontend
has to read `ownerOf`, `tickets`, `tokenToEvent` and `concertEvents` four times in a row, and the contract **does not inherit ERC721Enumerable**,
so the "My Tickets" page cannot obtain the list of held tickets.

The current approach: Member 1 reconstructs it in `backend/ticket_api.py` using event scanning plus a per-token `ownerOf` check
(`tokens_of()` / `get_ticket()`), read-only, without modifying the contract. If Gas/request count is to be optimized later, the recommendation is to add to the contract:

```solidity
function getTicket(uint256 tokenId) external view returns (
    address owner, uint256 eventId, uint256 originalPrice,
    bool isListed, uint256 listingPrice, uint256 resaleCount, bool used
) { ... }
```

### 5. `buyResale` pushes funds to the seller (Low)

```solidity
(bool success, ) = payable(seller).call{value: sellerAmount}("");
require(success, "Payment to seller failed");
```

If the seller is a contract that rejects ETH, this ticket can never be sold (every purchase will revert).
EOA sellers are unaffected. A more robust approach is to switch to a pull model, as with `pendingProceeds`:

```solidity
pendingResaleProceeds[seller] += sellerAmount;   // the seller withdraws themselves
```

## II. Design Limitations (they do not necessarily have to be fixed, but they should be written in the report)

| Observation | Explanation |
|---|---|
| The primary-market per-wallet limit only counts `purchasedByWallet` | Tickets bought through `buyResale` are not counted toward the limit, so the per-wallet limit can be bypassed by "buying second-hand"; the contract inherently cannot stop one person from using multiple wallets, which is already listed as a limitation in the report |
| `checkIn` does not verify the identity of the ticket holder | A verifier can check in any unused ticket (including one held by someone else). This project supplies this layer off-chain through a "ticket-holder-signed QR code"; the contract layer only guarantees that "a ticket can be checked in only once" |
| `approve` / `setApprovalForAll` still exist | Approval is possible, but `transferFrom` / `safeTransferFrom` are all overridden to revert, so approvals have no practical use and can be understood as harmless leftover interfaces |
| `purchaseTickets` requires the amount to be **exactly equal** | Paying 1 wei extra reverts directly instead of refunding. The frontend must compute the exact amount from the ticket price (Member 1's `buy_ticket` already computes `price × quantity`) |
| The contract has no pause switch | When something goes wrong, the only option is to stop a single event with `setEventActive(false)`; there is no global pause |

## III. Test Script for `Helper.sol`

1. `runAllTests()` only spends **1 ETH** (buying 1 ticket), while the README tells you to enter `5 ether` in Remix's Value field.
   Entering 5 ETH also works (the remainder is refunded at the end), but the documentation figures do not match, so 1 ETH should be used consistently.
2. The `Helper` constructor calls `new ConcertTicket()`, so **Helper itself is the owner**,
   which is the only reason `setVerifier(address(this), true)` succeeds. If it were changed to "pass in the address of an already deployed main contract", this line would revert directly.
   To run "integration tests against a deployed instance", the owner of the main contract must first authorize Helper.
3. Step 3, "buy 2 tickets to trigger the per-wallet limit", is actually stopped by `Wallet limit exceeded`,
   which follows from the contract's order of **validating the limit first and the amount second** — if the order were reversed, the same test would fail with
   `Incorrect ETH amount`, and the test conclusion would be misjudged. The tests should state the expected revert reason explicitly.

## IV. List of Contract Dependencies for This Delivery

| Page / interface | Contract functions depended on |
|---|---|
| Event management | `createEvent` `setEventActive` `setPresaleActive` `setWhitelistBatch` `concertEvents` `nextEventId` |
| Ticket purchase | `canPurchase` `purchaseTickets` `nextTokenId` `remainingSupply` |
| My Tickets | `ownerOf` `tickets` `tokenToEvent` `getMaxResalePrice` |
| Secondary market | `listForResale` `cancelListing` `buyResale` |
| Ticket verification | `verifiers` `setVerifier` `checkIn` |
| Evidence | `TicketPurchased` `TicketResold` `TicketCheckedIn` `Transfer` events |
