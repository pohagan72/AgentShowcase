# tests/test_docs_renderer.py
#
# Unit tests for the /docs Available-tools table renderer. The single most
# important behavior under test is the startup-fail guardrail: if the live MCP
# registry and docs/tool_examples.yaml fall out of sync, create_app() must
# raise — that's the invariant that keeps /docs from silently drifting.
import pytest
import yaml

from docs_renderer import (
    DocsExampleDrift,
    _render_table,
    _validate_against_registry,
)
from mcp_tools import TOOLS


def _all_tool_names_examples() -> dict[str, dict]:
    """Return a fully-valid examples dict matching the live registry."""
    return {name: {"example_prompt": f"do something with {name}"} for name in TOOLS}


def test_validate_happy_path_does_not_raise():
    _validate_against_registry(_all_tool_names_examples())


def test_validate_raises_when_tool_missing_example():
    examples = _all_tool_names_examples()
    a_tool = next(iter(examples))
    del examples[a_tool]
    with pytest.raises(DocsExampleDrift) as exc:
        _validate_against_registry(examples)
    assert a_tool in str(exc.value)


def test_validate_raises_when_yaml_has_unregistered_tool():
    examples = _all_tool_names_examples()
    examples["ghost_tool"] = {"example_prompt": "this tool does not exist"}
    with pytest.raises(DocsExampleDrift) as exc:
        _validate_against_registry(examples)
    assert "ghost_tool" in str(exc.value)


def test_validate_raises_on_missing_example_prompt_field():
    examples = _all_tool_names_examples()
    a_tool = next(iter(examples))
    examples[a_tool] = {"some_other_field": "x"}
    with pytest.raises(DocsExampleDrift) as exc:
        _validate_against_registry(examples)
    assert a_tool in str(exc.value)


def test_validate_raises_on_empty_example_prompt():
    examples = _all_tool_names_examples()
    a_tool = next(iter(examples))
    examples[a_tool] = {"example_prompt": ""}
    with pytest.raises(DocsExampleDrift):
        _validate_against_registry(examples)


def test_render_table_includes_every_tool_in_registry_order():
    """Table iterates via TOOLS so the rendered order matches the registry
    declaration, not YAML key order. Smoke-check the first and last."""
    html = _render_table(_all_tool_names_examples())
    for name in TOOLS:
        assert f"<code>{name}</code>" in html

    # Order check: first registered tool appears before the last.
    names = list(TOOLS)
    first_pos = html.index(f"<code>{names[0]}</code>")
    last_pos = html.index(f"<code>{names[-1]}</code>")
    assert first_pos < last_pos


def test_render_table_escapes_html_in_example_prompt():
    """If a prompt ever contains <script> or similar, the renderer must escape
    it so /docs doesn't become an XSS surface."""
    examples = _all_tool_names_examples()
    a_tool = next(iter(examples))
    examples[a_tool] = {"example_prompt": '<script>alert("x")</script>'}
    html = _render_table(examples)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_live_yaml_matches_registry(tmp_path):
    """End-to-end check against the real docs/tool_examples.yaml on disk.
    If this fails, the YAML has drifted from mcp_tools.TOOLS and create_app()
    will refuse to boot in production. Same outcome as the create_app() boot,
    but with a clearer failure message at unit-test time."""
    from docs_renderer import _load_examples

    examples = _load_examples()
    _validate_against_registry(examples)
