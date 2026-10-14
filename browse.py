"""Drive a real Chromium browser — headless here, or the visible one in hive-browser.

Run with /opt/venv/bin/python. The python3 first on PATH in the mind
containers is a stale venv whose Playwright expects a Chromium build that is
not installed, and fails with "Executable doesn't exist".

A run is a list of steps executed in order against one page:

    /opt/venv/bin/python browse.py --phone --hive \\
        open http://hive-site:8710/kanban/board \\
        tap 'text=Kanban' \\
        shot /tmp/after-tap.png \\
        text

Steps: open URL, tap SELECTOR, type SELECTOR TEXT, press KEY, wait MS,
waitfor SELECTOR, shot PATH, text, url, eval JS. Selectors are Playwright
selectors, so 'text=Backlog' and 'button.console-nav-link' both work.

--headed drives the visible browser at HIVE_BROWSER_CDP (default
http://hive-browser:9223) in a new tab, so Daniel watching
browser.sparktobloom.com sees it happen. The tab closes when the run ends;
--keep leaves it open for him.

--hive signs in to the hive site first. Credentials come from HIVE_USERNAME
and HIVE_PASSWORD, else from the keyring entries CYPHER_HIVE_USERNAME and
CYPHER_HIVE_PASSWORD.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

PHONE = {"viewport": {"width": 390, "height": 844}, "device_scale_factor": 3,
         "is_mobile": True, "has_touch": True,
         "user_agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
                        "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")}
DESKTOP = {"viewport": {"width": 1366, "height": 900}}
DEFAULT_CDP = "http://hive-browser:9223"
DEFAULT_HIVE = "http://hive-site:8710"

STEP_ARITY = {"open": 1, "tap": 1, "type": 2, "press": 1, "wait": 1, "waitfor": 1,
              "shot": 1, "text": 0, "url": 0, "eval": 1}


@dataclass
class Session:
    """One page plus whatever owns it. close() closes a headed tab unless
    keep is set, and never closes the visible browser itself."""
    page: Page
    context: BrowserContext
    browser: Browser
    headed: bool
    _pw: Any = field(repr=False, default=None)
    keep: bool = False

    def close(self) -> None:
        if not self.headed:
            self.context.close()
            self.browser.close()
        elif not self.keep and not self.page.is_closed():
            self.page.close()
        self._pw.stop()


def start(*, phone: bool = False, headed: bool = False, cdp_url: str | None = None,
          keep: bool = False) -> Session:
    pw = sync_playwright().start()
    profile = PHONE if phone else DESKTOP
    try:
        if headed:
            url = _by_address(cdp_url or os.getenv("HIVE_BROWSER_CDP", DEFAULT_CDP))
            try:
                browser = pw.chromium.connect_over_cdp(url)
            except Exception as exc:
                raise SystemExit(
                    f"the visible browser is not answering at {url} ({str(exc).splitlines()[0]}). "
                    "It runs in the hive-browser container; start it on the host with: docker compose "
                    "-f /home/daniel/Storage/Dev/hive-browser/container/compose.yaml up -d --build") from None
            # A new context would be an invisible incognito window's worth of
            # state nobody sees reused; the default context is the window on
            # Daniel's screen. Phone emulation is applied per page instead.
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            if phone:
                emulate_phone(page)
            else:
                page.set_viewport_size(profile["viewport"])
        else:
            browser = pw.chromium.launch()
            context = browser.new_context(**profile)
            page = context.new_page()
    except BaseException:
        pw.stop()
        raise
    return Session(page=page, context=context, browser=browser, headed=headed, _pw=pw, keep=keep)


def _by_address(url: str) -> str:
    """Chromium's debugging endpoint answers only to an IP address or
    localhost in the Host header — a DNS-rebinding guard — so the container
    name is resolved here rather than sent."""
    import socket
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        socket.inet_aton(host)
        return url
    except OSError:
        pass
    if host == "localhost":
        return url
    try:
        address = socket.gethostbyname(host)
    except OSError:
        return url  # let the connect fail and report the name it was given
    netloc = address + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=netloc))


def emulate_phone(page: Page) -> None:
    """Make one tab of an already-running browser a phone. A launched browser
    gets this from its context options; a tab in Daniel's visible window has
    no context of its own, so the same device is set through CDP emulation —
    touch included, or every tap would silently become a click."""
    vp = PHONE["viewport"]
    cdp = page.context.new_cdp_session(page)
    cdp.send("Emulation.setDeviceMetricsOverride", {"width": vp["width"], "height": vp["height"],
             "deviceScaleFactor": PHONE["device_scale_factor"], "mobile": True})
    cdp.send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
    cdp.send("Emulation.setEmitTouchEventsForMouse", {"enabled": True, "configuration": "mobile"})
    cdp.send("Network.setUserAgentOverride", {"userAgent": PHONE["user_agent"], "platform": "iPhone"})
    page._hive_touch_cdp = cdp


def touch_tap(page: Page, locator) -> None:
    """A finger tap on a phone-emulated tab of the visible browser. Playwright
    refuses tap() outside a touch context it created, so the touch is sent
    through CDP at the element's centre — the same events a phone emits."""
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box is None:
        raise RuntimeError("element to tap is not visible")
    point = {"x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2}
    cdp = page._hive_touch_cdp
    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [point]})
    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def hive_credentials() -> tuple[str, str]:
    user, password = os.getenv("HIVE_USERNAME"), os.getenv("HIVE_PASSWORD")
    if user and password:
        return user, password
    # The mind container's own keyring, which a bare shell does not select.
    os.environ.setdefault("KEY_RING", "/usr/src/app/data/keyring")
    os.environ.setdefault("PYTHON_KEYRING_BACKEND", "core.keyring_backend.HiveMindKeyring")
    if "/usr/src/app" not in sys.path:
        sys.path.append("/usr/src/app")
    try:
        import keyring
        user = user or keyring.get_password("hive-mind", "CYPHER_HIVE_USERNAME")
        password = password or keyring.get_password("hive-mind", "CYPHER_HIVE_PASSWORD")
    except Exception:  # keyring absent or unreadable: fall through to the error below
        pass
    if not user or not password:
        raise SystemExit("hive sign-in needs HIVE_USERNAME and HIVE_PASSWORD, or the keyring "
                         "entries CYPHER_HIVE_USERNAME and CYPHER_HIVE_PASSWORD")
    return user, password


