# docs_renderer.py
#
# Builds the "Available tools" HTML table for the /docs page from the live MCP
# registry, joined against docs/tool_examples.yaml. Rendered once at
# create_app() startup; cached as a module-level string and injected into
# templates/partials/_docs_content.html as a Jinja variable.
#
# The whole point of this module is the startup-fail guardrail: if a tool is in
# mcp_tools.TOOLS but has no entry in tool_examples.yaml (or vice-versa), we
# raise at app boot. This is the invariant that keeps /docs from silently going
# stale when tools are added, renamed, or removed.
from __future__ import annotations

from html import escape
from pathlib import Path

import yaml

from mcp_tools import TOOLS

TOOL_EXAMPLES_PATH = Path(__file__).parent / "docs" / "tool_examples.yaml"


class DocsExampleDrift(RuntimeError):
    """Raised when docs/tool_examples.yaml does not match mcp_tools.TOOLS."""


def _load_examples(path: Path = TOOL_EXAMPLES_PATH) -> dict[str, dict]:
    if not path.exists():
        raise DocsExampleDrift(
            f"docs/tool_examples.yaml not found at {path}. Every MCP tool must "
            f"have an example prompt; see the docstring at the top of the file."
        )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise DocsExampleDrift(
            f"docs/tool_examples.yaml must be a mapping at the top level, got "
            f"{type(data).__name__}."
        )
    return data


def _validate_against_registry(examples: dict[str, dict]) -> None:
    """Hard-fail invariant: every tool has an example and every example has a tool."""
    registered = set(TOOLS.keys())
    documented = set(examples.keys())

    missing_examples = registered - documented
    if missing_examples:
        raise DocsExampleDrift(
            "These MCP tools are registered in mcp_tools.TOOLS but have no "
            "example prompt in docs/tool_examples.yaml: "
            f"{sorted(missing_examples)}. Add an entry per tool with an "
            "'example_prompt' field."
        )

    extra_examples = documented - registered
    if extra_examples:
        raise DocsExampleDrift(
            "docs/tool_examples.yaml has entries for tools that are NOT in "
            f"mcp_tools.TOOLS: {sorted(extra_examples)}. Either register the "
            "tool or remove the example entry."
        )

    for tool_name, entry in examples.items():
        if not isinstance(entry, dict) or not entry.get("example_prompt"):
            raise DocsExampleDrift(
                f"docs/tool_examples.yaml entry for '{tool_name}' must be a "
                f"mapping with a non-empty 'example_prompt' field."
            )


def _render_table(examples: dict[str, dict]) -> str:
    """Render the cached HTML for the Available-tools table body.

    Returns the <tbody> rows only — _docs_content.html owns the <table>, <thead>,
    and surrounding chrome so any style tweaks stay in the template.
    """
    rows: list[str] = []
    # Iterate via TOOLS so display order matches the registry, not YAML order.
    for tool_name, spec in TOOLS.items():
        example = examples[tool_name]["example_prompt"].strip()
        rows.append(
            "<tr>"
            f"<td><code>{escape(spec.name)}</code><br><small>{escape(spec.title)}</small></td>"
            f"<td>{escape(spec.description)}</td>"
            f"<td><em>&ldquo;{escape(example)}&rdquo;</em></td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_tools_table_html() -> str:
    """Load + validate + render. Raises DocsExampleDrift on any mismatch."""
    examples = _load_examples()
    _validate_against_registry(examples)
    return _render_table(examples)
