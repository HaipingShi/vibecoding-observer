"""Redactor — sanitize text before it leaves the local machine.

If a future remote-LLM mode is enabled by explicit opt-in, only *fragments* of
anomalous events should be sent for explanation. Those fragments must never
leak:

  - Absolute file paths (reveal project structure / usernames)
  - Secrets (API keys, tokens, passwords)
  - Environment variable values
  - Personally identifiable information (emails, phone numbers)

The redactor replaces these with opaque placeholders BEFORE the text is
handed to the LLM client. The mapping is returned alongside the redacted
text so a user can audit what was sent (the "preview" capability).

Local mode: the redactor still runs (defense in depth), but nothing leaves
the process — the mapping is purely for the audit trail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["RedactionResult", "Redactor", "redact"]


# --------------------------------------------------------------------------- #
# Patterns (order matters: more specific first)
# --------------------------------------------------------------------------- #

# Absolute Unix paths: /Users/<user>/projects/foo → <PATH:projects/foo>
# We keep the last two segments as a hint (useful for analysis) but mask
# the username and root.
_PATH_RE = re.compile(r"/(?:Users|home|root)/[^/\s]+((?:/[^/\s]+){1,4})")

# API keys / tokens: common formats.
# - OpenAI-style: sk-... (40+ chars)
# - Generic hex/base64 tokens: 32+ hex chars
# - Bearer tokens
_API_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{20,}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.=]{20,}")
_HEX_TOKEN_RE = re.compile(r"\b[A-Fa-f0-9]{32,}\b")

# Environment variable assignments: KEY=VALUE (VALUE quoted or unquoted)
_ENV_ASSIGN_RE = re.compile(
    r"(?P<key>[A-Z][A-Z0-9_]{2,})=(?P<val>[^\s\"]+|\"[^\"]*\")"
)

# Email addresses.
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Phone numbers (loose: 11+ digits with optional separators).
_PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Output of a redaction pass."""

    redacted_text: str
    """The sanitized text safe to send to a remote LLM."""

    mapping: dict[str, str] = field(default_factory=dict)
    """original_fragment -> placeholder, for audit/preview."""

    @property
    def redaction_count(self) -> int:
        return len(self.mapping)


class Redactor:
    """Sanitize text fragments for remote LLM transmission.

    The redactor is stateless; each call is independent. The returned
    mapping lets the caller build a "preview" of what will be sent.
    """

    def redact(self, text: str) -> RedactionResult:
        """Return sanitized text plus the original→placeholder mapping."""
        mapping: dict[str, str] = {}
        result = text

        result = self._apply(result, _API_KEY_RE, "<API_KEY>", mapping)
        result = self._apply(result, _BEARER_RE, "<BEARER_TOKEN>", mapping)
        result = self._apply_paths(result, mapping)
        result = self._apply_env(result, mapping)
        result = self._apply(result, _HEX_TOKEN_RE, "<TOKEN>", mapping)
        result = self._apply(result, _EMAIL_RE, "<EMAIL>", mapping)
        result = self._apply(result, _PHONE_RE, "<PHONE>", mapping)

        return RedactionResult(redacted_text=result, mapping=mapping)

    def redact_many(self, texts: list[str]) -> list[RedactionResult]:
        """Redact a batch of fragments independently."""
        return [self.redact(t) for t in texts]

    # ----------------------------------------------------------------- #
    # Individual redactors
    # ----------------------------------------------------------------- #
    @staticmethod
    def _apply(
        text: str,
        pattern: re.Pattern[str],
        placeholder: str,
        mapping: dict[str, str],
    ) -> str:
        """Replace all matches with placeholder, recording originals."""
        found = pattern.findall(text)
        if not found:
            return text

        # For findall returning groups, take the full match instead.
        matches = list(pattern.finditer(text))
        for m in matches:
            original = m.group(0)
            if original not in mapping:
                mapping[original] = placeholder
        return pattern.sub(placeholder, text)

    @staticmethod
    def _apply_paths(text: str, mapping: dict[str, str]) -> str:
        """Mask absolute paths but keep the last two segments as a hint."""

        def _replace(m: re.Match[str]) -> str:
            tail = m.group(1)  # e.g. /projects/foo
            original = m.group(0)
            placeholder = f"<PATH:{tail}>"
            mapping[original] = placeholder
            return placeholder

        return _PATH_RE.sub(_replace, text)

    @staticmethod
    def _apply_env(text: str, mapping: dict[str, str]) -> str:
        """Mask environment variable values but keep the key name."""

        def _replace(m: re.Match[str]) -> str:
            key = m.group("key")
            original = m.group(0)
            placeholder = f"{key}=<ENV_VALUE>"
            mapping[original] = placeholder
            return placeholder

        return _ENV_ASSIGN_RE.sub(_replace, text)


# --------------------------------------------------------------------------- #
# Convenience
# --------------------------------------------------------------------------- #


def redact(text: str) -> RedactionResult:
    """One-shot redaction without instantiating."""
    return Redactor().redact(text)
