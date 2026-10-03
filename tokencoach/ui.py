"""UI components -- menu bar app, floating panel, windows."""

import rumps
import atexit
import json
import os
import subprocess
import sys
import tempfile
import time
import threading
import urllib.parse
from datetime import datetime, timezone, timedelta

from tokencoach.config import (
    APP_NAME, REPO_URL, UPSTREAM_URL, LAUNCH_AGENT_LABEL, LAUNCH_AGENT_PLIST, LOG_FILE, log, load_config, save_config, notif_enabled, set_notif,
    install_python, QUIT_MARKER,
    REFRESH_INTERVALS, DEFAULT_REFRESH,
    WARN_THRESHOLD, CRIT_THRESHOLD, PACING_ALERT_MINUTES,
    UPDATE_CHECK_INTERVAL, HISTORY_COLORS,
    WIDGET_CACHE_DIR,
)
from tokencoach.providers import (
    LimitRow, UsageData, ProviderData, parse_usage, fetch_raw,
    fetch_claude_code_stats, fetch_chatgpt, PROVIDER_REGISTRY, COOKIE_PROVIDERS,
    CurlHTTPError, parse_cookie_string,
    _auto_detect_cookies, _auto_detect_chatgpt_cookies,
    _warn_keychain_once, _fmt_reset, _BROWSER_COOKIE3_OK,
)
from tokencoach.history import (
    _load_history, _save_history, _append_history,
    _calc_burn_rate, _calc_eta_minutes, _fmt_eta, _sparkline,
    _init_history_db, _record_sample, _rollup_daily_stats,
    _get_today_stats,
    _fetch_history_data, _nscolor,
)
from tokencoach.widget import _write_widget_cache, _is_widget_installed
from tokencoach.update import _check_and_apply_update, _restart_app
from tokencoach import ledger as _ledger
from tokencoach import providers as _providers
from tokencoach import health


# -- Brand icon helpers --------------------------------------------------------

_ICON_DIR   = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_ICON_SIZE  = 14   # points -- matches menu bar font height
_icon_cache: dict = {}


def _bar_icon(filename: str, tint_hex: str | None = None):
    """Lazy-load and cache a menu bar icon (14x14 pt NSImage).

    tint_hex: e.g. '#74AA9C' -- applied to monochrome (black) icons so they
              show in the brand color. Pass None for already-coloured icons.
    """
    key = (filename, tint_hex)
    if key in _icon_cache:
        return _icon_cache[key]
    img = None
    try:
        from AppKit import NSImage, NSColor
        path = os.path.join(_ICON_DIR, filename)
        raw = NSImage.alloc().initWithContentsOfFile_(path)
        if raw:
            img = raw.copy()
            img.setSize_((_ICON_SIZE, _ICON_SIZE))
            if tint_hex:
                r = int(tint_hex[1:3], 16) / 255
                g = int(tint_hex[3:5], 16) / 255
                b = int(tint_hex[5:7], 16) / 255
                color = NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)
                img.setTemplate_(True)
                if hasattr(img, "imageWithTintColor_"):
                    img = img.imageWithTintColor_(color)
    except Exception as e:
        log.debug("_bar_icon %s: %s", filename, e)
    _icon_cache[key] = img
    return img


def _icon_astr(img, base_attrs: dict):
    """Wrap an NSImage in an NSAttributedString via NSTextAttachment."""
    from AppKit import NSTextAttachment, NSAttributedString
    from Foundation import NSMakeRect, NSMutableAttributedString
    att = NSTextAttachment.alloc().init()
    att.setImage_(img)
    att.setBounds_(NSMakeRect(0, -3, _ICON_SIZE, _ICON_SIZE))
    astr = NSAttributedString.attributedStringWithAttachment_(att)
    m = NSMutableAttributedString.alloc().initWithAttributedString_(astr)
    for k, v in base_attrs.items():
        m.addAttribute_value_range_(k, v, (0, m.length()))
    return m


# -- Sticky toggle view (menu stays open on click) ----------------------------

_HAS_TOGGLE_VIEW = False
try:
    from AppKit import NSView, NSTextField, NSFont, NSColor, NSBezierPath, NSTrackingArea
    from Foundation import NSMakeRect
    import objc

    _TRACK_FLAGS = 0x01 | 0x80   # mouseEnteredAndExited | activeInActiveApp

    class _BarToggleView(NSView):
        """Custom NSView for menu items -- clicking does NOT dismiss the menu."""

        def initWithFrame_(self, frame):
            self = objc.super(_BarToggleView, self).initWithFrame_(frame)
            if self:
                self._action = None
                self._label = None
                self._hovering = False
                area = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
                    self.bounds(), _TRACK_FLAGS, self, None,
                )
                self.addTrackingArea_(area)
            return self

        def mouseUp_(self, event):
            if callable(self._action):
                self._action()

        def mouseEntered_(self, event):
            self._hovering = True
            self.setNeedsDisplay_(True)

        def mouseExited_(self, event):
            self._hovering = False
            self.setNeedsDisplay_(True)

        def drawRect_(self, rect):
            if self._hovering:
                NSColor.selectedMenuItemColor().set()
                NSBezierPath.fillRect_(rect)
                if self._label:
                    self._label.setTextColor_(NSColor.selectedMenuItemTextColor())
            else:
                if self._label:
                    self._label.setTextColor_(NSColor.labelColor())

    _HAS_TOGGLE_VIEW = True
except Exception:
    pass


# -- History window helpers ----------------------------------------------------

def _ensure_history_handler():
    """Lazily create an ObjC click handler for heatmap cells."""
    h = getattr(_ensure_history_handler, '_inst', None)
    if h is not None:
        return h
    try:
        from AppKit import NSObject

        class _HMapHandler(NSObject):
            def cellClicked_(self, sender):
                fn = getattr(type(self), '_on_click', None)
                if fn:
                    fn(sender.tag())
        _ensure_history_handler._inst = _HMapHandler.alloc().init()
    except Exception:
        log.debug("Failed to create history click handler", exc_info=True)
        _ensure_history_handler._inst = None
    return _ensure_history_handler._inst


def _show_history_window(conn) -> None:
    """Show a native macOS Usage History window with heatmap, stats, and charts."""
    from AppKit import (
        NSWindow, NSTextField, NSFont, NSColor, NSView, NSScrollView,
        NSButton, NSMakeRect, NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
        NSWindowStyleMaskFullSizeContentView, NSBackingStoreBuffered,
        NSTextAlignmentCenter, NSTextAlignmentLeft,
        NSApplication, NSFloatingWindowLevel, NSScreen,
        NSVisualEffectView,
    )
    import Quartz

    # Reuse existing window if open
    existing = getattr(_show_history_window, "_active_win", None)
    if existing is not None:
        try:
            existing.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            return
        except Exception:
            pass

    data = _fetch_history_data(conn)
    if data is None:
        return

    WIN_W = 560
    WIN_H = 680
    PAD = 28
    inner_w = WIN_W - PAD * 2

    summary = data["summary"]
    days = data["days"]
    per_day_detail = data.get("per_day_detail", {})
    today_windows = data.get("today_windows", {})
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Only show providers that have actual usage data
    providers = [p for p in data["providers"] if p["peak"] > 0]

    # -- Helpers --------------------------------------------------------

    def _cg(hex_str, alpha=1.0):
        h = hex_str.lstrip("#")
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
        return Quartz.CGColorCreateGenericRGB(r, g, b, alpha)

    dark_bg = _cg("#1C1C2A")
    card_bg = _cg("#232336")
    track_bg = _cg("#1C1C2A")
    dim = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.55, 0.55, 0.6, 1.0)
    dimmer = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.4, 0.45, 1.0)

    # -- Precompute heatmap cell sizing (needed for doc_h) ----------------
    today = datetime.now(timezone.utc).date()
    _hm_start = today - timedelta(days=89)
    _hm_start -= timedelta(days=_hm_start.weekday())
    _hm_num_days = (today - _hm_start).days + 1
    _hm_num_cols = (_hm_num_days + 6) // 7
    DAY_LABEL_W = 32
    _hm_avail = inner_w - DAY_LABEL_W
    HGAP = 3
    CELL = max(10, int((_hm_avail - HGAP * (_hm_num_cols - 1)) / _hm_num_cols))
    HSTEP = CELL + HGAP

    # -- Compute total content height -------------------------------------
    HEATMAP_H = 7 * HSTEP + 14 + CELL + 8  # 7 rows + month labels + legend
    CARD_H = 60
    BAR_H = 14
    BAR_GAP = 5
    INTRADAY_BLOCK = 20 + 5 * (BAR_H + BAR_GAP) + 8

    doc_h = PAD + 16          # top padding (below titlebar)
    doc_h += 32 + 22          # title + subtitle
    doc_h += 16 + HEATMAP_H   # gap + heatmap
    doc_h += 24               # day info row below heatmap
    doc_h += 24 + CARD_H      # gap + stat cards
    PROV_HEADER = 22 + 18     # colored dot/name + summary line
    for p in providers:
        doc_h += 24 + PROV_HEADER
        if p["key"] in today_windows:
            doc_h += INTRADAY_BLOCK
        else:
            doc_h += 7 * (BAR_H + BAR_GAP) + 16
    doc_h += 24 + 20 + PAD    # gap + footer + bottom pad
    doc_h = max(doc_h, WIN_H)

    # Placement helpers: top_y is logical offset from top, converted to
    # NSView bottom-up coordinates via  real_y = parent_h - top_y - h

    def _v(parent, x, top_y, w, h, bg=None, corner=0, ph=None, tooltip=None):
        real_y = (ph or doc_h) - top_y - h
        v = NSView.alloc().initWithFrame_(NSMakeRect(x, real_y, w, h))
        v.setWantsLayer_(True)
        if bg:
            v.layer().setBackgroundColor_(bg)
        if corner:
            v.layer().setCornerRadius_(corner)
            v.layer().setMasksToBounds_(True)
        if tooltip:
            v.setToolTip_(tooltip)
        parent.addSubview_(v)
        return v

    def _lbl(parent, text, x, top_y, w, h=0, size=12, weight=0.0,
             color=None, align=NSTextAlignmentLeft, mono=False, ph=None):
        if h == 0:
            h = int(size * 1.5 + 2)
        real_y = (ph or doc_h) - top_y - h
        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(x, real_y, w, h))
        lbl.setStringValue_(text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setAlignment_(align)
        if mono:
            lbl.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(size, weight))
        else:
            lbl.setFont_(NSFont.systemFontOfSize_weight_(size, weight))
        lbl.setTextColor_(color or NSColor.labelColor())
        parent.addSubview_(lbl)
        return lbl

    # -- Build window -----------------------------------------------------
    screen = NSScreen.mainScreen().frame()
    sx = (screen.size.width - WIN_W) / 2
    sy = (screen.size.height - WIN_H) / 2

    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(sx, sy, WIN_W, WIN_H),
        (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
         | NSWindowStyleMaskFullSizeContentView),
        NSBackingStoreBuffered,
        False,
    )
    win.setTitle_("")
    win.setTitlebarAppearsTransparent_(True)
    win.setTitleVisibility_(1)
    win.setLevel_(NSFloatingWindowLevel)
    win.setMovableByWindowBackground_(True)

    content = win.contentView()
    content.setWantsLayer_(True)

    blur = NSVisualEffectView.alloc().initWithFrame_(content.bounds())
    blur.setAutoresizingMask_(18)
    blur.setBlendingMode_(0)
    blur.setMaterial_(3)
    blur.setState_(1)
    content.addSubview_(blur)

    scroll = NSScrollView.alloc().initWithFrame_(content.bounds())
    scroll.setAutoresizingMask_(18)
    scroll.setHasVerticalScroller_(True)
    scroll.setDrawsBackground_(False)
    scroll.setBorderType_(0)
    content.addSubview_(scroll)

    doc = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, doc_h))
    scroll.setDocumentView_(doc)

    # -- Layout (top-down y cursor) ---------------------------------------
    y = PAD + 16

    # Title
    _lbl(doc, "Usage History", PAD, y, inner_w, size=22, weight=0.56)
    y += 32
    _lbl(doc, f"Average daily usage across all providers  \u00b7  {summary['total_days']} days tracked",
         PAD, y, inner_w, size=12, color=dim)
    y += 30

    # -- Heatmap (hero section -- fills available width) ------------------
    HLEFT = PAD + DAY_LABEL_W
    hm_top = y
    start = _hm_start

    # Day labels
    for row, dl in enumerate(["Mon", "", "Wed", "", "Fri", "", "Sun"]):
        if dl:
            _lbl(doc, dl, PAD, hm_top + row * HSTEP + 1, DAY_LABEL_W - 4,
                 size=9, color=dimmer)

    # Cells (interactive NSButtons for click-to-inspect)
    handler = _ensure_history_handler()
    date_for_tag = {}  # tag -> date_str
    tag_counter = [0]

    current = start
    col = 0
    last_month = -1
    while current <= today:
        row = current.weekday()
        cx = HLEFT + col * HSTEP
        cy = hm_top + row * HSTEP

        if current.month != last_month and row == 0:
            _lbl(doc, current.strftime("%b"), cx, hm_top - 14, 40,
                 size=9, color=dimmer)
            last_month = current.month

        ds = current.strftime("%Y-%m-%d")
        pct = days.get(ds, -1)
        if pct < 0:
            cc = dark_bg
            tip = f"{ds}  \u2013  No data"
        else:
            t = min(pct / 100, 1.0)
            r = 0.14 + t * 0.71
            g = 0.14 + t * 0.33
            b = 0.20 + t * 0.14
            cc = Quartz.CGColorCreateGenericRGB(r, g, b, 1.0)
            tip = f"{ds}  \u2013  Peak usage {pct}%"

        tag = tag_counter[0]
        tag_counter[0] += 1
        date_for_tag[tag] = ds

        real_y = doc_h - cy - CELL
        btn = NSButton.alloc().initWithFrame_(NSMakeRect(cx, real_y, CELL, CELL))
        btn.setBordered_(False)
        btn.setTitle_("")
        btn.setWantsLayer_(True)
        btn.layer().setBackgroundColor_(cc)
        btn.layer().setCornerRadius_(3)
        btn.layer().setMasksToBounds_(True)
        btn.setToolTip_(tip)
        if handler:
            btn.setTarget_(handler)
            btn.setAction_(b"cellClicked:")
            btn.setTag_(tag)
        doc.addSubview_(btn)

        if row == 6:
            col += 1
        current += timedelta(days=1)

    # Legend
    legend_y = hm_top + 7 * HSTEP + 8
    lx = HLEFT
    _lbl(doc, "Less", lx - 30, legend_y + 1, 28, size=9, color=dimmer)
    for lv in [0, 25, 50, 75, 100]:
        t = lv / 100
        lr = 0.14 + t * 0.71
        lg = 0.14 + t * 0.33
        lb = 0.20 + t * 0.14
        _v(doc, lx, legend_y, CELL, CELL,
           Quartz.CGColorCreateGenericRGB(lr, lg, lb, 1.0), corner=3)
        lx += HSTEP
    _lbl(doc, "More", lx + 3, legend_y + 1, 30, size=9, color=dimmer)

    y = legend_y + CELL + 16

    # -- Selected Day info row (updatable on click) ----------------------
    _day_names_fmt = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    def _fmt_date_label(ds):
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d")
            return f"{_day_names_fmt[dt.weekday()]} {dt.strftime('%b %d')}"
        except Exception:
            return ds

    today_detail = per_day_detail.get(today_str, {})
    info_parts = []
    for key, stats in sorted(today_detail.items()):
        lbl_name = (key.replace("_", " ").title()
                    .replace("Chatgpt", "ChatGPT").replace("Api", "API"))
        info_parts.append(f"{lbl_name} {stats['avg_pct']}% used")
    initial_info = (f"{_fmt_date_label(today_str)}  \u2014  "
                    + "  \u00b7  ".join(info_parts)) if info_parts else "Click a cell to see day details"

    info_label = _lbl(doc, initial_info, PAD, y, inner_w, size=11, color=dim)
    y += 24

    # Wire click handler to update info label
    if handler:
        def _on_click(tag):
            ds = date_for_tag.get(tag, "")
            if not ds:
                return
            detail = per_day_detail.get(ds, {})
            parts = []
            for key, stats in sorted(detail.items()):
                name = (key.replace("_", " ").title()
                        .replace("Chatgpt", "ChatGPT").replace("Api", "API"))
                parts.append(f"{name} {stats['avg_pct']}% used")
            text = f"{_fmt_date_label(ds)}  \u2014  "
            text += "  \u00b7  ".join(parts) if parts else "No data"
            info_label.setStringValue_(text)
        type(handler)._on_click = _on_click

    # -- Stats Cards ------------------------------------------------------
    CARD_GAP = 10
    card_w = (inner_w - CARD_GAP * 2) / 3
    cards = [
        (f"{summary['highest'][1]}%", "Highest Day", summary["highest"][0], "#D97757"),
        (f"{summary['lowest'][1]}%", "Lowest Day", summary["lowest"][0], "#74AA9C"),
        (f"{summary['avg']}%", "Daily Avg", "", "#6E40C9"),
    ]
    for i, (val, lbl, sub, clr) in enumerate(cards):
        cx = PAD + i * (card_w + CARD_GAP)
        card = _v(doc, cx, y, card_w, CARD_H, card_bg, corner=10)
        # Accent bar
        _v(card, 0, 8, 3, CARD_H - 16, _cg(clr), corner=1.5, ph=CARD_H)
        # Value
        _lbl(card, val, 12, 10, card_w - 16, size=17, weight=0.56, mono=True, ph=CARD_H)
        # Label
        _lbl(card, lbl, 12, 32, card_w - 16, size=10, color=dim, ph=CARD_H)
        # Sub-label
        if sub:
            _lbl(card, sub, 12, 44, card_w - 16, size=9, color=dimmer, ph=CARD_H)

    y += CARD_H + 24

    # -- Per-provider sections (only those with data) ---------------------
    _day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    BLABEL_W = 32
    BPCT_W = 38

    # Metric context: what the % means for each provider key
    _metric_hint = {
        "claude": "5-hour session window",
    }

    for prov in providers:
        # Colored dot + name
        _v(doc, PAD, y + 5, 8, 8, _cg(prov["color"]), corner=4)
        _lbl(doc, prov["label"], PAD + 14, y, 250, size=14, weight=0.5)
        # Metric hint next to name
        hint = _metric_hint.get(prov["key"], "rate limit")
        _lbl(doc, hint, PAD + 14 + len(prov["label"]) * 9, y + 2, 200,
             size=10, color=dimmer)
        y += 22

        # Summary
        stxt = f"Avg {prov['avg']}% used  \u00b7  Peak {prov['peak']}% used"
        _lbl(doc, stxt, PAD, y, inner_w, size=11, color=dim)
        y += 18

        bar_area = inner_w - BLABEL_W - BPCT_W - 8
        accent = _cg(prov["color"])

        # Intraday 5h windows replace the 7-day chart when available
        prov_windows = today_windows.get(prov["key"], {})
        if prov_windows:
            _lbl(doc, "Today\u2019s Sessions", PAD, y, inner_w, size=11, weight=0.4, color=dim)
            y += 20
            window_labels = ["00\u201305h", "05\u201310h", "10\u201315h", "15\u201320h", "20\u201324h"]
            for widx in range(5):
                wpct = prov_windows.get(widx, 0)
                wy = y + widx * (BAR_H + BAR_GAP)
                _lbl(doc, window_labels[widx], PAD, wy + 1, BLABEL_W + 10,
                     h=BAR_H, size=9, color=dim)
                _v(doc, PAD + BLABEL_W + 10, wy, bar_area - 10, BAR_H, track_bg, corner=4)
                if wpct > 0:
                    bw = max(6, (bar_area - 10) * wpct / 100)
                    _v(doc, PAD + BLABEL_W + 10, wy, bw, BAR_H, accent, corner=4)
                _lbl(doc, f"{wpct}%", PAD + BLABEL_W + bar_area + 6, wy + 1, BPCT_W,
                     h=BAR_H, size=10, weight=0.3, color=dim, mono=True)
            y += 5 * (BAR_H + BAR_GAP) + 8
        else:
            # 7-day bar chart (fallback when no intraday data)
            day_data = {d["date"]: d["peak_pct"] for d in prov["weekly"]}
            for i in range(7):
                day = today - timedelta(days=6 - i)
                ds = day.strftime("%Y-%m-%d")
                pct = day_data.get(ds, 0)
                by = y + i * (BAR_H + BAR_GAP)

                _lbl(doc, _day_names[day.weekday()], PAD, by + 1, BLABEL_W,
                     h=BAR_H, size=10, color=dim)
                _v(doc, PAD + BLABEL_W, by, bar_area, BAR_H, track_bg, corner=4)
                if pct > 0:
                    bw = max(6, bar_area * pct / 100)
                    _v(doc, PAD + BLABEL_W, by, bw, BAR_H, accent, corner=4)
                _lbl(doc, f"{pct}%", PAD + BLABEL_W + bar_area + 6, by + 1, BPCT_W,
                     h=BAR_H, size=10, weight=0.3, color=dim, mono=True)
            y += 7 * (BAR_H + BAR_GAP) + 16

    # -- Footer -----------------------------------------------------------
    _lbl(doc, f"Data since {summary['earliest']}  \u00b7  {summary['total_days']} days tracked",
         PAD, y, inner_w, size=10, color=dimmer, align=NSTextAlignmentCenter)

    # -- Scroll to top ----------------------------------------------------
    visible_h = scroll.contentSize().height
    if doc_h > visible_h:
        clip = scroll.contentView()
        clip.scrollToPoint_((0, doc_h - visible_h))
        scroll.reflectScrolledClipView_(clip)

    win.makeKeyAndOrderFront_(None)
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    _show_history_window._active_win = win


