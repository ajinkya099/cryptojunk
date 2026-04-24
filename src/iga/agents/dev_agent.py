"""
DevAgent — Autonomous IGA codebase development agent.

Every run cycle:
1. Scans the entire codebase for TODOs, gaps, and missing implementations
2. Asks Claude what to build / improve next
3. Claude writes the actual code
4. Tests are run — if they pass, changes are committed and pushed
5. Repeat on next schedule
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog

from iga.agents.base import AgentResult, BaseAgent
from iga.config import settings

logger = structlog.get_logger("agent.dev")

REPO_ROOT = Path(__file__).parent.parent.parent.parent  # /repo root

DEV_SYSTEM_PROMPT = """
You are DevAgent, an autonomous software engineer working on the IGA AI Framework.

Your job is to continuously improve this Python codebase by:
1. Implementing missing features (look for TODO/FIXME/NotImplemented)
2. Adding missing test coverage
3. Improving error handling
4. Filling in stub implementations
5. Adding new IGA features that make sense given the domain

The IGA system manages:
- Identity lifecycle (Joiner/Mover/Leaver)
- Access certification campaigns
- Role mining and RBAC management
- Segregation of Duties detection

Rules you MUST follow:
- Return a JSON object with file changes — do NOT return prose explanations
- Only change Python files under src/ or tests/
- Every change must keep the test suite green
- Prefer small, focused improvements over large rewrites
- Never break existing interfaces
- Add docstrings only where truly non-obvious
- Keep code idiomatic Python 3.11+

Response format (strict JSON):
{
  "summary": "one sentence describing what was built",
  "changes": [
    {
      "path": "src/iga/...",
      "action": "create|modify|delete",
      "content": "full file content as a string",
      "reason": "why this change"
    }
  ],
  "tests_to_run": ["tests/test_..."],
  "next_suggested_task": "what to build after this"
}
"""


@dataclass
class CodebaseSnapshot:
    """A snapshot of the current state of the codebase."""
    files: dict[str, str] = field(default_factory=dict)        # path → content
    todos: list[dict] = field(default_factory=list)             # {file, line, text}
    missing_tests: list[str] = field(default_factory=list)      # modules with no tests
    stub_functions: list[dict] = field(default_factory=list)    # {file, func, line}
    total_lines: int = 0
    test_coverage_pct: float = 0.0


@dataclass
class DevCycleResult:
    """Result of one autonomous development cycle."""
    success: bool
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    tests_passed: bool = False
    committed: bool = False
    pushed: bool = False
    errors: list[str] = field(default_factory=list)
    next_task: str = ""
    duration_seconds: float = 0.0


class DevAgent(BaseAgent):
    """
    Autonomous development agent that continuously improves the IGA codebase.

    Schedule: runs on demand or via Celery Beat.
    Each cycle: scan → analyze → generate → test → commit → push.
    """

    def __init__(self) -> None:
        super().__init__(
            name="dev_agent",
            description="Autonomous code writer — scans codebase, implements improvements, commits",
        )
        self.repo_root = REPO_ROOT
        self.src_root = REPO_ROOT / "src" / "iga"
        self.tests_root = REPO_ROOT / "tests"

    async def run(self) -> AgentResult:
        import time
        start = self._start_run()
        result = AgentResult(agent_name=self.name, success=True, dry_run=self.dry_run)

        try:
            # 1. Scan codebase
            self.log.info("dev_cycle_start", step="scan")
            snapshot = self._scan_codebase()
            result.items_processed = len(snapshot.files)

            # 2. Ask Claude what to build
            self.log.info("dev_cycle_start", step="analyze", todos=len(snapshot.todos),
                         stubs=len(snapshot.stub_functions))
            cycle = await self._run_dev_cycle(snapshot)

            if not cycle.success:
                result.success = False
                result.errors.extend(cycle.errors)
                return self._end_run(result, start)

            result.items_actioned = len(cycle.files_changed)
            self.log.info("dev_cycle_result", summary=cycle.summary,
                         files=cycle.files_changed, tests_passed=cycle.tests_passed,
                         committed=cycle.committed)

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            self.log.error("dev_agent_error", error=str(e))

        return self._end_run(result, start)

    # ── Codebase Scanning ────────────────────────────────────────────

    def _scan_codebase(self) -> CodebaseSnapshot:
        """Read all Python source files and extract signals for Claude."""
        snap = CodebaseSnapshot()

        for py_file in sorted(self.src_root.rglob("*.py")):
            rel = str(py_file.relative_to(self.repo_root))
            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception:
                continue

            snap.files[rel] = content
            snap.total_lines += content.count("\n")

            # Find TODO / FIXME / NotImplemented
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if any(marker in stripped for marker in ("TODO", "FIXME", "# TODO", "# FIXME")):
                    snap.todos.append({"file": rel, "line": i, "text": stripped})
                if "raise NotImplementedError" in stripped:
                    snap.todos.append({"file": rel, "line": i, "text": f"NotImplemented: {stripped}"})

            # Find stub functions (pass-only or empty bodies)
            snap.stub_functions.extend(self._find_stubs(rel, content))

        # Find modules with no corresponding test file
        for rel_path in snap.files:
            module = Path(rel_path).stem
            test_path = self.tests_root / f"test_{module}.py"
            test_path2 = self.tests_root / "test_api" / f"test_{module}.py"
            test_path3 = self.tests_root / "test_services" / f"test_{module}.py"
            if not any(p.exists() for p in [test_path, test_path2, test_path3]):
                snap.missing_tests.append(rel_path)

        return snap

    def _find_stubs(self, path: str, content: str) -> list[dict]:
        """Find functions that are stubs (body is just pass or ...)."""
        stubs = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = node.body
                    # Single-statement body that is just pass or Ellipsis
                    if len(body) == 1:
                        stmt = body[0]
                        if isinstance(stmt, ast.Pass):
                            stubs.append({"file": path, "func": node.name, "line": node.lineno})
                        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                            if stmt.value.value is ...:
                                stubs.append({"file": path, "func": node.name, "line": node.lineno})
        except SyntaxError:
            pass
        return stubs

    # ── Dev Cycle ────────────────────────────────────────────────────

    async def _run_dev_cycle(self, snapshot: CodebaseSnapshot) -> DevCycleResult:
        """Ask Claude to analyze the codebase and produce code changes."""
        cycle = DevCycleResult(success=False)

        # Build a focused context for Claude (not the entire codebase — too big)
        context = self._build_context(snapshot)

        user_prompt = f"""
