// =============================================================================
// musik Import-Monitor — Nav-Boot (Story 11.7)
// MG 4.4.1+ erzwingt eine CSP mit connect-src 'self' (HTTP-Header aus
// core/middleware.py — für das Static-Overlay nicht änderbar), womit der
// frühere integrierte Tab :8283 nicht mehr fetchen darf (stiller
// Leer-Tab, entdeckt 2026-11-13). Der Monitor lebt deshalb jetzt VOM
// BOT SELBST:  http://<host>:8283/monitor   (same-origin, musik/monitor.html)
// Diese Datei setzt nur noch den Öffnen-Link im Panel. Bei Upstream-Bumps
// bleiben die musik-monitor-Marker in index.html (3 Blöcke) und die 3
// Stellen in js/core.js bestehen — Prozedur: overlay/README.md.
// =============================================================================
(function () {
    'use strict';
    const a = document.getElementById("monitorOpenLink");
    if (a) a.href = location.protocol + "//" + location.hostname + ":8283/monitor";
})();