# -- Display helpers -----------------------------------------------------------

def _fmt_count(n: int) -> str:
    """Format a message count compactly: 1234 -> '1.2k', 999 -> '999'."""
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _remaining(pct: int) -> int:
    """Providers report percent USED; every user-facing gauge shows what's left.

    Kept as a single conversion point: usage stays the internal unit, so alert
    thresholds and history keep working, and only the display inverts.
    """
    return max(0, min(100, 100 - pct))


def _bar(pct: int, width: int = 14) -> str:
    filled = round(pct / 100 * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def _status_icon(pct: int) -> str:
    if pct >= CRIT_THRESHOLD:
        return "\U0001f534"
    if pct >= WARN_THRESHOLD:
        return "\U0001f7e1"
    return "\U0001f7e2"


def _row_lines(row: LimitRow) -> list[str]:
    left = _remaining(row.pct)
    bar = _bar(left)
    line1 = f"  {row.label}  {left}% left"
    line2 = f"  {bar}  {row.reset_str}" if row.reset_str else f"  {bar}"
    return [line1, line2]


def _panel_reset_label(reset_str: str) -> str:
    """Compact a row's reset copy for the floating panel.

    Claude omits a 5-hour reset while that rolling window has not started.
    Say so rather than rendering a blank line or inventing a date. Keep
    near-term resets relative so their distance is instantly scannable.
    """
    if not reset_str:
        return "starts on use"

    text = reset_str.removeprefix("resets ")
    if text.startswith("today "):
        return text.removeprefix("today ")
    if text.startswith("tomorrow "):
        return f"+1d {text.removeprefix('tomorrow ')}"

    now = datetime.now().astimezone()
    weekday, _, clock = text.partition(" ")
    weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    if weekday in weekdays and clock:
        days = (weekdays.index(weekday) - now.weekday()) % 7 or 7
        return f"+{days}d {clock}"

    try:
        target = datetime.strptime(text, "%b %d, %H:%M").replace(
            year=now.year, tzinfo=now.tzinfo
        )
        if target < now:
            target = target.replace(year=target.year + 1)
        days = (target.date() - now.date()).days
        if 1 <= days <= 7:
            return f"+{days}d {target.strftime('%H:%M')}"
    except ValueError:
        pass
    return text.replace(",", "")


def _panel_limit_label(row: LimitRow) -> str:
    """Fit a limit's window and reset time into one floating-panel line."""
    window = {
        "5-hour": "5h",
        "Weekly": "W",
        "Weekly (Sonnet)": "W/S",
    }.get(row.label, row.label)
    return f"{window} \u00b7 {_panel_reset_label(row.reset_str)}"


def _provider_lines(pd: ProviderData) -> list[str]:
    sym = "\u00a5" if pd.currency == "CNY" else ("" if pd.currency == "" else "$")
    if pd.error:
        return [f"  \u26a0\ufe0f  {pd.error[:60]}"]
    # ChatGPT multi-row format (stored in pd._rows by _parse_wham_usage)
    rows = getattr(pd, "_rows", None)
    if rows:
        lines = []
        for row in rows:
            for line in _row_lines(row):
                if line:
                    lines.append(line)
        return lines
    # Standard spending / balance format
    lines = []
    if pd.pct is not None:
        left = _remaining(pd.pct)
        bar = _bar(left)
        lines.append(f"  {sym}{pd.spent:.2f} / {sym}{pd.limit:.2f} {pd.period}")
        lines.append(f"  {bar}  {left}% left")
    elif pd.balance is not None:
        lines.append(f"  {sym}{pd.balance:.2f} remaining")
    elif pd.spent is not None:
        lines.append(f"  {sym}{pd.spent:.2f} {pd.period}")
    return lines


def _mi(title: str) -> rumps.MenuItem:
    """Display-only menu item (non-clickable but visually active)."""
    item = rumps.MenuItem(title)
    item.set_callback(None)
    item._menuitem.setEnabled_(True)
    return item


# Apple system orange / red, as in the dashboard and the menu bar percentage.
_HEALTH_HEX = {health.WATCH: "#FF9F0A", health.CRITICAL: "#FF3B30"}


def _colored_mi(title: str, color_hex: str) -> rumps.MenuItem:
    """Display-only menu item with brand-colored text."""
    item = rumps.MenuItem(title)
    item.set_callback(None)
    item._menuitem.setEnabled_(True)
    try:
        from AppKit import NSColor, NSForegroundColorAttributeName
        from Foundation import NSAttributedString
        r = int(color_hex[1:3], 16) / 255
        g = int(color_hex[3:5], 16) / 255
        b = int(color_hex[5:7], 16) / 255
        color = NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 0.75)
        astr = NSAttributedString.alloc().initWithString_attributes_(
            title, {NSForegroundColorAttributeName: color}
        )
        item._menuitem.setAttributedTitle_(astr)
    except Exception as e:
        log.debug("_colored_mi: %s", e)
    return item


def _menu_icon(filename: str, tint_hex: str | None = None, size: int = 16):
    """Load an NSImage for use in a menu item, optionally tinted."""
    try:
        from AppKit import NSImage, NSColor
        path = os.path.join(_ICON_DIR, filename)
        raw = NSImage.alloc().initWithContentsOfFile_(path)
        if not raw:
            return None
        img = raw.copy()
        img.setSize_((size, size))
        if tint_hex:
            r = int(tint_hex[1:3], 16) / 255
            g = int(tint_hex[3:5], 16) / 255
            b = int(tint_hex[5:7], 16) / 255
            color = NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)
            img.setTemplate_(True)
            if hasattr(img, "imageWithTintColor_"):
                img = img.imageWithTintColor_(color)
        return img
    except Exception as e:
        log.debug("_menu_icon %s: %s", filename, e)
        return None


def _section_header_mi(title: str, icon_filename: str | None,
                        color_hex: str, icon_tint: str | None = None) -> rumps.MenuItem:
    """Section header with brand icon and colored bold title."""
    item = rumps.MenuItem(title)
    item.set_callback(None)
    item._menuitem.setEnabled_(True)
    try:
        from AppKit import (NSColor, NSFont,
                            NSForegroundColorAttributeName, NSFontAttributeName)
        from Foundation import NSAttributedString
        r = int(color_hex[1:3], 16) / 255
        g = int(color_hex[3:5], 16) / 255
        b = int(color_hex[5:7], 16) / 255
        color = NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)
        font = NSFont.boldSystemFontOfSize_(13)
        attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
        astr = NSAttributedString.alloc().initWithString_attributes_(title, attrs)
        item._menuitem.setAttributedTitle_(astr)
        if icon_filename:
            img = _menu_icon(icon_filename, tint_hex=icon_tint)
            if img:
                item._menuitem.setImage_(img)
    except Exception as e:
        log.debug("_section_header_mi: %s", e)
    return item


# -- login item helpers --------------------------------------------------------

def _script_path() -> str:
    # The LaunchAgent must launch the package entry shim, not this module
    # file: `python3 .../tokencoach/ui.py` fails (the tokencoach package is
    # not importable that way and ui.py has no __main__ guard). tokencoach.py
    # lives at the repo root and puts that root on sys.path so the package
    # resolves. Fall back to this file only if the shim is somehow missing.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shim = os.path.join(root, "tokencoach.py")
    return shim if os.path.exists(shim) else os.path.abspath(__file__)


def _is_login_item() -> bool:
    """Starts at login when our LaunchAgent exists (no System Events prompt)."""
    return os.path.exists(LAUNCH_AGENT_PLIST)


def _login_item_args() -> list[str]:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [install_python(root), _script_path()]


def _login_item_current() -> bool:
    """The agent exists and launches this install. One written by an older
    Homebrew version points at a Cellar folder that `brew upgrade` deleted."""
    import plistlib
    try:
        with open(LAUNCH_AGENT_PLIST, "rb") as f:
            return plistlib.load(f).get("ProgramArguments") == _login_item_args()
    except Exception:
        return False


def _job_pid(wait: float = 0.0) -> int | None:
    """PID launchd reports for our agent, waiting up to `wait` seconds for one."""
    import re
    deadline = time.time() + wait
    while True:
        out = subprocess.run(["launchctl", "list", LAUNCH_AGENT_LABEL],
                             capture_output=True, text=True).stdout
        m = re.search(r'"PID" = (\d+);', out)
        if m or time.time() >= deadline:
            return int(m.group(1)) if m else None
        time.sleep(0.5)


def _stop_other_copies() -> list[int]:
    """Stop other menu bar copies of this install, such as one started by hand
    before the login item existed. Homebrew installs have no doctor to do it."""
    script = _script_path()
    out = subprocess.run(["ps", "-Ao", "pid=,args="], capture_output=True, text=True).stdout
    stopped = []
    for line in out.splitlines():
        pid, _, args = line.strip().partition(" ")
        parts = args.split()
        if len(parts) == 2 and parts[1] == script and pid.isdigit() and int(pid) != os.getpid():
            try:
                os.kill(int(pid), 15)
                stopped.append(int(pid))
            except OSError:
                pass
    return stopped


