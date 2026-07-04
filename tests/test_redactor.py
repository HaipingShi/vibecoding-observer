"""Tests for the Redactor (privacy sanitization).

Validates that paths, secrets, env vars, emails, and phones are masked
before text leaves the machine.
"""

from __future__ import annotations

from observer.redactor import Redactor, redact


class TestPathRedaction:
    def test_unix_path_masked(self) -> None:
        result = redact("edit /Users/example/projects/foo/main.py")
        assert "/Users/example" not in result.redacted_text
        assert "<PATH:" in result.redacted_text

    def test_path_hint_preserved(self) -> None:
        result = redact("reading /Users/example/projects/foo/config.toml")
        # The last segments are kept as a hint.
        assert "foo" in result.redacted_text or "<PATH:" in result.redacted_text

    def test_non_absolute_path_not_touched(self) -> None:
        result = redact("open src/main.py")
        assert result.redacted_text == "open src/main.py"


class TestSecretRedaction:
    def test_openai_key_masked(self) -> None:
        result = redact("key is sk-1234567890abcdefghijklmnopqrstuv")
        assert "sk-1234" not in result.redacted_text
        assert "<API_KEY>" in result.redacted_text

    def test_bearer_token_masked(self) -> None:
        result = redact("Authorization: Bearer abc123def456ghi789jkl012mno345pqr789")
        assert "abc123def" not in result.redacted_text
        assert "<BEARER_TOKEN>" in result.redacted_text

    def test_hex_token_masked(self) -> None:
        result = redact("token: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
        assert "a1b2c3d4" not in result.redacted_text
        assert "<TOKEN>" in result.redacted_text


class TestEnvVarRedaction:
    def test_env_value_masked(self) -> None:
        result = redact("DATABASE_URL=postgres://localhost/mydb")
        assert "postgres://localhost/mydb" not in result.redacted_text
        assert "<ENV_VALUE>" in result.redacted_text
        assert "DATABASE_URL" in result.redacted_text  # key kept

    def test_lowercase_var_not_touched(self) -> None:
        result = redact("path=src/main.py")
        assert result.redacted_text == "path=src/main.py"


class TestPIIRedaction:
    def test_email_masked(self) -> None:
        result = redact("contact person@example.com for details")
        assert "person@example.com" not in result.redacted_text
        assert "<EMAIL>" in result.redacted_text

    def test_phone_masked(self) -> None:
        result = redact("call 13800138000")
        assert "13800138000" not in result.redacted_text
        assert "<PHONE>" in result.redacted_text


class TestMapping:
    def test_mapping_populated(self) -> None:
        result = redact("/Users/example/projects/foo and sk-secret12345678901234567890")
        assert len(result.mapping) >= 2
        assert result.redaction_count >= 2

    def test_clean_text_no_redactions(self) -> None:
        result = redact("just some normal text about code")
        assert result.redaction_count == 0
        assert result.redacted_text == "just some normal text about code"


class TestBatchRedaction:
    def test_redact_many(self) -> None:
        r = Redactor()
        results = r.redact_many(["/Users/example/x", "normal text"])
        assert len(results) == 2
        assert results[0].redaction_count >= 1
        assert results[1].redaction_count == 0
