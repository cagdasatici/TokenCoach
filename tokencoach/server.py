"""Local-only listener that serves the dashboard and runs its buttons.

Bound to 127.0.0.1. Every request must carry the per-install secret (in the
URL for the page, in a custom header for actions), and the Host header must
name this listener, so other websites cannot read the dashboard or trigger
actions (a custom header forces a CORS preflight we never approve, and the
Host check defeats DNS rebinding). Standard library only.
"""

import json
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from tokencoach import ledger
from tokencoach.config import log, load_config, save_config

PREFERRED_PORT = 47821
TOKEN_HEADER = "X-TokenCoach"


def get_token(config: dict) -> str:
    """Stable per-install secret, so a bookmarked dashboard URL keeps working."""
    tok = config.get("dashboard_token")
    if not tok:
        tok = secrets.token_urlsafe(24)
        config["dashboard_token"] = tok
        save_config(config)
    return tok


class _Handler(BaseHTTPRequestHandler):
    server_version = "TokenCoach"

    def log_message(self, fmt, *args):          # keep the app log quiet
        # the page URL carries the secret; the log is less private than the config
        log.debug("dashboard: %s", re.sub(r"([?&]t=)[^&\s]*", r"\1…", fmt % args))

    # -- guards -------------------------------------------------------------
    def _host_ok(self) -> bool:
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _token_ok(self, given: str | None) -> bool:
        return secrets.compare_digest((given or "").encode(), self.server.token.encode())

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj).encode(), "application/json")

    # -- routes -------------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        if url.path not in ("/", "/data"):
            return self._send(404, b"Not found", "text/plain")
        if not self._token_ok(parse_qs(url.query).get("t", [""])[0]):
            return self._send(403, b"Open the dashboard from the TokenCoach menu bar icon.", "text/plain")
        try:
            from tokencoach.ledger_report import build_report, dashboard_data
            conn = ledger.open_ledger()
            try:
                live = {"token": self.server.token,
                        "indexed_at": getattr(self.server.app, "_ledger_updated", None),
                        "index_status": getattr(self.server.app, "_ledger_status", "")}
                if url.path == "/data":
                    data = dashboard_data(conn, load_config())
                    data["live"] = live
                    return self._json(200, data)
                page = build_report(conn, load_config(), live=live)
            finally:
                conn.close()
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        except Exception:
            log.exception("dashboard render failed")
            self._send(500, b"Dashboard error - see ~/Library/Logs/TokenCoach/tokencoach.log", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        if not self._host_ok() or not self._token_ok(self.headers.get(TOKEN_HEADER)):
            return self._json(403, {"ok": False, "error": "Forbidden"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 <= n <= 1_000_000:
                raise ValueError("bad Content-Length")
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"ok": False, "error": "Bad request"})
        action = url.path.removeprefix("/api/")
        handler = ACTIONS.get(action)
        if not handler:
            return self._json(404, {"ok": False, "error": "Unknown action"})
        from tokencoach.config import DEMO
        if DEMO and action in DEMO_BLOCKED:
            return self._json(200, {"ok": False, "error": "Not available with sample data. "
                                                           "Install TokenCoach to use it on your own history."})
        conn = ledger.open_ledger()
        try:
            result = handler(conn, body, self.server.app)
            self._json(200, {"ok": True, **(result or {})})
        except (ValueError, RuntimeError) as e:
            self._json(200, {"ok": False, "error": str(e)})
        except Exception:
            log.exception("dashboard action %s failed", action)
            self._json(500, {"ok": False, "error": "Something went wrong - see ~/Library/Logs/TokenCoach/tokencoach.log"})
        finally:
            conn.close()


# ── actions ──────────────────────────────────────────────────────────────────

def _improve(conn, body, app):
    from tokencoach.coach import improve_prompt
    return improve_prompt(conn, str(body.get("prompt_id") or ""), force=bool(body.get("force")))


def _apply(conn, body, app):
    from tokencoach.coach import apply_lesson
    return {"files": apply_lesson(conn, str(body.get("id") or ""), allow_review=bool(body.get("confirm")))}


def _apply_ready(conn, body, app):
    from tokencoach.coach import apply_ready
    return {"files": apply_ready(conn)}


def _unapply(conn, body, app):
    from tokencoach.coach import unapply_lesson
    unapply_lesson(conn, str(body.get("id") or ""))


def _edit(conn, body, app):
    from tokencoach.coach import edit_lesson
    return edit_lesson(conn, str(body.get("id") or ""), title=body.get("title"), rule=body.get("rule"),
                       scope=body.get("scope"), tools=body.get("tools"))


def _dismiss(conn, body, app):
    from tokencoach.coach import dismiss_lesson
    dismiss_lesson(conn, str(body.get("id") or ""))


def _analyze(conn, body, app):
    from tokencoach.optimizer import run_optimizer
    from tokencoach.coach import detect_lessons
    detect_lessons(conn)
    run_optimizer(conn)


def _save_template(conn, body, app):
    from tokencoach.coach import save_template
    text = str(body.get("text") or "").strip()
    if not text:
        raise ValueError("Nothing to save.")
    return {"id": save_template(conn, str(body.get("title") or ""), text, body.get("prompt_id"))}


def _delete_template(conn, body, app):
    from tokencoach.coach import delete_template
    delete_template(conn, int(body.get("id") or 0))


def _nudges(conn, body, app):
    """Turn Claude Code nudges on or off."""
    from tokencoach import nudge
    on = bool(body.get("on"))
    if app is not None:
        app.set_nudges(on)
    else:
        import os
        install_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        nudge.install(install_dir) if on else nudge.uninstall()
    return {"on": nudge.is_installed()}


# Actions that would spend quota or change the person's real setup. Improve is
# allowed: cached sample rewrites show, and run_claude refuses a real run.
DEMO_BLOCKED = {"analyze", "nudges"}

ACTIONS = {
    "improve": _improve, "lesson/apply": _apply, "lessons/apply-ready": _apply_ready,
    "lesson/unapply": _unapply, "lesson/dismiss": _dismiss, "lesson/edit": _edit, "analyze": _analyze,
    "template/save": _save_template, "template/delete": _delete_template,
    "nudges": _nudges,
}


class DashboardServer:
    def __init__(self, token: str, app=None, port: int = PREFERRED_PORT):
        # Never silently move the bookmark to an arbitrary port or trust the
        # occupant. The UI provides a labelled read-only copy if binding fails.
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.token = token
        self.httpd.app = app
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/?t={self.httpd.token}"

    def start(self):
        self.thread.start()
        log.info("dashboard listening on 127.0.0.1:%s", self.httpd.server_address[1])
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
