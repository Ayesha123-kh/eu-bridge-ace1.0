"""Accounts and sessions using only the standard library."""
import hashlib
import hmac
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.db import connect

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SESSION_DAYS = 14


class AuthError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    return f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        return hmac.compare_digest(_scrypt(password, bytes.fromhex(salt)).hex(), digest)
    except ValueError:
        return False


def _public(row) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row["name"]}


def signup(name: str, email: str, password: str) -> dict:
    name, email = (name or "").strip(), (email or "").strip().lower()
    if not 2 <= len(name) <= 80:
        raise AuthError("Enter your full name (2 to 80 characters).")
    if not EMAIL_RE.match(email) or len(email) > 200:
        raise AuthError("Enter a valid email address.")
    if len(password or "") < 8:
        raise AuthError("Use a password of at least 8 characters.")
    conn = connect()
    try:
        if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise AuthError("An account with this email already exists. Sign in instead.")
        uid = str(uuid.uuid4())
        conn.execute("INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?,?,?,?,?)",
                     (uid, email, name, hash_password(password), _now().isoformat()))
        conn.commit()
        return {"id": uid, "email": email, "name": name}
    finally:
        conn.close()


def login(email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    finally:
        conn.close()
    stored = row["password_hash"] if row else hash_password("not-a-real-password")
    ok = verify_password(password or "", stored)
    if not row or not ok:
        raise AuthError("Email or password is incorrect.")
    return _public(row)


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    conn = connect()
    try:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now().isoformat(),))
        conn.execute("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?,?,?)",
                     (hashlib.sha256(token.encode()).hexdigest(), user_id,
                      (_now() + timedelta(days=SESSION_DAYS)).isoformat()))
        conn.commit()
    finally:
        conn.close()
    return token


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    conn = connect()
    try:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash=? AND s.expires_at > ?",
            (hashlib.sha256(token.encode()).hexdigest(), _now().isoformat())).fetchone()
        return _public(row) if row else None
    finally:
        conn.close()


def end_session(token: str | None) -> None:
    if not token:
        return
    conn = connect()
    try:
        conn.execute("DELETE FROM sessions WHERE token_hash=?",
                     (hashlib.sha256(token.encode()).hexdigest(),))
        conn.commit()
    finally:
        conn.close()


def claim_guest_scans(guest_id: str, user_id: str) -> int:
    """Move scans made as a guest into the account that just signed in."""
    conn = connect()
    try:
        n = conn.execute("UPDATE scans SET owner=? WHERE owner=?",
                         (f"u:{user_id}", f"g:{guest_id}")).rowcount
        conn.commit()
        return n
    finally:
        conn.close()
