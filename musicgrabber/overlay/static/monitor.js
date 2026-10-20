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
    let lastReviewShown = [];
    let msgTimer = null;
    let msgText = null;   // überlebt Poll-Re-Renders

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
            .mon-acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 5px; }
            .mon-act { cursor: pointer; border: 1px solid rgba(128,128,128,.4); background: transparent; color: inherit; border-radius: 6px; padding: 2px 10px; font-size: 12.5px; }
            .mon-act:hover { background: rgba(128,128,128,.18); }
            .mon-msg { border: 1px solid rgba(80,200,120,.5); border-radius: 10px; padding: 8px 14px; }
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
        const retry = (ing.counts || {}).network
            ? `<button class="mon-act" id="monRetry">🔁 ${ing.counts.network} Netz-Unit(s) erneut versuchen</button>`
            : "";
        return `<div class="mon-head"><span>${busy}</span>` +
            `<span>🗄 <b>${ing.total ?? 0}</b> Unit(s)</span>` +
            `<span>⏱ letzte Änderung ${esc(relAge(ing.last_change))}</span>` +
            `<span>${bl}</span>` +
            `<span><button class="mon-act" id="monIngest">🔄 Ingest jetzt</button> ${retry}</span></div>`;
    }

    function reviewHtml(review) {
        lastReviewShown = (review || []).slice(0, 20);
        if (!lastReviewShown.length) {
            return '<div class="mon-box"><h3>Review-Queue</h3>' +
                '<div class="mon-item">✅ nichts wartet</div></div>';
        }
        const items = lastReviewShown.map((u, i) => {
            const g = u.guessed || {};
            const label = [g.artist, g.album].filter(Boolean).join(" - ")
                || baseName(u.path);
            const cands = (u.candidates || []).map((c, ci) =>
                `<button class="mon-act" data-rev="${i}" data-dec="${ci ? "accept2" : "accept"}">K${ci + 1}: ${esc([c.artist, c.album].filter(Boolean).join(" - ") || c.source || "?")}${c.year ? " (" + c.year + ")" : ""}</button>`);
            return `<div class="mon-item">` +
                `<div>⚠️ <b>${esc(label)}</b> <span class="mon-mut">· ${u.n_files ?? "?"} Datei(en) · ${esc(relAge(u.updated))}${u.reason ? " · " + esc(String(u.reason).slice(0, 120)) : ""}</span></div>` +
                `<div class="mon-acts">${cands.join("")}` +
                `<button class="mon-act" data-rev="${i}" data-dec="asis">📦 As-is (eigene Tags)</button>` +
                `<button class="mon-act" data-rev="${i}" data-dec="override">✏️ Override…</button>` +
                `<button class="mon-act" data-rev="${i}" data-dec="ignore">🔇 Ignorieren</button>` +
                `</div></div>`;
        }).join("");
        const more = (review || []).length > 20
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

    function setMsg(msg) {
        msgText = msg;
        const el = document.getElementById("monitorMsg");
        if (!el) return;
        el.style.display = msg ? "" : "none";
        if (msg) el.textContent = msg;
        clearTimeout(msgTimer);
        if (msg) msgTimer = setTimeout(() => {
            msgText = null;
            el.style.display = "none";
        }, 8000);
    }

    async function postAction(payload) {
        try {
            const r = await fetch(apiUrl("/api/action"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const out = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(out.error || "HTTP " + r.status);
            rememberJob(out.queued);
            setMsg("✅ Auftrag " + (out.queued || "") +
                " angenommen — Ergebnis unten bei „Meine Aufträge“.");
            tick();
        } catch (e) {
            setError("Aktion fehlgeschlagen: " + e.message);
        }
    }

    function myJobs() {
        try {
            return JSON.parse(sessionStorage.getItem("monJobs") || "[]");
        } catch (e) {
            return [];
        }
    }

    function rememberJob(id) {
        if (!id) return;
        const jobs = myJobs().filter(j => j !== id);
        jobs.unshift(id);
        sessionStorage.setItem("monJobs", JSON.stringify(jobs.slice(0, 8)));
    }

    function myJobsHtml(jobsAll) {
        const ids = myJobs();
        if (!ids.length) return "";
        const byId = {};
        for (const j of (jobsAll || [])) byId[j.id] = j;
        const rows = ids.map(id => {
            const j = byId[id];
            if (!j) {
                return `<div class="mon-item mon-mut">⏳ ${esc(id)} ` +
                    "(wartet auf Ausführung…)</div>";
            }
            const icon = j.status === "done" ? "✅"
                : j.status === "error" ? "❌"
                    : j.status === "running" ? "🔄" : "⏳";
            const head = String(j.summary || j.text || "")
                .split("\n")[0].slice(0, 120);
            const age = j.created ? ` · ${esc(relAge(j.created))}` : "";
            return `<div class="mon-item">${icon} ${esc(head)}${age}</div>`;
        }).join("");
        return `<div class="mon-box"><h3>Meine Aufträge (diese Sitzung)</h3>${rows}</div>`;
    }

    function doReview(u, dec) {
        if (!u) return;
        const name = baseName(u.path);
        if (dec === "asis") {
            if (!confirm("As-is-Import auf die eigenen Tags? Schreibt die Bibliothek.\n" + name)) return;
            postAction({ action: "asis", unit_paths: [u.path] });
        } else if (dec === "ignore") {
            if (!confirm("Unit ignorieren (kein Import, reversibel über State)?\n" + name)) return;
            postAction({ action: "review", decisions: [{ unit_path: u.path, decision: "ignore" }] });
        } else if (dec === "override") {
            const spec = prompt("Override — Format: Artist|Album|MBID (Felder leer lassen = unverändert; MBID schlägt Suche)");
            if (spec === null) return;
            const parts = spec.split("|").map(s => s.trim());
            const artist = parts[0] || "", album = parts[1] || "", mbid = parts[2] || "";
            if (!artist && !album && !mbid) { alert("Override ohne Felder — abgebrochen."); return; }
            if (!confirm("Override-Import ausführen? Schreibt die Bibliothek.\n" + name)) return;
            postAction({ action: "review", decisions: [{ unit_path: u.path, decision: "override", override_artist: artist, override_album: album, override_mbid: mbid }] });
        } else { // accept / accept2
            if (!confirm("Mit diesem Kandidaten importieren? Schreibt die Bibliothek.\n" + name)) return;
            postAction({ action: "review", decisions: [{ unit_path: u.path, decision: dec }] });
        }
    }

    function render(snap) {
        const box = document.getElementById("monitorContent");
        if (!box) return;
        box.innerHTML =
            `<div class="mon-wrap">` +
            `<div id="monitorErr" class="mon-err" style="display:none"></div>` +
            `<div id="monitorMsg" class="mon-msg" style="display:${msgText ? "" : "none"}">${esc(msgText || "")}</div>` +
            myJobsHtml(snap.jobs_all) +
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
        box.querySelectorAll(".mon-act[data-rev]").forEach(b =>
            b.addEventListener("click", () =>
                doReview(lastReviewShown[Number(b.dataset.rev)], b.dataset.dec)));
        const ingest = document.getElementById("monIngest");
        if (ingest) ingest.addEventListener("click", () => {
            if (confirm("Ingest-Lauf jetzt anstoßen? (scannt Staging und importiert)")) postAction({ action: "ingest" });
        });
        const retry = document.getElementById("monRetry");
        if (retry) retry.addEventListener("click", () => {
            if (confirm("Alle Netzwerk-Units zurück auf pending setzen? Der nächste Ingest versucht sie erneut.")) postAction({ action: "retry" });
        });
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