def _add_login_item(handoff: bool = False) -> bool:
    """Write the agent and load it. With `handoff`, returns True when launchd
    now runs its own supervised copy, so this process should exit: two copies
    would show two icons."""
    import plistlib
    plist = LAUNCH_AGENT_PLIST
    plist_data = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": _login_item_args(),
        "RunAtLoad": True,
        # Restart on ANY exit. This used to be {"SuccessfulExit": False}, which
        # respawns only after a crash - so any clean exit left the app dead
        # until the next login, with nothing reporting that it had gone.
        # Quit still works: _quit_app() unloads this job first, so launchd has
        # nothing to respawn. _restart_app() restarts through launchctl
        # kickstart, so launchd never runs two copies.
        "KeepAlive": True,
        "StandardOutPath": LOG_FILE,
        "StandardErrorPath": LOG_FILE,
    }
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    with open(plist, "wb") as f:
        plistlib.dump(plist_data, f)
    if _job_pid() == os.getpid():
        return False        # we are the job; launchd reads the new file at the next login
    # a job loaded from a stale file keeps failing to spawn until it is reloaded
    subprocess.run(["launchctl", "unload", plist], capture_output=True)
    result = subprocess.run(["launchctl", "load", plist], capture_output=True)
    if result.returncode != 0:
        log.warning("launchctl load failed: %s", result.stderr.decode(errors="replace"))
        return False
    return handoff and _job_pid(wait=3) not in (None, os.getpid())


def _quit_app(_sender=None):
    """Quit for real.

    The launch agent is KeepAlive, so simply exiting would be undone within
    seconds. Unload the job first; launchd then has nothing to respawn. The
    plist stays on disk, so it starts again at the next login or from the Dock
    launcher. The marker tells the doctor's watchdog to leave it stopped.
    """
    try:
        with open(QUIT_MARKER, "w") as f:
            f.write(f"{time.time():.0f}\n")
    except OSError:
        log.debug("could not write quit marker", exc_info=True)
    try:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"],
            capture_output=True,
        )
    except Exception:
        log.debug("bootout on quit failed", exc_info=True)
    rumps.quit_application()


def _remove_login_item():
    plist = LAUNCH_AGENT_PLIST
    if os.path.exists(plist):
        subprocess.run(["launchctl", "unload", plist], capture_output=True)
        os.remove(plist)


# -- native macOS dialogs via osascript ----------------------------------------

def _ask_text(title: str, prompt: str, default: str = "") -> str | None:
    def _esc(s: str) -> str:
        """Escape a string for safe embedding in AppleScript double-quoted strings."""
        return s.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'display dialog "{_esc(prompt)}" '
        f'default answer "{_esc(default)}" '
        f'with title "{_esc(title)}" '
        f'buttons {{"Cancel", "Save"}} default button "Save"'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return None
        out = result.stdout.strip()
        if "text returned:" in out:
            return out.split("text returned:")[-1].strip()
    except Exception:
        log.exception("_ask_text failed")
    return None


def _choose_file(prompt: str) -> str | None:
    """Native file picker via AppleScript; returns a POSIX path or None."""
    script = (
        f'POSIX path of (choose file with prompt "{prompt}" '
        'of type {"zip", "json", "public.zip-archive", "public.json"})'
    )
    try:
        result = subprocess.run(["osascript", "-e", script],
                                capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        log.exception("_choose_file failed")
    return None


def _ledger_menu_lines(summary: dict | None, status: str) -> list[str]:
    """Display lines for the menu's spend section (pure, testable)."""
    if summary is None:
        return ["  " + (status or "Indexing local logs\u2026")]
    lines = [
        f"  Today  {_ledger.fmt_usd(summary['cost'])}"
        f"  \u00b7  {summary['prompts']} prompts"
        f"  \u00b7  {_ledger.fmt_tokens(summary['tokens'])} tokens"
    ]
    tp = summary.get("top_project")
    if tp:
        lines.append(f"  Top project  {tp['project']}  {_ledger.fmt_usd(tp['cost'])}")
    top = summary.get("top_prompt")
    if top:
        text = " ".join(top["text"].split())
        if len(text) > 38:
            text = text[:37] + "\u2026"
        lines.append(f"  Top prompt  \u201c{text}\u201d  {_ledger.fmt_usd(top['cost'])}")
    if status:
        lines.append(f"  {status}")
    return lines


def _clipboard_text() -> str:
    try:
        result = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


# -- notification helpers ------------------------------------------------------

def _notify(title: str, subtitle: str, message: str = ""):
    """rumps.notification wrapper -- silently swallows if the notification
    center is unavailable (e.g. missing Info.plist in dev environments)."""
    try:
        rumps.notification(title, subtitle, message)
    except Exception as e:
        log.debug("notification suppressed: %s", e)


def _show_text(title: str, text: str):
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
            prefix="claude_usage_raw_"
        )
        tmp.write(text)
        tmp.close()
        subprocess.Popen(["open", "-a", "TextEdit", tmp.name])
        # Schedule cleanup after 60 seconds (enough time for TextEdit to open)
        def _cleanup():
            time.sleep(60)
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        threading.Thread(target=_cleanup, daemon=True).start()
    except Exception:
        log.exception("_show_text failed")


# -- floating panel (replaces NSMenu) ------------------------------------------

# Brand colors for each provider
_BRAND_COLORS = {
    "Claude": "#D97757",
    "ChatGPT": "#74AA9C",
}

# ObjC subclasses are defined lazily on first use so AppKit import
# doesn't crash in headless / test contexts.
_panel_classes_ready = False
_DismissablePanelClass = None
_ClickHandlerClass = None


def _ensure_panel_classes():
    """Create the ObjC subclasses exactly once."""
    global _panel_classes_ready, _DismissablePanelClass, _ClickHandlerClass
    if _panel_classes_ready:
        return
    try:
        from AppKit import NSPanel, NSObject
        import objc

        class _DismissablePanel(NSPanel):
            """Borderless panel that dismisses on Esc and focus loss."""

            def canBecomeKeyWindow(self):
                return True

            def resignKeyWindow(self):
                objc.super(_DismissablePanel, self).resignKeyWindow()
                try:
                    cb = getattr(self, '_dismiss_callback', None)
                    if callable(cb):
                        cb()
                except Exception:
                    pass

            def cancelOperation_(self, sender):
                try:
                    cb = getattr(self, '_dismiss_callback', None)
                    if callable(cb):
                        cb()
                except Exception:
                    pass

        class _ClickHandler(NSObject):
            """ObjC target for the NSStatusItem button click."""

            def togglePanel_(self, sender):
                try:
                    # Detect right-click: show fallback menu instead
                    from AppKit import NSApplication
                    evt = NSApplication.sharedApplication().currentEvent()
                    # NSEventTypeRightMouseDown=3, NSEventTypeRightMouseUp=4
                    if evt and evt.type() in (3, 4):
                        menu_fn = getattr(type(self), '_show_menu_fn', None)
                        if callable(menu_fn):
                            menu_fn()
                        return
                    cb = getattr(type(self), '_toggle_fn', None)
                    if callable(cb):
                        cb()
                except Exception:
                    log.debug("_ClickHandler.togglePanel_ error", exc_info=True)

            def refreshClicked_(self, sender):
                try:
                    cb = getattr(type(self), '_refresh_fn', None)
                    if callable(cb):
                        cb()
                except Exception:
                    log.debug("_ClickHandler.refreshClicked_ error", exc_info=True)

            def dashboardClicked_(self, sender):
                try:
                    cb = getattr(type(self), '_dashboard_fn', None)
                    if callable(cb):
                        cb()
                except Exception:
                    log.debug("_ClickHandler.dashboardClicked_ error", exc_info=True)

            def gearClicked_(self, sender):
                try:
                    get_menu = getattr(type(self), '_gear_menu_fn', None)
                    menu = get_menu() if callable(get_menu) else None
                    if menu:
                        from AppKit import NSMenu, NSApplication
                        NSMenu.popUpContextMenu_withEvent_forView_(
                            menu,
                            NSApplication.sharedApplication().currentEvent(),
                            sender,
                        )
                    else:
                        subprocess.Popen(["open", "https://claude.ai/settings/usage"])
                except Exception:
                    log.debug("_ClickHandler.gearClicked_ error", exc_info=True)

            def shareClicked_(self, sender):
                try:
                    cb = getattr(type(self), '_share_fn', None)
                    if callable(cb):
                        cb(sender)
                except Exception:
                    pass

            def copyImage_(self, sender):
                try:
                    cb = getattr(type(self), '_copy_image_fn', None)
                    if callable(cb):
                        cb()
                except Exception:
                    log.debug("_ClickHandler.copyImage_ error", exc_info=True)

            def shareOnX_(self, sender):
                try:
                    cb = getattr(type(self), '_share_on_x_fn', None)
                    if callable(cb):
                        cb()
                except Exception:
                    log.debug("_ClickHandler.shareOnX_ error", exc_info=True)

        _DismissablePanelClass = _DismissablePanel
        _ClickHandlerClass = _ClickHandler
        _panel_classes_ready = True
    except Exception:
        log.debug("_ensure_panel_classes failed", exc_info=True)


class _SharePopover:
    """Two-option share menu: Copy Image or Share on X."""

    def __init__(self, app: "TokenCoachApp"):
        self.app = app

    def show(self, sender):
        """Show a context menu with share options near the share button."""
        try:
            from AppKit import NSMenu, NSMenuItem, NSFont, NSApplication

            menu = NSMenu.alloc().init()
            menu.setAutoenablesItems_(False)

            # -- Copy Image --
            item1 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "  Copy Image", b"copyImage:", ""
            )
            item1.setEnabled_(True)
            handler = self.app._panel._handler
            if handler:
                item1.setTarget_(handler)
            menu.addItem_(item1)

            # -- Share on X --
            item2 = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "  Share on X", b"shareOnX:", ""
            )
            item2.setEnabled_(True)
            if handler:
                item2.setTarget_(handler)
            menu.addItem_(item2)

            # Pop up at mouse location
            evt = NSApplication.sharedApplication().currentEvent()
            panel_obj = self.app._panel._panel
            if evt and panel_obj:
                NSMenu.popUpContextMenu_withEvent_forView_(
                    menu, evt, panel_obj.contentView()
                )
            else:
                # Fallback: pop up at status item button
                btn = self.app._nsapp.nsstatusitem.button()
                if btn:
                    menu.popUpMenuPositioningItem_atLocation_inView_(
                        None, (0, 0), btn
                    )
        except Exception:
            log.debug("_SharePopover.show failed", exc_info=True)

    def copy_image(self):
        """Render the panel as PNG with watermark and copy to clipboard."""
        try:
            from AppKit import (
                NSBitmapImageRep, NSPasteboard, NSImage,
                NSGraphicsContext, NSColor, NSFont, NSBezierPath,
            )
            from Foundation import (
                NSMakeRect, NSMakeSize, NSAttributedString,
                NSFontAttributeName, NSForegroundColorAttributeName,
            )

            panel = self.app._panel
            if not panel or not panel._panel:
                return

            view = panel._panel.contentView()
            bounds = view.bounds()

            # Create bitmap from current view
            view.lockFocus()
            rep = NSBitmapImageRep.alloc().initWithFocusedViewRect_(bounds)
            view.unlockFocus()

            if not rep:
                return

            # Build composite image: panel content + watermark bar at bottom
            w = int(bounds.size.width)
            h = int(bounds.size.height)
            watermark_h = 24
            total_h = h + watermark_h

            img = NSImage.alloc().initWithSize_(NSMakeSize(w, total_h))
            img.lockFocus()

            # Draw panel content (shifted up by watermark height)
            rep.drawInRect_(NSMakeRect(0, watermark_h, w, h))

            # Draw watermark bar at the bottom
            NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.1, 0.1, 0.12, 1.0
            ).set()
            NSBezierPath.fillRect_(NSMakeRect(0, 0, w, watermark_h))

            attrs = {
                NSFontAttributeName: NSFont.systemFontOfSize_weight_(9, 0.3),
                NSForegroundColorAttributeName: NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.5, 0.5, 0.55, 1.0
                ),
            }
            text = NSAttributedString.alloc().initWithString_attributes_(
                f"{APP_NAME}  \u00b7  {REPO_URL.removeprefix('https://')}", attrs
            )
            text.drawAtPoint_((8, 6))

            # Capture the composite
            final_rep = NSBitmapImageRep.alloc().initWithFocusedViewRect_(
                NSMakeRect(0, 0, w, total_h)
            )
            img.unlockFocus()

            if not final_rep:
                return

            # Copy PNG to clipboard  (4 = NSBitmapImageFileTypePNG)
            png_data = final_rep.representationUsingType_properties_(4, {})
            if not png_data:
                return

            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setData_forType_(png_data, "public.png")

            log.info("Panel screenshot copied to clipboard")
            _notify(APP_NAME, "Copied!", "Panel screenshot copied to clipboard")
        except Exception:
            log.debug("_SharePopover.copy_image failed", exc_info=True)

    def share_on_x(self):
        """Open X/Twitter with pre-filled usage stats."""
        try:
            parts = []
            data = self.app._last_data
            if data and data.session:
                parts.append(f"Claude {_remaining(data.session.pct)}% left")
            for pd in self.app._provider_data:
                best = self.app._provider_bar_pct(pd)
                if best is not None:
                    parts.append(f"{pd.name} {_remaining(best)}% left")

            stats = " \u00b7 ".join(parts) if parts else "my AI usage"
            text = f"{stats} \u2014 tracking with {APP_NAME}"
            url = (
                "https://x.com/intent/post?text="
                + urllib.parse.quote(text)
                + "&url="
                + urllib.parse.quote(REPO_URL)
            )
            subprocess.Popen(["open", url])
        except Exception:
            log.debug("_SharePopover.share_on_x failed", exc_info=True)


