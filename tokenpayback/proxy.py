"""Local LLM proxy — sits between your tools and any LLM API, logs everything locally.

Why?
  Parser-based ingestion (Claude Code / Codex / Hermes / ...) only covers tools that
  keep local session logs. To capture *anything* hitting an LLM API — your own
  scripts, OpenRouter, HuggingFace, custom agents — we need a different vector.

  This proxy is that vector. Point any OpenAI-compatible / Anthropic tool at
  http://localhost:PORT and we log the traffic to ~/.tokenpayback/proxy_log.jsonl
  before forwarding upstream.

Usage:
  tokenpayback proxy start --upstream anthropic    # listen on default port 4000
  tokenpayback proxy start --upstream openrouter --port 4001

  # In another shell, point your tool at the proxy:
  export ANTHROPIC_BASE_URL=http://localhost:4000   # anthropic SDK
  export OPENAI_BASE_URL=http://localhost:4001/v1   # openai SDK / langchain / aider

Privacy:
  - The proxy is local-only (binds 127.0.0.1)
  - Your real upstream API key is read from env or ~/.tokenpayback/proxy.yaml
    (chmod 600) and NEVER logged
  - Log entries include prompt/response text — you decide if that's OK on your machine
  - Set TOKENPAYBACK_PROXY_REDACT=1 to hash text instead of storing it
"""
from __future__ import annotations
import http.server
import json
import os
import socketserver
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
import yaml


DATA_DIR = Path.home() / ".tokenpayback"
PROXY_CONFIG = DATA_DIR / "proxy.yaml"
PROXY_LOG = DATA_DIR / "proxy_log.jsonl"
PID_FILE = DATA_DIR / "proxy.pid"


UPSTREAM_PRESETS: dict[str, dict] = {
    "anthropic":   {"base_url": "https://api.anthropic.com",          "key_env": "ANTHROPIC_API_KEY", "auth_style": "anthropic"},
    "openai":      {"base_url": "https://api.openai.com",             "key_env": "OPENAI_API_KEY",    "auth_style": "bearer"},
    "openrouter":  {"base_url": "https://openrouter.ai/api",          "key_env": "OPENROUTER_API_KEY","auth_style": "bearer"},
    "groq":        {"base_url": "https://api.groq.com/openai",        "key_env": "GROQ_API_KEY",      "auth_style": "bearer"},
    "mistral":     {"base_url": "https://api.mistral.ai",             "key_env": "MISTRAL_API_KEY",   "auth_style": "bearer"},
    "deepseek":    {"base_url": "https://api.deepseek.com",           "key_env": "DEEPSEEK_API_KEY",  "auth_style": "bearer"},
    "huggingface": {"base_url": "https://api-inference.huggingface.co","key_env":"HF_API_KEY",       "auth_style": "bearer"},
    "paigod":      {"base_url": "https://apiproxy.paigod.work",       "key_env": "PAIGOD_API_KEY",    "auth_style": "bearer"},
}


# --- log writing ----------------------------------------------------------------
_log_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(text: str) -> str:
    """Replace text with a one-way hash if redaction is on."""
    if os.environ.get("TOKENPAYBACK_PROXY_REDACT"):
        import hashlib
        return f"sha256:{hashlib.sha256(text.encode()).hexdigest()[:24]}"
    return text


