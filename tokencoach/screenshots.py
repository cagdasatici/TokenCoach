"""README screenshots from sample data, rendered by headless Google Chrome.

Run: python3 tokencoach.py --screenshots docs/images
Only ever called from `--screenshots`, which points the app at a separate
sample-data folder first, so no personal data can end up in an image.
"""

import os
import subprocess
import tempfile

from tokencoach.config import DEMO, log

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# name -> (query string, width, height)
SHOTS = {
    "dashboard-light": ("theme=light&view=simple&range=30d", 1280, 1700),
    "dashboard-dark":  ("theme=dark&view=simple&range=30d", 1280, 1700),
    "coach-dark":      ("theme=dark&view=simple&range=30d&hide=health,card-timeline,card-top,templates-card", 1280, 900),
    "advanced-dark":   ("theme=dark&view=advanced&range=30d&hide=health,card-coach,card-top,templates-card", 1280, 1500),
}

NUDGE_HTML = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#0d1117;font:15px/1.55 ui-monospace,Menlo,monospace;color:#c9d1d9}
.w{padding:26px 30px} .p{color:#e6edf3} .p b{color:#d97757} .n{margin-top:14px;border-left:3px solid #d97757;
padding:8px 12px;background:#161b22;color:#e6edf3;white-space:pre-wrap} .n i{color:#d97757;font-style:normal}
.dim{color:#8b949e;margin-top:12px}</style><div class="w">
<div class="p"><b>&gt;</b> implement all the remaining items from the roadmap and commit</div>
<div class="n"><i>TokenCoach:</i> ⚠ 312k tokens of context: every reply re-reads all of it (~$0.16 per reply on claude-opus-5). If this is a new task, /clear and start with a 2-line brief — this is usually the single biggest saving.
🎯 Broad asks like this averaged 87 responses ($7.40) in your history, vs 9 ($0.60) overall. Naming the files or items to change usually cuts that a lot.</div>
<div class="dim">(Claude Code continues with your prompt; the nudge never blocks it.)</div></div>"""


def _shoot(url: str, out: str, w: int, h: int) -> None:
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", f"--window-size={w},{h}",
                    "--virtual-time-budget=6000", f"--screenshot={out}", url],
                   check=True, capture_output=True, timeout=120)


def _view_png(view, out: str, scale: int = 2) -> None:
    """Draw a view into a PNG at `scale`x, whatever the screen's backing scale
    (a headless or non-Retina session would otherwise give a blurry 1x image)."""
    from AppKit import NSBitmapImageRep
    bounds = view.bounds()
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, int(bounds.size.width * scale), int(bounds.size.height * scale),
        8, 4, True, False, "NSCalibratedRGBColorSpace", 0, 0)
    rep.setSize_(bounds.size)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    with open(out, "wb") as f:
        f.write(bytes(rep.representationUsingType_properties_(4, {})))   # PNG


def _bare_app():
    """A TokenCoachApp that is drawn but never run, with no real config."""
    import threading
    import rumps
    from tokencoach.ui import TokenCoachApp
    app = TokenCoachApp.__new__(TokenCoachApp)
    # rumps.App creates ~/Library/Application Support/<name>; keep that out of
    # the person's real Library while drawing.
    import rumps.rumps as _rumps_impl
    real = _rumps_impl.application_support
    scratch = tempfile.mkdtemp(prefix="tokencoach-render-")
    _rumps_impl.application_support = lambda name: scratch
    try:
        rumps.App.__init__(app, "TokenCoach", quit_button=None)
    finally:
        _rumps_impl.application_support = real
    app.config, app._config_lock = {}, threading.Lock()
    return app


def render_panel(conn, out: str) -> None:
    """The real menu bar panel, drawn offscreen with sample quota and spend."""
    import sqlite3
    from datetime import datetime
    from AppKit import NSAppearance
    from tokencoach import ledger
    from tokencoach.providers import LimitRow, UsageData, ProviderData
    from tokencoach.ui import _UsagePanel
    app = _bare_app()
    app._history, app._last_updated = {}, datetime.now()
    app._last_data = UsageData(session=LimitRow("5-hour", 38, "resets today 16:40"),
                               weekly_all=LimitRow("Weekly", 61, "resets Thu 09:00"))
    chatgpt = ProviderData(name="ChatGPT")
    chatgpt._rows = [LimitRow("5-hour", 22, "resets today 18:05"), LimitRow("Weekly", 47, "resets Mon 10:00")]
    app._provider_data = [chatgpt]
    app._history_db = sqlite3.connect(":memory:")
    app._history_db.execute("CREATE TABLE samples (ts, key, pct)")
    app._ledger_summary, app._ledger_status = ledger.today_summary(conn), ""
    panel = _UsagePanel(app)
    panel._ensure_built()
    panel._rebuild_content()
    panel._panel.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
    _view_png(panel._panel.contentView(), out)


def render_setup_guide(out_dir: str) -> list[str]:
    """The first-run guide's dialogs, as a new script install sees them.

    Runs the real `_run_setup_guide` with each dialog drawn to a PNG instead
    of shown, always taking the first button. Nothing is saved, nudges are not
    turned on and the sign-in window never opens."""
    from AppKit import NSAlert, NSAppearance
    from tokencoach import nudge, onboarding, ui
    steps = onboarding.plan_steps(codex_found=False, nudges_on=False)
    written = []

    def draw(title=None, message="", ok=None, cancel=None, other=None, icon_path=None):
        if not isinstance(cancel, str):
            cancel = "Cancel" if cancel else None
        alert = NSAlert.alertWithMessageText_defaultButton_alternateButton_otherButton_informativeTextWithFormat_(
            title, ok, cancel, other, str(message).replace("%", "%%"))
        alert.setAlertStyle_(0)
        window = alert.window()
        window.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameAqua"))
        alert.layout()
        out = os.path.join(out_dir, f"setup-{len(written) + 1}-{steps[len(written)]}.png")
        _view_png(window.contentView().superview(), out)
        written.append(out)
        return 1

    app = _bare_app()
    app.set_nudges = app._sign_in = app._follow_browser_login = lambda *a: None
    patches = [(ui.rumps, "alert", draw), (ui, "save_config", lambda *a: None),
               (ui, "bundled", lambda: False),
               (ui._providers, "codex_signin_available", lambda: False),
               (nudge, "is_installed", lambda: False)]
    saved = [(obj, name, getattr(obj, name)) for obj, name, _ in patches]
    try:
        for obj, name, value in patches:
            setattr(obj, name, value)
        app._run_setup_guide()
    finally:
        for obj, name, value in saved:
            setattr(obj, name, value)
    return written


def capture(conn, config: dict, out_dir: str) -> list[str]:
    if not DEMO:
        raise RuntimeError("Screenshots are only taken from sample data (--screenshots).")
    if not os.path.exists(CHROME):
        raise RuntimeError("Google Chrome is needed for screenshots.")
    from tokencoach.ledger_report import build_report
    os.makedirs(out_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="tokencoach-shots-")
    page = os.path.join(tmp, "dashboard.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(build_report(conn, config))
    written = []
    for name, (qs, w, h) in SHOTS.items():
        out = os.path.join(out_dir, f"{name}.png")
        _shoot(f"file://{page}?{qs}", out, w, h)
        written.append(out)
    nudge = os.path.join(tmp, "nudge.html")
    with open(nudge, "w", encoding="utf-8") as f:
        f.write(NUDGE_HTML)
    out = os.path.join(out_dir, "nudge.png")
    _shoot(f"file://{nudge}", out, 1000, 250)
    written.append(out)
    try:
        out = os.path.join(out_dir, "panel.png")
        render_panel(conn, out)
        written.append(out)
    except Exception:
        log.exception("panel screenshot failed")
    try:
        written += render_setup_guide(out_dir)
    except Exception:
        log.exception("setup guide screenshots failed")
    log.info("screenshots written to %s", out_dir)
    return written
