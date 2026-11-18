"""QR ticket stub: short-lived + signed by the holder, cross-checked against on-chain state at check-in.

Design (corresponds to Member 4's T13/T14):
* The QR code carries a JSON payload rather than a bare tokenId:
      {v, token_id, holder, nonce, issued_at, expires_at, sig}
* sig = the holder's private key signing canonical text with EIP-191 (personal_sign).
* At check-in the same text is rebuilt and the signing address recovered; all of the following must hold:
      1. signing address == payload.holder
      2. payload.holder == on-chain ownerOf(tokenId)
      3. not expired (180 seconds by default)
      4. ticket not checked in yet
  Any failure rejects the ticket, so a screenshot/forwarded QR code dies after expiry and the
  previous owner cannot reuse it either.
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
DEFAULT_TTL = 180  # seconds


def _canonical_text(payload: dict[str, Any]) -> str:
    """Signed plaintext: fixed field order, rebuilt the same way by the verifier, so any tampered field fails verification."""
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
    """Sign the ticket stub with the holder's wallet and return a payload that can be encoded into a QR code directly."""
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
    """Validate the ticket stub and return the per-check results (no on-chain write)."""
    now = int(time.time()) if now is None else int(now)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1. Version
    add("Payload version", payload.get("v") == VERSION, f"v={payload.get('v')}")

    # 2. Signature
    try:
        recovered = Account.recover_message(
            encode_defunct(text=_canonical_text(payload)), signature=payload["sig"]
        )
    except Exception as exc:  # noqa: BLE001
        recovered = ""
        add("Signature parseable", False, f"{exc}"[:120])
    signed_ok = recovered.lower() == str(payload.get("holder", "")).lower()
    add("Signature matches holder", signed_ok, f"holder={payload.get('holder', '')[:10]}… recovered={recovered or '—'}")

    # 3. Validity window
    expires_at = int(payload.get("expires_at", 0))
    add("Not expired", expires_at > now, f"{max(expires_at - now, 0)} s left" if expires_at > now else "expired")

    # 4. On-chain owner
    owner_ok = bool(ticket) and ticket.get("owner", "").lower() == str(payload.get("holder", "")).lower()
    add("Matches on-chain ownerOf", owner_ok, f"ownerOf={ticket.get('owner') if ticket else '—'}")

    # 5. Whether it is already checked in
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