class _UsagePanel:
    """Premium floating panel that replaces the default NSMenu dropdown."""

    PANEL_WIDTH = 340
    MAX_HEIGHT = 600
    PAD = 16
    PROGRESS_H = 6
    PROGRESS_RADIUS = 3
    DOT_SIZE = 8
    SECTION_GAP = 12
    ROW_GAP = 4

    def __init__(self, app: "TokenCoachApp"):
        self._app = app
        self._panel = None           # NSPanel instance
        self._visible = False
        self._content_view = None    # The NSView inside the scroll view's document
        self._handler = None         # ObjC click handler instance
        self._scroll = None
        self._built = False

    # -- public API -----------------------------------------------------------

    @property
    def visible(self) -> bool:
        return self._visible

    def toggle(self):
        """Show or dismiss the panel."""
        if self._visible:
            self.dismiss()
        else:
            self.show()

    def show(self):
        """Build/refresh the panel and show it below the status item."""
        try:
            self._ensure_built()
            self.refresh()
            self._position_panel()
            # Fade-in animation
            self._panel.setAlphaValue_(0.0)
            self._panel.makeKeyAndOrderFront_(None)
            from AppKit import NSApplication, NSAnimationContext
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            ctx = NSAnimationContext.currentContext()
            ctx.setDuration_(0.12)
            self._panel.animator().setAlphaValue_(1.0)
            self._visible = True
        except Exception:
            log.debug("_UsagePanel.show failed", exc_info=True)

    def dismiss(self):
        """Hide the panel with a quick fade-out."""
        try:
            if self._panel:
                from AppKit import NSAnimationContext
                ctx = NSAnimationContext.currentContext()
                ctx.setDuration_(0.08)
                self._panel.animator().setAlphaValue_(0.0)
                # Schedule orderOut after animation
                from Foundation import NSTimer
                def _hide(_timer):
                    try:
                        self._panel.orderOut_(None)
                        self._panel.setAlphaValue_(1.0)
                    except Exception:
                        pass
                NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.1, False, _hide)
        except Exception:
            if self._panel:
                self._panel.orderOut_(None)
        self._visible = False

    def refresh(self):
        """Rebuild the panel content with current data."""
        try:
            if not self._built:
                return
            self._rebuild_content()
        except Exception:
            log.debug("_UsagePanel.refresh failed", exc_info=True)

    # -- construction ---------------------------------------------------------

    def _ensure_built(self):
        """Lazily create the NSPanel and its chrome (vibrancy, scroll, etc.)."""
        if self._built:
            return
        _ensure_panel_classes()
        if _DismissablePanelClass is None:
            log.warning("Panel ObjC classes not available")
            return

        from AppKit import (
            NSVisualEffectView, NSScrollView, NSView,
            NSBackingStoreBuffered, NSApplication,
        )
        from Foundation import NSMakeRect

        # Panel: borderless, non-activating
        # styleMask: 0 = borderless
        panel = _DismissablePanelClass.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, self.PANEL_WIDTH, 200),
            0,  # borderless
            NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(3)         # NSFloatingWindowLevel
        panel.setHasShadow_(True)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(self._clear_color())
        panel.setMovableByWindowBackground_(False)
        panel.setWorksWhenModal_(True)
        panel.setHidesOnDeactivate_(False)
        panel._dismiss_callback = self.dismiss

        content = panel.contentView()
        content.setWantsLayer_(True)
        content.layer().setCornerRadius_(12)
        content.layer().setMasksToBounds_(True)

        # Vibrancy background
        blur = NSVisualEffectView.alloc().initWithFrame_(content.bounds())
        blur.setAutoresizingMask_(18)  # width + height
        blur.setBlendingMode_(0)       # behindWindow
        blur.setMaterial_(3)           # dark
        blur.setState_(1)              # active
        content.addSubview_(blur)

        # Scroll view fills the panel
        scroll = NSScrollView.alloc().initWithFrame_(content.bounds())
        scroll.setAutoresizingMask_(18)
        scroll.setHasVerticalScroller_(True)
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(0)
        content.addSubview_(scroll)

        doc = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, self.PANEL_WIDTH, 200))
        scroll.setDocumentView_(doc)

        self._panel = panel
        self._scroll = scroll
        self._content_view = doc
        self._blur = blur

        # ObjC handler
        if _ClickHandlerClass is not None:
            self._handler = _ClickHandlerClass.alloc().init()

        self._built = True

    def _clear_color(self):
        from AppKit import NSColor
        return NSColor.clearColor()

    # -- positioning ----------------------------------------------------------

    def _position_panel(self):
        """Place the panel below the status bar button, centered."""
        try:
            btn = self._app._nsapp.nsstatusitem.button()
            if not btn:
                return
            btn_win = btn.window()
            if not btn_win:
                return
            # Get button frame in screen coordinates
            btn_frame = btn.frame()
            screen_rect = btn_win.convertRectToScreen_(btn_frame)

            # Panel top-center aligns with button bottom-center
            panel_x = screen_rect.origin.x + screen_rect.size.width / 2 - self.PANEL_WIDTH / 2
            panel_y = screen_rect.origin.y - self._panel.frame().size.height - 4

            # Clamp to screen
            from AppKit import NSScreen
            screen = NSScreen.mainScreen()
            if screen:
                sf = screen.visibleFrame()
                panel_x = max(sf.origin.x + 4, min(panel_x, sf.origin.x + sf.size.width - self.PANEL_WIDTH - 4))
                panel_y = max(sf.origin.y + 4, panel_y)

            from Foundation import NSMakeRect
            new_frame = NSMakeRect(
                panel_x, panel_y,
                self.PANEL_WIDTH,
                self._panel.frame().size.height,
            )
            self._panel.setFrame_display_(new_frame, True)
        except Exception:
            log.debug("_position_panel failed", exc_info=True)

    # -- content rebuild ------------------------------------------------------

    def _rebuild_content(self):
        """Tear down and rebuild all subviews in the document view."""
        from AppKit import (
            NSView, NSTextField, NSFont, NSColor, NSButton,
            NSTextAlignmentLeft, NSTextAlignmentRight,
        )
        from Foundation import NSMakeRect
        import Quartz

        doc = self._content_view
        # Remove all existing subviews
        for sv in list(doc.subviews()):
            sv.removeFromSuperview()

        W = self.PANEL_WIDTH
        PAD = self.PAD
        inner = W - PAD * 2

        # We build top-down, tracking y offset from top.
        # At the end we set the doc height and convert to bottom-up coords.
        elements = []  # list of (top_y, builder_fn) -- deferred so we know total height

        # We'll accumulate content height
        y = PAD  # start below top edge

        # ── Header ──────────────────────────────────────────────────────
        header_h = 24
        elements.append(('header', y, header_h))
        y += header_h + 8

        # ── Separator ───────────────────────────────────────────────────
        elements.append(('sep', y, 1))
        y += 1 + self.SECTION_GAP

        # ── Provider sections ───────────────────────────────────────────
        data = self._app._last_data
        provider_data = self._app._provider_data
        history = self._app._history
        history_db = self._app._history_db

        has_any_data = False

        # Claude section
        if data and any([data.session, data.weekly_all, data.weekly_sonnet]):
            has_any_data = True
            # Each limit row carries its own reset time, so the provider
            # header remains a clean identifier rather than privileging 5-hour.
            elements.append(('provider_header', y, 18, 'Claude', '#D97757', ''))
            y += 18 + 6

            # Rows
            for row in [data.session, data.weekly_all, data.weekly_sonnet]:
                if row:
                    elements.append(('limit_row', y, 20, row, '#D97757'))
                    y += 20 + self.ROW_GAP

            # ETA
            eta = _calc_eta_minutes(history, "claude")
            if eta is not None:
                elements.append(('eta_line', y, 14, eta))
                y += 14 + 2

            # Sparkline
            spark = _sparkline(history, "claude")
            if spark:
                elements.append(('spark_line', y, 14, spark))
                y += 14 + 2

            y += self.SECTION_GAP

        # ChatGPT section
        chatgpt_pd = next((pd for pd in provider_data if pd.name == "ChatGPT"), None)
        if chatgpt_pd and not chatgpt_pd.error:
            has_any_data = True
            rows = getattr(chatgpt_pd, "_rows", None) or []
            elements.append(('provider_header', y, 18, 'ChatGPT', '#74AA9C', ''))
            y += 18 + 6
            for row in rows:
                elements.append(('limit_row', y, 20, row, '#74AA9C'))
                y += 20 + self.ROW_GAP
                hkey = f"chatgpt_{row.label.lower().replace(' ', '_')}"
                eta = _calc_eta_minutes(history, hkey)
                if eta is not None:
                    elements.append(('eta_line', y, 14, eta))
                    y += 14 + 2
            y += self.SECTION_GAP

        # No data placeholder
        if not has_any_data:
            elements.append(('placeholder', y, 40))
            y += 40 + self.SECTION_GAP

        # Spend today (usage ledger)
        summary = getattr(self._app, "_ledger_summary", None)
        if summary is not None:
            elements.append(('provider_header', y, 18, 'Spend today', '#8E8E93',
                             f"{_ledger.fmt_usd(summary['cost'])} API-equiv."))
            y += 18 + 6
            for line in _ledger_menu_lines(summary, getattr(self._app, "_ledger_status", ""))[1:]:
                elements.append(('text_line', y, 14, line.strip()))
                y += 14 + 2
            elements.append(('dashboard_btn', y, 22))
            y += 22 + 2
            y += self.SECTION_GAP

        # ── Footer separator ────────────────────────────────────────────
        elements.append(('sep', y, 1))
        y += 1 + 8

        # ── Footer ──────────────────────────────────────────────────────
        footer_h = 20
        elements.append(('footer', y, footer_h))
        y += footer_h + PAD

        # ── Set document height and panel height ────────────────────────
        total_h = min(y, self.MAX_HEIGHT)
        doc_h = y  # full content height (may exceed panel if scrollable)

        doc.setFrame_(NSMakeRect(0, 0, W, doc_h))

        # Resize panel
        self._panel.setContentSize_((W, total_h))

        # Now render all elements (converting top_y to bottom-up NSView coords)
        for elem in elements:
            kind = elem[0]
            top_y = elem[1]
            h = elem[2]
            real_y = doc_h - top_y - h

            if kind == 'header':
                self._render_header(doc, PAD, real_y, inner, h, NSTextField, NSFont,
                                    NSColor, NSButton, NSMakeRect, NSTextAlignmentLeft)

            elif kind == 'sep':
                sep = NSView.alloc().initWithFrame_(NSMakeRect(PAD, real_y, inner, 1))
                sep.setWantsLayer_(True)
                sep.layer().setBackgroundColor_(
                    Quartz.CGColorCreateGenericRGB(1, 1, 1, 0.08)
                )
                doc.addSubview_(sep)

            elif kind == 'provider_header':
                _, _, _, name, color_hex, right_text = elem
                self._render_provider_header(
                    doc, PAD, real_y, inner, h, name, color_hex, right_text,
                    NSView, NSTextField, NSFont, NSColor, NSMakeRect,
                    NSTextAlignmentLeft, NSTextAlignmentRight, Quartz,
                )

            elif kind == 'limit_row':
                _, _, _, row, color_hex = elem
                self._render_limit_row(
                    doc, PAD, real_y, inner, h, row, color_hex,
                    NSView, NSTextField, NSFont, NSColor, NSMakeRect,
                    NSTextAlignmentLeft, NSTextAlignmentRight, Quartz,
                )

            elif kind == 'eta_line':
                _, _, _, eta_min = elem
                self._render_small_text(
                    doc, PAD, real_y, inner, h,
                    f"\u23f1 At this pace: limit in ~{_fmt_eta(eta_min)}",
                    NSTextField, NSFont, NSColor, NSMakeRect,
                )

            elif kind == 'spark_line':
                _, _, _, spark_str = elem
                self._render_small_text(
                    doc, PAD, real_y, inner, h,
                    spark_str,
                    NSTextField, NSFont, NSColor, NSMakeRect,
                )

            elif kind == 'dashboard_btn':
                btn = NSButton.alloc().initWithFrame_(NSMakeRect(PAD - 6, real_y, 170, h))
                btn.setTitle_("Open dashboard \u2197")
                btn.setBordered_(False)
                btn.setAlignment_(NSTextAlignmentLeft)
                btn.setFont_(NSFont.systemFontOfSize_weight_(12, 0.3))
                try:
                    btn.setContentTintColor_(NSColor.linkColor())
                except Exception:
                    pass
                if self._handler:
                    btn.setTarget_(self._handler)
                    btn.setAction_(b"dashboardClicked:")
                doc.addSubview_(btn)

            elif kind == 'text_line':
                _, _, _, text = elem
                self._render_small_text(
                    doc, PAD, real_y, inner, h, text,
                    NSTextField, NSFont, NSColor, NSMakeRect,
                )

            elif kind == 'placeholder':
                self._render_small_text(
                    doc, PAD, real_y, inner, h,
                    "Waiting for data...",
                    NSTextField, NSFont, NSColor, NSMakeRect,
                    size=13, weight=0.3,
                )

            elif kind == 'footer':
                self._render_footer(doc, PAD, real_y, inner, h,
                                    NSTextField, NSFont, NSColor, NSButton,
                                    NSMakeRect, NSTextAlignmentLeft, NSTextAlignmentRight)

        # Scroll to top
        try:
            visible_h = self._scroll.contentSize().height
            if doc_h > visible_h:
                clip = self._scroll.contentView()
                clip.scrollToPoint_((0, doc_h - visible_h))
                self._scroll.reflectScrolledClipView_(clip)
        except Exception:
            pass

    # -- render helpers -------------------------------------------------------

    def _render_header(self, parent, x, y, w, h, NSTextField, NSFont,
                       NSColor, NSButton, NSMakeRect, NSTextAlignmentLeft):
        """Render: 'TokenCoach' title + gear + share buttons."""
        # Title
        title = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w - 60, h))
        title.setStringValue_(APP_NAME)
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setEditable_(False)
        title.setSelectable_(False)
        title.setAlignment_(NSTextAlignmentLeft)
        title.setFont_(NSFont.systemFontOfSize_weight_(15, 0.56))
        title.setTextColor_(NSColor.labelColor())
        parent.addSubview_(title)

        # Share button
        share_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x + w - 52, y, 24, h))
        share_btn.setTitle_("\u2197")
        share_btn.setBordered_(False)
        share_btn.setFont_(NSFont.systemFontOfSize_(14))
        if self._handler:
            share_btn.setTarget_(self._handler)
            share_btn.setAction_(b"shareClicked:")
        parent.addSubview_(share_btn)

        # Gear button
        gear_btn = NSButton.alloc().initWithFrame_(NSMakeRect(x + w - 26, y, 24, h))
        gear_btn.setTitle_("\u2699")
        gear_btn.setBordered_(False)
        gear_btn.setFont_(NSFont.systemFontOfSize_(14))
        if self._handler:
            gear_btn.setTarget_(self._handler)
            gear_btn.setAction_(b"gearClicked:")
        parent.addSubview_(gear_btn)

    def _render_provider_header(self, parent, x, y, w, h, name, color_hex,
                                right_text, NSView, NSTextField, NSFont,
                                NSColor, NSMakeRect, NSTextAlignmentLeft,
                                NSTextAlignmentRight, Quartz):
        """Render: colored dot + bold provider name + right-aligned reset text."""
        # Colored dot
        dot_y = y + (h - self.DOT_SIZE) / 2
        dot = NSView.alloc().initWithFrame_(NSMakeRect(x, dot_y, self.DOT_SIZE, self.DOT_SIZE))
        dot.setWantsLayer_(True)
        hx = color_hex.lstrip("#")
        r, g, b = int(hx[0:2], 16) / 255, int(hx[2:4], 16) / 255, int(hx[4:6], 16) / 255
        dot.layer().setBackgroundColor_(Quartz.CGColorCreateGenericRGB(r, g, b, 1.0))
        dot.layer().setCornerRadius_(self.DOT_SIZE / 2)
        dot.layer().setMasksToBounds_(True)
        parent.addSubview_(dot)

        # Provider name (bold)
        name_x = x + self.DOT_SIZE + 6
        name_w = w - self.DOT_SIZE - 6 - 120
        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(name_x, y, name_w, h))
        lbl.setStringValue_(name)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setAlignment_(NSTextAlignmentLeft)
        lbl.setFont_(NSFont.systemFontOfSize_weight_(13, 0.5))
        lbl.setTextColor_(NSColor.labelColor())
        parent.addSubview_(lbl)

        # Right text (reset time or count)
        if right_text:
            rt = NSTextField.alloc().initWithFrame_(NSMakeRect(x + w - 140, y, 140, h))
            rt.setStringValue_(right_text)
            rt.setBezeled_(False)
            rt.setDrawsBackground_(False)
            rt.setEditable_(False)
            rt.setSelectable_(False)
            rt.setAlignment_(NSTextAlignmentRight)
            rt.setFont_(NSFont.systemFontOfSize_(11))
            rt.setTextColor_(NSColor.secondaryLabelColor())
            parent.addSubview_(rt)

    def _render_limit_row(self, parent, x, y, w, h, row, color_hex,
                          NSView, NSTextField, NSFont, NSColor, NSMakeRect,
                          NSTextAlignmentLeft, NSTextAlignmentRight, Quartz):
        """Render: compact window/reset label + progress bar + percentage."""
        label_w = 112
        pct_w = 40
        bar_x = x + label_w + 4
        bar_w = w - label_w - pct_w - 8
        bar_y = y + (h - self.PROGRESS_H) / 2

        # One line keeps the panel compact while preserving which window resets.
        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, label_w, h))
        lbl.setStringValue_(_panel_limit_label(row))
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setAlignment_(NSTextAlignmentLeft)
        lbl.setFont_(NSFont.systemFontOfSize_(10))
        lbl.setTextColor_(NSColor.secondaryLabelColor())
        parent.addSubview_(lbl)

        # Track (background)
        track = NSView.alloc().initWithFrame_(NSMakeRect(bar_x, bar_y, bar_w, self.PROGRESS_H))
        track.setWantsLayer_(True)
        track.layer().setBackgroundColor_(
            Quartz.CGColorCreateGenericRGB(0.15, 0.15, 0.2, 1.0)
        )
        track.layer().setCornerRadius_(self.PROGRESS_RADIUS)
        track.layer().setMasksToBounds_(True)
        parent.addSubview_(track)

        # Fill: the bar shows what remains, so it drains as quota is consumed.
        left = _remaining(row.pct)
        fill_w = max(0, bar_w * left / 100)
        if fill_w > 0:
            fill = NSView.alloc().initWithFrame_(NSMakeRect(bar_x, bar_y, fill_w, self.PROGRESS_H))
            fill.setWantsLayer_(True)
            hx = color_hex.lstrip("#")
            r, g, b = int(hx[0:2], 16) / 255, int(hx[2:4], 16) / 255, int(hx[4:6], 16) / 255
            fill.layer().setBackgroundColor_(Quartz.CGColorCreateGenericRGB(r, g, b, 1.0))
            fill.layer().setCornerRadius_(self.PROGRESS_RADIUS)
            fill.layer().setMasksToBounds_(True)
            parent.addSubview_(fill)

        # Percentage text
        pct_lbl = NSTextField.alloc().initWithFrame_(
            NSMakeRect(x + w - pct_w, y, pct_w, h)
        )
        pct_lbl.setStringValue_(f"{left}%")
        pct_lbl.setBezeled_(False)
        pct_lbl.setDrawsBackground_(False)
        pct_lbl.setEditable_(False)
        pct_lbl.setSelectable_(False)
        pct_lbl.setAlignment_(NSTextAlignmentRight)
        pct_lbl.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(11, 0.3))
        pct_lbl.setTextColor_(NSColor.labelColor())
        parent.addSubview_(pct_lbl)

    def _render_small_text(self, parent, x, y, w, h, text,
                           NSTextField, NSFont, NSColor, NSMakeRect,
                           size=10, weight=0.0):
        """Render a small secondary-colored text line."""
        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        lbl.setStringValue_(text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setFont_(NSFont.systemFontOfSize_weight_(size, weight))
        lbl.setTextColor_(NSColor.secondaryLabelColor())
        parent.addSubview_(lbl)

    def _render_footer(self, parent, x, y, w, h,
                       NSTextField, NSFont, NSColor, NSButton,
                       NSMakeRect, NSTextAlignmentLeft, NSTextAlignmentRight):
        """Render: 'Updated HH:MM' left + 'Refresh' button right."""
        updated = self._app._last_updated
        if updated:
            ts = updated.strftime("%H:%M")
        else:
            ts = "--:--"
        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w - 80, h))
        lbl.setStringValue_(f"Updated {ts}")
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setAlignment_(NSTextAlignmentLeft)
        lbl.setFont_(NSFont.systemFontOfSize_(10))
        lbl.setTextColor_(NSColor.tertiaryLabelColor())
        parent.addSubview_(lbl)

        # Refresh button
        btn = NSButton.alloc().initWithFrame_(NSMakeRect(x + w - 70, y, 70, h))
        btn.setTitle_("\u21bb Refresh")
        btn.setBordered_(False)
        btn.setFont_(NSFont.systemFontOfSize_(10))
        if self._handler:
            btn.setTarget_(self._handler)
            btn.setAction_(b"refreshClicked:")
        parent.addSubview_(btn)


