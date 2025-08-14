#!/usr/bin/env python3
"""
Generate a human-readable progress dashboard from the machine registry.

Reads:
    - [`docs/progress/features.json`](docs/progress/features.json:1)

Writes:
    - [`docs/progress/dashboard.md`](docs/progress/dashboard.md:1) (default)

Usage examples:
    python scripts/progress/generate_dashboard.py
    python scripts/progress/generate_dashboard.py --input docs/progress/features.json --output docs/progress/dashboard.md

This script is intentionally minimal and uses only the Python standard library so
it can be run in CI or by local developer environments without extra dependencies.

The generator is safe for use by an AI assistant (Roo) or by a human developer:
- The input registry is a simple JSON array of feature objects (see repo file above).
- The output is a Markdown table summarizing items and a status summary.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List


def load_registry(path: Path) -> List[Dict[str, Any]]:
    """
    Load the machine-readable registry (JSON) from `path`.

    Args:
        path: Path to the JSON registry file.

    Returns:
        A list of feature dictionaries.

    Raises:
        FileNotFoundError: if the registry file does not exist.
        json.JSONDecodeError: if the file is not valid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"Registry not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def summarize(items: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Compute status counts for the provided items.

    Args:
        items: List of feature dicts.

    Returns:
        A mapping status -> count.
    """
    counts: Dict[str, int] = {}
    for it in items:
        status = (it.get("status") or "planned").lower()
        counts[status] = counts.get(status, 0) + 1
    return counts


def _escape_md(text: str) -> str:
    """Escape pipe characters for safe Markdown table cells."""
    return text.replace("|", "\\|") if isinstance(text, str) else str(text)


def render_markdown(items: List[Dict[str, Any]]) -> str:
    """
    Render a markdown dashboard from registry items.

    Args:
        items: List of feature dictionaries.

    Returns:
        Markdown content as a string.
    """
    counts = summarize(items)
    lines: List[str] = []
    lines.append("# Progress Dashboard")
    lines.append("")
    lines.append("Generated: " + datetime.utcnow().isoformat() + "Z")
    lines.append("")
    lines.append("## Summary")
    for status in ["planned", "in_progress", "partial", "done", "blocked", "deferred"]:
        lines.append(f"- {status.capitalize()}: {counts.get(status, 0)}")
    lines.append("")
    lines.append("## Items")
    lines.append("")
    lines.append("| ID | Title | Status | Next step | Last updated | Specs | Code |")
    lines.append("|---|---|---|---|---|---|---|")

    for it in items:
        id_ = _escape_md(str(it.get("id", "")))
        title = _escape_md(str(it.get("title", "")))
        status = _escape_md(str(it.get("status", "")))
        next_step = _escape_md(str(it.get("next_step", "")))
        last = _escape_md(str(it.get("last_updated", "")))
        spec_refs = it.get("spec_refs", []) or []
        code_refs = it.get("code_refs", []) or []
        # Render clickable short links for specs/code (filename shown, path as link)
        spec_links = ", ".join(f"[`{Path(s).name}`]({s})" for s in spec_refs)
        code_links = ", ".join(f"[`{Path(c).name}`]({c})" for c in code_refs)
        lines.append(f"| `{id_}` | {title} | {status} | {next_step} | {last} | {spec_links} | {code_links} |")

    return "\n".join(lines)


def write_dashboard(content: str, out_path: Path) -> None:
    """
    Write the generated markdown content to out_path, creating parent dirs.

    Args:
        content: Markdown content to write.
        out_path: Destination file path.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


def main() -> int:
    """
    Command-line entry point.

    Returns:
        Exit code (0 on success, non-zero on failure).
    """
    import argparse

    parser = argparse.ArgumentParser(description="Generate progress dashboard from registry.")
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path("docs/progress/features.json"),
        help="Path to the machine registry (JSON).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("docs/progress/dashboard.md"),
        help="Output markdown path for the generated dashboard.",
    )
    args = parser.parse_args()

    try:
        items = load_registry(args.input)
    except Exception as e:
        print(f"ERROR: Failed to load registry: {e}")
        return 2

    content = render_markdown(items)
    write_dashboard(content, args.output)
    print(f"Wrote dashboard to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())