def hive_sign_in(session: Session, base_url: str = DEFAULT_HIVE,
                 username: str | None = None, password: str | None = None) -> None:
    """Post the hive login form through the browser's own request context, so
    the session cookie lands in the browser exactly as a real sign-in would."""
    if username is None or password is None:
        username, password = hive_credentials()
    base = base_url.rstrip("/")
    response = session.context.request.post(f"{base}/login", form={
        "username": username, "password": password, "next": "/overview"}, max_redirects=0)
    # The production cookie is scoped to the parent domain sparktobloom.com,
    # so a browser talking to hive by its container name rejects it outright.
    # Take the token off the response and pin it to the host being browsed.
    for header in response.headers_array:
        if header["name"].lower() == "set-cookie" and header["value"].startswith("hive_session="):
            token = header["value"].split(";", 1)[0].split("=", 1)[1]
            session.context.add_cookies([{"name": "hive_session", "value": token, "url": base}])
    if response.status != 303 or not any(c["name"] == "hive_session" for c in session.context.cookies(base)):
        raise RuntimeError(f"hive sign-in as {username} failed: HTTP {response.status}")


def run_step(page: Page, name: str, args: list[str]) -> str | None:
    if name == "open":
        page.goto(args[0], wait_until="load")
    elif name == "tap":
        # A touch page gets a real tap — the gesture a phone makes, which is
        # what the Kanban bug hid from a click. Without touch, tap() raises,
        # and a desktop page gets a click.
        locator = page.locator(args[0]).first
        if page.evaluate("navigator.maxTouchPoints") == 0:
            locator.click(timeout=15000)
        elif getattr(page, "_hive_touch_cdp", None):
            touch_tap(page, locator)
        else:
            locator.tap(timeout=15000)
        page.wait_for_load_state("load")
    elif name == "type":
        page.locator(args[0]).first.fill(args[1])
    elif name == "press":
        page.keyboard.press(args[0])
    elif name == "wait":
        page.wait_for_timeout(int(args[0]))
    elif name == "waitfor":
        page.locator(args[0]).first.wait_for()
    elif name == "shot":
        page.screenshot(path=args[0])
        return args[0]
    elif name == "text":
        return page.locator("body").inner_text()
    elif name == "url":
        return page.url
    elif name == "eval":
        return repr(page.evaluate(args[0]))
    else:
        raise ValueError(f"unknown step {name!r}; known: {', '.join(STEP_ARITY)}")
    return None


def parse_steps(tokens: list[str]) -> list[tuple[str, list[str]]]:
    steps, i = [], 0
    while i < len(tokens):
        name = tokens[i]
        if name not in STEP_ARITY:
            raise SystemExit(f"unknown step {name!r}; known: {', '.join(STEP_ARITY)}")
        arity = STEP_ARITY[name]
        args = tokens[i + 1:i + 1 + arity]
        if len(args) != arity:
            raise SystemExit(f"step {name!r} takes {arity} argument(s)")
        steps.append((name, args))
        i += 1 + arity
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--phone", action="store_true", help="390x844 touch phone instead of desktop")
    parser.add_argument("--headed", action="store_true", help="drive the visible browser over CDP")
    parser.add_argument("--keep", action="store_true", help="with --headed, leave the tab open afterwards")
    parser.add_argument("--cdp", default=None, help=f"CDP URL for --headed (default {DEFAULT_CDP})")
    parser.add_argument("--hive", action="store_true", help="sign in to the hive site first")
    parser.add_argument("--hive-url", default=DEFAULT_HIVE, help=f"hive site for --hive (default {DEFAULT_HIVE})")
    parser.add_argument("steps", nargs=argparse.REMAINDER)
    ns = parser.parse_args(argv)
    steps = parse_steps(ns.steps)
    session = start(phone=ns.phone, headed=ns.headed, cdp_url=ns.cdp, keep=ns.keep)
    try:
        if ns.hive:
            hive_sign_in(session, ns.hive_url)
        for name, args in steps:
            out = run_step(session.page, name, args)
            if out is not None:
                print(f"[{name}] {out}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