def write_log_entry(entry: dict) -> None:
    PROXY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _log_lock:
        with open(PROXY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


# --- response parsing (per provider) --------------------------------------------
def parse_anthropic_response(content: bytes) -> dict:
    text_pieces: list[str] = []
    input_tokens = output_tokens = cache_create = cache_read = 0
    tool_uses: list[str] = []
    model = ""

    # Try JSON (non-streaming)
    try:
        d = json.loads(content)
        if isinstance(d, dict):
            model = d.get("model", "")
            usage = d.get("usage") or {}
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_create = usage.get("cache_creation_input_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            for c in d.get("content", []):
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        text_pieces.append(c.get("text", ""))
                    elif c.get("type") == "tool_use":
                        tool_uses.append(c.get("name", "?"))
            return {"text": "".join(text_pieces), "input_tokens": input_tokens, "output_tokens": output_tokens,
                    "cache_create": cache_create, "cache_read": cache_read, "tools": tool_uses, "model": model}
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    # SSE streaming
    try:
        for raw_line in content.split(b"\n"):
            if not raw_line.startswith(b"data: "):
                continue
            payload = raw_line[6:].strip()
            if not payload:
                continue
            try:
                d = json.loads(payload)
            except json.JSONDecodeError:
                continue
            t = d.get("type")
            if t == "message_start":
                msg = d.get("message", {})
                model = msg.get("model", model)
                u = msg.get("usage", {})
                input_tokens = u.get("input_tokens", input_tokens)
                cache_create = u.get("cache_creation_input_tokens", cache_create)
                cache_read = u.get("cache_read_input_tokens", cache_read)
            elif t == "content_block_delta":
                delta = d.get("delta", {})
                if delta.get("type") == "text_delta":
                    text_pieces.append(delta.get("text", ""))
            elif t == "content_block_start":
                cb = d.get("content_block", {})
                if cb.get("type") == "tool_use":
                    tool_uses.append(cb.get("name", "?"))
            elif t == "message_delta":
                u = d.get("usage", {})
                output_tokens = u.get("output_tokens", output_tokens)
    except Exception:
        pass

    return {"text": "".join(text_pieces), "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cache_create": cache_create, "cache_read": cache_read, "tools": tool_uses, "model": model}


def parse_openai_response(content: bytes) -> dict:
    text_pieces: list[str] = []
    input_tokens = output_tokens = 0
    tool_uses: list[str] = []
    model = ""

    try:
        d = json.loads(content)
        if isinstance(d, dict):
            model = d.get("model", "")
            u = d.get("usage") or {}
            input_tokens = u.get("prompt_tokens", 0)
            output_tokens = u.get("completion_tokens", 0)
            for c in d.get("choices", []):
                msg = c.get("message") or c.get("delta") or {}
                if isinstance(msg, dict):
                    t = msg.get("content") or ""
                    if isinstance(t, str) and t:
                        text_pieces.append(t)
                    for tc in (msg.get("tool_calls") or []):
                        if isinstance(tc, dict):
                            fn = (tc.get("function") or {}).get("name")
                            if fn:
                                tool_uses.append(fn)
            return {"text": "".join(text_pieces), "input_tokens": input_tokens, "output_tokens": output_tokens,
                    "cache_create": 0, "cache_read": 0, "tools": tool_uses, "model": model}
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    try:
        for raw_line in content.split(b"\n"):
            if not raw_line.startswith(b"data: "):
                continue
            payload = raw_line[6:].strip()
            if payload == b"[DONE]" or not payload:
                continue
            try:
                d = json.loads(payload)
            except json.JSONDecodeError:
                continue
            model = d.get("model", model)
            for c in d.get("choices", []):
                delta = c.get("delta") or {}
                t = delta.get("content") or ""
                if isinstance(t, str) and t:
                    text_pieces.append(t)
                for tc in (delta.get("tool_calls") or []):
                    if isinstance(tc, dict):
                        fn = (tc.get("function") or {}).get("name")
                        if fn:
                            tool_uses.append(fn)
            u = d.get("usage")
            if u:
                input_tokens = u.get("prompt_tokens", input_tokens)
                output_tokens = u.get("completion_tokens", output_tokens)
    except Exception:
        pass

    return {"text": "".join(text_pieces), "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cache_create": 0, "cache_read": 0, "tools": tool_uses, "model": model}


def parse_request_body(body: bytes, auth_style: str) -> dict:
    """Extract the user's prompt for logging (first 600 chars of system+user content)."""
    try:
        d = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"model": "", "prompt_summary": "", "streaming": False, "tools_declared": 0}
    model = d.get("model", "")
    streaming = bool(d.get("stream", False))
    tools_declared = len(d.get("tools") or [])
    parts: list[str] = []
    if "system" in d and isinstance(d["system"], str):
        parts.append("[system] " + d["system"][:200])
    for m in (d.get("messages") or []):
        if not isinstance(m, dict):
            continue
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(f"[{role}] " + c.get("text", "")[:200])
        elif isinstance(content, str):
            parts.append(f"[{role}] " + content[:200])
        if sum(len(p) for p in parts) > 600:
            break
    summary = " | ".join(parts)[:600]
    return {"model": model, "prompt_summary": summary, "streaming": streaming, "tools_declared": tools_declared}


# --- handler --------------------------------------------------------------------
class ProxyHandler(http.server.BaseHTTPRequestHandler):
    """Closure-style: the upstream config is attached via subclassing in `make_server`."""
    upstream: dict = {}

    def log_message(self, fmt: str, *args: Any) -> None:
        # Quiet stdlib's default per-request log — we have our own
        return

    def _hop_by_hop(self) -> set[str]:
        return {"transfer-encoding", "content-encoding", "content-length", "connection",
                "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"}

    def _build_upstream_headers(self, real_key: str) -> dict:
        h: dict[str, str] = {}
        for k, v in self.headers.items():
            kl = k.lower()
            if kl in self._hop_by_hop() or kl == "host":
                continue
            h[k] = v
        # Inject the real upstream key
        if self.upstream.get("auth_style") == "anthropic":
            h["x-api-key"] = real_key
            h["anthropic-version"] = h.get("anthropic-version") or "2023-06-01"
            # Remove any incoming Authorization the client sent
            h.pop("Authorization", None)
        else:
            h["Authorization"] = f"Bearer {real_key}"
            h.pop("x-api-key", None)
        return h

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self) -> None:
        self._proxy_request()

    def do_POST(self) -> None:
        self._proxy_request()

    def do_PUT(self) -> None:
        self._proxy_request()

    def do_DELETE(self) -> None:
        self._proxy_request()

    def _proxy_request(self) -> None:
        started = time.time()
        clen = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(clen) if clen > 0 else b""

        upstream_url = self.upstream["base_url"].rstrip("/") + self.path
        real_key = (self.upstream.get("api_key")
                    or os.environ.get(self.upstream.get("key_env") or "")
                    or "")
        if not real_key:
            self._send_error(401, f"Upstream API key missing. Set env {self.upstream.get('key_env')} or proxy.yaml.")
            return

        headers = self._build_upstream_headers(real_key)
        is_llm_path = any(seg in self.path for seg in ("/messages", "/chat/completions", "/completions", "/responses"))
        req_meta = parse_request_body(body, self.upstream.get("auth_style", "bearer")) if is_llm_path and body else {
            "model": "", "prompt_summary": "", "streaming": False, "tools_declared": 0
        }

        try:
            r = requests.request(self.command, upstream_url, data=body, headers=headers,
                                 stream=True, timeout=300, allow_redirects=False)
        except requests.RequestException as e:
            self._send_error(502, f"upstream connect failed: {e}")
            write_log_entry({
                "timestamp": _now_iso(), "upstream": self.upstream.get("name", "?"),
                "method": self.command, "path": self.path, "status": 0, "duration_ms": int((time.time()-started)*1000),
                "error": str(e), "model": req_meta.get("model"), "prompt_summary": _redact(req_meta.get("prompt_summary", "")),
            })
            return

        self.send_response(r.status_code)
        for k, v in r.headers.items():
            if k.lower() in self._hop_by_hop():
                continue
            self.send_header(k, v)
        self.end_headers()

        buf = bytearray()
        try:
            for chunk in r.iter_content(chunk_size=4096):
                if chunk:
                    self.wfile.write(chunk)
                    try:
                        self.wfile.flush()
                    except Exception:
                        pass
                    buf.extend(chunk)
                    if len(buf) > 8 * 1024 * 1024:  # cap captured content at 8MB to keep logs sane
                        break
        except Exception as e:
            print(f"  ! proxy stream error: {e}", file=sys.stderr)

        duration_ms = int((time.time() - started) * 1000)
        log_entry: dict[str, Any] = {
            "timestamp": _now_iso(),
            "upstream": self.upstream.get("name", "?"),
            "method": self.command,
            "path": self.path,
            "status": r.status_code,
            "duration_ms": duration_ms,
            "model": req_meta.get("model"),
            "streaming": req_meta.get("streaming"),
            "tools_declared": req_meta.get("tools_declared"),
            "prompt_summary": _redact(req_meta.get("prompt_summary") or ""),
        }
        if is_llm_path and 200 <= r.status_code < 300:
            try:
                if self.upstream.get("auth_style") == "anthropic":
                    p = parse_anthropic_response(bytes(buf))
                else:
                    p = parse_openai_response(bytes(buf))
                log_entry.update({
                    "model": p.get("model") or log_entry["model"],
                    "input_tokens": p["input_tokens"],
                    "output_tokens": p["output_tokens"],
                    "cache_create": p["cache_create"],
                    "cache_read": p["cache_read"],
                    "tools_used": p["tools"],
                    "response_summary": _redact(p["text"][:600]),
                    "est_cost_usd": _estimate_cost(self.upstream.get("name", ""), p),
                })
            except Exception as e:
                log_entry["parse_error"] = str(e)
        write_log_entry(log_entry)

    def _send_error(self, code: int, msg: str) -> None:
        body = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass


