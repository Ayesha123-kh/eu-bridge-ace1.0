"""Mask secrets before any code leaves this server for the AI provider."""
import re

_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED PRIVATE KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "[REDACTED]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}|\bgh[pousr]_[A-Za-z0-9]{30,}"), "[REDACTED]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED]"),
    (re.compile(r"""(?i)((?:api[_-]?key|secret|token|passw(?:or)?d)\s*[:=]\s*['"])([^'"\n]{8,})(['"])"""),
     r"\1[REDACTED]\3"),
]


def redact(text: str) -> tuple[str, int]:
    """Returns (masked_text, number_of_secrets_masked)."""
    total = 0
    for rx, repl in _PATTERNS:
        text, n = rx.subn(repl, text)
        total += n
    return text, total
