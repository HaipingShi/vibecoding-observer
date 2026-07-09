"""Project-local signal profile configuration.

The core analyzer recognizes generic engineering events. This module loads a
small project dialect file, when present, and converts it into additional
``SignalProfile`` rules without requiring a YAML dependency.
"""

from __future__ import annotations

import fnmatch
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from observer.event_signals import (
    CODE_RAIL_PROFILE,
    DEFAULT_PROFILES,
    SignalProfile,
    compile_signal_patterns,
)

__all__ = ["SignalConfig", "load_signal_config"]

_CONFIG_NAMES = ("observer.yaml", ".observer.yaml", "observer.json", "observer.toml")
_BUILTIN_PROFILES = {"coderail": CODE_RAIL_PROFILE}
_CODERAIL_MARKERS = (
    ".coderail",
    "docs/TRACELOG.jsonl",
    "docs/TRACE_INDEX.md",
    "scripts/done_gate.py",
    "scripts/trace_event.py",
    "scripts/trace_index.py",
)


@dataclass(frozen=True, slots=True)
class SignalConfig:
    """Resolved signal profiles for one project."""

    profiles: tuple[SignalProfile, ...]
    source_path: str | None
    profile_names: tuple[str, ...]
    custom_rule_keys: tuple[str, ...]
    unrecognized_keys: tuple[str, ...] = ()
    auto_detected_profiles: tuple[str, ...] = ()

    @property
    def confidence_hint(self) -> str:
        if self.source_path:
            return "high"
        if self.auto_detected_profiles:
            return "medium"
        return "low"

    def to_dict(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "profile_names": list(self.profile_names),
            "custom_rule_keys": list(self.custom_rule_keys),
            "unrecognized_keys": list(self.unrecognized_keys),
            "auto_detected_profiles": list(self.auto_detected_profiles),
            "confidence_hint": self.confidence_hint,
        }


def load_signal_config(project_path: str | Path | None) -> SignalConfig:
    """Load project-specific signal profiles, falling back to generic rules."""
    root = Path(project_path).expanduser().resolve() if project_path else None
    config_path = _find_config(root)
    raw = _read_config(config_path) if config_path else {}
    observer = _observer_section(raw)

    profiles = list(DEFAULT_PROFILES)
    selected_profile_names: list[str] = [profile.name for profile in profiles]
    auto_detected: list[str] = []

    for name in _selected_builtin_profiles(observer):
        if name in _BUILTIN_PROFILES and name not in selected_profile_names:
            profiles.append(_BUILTIN_PROFILES[name])
            selected_profile_names.append(name)

    if not config_path and root and _looks_like_coderail_project(root):
        profiles.append(CODE_RAIL_PROFILE)
        selected_profile_names.append(CODE_RAIL_PROFILE.name)
        auto_detected.append(CODE_RAIL_PROFILE.name)

    custom_profile, custom_keys, unknown_keys = _custom_profile(observer)
    if custom_profile:
        profiles.append(custom_profile)
        selected_profile_names.append(custom_profile.name)

    return SignalConfig(
        profiles=tuple(profiles),
        source_path=str(config_path) if config_path else None,
        profile_names=tuple(selected_profile_names),
        custom_rule_keys=tuple(custom_keys),
        unrecognized_keys=tuple(unknown_keys),
        auto_detected_profiles=tuple(auto_detected),
    )


