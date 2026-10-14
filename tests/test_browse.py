import struct
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import browse
from conftest import free_port, wait_http


def png_size(path: str) -> tuple[int, int]:
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


@pytest.mark.parametrize("phone,pointer", [(True, "touch"), (False, "mouse")])
def test_a_tap_lands_as_a_finger_on_a_phone_and_a_mouse_on_a_desktop(page_url, phone, pointer):
    session = browse.start(phone=phone)
    try:
        browse.run_step(session.page, "open", [page_url])
        browse.run_step(session.page, "tap", ["#go"])
        assert browse.run_step(session.page, "text", []).splitlines()[-1] == pointer
    finally:
        session.close()


def test_typing_fills_the_field(page_url):
    session = browse.start()
    try:
        browse.run_step(session.page, "open", [page_url])
        browse.run_step(session.page, "type", ["#name", "Cypher"])
        assert session.page.input_value("#name") == "Cypher"
    finally:
        session.close()


@pytest.mark.parametrize("phone,expected", [(True, (390 * 3, 844 * 3)), (False, (1366, 900))])
def test_a_screenshot_is_an_image_of_the_requested_screen_size(page_url, tmp_path, phone, expected):
    shot = str(tmp_path / "shot.png")
    session = browse.start(phone=phone)
    try:
        browse.run_step(session.page, "open", [page_url])
        assert browse.run_step(session.page, "shot", [shot]) == shot
    finally:
        session.close()
    assert png_size(shot) == expected


def test_hive_sign_in_lets_a_protected_page_load(hive_site):
    session = browse.start(phone=True)
    try:
        browse.hive_sign_in(session, hive_site["url"], hive_site["username"], hive_site["password"])
        browse.run_step(session.page, "open", [hive_site["url"] + "/kanban/board"])
        assert session.page.url == hive_site["url"] + "/kanban/board"
    finally:
        session.close()


def test_hive_sign_in_with_a_wrong_password_says_so(hive_site):
    session = browse.start()
    try:
        with pytest.raises(RuntimeError, match="sign-in as browser-test failed"):
            browse.hive_sign_in(session, hive_site["url"], hive_site["username"], "wrong")
    finally:
        session.close()


@pytest.fixture
def visible_browser():
    """A separately running Chromium with a remote debugging port, standing in
    for the one in the hive-browser container."""
    port = free_port()
    with sync_playwright() as pw:
        exe = pw.chromium.executable_path
    profile = tempfile.mkdtemp()
    proc = subprocess.Popen([exe, "--headless=new", "--no-sandbox", f"--remote-debugging-port={port}",
                             f"--user-data-dir={profile}", "--no-first-run", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_http(f"http://127.0.0.1:{port}/json/version")
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(10)


def _pages(cdp):
    import json
    from urllib.request import urlopen
    return [t for t in json.load(urlopen(cdp + "/json/list")) if t["type"] == "page"]


def test_headed_mode_drives_a_tab_in_the_running_browser_and_keep_leaves_it_open(visible_browser, page_url):
    browse.main(["--headed", "--keep", "--cdp", visible_browser, "open", page_url])
    assert [t["url"] for t in _pages(visible_browser) if t["url"] == page_url] == [page_url]


def test_headed_mode_closes_its_tab_when_the_run_ends(visible_browser, page_url):
    before = len(_pages(visible_browser))
    browse.main(["--headed", "--cdp", visible_browser, "open", page_url])
    assert len(_pages(visible_browser)) == before


def test_a_headed_phone_tab_taps_with_a_finger(visible_browser, page_url):
    session = browse.start(phone=True, headed=True, cdp_url=visible_browser)
    try:
        browse.run_step(session.page, "open", [page_url])
        browse.run_step(session.page, "tap", ["#go"])
        assert browse.run_step(session.page, "text", []).splitlines()[-1] == "touch"
        assert session.page.evaluate("innerWidth") == 390
    finally:
        session.close()


def test_headed_mode_with_no_visible_browser_says_how_to_start_it():
    from conftest import free_port
    with pytest.raises(SystemExit, match="hive-browser container"):
        browse.start(headed=True, cdp_url=f"http://127.0.0.1:{free_port()}")


def test_the_visible_browser_is_addressed_by_ip_because_chromium_refuses_a_name():
    """Chromium's debugging port rejects a Host header that is a name, and the
    container is only known by its name, so the name is sent as its address."""
    import socket
    name = socket.gethostname()
    address = socket.gethostbyname(name)
    assert browse._by_address(f"http://{name}:9223") == f"http://{address}:9223"
