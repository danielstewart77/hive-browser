# A visible Chromium on a virtual screen, watchable through noVNC.
# Playwright's own image carries a Chromium and every library it needs, and
# pinning it to the Playwright that drives it keeps CDP versions in step.
FROM mcr.microsoft.com/playwright:v1.63.0-noble

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb fluxbox x11vnc novnc websockify socat supervisor fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/* \
    && printf '%s\n' '<!doctype html><meta http-equiv="refresh" content="0;url=vnc.html?autoconnect=1&resize=scale&reconnect=1&show_dot=1">' \
        > /usr/share/novnc/index.html

COPY supervisord.conf /etc/supervisor/conf.d/hive-browser.conf
COPY start-chromium.sh /usr/local/bin/start-chromium
# Chromium runs as the image's own unprivileged pwuser, never as root.
RUN chmod +x /usr/local/bin/start-chromium \
    && id pwuser \
    && mkdir -p /profile && chown pwuser:pwuser /profile

ENV DISPLAY=:99 SCREEN=1280x900x24
EXPOSE 6080 9223
CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
