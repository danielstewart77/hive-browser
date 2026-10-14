# hive-browser

A real Chromium for minds. `browse.py` drives it: headless and private by
default, or `--headed` against the visible browser in `container/`, which
Daniel watches and can take over at browser.sparktobloom.com (noVNC behind
Cloudflare Access).

Cypher's skill for it lives at `minds/cypher/.dsh/skills/browse/SKILL.md` in
hive_mind. Board feature: "Cypher gets a browser".

## Run the visible browser

    docker compose -f container/compose.yaml up -d --build

noVNC is published on host port 8712 for Caddy. The CDP port is reachable
only on the `hivemind` network as `hive-browser:9223` and is never published.

## Tests

    python3 -m venv /tmp/hivevenv && /tmp/hivevenv/bin/pip install -r /mnt/dev/hive/requirements.txt
    HIVE_PYTHON=/tmp/hivevenv/bin/python /opt/venv/bin/python -m pytest

The hive sign-in tests start a real hive site from `HIVE_SRC`
(default /mnt/dev/hive/src) on a throwaway database.
