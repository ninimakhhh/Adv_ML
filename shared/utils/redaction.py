"""
PII redaction utility.

Detects and replaces:
  - Credit/debit card numbers (Luhn-validated)
  - CVV codes (3-4 digit codes after card-related keywords)
  - Passwords (text following password:/pwd:/pass= keywords)
  - US Social Security Numbers  (XXX-XX-XXXX)
  - IBANs  (2-letter country code + 2 digits + up to 34 alphanums)

Usage:
    from shared.utils.redaction import redact

    clean, events = redact("My card is 4111 1111 1111 1111 and SSN 123-45-6789")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RedactionEvent:
    kind: str        # CARD | CVV | PASSWORD | SSN | IBAN
    original: str
    replacement: str


# ---------------------------------------------------------------------------
# Luhn check
# ---------------------------------------------------------------------------

def _luhn_valid(digits: str) -> bool:
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Card: 16 digits in groups of 4 separated by spaces or hyphens
_CARD_RE = re.compile(
    r'\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b'
)

# CVV: 3-4 digits following card-security keywords
_CVV_RE = re.compile(
    r'(?:cvv|cvc|cvv2|security\s*code)\s*[:\s=]+(\d{3,4})\b',
    re.IGNORECASE,
)

# Password after common keywords
_PWD_RE = re.compile(
    r'(?:password|passwd|pwd|pass)\s*[:\s=]+(\S+)',
    re.IGNORECASE,
)

# US SSN: 123-45-6789
_SSN_RE = re.compile(r'\b(\d{3}-\d{2}-\d{4})\b')

# IBAN: e.g. PT50 0002 0123 1234 5678 9015 4
_IBAN_RE = re.compile(
    r'\b([A-Z]{2}\d{2}[A-Z0-9](?:\s?[A-Z0-9]{4}){2,8})\b'
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def redact(text: str) -> tuple[str, list[RedactionEvent]]:
    """Return (redacted_text, list_of_events)."""
    events: list[RedactionEvent] = []

    # 1 — Cards (Luhn-validated)
    def _replace_card(m: re.Match) -> str:
        raw = m.group(1)
        digits = re.sub(r'[\s\-]', '', raw)
        if len(digits) == 16 and _luhn_valid(digits):
            events.append(RedactionEvent("CARD", raw, "[CARD_REDACTED]"))
            return "[CARD_REDACTED]"
        return raw

    text = _CARD_RE.sub(_replace_card, text)

    # 2 — CVV
    def _replace_cvv(m: re.Match) -> str:
        full = m.group(0)
        code = m.group(1)
        replacement = full.replace(code, "[CVV_REDACTED]")
        events.append(RedactionEvent("CVV", code, "[CVV_REDACTED]"))
        return replacement

    text = _CVV_RE.sub(_replace_cvv, text)

    # 3 — Passwords
    def _replace_pwd(m: re.Match) -> str:
        full = m.group(0)
        secret = m.group(1)
        replacement = full.replace(secret, "[PASSWORD_REDACTED]")
        events.append(RedactionEvent("PASSWORD", secret, "[PASSWORD_REDACTED]"))
        return replacement

    text = _PWD_RE.sub(_replace_pwd, text)

    # 4 — SSN
    def _replace_ssn(m: re.Match) -> str:
        events.append(RedactionEvent("SSN", m.group(1), "[SSN_REDACTED]"))
        return "[SSN_REDACTED]"

    text = _SSN_RE.sub(_replace_ssn, text)

    # 5 — IBAN
    def _replace_iban(m: re.Match) -> str:
        raw = m.group(1)
        digits_only = re.sub(r'\s', '', raw)
        if len(digits_only) >= 15:
            events.append(RedactionEvent("IBAN", raw, "[IBAN_REDACTED]"))
            return "[IBAN_REDACTED]"
        return raw

    text = _IBAN_RE.sub(_replace_iban, text)

    return text, events
