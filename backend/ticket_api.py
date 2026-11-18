"""成员 1 交付的 Python 接口层（backend/ticket_api.py）。

成员 4 的 Streamlit 页面只允许调用本文件的函数，不直接写 Web3 代码：
    from backend.ticket_api import get_ticket_owner, buy_ticket, ...

约定
----
* 账户参数 `who` 既可以是角色名（"organizer" / "buyerA" / "buyerB" / "verifier" / "attacker"），
  也可以是 0x 地址。
* 写操作返回 `TxResult`：ok / tx_hash / block_number / gas_used / error。
* 金额参数一律用 ETH（float 或 str），内部换算成 wei，避免页面层出现精度错误。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from web3 import Web3

from .chain import Chain, TxResult, get_chain, hx

TRANSFER_TOPIC = hx(Web3.keccak(text="Transfer(address,address,uint256)"))


# ----------------------------------------------------------------------
# 内部工具
# ----------------------------------------------------------------------
def _chain() -> Chain:
    return get_chain()


def _contract():
    return _chain().require_contract()


def _addr(who: str) -> str:
    """角色名或地址 -> checksum 地址。"""
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
    """从 ABI 里取事件签名并计算 topic0。"""
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
# 链路状态
# ----------------------------------------------------------------------
def chain() -> Chain:
    """暴露底层 Chain（成员 1 内部/测试脚本使用；页面请优先用下面的语义化函数）。"""
    return get_chain()


def get_w3():
    return get_chain().w3


def get_settings():
    return get_chain().settings


def get_chain_status() -> dict[str, Any]:
    """链连接、chainId、区块高度、合约地址、各测试账户余额。"""
    return _chain().chain_status()


def get_receipt(tx_hash: str) -> dict[str, Any]:
    """查询交易是否被打包、Gas 用量、所在区块。"""
    return _chain().receipt(tx_hash)


def get_contract_address() -> str | None:
    return _chain().settings.contract_address


def get_accounts() -> dict[str, str]:
    return dict(_chain().settings.account_addresses)


def signing_key(role: str) -> str:
    """取角色私钥（仅课堂 Demo 的页面代签使用；真实产品应由用户钱包签名）。"""
    return _chain().settings.key(role)


def get_balance_eth(who: str) -> float:
    return _chain().balance_eth(_addr(who))


# ----------------------------------------------------------------------
# 活动（成员 2 的合约逻辑）
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
    """主办方创建活动。event_time 可传 datetime 或 unix 时间戳。"""
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
    """单个或多个地址写入预售白名单（多个时走 setWhitelistBatch）。"""
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
    """遍历 nextEventId 读取全部活动（活动数量很少，逐个 call 足够）。"""
    next_id = get_next_event_id()
    return [ev for ev in (get_event(i) for i in range(1, next_id)) if ev]


def get_next_event_id() -> int:
    return int(_contract().functions.nextEventId().call())


def remaining_supply(event_id: int) -> int:
    return int(_contract().functions.remainingSupply(int(event_id)).call())


def purchased_count(event_id: int, who: str) -> int:
    """链上 `purchasedByWallet`：只统计一级市场购买，二手买入不计入限购。"""
    return int(_contract().functions.purchasedByWallet(int(event_id), _addr(who)).call())


def can_purchase(event_id: int, who: str, quantity: int = 1) -> tuple[bool, str]:
    """链上预检：(是否可以买, 原因)。最终仍以 purchaseTickets 的链上校验为准。"""
    ok, reason = _contract().functions.canPurchase(int(event_id), _addr(who), int(quantity)).call()
    return bool(ok), str(reason)


# ----------------------------------------------------------------------
# 一级购票
# ----------------------------------------------------------------------
def buy_ticket(event_id: int, buyer: str = "buyerA", quantity: int = 1) -> TxResult:
    """一级市场购票：返回值里带 first_token_id / last_token_id，方便页面直接展示。"""
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
# 门票
# ----------------------------------------------------------------------
def get_ticket_owner(token_id: int) -> str:
    """读取门票当前持有人。"""
    return _contract().functions.ownerOf(int(token_id)).call()


def get_max_resale_price(token_id: int) -> dict[str, Any]:
    """动态转售上限：距演出 >7 天为原价 120%，≤7 天为原价 100%。

    合约在演出开始后做减法会下溢，这里捕获并返回 None，避免页面崩溃。
    """
    contract = _contract()
    try:
        wei = int(contract.functions.getMaxResalePrice(int(token_id)).call())
        return {"ok": True, "max_price_wei": wei, "max_price_eth": from_wei(wei)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "max_price_wei": None, "max_price_eth": None, "error": str(exc)[:200]}


def get_ticket(token_id: int) -> dict[str, Any] | None:
    """门票完整状态：票主、所属活动、挂牌价、转售次数、是否已核销。"""
    contract = _contract()
    try:
        owner = contract.functions.ownerOf(int(token_id)).call()
    except Exception:  # noqa: BLE001  不存在的 tokenId
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
    """某地址当前持有的 tokenId 列表。

    合约没有继承 ERC721Enumerable，因此通过扫描 Transfer 事件 + 校验当前 ownerOf 得到。
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
    """最近的 NFT 转移记录（购票铸造 / 转售），供页面展示交易证据。"""
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
# 二手市场（成员 3 的合约逻辑）
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
        return TxResult(ok=False, function="buyResale", error=f"门票 {token_id} 不存在")
    fn = _contract().functions.buyResale(int(token_id))
    result = _chain().send(fn, role=_role_of(buyer), value=ticket["listing_price_wei"])
    if result.ok:
        result.extra["price_eth"] = ticket["listing_price_eth"]
    return result


