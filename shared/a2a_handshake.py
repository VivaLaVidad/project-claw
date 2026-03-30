"""
Project Claw - A2A Handshake (lightweight libp2p style over WS)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, Field


class ClawHeader(BaseModel):
    source_id: str
    target_id: str
    timestamp: float = Field(default_factory=time.time)
    msg_type: str
    packet_id: str = Field(default_factory=lambda: secrets.token_hex(8))


class ClawPacket(BaseModel):
    header: ClawHeader
    payload: str  # base64(nonce + ciphertext)
    signature: str


def _norm_key(raw: str, length: int) -> bytes:
    b = raw.encode("utf-8")
    if len(b) == length:
        return b
    return hashlib.sha256(b).digest()[:length]


def _aes_key() -> bytes:
    return _norm_key(os.getenv("A2A_AES_KEY", "claw-aes-dev-key-change-me"), 32)


def _sign_key() -> bytes:
    return _norm_key(os.getenv("A2A_SIGN_KEY", "claw-sign-dev-key-change-me"), 32)


def _sign(header: ClawHeader, encrypted_payload: str, sign_key: bytes) -> str:
    header_json = json.dumps(header.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    msg = f"{header_json}::{encrypted_payload}".encode("utf-8")
    return hmac.new(sign_key, msg, hashlib.sha256).hexdigest()


def encrypt_payload(payload: Dict[str, Any], aes_key: bytes | None = None) -> str:
    key = aes_key or _aes_key()
    nonce = secrets.token_bytes(12)
    aes = AESGCM(key)
    plain = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cipher = aes.encrypt(nonce, plain, None)
    return base64.b64encode(nonce + cipher).decode("utf-8")


def decrypt_payload(encrypted_payload: str, aes_key: bytes | None = None) -> Dict[str, Any]:
    key = aes_key or _aes_key()
    data = base64.b64decode(encrypted_payload.encode("utf-8"))
    nonce, cipher = data[:12], data[12:]
    plain = AESGCM(key).decrypt(nonce, cipher, None)
    return json.loads(plain.decode("utf-8"))


def build_packet(source_id: str, target_id: str, msg_type: str, payload: Dict[str, Any]) -> ClawPacket:
    h = ClawHeader(source_id=source_id, target_id=target_id, msg_type=msg_type)
    encrypted = encrypt_payload(payload)
    sig = _sign(h, encrypted, _sign_key())
    return ClawPacket(header=h, payload=encrypted, signature=sig)


def open_packet(packet: ClawPacket | Dict[str, Any], expected_target_id: str = "") -> Dict[str, Any]:
    p = packet if isinstance(packet, ClawPacket) else ClawPacket(**packet)
    expected_sig = _sign(p.header, p.payload, _sign_key())
    if not hmac.compare_digest(expected_sig, p.signature):
        raise ValueError("bad_packet_signature")
    if expected_target_id and p.header.target_id not in (expected_target_id, "*"):
        raise ValueError("packet_target_mismatch")
    payload = decrypt_payload(p.payload)
    return {"header": p.header.model_dump(), "payload": payload}
