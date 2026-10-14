import os
import socket
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A page whose state changes only when its button is activated, and which
# reports the viewport it was rendered at.
PAGE = b"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body><button id="go" onpointerdown="document.getElementById('state').textContent=event.pointerType">Go</button>
<p id="state">idle</p><input id="name"></body></html>"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_http(url: str, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urlopen(url, timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"{url} never answered")


@pytest.fixture(scope="session")
def page_url():
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(PAGE)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@pytest.fixture(scope="session")
def hive_site(tmp_path_factory):
    """A real hive site on a throwaway database with one seeded user.

    It runs in the interpreter that has the hive's own dependencies
    (HIVE_PYTHON), which is not the one carrying Playwright."""
    src = Path(os.getenv("HIVE_SRC", "/mnt/dev/hive/src"))
    if not (src / "main.py").exists():
        pytest.skip(f"no hive checkout at {src}")
    port = free_port()
    env = dict(os.environ, HIVE_DB_PATH=str(tmp_path_factory.mktemp("hive") / "hive.db"),
               HIVE_SECRET_KEY="browse-test", HIVE_SEED_USERNAME="browser-test",
               HIVE_SEED_PASSWORD="correct horse", HIVE_HOST="127.0.0.1", HIVE_PORT=str(port),
               HIVE_COOKIE_DOMAIN="sparktobloom.com")
    proc = subprocess.Popen([os.getenv("HIVE_PYTHON", "python3"), "main.py"], cwd=src, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_http(f"http://127.0.0.1:{port}/login")
        yield {"url": f"http://127.0.0.1:{port}", "username": "browser-test", "password": "correct horse"}
    finally:
        proc.terminate()
        proc.wait(10)
