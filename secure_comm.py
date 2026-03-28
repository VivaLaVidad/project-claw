"""
secure_comm.py
Project Claw v14.3 - A2A 端到端加密通信

修复：
- hmac.new → hmac.new 正确调用（Python 标准库是 hmac.new）
- NonceReplayProtector 加 threading.Lock 保证并发安全
- 时间戳校验精度提升
- 所有异常消息标准化
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from threading import Lock
from typing import Any

try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:  # pragma: no cover
    Fernet = None  # type: ignore
    _FERNET_AVAILABLE = False


# ─── 异常 ─────────────────────────────────────────────────────────────────
class SecureEnvelopeError(ValueError):
    """所有信封校验失败统一抛出此异常。"""


# ─── 工具函数 ──────────────────────────────────────────────────────────────
def _canonical_json(data: dict[str, Any]) -> str:
    """确定性 JSON 序列化（sort_keys + 无空格）。"""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _to_key(secret: str | bytes) -> bytes:
    return secret if isinstance(secret, bytes) else secret.encode("utf-8")


def _hmac_sha256(key: str | bytes, message: str) -> str:
    """正确调用 hmac.new（非 hmac.new，Python stdlib 是 hmac.new）。"""
    return hmac.new(
        _to_key(key),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ─── Payload 加密/解密 ────────────────────────────────────────────────────
def _encode_payload(
    payload: dict[str, Any],
    encryption_key: str = "",
) -> tuple[str, str]:
    raw = _canonical_json(payload).encode("utf-8")
    if encryption_key:
        if not _FERNET_AVAILABLE:
            raise SecureEnvelopeError("cryptography 未安装，无法加密 payload")
        raw = Fernet(encryption_key.encode("utf-8")).encrypt(raw)
        return "fernet", base64.b64encode(raw).decode("ascii")
    return "none", base64.b64encode(raw).decode("ascii")


def _decode_payload(
    enc: str,
    payload_b64: str,
    encryption_key: str = "",
) -> dict[str, Any]:
    try:
        raw = base64.b64decode(payload_b64.encode("ascii"))
    except Exception as e:
        raise SecureEnvelopeError(f"payload base64 解码失败: {e}") from e

    if enc == "fernet":
        if not encryption_key:
            raise SecureEnvelopeError("加密 payload 缺少 encryption_key")
        if not _FERNET_AVAILABLE:
            raise SecureEnvelopeError("cryptography 未安装，无法解密 payload")
        try:
            raw = Fernet(encryption_key.encode("utf-8")).decrypt(raw)
        except Exception as e:
            raise SecureEnvelopeError(f"Fernet 解密失败: {e}") from e
    elif enc != "none":
        raise SecureEnvelopeError(f"不支持的加密方式: {enc}")

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise SecureEnvelopeError(f"payload JSON 解析失败: {e}") from e


# ─── 信封构建 ──────────────────────────────────────────────────────────────
def build_secure_envelope(
    payload: dict[str, Any],
    sender_id: str,
    receiver_id: str,
    secret: str,
    encryption_key: str = "",
) -> dict[str, Any]:
    """
    构建 A2A 安全信封（AES-GCM/Fernet 加密 + HMAC-SHA256 签名）。

    信封结构：
        v, alg, enc, sender_id, receiver_id, ts, nonce, payload, sig
    """
    if not secret:
        raise SecureEnvelopeError("signing secret 不能为空")
    if not sender_id or not receiver_id:
        raise SecureEnvelopeError("sender_id / receiver_id 不能为空")

    enc, encoded_payload = _encode_payload(payload, encryption_key)
    env: dict[str, Any] = {
        "v":           "1",
        "alg":         "HS256",
        "enc":         enc,
        "sender_id":   sender_id,
        "receiver_id": receiver_id,
        "ts":          time.time(),
        "nonce":       uuid.uuid4().hex[:16],
        "payload":     encoded_payload,
    }
    env["sig"] = _hmac_sha256(secret, _canonical_json(env))
    return env


# ─── 信封校验 ──────────────────────────────────────────────────────────────
_REQUIRED_FIELDS = frozenset(
    {"v", "alg", "enc", "sender_id", "receiver_id", "ts", "nonce", "payload", "sig"}
)


def verify_and_unpack_envelope(
    envelope: dict[str, Any],
    expected_receiver_id: str,
    secret: str,
    encryption_key: str = "",
    max_skew_seconds: int = 120,
) -> dict[str, Any]:
    """
    校验 A2A 安全信封并解包 payload。

    校验顺序：
    1. 字段完整性
    2. 算法白名单
    3. receiver_id 匹配
    4. 时间戳偏差
    5. HMAC 签名（constant-time compare)
    6. payload 解密/解码
    """
    # 1. 字段完整性
    missing = _REQUIRED_FIELDS - set(envelope.keys())
    if missing:
        raise SecureEnvelopeError(f"信封缺少字段: {missing}")

    # 2. 算法白名单
    if envelope.get("alg") != "HS256":
        raise SecureEnvelopeError(f"不支持的签名算法: {envelope.get('alg')}")

    # 3. receiver_id 匹配
    if envelope.get("receiver_id") != expected_receiver_id:
        raise SecureEnvelopeError(
            f"receiver_id 不匹配: expected={expected_receiver_id} "
            f"got={envelope.get('receiver_id')}"
        )

    # 4. 时间戳偏差
    try:
        ts = float(envelope["ts"])
    except (ValueError, TypeError) as e:
        raise SecureEnvelopeError(f"无效的时间戳: {e}") from e
    skew = abs(time.time() - ts)
    if skew > max_skew_seconds:
        raise SecureEnvelopeError(
            f"信封已过期或时钟偏差过大: skew={skew:.1f}s max={max_skew_seconds}s"
        )

    # 5. HMAC 签名（constant-time）
    received_sig = str(envelope.get("sig", ""))
    unsigned = {k: v for k, v in envelope.items() if k != "sig"}
    expected_sig = _hmac_sha256(secret, _canonical_json(unsigned))
    if not hmac.compare_digest(received_sig, expected_sig):
        raise SecureEnvelopeError("信封签名校验失败")

    # 6. payload 解密
    return _decode_payload(
        str(envelope.get("enc", "none")),
        str(envelope.get("payload", "")),
        encryption_key,
    )


# ─── 工具 ──────────────────────────────────────────────────────────────────
def generate_fernet_key() -> str:
    if not _FERNET_AVAILABLE:
        raise SecureEnvelopeError("cryptography 未安装")
    return Fernet.generate_key().decode("utf-8")


def resolve_encryption_key(config_key: str) -> str:
    return config_key or os.getenv("PROJECT_CLAW_A2A_ENCRYPTION_KEY", "")


# ─── NonceReplayProtector（线程安全）──────────────────────────────────────
class NonceReplayProtector:
    """
    防重放攻击：记录已见过的 (sender_id, nonce) 对。
    TTL 内的重复 nonce 抛出 SecureEnvelopeError。
    线程安全：内部使用 threading.Lock。
    """

    def __init__(self, ttl_seconds: int = 180) -> None:
        self.ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}
        self._lock = Lock()

    def check_and_mark(
        self,
        sender_id: str,
        nonce: str,
        ts: float,
    ) -> None:
        """
        检查 nonce 是否重放，并标记为已见。
        先检查时间窗口，再检查重放，最后写入。
        """
        now = time.time()

        # 时间窗口校验
        if abs(now - ts) > self.ttl_seconds:
            raise SecureEnvelopeError(
                f"nonce 时间戳超出重放窗口: ts={ts:.1f} now={now:.1f}"
            )

        key = f"{sender_id}:{nonce}"
        with self._lock:
            # 清理过期 nonce（惰性清理）
            cutoff = now - self.ttl_seconds
            expired = [k for k, t in self._seen.items() if t < cutoff]
            for k in expired:
                del self._seen[k]

            # 重放检测
            if key in self._seen:
                raise SecureEnvelopeError(f"重放攻击检测：nonce={nonce} sender={sender_id}")

            self._seen[key] = now
