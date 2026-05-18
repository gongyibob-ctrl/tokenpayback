"""`tokenpayback` CLI — scan Claude Code sessions, classify, serve dashboard, open browser."""
from __future__ import annotations
import argparse
import http.server
import json
import shutil
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .util import load_config, last_n_weeks

DEFAULT_DATA_DIR = Path.home() / ".tokenpayback"


def _bundled_dashboard_dir() -> Path:
    return Path(__file__).parent / "dashboard"


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan ~/.claude/projects, classify, write data.json to data dir."""
    from .parse_claude import collect_all
    from . import classify_sessions as classify_mod
    from . import roi as roi_mod

    data_dir: Path = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"scanning ~/.claude/projects/...")
    sessions = collect_all()
    print(f"  found {len(sessions)} sessions")

    sessions_path = data_dir / "sessions.json"
    if args.no_classify:
        print("  skipping LLM classification (--no-classify)")
        # Still write the raw sessions so we can at least show cost-by-project (without category)
        sessions_path.write_text(json.dumps(sessions, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"classifying with LLM ({len(sessions)} sessions, ~2s each)...")
        enriched = []
        for i, s in enumerate(sessions, 1):
            c = classify_mod.classify_session(s)
            s["classification"] = c
            enriched.append(s)
            if i % 5 == 0 or i == len(sessions):
                print(f"  [{i}/{len(sessions)}] {c['category']:<14} {c['project'][:30]} ${s['est_cost_usd']:.2f}")
        sessions_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2, default=str))
        print(f"  wrote {sessions_path}")

    # Optionally also run GitHub ROI (needs gh CLI auth)
    if not args.no_github:
        try:
            cfg = load_config_with_fallbacks(args.config)
            weeks = last_n_weeks(args.weeks)
            print(f"computing GitHub ROI for {weeks}...")
            weeks_data = roi_mod.build_weeks(weeks, cfg)
            data = roi_mod.render_dashboard_json(weeks_data, cfg)
            # Patch in our sessions from the data_dir location
            try:
                data["sessions"] = json.loads(sessions_path.read_text())
                data["sessionsTotals"] = roi_mod._summarize_sessions(data["sessions"])
            except Exception:
                pass
            (data_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
            md = roi_mod.render_markdown(weeks_data, cfg)
            (data_dir / "latest.md").write_text(md)
            print(f"  wrote {data_dir / 'data.json'}")
        except Exception as e:
            print(f"  ! GitHub ROI step failed: {e}", file=sys.stderr)
            print(f"  (falling back to sessions-only view)", file=sys.stderr)
            data = {
                "generatedAt": _now_iso(),
                "config": {"github_username": "(unset)", "hourly_rate_usd": 150, "value_per_pr_usd": 600, "value_per_line_committed_usd": 0.3},
                "weeks": [],
                "sessions": json.loads(sessions_path.read_text()),
            }
            from .roi import _summarize_sessions
            data["sessionsTotals"] = _summarize_sessions(data["sessions"])
            (data_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        # No-github mode: write minimal data.json with just sessions
        data = {
            "generatedAt": _now_iso(),
            "config": {"github_username": "(skipped)", "hourly_rate_usd": 150, "value_per_pr_usd": 600, "value_per_line_committed_usd": 0.3},
            "weeks": [],
            "sessions": json.loads(sessions_path.read_text()),
        }
        from .roi import _summarize_sessions
        data["sessionsTotals"] = _summarize_sessions(data["sessions"])
        (data_dir / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Serve bundled dashboard + data.json on localhost, open browser."""
    data_dir: Path = args.data_dir
    if not (data_dir / "data.json").exists():
        print(f"no data found in {data_dir}. Run `tokenpayback scan` first.", file=sys.stderr)
        return 1

    # Assemble: copy bundled dashboard files + user's data.json into a serve dir
    serve_dir = data_dir / "_serve"
    serve_dir.mkdir(exist_ok=True)
    for f in _bundled_dashboard_dir().iterdir():
        shutil.copy2(f, serve_dir / f.name)
    shutil.copy2(data_dir / "data.json", serve_dir / "data.json")

    port = args.port or _free_port()
    url = f"http://localhost:{port}/"

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args2):
            pass
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(serve_dir), **kw)

    with socketserver.TCPServer(("127.0.0.1", port), QuietHandler) as httpd:
        print(f"\n  ▸ tokenpayback dashboard: {url}")
        print(f"  ▸ press Ctrl+C to stop\n")
        if not args.no_browser:
            threading.Timer(0.3, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    rc = cmd_scan(args)
    if rc != 0:
        return rc
    return cmd_serve(args)


def load_config_with_fallbacks(config_path: Path | None) -> dict:
    """Try user-specified config, else config.local.yaml in cwd, else built-in defaults."""
    import yaml
    if config_path and config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f)
    local = Path.cwd() / "config.local.yaml"
    if local.exists():
        with open(local) as f:
            return yaml.safe_load(f)
    # Defaults — let it run without any config
    return {
        "hourly_rate_usd": 150,
        "value_per_pr_usd": 600,
        "value_per_line_committed_usd": 0.30,
        "github_username": _gh_user_or_blank(),
        "github_repos": [],
        "fixed_monthly_subscriptions_usd": {"cursor": 20, "github_copilot": 19},
        "providers": {"anthropic": {"enabled": True}, "openai": {"enabled": False}},
        "report_dir": "reports",
        "dashboard_data": "data.json",
    }


def _gh_user_or_blank() -> str:
    import subprocess
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def _free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tokenpayback",
        description="Are your AI tokens paying off? Classify your Claude Code sessions and see ROI.",
    )
    p.add_argument("--version", action="version", version=f"tokenpayback {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR,
                        help="Where to store sessions.json / data.json (default: ~/.tokenpayback/)")
    common.add_argument("--config", type=Path, help="Path to config.yaml (default: ./config.local.yaml or built-in)")
    common.add_argument("--weeks", type=int, default=4)

    sub = p.add_subparsers(dest="cmd")

    s_scan = sub.add_parser("scan", parents=[common], help="Scan ~/.claude + classify + write data.json")
    s_scan.add_argument("--no-classify", action="store_true", help="Skip LLM classification (faster, less insight)")
    s_scan.add_argument("--no-github", action="store_true", help="Skip GitHub PR/commit fetching")
    s_scan.set_defaults(func=cmd_scan)

    s_serve = sub.add_parser("serve", parents=[common], help="Serve dashboard locally and open browser")
    s_serve.add_argument("--port", type=int, help="HTTP port (default: auto)")
    s_serve.add_argument("--no-browser", action="store_true")
    s_serve.set_defaults(func=cmd_serve)

    # default: full run
    p.add_argument("--no-classify", action="store_true", help="(default cmd) skip LLM classification")
    p.add_argument("--no-github", action="store_true")
    p.add_argument("--port", type=int)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p.add_argument("--config", type=Path)
    p.add_argument("--weeks", type=int, default=4)
    p.set_defaults(func=cmd_all)
    return p


def main() -> None:
    args = build_parser().parse_args()
    func = getattr(args, "func", cmd_all)
    sys.exit(func(args))


if __name__ == "__main__":
    main()
