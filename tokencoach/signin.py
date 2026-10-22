"""Built-in "Sign in to Claude" window: a WKWebView on claude.ai/login.

Reading browser cookies is often blocked by macOS (Keychain / Full Disk
Access). Signing in here instead puts the session in this app's own WebKit
store, so nothing outside TokenCoach is read. WebKit is imported lazily: if
it is missing, `available()` is False and the caller falls back to pasting.
"""
import logging
import threading
from urllib.parse import urlparse

log = logging.getLogger("tokencoach")

LOGIN_URL = "https://claude.ai/login"
_WANTED = ("sessionKey", "lastActiveOrg", "routingHint")
GOOGLE_MESSAGE = ("If Google says this browser isn't supported, use 'Continue with email' here, "
                  "or sign in with your browser instead.")


def is_google_sso_url(url: str) -> bool:
    """True for Google's sign-in pages, which refuse to load in embedded webviews."""
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return False
    return host == "accounts.google.com" or host.endswith(".accounts.google.com")


def safari_ua_suffix(version: str) -> str:
    """What Safari appends to WebKit's user agent, e.g. 'Version/18.0 Safari/605.1.15'."""
    v = version if version and all(p.isdigit() for p in version.split(".")) else "18.0"
    return f"Version/{v} Safari/605.1.15"


def _safari_version() -> str:
    try:
        import plistlib
        with open("/Applications/Safari.app/Contents/Info.plist", "rb") as f:
            return str(plistlib.load(f).get("CFBundleShortVersionString", ""))
    except Exception:
        return ""


def build_cookie_string(cookies) -> str:
    """cookies: iterable of (name, domain, value). Returns '' without a sessionKey.

    Keeps only sessionKey / lastActiveOrg / routingHint set for claude.ai;
    never Cloudflare or other cookies.
    """
    picked = {}
    for name, domain, value in cookies:
        d = (domain or "").lstrip(".").lower()
        if (d == "claude.ai" or d.endswith(".claude.ai")) and name in _WANTED and value:
            picked[name] = value
    if "sessionKey" not in picked:
        return ""
    return "; ".join(f"{k}={picked[k]}" for k in _WANTED if k in picked)


def available() -> bool:
    try:
        import WebKit  # noqa: F401
        return True
    except Exception:
        return False


_controller = None      # the one open window, if any


def _guarded(fn, *args):
    """Run a WebKit/AppKit callback. An exception escaping one is uncaught
    inside Cocoa and terminates the whole menubar app, so log it instead."""
    try:
        return fn(*args)
    except Exception:
        log.exception("sign-in window callback failed")


def open_window(on_success, on_browser_fallback=None) -> bool:
    """Show (or raise) the sign-in window. Call on the main thread.

    on_success(cookie_str) runs on the main thread once a validated session
    exists. on_browser_fallback() runs when the person picks "Use my browser
    instead". Returns False if WebKit is unavailable.
    """
    global _controller
    if _controller is not None:
        _controller.raise_window()
        return True
    if not available():
        return False
    try:
        _controller = _SignInWindow(on_success, on_browser_fallback)
        _controller.show()
    except Exception:
        log.exception("could not open the sign-in window")
        _controller = None
        return False
    return True


