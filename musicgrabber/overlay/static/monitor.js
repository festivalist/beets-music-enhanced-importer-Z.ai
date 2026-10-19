// =============================================================================
// musik Import-Monitor (EPIC 9, Story 9.4 — Overlay-Tab, ADR-0001/0002)
// Read-only Blick auf den LAN-HTTP-Endpoint des musik-Bots (Default :8283):
// Laufstatus, Unit-Status + Filter, Review-Queue, _incoming-Stau, Bot-Jobs.
// Aktionen folgen mit Story 9.5. Bei Upstream-Bumps diese Datei UND die
// musik-monitor:begin/end-Blöcke in index.html/app.js neu einsetzen
// (Prozedur: overlay/README.md).
// =============================================================================
(function () {
    'use strict';

    const MONITOR_PORT = "8283";   // musik config: musik: bot_http: port
    const POLL_MS = 5000;
    const MAX_ROWS = 300;
    const STATUS_ORDER = ["review", "error", "network", "pending",
        "unmatched", "auto", "duplicate", "ignored"];
    const STATUS_LABELS = {
        auto: "auto", review: "Review", error: "Fehler", pending: "offen",
        unmatched: "unmatched", network: "Netz", duplicate: "Dubletten",
        ignored: "ignoriert"
    };

    let filter = null;
    let lastSnap = null;

    function apiUrl(path) {
        const u = new URL(path, location.origin);
        u.port = MONITOR_PORT;
        return u.toString();
    }

    function esc(s) {
        return String(s ?? "").replace(/[&<>"']/g, c => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;",
            '"': "&quot;", "'": "&#39;"
        }[c]));
    }

    function relAge(ts) {
        if (!ts) return "unbekannt";
        const d = Math.max(0, Date.now() / 1000 - ts);
        if (d < 90) return "gerade eben";
        if (d < 5400) return "vor " + Math.floor(d / 60) + " min";
        if (d < 172800) return "vor " + Math.floor(d / 3600) + " h";
        return "vor " + Math.floor(d / 86400) + " d";
    }

    function baseName(p) {
        const parts = String(p || "").split(/[\\/]/);
        return parts[parts.length - 1] || String(p || "?");
    }

    function injectStyle() {
        if (document.getElementById("monitorStyle")) return;
        const st = document.createElement("style");
        st.id = "monitorStyle";
        st.textContent = `
            #monitorTabContainer { overflow-y: auto; }
            .mon-wrap { font-size: 14px; display: flex; flex-direction: column; gap: 14px; max-width: 980px; }
            .mon-head { display: flex; flex-wrap: wrap; gap: 8px 22px; align-items: baseline; opacity: .92; }
            .mon-box, .mon-rev, .mon-err { border: 1px solid rgba(128,128,128,.35); border-radius: 10px; padding: 10px 14px; }
            .mon-rev { border-color: rgba(230,170,60,.55); }
            .mon-err { border-color: rgba(220,80,80,.6); }
            .mon-box h3, .mon-rev h3 { margin: 0 0 8px 0; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; opacity: .7; }
            .mon-chips { display: flex; flex-wrap: wrap; gap: 8px; }
            .mon-chip { cursor: pointer; border: 1px solid rgba(128,128,128,.4); background: transparent; color: inherit; border-radius: 999px; padding: 3px 12px; font-size: 13px; }
            .mon-chip-on { background: rgba(128,128,128,.25); font-weight: 600; }
            .mon-table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .mon-table th, .mon-table td { text-align: left; padding: 4px 8px; border-bottom: 1px solid rgba(128,128,128,.18); vertical-align: top; }
            .mon-table th { opacity: .65; font-weight: 600; }
            .mon-mut { opacity: .65; }
            .mon-item { padding: 3px 0; }
        `;
        document.head.appendChild(st);
    }

    function headHtml(ing, backlog) {
        const busy = ing.busy === true ? "🔄 Ingest <b>läuft</b>"
            : ing.busy === false ? "💤 Ingest idle"
                : "❓ Ingest-Status unbekannt (Windows-Dev oder kein Lock)";
        const bl = (backlog && backlog.audio_files != null)
            ? `📥 Stau: <b>${backlog.audio_files}</b> Datei(en)`
            : "📥 Stau: ?";
        return `<div class="mon-head"><span>${busy}</span>` +
            `<span>🗄 <b>${ing.total ?? 0}</b> Unit(s)</span>` +
            `<span>⏱ letzte Änderung ${esc(relAge(ing.last_change))}</span>` +
            `<span>${bl}</span></div>`;
    }

    function reviewHtml(review) {
        if (!review || !review.length) {
            return '<div class="mon-box"><h3>Review-Queue</h3>' +
                '<div class="mon-item">✅ nichts wartet</div></div>';
        }
        const items = review.slice(0, 20).map(u =>
            `<div class="mon-item">⚠️ ${esc(baseName(u.path))} <span class="mon-mut">· ${u.n_files ?? "?"} Datei(en) · ${esc(relAge(u.updated))}${u.reason ? " · " + esc(String(u.reason).slice(0, 120)) : ""}</span></div>`).join("");
        const more = review.length > 20
            ? `<div class="mon-item mon-mut">… und ${review.length - 20} weitere</div>` : "";
        return `<div class="mon-rev"><h3>⚠️ Review-Queue: ${review.length} Unit(s) warten auf eine Entscheidung</h3>${items}${more}</div>`;
    }

    function jobsHtml(jobs) {
        if (!jobs) return "";
        const parts = [];
        if (jobs.running_job) {
            parts.push(`<div class="mon-item">🔄 läuft: ${esc(String(jobs.running_job.text || "").slice(0, 100))}</div>`);
        } else {
            parts.push('<div class="mon-item">💤 keine Bot-Jobs aktiv</div>');
        }
        parts.push(`<div class="mon-item mon-mut">⏳ wartend: ${jobs.queued ?? 0}</div>`);
        for (const j of (jobs.recent || []).slice(0, 5)) {
            const icon = j.status === "done" ? "✅" : "❌";
            const head = String(j.summary || j.text || "").split("\n")[0].slice(0, 110);
            const age = j.finished ? ` · ${esc(relAge(j.finished))}` : "";
            parts.push(`<div class="mon-item mon-mut">${icon} ${esc(head)}${age}</div>`);
        }
        return `<div class="mon-box"><h3>Bot-Jobs (Telegram + Monitor)</h3>${parts.join("")}</div>`;
    }

    function unitsHtml(ing) {
        const counts = ing.counts || {};
        const chips = STATUS_ORDER.filter(s => counts[s]).map(s =>
            `<button class="mon-chip${filter === s ? " mon-chip-on" : ""}" data-st="${s}">${STATUS_LABELS[s] || s} ${counts[s]}</button>`).join("");
        let units = ing.units || [];
        if (filter) units = units.filter(u => u.status === filter);
        const rows = units.slice(0, MAX_ROWS).map(u =>
            `<tr><td title="${esc(u.path)}">${esc(baseName(u.path))}</td><td>${esc(STATUS_LABELS[u.status] || u.status)}</td><td>${esc(String(u.reason || "").slice(0, 120))}</td><td>${u.n_files ?? "?"}</td><td>${esc(relAge(u.updated))}</td></tr>`).join("");
        const hint = units.length > MAX_ROWS
            ? `<div class="mon-mut" style="margin-top:6px">… ${units.length - MAX_ROWS} weitere — Filter benutzen</div>` : "";
        return `<div class="mon-box"><h3>Units${filter ? ` — Filter: ${STATUS_LABELS[filter] || filter}` : ""}</h3>` +
            `<div class="mon-chips">${chips || '<span class="mon-mut">keine Units</span>'}</div>` +
            `<table class="mon-table" style="margin-top:8px"><thead><tr><th>Unit</th><th>Status</th><th>Grund</th><th>Dateien</th><th>geändert</th></tr></thead><tbody>${rows}</tbody></table>${hint}</div>`;
    }

    function setError(msg) {
        const el = document.getElementById("monitorErr");
        if (!el) return;
        el.style.display = msg ? "" : "none";
        if (msg) el.textContent = msg;
    }

    function render(snap) {
        const box = document.getElementById("monitorContent");
        if (!box) return;
        box.innerHTML =
            `<div class="mon-wrap">` +
            `<div id="monitorErr" class="mon-err" style="display:none"></div>` +
            headHtml(snap.ingest || {}, snap.backlog) +
            reviewHtml(snap.review) +
            jobsHtml(snap.jobs) +
            unitsHtml(snap.ingest || {}) +
            `</div>`;
        box.querySelectorAll(".mon-chip").forEach(ch =>
            ch.addEventListener("click", () => {
                filter = (filter === ch.dataset.st) ? null : ch.dataset.st;
                if (lastSnap) render(lastSnap);
            }));
    }

    async function tick() {
        try {
            const r = await fetch(apiUrl("/api/status"));
            if (!r.ok) throw new Error("HTTP " + r.status);
            lastSnap = await r.json();
            render(lastSnap);
            setError(null);
        } catch (e) {
            setError("Import-Monitor-Endpoint nicht erreichbar (" + e.message +
                ") — läuft der musik-Bot (bot_http, Port " + MONITOR_PORT + ")?");
        }
    }

    function start() {
        injectStyle();
        tick();
        setInterval(() => { if (!document.hidden) tick(); }, POLL_MS);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
