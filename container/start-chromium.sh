#!/bin/sh
# Chromium binds its debugging port to loopback only; socat (in supervisord)
# re-exposes it on 9223 inside the docker network. It is never published.
# Wait for the virtual screen rather than burning supervisord's retries.
i=0; while [ ! -e /tmp/.X11-unix/X99 ] && [ $i -lt 100 ]; do sleep 0.1; i=$((i+1)); done
exe=$(ls -d /ms-playwright/chromium-*/chrome-linux*/chrome | head -n1)
rm -f /profile/SingletonLock /profile/SingletonSocket /profile/SingletonCookie
exec "$exe" --no-sandbox --no-first-run --no-default-browser-check \
    --user-data-dir=/profile --remote-debugging-port=9222 \
    --start-maximized --window-position=0,0 --window-size=1280,900 \
    --disable-dev-shm-usage about:blank