# --- cost estimate --------------------------------------------------------------
def _estimate_cost(upstream: str, parsed: dict) -> float:
    # Coarse heuristic — real cost depends on model. Refine via config later.
    presets = {
        "anthropic":   (3e-6, 15e-6, 3.75e-6, 0.3e-6),     # rough sonnet-ish
        "openai":      (1.25e-6, 10e-6, 0, 0),
        "openrouter":  (1.5e-6, 12e-6, 0, 0),
        "groq":        (0.10e-6, 0.20e-6, 0, 0),
        "deepseek":    (0.27e-6, 1.10e-6, 0, 0),
        "mistral":     (0.5e-6, 1.5e-6, 0, 0),
        "huggingface": (0, 0, 0, 0),
        "paigod":      (3e-6, 15e-6, 3.75e-6, 0.3e-6),
    }
    rates = presets.get(upstream, (3e-6, 15e-6, 0, 0))
    return round(
        parsed["input_tokens"] * rates[0]
        + parsed["output_tokens"] * rates[1]
        + parsed["cache_create"] * rates[2]
        + parsed["cache_read"] * rates[3],
        6,
    )


# --- server -----------------------------------------------------------------
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(upstream_name: str, upstream_cfg: dict) -> type[ProxyHandler]:
    cfg = dict(upstream_cfg)
    cfg["name"] = upstream_name
    return type("BoundProxyHandler", (ProxyHandler,), {"upstream": cfg})


