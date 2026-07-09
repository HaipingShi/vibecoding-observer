"""Tests for profile contract and consulting output documentation."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_consulting_output_examples_cover_core_output_types() -> None:
    text = (ROOT / "docs" / "CONSULTING_OUTPUT_EXAMPLES.md").read_text()

    for output_type in [
        "project_start_prompt",
        "task_prompt_template",
        "mid_project_recovery_plan",
        "architecture_level_review",
        "agent_instructions_snippet",
    ]:
        assert f"## Example: {output_type}" in text
        assert f'"output_type": "{output_type}"' in text


def test_consulting_output_examples_include_consumption_rules() -> None:
    text = (ROOT / "docs" / "CONSULTING_OUTPUT_EXAMPLES.md").read_text()

    for required in [
        "Restate the selected route title",
        "Read `consulting_output.output_type`",
        "Use `consulting_output.sections`",
        "End with a short check against `completion_criteria`",
        "Do not present a fixed menu when dynamic routes are available",
    ]:
        assert required in text


def test_profile_contract_links_to_consulting_output_examples() -> None:
    text = (ROOT / "docs" / "PROFILE_CONTRACT.md").read_text()

    assert "CONSULTING_OUTPUT_EXAMPLES.md" in text


def test_profile_contract_documents_share_card_boundary() -> None:
    text = (ROOT / "docs" / "PROFILE_CONTRACT.md").read_text()

    assert "`share_card`" in text
    assert "optional `share-card.svg` export" in text
    assert "playful user-delivery wrapper" in text
    assert "Keep exaggeration playful" in text


def test_release_governance_documents_publication_boundaries() -> None:
    release = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    gitignore = (ROOT / ".gitignore").read_text()

    for text in [release, agents]:
        assert "vibecoding-observer" in text
        assert "observer" in text
        assert "agentlens" in text
        assert ".analysis-profile.json" in text

    for ignored in [
        ".agent/",
        ".coderail/",
        "coderail-output/",
        "project-template/",
        "e2e_output/",
        "my-report/",
    ]:
        assert ignored in gitignore


def test_readme_documents_diagnostic_consulting_flow() -> None:
    text = (ROOT / "README.md").read_text()

    for required in [
        "Section VII",
        "consulting_routes",
        "consulting_output.output_type",
        "项目启动 prompt",
        "中途恢复计划",
        "Profile 契约",
        "咨询产物示例",
    ]:
        assert required in text


def test_release_facing_docs_use_consistent_terms() -> None:
    docs = {
        "README.md": (ROOT / "README.md").read_text(),
        "SKILL.md": (ROOT / "SKILL.md").read_text(),
        "PROFILE_CONTRACT.md": (
            ROOT / "docs" / "PROFILE_CONTRACT.md"
        ).read_text(),
        "CONSULTING_OUTPUT_EXAMPLES.md": (
            ROOT / "docs" / "CONSULTING_OUTPUT_EXAMPLES.md"
        ).read_text(),
    }

    for text in docs.values():
        assert re.search(r"(?<!analysis-)profile\.json", text) is None
        assert ".analysis-profile.json" in text
        assert "consulting_routes" in text

    assert "18 labels" not in docs["README.md"]
    assert "28 labels" in docs["README.md"]
    assert "不要安装 PyPI\n上名为 `agentlens` 的包；它不是这个项目" in docs["README.md"]
    assert "agentlens` name is deprecated" in docs["README.md"]
    assert "consulting_output" in docs["PROFILE_CONTRACT.md"]
    assert "consulting_output" in docs["CONSULTING_OUTPUT_EXAMPLES.md"]


def test_docs_explain_agent_runtime_and_user_deliverable_split() -> None:
    readme = (ROOT / "README.md").read_text()
    skill = (ROOT / "SKILL.md").read_text()
    contract = (ROOT / "docs" / "PROFILE_CONTRACT.md").read_text()

    for text in [readme, skill, contract]:
        assert "state" in text
        assert "trace" in text
        assert "guide" in text

    assert "可阅读、可理解、可执行" in readme
    assert "hand back file paths" in skill
    assert "agent-facing substrate" in contract
    assert "user-facing deliverable" in contract
