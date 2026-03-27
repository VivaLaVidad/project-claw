from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

try:
    from cryptography.fernet import Fernet
except Exception:  # pragma: no cover
    Fernet = None


class SecureEnvelopeError(ValueError):
    pass


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _to_key(secret: str | bytes) -> bytes:
    if isinstance(secret, bytes):
        return secret
    return secret.encode("utf-8")


def _encode_payload(payload: dict[str, Any], encryption_key: str = "") -> tuple[str, str]:
    raw = _canonical_json(payload).encode("utf-8")
    if encryption_key:
        if Fernet is None:
            raise SecureEnvelopeError("cryptography not installed, cannot encrypt payload")
        raw = Fernet(encryption_key.encode("utf-8")).encrypt(raw)
        return "fernet", base64.b64encode(raw).decode("ascii")
    return "none", base64.b64encode(raw).decode("ascii")


def _decode_payload(enc: str, payload_b64: str, encryption_key: str = "") -> dict[str, Any]:
    raw = base64.b64decode(payload_b64.encode("ascii"))
    if enc == "fernet":
        if not encryption_key:
            raise SecureEnvelopeError("missing encryption key for encrypted payload")
        if Fernet is None:
            raise SecureEnvelopeError("cryptography not installed, cannot decrypt payload")
        raw = Fernet(encryption_key.encode("utf-8")).decrypt(raw)
    return json.loads(raw.decode("utf-8"))


def build_secure_envelope(
    payload: dict[str, Any],
    sender_id: str,
    receiver_id: str,
    secret: str,
    encryption_key: str = "",
) -> dict[str, Any]:
    enc, encoded_payload = _encode_payload(payload, encryption_key)
    env = {
        "v": "1",
        "alg": "HS256",
        "enc": enc,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "ts": time.time(),
        "nonce": uuid.uuid4().hex[:16],
        "payload": encoded_payload,
    }
    signing_text = _canonical_json(env)
    env["sig"] = hmac.new(_to_key(secret), signing_text.encode("utf-8"), hashlib.sha256).hexdigest()
    return env


def verify_and_unpack_envelope(
    envelope: dict[str, Any],
    expected_receiver_id: str,
    secret: str,
    encryption_key: str = "",
    max_skew_seconds: int = 120,
) -> dict[str, Any]:
    required = {"v", "alg", "enc", "sender_id", "receiver_id", "ts", "nonce", "payload", "sig"}
    if not required.issubset(set(envelope.keys())):
        raise SecureEnvelopeError("invalid envelope fields")
    if envelope.get("alg") != "HS256":
        raise SecureEnvelopeError("unsupported signature algorithm")
    if envelope.get("receiver_id") != expected_receiver_id:
        raise SecureEnvelopeError("envelope receiver mismatch")
    skew = abs(time.time() - float(envelope.get("ts", 0)))
    if skew > max_skew_seconds:
        raise SecureEnvelopeError(f"envelope expired or clock skew too high: {skew:.1f}s")

    sig = envelope.get("sig", "")
    unsigned = {k: envelope[k] for k in envelope.keys() if k != "sig"}
    expected_sig = hmac.new(_to_key(secret), _canonical_json(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise SecureEnvelopeError("invalid envelope signature")

    return _decode_payload(str(envelope.get("enc", "none")), str(envelope.get("payload", "")), encryption_key)


def generate_fernet_key() -> str:
    if Fernet is None:
        raise SecureEnvelopeError("cryptography not installed")
    return Fernet.generate_key().decode("utf-8")


def resolve_encryption_key(config_key: str) -> str:
    return config_key or os.getenv("PROJECT_CLAW_A2A_ENCRYPTION_KEY", "")


class NonceReplayProtector:
    def __init__(self, ttl_seconds: int = 180):
        self.ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}

    def check_and_mark(self, sender_id: str, nonce: str, ts: float) -> None:
        key = f"{sender_id}:{nonce}"
        now = time.time()
        expired = [k for k, v in self._seen.items() if now - v > self.ttl_seconds]
        for k in expired:
            self._seen.pop(k, None)
        if key in self._seen:
            raise SecureEnvelopeError("replayed envelope nonce")
        if abs(now - ts) > self.ttl_seconds:
            raise SecureEnvelopeError("envelope timestamp out of replay window")
        self._seen[key] = now