def listed_tickets() -> list[dict[str, Any]]:
    """当前所有在售门票（token 数量很少，逐个读 tickets 足够）。"""
    out = []
    for token_id in all_tokens():
        ticket = get_ticket(token_id)
        if ticket and ticket["is_listed"]:
            out.append(ticket)
    return out


def pending_proceeds(who: str = "organizer") -> float:
    """主办方待提取的一级市场票款（ETH）。

    合约是拉取式结算：购票款只记账到 `pendingProceeds`，购票交易里不会自动转出。
    """
    return from_wei(int(_contract().functions.pendingProceeds(_addr(who)).call()))


def pending_platform_fees(who: str = "deployer") -> float:
    """待提取的二级市场平台手续费（ETH）：每笔转售按售价 5% 记给合约 owner。"""
    return from_wei(int(_contract().functions.pendingPlatformFees(_addr(who)).call()))


def withdraw_proceeds(who: str = "organizer") -> TxResult:
    """主办方提取自己名下的票款（对应合约 `withdrawProceeds`）。"""
    return _chain().send(_contract().functions.withdrawProceeds(), role=_role_of(who))


def withdraw_platform_fees(owner: str = "deployer") -> TxResult:
    return _chain().send(_contract().functions.withdrawPlatformFees(), role=_role_of(owner))


# ----------------------------------------------------------------------
# 验票
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
# 事件
# ----------------------------------------------------------------------
def get_events(event_name: str, from_block: int | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """按名称读取链上事件（TicketPurchased / TicketResold / TicketCheckedIn ...）。"""
    chain = _chain()
    event = getattr(chain.require_contract().events, event_name)
    logs = event.get_logs(from_block=from_block or max(chain.settings.deploy_block, 0), to_block="latest")
    rows = []
    for log in logs[-limit:]:
        rows.append({"args": dict(log["args"]), "block": log["blockNumber"], "tx_hash": hx(log["transactionHash"])})
    return rows


# ----------------------------------------------------------------------
def _role_of(who: str) -> str:
    """把地址反查成角色名（send 需要角色名来取私钥）。"""
    w = str(who).strip()
    if not w.startswith("0x"):
        return w
    target = Web3.to_checksum_address(w)
    for role, addr in _chain().settings.account_addresses.items():
        if Web3.to_checksum_address(addr) == target:
            return role
    raise ValueError(f"地址 {w} 不在 .env 的测试账户中，无法代签交易")