Current IGA codebase state:
- Source files: {len(snapshot.files)}
- Total lines: {snapshot.total_lines:,}
- TODOs/FIXMEs: {len(snapshot.todos)}
- Stub functions: {len(snapshot.stub_functions)}
- Modules without tests: {len(snapshot.missing_tests)}

TODOs found:
{json.dumps(snapshot.todos[:10], indent=2)}

Stub functions found:
{json.dumps(snapshot.stub_functions[:10], indent=2)}

Modules missing tests:
{json.dumps(snapshot.missing_tests[:8], indent=2)}

Relevant source files (key parts):
{context}

Pick ONE focused improvement to implement right now.
Prefer: fixing TODOs > adding tests > adding missing features.
Return the strict JSON format described in your system prompt.
"""
        try:
            raw = await self.ask_claude(DEV_SYSTEM_PROMPT, user_prompt, expect_json=True)
            parsed = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            cycle.errors.append(f"Claude response parse error: {e}")
            return cycle

        changes = parsed.get("changes", [])
        cycle.summary = parsed.get("summary", "")
        cycle.next_task = parsed.get("next_suggested_task", "")

        if not changes:
            cycle.success = True  # Claude had nothing to do
            cycle.summary = "No improvements needed this cycle"
            return cycle

        # Apply changes
        applied = self._apply_changes(changes)
        cycle.files_changed = applied

        # Run tests
        cycle.tests_passed = self._run_tests(parsed.get("tests_to_run"))

        if not cycle.tests_passed:
            self.log.warning("dev_cycle_tests_failed", reverting=True)
            self._revert_changes(applied)
            cycle.errors.append("Tests failed — changes reverted")
            return cycle

        # Commit and push
        if not self.dry_run:
            cycle.committed, cycle.pushed = self._git_commit_push(cycle.summary, applied)
        else:
            self.log.info("dev_cycle_dry_run", files=applied, summary=cycle.summary)
            cycle.committed = False
            cycle.pushed = False

        cycle.success = True
        return cycle

    def _build_context(self, snapshot: CodebaseSnapshot) -> str:
        """Build a condensed context string for Claude — key files only."""
        priority_files = [
            "src/iga/agents/base.py",
            "src/iga/agents/lifecycle.py",
            "src/iga/services/lifecycle.py",
            "src/iga/services/sod.py",
            "src/iga/api/agents.py",
            "src/iga/workers/tasks.py",
        ]
        lines = []
        for path in priority_files:
            if path in snapshot.files:
                content = snapshot.files[path]
                # Trim to first 60 lines for context budget
                preview = "\n".join(content.splitlines()[:60])
                lines.append(f"\n### {path}\n```python\n{preview}\n...\n```")
        return "\n".join(lines)

    # ── File Operations ──────────────────────────────────────────────

    def _apply_changes(self, changes: list[dict]) -> list[str]:
        """Write Claude's code changes to disk."""
        applied = []
        for change in changes:
            path = change.get("path", "")
            action = change.get("action", "modify")
            content = change.get("content", "")

            if not path or not path.startswith("src/") and not path.startswith("tests/"):
                self.log.warning("dev_skipping_unsafe_path", path=path)
                continue

            full_path = self.repo_root / path

            try:
                if action == "delete":
                    if full_path.exists():
                        full_path.unlink()
                        applied.append(path)
                elif action in ("create", "modify"):
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(content, encoding="utf-8")
                    applied.append(path)
                    self.log.info("dev_file_written", path=path, action=action,
                                 lines=content.count("\n"))
            except Exception as e:
                self.log.error("dev_file_write_error", path=path, error=str(e))

        return applied

    def _revert_changes(self, paths: list[str]) -> None:
        """Git checkout to revert failed changes."""
        if not paths:
            return
        try:
            subprocess.run(
                ["git", "checkout", "--"] + paths,
                cwd=self.repo_root,
                check=True,
                capture_output=True,
            )
            self.log.info("dev_changes_reverted", paths=paths)
        except subprocess.CalledProcessError as e:
            self.log.error("dev_revert_failed", error=e.stderr.decode())

    # ── Test Runner ──────────────────────────────────────────────────

    def _run_tests(self, test_paths: list[str] | None = None) -> bool:
        """Run pytest and return True if all tests pass."""
        cmd = ["python", "-m", "pytest", "-q", "--tb=short"]
        if test_paths:
            cmd += [str(self.repo_root / p) for p in test_paths if p]
        else:
            cmd.append(str(self.tests_root))

        env = {**os.environ, "PYTHONPATH": str(self.src_root.parent)}

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            passed = result.returncode == 0
            if passed:
                self.log.info("dev_tests_passed", output=result.stdout.strip().splitlines()[-1])
            else:
                self.log.warning("dev_tests_failed",
                                stdout=result.stdout[-500:],
                                stderr=result.stderr[-200:])
            return passed
        except subprocess.TimeoutExpired:
            self.log.error("dev_tests_timeout")
            return False

    # ── Git Operations ────────────────────────────────────────────────

    def _git_commit_push(self, summary: str, files: list[str]) -> tuple[bool, bool]:
        """Stage changed files, commit with AI summary, and push."""
        try:
            # Stage only the files we changed
            subprocess.run(
                ["git", "add"] + files,
                cwd=self.repo_root,
                check=True,
                capture_output=True,
            )

            # Check if there's anything staged
            status = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )
            if not status.stdout.strip():
                self.log.info("dev_nothing_to_commit")
                return False, False

            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            commit_msg = (
                f"feat(dev-agent): {summary}\n\n"
                f"Autonomous improvement by DevAgent at {timestamp}\n\n"
                "https://claude.ai/code/session_012fhACrP2dbhtTMt5SeUrqy"
            )

            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=self.repo_root,
                check=True,
                capture_output=True,
            )
            self.log.info("dev_committed", summary=summary)

            # Push with retry
            for attempt in range(4):
                push = subprocess.run(
                    ["git", "push", "-u", "origin", "claude/iga-ai-framework-2bUVS"],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                )
                if push.returncode == 0:
                    self.log.info("dev_pushed", attempt=attempt + 1)
                    return True, True
                import time
                wait = 2 ** attempt
                self.log.warning("dev_push_retry", attempt=attempt + 1, wait=wait)
                time.sleep(wait)

            self.log.error("dev_push_failed_all_retries")
            return True, False

        except subprocess.CalledProcessError as e:
            self.log.error("dev_git_error", error=e.stderr.decode() if e.stderr else str(e))
            return False, False