class _SignInWindow:
    def __init__(self, on_success, on_browser_fallback):
        import objc
        import AppKit
        import Foundation
        import WebKit
        self._on_success = on_success
        self._on_fallback = on_browser_fallback
        self._done = False
        self._checking = False
        self._rejected = None   # a stale session left in the store: don't re-ask claude.ai every tick
        self._timer = None
        self._popups = []       # (window, webview) for sign-in pop-ups
        owner = self

        class _Delegate(Foundation.NSObject, protocols=[objc.protocolNamed("WKNavigationDelegate"),
                                                        objc.protocolNamed("WKUIDelegate")]):
            def webView_didFinishNavigation_(self, _wv, _nav):
                _guarded(owner.poll)

            def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
                    self, wv, _cfg, action, _features):
                # "Continue with Google" opens a pop-up; returning None refuses it and
                # claude.ai shows "There was an error logging you in".
                return _guarded(owner.open_popup, _cfg, action)

            def webViewDidClose_(self, wv):
                _guarded(owner.close_popup, wv)

            # Not decidePolicyForNavigationAction: PyObjC can't call its
            # decisionHandler block ("cannot call block without a signature"), and
            # that uncaught exception inside WebKit killed the whole app.
            def webView_didStartProvisionalNavigation_(self, wv, _nav):
                _guarded(owner.check_url, wv)

            def webView_didReceiveServerRedirectForProvisionalNavigation_(self, wv, _nav):
                _guarded(owner.check_url, wv)

            def windowWillClose_(self, _note):
                _guarded(owner.close)

            def tick_(self, _timer):
                _guarded(owner.poll)

            def useBrowser_(self, _sender):
                _guarded(owner.use_browser)

        self._delegate = _Delegate.alloc().init()
        style = (AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable
                 | AppKit.NSWindowStyleMaskMiniaturizable)
        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(0, 0, 480, 680), style, AppKit.NSBackingStoreBuffered, False)
        self._window.setTitle_("Sign in to Claude")
        self._window.setReleasedWhenClosed_(False)
        self._window.center()
        self._window.setDelegate_(self._delegate)
        content = self._window.contentView()
        bounds = content.bounds()
        # A bar above the page, hidden until Google sign-in is attempted.
        self._bar = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, bounds.size.height - 64, bounds.size.width, 64))
        self._bar.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
        label = AppKit.NSTextField.labelWithString_(GOOGLE_MESSAGE)
        label.setFrame_(Foundation.NSMakeRect(8, 30, bounds.size.width - 16, 30))
        label.setFont_(AppKit.NSFont.systemFontOfSize_(11))
        label.setAutoresizingMask_(AppKit.NSViewWidthSizable)
        btn = AppKit.NSButton.alloc().initWithFrame_(Foundation.NSMakeRect(8, 4, 170, 24))
        btn.setTitle_("Use my browser instead")
        btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        btn.setTarget_(self._delegate)
        btn.setAction_("useBrowser:")
        self._bar.addSubview_(label)
        self._bar.addSubview_(btn)
        self._bar.setHidden_(True)
        self._bar_height = 64
        cfg = WebKit.WKWebViewConfiguration.alloc().init()     # default persistent data store
        # Same engine as Safari, so say so: Google refuses sign-in to user agents
        # that lack the Safari token, which a plain WKWebView does.
        cfg.setApplicationNameForUserAgent_(safari_ua_suffix(_safari_version()))
        self._web = WebKit.WKWebView.alloc().initWithFrame_configuration_(
            Foundation.NSMakeRect(0, 0, bounds.size.width, bounds.size.height), cfg)
        self._web.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        self._web.setNavigationDelegate_(self._delegate)
        self._web.setUIDelegate_(self._delegate)
        content.addSubview_(self._web)
        content.addSubview_(self._bar)

    def show(self):
        import AppKit
        import Foundation
        self._web.loadRequest_(Foundation.NSURLRequest.requestWithURL_(
            Foundation.NSURL.URLWithString_(LOGIN_URL)))
        self._timer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.5, self._delegate, "tick:", None, True)
        self.raise_window()

    def raise_window(self):
        import AppKit
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        self._window.makeKeyAndOrderFront_(None)

    def open_popup(self, cfg, action):
        """A child window for window.open(). WebKit requires the returned view to
        use `cfg`, which shares this window's cookie store, so a session set by
        the pop-up is picked up by poll()."""
        import AppKit
        import Foundation
        import WebKit
        frame = self._window.frame()
        win = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(frame.origin.x + 40, frame.origin.y - 40, 480, 640),
            AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable,
            AppKit.NSBackingStoreBuffered, False)
        win.setTitle_("Sign in to Claude")
        win.setReleasedWhenClosed_(False)
        web = WebKit.WKWebView.alloc().initWithFrame_configuration_(
            win.contentView().bounds(), cfg)
        web.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        web.setNavigationDelegate_(self._delegate)
        web.setUIDelegate_(self._delegate)
        win.contentView().addSubview_(web)
        win.makeKeyAndOrderFront_(None)
        self._popups.append((win, web))
        url = action.request().URL()
        self.check_url(web, str(url.absoluteString()) if url else "")
        return web

    def close_popup(self, web):
        """The pop-up called window.close() (Google sign-in finished or was cancelled)."""
        for win, w in list(self._popups):
            if w is web:
                self._popups.remove((win, w))
                w.setNavigationDelegate_(None)
                w.setUIDelegate_(None)
                win.orderOut_(None)
                win.close()
        self.poll()

    def check_url(self, web, url=None):
        """On a Google page, offer the browser fallback in case Google still refuses."""
        if url is None:
            u = web.URL()
            url = str(u.absoluteString()) if u else ""
        if is_google_sso_url(url):
            self.show_google_notice()

    def show_google_notice(self):
        import Foundation
        h = self._bar_height
        frame = self._web.frame()
        self._web.setFrame_(Foundation.NSMakeRect(0, 0, frame.size.width, self._window.contentView().bounds().size.height - h))
        self._bar.setHidden_(False)

    def use_browser(self):
        import subprocess
        subprocess.Popen(["open", "https://claude.ai"])
        cb = self._on_fallback
        self.close()
        if cb:
            cb()

    def poll(self):
        if self._done or self._checking:
            return
        self._checking = True

        def read(cookies):
            triples = [(str(c.name()), str(c.domain()), str(c.value())) for c in (cookies or [])]
            cookie_str = build_cookie_string(triples)
            if not cookie_str or cookie_str == self._rejected:
                self._checking = False
                return
            threading.Thread(target=self._validate, args=(cookie_str,), daemon=True).start()

        def handler(cookies):
            # WebKit calls this on the main thread. Uncaught, an error here would end
            # the app; and _checking must be reset or every later poll is skipped.
            try:
                read(cookies)
            except Exception:
                log.exception("sign-in window: reading cookies failed")
                self._checking = False

        store = self._web.configuration().websiteDataStore().httpCookieStore()
        store.getAllCookies_(handler)

    def _validate(self, cookie_str):
        from PyObjCTools import AppHelper
        from tokencoach.providers import _claude_cookie_is_valid
        ok = _claude_cookie_is_valid(cookie_str)
        log.debug("sign-in window: session cookie valid=%s", ok)
        AppHelper.callAfter(_guarded, self._finish, cookie_str, ok)

    def _finish(self, cookie_str, ok):
        self._checking = False
        if not ok:
            self._rejected = cookie_str
            return
        if self._done:
            return
        self._done = True
        cb = self._on_success
        self.close()
        cb(cookie_str)

    def close(self):
        global _controller
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        for win, web in self._popups:
            try:
                web.setNavigationDelegate_(None)
                web.setUIDelegate_(None)
                win.orderOut_(None)
                win.close()
            except Exception:
                log.debug("sign-in pop-up close failed", exc_info=True)
        self._popups = []
        try:
            self._web.setNavigationDelegate_(None)
            self._window.setDelegate_(None)
            self._window.orderOut_(None)
            self._window.close()
        except Exception:
            log.debug("sign-in window close failed", exc_info=True)
        if _controller is self:
            _controller = None
