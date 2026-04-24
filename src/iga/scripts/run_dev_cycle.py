"""
Standalone runner — trigger one DevAgent development cycle.

Usage:
    PYTHONPATH=src python -m iga.scripts.run_dev_cycle

The DevAgent will:
1. Scan the entire IGA codebase
2. Find TODOs, missing tests, stub functions, gaps
3. Ask Claude what to implement next
4. Claude writes the code
5. pytest runs — if green, git commit + push
6. Print a summary of what changed
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Silence SQLAlchemy INFO spam
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


async def main() -> None:
    from iga.agents.dev_agent import DevAgent, REPO_ROOT
    import structlog

    log = structlog.get_logger("dev_runner")

    dry_run = os.environ.get("AGENT_DRY_RUN", "true").lower() == "true"
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key or api_key == "test":
        print("WARNING: ANTHROPIC_API_KEY not set or is placeholder.")
        print("         Set a real key to enable AI code generation.")
        print("         Continuing in dry-run/demo mode...\n")

    print("=" * 65)
    print("  DevAgent — Autonomous IGA Development Cycle")
    print(f"  Repo   : {REPO_ROOT}")
    print(f"  Model  : {os.environ.get('AGENT_MODEL','claude-sonnet-4-6')}")
    print(f"  Dry run: {dry_run}")
    print("=" * 65)
    print()

    agent = DevAgent()

    # Step 1: Scan
    print("[ 1/4 ] Scanning codebase...")
    snapshot = agent._scan_codebase()
    print(f"        Files  : {len(snapshot.files)}")
    print(f"        Lines  : {snapshot.total_lines:,}")
    print(f"        TODOs  : {len(snapshot.todos)}")
    print(f"        Stubs  : {len(snapshot.stub_functions)}")
    print(f"        No tests: {len(snapshot.missing_tests)}")
    if snapshot.todos:
        print("\n        Top TODOs:")
        for t in snapshot.todos[:5]:
            print(f"          {t['file']}:{t['line']} → {t['text'][:70]}")
    print()

    # Step 2–4: Ask Claude → write code → test → commit
    print("[ 2/4 ] Asking Claude what to implement next...")
    if not api_key or api_key == "test":
        print("        (Skipping AI call — no real API key)")
        print()
        print("[ 3/4 ] Tests: skipped (no code generated)")
        print()
        print("[ 4/4 ] Commit: skipped")
        print()
        print("─" * 65)
        print("  Set ANTHROPIC_API_KEY=sk-ant-... and re-run to enable")
        print("  autonomous code generation, testing, and pushing.")
        return

    result = await agent.run()
    print()
    print("[ 3/4 ] Running tests...")
    print()
    print("[ 4/4 ] Committing and pushing...")
    print()
    print("=" * 65)
    print(f"  Status  : {'SUCCESS' if result.success else 'FAILED'}")
    print(f"  Scanned : {result.items_processed} files")
    print(f"  Changed : {result.items_actioned} files")
    print(f"  Duration: {result.duration_seconds:.1f}s")
    if result.errors:
        print(f"  Errors  : {result.errors}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
