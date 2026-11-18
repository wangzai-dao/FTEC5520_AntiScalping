"""二维码票根：短时有效 + 持票人签名，验票时与链上状态交叉校验。

设计（对应成员 4 的 T13/T14）：
* 二维码里不是裸 tokenId，而是一段 JSON：
      {v, token_id, holder, nonce, issued_at, expires_at, sig}
* sig = 持票人私钥对规范化文本做 EIP-191 (personal_sign) 签名。
* 验票时重新拼出同一段文本并恢复签名地址，要求：
      1. 签名地址 == payload.holder
      2. payload.holder == 链上 ownerOf(tokenId)
      3. 未过期（默认 180 秒）
      4. 门票尚未核销
  任一不满足即拒绝，因此截图/转发二维码在过期后失效，旧票主也无法复用。
"""

from __future__ import annotations

import io
import json
import secrets
import time
from typing import Any

import qrcode
from eth_account import Account
from eth_account.messages import encode_defunct

VERSION = 1
DOMAIN = "FTEC5520-TICKET"
DEFAULT_TTL = 180  # 秒


def _canonical_text(payload: dict[str, Any]) -> str:
    """签名原文：字段顺序固定，验签端用同样方式重建，任何字段被改都会验签失败。"""
    return "\n".join(
        [
            f"{DOMAIN}/v{payload['v']}",
            f"token_id:{payload['token_id']}",
            f"holder:{payload['holder'].lower()}",
            f"nonce:{payload['nonce']}",
            f"issued_at:{payload['issued_at']}",
            f"expires_at:{payload['expires_at']}",
        ]
    )


def create_ticket_qr(
    token_id: int,
    holder_address: str,
    private_key: str,
    ttl: int = DEFAULT_TTL,
) -> dict[str, Any]:
    """由持票人钱包对票根签名，返回可直接编码进二维码的 payload。"""
    issued_at = int(time.time())
    payload = {
        "v": VERSION,
        "token_id": int(token_id),
        "holder": holder_address,
        "nonce": secrets.token_hex(8),
        "issued_at": issued_at,
        "expires_at": issued_at + int(ttl),
    }
    signed = Account.sign_message(encode_defunct(text=_canonical_text(payload)), private_key)
    payload["sig"] = signed.signature.hex()
    if not payload["sig"].startswith("0x"):
        payload["sig"] = "0x" + payload["sig"]
    return payload


def payload_to_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_payload(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    required = {"v", "token_id", "holder", "nonce", "issued_at", "expires_at", "sig"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"QR payload is missing fields: {', '.join(sorted(missing))}")
    return data


def verify_payload(payload: dict[str, Any], ticket: dict[str, Any] | None, now: int | None = None) -> dict[str, Any]:
    """校验票根，返回逐项检查结果（不含链上写操作）。"""
    now = int(time.time()) if now is None else int(now)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1. 版本
    add("Payload version", payload.get("v") == VERSION, f"v={payload.get('v')}")

    # 2. 签名
    try:
        recovered = Account.recover_message(
            encode_defunct(text=_canonical_text(payload)), signature=payload["sig"]
        )
    except Exception as exc:  # noqa: BLE001
        recovered = ""
        add("Signature parseable", False, f"{exc}"[:120])
    signed_ok = recovered.lower() == str(payload.get("holder", "")).lower()
    add("Signature matches holder", signed_ok, f"holder={payload.get('holder', '')[:10]}… recovered={recovered or '—'}")

    # 3. 有效期
    expires_at = int(payload.get("expires_at", 0))
    add("Not expired", expires_at > now, f"{max(expires_at - now, 0)} s left" if expires_at > now else "expired")

    # 4. 链上票主
    owner_ok = bool(ticket) and ticket.get("owner", "").lower() == str(payload.get("holder", "")).lower()
    add("Matches on-chain ownerOf", owner_ok, f"ownerOf={ticket.get('owner') if ticket else '—'}")

    # 5. 是否已核销
    unused = bool(ticket) and not ticket.get("used")
    add("Ticket not used", unused, "used=true" if (ticket and ticket.get("used")) else "used=false")

    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "checks": checks, "recovered": recovered, "payload": payload, "ticket": ticket}


def make_qr_png(payload: dict[str, Any]) -> bytes:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(payload_to_text(payload))
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_qr_pil(payload: dict[str, Any]):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=2)
    qr.add_data(payload_to_text(payload))
    qr.make(fit=True)
    return qr.make_image(fill_color="#111827", back_color="white").get_image()