def _find_config(root: Path | None) -> Path | None:
    if root is None or not root.exists():
        return None
    for name in _CONFIG_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def _read_config(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix == ".toml":
        return tomllib.loads(path.read_text(encoding="utf-8"))
    return _read_yaml_subset(path)


def _read_yaml_subset(path: Path) -> dict[str, Any]:
    """Parse the small observer.yaml subset used for project signal profiles."""
    result: dict[str, Any] = {}
    current_section: dict[str, Any] | None = result
    current_key: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped.endswith(":"):
            key = stripped[:-1].strip()
            result.setdefault(key, {})
            current_section = result[key] if isinstance(result[key], dict) else result
            current_key = None
            continue

        if current_section is None:
            continue

        if stripped.startswith("- ") and current_key:
            value = _clean_scalar(stripped[2:])
            current_section.setdefault(current_key, [])
            if isinstance(current_section[current_key], list):
                current_section[current_key].append(value)
            continue

        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            current_section[key] = _parse_scalar_or_list(value)
            current_key = None
        else:
            current_section[key] = []
            current_key = key

    return result


def _observer_section(raw: dict[str, Any]) -> dict[str, Any]:
    section = raw.get("observer", raw)
    return section if isinstance(section, dict) else {}


def _selected_builtin_profiles(observer: dict[str, Any]) -> tuple[str, ...]:
    selected: list[str] = []
    for key in ("governance_profile", "profile", "profiles"):
        value = observer.get(key)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and item.strip().lower() in _BUILTIN_PROFILES:
                selected.append(item.strip().lower())
    return tuple(dict.fromkeys(selected))


def _custom_profile(
    observer: dict[str, Any],
) -> tuple[SignalProfile | None, list[str], list[str]]:
    key_map = {
        "docs_as_artifacts": "design_artifact_patterns",
        "design_artifacts": "design_artifact_patterns",
        "artifact_patterns": "design_artifact_patterns",
        "verify_commands": "verification_patterns",
        "verification_commands": "verification_patterns",
        "verification_markers": "verification_patterns",
        "governance_markers": "governance_patterns",
        "task_markers": "governance_patterns",
        "constraint_markers": "governance_patterns",
        "persistence_markers": "persistence_patterns",
        "closure_markers": "closure_patterns",
        "handoff_markers": "handoff_patterns",
        "generated_ignore": "ignore_patterns",
        "external_readonly": "ignore_patterns",
        "ignore_patterns": "ignore_patterns",
    }
    allowed_metadata = {"project_type", "governance_profile", "profile", "profiles"}
    buckets: dict[str, list[str]] = {}
    custom_keys: list[str] = []
    unknown_keys: list[str] = []

    for key, value in observer.items():
        target = key_map.get(key)
        if not target:
            if key not in allowed_metadata:
                unknown_keys.append(str(key))
            continue
        values = _as_list(value)
        if not values:
            continue
        buckets.setdefault(target, []).extend(values)
        custom_keys.append(key)

    if not buckets:
        return None, custom_keys, unknown_keys

    profile = SignalProfile(
        name="project_config",
        design_artifact_patterns=_compile_config_patterns(buckets.get("design_artifact_patterns", [])),
        verification_patterns=_compile_config_patterns(buckets.get("verification_patterns", [])),
        governance_patterns=_compile_config_patterns(buckets.get("governance_patterns", [])),
        persistence_patterns=_compile_config_patterns(buckets.get("persistence_patterns", [])),
        closure_patterns=_compile_config_patterns(buckets.get("closure_patterns", [])),
        handoff_patterns=_compile_config_patterns(buckets.get("handoff_patterns", [])),
        ignore_patterns=_compile_config_patterns(buckets.get("ignore_patterns", [])),
    )
    return profile, custom_keys, unknown_keys


def _compile_config_patterns(values: list[str]) -> tuple[re.Pattern[str], ...]:
    return compile_signal_patterns(*[_pattern_from_value(value) for value in values])


def _pattern_from_value(value: str) -> str:
    if any(ch in value for ch in "*?["):
        return fnmatch.translate(value)
    return re.escape(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _parse_scalar_or_list(value: str) -> str | list[str]:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_clean_scalar(item) for item in inner.split(",")]
    return _clean_scalar(value)


def _clean_scalar(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _looks_like_coderail_project(root: Path) -> bool:
    return any((root / marker).exists() for marker in _CODERAIL_MARKERS)