# -- app -----------------------------------------------------------------------

class TokenCoachApp(rumps.App):
    def __init__(self):
        # Menu bar only: hide the Dock icon and Cmd-Tab entry. Must happen
        # before the AppKit run loop starts (i.e. before .run()), otherwise
        # the icon flashes into the Dock and back out.
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        super().__init__("\u25c6", quit_button=None)
        self.config = load_config()
        legacy_config_changed = self.config.pop("copilot_cookies", None) is not None
        legacy_config_changed |= self.config.pop("cursor_cookies", None) is not None
        notifications = self.config.get("notifications")
        if isinstance(notifications, dict):
            legacy_config_changed |= notifications.pop("copilot_pacing", None) is not None
            legacy_config_changed |= notifications.pop("cursor_warning", None) is not None
            legacy_config_changed |= notifications.pop("cursor_pacing", None) is not None
        chosen_bar = self.config.get("bar_providers")
        if isinstance(chosen_bar, list) and any(name in ("Copilot", "Cursor") for name in chosen_bar):
            cleaned_bar = [name for name in chosen_bar if name not in ("Copilot", "Cursor")]
            if cleaned_bar:
                self.config["bar_providers"] = cleaned_bar
            else:
                self.config.pop("bar_providers", None)
            legacy_config_changed = True
        if legacy_config_changed:
            save_config(self.config)
        self._last_raw: dict = {}
        self._last_data: UsageData | None = None
        self._provider_data: list[ProviderData] = []
        self._warned_pcts: set[str] = set()   # track which rows we've notified
        self._prev_pcts: dict[str, int] = {}  # previous pct per row key (reset detection)
        self._auth_fail_count = 0
        self._chatgpt_cookie_retry_after = 0.0
        # Providers whose cookies were looked for unasked this run. Reading
        # Chromium cookies needs the browser's Keychain key, so with nothing
        # saved we look once, not on every refresh; the menu's detect items
        # and repeated auth failures still look again.
        self._auto_detected: set[str] = set()
        self._fetching = False
        self._last_updated: datetime | None = None

        self._refresh_interval = self.config.get("refresh_interval", DEFAULT_REFRESH)
        self._cc_stats: dict | None = None   # Claude Code local stats
        self._history = _load_history()       # usage history for burn rate / sparkline
        self._pacing_alerted: set[str] = set()  # track which providers we've pacing-alerted
        self._history_db = _init_history_db()
        self._last_rollup = 0
        try:
            _rollup_daily_stats(self._history_db)
            self._last_rollup = time.time()
        except Exception:
            log.exception("startup rollup failed")

        # Thread-safe UI update queue (background thread -> main thread)
        self._ui_pending_title: str | None = None
        self._ui_pending_data: UsageData | None = None
        self._ui_lock = threading.Lock()
        self._config_lock = threading.Lock()
        self._db_lock = threading.Lock()
        self._login_item_cached: bool | None = None
        self._last_update_check = self.config.get("last_update_check", 0)

        # Usage ledger (per-prompt tokens/cost from local agent logs)
        self._ledger_conn = None
        self._ledger_lock = threading.Lock()
        self._ledger_busy = False
        self._ledger_summary: dict | None = None
        self._ledger_status = ""
        self._optimizer_running = False
        self._last_lesson_scan = 0.0
        try:
            os.remove(QUIT_MARKER)        # started again, so the watchdog may supervise it
        except FileNotFoundError:
            pass
        except OSError:
            log.debug("could not remove quit marker", exc_info=True)
        # Before the dashboard starts: a copy that hands over to launchd must not
        # hold the dashboard port while the supervised copy binds it.
        from tokencoach.legacy import finish_legacy_install
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not finish_legacy_install(root):
            if not _login_item_current() and _add_login_item(handoff=True):
                log.info("login agent written; handing over to the copy launchd started")
                os._exit(0)
            if _job_pid() == os.getpid():
                for pid in _stop_other_copies():
                    log.info("stopped another copy of this install (pid %d)", pid)

        self._dashboard = None
        try:
            from tokencoach.server import DashboardServer, get_token
            with self._config_lock:
                token = get_token(self.config)
            self._dashboard = DashboardServer(token, app=self).start()
        except Exception:
            log.exception("dashboard listener failed to start; buttons will be read-only")
        self._sync_nudges()

        # Floating panel (premium UI that replaces NSMenu)
        self._panel = _UsagePanel(self)
        self._share_popover = _SharePopover(self)
        self._click_handler_inst = None   # set in _deferred_welcome

        self._rebuild_menu(None)
        self._timer = rumps.Timer(self._on_timer, self._refresh_interval)
        self._timer.start()
        # Fast ticker: drains pending UI updates on the main thread (avoids AppKit crashes)
        self._ui_ticker = rumps.Timer(self._flush_ui, 0.25)
        self._ui_ticker.start()

        # Deferred startup info (runs after the run loop is active)
        self._welcome_timer = rumps.Timer(self._deferred_welcome, 2)
        self._welcome_timer.start()

        # Always try to fetch on startup -- browser JS works even without saved cookies
        atexit.register(self._shutdown)
        self._schedule_fetch()
        self._schedule_ledger()

    def _shutdown(self):
        """Clean up resources on exit."""
        try:
            self._history_db.close()
        except Exception:
            pass

    def _is_login_item_cached(self) -> bool:
        if self._login_item_cached is None:
            self._login_item_cached = _is_login_item()
        return self._login_item_cached

    # -- menu -----------------------------------------------------------------

    def _rebuild_menu(self, data: UsageData | None):
        items: list = []

        # -- health: one line on top when the quota needs attention -----------
        q = getattr(self, "_quota_health", None)
        line = health.menu_line(q) if q else None
        if line:
            head, _, detail = line.partition(". ")
            items.append(_colored_mi(f"  {head}", _HEALTH_HEX[q["state"]]))
            if detail:
                items.append(_mi(f"  {detail}"))
            items.append(None)

        # -- CLAUDE section ---------------------------------------------------
        items.append(_section_header_mi("  Claude", "claude_icon.png", "#D97757"))

        if data is None or not any([data.session, data.weekly_all, data.weekly_sonnet]):
            items.append(_mi("  No data \u2014 click Auto-detect from Browser"))
        else:
            if data.session:
                lines = _row_lines(data.session)
                items.append(_mi(lines[0]))
                items.append(_colored_mi(lines[1], "#D97757"))
                # ETA + sparkline for Claude session
                eta = _calc_eta_minutes(self._history, "claude")
                if eta is not None:
                    items.append(_mi(f"  \u23f1 At this pace: limit in ~{_fmt_eta(eta)}"))
                spark = _sparkline(self._history, "claude")
                if spark:
                    items.append(_mi(f"  {spark}"))
                    items.append(_mi(f"  \U0001f4c8 24h usage trend"))
                items.append(None)

            for row in [data.weekly_all, data.weekly_sonnet]:
                if row:
                    lines = _row_lines(row)
                    items.append(_mi(lines[0]))
                    items.append(_colored_mi(lines[1], "#D97757"))
                    items.append(None)


        # -- CHATGPT section (if detected) ------------------------------------
        chatgpt_pd = next(
            (pd for pd in self._provider_data if pd.name == "ChatGPT"), None
        )
        if chatgpt_pd:
            items.append(_section_header_mi("  ChatGPT", "chatgpt_icon_clean.png",
                                            "#74AA9C", icon_tint="#74AA9C"))
            rows = getattr(chatgpt_pd, "_rows", None)
            if rows:
                for row in rows:
                    lines = _row_lines(row)
                    items.append(_mi(lines[0]))
                    items.append(_colored_mi(lines[1], "#74AA9C"))
                    hkey = f"chatgpt_{row.label.lower().replace(' ', '_')}"
                    eta = _calc_eta_minutes(self._history, hkey)
                    if eta is not None:
                        items.append(_mi(f"  \u23f1 At this pace: limit in ~{_fmt_eta(eta)}"))
                    spark = _sparkline(self._history, hkey)
                    if spark:
                        items.append(_mi(f"  {spark}"))
                        items.append(_mi(f"  \U0001f4c8 24h usage trend"))
                    items.append(None)
            else:
                for line in _provider_lines(chatgpt_pd):
                    if line:
                        items.append(_mi(line))
                items.append(None)

        # -- CLAUDE CODE section ----------------------------------------------
        if self._cc_stats:
            cc = self._cc_stats
            items.append(_section_header_mi("  Claude Code", "claude_icon.png", "#D97757"))
            if cc["today_messages"] > 0:
                items.append(_mi(
                    f"  Today     {_fmt_count(cc['today_messages'])} msgs"
                    f"  \u00b7  {cc['today_sessions']} sessions"
                ))
            wm = cc["week_messages"]
            if wm > 0:
                items.append(_mi(
                    f"  This week  {_fmt_count(wm)} msgs"
                    f"  \u00b7  {cc['week_sessions']} sessions"
                    f"  \u00b7  {_fmt_count(cc['week_tool_calls'])} tools"
                ))
            if cc.get("last_date"):
                items.append(_mi(f"  Last active  {cc['last_date']}"))
            items.append(None)

        # -- Spend (usage ledger) ---------------------------------------------
        items.append(_mi(f"  {APP_NAME} \u00b7 spend (API-equivalent)"))
        for line in _ledger_menu_lines(self._ledger_summary, self._ledger_status):
            items.append(_mi(line))
        items.append(rumps.MenuItem("Open Dashboard \u2197", callback=self._open_dashboard))
        items.append(rumps.MenuItem(
            "Analyzing\u2026" if self._optimizer_running else "Analyze My Usage\u2026",
            callback=None if self._optimizer_running else self._analyze_usage,
        ))
        items.append(rumps.MenuItem("Import Chat Export\u2026", callback=self._import_chat_export))
        items.append(rumps.MenuItem("Set Plan Prices\u2026", callback=self._set_plan_prices))
        try:
            from tokencoach.nudge import is_installed as _nudges_on
            nudge_item = rumps.MenuItem("Nudges in Claude Code", callback=self._toggle_nudges)
            nudge_item._menuitem.setState_(1 if _nudges_on() else 0)
            items.append(nudge_item)
        except Exception:
            log.debug("nudge menu item failed", exc_info=True)
        items.append(None)

        # -- Other API providers ----------------------------------------------
        for pd in self._provider_data:
            if pd.name == "ChatGPT":
                continue
            items.append(_mi(f"  {pd.name}"))
            items.append(None)
            for line in _provider_lines(pd):
                if line:
                    items.append(_mi(line))
            items.append(None)

        # -- Usage History window ---------------------------------------------
        try:
            today_stats = _get_today_stats(self._history_db)
            past_keys = {r[0] for r in self._history_db.execute(
                "SELECT DISTINCT key FROM daily_stats"
            ).fetchall()}
            has_history = bool(past_keys or today_stats)
            if has_history:
                items.append(rumps.MenuItem(
                    "Usage History\u2026", callback=self._open_history_window,
                ))
                items.append(None)
        except Exception:
            log.exception("Usage History menu item failed")

        # -- Footer -----------------------------------------------------------
        if self._last_updated:
            t = self._last_updated.strftime("%H:%M")
            items.append(_mi(f"  Updated {t}"))
            items.append(None)

        # -- Actions ----------------------------------------------------------
        items.append(rumps.MenuItem("Refresh Now", callback=self._do_refresh))
        items.append(rumps.MenuItem("Open claude.ai/settings/usage", callback=self._open_usage_page))
        items.append(rumps.MenuItem("Share on X / Twitter\u2026", callback=self._share_on_x))
        items.append(rumps.MenuItem("\u2b50 Star on GitHub", callback=self._open_github))
        items.append(None)

        # Status bar display submenu
        bar_menu = rumps.MenuItem("Status Bar")
        chosen = self.config.get("bar_providers") or []
        # In auto mode, compute which providers would be shown
        if not chosen:
            available_names = {"Claude"} if self._last_data else set()
            for pd in self._provider_data:
                if self._provider_bar_pct(pd) is not None:
                    available_names.add(pd.name)
            auto_shown = [n for n in self._BAR_PRIORITY if n in available_names][:2]
        else:
            auto_shown = []
        self._bar_toggle_views = {}
        for name in self._BAR_PRIORITY:
            is_on = name in chosen if chosen else name in auto_shown
            item = self._make_sticky_toggle(name, is_on, name)
            bar_menu.add(item)
        bar_menu.add(None)
        is_auto = not chosen
        auto_item = rumps.MenuItem(
            "\u2713 Auto (top 2 active)" if is_auto else "Reset to Auto",
            callback=self._bar_reset_auto,
        )
        bar_menu.add(auto_item)
        items.append(bar_menu)

        # Refresh interval submenu
        interval_menu = rumps.MenuItem("Refresh Interval")
        for label, secs in REFRESH_INTERVALS.items():
            item = rumps.MenuItem(label, callback=self._make_interval_cb(secs, label))
            item._menuitem.setState_(1 if secs == self._refresh_interval else 0)
            interval_menu.add(item)
        items.append(interval_menu)

        # Notifications submenu
        notif_menu = rumps.MenuItem("Notifications")
        _notif_labels = [
            ("claude_warning",  "Claude \u2014 usage warnings (80% / 95%)"),
            ("claude_reset",    "Claude \u2014 reset alerts"),
            ("claude_pacing",   "Claude \u2014 pacing alert (ETA < 30 min)"),
            ("chatgpt_warning", "ChatGPT \u2014 usage warnings (80% / 95%)"),
            ("chatgpt_reset",   "ChatGPT \u2014 reset alerts"),
            ("chatgpt_pacing",  "ChatGPT \u2014 pacing alert (ETA < 30 min)"),
        ]
        for nkey, nlabel in _notif_labels:
            item = rumps.MenuItem(nlabel, callback=self._make_notif_toggle_cb(nkey))
            item._menuitem.setState_(1 if notif_enabled(self.config, nkey) else 0)
            notif_menu.add(item)
        items.append(notif_menu)
        items.append(None)

        # API providers submenu
        providers_menu = rumps.MenuItem("API Providers")
        for cfg_key, (name, _) in PROVIDER_REGISTRY.items():
            is_set = bool(self.config.get(cfg_key))
            marker = "\u2713" if is_set else "+"
            if cfg_key in COOKIE_PROVIDERS:
                label = f"{marker} {name} (auto-detect)"
            else:
                label = f"{marker} {name} API Key\u2026"
            providers_menu.add(rumps.MenuItem(
                label, callback=self._make_provider_key_cb(cfg_key, name)
            ))
        items.append(providers_menu)

        items.append(None)
        items.append(rumps.MenuItem("Auto-detect from Browser", callback=self._auto_detect_menu))
        items.append(rumps.MenuItem("Set Session Cookie\u2026", callback=self._set_cookie))
        items.append(rumps.MenuItem("Paste Cookie from Clipboard", callback=self._paste_cookie))
        items.append(rumps.MenuItem("Show Raw API Data\u2026", callback=self._show_raw))
        items.append(None)

        login_item = rumps.MenuItem("Launch at Login", callback=self._toggle_login_item)
        login_item._menuitem.setState_(1 if self._is_login_item_cached() else 0)
        items.append(login_item)

        # Desktop Widget status
        if _is_widget_installed():
            widget_item = rumps.MenuItem(
                "Desktop Widget  \u2713  Installed",
                callback=self._open_widget_settings,
            )
        else:
            widget_item = rumps.MenuItem(
                "Desktop Widget  \u00b7  Not Installed",
                callback=self._install_widget_prompt,
            )
        items.append(widget_item)

        items.append(None)
        items.append(rumps.MenuItem(f"About {APP_NAME}", callback=self._about))
        items.append(rumps.MenuItem("Quit", callback=_quit_app))

        self.menu.clear()
        self.menu = items
        # Prevent macOS from auto-disabling display-only items
        try:
            ns_menu = self._nsapp.nsstatusitem.menu()
            if ns_menu:
                ns_menu.setAutoenablesItems_(False)
        except Exception:
            pass

    # -- thread-safe UI helpers -----------------------------------------------

    def _post_title(self, title: str):
        """Queue a title update from any thread."""
        with self._ui_lock:
            self._ui_pending_title = title

    def _post_data(self, data: UsageData):
        """Queue a full UI update (title + menu) from any thread."""
        with self._ui_lock:
            self._ui_pending_data = data

    def _flush_ui(self, _timer):
        """Main-thread ticker: apply any queued updates from background threads."""
        with self._ui_lock:
            title = self._ui_pending_title
            data = self._ui_pending_data
            self._ui_pending_title = None
            self._ui_pending_data = None
        if data is not None:
            self._apply(data)
        elif title is not None:
            self.title = title

    # -- widget ---------------------------------------------------------------

    def _deferred_welcome(self, _timer):
        """Runs once after the run loop is active, then stops itself."""
        _timer.stop()
        self._hook_status_button()
        self._check_widget_status()

    def _hook_status_button(self):
        """Replace NSMenu with panel toggle on the status item button click."""
        try:
            _ensure_panel_classes()
            if _ClickHandlerClass is None:
                log.warning("Cannot hook status button: ObjC classes unavailable")
                return

            btn = self._nsapp.nsstatusitem.button()
            if not btn:
                log.warning("Cannot hook status button: button() returned None")
                return

            # Keep original menu reference so rumps internals don't break
            self._original_menu = self._nsapp.nsstatusitem.menu()

            # Build a minimal right-click menu (fallback with Quit)
            from AppKit import NSMenu, NSMenuItem
            fallback = NSMenu.alloc().init()
            fallback.setAutoenablesItems_(False)
            quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Quit", b"terminate:", "q"
            )
            fallback.addItem_(quit_item)

            # Remove menu from status item so clicks route to button action
            self._nsapp.nsstatusitem.setMenu_(None)

            # Set up click handler
            handler = _ClickHandlerClass.alloc().init()
            type(handler)._toggle_fn = lambda: self._panel.toggle()
            type(handler)._refresh_fn = lambda: self._do_refresh(None)
            type(handler)._share_fn = lambda sender=None: self._share_popover.show(sender)
            type(handler)._copy_image_fn = lambda: self._share_popover.copy_image()
            type(handler)._share_on_x_fn = lambda: self._share_popover.share_on_x()
            type(handler)._show_menu_fn = lambda: self._show_fallback_menu()
            type(handler)._gear_menu_fn = lambda: self._get_settings_menu()
            type(handler)._dashboard_fn = lambda: self._open_dashboard(None)
            self._click_handler_inst = handler

            btn.setTarget_(handler)
            btn.setAction_(b"togglePanel:")

            # Accept both left and right mouse up so we can detect right-click
            # NSLeftMouseUpMask=4, NSRightMouseUpMask=16
            btn.sendActionOn_(4 | 16)

            log.info("Status button hooked for panel toggle")
        except Exception:
            log.debug("_hook_status_button failed", exc_info=True)

    def _show_fallback_menu(self):
        """Show the full NSMenu on right-click (fallback for settings/quit)."""
        try:
            # Dismiss the panel first if visible
            if self._panel and self._panel.visible:
                self._panel.dismiss()

            # Use the current rumps-managed menu (always up to date from _rebuild_menu)
            ns_menu = self._menu._menu if hasattr(self._menu, '_menu') else None
            if ns_menu is None:
                ns_menu = getattr(self, '_original_menu', None)
            if ns_menu:
                self._nsapp.nsstatusitem.popUpStatusItemMenu_(ns_menu)
        except Exception:
            log.debug("_show_fallback_menu failed", exc_info=True)

    def _get_settings_menu(self):
        """Return the full NSMenu for use as a settings popover from the gear button."""
        try:
            ns_menu = self._menu._menu if hasattr(self._menu, '_menu') else None
            if ns_menu is None:
                ns_menu = getattr(self, '_original_menu', None)
            return ns_menu
        except Exception:
            log.debug("_get_settings_menu failed", exc_info=True)
            return None

    def _check_widget_status(self):
        """Show startup info about what the app is doing."""
        seen_welcome = self.config.get("seen_welcome", False)
        widget_ok = _is_widget_installed()

        if not seen_welcome:
            # First launch: say hello, then show the dashboard once the
            # ledger has had a moment to index existing logs.
            _notify(
                f"Welcome to {APP_NAME}",
                "Tracking Claude Code, Cowork and Codex",
                "Click the \u25c6 in your menu bar. Your dashboard is opening.",
            )
            threading.Timer(20.0, lambda: self._open_dashboard(None)).start()
            self.config["seen_welcome"] = True
            save_config(self.config)
        else:
            # Subsequent launches -- brief notification
            if widget_ok:
                _notify(
                    APP_NAME,
                    "Running",
                    "Menu bar and desktop widget are synced.",
                )
            else:
                _notify(
                    APP_NAME,
                    "Running",
                    (
                        "Tracking usage from your menu bar. "
                        "A desktop widget is also available, check the menu."
                    ),
                )

    def _open_widget_settings(self, _sender):
        """Open the widget host app (shows add-widget instructions)."""
        subprocess.Popen(
            ["open", "-a", "TokenCoachWidget"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _install_widget_prompt(self, _sender):
        """Show instructions for building/installing the widget."""
        widget_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "widget")
        build_script = os.path.join(widget_dir, "build_widget.sh")
        if os.path.isfile(build_script):
            rumps.alert(
                title="Install Desktop Widget",
                message=(
                    "The widget needs Xcode. To install it, run in Terminal:\n\n"
                    f"bash '{build_script}'\n\n"
                    f"Then right-click the desktop \u2192 Edit Widgets \u2192 search '{APP_NAME}'."
                ),
            )
            return
        rumps.alert(
            title="Desktop Widget",
            message=(
                "The widget is built from source with Xcode and is included with the "
                "one-line installer (see the README). Homebrew installs the menu bar app only."
            ),
        )

    # -- fetch ----------------------------------------------------------------

    def _on_timer(self, _timer):
        self._schedule_fetch()
        self._schedule_ledger()

    # -- usage ledger ----------------------------------------------------------

    def _ledger(self):
        if self._ledger_conn is None:
            self._ledger_conn = _ledger.open_ledger()
        return self._ledger_conn

    def _schedule_ledger(self):
        with self._ledger_lock:
            if self._ledger_busy:
                return
            self._ledger_busy = True
        threading.Thread(target=self._ledger_pass, daemon=True).start()

    def _ledger_pass(self):
        """Index new log lines, then refresh the menu's spend summary.
        Runs off the main thread; never blocks the quota fetch."""
        try:
            overrides = _ledger.ledger_overrides(self.config)
            with self._ledger_lock:
                conn = self._ledger()
                counts = _ledger.ingest(conn, overrides=overrides, time_budget=30)
                self._ledger_summary = _ledger.today_summary(conn)
                if counts["complete"]:
                    if time.time() - self._last_lesson_scan > 3600:
                        try:
                            from tokencoach.coach import detect_lessons
                            detect_lessons(conn)
                            self._last_lesson_scan = time.time()
                        except Exception:
                            log.exception("lesson detection failed")
                    try:
                        from tokencoach import yield_metrics
                        yield_metrics.refresh(conn)      # commits of repositories the person opted in
                    except Exception:
                        log.exception("commit scan failed")
                    try:
                        from tokencoach.ledger_report import write_report
                        write_report(conn, self.config)
                    except Exception:
                        log.exception("dashboard write failed")
            if not counts["complete"]:
                self._ledger_status = "Still indexing older logs\u2026"
                threading.Timer(1.0, self._schedule_ledger).start()
            elif not self._optimizer_running:
                self._ledger_status = ""
        except Exception:
            log.exception("ledger pass failed")
            self._ledger_status = "Usage ledger unavailable (see log)"
        finally:
            self._ledger_busy = False
        if self._last_data is not None:
            self._post_data(self._last_data)

    def _open_dashboard(self, _sender):
        """Open the dashboard in Chrome (or the default browser). Rebuilds it
        first so it is current even between refreshes."""
        if self._panel and self._panel.visible:
            self._panel.dismiss()

        def work():
            try:
                from tokencoach.ledger_report import write_report, open_file
                browser = self.config.get("dashboard_browser")
                if self._dashboard is not None:
                    open_file(self._dashboard.url, browser)
                    return
                conn = _ledger.open_ledger()   # own connection: safe across threads
                try:
                    path = write_report(conn, self.config)
                finally:
                    conn.close()
                open_file(path, browser)
            except Exception:
                log.exception("dashboard failed")
                _notify(APP_NAME, "Could not open the dashboard", "See ~/Library/Logs/TokenCoach/tokencoach.log")
        threading.Thread(target=work, daemon=True).start()

    def _set_plan_prices(self, _sender):
        """Ask for monthly plan prices so the dashboard can show plan value."""
        plans = dict(self.config.get("ledger_plans") or {})
        for key, name in (("claude", "Claude"), ("chatgpt", "ChatGPT")):
            cur = plans.get(key)
            ans = _ask_text(
                "Plan prices",
                f"Your {name} plan price per month in USD (e.g. 20, 100, 200). Leave empty if you have none.",
                "" if cur is None else f"{cur:g}",
            )
            if ans is None:
                return
            ans = ans.strip().lstrip("$")
            if not ans:
                plans.pop(key, None)
                continue
            try:
                plans[key] = float(ans)
            except ValueError:
                _notify(APP_NAME, "Not a number", f"{name} price left unchanged")
        with self._config_lock:
            self.config["ledger_plans"] = plans
            save_config(self.config)
        self._schedule_ledger()

    def _sync_nudges(self):
        """Keep the Claude Code hook in line with the setting (on unless the
        person turned it off), pointing at this install."""
        try:
            from tokencoach import nudge
            want = (self.config.get("nudges") or {}).get("level", nudge.DEFAULT_LEVEL) != "off"
            install_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # install, or re-point a hook left behind by a moved install
            if want and nudge.installed_commands() != [nudge.hook_command(install_dir)]:
                nudge.install(install_dir)
                log.info("Claude Code nudge hook installed for %s", install_dir)
        except Exception:
            log.exception("nudge hook sync failed")

    def set_nudges(self, on: bool):
        from tokencoach import nudge
        install_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with self._config_lock:
            cfg = self.config.setdefault("nudges", {})
            cfg["level"] = nudge.DEFAULT_LEVEL if on else "off"
            save_config(self.config)
        if on:
            nudge.install(install_dir)
        else:
            nudge.uninstall()

    def _toggle_nudges(self, sender):
        from tokencoach import nudge
        try:
            self.set_nudges(not nudge.is_installed())
            sender._menuitem.setState_(1 if nudge.is_installed() else 0)
        except Exception:
            log.exception("toggle nudges failed")
            _notify(APP_NAME, "Could not change Claude Code settings", "See ~/Library/Logs/TokenCoach/tokencoach.log")

    def _analyze_usage(self, _sender):
        if self._optimizer_running:
            return
        self._optimizer_running = True
        self._ledger_status = "Analyzing your usage with Claude\u2026"
        if self._last_data is not None:
            self._post_data(self._last_data)

        def work():
            try:
                from tokencoach.optimizer import run_optimizer
                from tokencoach.coach import detect_lessons
                from tokencoach.ledger_report import open_file
                conn = _ledger.open_ledger()
                try:
                    detect_lessons(conn)
                    path = run_optimizer(conn)
                finally:
                    conn.close()
                open_file(path)
                _notify(APP_NAME, "Usage advice is ready", "Opened in your browser")
            except Exception as e:
                log.exception("optimizer failed")
                _notify(APP_NAME, "Usage analysis failed", str(e)[:200])
            finally:
                self._optimizer_running = False
                self._ledger_status = ""
                if self._last_data is not None:
                    self._post_data(self._last_data)
        threading.Thread(target=work, daemon=True).start()

    def _import_chat_export(self, _sender):
        def work():
            path = _choose_file("Choose a claude.ai or ChatGPT data export (.zip or conversations.json)")
            if not path:
                return
            try:
                from tokencoach.chat_import import import_export
                conn = _ledger.open_ledger()
                try:
                    res = import_export(conn, path)
                finally:
                    conn.close()
                _notify(APP_NAME, f"Imported {res['prompts']} chat prompts",
                        f"{res['conversations']} conversations from {res['file']} (token counts estimated)")
            except Exception as e:
                log.exception("chat import failed")
                _notify(APP_NAME, "Chat import failed", str(e)[:200])
        threading.Thread(target=work, daemon=True).start()

    def _schedule_fetch(self):
        with self._ui_lock:
            if self._fetching:
                return
            self._fetching = True
        threading.Thread(target=self._fetch_and_update, daemon=True).start()

    def _fetch_and_update(self):

        try:
            with self._config_lock:
                sk = self.config.get("cookie_str")
            if not sk and "claude" not in self._auto_detected:
                self._auto_detected.add("claude")
                sk = _auto_detect_cookies()
                if sk:
                    with self._config_lock:
                        self.config["cookie_str"] = sk
                        save_config(self.config)
            if not sk:
                self._post_title("\u25c6")
                self._fetching = False
                return
            raw = fetch_raw(sk)
            self._last_raw = raw
            self._auth_fail_count = 0
            data = parse_usage(raw)
            self._last_data = data
            self._last_updated = datetime.now()
            log.debug("parsed UsageData: %s", data)
            self._check_warnings(data)
            self._fetch_providers()
            self._check_provider_warnings(self._provider_data)
            self._cc_stats = fetch_claude_code_stats()

            # -- record usage history --
            if data.session:
                _append_history(self._history, "claude", data.session.pct)
            # Per-row history for multi-limit providers (avoids mixing
            # different limit types which made ETAs jump around).
            for prefix, pname in [("chatgpt", "ChatGPT")]:
                pd = next((p for p in self._provider_data if p.name == pname), None)
                if pd and not pd.error:
                    rows = getattr(pd, "_rows", None)
                    if rows:
                        for row in rows:
                            hkey = f"{prefix}_{row.label.lower().replace(' ', '_')}"
                            _append_history(self._history, hkey, row.pct)
            _save_history(self._history)

            # -- record to SQLite history --
            try:
                with self._db_lock:
                    if data.session:
                        _record_sample(self._history_db, "claude", data.session.pct)
                    for prefix, pname in [("chatgpt", "ChatGPT")]:
                        pd = next((p for p in self._provider_data if p.name == pname), None)
                        if pd and not pd.error:
                            rows = getattr(pd, "_rows", None)
                            if rows:
                                for row in rows:
                                    hkey = f"{prefix}_{row.label.lower().replace(' ', '_')}"
                                    _record_sample(self._history_db, hkey, row.pct)
                    self._history_db.commit()
                    # Periodic rollup (every hour)
                    if time.time() - self._last_rollup > 3600:
                        _rollup_daily_stats(self._history_db)
                        self._last_rollup = time.time()
            except Exception:
                log.exception("SQLite history recording failed")

            self._check_pacing_alerts()

            self._post_data(data)          # <- main thread applies title + menu
            _write_widget_cache(data, self._provider_data, self._cc_stats, self.config,
                                windows=health.windows_from(data, self._provider_data, self._history))

            # -- silent auto-update --
            if time.time() - self._last_update_check > UPDATE_CHECK_INTERVAL:
                self._last_update_check = time.time()
                with self._config_lock:
                    self.config["last_update_check"] = self._last_update_check
                    save_config(self.config)
                if _check_and_apply_update():
                    _restart_app()
        except CurlHTTPError as e:
            resp = getattr(e, "response", None)
            code = getattr(resp, "status_code", 0) or 0
            log.error("HTTP error: %s (status=%s)", e, code, exc_info=True)
            if code in (401, 403):
                self._auth_fail_count += 1
                self._post_title("\u25c6 !")
                if self._auth_fail_count >= 2:
                    self._auth_fail_count = 0
                    cookie_str = _auto_detect_cookies()
                    if cookie_str:
                        with self._config_lock:
                            self.config["cookie_str"] = cookie_str
                            save_config(self.config)
                        self._warned_pcts.clear()
                        log.info("Auth failed \u2014 auto-detected fresh cookies from browser")
                        self._schedule_fetch()
                    else:
                        _notify(
                            APP_NAME,
                            "Session expired \u2014 please update your cookie",
                            "Click: Set Session Cookie\u2026 or Auto-detect from Browser",
                        )
            else:
                self._post_title("\u25c6 err")
        except Exception:
            log.exception("fetch failed")
            self._post_title("\u25c6 ?")
        finally:
            self._fetching = False

    def _check_warnings(self, data: UsageData):
        """Send macOS notification when a Claude limit crosses a threshold or resets."""
        rows = [
            (data.session,       "session"),
            (data.weekly_all,    "weekly_all"),
            (data.weekly_sonnet, "weekly_sonnet"),
        ]
        warn_enabled = notif_enabled(self.config, "claude_warning")
        reset_enabled = notif_enabled(self.config, "claude_reset")

        for row, key in rows:
            if row is None:
                continue
            warn_key = f"{key}_{WARN_THRESHOLD}"
            crit_key = f"{key}_{CRIT_THRESHOLD}"
            prev = self._prev_pcts.get(key)

            # Reset detection: pct dropped significantly (>=10 pp) from above-warn to below
            if (reset_enabled and prev is not None
                    and prev >= WARN_THRESHOLD and row.pct < WARN_THRESHOLD
                    and (prev - row.pct) >= 10):
                self._warned_pcts.discard(warn_key)
                self._warned_pcts.discard(crit_key)
                _notify(
                    f"{APP_NAME} \u2705",
                    f"{row.label} has reset!",
                    f"{_remaining(row.pct)}% left \u2014 you're good to go.",
                )

            if warn_enabled:
                if row.pct >= CRIT_THRESHOLD and crit_key not in self._warned_pcts:
                    self._warned_pcts.add(crit_key)
                    _notify(
                        f"{APP_NAME} \U0001f534",
                        f"{row.label}: only {_remaining(row.pct)}% left!",
                        row.reset_str or "Limit almost reached",
                    )
                elif row.pct >= WARN_THRESHOLD and warn_key not in self._warned_pcts:
                    self._warned_pcts.add(warn_key)
                    _notify(
                        f"{APP_NAME} \U0001f7e1",
                        f"{row.label}: {_remaining(row.pct)}% left",
                        row.reset_str or "Approaching limit",
                    )
                elif row.pct < WARN_THRESHOLD:
                    self._warned_pcts.discard(warn_key)
                    self._warned_pcts.discard(crit_key)

            self._prev_pcts[key] = row.pct

    def _check_provider_warnings(self, provider_data: list):
        """Send macOS notification when provider rate limits cross a threshold or reset."""
        _warn_providers = [
            ("ChatGPT", "chatgpt", "chatgpt_warning", "chatgpt_reset"),
        ]
        for pname, prefix, warn_nkey, reset_nkey in _warn_providers:
            pd = next((p for p in provider_data if p.name == pname), None)
            if pd is None or pd.error:
                continue

            rows = getattr(pd, "_rows", None) or []
            warn_enabled = notif_enabled(self.config, warn_nkey)
            reset_enabled = notif_enabled(self.config, reset_nkey) if reset_nkey else False

            for row in rows:
                key = f"{prefix}_{row.label}"
                warn_key = f"{key}_{WARN_THRESHOLD}"
                crit_key = f"{key}_{CRIT_THRESHOLD}"
                prev = self._prev_pcts.get(key)

                if (reset_enabled and prev is not None
                        and prev >= WARN_THRESHOLD and row.pct < WARN_THRESHOLD
                        and (prev - row.pct) >= 10):
                    self._warned_pcts.discard(warn_key)
                    self._warned_pcts.discard(crit_key)
                    _notify(
                        f"{APP_NAME} \u2705",
                        f"{pname} {row.label} has reset!",
                        f"{_remaining(row.pct)}% left \u2014 you're good to go.",
                    )

                if warn_enabled:
                    if row.pct >= CRIT_THRESHOLD and crit_key not in self._warned_pcts:
                        self._warned_pcts.add(crit_key)
                        _notify(
                            f"{APP_NAME} \U0001f534",
                            f"{pname} {row.label}: only {_remaining(row.pct)}% left!",
                            row.reset_str or "Limit almost reached",
                        )
                    elif row.pct >= WARN_THRESHOLD and warn_key not in self._warned_pcts:
                        self._warned_pcts.add(warn_key)
                        _notify(
                            f"{APP_NAME} \U0001f7e1",
                            f"{pname} {row.label}: {_remaining(row.pct)}% left",
                            row.reset_str or "Approaching limit",
                        )
                    elif row.pct < WARN_THRESHOLD:
                        self._warned_pcts.discard(warn_key)
                        self._warned_pcts.discard(crit_key)

                self._prev_pcts[key] = row.pct

    def _check_pacing_alerts(self):
        """Send predictive notification when ETA drops below PACING_ALERT_MINUTES."""
        # Static entries (single history key per provider)
        checks: list[tuple[str, str, str]] = [
            ("claude",  "claude_pacing",  "Claude session"),
        ]
        # Dynamic per-row entries for multi-limit providers
        for prefix, pname, nkey in [
            ("chatgpt", "ChatGPT", "chatgpt_pacing"),
        ]:
            pd = next((p for p in self._provider_data if p.name == pname), None)
            if pd and not pd.error:
                rows = getattr(pd, "_rows", None) or []
                for row in rows:
                    hkey = f"{prefix}_{row.label.lower().replace(' ', '_')}"
                    checks.append((hkey, nkey, f"{pname} {row.label}"))

        for hkey, nkey, label in checks:
            if not notif_enabled(self.config, nkey):
                continue
            eta = _calc_eta_minutes(self._history, hkey)
            if eta is not None and eta <= PACING_ALERT_MINUTES:
                if hkey not in self._pacing_alerted:
                    self._pacing_alerted.add(hkey)
                    _notify(
                        f"{APP_NAME} \u23f1",
                        f"Slow down \u2014 {label} limit in ~{_fmt_eta(eta)}",
                        "At your current pace you'll hit the cap soon.",
                    )
            else:
                self._pacing_alerted.discard(hkey)

    # Bar icon/color config per provider name
    _BAR_PROVIDERS = {
        "Claude":  {"icon": "claude_icon.png",        "tint": None,      "color": "#D97757", "sym": "\u25cf"},
        "ChatGPT": {"icon": "chatgpt_icon_clean.png", "tint": "#74AA9C", "color": "#74AA9C", "sym": "\u25c7"},
    }

    def _set_bar_title(self, provider_segments: list[tuple[str, int, str]],
                       cc_msgs: int | None = None, states: dict | None = None):
        """Multi-indicator attributed title with brand logo icons.

        provider_segments: list of (provider_name, pct, extra_suffix)
          e.g. [("Claude", 36, " \u00b7"), ("ChatGPT", 12, "")]

        states: provider_name -> health state. Like the battery icon, the
        percentage keeps the normal menu bar color while healthy and turns
        orange (watch) or red (empty) only when it needs attention.

        Falls back to colored text symbols if AppKit / icons unavailable.
        """
        states = states or {}
        try:
            from AppKit import (NSColor, NSFont,
                                NSForegroundColorAttributeName, NSFontAttributeName)
            from Foundation import NSMutableAttributedString, NSAttributedString

            def _rgb(hex_str):
                r = int(hex_str[1:3], 16) / 255
                g = int(hex_str[3:5], 16) / 255
                b = int(hex_str[5:7], 16) / 255
                return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0)

            font = NSFont.menuBarFontOfSize_(0)
            base = {NSFontAttributeName: font} if font else {}

            s = NSMutableAttributedString.alloc().initWithString_("",)

            for i, (name, pct, suffix) in enumerate(provider_segments):
                cfg = self._BAR_PROVIDERS.get(name, {})
                color_hex = cfg.get("color", "#AAAAAA")
                color = _rgb(color_hex)

                if i > 0:
                    s.appendAttributedString_(
                        NSAttributedString.alloc().initWithString_attributes_("   ", base)
                    )

                icon_file = cfg.get("icon")
                tint = cfg.get("tint")
                img = _bar_icon(icon_file, tint_hex=tint) if icon_file else None
                if img:
                    s.appendAttributedString_(_icon_astr(img, base))
                else:
                    sym = cfg.get("sym", "\u25cf")
                    seg = NSMutableAttributedString.alloc().initWithString_attributes_(f"{sym} ", base)
                    seg.addAttribute_value_range_(NSForegroundColorAttributeName, color, (0, len(sym)))
                    s.appendAttributedString_(seg)

                num = NSMutableAttributedString.alloc().initWithString_attributes_(
                    f" {_remaining(pct)}%{suffix}", base)
                alert = {health.WATCH: NSColor.systemOrangeColor,
                         health.CRITICAL: NSColor.systemRedColor}.get(states.get(name))
                if alert:
                    num.addAttribute_value_range_(
                        NSForegroundColorAttributeName, alert(), (1, len(f"{_remaining(pct)}%")))
                s.appendAttributedString_(num)

            # -- Claude Code  diamond 3.2k --
            if cc_msgs is not None and cc_msgs > 0:
                cc_color = _rgb("#D97757")
                seg = NSMutableAttributedString.alloc().initWithString_attributes_(
                    f"   \u25c6 {_fmt_count(cc_msgs)}", base
                )
                seg.addAttribute_value_range_(NSForegroundColorAttributeName, cc_color, (3, 2))
                s.appendAttributedString_(seg)

            self._nsapp.nsstatusitem.setAttributedTitle_(s)
            return
        except Exception as e:
            log.debug("_set_bar_title failed: %s", e)
        # Plain-text fallback
        parts = []
        for name, pct, suffix in provider_segments:
            cfg = self._BAR_PROVIDERS.get(name, {})
            sym = cfg.get("sym", "\u25cf")
            parts.append(f"{sym} {_remaining(pct)}%{suffix}")
        if cc_msgs is not None and cc_msgs > 0:
            parts.append(f"\u25c6 {_fmt_count(cc_msgs)}")
        self.title = "  ".join(parts)

    def _provider_bar_pct(self, pd: ProviderData) -> int | None:
        """Extract a single percentage for the menu bar from a provider.

        Only the immediate-status rows count. A "Weekly" or "(Weekly)" row is a longer
        horizon than the bar communicates and must not be able to outrank
        the 5h/session number - same principle as Claude's own bar icon,
        which is driven by the session limit, never the max of all limits.
        """
        if pd.error:
            return None
        rows = getattr(pd, "_rows", None)
        if rows:
            immediate = [
                r for r in rows
                if r.label != "Weekly" and not r.label.endswith("(Weekly)")
            ]
            return max(r.pct for r in (immediate or rows))
        if pd.pct is not None:
            return pd.pct
        return None

    # Priority order for the 2 bar slots (highest first)
    _BAR_PRIORITY = ["Claude", "ChatGPT"]

    def _apply(self, data: UsageData):
        self._quota_health = health.quota_health(
            health.windows_from(data, self._provider_data, self._history))
        primary = data.session or data.weekly_all or data.weekly_sonnet
        if primary:
            weekly_maxed = any(
                r and r.pct >= CRIT_THRESHOLD
                for r in [data.weekly_all, data.weekly_sonnet]
            )
            extra = " \u00b7" if (weekly_maxed and primary is data.session
                             and primary.pct < CRIT_THRESHOLD) else ""

            # Collect all available segments
            available: dict[str, tuple[str, int, str]] = {}
            available["Claude"] = ("Claude", primary.pct, extra)
            for pd in self._provider_data:
                bar_pct = self._provider_bar_pct(pd)
                if bar_pct is not None:
                    available[pd.name] = (pd.name, bar_pct, "")

            # User-configured bar providers, or auto top 2 by priority
            chosen = self.config.get("bar_providers")
            if chosen:
                segments = [available[n] for n in chosen if n in available]
            else:
                segments = [available[n] for n in self._BAR_PRIORITY
                            if n in available][:2]

            # Claude Code weekly messages
            cc_msgs: int | None = None
            if self._cc_stats:
                cc_msgs = self._cc_stats.get("week_messages")

            self._set_bar_title(segments, cc_msgs=cc_msgs, states={
                "Claude": self._quota_health["providers"].get("claude"),
                "ChatGPT": self._quota_health["providers"].get("codex")})
        else:
            self.title = "\u25c6"
        self._rebuild_menu(data)
        # Refresh the floating panel if it's currently visible
        try:
            if self._panel and self._panel.visible:
                self._panel.refresh()
        except Exception:
            log.debug("panel refresh in _apply failed", exc_info=True)

    def _fetch_providers(self):
        """Fetch all configured third-party API providers (sync, called from fetch thread)."""
        # Auto-detect ChatGPT cookies if not saved yet
        _cookie_detectors = {
            "chatgpt_cookies": _auto_detect_chatgpt_cookies,
        }
        for cfg_key in COOKIE_PROVIDERS:
            with self._config_lock:
                has_key = bool(self.config.get(cfg_key))
            if not has_key and cfg_key not in self._auto_detected:
                self._auto_detected.add(cfg_key)
                detect_fn = _cookie_detectors.get(cfg_key)
                if detect_fn:
                    ck = detect_fn()
                    if ck:
                        with self._config_lock:
                            self.config[cfg_key] = ck
                            save_config(self.config)

        with self._config_lock:
            keys_snapshot = {k: self.config.get(k) for k in PROVIDER_REGISTRY}
        tasks = []
        for cfg_key, (name, fetch_fn) in PROVIDER_REGISTRY.items():
            key = keys_snapshot.get(cfg_key)
            if key:
                tasks.append((fetch_fn, key))
        if tasks:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            results = []
            with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
                futures = {pool.submit(fn, k): (fn, k) for fn, k in tasks}
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception:
                        log.exception("provider fetch failed")
            self._provider_data = results

            # Saved browser cookies can expire while another browser still has
            # a valid session. On a 401, try one different browser candidate
            # and persist it only after its usage request succeeds. Cool down
            # retries so a logged-out browser does not trigger cookie scans on
            # every refresh interval.
            chatgpt_pd = next((pd for pd in results if pd.name == "ChatGPT"), None)
            old_cookie = keys_snapshot.get("chatgpt_cookies")
            if (chatgpt_pd and chatgpt_pd.error and "HTTP 401" in chatgpt_pd.error
                    and old_cookie and time.time() >= self._chatgpt_cookie_retry_after):
                self._chatgpt_cookie_retry_after = time.time() + 15 * 60
                try:
                    refreshed_cookie = _auto_detect_chatgpt_cookies(exclude={old_cookie})
                    if refreshed_cookie and refreshed_cookie != old_cookie:
                        refreshed_data = fetch_chatgpt(refreshed_cookie)
                        if not refreshed_data.error:
                            with self._config_lock:
                                self.config["chatgpt_cookies"] = refreshed_cookie
                                save_config(self.config)
                            self._provider_data = [
                                refreshed_data if pd.name == "ChatGPT" else pd
                                for pd in results
                            ]
                            log.info("Replaced expired ChatGPT browser session")
                        else:
                            log.info("A second ChatGPT browser session also failed: %s",
                                     refreshed_data.error)
                except Exception:
                    log.debug("ChatGPT cookie recovery failed", exc_info=True)
        else:
            self._provider_data = []

    # -- callbacks ------------------------------------------------------------

    def _do_refresh(self, _sender):
        self._chatgpt_cookie_retry_after = 0.0
        self._schedule_fetch()

    def _open_usage_page(self, _sender):
        subprocess.Popen(["open", "https://claude.ai/settings/usage"])

    def _open_history_window(self, _sender):
        try:
            _show_history_window(self._history_db)
        except Exception:
            log.exception("Failed to open history window")

    def _open_github(self, _sender):
        subprocess.Popen(["open", REPO_URL])

    def _about(self, _sender):
        resp = rumps.alert(
            title=f"About {APP_NAME}",
            message=(
                f"{APP_NAME} tracks every Claude and ChatGPT prompt, coaches you to spend "
                "less for the same results, and shows the quota you have left.\n\n"
                "It began as a fork of AIQuotaBar by Toprak Yagcioglu, whose menu bar "
                "app is the foundation this one is built on. Thank you, Toprak."
            ),
            ok="Close", other="AIQuotaBar on GitHub",
        )
        if resp == -1:
            subprocess.Popen(["open", UPSTREAM_URL])

    def _share_on_x(self, _sender):
        data = self._last_data
        if data and data.session:
            pct = int(data.session.pct)
            icon = _status_icon(pct)
            text = (
                f"I've got {_remaining(pct)}% of my Claude session limit left {icon}\n"
                f"{APP_NAME} tracks every Claude + ChatGPT prompt and coaches me to "
                f"spend less for the same results\n"
                f"{REPO_URL.removeprefix('https://')}"
            )
        else:
            text = (
                f"{APP_NAME}: see what every Claude + ChatGPT prompt costs, and get "
                "coached to spend less for the same results\n"
                f"{REPO_URL.removeprefix('https://')}"
            )
        url = "https://x.com/intent/post?text=" + urllib.parse.quote(text)
        subprocess.Popen(["open", url])

    def _make_provider_key_cb(self, cfg_key: str, name: str):
        def _cb(_sender):
            if cfg_key in COOKIE_PROVIDERS:
                # Cookie-based: re-run auto-detect
                _detectors = {
                    "chatgpt_cookies": _auto_detect_chatgpt_cookies,
                }
                detect_fn = _detectors.get(cfg_key)
                if detect_fn:
                    _providers.forget_cookie_lookup()
                    ck = detect_fn()
                    if ck:
                        self.config[cfg_key] = ck
                        save_config(self.config)
                        if cfg_key == "chatgpt_cookies":
                            self._chatgpt_cookie_retry_after = 0.0
                        _notify(APP_NAME, f"{name} cookies updated \u2713", "Fetching usage\u2026")
                        self._schedule_fetch()
                    else:
                        _notify(APP_NAME, f"Could not find {name} session",
                                f"Make sure you are logged into {name} in your browser.")
                return
            # API key-based
            # The saved key is never pre-filled: the dialog travels as an
            # osascript command-line argument, which other processes can read.
            current = self.config.get(cfg_key, "")
            key = _ask_text(
                title=f"{APP_NAME} \u2014 {name}",
                prompt=(f"A {name} API key ending in \u2026{current[-4:]} is saved. Paste a new one to "
                        "replace it, type remove to delete it, or leave this empty to keep it."
                        if current else f"Paste your {name} API key."),
            )
            if key is None or not key.strip():
                return
            if key.strip().lower() == "remove":
                self.config.pop(cfg_key, None)
            else:
                self.config[cfg_key] = key.strip()
            save_config(self.config)
            self._schedule_fetch()
        return _cb

    def _make_notif_toggle_cb(self, nkey: str):
        def _cb(sender):
            current = notif_enabled(self.config, nkey)
            set_notif(self.config, nkey, not current)
            sender._menuitem.setState_(0 if current else 1)
        return _cb

    def _make_interval_cb(self, secs: int, label: str):
        def _cb(_sender):
            self._refresh_interval = secs
            self.config["refresh_interval"] = secs
            save_config(self.config)
            self._timer.stop()
            self._timer = rumps.Timer(self._on_timer, secs)
            self._timer.start()
            self._rebuild_menu(self._last_data)
        return _cb

    _TOGGLE_ICONS = {
        "Claude":  ("claude_icon.png",        None),
        "ChatGPT": ("chatgpt_icon_clean.png", "#74AA9C"),
    }

    def _make_sticky_toggle(self, display_name: str, is_on: bool, name: str):
        """Create a menu item that stays open on click (custom NSView) with a real icon."""
        item = rumps.MenuItem("")

        if _HAS_TOGGLE_VIEW:
            from AppKit import NSImageView

            view_w, view_h = 220, 22
            check_w = 22          # space for checkmark
            icon_sz = 16
            icon_pad = 4
            label_x = check_w + icon_sz + icon_pad + 4

            view = _BarToggleView.alloc().initWithFrame_(NSMakeRect(0, 0, view_w, view_h))

            # Checkmark label
            check = NSTextField.labelWithString_("\u2713" if is_on else "")
            check.setFont_(NSFont.menuFontOfSize_(14))
            check.setFrame_(NSMakeRect(6, 1, check_w - 4, view_h - 2))
            check.setBezeled_(False)
            check.setDrawsBackground_(False)
            check.setEditable_(False)
            check.setSelectable_(False)
            view.addSubview_(check)

            # Real icon
            icon_file, icon_tint = self._TOGGLE_ICONS.get(name, (None, None))
            if icon_file:
                img = _menu_icon(icon_file, tint_hex=icon_tint, size=icon_sz)
                if img:
                    iv = NSImageView.alloc().initWithFrame_(
                        NSMakeRect(check_w, (view_h - icon_sz) / 2, icon_sz, icon_sz)
                    )
                    iv.setImage_(img)
                    view.addSubview_(iv)

            # Provider name label
            label = NSTextField.labelWithString_(display_name)
            label.setFont_(NSFont.menuFontOfSize_(14))
            label.setFrame_(NSMakeRect(label_x, 1, view_w - label_x - 4, view_h - 2))
            label.setBezeled_(False)
            label.setDrawsBackground_(False)
            label.setEditable_(False)
            label.setSelectable_(False)
            view.addSubview_(label)

            view._label = label
            view._check = check
            self._bar_toggle_views[name] = (view, label, check)

            def _make_action(n):
                def _action():
                    self._do_bar_toggle(n)
                return _action

            view._action = _make_action(name)
            item._menuitem.setView_(view)
        else:
            # Fallback: standard menu item (will close on click)
            item = rumps.MenuItem(display_name, callback=lambda _: self._do_bar_toggle(name))
            item._menuitem.setState_(1 if is_on else 0)
            icon_file, icon_tint = self._TOGGLE_ICONS.get(name, (None, None))
            if icon_file:
                img = _menu_icon(icon_file, tint_hex=icon_tint, size=16)
                if img:
                    item._menuitem.setImage_(img)

        return item

    def _do_bar_toggle(self, name: str):
        """Toggle a provider in the status bar and update views in-place."""
        chosen = self.config.get("bar_providers")
        if not chosen:
            # Switching from auto -> manual: seed with current auto selection
            available_names = {"Claude"} if self._last_data else set()
            for pd in self._provider_data:
                if self._provider_bar_pct(pd) is not None:
                    available_names.add(pd.name)
            chosen = [n for n in self._BAR_PRIORITY if n in available_names][:2]
        if name in chosen:
            chosen.remove(name)
        else:
            chosen.append(name)
        # If empty after removal, go back to auto
        if not chosen:
            self.config.pop("bar_providers", None)
        else:
            self.config["bar_providers"] = chosen
        save_config(self.config)

        # Update all toggle views in-place (no menu rebuild needed)
        effective = self.config.get("bar_providers")
        if not effective:
            available_names = {"Claude"} if self._last_data else set()
            for pd in self._provider_data:
                if self._provider_bar_pct(pd) is not None:
                    available_names.add(pd.name)
            auto_shown = set(
                [n for n in self._BAR_PRIORITY if n in available_names][:2]
            )
        else:
            auto_shown = None

        for n, (view, label, check) in self._bar_toggle_views.items():
            is_on = n in effective if effective else n in auto_shown
            check.setStringValue_("\u2713" if is_on else "")

        if self._last_data:
            self._apply(self._last_data)

    def _bar_reset_auto(self, _sender):
        """Reset bar display to auto-detect (top 2 active providers)."""
        self.config.pop("bar_providers", None)
        save_config(self.config)
        self._rebuild_menu(self._last_data)
        if self._last_data:
            self._apply(self._last_data)

    def _set_cookie(self, _sender):
        key = _ask_text(
            title="Claude Usage \u2014 Set Cookies",
            prompt=(
                "Paste ALL cookies from claude.ai (needed to bypass Cloudflare)\n\n"
                "How to get them:\n"
                "  1. Open https://claude.ai/settings/usage in Chrome\n"
                "  2. F12 \u2192 Network tab \u2192 click any request to claude.ai\n"
                "  3. In Headers, find the 'cookie:' row\n"
                "  4. Right-click it \u2192 Copy value  (long string with semicolons)"
                + ("\n\nCookies are saved already; leave this empty to keep them."
                   if self.config.get("cookie_str") else "")
            ),
            # Never pre-fill the saved cookie: osascript gets the dialog as a
            # command-line argument, which other processes can read.
        )
        if key:
            self.config["cookie_str"] = key.strip()
            save_config(self.config)
            self._warned_pcts.clear()
            self._auth_fail_count = 0
            self._schedule_fetch()

    def _paste_cookie(self, _sender):
        text = _clipboard_text()
        if not text or ("sessionKey" not in text and "=" not in text):
            _notify(
                APP_NAME,
                "Nothing useful in clipboard",
                "Copy your cookie string from Chrome DevTools first.",
            )
            return
        self.config["cookie_str"] = text
        save_config(self.config)
        self._warned_pcts.clear()
        self._auth_fail_count = 0
        self._schedule_fetch()
        _notify(
            APP_NAME,
            "Cookie updated from clipboard \u2713",
            "Fetching usage data\u2026",
        )

    def _show_raw(self, _sender):
        text = json.dumps(self._last_raw.get("usage", self._last_raw), indent=2)
        _show_text(title="Claude Usage \u2014 Raw API Response", text=text)

    def _toggle_login_item(self, sender):
        if _is_login_item():
            _remove_login_item()
            self._login_item_cached = False
            sender._menuitem.setState_(0)
            _notify(APP_NAME, "Removed from Login Items", "")
        else:
            _add_login_item()
            self._login_item_cached = True
            sender._menuitem.setState_(1)
            _notify(APP_NAME, "Added to Login Items", "Will launch automatically on login")

    def _try_auto_detect(self):
        """Background: silently try to grab cookies from the browser on first run."""
        cookie_str = _auto_detect_cookies()
        if cookie_str:
            self.config["cookie_str"] = cookie_str
            save_config(self.config)
            _notify(
                APP_NAME,
                "Cookies auto-detected from your browser \u2713",
                "Fetching usage data\u2026",
            )
            self._schedule_fetch()

    def _auto_detect_menu(self, _sender):
        """Menu item: manually trigger auto-detect (runs in background thread)."""
        if not _BROWSER_COOKIE3_OK:
            _notify(
                APP_NAME,
                "browser-cookie3 not installed",
                "Run: pip install browser-cookie3",
            )
            return
        # Run cookie detection in a background thread -- browser_cookie3 accesses
        # SQLite databases and Keychain which can hard-crash if called on the main thread.
        threading.Thread(target=self._do_auto_detect, daemon=True).start()

    def _do_auto_detect(self):
        """Background: detect cookies then schedule a fetch."""
        _providers.forget_cookie_lookup()        # asked for now: don't reuse a lookup from before
        try:
            cookie_str = _auto_detect_cookies()
        except Exception:
            log.exception("_auto_detect_cookies failed")
            cookie_str = None
        if cookie_str:
            with self._config_lock:
                self.config["cookie_str"] = cookie_str
                save_config(self.config)
            self._warned_pcts.clear()
            self._auth_fail_count = 0
            _notify(APP_NAME, "Cookies auto-detected \u2713", "Fetching usage data\u2026")
            self._schedule_fetch()
        elif _providers.last_blocked_browsers:
            names = ", ".join(b.title() for b in _providers.last_blocked_browsers)
            _notify(
                APP_NAME,
                f"macOS kept TokenCoach out of {names}",
                "Its privacy protection blocks reading another app's data. Use "
                "Set Session Cookie\u2026 in this menu instead.",
            )
        else:
            _notify(
                APP_NAME,
                "Could not find claude.ai session in any browser",
                "Make sure you are logged in to claude.ai in Chrome, Firefox, or Safari.",
            )