def serve(upstream: str, port: int = 4000, host: str = "127.0.0.1") -> None:
    if upstream not in UPSTREAM_PRESETS and not _load_proxy_config().get("upstreams", {}).get(upstream):
        raise SystemExit(f"unknown upstream: {upstream}. Known: {', '.join(UPSTREAM_PRESETS)}")
    cfg = _resolve_upstream(upstream)
    handler = make_handler(upstream, cfg)
    server = ThreadedTCPServer((host, port), handler)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(f"{os.getpid()}\n{upstream}\n{host}:{port}\n")
    try:
        key_status = "✓ key found" if (cfg.get("api_key") or os.environ.get(cfg.get("key_env") or "")) else "✗ key missing"
        print(f"  ▸ tokenpayback proxy listening on http://{host}:{port}")
        print(f"  ▸ upstream: {upstream}  ({cfg['base_url']})  [{key_status}]")
        print(f"  ▸ logging to {PROXY_LOG}")
        print(f"  ▸ point your tool's base URL at this proxy:")
        if cfg.get("auth_style") == "anthropic":
            print(f"       export ANTHROPIC_BASE_URL=http://{host}:{port}")
        else:
            print(f"       export OPENAI_BASE_URL=http://{host}:{port}/v1")
        print(f"  ▸ press Ctrl+C to stop\n")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        try:
            PID_FILE.unlink()
        except FileNotFoundError:
            pass
        server.server_close()


def _resolve_upstream(name: str) -> dict:
    cfg = dict(UPSTREAM_PRESETS.get(name, {}))
    user_cfg = _load_proxy_config().get("upstreams", {}).get(name, {})
    cfg.update(user_cfg)
    return cfg


def _load_proxy_config() -> dict:
    if not PROXY_CONFIG.exists():
        return {}
    try:
        return yaml.safe_load(PROXY_CONFIG.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def status() -> None:
    if not PID_FILE.exists():
        print("proxy not running")
        return
    info = PID_FILE.read_text().strip().splitlines()
    pid = info[0] if info else ""
    try:
        os.kill(int(pid), 0)
        print(f"proxy running pid={pid}")
        for line in info[1:]:
            print(f"  {line}")
    except (ValueError, ProcessLookupError, PermissionError):
        print(f"stale pid file ({pid}) — proxy not actually running")
        PID_FILE.unlink(missing_ok=True)


def stop() -> None:
    if not PID_FILE.exists():
        print("proxy not running")
        return
    pid = int(PID_FILE.read_text().splitlines()[0])
    try:
        os.kill(pid, 15)  # SIGTERM
        print(f"sent SIGTERM to pid {pid}")
    except ProcessLookupError:
        print("process already gone")
    finally:
        PID_FILE.unlink(missing_ok=True)
