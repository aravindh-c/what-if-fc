"""Export the moment workflow graph as a Mermaid diagram.

Usage:
    python -m scripts.export_workflow_diagram

Writes docs/workflow.mmd.
"""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    from agent_framework import WorkflowViz

    from agents.workflow import _build_workflow

    workflow = _build_workflow(client=None, kql=None, timeout_s=30.0)
    mermaid = WorkflowViz(workflow).to_mermaid()

    out = Path(__file__).parent.parent / "docs" / "workflow.mmd"
    out.write_text(mermaid, encoding="utf-8")
    print(f"Written: {out}")
    print(mermaid)


if __name__ == "__main__":
    main()
