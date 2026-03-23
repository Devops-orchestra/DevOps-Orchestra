"""
Populate `state.git_meta` after clone: local path, changed files vs base ref, short summary.
"""
import subprocess
from typing import List, Optional

from shared_modules.state.devops_state import DevOpsAgentState
from shared_modules.utils.logger import logger

DEFAULT_BASE_REFS = ("origin/main", "origin/master", "main", "master")


def _run_git(args: List[str], cwd: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _resolve_merge_base(cwd: str, head: str, candidate_bases: tuple) -> Optional[str]:
    for base in candidate_bases:
        r = _run_git(["rev-parse", "--verify", base], cwd=cwd, timeout=30)
        if r.returncode != 0:
            continue
        base_sha = r.stdout.strip()
        mb = _run_git(["merge-base", head, base_sha], cwd=cwd, timeout=30)
        if mb.returncode == 0 and mb.stdout.strip():
            return mb.stdout.strip()
    return None


def populate_git_metadata(
    state: DevOpsAgentState,
    clone_path: str,
    branch: str,
    base_refs: tuple = DEFAULT_BASE_REFS,
) -> None:
    """
    Set local_path and try to fill changed_files + diff_summary using git.
    Best-effort: never raises.
    """
    state.git_meta.local_path = clone_path
    state.git_meta.branch = branch
    state.git_meta.base_ref_used = None

    try:
        head_r = _run_git(["rev-parse", "HEAD"], cwd=clone_path, timeout=30)
        if head_r.returncode != 0:
            state.git_meta.diff_summary = "Could not resolve HEAD."
            return
        head = head_r.stdout.strip()

        # Optional: shallow clones may need fetch for origin/main
        _run_git(["fetch", "origin", "--depth=1"], cwd=clone_path, timeout=180)

        merge_base = _resolve_merge_base(clone_path, head, base_refs)
        if not merge_base:
            # Fallback: last commit only
            diff_r = _run_git(["diff", "--name-only", "HEAD~1", "HEAD"], cwd=clone_path, timeout=60)
            if diff_r.returncode == 0:
                files = [f.strip() for f in diff_r.stdout.splitlines() if f.strip()]
                state.git_meta.changed_files = files
                state.git_meta.diff_summary = f"{len(files)} file(s) in latest commit (no merge-base with main/master)."
            else:
                state.git_meta.diff_summary = "Could not compute diff (no merge-base)."
            return

        for base in base_refs:
            br = _run_git(["rev-parse", "--verify", base], cwd=clone_path, timeout=30)
            if br.returncode == 0:
                state.git_meta.base_ref_used = base
                break

        diff_r = _run_git(["diff", "--name-only", merge_base, head], cwd=clone_path, timeout=120)
        if diff_r.returncode != 0:
            state.git_meta.diff_summary = f"git diff failed: {diff_r.stderr[:200]}"
            return

        files = [f.strip() for f in diff_r.stdout.splitlines() if f.strip()]
        state.git_meta.changed_files = files

        stat_r = _run_git(["diff", "--stat", merge_base, head], cwd=clone_path, timeout=120)
        stat_snip = (stat_r.stdout or "").strip()[:800] if stat_r.returncode == 0 else ""
        state.git_meta.diff_summary = (
            f"{len(files)} file(s) changed vs merge-base ({state.git_meta.base_ref_used or 'unknown'}).\n{stat_snip}"
        )
    except Exception as e:
        logger.warning(f"[Git metadata] {e}")
        state.git_meta.diff_summary = f"Git metadata error: {e}"
