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
GOOGLE_MESSAGE = ("Google sign-in doesn't work inside apps. Use 'Continue with email' here, "
                  "or sign in with your browser instead.")


def is_google_sso_url(url: str) -> bool:
    """True for Google's sign-in pages, which refuse to load in embedded webviews."""
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except ValueError:
        return False
    return host == "accounts.google.com" or host.endswith(".accounts.google.com")


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
        owner = self

        class _Delegate(Foundation.NSObject, protocols=[objc.protocolNamed("WKNavigationDelegate"),
                                                        objc.protocolNamed("WKUIDelegate")]):
            def webView_didFinishNavigation_(self, _wv, _nav):
                owner.poll()

            def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
                    self, wv, _cfg, action, _features):
                # Sign-in pop-ups (window.open) would otherwise silently do nothing.
                url = action.request().URL()
                if is_google_sso_url(str(url.absoluteString()) if url else ""):
                    owner.show_google_notice()
                else:
                    wv.loadRequest_(action.request())
                return None

            def webView_decidePolicyForNavigationAction_decisionHandler_(self, _wv, action, handler):
                url = action.request().URL()
                if is_google_sso_url(str(url.absoluteString()) if url else ""):
                    handler(WebKit.WKNavigationActionPolicyCancel)
                    owner.show_google_notice()
                else:
                    handler(WebKit.WKNavigationActionPolicyAllow)

            def windowWillClose_(self, _note):
                owner.close()

            def tick_(self, _timer):
                owner.poll()

            def useBrowser_(self, _sender):
                owner.use_browser()

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

        def handler(cookies):
            # WebKit calls this on the main thread.
            triples = [(str(c.name()), str(c.domain()), str(c.value())) for c in (cookies or [])]
            cookie_str = build_cookie_string(triples)
            if not cookie_str or cookie_str == self._rejected:
                self._checking = False
                return
            threading.Thread(target=self._validate, args=(cookie_str,), daemon=True).start()

        store = self._web.configuration().websiteDataStore().httpCookieStore()
        store.getAllCookies_(handler)

    def _validate(self, cookie_str):
        from PyObjCTools import AppHelper
        from tokencoach.providers import _claude_cookie_is_valid
        ok = _claude_cookie_is_valid(cookie_str)
        log.debug("sign-in window: session cookie valid=%s", ok)
        AppHelper.callAfter(self._finish, cookie_str, ok)

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
        try:
            self._web.setNavigationDelegate_(None)
            self._window.setDelegate_(None)
            self._window.orderOut_(None)
            self._window.close()
        except Exception:
            log.debug("sign-in window close failed", exc_info=True)
        if _controller is self:
            _controller = None
