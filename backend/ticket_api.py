"""Python interface layer delivered by Member 1 (backend/ticket_api.py).

The Streamlit pages of Member 4 may only call the functions in this file and must not
write Web3 code directly:
    from backend.ticket_api import get_ticket_owner, buy_ticket, ...

Conventions
-----------
* The account argument `who` may be a role name ("organizer" / "buyerA" / "buyerB" /
  "verifier" / "attacker") or a 0x address.
* Write operations return `TxResult`: ok / tx_hash / block_number / gas_used / error.
* Amounts are always given in ETH (float or str) and converted to wei internally, so the
  page layer never hits precision errors.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from web3 import Web3

from .chain import Chain, TxResult, get_chain, hx

TRANSFER_TOPIC = hx(Web3.keccak(text="Transfer(address,address,uint256)"))


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------
def _chain() -> Chain:
    return get_chain()


def _contract():
    return _chain().require_contract()


def _addr(who: str) -> str:
    """Role name or address -> checksum address."""
    w = str(who).strip()
    if w.startswith("0x") and len(w) == 42:
        return Web3.to_checksum_address(w)
    try:
        return Web3.to_checksum_address(_chain().settings.address(w))
    except KeyError as exc:
        raise ValueError(f"Unknown account {who!r}; available roles: {', '.join(_chain().settings.account_addresses)}") from exc


def to_wei(eth: float | str | Decimal) -> int:
    return Web3.to_wei(Decimal(str(eth)), "ether")


def from_wei(wei: int | None) -> float:
    if wei is None:
        return 0.0
    return float(Web3.from_wei(int(wei), "ether"))


def _event_topic(name: str) -> str:
    """Look up an event signature in the ABI and compute topic0."""
    for item in _chain().abi:
        if item.get("type") == "event" and item.get("name") == name:
            types = ",".join(i["type"] for i in item["inputs"])
            return hx(Web3.keccak(text=f"{name}({types})"))
    raise KeyError(name)


def _decode_transfer_logs(logs: Iterable[dict]) -> list[dict]:
    out = []
    for log in logs:
        topics = log["topics"]
        if len(topics) < 4:
            continue
        out.append(
            {
                "from": Web3.to_checksum_address("0x" + topics[1].hex()[-40:]),
                "to": Web3.to_checksum_address("0x" + topics[2].hex()[-40:]),
                "token_id": int(topics[3].hex(), 16),
                "block": log["blockNumber"],
                "tx_hash": hx(log["transactionHash"]),
            }
        )
    return out


# ----------------------------------------------------------------------
# Chain status
# ----------------------------------------------------------------------
def chain() -> Chain:
    """Expose the underlying Chain (for Member 1 internals and test scripts).

    Pages should prefer the semantic functions below.
    """
    return get_chain()


def get_w3():
    return get_chain().w3


def get_settings():
    return get_chain().settings


def get_chain_status() -> dict[str, Any]:
    """Chain connection, chainId, block height, contract address, test account balances."""
    return _chain().chain_status()


def get_receipt(tx_hash: str) -> dict[str, Any]:
    """Check whether a transaction was mined, plus its gas usage and block."""
    return _chain().receipt(tx_hash)


def get_contract_address() -> str | None:
    return _chain().settings.contract_address


def get_accounts() -> dict[str, str]:
    return dict(_chain().settings.account_addresses)


def signing_key(role: str) -> str:
    """Fetch a role's private key (page-side signing for the class demo only).

    A real product would let the user's own wallet sign.
    """
    return _chain().settings.key(role)


def get_balance_eth(who: str) -> float:
    return _chain().balance_eth(_addr(who))


# ----------------------------------------------------------------------
# Events (Member 2's contract logic)
# ----------------------------------------------------------------------
def create_event(
    name: str,
    price_eth: float | str,
    max_supply: int,
    event_time: datetime | int,
    wallet_limit: int,
    presale_active: bool = False,
    organizer: str = "organizer",
) -> TxResult:
    """Organizer creates an event. event_time may be a datetime or a unix timestamp."""
    ts = int(event_time.timestamp()) if isinstance(event_time, datetime) else int(event_time)
    fn = _contract().functions.createEvent(
        name, to_wei(price_eth), int(max_supply), ts, int(wallet_limit), bool(presale_active)
    )
    result = _chain().send(fn, role=_role_of(organizer))
    if result.ok:
        result.extra["event_id"] = get_next_event_id() - 1
    return result


def set_event_active(event_id: int, active: bool, organizer: str = "organizer") -> TxResult:
    fn = _contract().functions.setEventActive(int(event_id), bool(active))
    return _chain().send(fn, role=_role_of(organizer))


def set_presale_active(event_id: int, presale_active: bool, organizer: str = "organizer") -> TxResult:
    fn = _contract().functions.setPresaleActive(int(event_id), bool(presale_active))
    return _chain().send(fn, role=_role_of(organizer))


def set_whitelist(event_id: int, accounts: str | Iterable[str], allowed: bool = True,
                  organizer: str = "organizer") -> TxResult:
    """Add one or more addresses to the presale whitelist (setWhitelistBatch for many)."""
    contract = _contract()
    if isinstance(accounts, str):
        fn = contract.functions.setWhitelist(int(event_id), _addr(accounts), bool(allowed))
    else:
        fn = contract.functions.setWhitelistBatch(
            int(event_id), [_addr(a) for a in accounts], bool(allowed)
        )
    return _chain().send(fn, role=_role_of(organizer))


def get_event(event_id: int) -> dict[str, Any] | None:
    raw = _contract().functions.concertEvents(int(event_id)).call()
    if raw[6] == "0x0000000000000000000000000000000000000000":
        return None
    return {
        "event_id": int(event_id),
        "name": raw[0],
        "price_eth": from_wei(raw[1]),
        "price_wei": int(raw[1]),
        "max_supply": int(raw[2]),
        "sold": int(raw[3]),
        "event_time": int(raw[4]),
        "event_time_str": datetime.fromtimestamp(int(raw[4]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "wallet_limit": int(raw[5]),
        "organizer": raw[6],
        "active": bool(raw[7]),
        "presale_active": bool(raw[8]),
        "remaining": int(raw[2]) - int(raw[3]),
    }


def list_events() -> list[dict[str, Any]]:
    """Read all events by iterating nextEventId (few events, so per-id calls are fine)."""
    next_id = get_next_event_id()
    return [ev for ev in (get_event(i) for i in range(1, next_id)) if ev]


def get_next_event_id() -> int:
    return int(_contract().functions.nextEventId().call())


def remaining_supply(event_id: int) -> int:
    return int(_contract().functions.remainingSupply(int(event_id)).call())


def purchased_count(event_id: int, who: str) -> int:
    """On-chain `purchasedByWallet`: primary-market buys only; resales do not count."""
    return int(_contract().functions.purchasedByWallet(int(event_id), _addr(who)).call())


def can_purchase(event_id: int, who: str, quantity: int = 1) -> tuple[bool, str]:
    """On-chain pre-check: (can buy, reason). The purchaseTickets on-chain check is final."""
    ok, reason = _contract().functions.canPurchase(int(event_id), _addr(who), int(quantity)).call()
    return bool(ok), str(reason)


# ----------------------------------------------------------------------
# Primary-market purchase
# ----------------------------------------------------------------------
def buy_ticket(event_id: int, buyer: str = "buyerA", quantity: int = 1) -> TxResult:
    """Primary-market purchase: the result also carries first_token_id / last_token_id."""
    contract = _contract()
    event = get_event(event_id)
    if event is None:
        return TxResult(ok=False, function="purchaseTickets", error=f"event {event_id} does not exist")
    first = int(contract.functions.nextTokenId().call())
    fn = contract.functions.purchaseTickets(int(event_id), int(quantity))
    result = _chain().send(fn, role=_role_of(buyer), value=event["price_wei"] * int(quantity))
    if result.ok:
        result.extra.update(first_token_id=first, last_token_id=first + int(quantity) - 1,
                            total_paid_eth=event["price_eth"] * int(quantity))
    return result


# ----------------------------------------------------------------------
# Tickets
# ----------------------------------------------------------------------
def get_ticket_owner(token_id: int) -> str:
    """Read the current holder of a ticket."""
    return _contract().functions.ownerOf(int(token_id)).call()


def get_max_resale_price(token_id: int) -> dict[str, Any]:
    """Dynamic resale cap: 120% of face value when >7 days before the show, else 100%.

    Once the show has started the contract's subtraction would underflow, so the error is
    caught and None is returned instead of crashing the page.
    """
    contract = _contract()
    try:
        wei = int(contract.functions.getMaxResalePrice(int(token_id)).call())
        return {"ok": True, "max_price_wei": wei, "max_price_eth": from_wei(wei)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "max_price_wei": None, "max_price_eth": None, "error": str(exc)[:200]}


def get_ticket(token_id: int) -> dict[str, Any] | None:
    """Full ticket state: owner, event, listing price, resale count, check-in state."""
    contract = _contract()
    try:
        owner = contract.functions.ownerOf(int(token_id)).call()
    except Exception:  # noqa: BLE001  nonexistent tokenId
        return None
    is_listed, listing_price, resale_count, used = contract.functions.tickets(int(token_id)).call()
    event_id = int(contract.functions.tokenToEvent(int(token_id)).call())
    event = get_event(event_id)
    cap = get_max_resale_price(token_id)
    return {
        "token_id": int(token_id),
        "owner": owner,
        "event_id": event_id,
        "event_name": event["name"] if event else "",
        "original_price_eth": event["price_eth"] if event else 0.0,
        "is_listed": bool(is_listed),
        "listing_price_wei": int(listing_price),
        "listing_price_eth": from_wei(listing_price),
        "resale_count": int(resale_count),
        "resale_limit": 3,
        "used": bool(used),
        "max_resale_price_eth": cap["max_price_eth"],
        "event_time": event["event_time"] if event else 0,
    }


def get_next_token_id() -> int:
    return int(_contract().functions.nextTokenId().call())


def all_tokens() -> list[int]:
    n = get_next_token_id()
    return list(range(1, n))


def tokens_of(who: str) -> list[int]:
    """List of tokenIds an address currently holds.

    The contract does not inherit ERC721Enumerable, so the list is built by scanning the
    Transfer events and then verifying the current ownerOf.
    """
    address = _addr(who)
    logs = _chain().w3.eth.get_logs(
        {
            "fromBlock": hex(max(_chain().settings.deploy_block, 0)),
            "toBlock": "latest",
            "address": _chain().settings.contract_address,
            "topics": [TRANSFER_TOPIC],
        }
    )
    candidates = {item["token_id"] for item in _decode_transfer_logs(logs) if item["to"] == address}
    owned = []
    for token_id in sorted(candidates):
        try:
            if get_ticket_owner(token_id) == address:
                owned.append(token_id)
        except Exception:  # noqa: BLE001
            continue
    return owned


def transfer_history(limit: int = 30) -> list[dict[str, Any]]:
    """Recent NFT transfers (mints on purchase / resales), shown by the page as evidence."""
    logs = _chain().w3.eth.get_logs(
        {
            "fromBlock": hex(max(_chain().settings.deploy_block, 0)),
            "toBlock": "latest",
            "address": _chain().settings.contract_address,
            "topics": [TRANSFER_TOPIC],
        }
    )
    return list(reversed(_decode_transfer_logs(logs)))[:limit]


# ----------------------------------------------------------------------
# Secondary market (Member 3's contract logic)
# ----------------------------------------------------------------------
def list_ticket(token_id: int, price_eth: float | str, seller: str = "buyerA") -> TxResult:
    fn = _contract().functions.listForResale(int(token_id), to_wei(price_eth))
    return _chain().send(fn, role=_role_of(seller))


def cancel_listing(token_id: int, seller: str = "buyerA") -> TxResult:
    fn = _contract().functions.cancelListing(int(token_id))
    return _chain().send(fn, role=_role_of(seller))


def buy_resale(token_id: int, buyer: str = "buyerB") -> TxResult:
    ticket = get_ticket(token_id)
    if ticket is None:
        return TxResult(ok=False, function="buyResale", error=f"Ticket {token_id} does not exist")
    fn = _contract().functions.buyResale(int(token_id))
    result = _chain().send(fn, role=_role_of(buyer), value=ticket["listing_price_wei"])
    if result.ok:
        result.extra["price_eth"] = ticket["listing_price_eth"]
    return result


def listed_tickets() -> list[dict[str, Any]]:
    """All tickets currently for sale (few tokens, so reading tickets one by one is fine)."""
    out = []
    for token_id in all_tokens():
        ticket = get_ticket(token_id)
        if ticket and ticket["is_listed"]:
            out.append(ticket)
    return out


def pending_proceeds(who: str = "organizer") -> float:
    """Primary-market revenue the organizer can still withdraw (ETH).

    Settlement is pull-based: the payment is only credited to `pendingProceeds` and the
    purchase transaction does not transfer it out.
    """
    return from_wei(int(_contract().functions.pendingProceeds(_addr(who)).call()))


def pending_platform_fees(who: str = "deployer") -> float:
    """Withdrawable resale platform fee (ETH): 5% of each resale price, to the owner."""
    return from_wei(int(_contract().functions.pendingPlatformFees(_addr(who)).call()))


def withdraw_proceeds(who: str = "organizer") -> TxResult:
    """Organizer withdraws the revenue credited to them (contract `withdrawProceeds`)."""
    return _chain().send(_contract().functions.withdrawProceeds(), role=_role_of(who))


def withdraw_platform_fees(owner: str = "deployer") -> TxResult:
    return _chain().send(_contract().functions.withdrawPlatformFees(), role=_role_of(owner))


# ----------------------------------------------------------------------
# Check-in
# ----------------------------------------------------------------------
def set_verifier(verifier: str, status: bool = True, owner: str = "deployer") -> TxResult:
    fn = _contract().functions.setVerifier(_addr(verifier), bool(status))
    return _chain().send(fn, role=_role_of(owner))


def is_verifier(who: str) -> bool:
    return bool(_contract().functions.verifiers(_addr(who)).call())


def check_in(token_id: int, verifier: str = "verifier") -> TxResult:
    fn = _contract().functions.checkIn(int(token_id))
    return _chain().send(fn, role=_role_of(verifier))


# ----------------------------------------------------------------------
# Events
# ----------------------------------------------------------------------
def get_events(event_name: str, from_block: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Read on-chain events by name (TicketPurchased / TicketResold / TicketCheckedIn ...)."""
    chain = _chain()
    event = getattr(chain.require_contract().events, event_name)
    logs = event.get_logs(from_block=from_block or max(chain.settings.deploy_block, 0), to_block="latest")
    rows = []
    for log in logs[-limit:]:
        rows.append({"args": dict(log["args"]), "block": log["blockNumber"], "tx_hash": hx(log["transactionHash"])})
    return rows


# ----------------------------------------------------------------------
def _role_of(who: str) -> str:
    """Map an address back to a role name (send needs the role name to get the key)."""
    w = str(who).strip()
    if not w.startswith("0x"):
        return w
    target = Web3.to_checksum_address(w)
    for role, addr in _chain().settings.account_addresses.items():
        if Web3.to_checksum_address(addr) == target:
            return role
    raise ValueError(f"Address {w} is not a .env test account; cannot sign on its behalf")
