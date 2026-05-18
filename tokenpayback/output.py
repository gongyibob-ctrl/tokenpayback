"""Collect engineering output per ISO week via GitHub REST search API."""
from __future__ import annotations
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from .util import load_config, week_range


def _gh_api(path: str) -> dict:
    result = subprocess.run(
        ["gh", "api", path, "-H", "Accept: application/vnd.github+json"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {path[:120]} failed: {result.stderr[:300]}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def search_commits(username: str, since: str, until: str) -> list[dict]:
    q = f"author:{username}+author-date:{since}..{until}"
    try:
        data = _gh_api(f"search/commits?q={q}&per_page=100")
        return data.get("items", [])
    except RuntimeError as e:
        print(f"  ! commits search failed: {e}", file=sys.stderr)
        return []


def search_prs_merged(username: str, since: str, until: str) -> list[dict]:
    q = f"author:{username}+is:pr+is:merged+merged:{since}..{until}"
    try:
        data = _gh_api(f"search/issues?q={q}&per_page=100")
        return data.get("items", [])
    except RuntimeError as e:
        print(f"  ! prs search failed: {e}", file=sys.stderr)
        return []


def pr_diff_stats(repo_full: str, pr_number: int) -> tuple[int, int, int]:
    try:
        data = _gh_api(f"repos/{repo_full}/pulls/{pr_number}")
        return data.get("additions", 0), data.get("deletions", 0), data.get("changed_files", 0)
    except RuntimeError:
        return 0, 0, 0


def repo_full_from_pr_url(html_url: str) -> str:
    # https://github.com/owner/repo/pull/123
    parts = html_url.rstrip("/").split("/")
    if len(parts) >= 5:
        return f"{parts[-4]}/{parts[-3]}"
    return ""


def is_revert(commit_item: dict) -> bool:
    msg = (((commit_item.get("commit") or {}).get("message")) or "").lower().lstrip()
    return msg.startswith("revert ") or "this reverts commit" in msg


def collect(weeks: list[str], config: dict, *, enrich_pr_stats: bool = True) -> dict[str, dict]:
    username = config["github_username"]
    out: dict[str, dict] = {}
    for w in weeks:
        monday, sunday = week_range(w)
        since = monday.isoformat()
        until = (sunday + dt.timedelta(days=1)).isoformat()
        commits = search_commits(username, since, until)
        prs = search_prs_merged(username, since, until)
        reverts = sum(1 for c in commits if is_revert(c))
        additions = deletions = changed_files = 0
        pr_details = []
        for p in prs:
            repo_full = repo_full_from_pr_url(p.get("html_url", ""))
            if enrich_pr_stats and repo_full:
                a, d, f = pr_diff_stats(repo_full, p.get("number"))
                additions += a; deletions += d; changed_files += f
            pr_details.append({
                "title": p.get("title", "")[:120],
                "url": p.get("html_url"),
                "repo": repo_full,
                "merged_at": p.get("closed_at"),
            })
        repos = sorted({d["repo"] for d in pr_details} - {""})
        out[w] = {
            "commits": len(commits),
            "reverts": reverts,
            "prs_merged": len(prs),
            "additions": additions,
            "deletions": deletions,
            "changed_files": changed_files,
            "repos_touched": repos,
            "prs": pr_details[:20],
        }
        print(f"  [{w}] commits={len(commits)} prs={len(prs)} repos={len(repos)}", file=sys.stderr)
    return out


if __name__ == "__main__":
    from .util import last_n_weeks
    cfg = load_config()
    weeks = last_n_weeks(4)
    print(json.dumps(collect(weeks, cfg), indent=2, ensure_ascii=False))
