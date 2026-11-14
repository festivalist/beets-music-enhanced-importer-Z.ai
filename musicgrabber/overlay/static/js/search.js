        // Tracks tab: search, live progress, results, artwork, explore similar,
        // source health, search history and the quality filter.

        let downloadingIds = new Set();
        let lastResults = [];
        let lastCompletedSearchQuery = '';
        let currentSearchToken = 0;
        let _searchProgressHideTimer = null;
        let _searchProgressRowTimers = [];
        let currentArtworkUrl = null;
        let currentArtworkArtist = null;
        let currentArtworkTitle = null;
        let currentSearchLogToken = null;
        let currentSource = 'all'; // Always search all sources
        // Source selector - restore saved preference and wire up clicks
        (function initSourceSelector() {
            const buttons = document.querySelectorAll('#sourceSelector .source-option');
            buttons.forEach(btn => {
                if (btn.dataset.source === currentSource) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
                btn.addEventListener('click', () => {
                    buttons.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentSource = btn.dataset.source;
                    localStorage.setItem(userStorageKey('searchSource'), currentSource);
                });
            });
        })();
        // Search history management
        function getSearchHistory() {
            const history = localStorage.getItem(userStorageKey('searchHistory'));
            return history ? JSON.parse(history) : [];
        }

        function saveSearchHistory(query) {
            let history = getSearchHistory();
            // Remove duplicates
            history = history.filter(q => q !== query);
            // Add to front
            history.unshift(query);
            // Keep last 10
            history = history.slice(0, 10);
            localStorage.setItem(userStorageKey('searchHistory'), JSON.stringify(history));
        }

        function showSearchHistory() {
            const history = getSearchHistory();
            if (history.length === 0) {
                searchHistory.classList.remove('show');
                return;
            }

            searchHistory.innerHTML = history.map(q => `
                <div class="history-item" data-query="${escapeHtml(q)}">
                    ${escapeHtml(q)}
                </div>
            `).join('');

            searchHistory.querySelectorAll('.history-item').forEach(item => {
                item.addEventListener('click', () => {
                    setSearchValue(item.dataset.query);
                    searchHistory.classList.remove('show');
                    search();
                });
            });

            searchHistory.classList.add('show');
        }

        function hideSearchHistory() {
            setTimeout(() => {
                searchHistory.classList.remove('show');
            }, 200);
        }

        // Search
        let lastSourceHealthToastAt = 0;
        let sourceHealthState = new Map();
        let sourceHealthPollTimer = null;
        function showUnavailableSourcesToast(sources) {
            if (!Array.isArray(sources) || sources.length === 0) return;
            const now = Date.now();
            if (now - lastSourceHealthToastAt < 30000) return;
            lastSourceHealthToastAt = now;
            const first = sources[0];
            const retryMs = first.retry_at ? Math.max(0, first.retry_at * 1000 - now) : 0;
            const retryText = retryMs ? `, retrying in ~${Math.max(1, Math.ceil(retryMs / 60000))} min` : '';
            const moreText = sources.length > 1 ? ` (+${sources.length - 1} more)` : '';
            showToast(`${first.label || first.id} unavailable${moreText}${retryText}`);
        }

        function sourceHealthTitle(source) {
            const checked = source.checked_at
                ? new Date(source.checked_at * 1000).toLocaleString()
                : 'not checked yet';
            if (source.healthy === null) return `${source.label}: checking`;
            if (source.available) return `${source.label}: available, checked ${checked}`;
            const reason = source.reason ? `, ${source.reason}` : '';
            const retry = source.retry_at
                ? `, retry after ${new Date(source.retry_at * 1000).toLocaleTimeString()}`
                : '';
            return `${source.label}: unavailable${reason}${retry}`;
        }

        // Short labels just for the Sources health strip - full names would wrap the
        // row. The tooltip (sourceHealthTitle) still carries the full name on hover.
        const SOURCE_HEALTH_SHORT_LABELS = {
            monochrome: 'MonoC',
            youtube: 'YT',
            soundcloud: 'SC',
            zvu4no: 'zvu4no',
            freemp3cloud: 'MP3C',
            jiosaavn: 'Saavn',
            soulseek: 'SLSK',
        };

        function renderSourceHealth(sources) {
            const strip = document.getElementById('sourceHealthStrip');
            if (!strip) return;
            const enabled = (sources || []).filter(source => source.enabled !== false);
            if (!enabled.length) {
                strip.style.display = 'none';
                strip.innerHTML = '';
                return;
            }
            const chips = enabled.map(source => {
                const stateClass = source.healthy === null
                    ? 'checking'
                    : (source.available ? 'healthy' : 'unavailable');
                const shortLabel = SOURCE_HEALTH_SHORT_LABELS[source.id] || source.label || source.id;
                return `<span class="source-health-chip ${stateClass}" title="${escapeAttr(sourceHealthTitle(source))}">
                    <span class="source-health-dot"></span>${escapeHtml(shortLabel)}
                </span>`;
            }).join('');
            const recheck = isAdmin()
                ? '<button type="button" class="source-health-recheck" id="sourceHealthRecheck">Re-check</button>'
                : '';
            strip.innerHTML = `<span class="source-health-label">Sources</span>${chips}${recheck}`;
            strip.style.display = 'flex';
            document.getElementById('sourceHealthRecheck')?.addEventListener('click', recheckSourceHealth);
        }

        async function loadSourceHealth(notifyTransitions = true) {
            try {
                const response = await apiFetch('/api/sources/health');
                if (!response.ok) return;
                const data = await response.json();
                const sources = Array.isArray(data.sources) ? data.sources : [];
                const newlyParked = notifyTransitions ? sources.filter(source => {
                    const previous = sourceHealthState.get(source.id);
                    return previous && previous.available !== false && source.available === false;
                }) : [];
                sourceHealthState = new Map(sources.map(source => [source.id, source]));
                renderSourceHealth(sources);
                showUnavailableSourcesToast(newlyParked);
                noticeNewBuild(data.build);
                noticeLibraryProblem(data.library);
            } catch {
                // Health is a useful hint, never a reason to break the search page.
            }
        }

        function startSourceHealthPolling() {
            if (sourceHealthPollTimer) clearInterval(sourceHealthPollTimer);
            loadSourceHealth(false);
            sourceHealthPollTimer = setInterval(() => loadSourceHealth(true), 30000);
        }

        async function recheckSourceHealth() {
            const button = document.getElementById('sourceHealthRecheck');
            if (button) {
                button.disabled = true;
                button.textContent = 'Checking…';
            }
            try {
                const response = await apiFetch('/api/sources/health/recheck', { method: 'POST' });
                if (!response.ok) throw new Error('Re-check failed');
                showToast('Source re-check started');
                setTimeout(() => loadSourceHealth(true), 1500);
                setTimeout(() => loadSourceHealth(true), 5000);
            } catch {
                showToast('Could not re-check sources', true);
            } finally {
                setTimeout(() => {
                    const current = document.getElementById('sourceHealthRecheck');
                    if (current) {
                        current.disabled = false;
                        current.textContent = 'Re-check';
                    }
                }, 1500);
            }
        }

        function clearDuplicateNotice() {
            const existing = document.getElementById('searchDuplicateNotice');
            if (existing) existing.remove();
        }

        function renderDuplicateNotice(notice) {
            clearDuplicateNotice();
            if (!notice || !notice.message) return;
            const sources = Array.isArray(notice.sources) ? notice.sources.map(s => s.source).filter(Boolean) : [];
            const sourceText = sources.length ? `Found via ${sources.map(escapeHtml).join(', ')}` : 'Already in your library';
            resultsTab.insertAdjacentHTML('afterbegin', `
                <div id="searchDuplicateNotice" class="search-duplicate-notice">
                    <i class="fa-solid fa-circle-info"></i>
                    <div>
                        <div class="search-duplicate-message">${escapeHtml(notice.message)}</div>
                        <div class="search-duplicate-source">${sourceText}</div>
                    </div>
                </div>
            `);
        }

        async function search() {
            if (searchBtn.disabled) return;
            const query = searchInput.value.trim();
            if (!query) return;

            // Links (playlists, albums, long videos worth splitting) belong in
            // Bulk Import, which already knows what to do with every URL shape
            // we support - send it there instead of searching Tracks for a URL.
            if (/^https?:\/\//i.test(query)) {
                searchInput.value = '';
                hideSearchHistory();
                document.querySelector('.tab[data-tab="bulk"]')?.click();
                spotifyUrlInput.value = query;
                await fetchSpotifyPlaylist();
                return;
            }

            const searchToken = ++currentSearchToken;
            currentSearchLogToken = null;
            lastCompletedSearchQuery = '';
            lastResults = [];

            // Save to history
            saveSearchHistory(query);
            hideSearchHistory();

            searchBtn.disabled = true;
            searchBtn.textContent = 'Searching…';
            resultsTab.innerHTML = `
                <div class="loading loading-with-copy" role="status">
                    <div class="spinner"></div>
                    <span>Warming up the search party…</span>
                </div>
            `;
            clearDuplicateNotice();
            relatedSuggestions.style.display = 'none';
            exploreBar.style.display = 'none';
            const _qualityRow = document.getElementById('qualityFilterRow');
            if (_qualityRow) _qualityRow.style.display = 'none';
            const _destRow1 = document.getElementById('destinationPickerRow');
            if (_destRow1) _destRow1.style.display = 'none';
            _exploreOriginalResults = null;
            _exploreResolvedResults = null;
            currentArtworkUrl = null;
            currentArtworkArtist = null;
            currentArtworkTitle = null;
            stopPreview(); // Stop any playing preview

            try {
                await runSearchStream(query, searchToken);
                if (searchToken === currentSearchToken) lastCompletedSearchQuery = query;
            } catch (error) {
                if (searchToken !== currentSearchToken) return;
                // Streaming hiccup: fall back to the plain blocking search so the
                // user never ends up worse off than before we had a stream.
                console.log('search stream failed, falling back to blocking:', error);
                hideSearchProgress();
                try {
                    await runSearchBlocking(query, searchToken);
                    if (searchToken === currentSearchToken) lastCompletedSearchQuery = query;
                } catch (err2) {
                    if (searchToken !== currentSearchToken) return;
                    resultsTab.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon"><i class="fa-solid fa-circle-exclamation"></i></div>
                            <p>Search failed. Try again.</p>
                        </div>
                    `;
                    showToast('Search failed', true);
                }
            } finally {
                if (searchToken === currentSearchToken) {
                    searchBtn.disabled = false;
                    searchBtn.textContent = 'Search';
                }
            }
        }

        // Streaming search: consume the NDJSON event stream and render results
        // progressively as each source lands, ticking off the source status panel.
        async function runSearchStream(query, searchToken) {
            const accumulator = [];
            let albumSuggestion = null;
            let renderedOnce = false;

            initSearchProgress();

            const response = await apiFetch('/api/search/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, limit: 15, source: currentSource })
            });
            if (!response.ok || !response.body) throw new Error('stream unavailable');

            // Artwork only needs the query, so kick it off straight away.
            const artworkParsed = parseArtistTitle(query);
            if (artworkParsed) fetchAndApplyArtwork(artworkParsed.artist, artworkParsed.title, searchToken);

            function handleEvent(ev) {
                if (searchToken !== currentSearchToken) return;
                switch (ev.type) {
                    case 'start':
                        renderSearchProgressRows(ev.sources || []);
                        break;
                    case 'source':
                        updateSourceStatus(ev.source, ev.status, ev.count);
                        if (ev.status === 'done' && ev.results && ev.results.length) {
                            accumulator.push(...ev.results);
                            accumulator.sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
                            renderResults(accumulator);
                            renderedOnce = true;
                            // Re-render wipes thumbnails, so re-apply any fetched artwork.
                            if (currentArtworkUrl && currentArtworkArtist && currentArtworkTitle) {
                                applyArtworkToResults(currentArtworkArtist, currentArtworkTitle, currentArtworkUrl);
                            }
                        }
                        break;
                    case 'rescore': {
                        // MusicBrainz answered after the quick sources had landed;
                        // move their cards to where the duration check puts them.
                        const scores = new Map((ev.results || []).map(r => [`${r.source}:${r.video_id}`, r.relevance_score]));
                        let moved = false;
                        for (const r of accumulator) {
                            const score = scores.get(`${r.source}:${r.video_id}`);
                            if (score !== undefined) { r.relevance_score = score; moved = true; }
                        }
                        if (moved) {
                            accumulator.sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
                            renderResults(accumulator);
                            if (currentArtworkUrl && currentArtworkArtist && currentArtworkTitle) {
                                applyArtworkToResults(currentArtworkArtist, currentArtworkTitle, currentArtworkUrl);
                            }
                        }
                        break;
                    }
                    case 'album_suggestion':
                        albumSuggestion = ev;
                        break;
                    case 'done':
                        currentSearchLogToken = ev.search_token || null;
                        showUnavailableSourcesToast(ev.unavailable_sources);
                        if (!renderedOnce) renderResults(accumulator); // shows the empty state
                        renderDuplicateNotice(ev.duplicate_notice);
                        showRelatedSuggestions(accumulator, albumSuggestion);
                        fetchAlbumArtwork(accumulator, searchToken);
                        finishSearchProgress();
                        break;
                    case 'error':
                        if (!renderedOnce) throw new Error(ev.detail || 'search failed');
                        finishSearchProgress();
                        break;
                }
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                if (searchToken !== currentSearchToken) { try { reader.cancel(); } catch (e) {} return; }
                buffer += decoder.decode(value, { stream: true });
                let nl;
                while ((nl = buffer.indexOf('\n')) >= 0) {
                    const line = buffer.slice(0, nl).trim();
                    buffer = buffer.slice(nl + 1);
                    if (!line) continue;
                    let ev;
                    try { ev = JSON.parse(line); } catch (e) { continue; }
                    handleEvent(ev);
                }
            }
            const tail = buffer.trim();
            if (tail) { try { handleEvent(JSON.parse(tail)); } catch (e) {} }
        }

        // Plain blocking search, kept as a fallback for when the stream falls over.
        async function runSearchBlocking(query, searchToken) {
            const response = await apiFetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, limit: 15, source: currentSource })
            });
            if (!response.ok) throw new Error('Search failed');

            const data = await response.json();
            if (searchToken !== currentSearchToken) return;
            lastResults = data.results;
            currentSearchLogToken = data.search_token || null;
            showUnavailableSourcesToast(data.unavailable_sources);
            renderResults(data.results);
            renderDuplicateNotice(data.duplicate_notice);
            showRelatedSuggestions(data.results, data.album_suggestion);

            const artworkParsed = parseArtistTitle(query);
            if (artworkParsed) {
                fetchAndApplyArtwork(artworkParsed.artist, artworkParsed.title, searchToken);
            }
            fetchAlbumArtwork(data.results, searchToken);
        }

        // ----- Live search progress panel -----
        // Quip pools live in static/quips.js (global SEARCH_QUIPS), sectioned per
        // source plus the funny-failure sections. Each row fades away on its own a
        // moment after it reports in, so the panel empties itself as sources land.

        function _randomQuip(list, fallback) {
            if (!Array.isArray(list) || !list.length) return fallback;
            return list[Math.floor(Math.random() * list.length)];
        }

        function _searchingQuip(source) {
            const s = (typeof SEARCH_QUIPS !== 'undefined' && SEARCH_QUIPS.searching) || null;
            const pool = s && (s[source] || s._default);
            return _randomQuip(pool, 'Having a rummage');
        }

        function _failureQuip(section, fallback) {
            const pool = (typeof SEARCH_QUIPS !== 'undefined' && SEARCH_QUIPS[section]) || null;
            return _randomQuip(pool, fallback);
        }

        function _slowQuip(source) {
            const s = (typeof SEARCH_QUIPS !== 'undefined' && SEARCH_QUIPS.slow) || null;
            const pool = s && (s[source] || s._default);
            return _randomQuip(pool, 'Still going, hang on');
        }

        // One dig at MusicBrainz's expense per Albums-browser loading state. No
        // queue-style rotation here: a single lookup has no state changes to key
        // a swap off, so we just pick once and let it stand.
        function _musicbrainzQuip() {
            return _randomQuip(typeof MUSICBRAINZ_QUIPS !== 'undefined' ? MUSICBRAINZ_QUIPS : null, 'Loading');
        }

        // If a source is still searching long after its mates finished, swap its
        // line for a "taking a while" quip (Soulseek's retry is the usual culprit).
        function _startRowSlowTimer(source) {
            const t = setTimeout(() => {
                const panel = document.getElementById('searchProgress');
                if (!panel) return;
                const row = panel.querySelector(`.search-progress-row[data-source="${CSS.escape(source)}"]`);
                if (!row || row.dataset.status !== 'searching') return;
                const text = row.querySelector('.search-progress-status');
                if (text) text.textContent = _slowQuip(source) + '…';
            }, 9000);
            _searchProgressRowTimers.push(t);
        }

        function _clearProgressRowTimers() {
            _searchProgressRowTimers.forEach(t => clearTimeout(t));
            _searchProgressRowTimers = [];
        }

        function initSearchProgress() {
            const panel = document.getElementById('searchProgress');
            if (!panel) return;
            if (_searchProgressHideTimer) { clearTimeout(_searchProgressHideTimer); _searchProgressHideTimer = null; }
            _clearProgressRowTimers();
            panel.classList.remove('search-progress-fading');
            panel.innerHTML = '';
            panel.style.display = '';
        }

        function _progressRowHtml(src) {
            return `
                <div class="search-progress-row" data-source="${escapeHtml(src)}" data-status="searching">
                    <span class="search-progress-icon"><span class="watched-refresh-spinner"></span></span>
                    <span class="search-progress-name">${escapeHtml(getSourceLabel(src))}</span>
                    <span class="search-progress-status">${escapeHtml(_searchingQuip(src))}&hellip;</span>
                </div>
            `;
        }

        function renderSearchProgressRows(sources) {
            const panel = document.getElementById('searchProgress');
            if (!panel) return;
            panel.innerHTML = sources.map(_progressRowHtml).join('');
            panel.style.display = sources.length ? '' : 'none';
            sources.forEach(_startRowSlowTimer);
        }

        function updateSourceStatus(source, status, count) {
            const panel = document.getElementById('searchProgress');
            if (!panel) return;
            let row = panel.querySelector(`.search-progress-row[data-source="${CSS.escape(source)}"]`);
            if (!row) {
                // A status turned up for a source we never listed (e.g. a parked
                // source skipped before its row existed). Make one so it's still seen.
                panel.insertAdjacentHTML('beforeend', _progressRowHtml(source));
                panel.style.display = '';
                row = panel.querySelector(`.search-progress-row[data-source="${CSS.escape(source)}"]`);
                if (!row) return;
            }
            row.dataset.status = status;
            const icon = row.querySelector('.search-progress-icon');
            const text = row.querySelector('.search-progress-status');
            if (status === 'done') {
                icon.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
                if (count) {
                    text.textContent = `${count} result${count === 1 ? '' : 's'}`;
                } else {
                    // Soulseek gets its own "soulless" line; everyone else the generic empty pool.
                    text.textContent = source === 'soulseek'
                        ? _failureQuip('soulless', 'no souls found')
                        : _failureQuip('empty', 'nothing here');
                }
            } else if (status === 'timeout') {
                icon.innerHTML = '<i class="fa-solid fa-hourglass-end"></i>';
                text.innerHTML = `${escapeHtml(_failureQuip('timeout', 'took too long, moved on'))}<button type="button" class="search-source-retry">Retry this source</button>`;
                text.querySelector('.search-source-retry')?.addEventListener('click', () => retrySearchSource(source, row));
            } else if (status === 'skipped') {
                icon.innerHTML = '<i class="fa-solid fa-circle-minus"></i>';
                text.textContent = _failureQuip('offline', 'offline, skipped');
            } else if (status === 'error') {
                icon.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
                text.innerHTML = `${escapeHtml(_failureQuip('error', 'had a wobble'))}<button type="button" class="search-source-retry">Retry this source</button>`;
                text.querySelector('.search-source-retry')?.addEventListener('click', () => retrySearchSource(source, row));
            }
            if (status !== 'timeout' && status !== 'error') _fadeOutRow(row);
        }

        async function retrySearchSource(source, row) {
            const query = searchInput.value.trim();
            if (!query || !row) return;
            const searchToken = currentSearchToken;
            row.classList.remove('search-progress-row-fading');
            row.dataset.status = 'searching';
            const icon = row.querySelector('.search-progress-icon');
            const text = row.querySelector('.search-progress-status');
            if (icon) icon.innerHTML = '<span class="watched-refresh-spinner"></span>';
            if (text) text.textContent = `${_searchingQuip(source)}…`;
            try {
                const response = await apiFetch('/api/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, limit: 15, source })
                });
                if (!response.ok) throw new Error('retry failed');
                const data = await response.json();
                if (searchToken !== currentSearchToken) return;
                const merged = [...lastResults];
                const seen = new Set(merged.map(result => `${result.source}:${result.video_id}`));
                for (const result of data.results || []) {
                    const key = `${result.source}:${result.video_id}`;
                    if (!seen.has(key)) {
                        seen.add(key);
                        merged.push(result);
                    }
                }
                merged.sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
                renderResults(merged);
                updateSourceStatus(source, 'done', (data.results || []).length);
                if (currentArtworkUrl && currentArtworkArtist && currentArtworkTitle) {
                    applyArtworkToResults(currentArtworkArtist, currentArtworkTitle, currentArtworkUrl);
                }
            } catch {
                if (searchToken === currentSearchToken) updateSourceStatus(source, 'error');
            }
        }

        function _fadeOutRow(row) {
            // Hold the final status on screen for a good while so it's easy to read
            // (success or failure alike), then drift it away on a gentle fade.
            const hold = setTimeout(() => {
                row.classList.add('search-progress-row-fading');
                const drop = setTimeout(() => {
                    row.remove();
                    const panel = document.getElementById('searchProgress');
                    if (panel && !panel.querySelector('.search-progress-row')) hideSearchProgress();
                }, 1300);
                _searchProgressRowTimers.push(drop);
            }, 3600);
            _searchProgressRowTimers.push(hold);
        }

        function finishSearchProgress() {
            // Rows fade out individually as they finish, so this is just a safety net:
            // if anything's still hanging about after a while, clear the panel.
            const panel = document.getElementById('searchProgress');
            if (!panel) return;
            if (_searchProgressHideTimer) clearTimeout(_searchProgressHideTimer);
            _searchProgressHideTimer = setTimeout(() => {
                if (!panel.querySelector('.search-progress-row')) hideSearchProgress();
            }, 8000);
        }

        function hideSearchProgress() {
            const panel = document.getElementById('searchProgress');
            if (!panel) return;
            if (_searchProgressHideTimer) { clearTimeout(_searchProgressHideTimer); _searchProgressHideTimer = null; }
            _clearProgressRowTimers();
            panel.classList.remove('search-progress-fading');
            panel.style.display = 'none';
            panel.innerHTML = '';
        }

        function parseArtistTitle(query) {
            const match = query.match(/^(.+?)\s+-\s+(.+)$/);
            if (!match) return null;
            return { artist: match[1].trim(), title: match[2].trim() };
        }

        async function fetchAndApplyArtwork(artist, title, searchToken) {
            try {
                const resp = await apiFetch(
                    `/api/search/artwork?artist=${encodeURIComponent(artist)}&title=${encodeURIComponent(title)}`
                );
                if (!resp.ok || searchToken !== currentSearchToken) return;
                const data = await resp.json();
                if (!data.url) return;
                currentArtworkUrl = data.url;
                currentArtworkArtist = artist;
                currentArtworkTitle = title;
                applyArtworkToResults(artist, title, data.url);
            } catch (e) {
                // Artwork is purely cosmetic, never fail the search over it
            }
        }

        function applyArtworkToResults(queryArtist, queryTitle, artworkUrl) {
            const norm = s => s.toLowerCase().replace(/[^a-z0-9\s]/g, '').replace(/\s+/g, ' ').trim();
            const normArtist = norm(queryArtist);
            const normTitle = norm(queryTitle);

            resultsTab.querySelectorAll('.result-item').forEach((item, index) => {
                const result = lastResults[index];
                if (!result) return;

                // Only fill in blank placeholders, leave source thumbnails alone
                const thumb = item.querySelector('.result-thumb');
                if (!thumb || thumb.tagName === 'IMG') return;

                const resultArtist = norm(result.artist || result.channel || '');
                const resultTitle = norm(result.title || '');
                const artistMatch = resultArtist.includes(normArtist) || normArtist.includes(resultArtist);
                const titleMatch = resultTitle.includes(normTitle) || normTitle.includes(resultTitle);

                if (artistMatch && titleMatch) {
                    // Marked as the query-level guess so a per-album cover, which
                    // knows more, is allowed to overrule it later.
                    thumb.replaceWith(_artworkImage(artworkUrl, 'is-query-art'));
                }
            });
        }

        function _artworkImage(url, extraClass) {
            const img = document.createElement('img');
            img.className = `result-thumb has-artwork${extraClass ? ' ' + extraClass : ''}`;
            img.src = url;
            img.alt = '';
            img.loading = 'lazy';
            return img;
        }

        // ----- Per-album cover art -----
        // slskd has no idea what a cover is, but the shared file's own path usually
        // names the album, so one lookup covers every result from the same record.
        // Cached for the session: search the same album twice and it costs nothing.
        const ALBUM_ARTWORK_MAX_LOOKUPS = 8;
        const albumArtworkCache = new Map();

        function albumArtworkKey(artist, album) {
            return `${(artist || '').toLowerCase().trim()}|${(album || '').toLowerCase().trim()}`;
        }

        function applyCachedAlbumArtwork() {
            resultsTab.querySelectorAll('.result-item').forEach(item => {
                const result = lastResults[parseInt(item.dataset.index)];
                if (!result || !result.artist || !result.album) return;

                const url = albumArtworkCache.get(albumArtworkKey(result.artist, result.album));
                if (!url) return;

                const thumb = item.querySelector('.result-thumb');
                if (!thumb) return;
                // Fill blanks, and overrule the query-level guess, but never touch a
                // thumbnail the source itself provided.
                if (thumb.tagName === 'IMG' && !thumb.classList.contains('is-query-art')) return;
                thumb.replaceWith(_artworkImage(url));
            });
        }

        async function fetchAlbumArtwork(results, searchToken) {
            const wanted = new Map();
            (results || []).forEach(r => {
                if (!r.artist || !r.album || r.thumbnail) return;
                const key = albumArtworkKey(r.artist, r.album);
                if (albumArtworkCache.has(key) || wanted.has(key)) return;
                wanted.set(key, { artist: r.artist, album: r.album });
            });
            if (!wanted.size) return;

            const lookups = [...wanted.entries()].slice(0, ALBUM_ARTWORK_MAX_LOOKUPS);
            await Promise.all(lookups.map(async ([key, { artist, album }]) => {
                try {
                    const resp = await apiFetch(
                        `/api/search/artwork?artist=${encodeURIComponent(artist)}&album=${encodeURIComponent(album)}`
                    );
                    if (!resp.ok) return;
                    const data = await resp.json();
                    if (data.url) albumArtworkCache.set(key, data.url);
                } catch (e) {
                    // Covers are decoration; a missing one never fails a search
                }
            }));

            if (searchToken === currentSearchToken) applyCachedAlbumArtwork();
        }

        // ----- Album browser cover art (Albums tab / Bulk Import artist view) -----
        // Same cache and courtesy cap as the search-result covers above, just aimed
        // at a discography list instead of a page of search hits. A prolific artist
        // can easily clear ALBUM_ARTWORK_MAX_LOOKUPS, so this works through the list
        // in batches rather than giving up after the first one.
        function _albumListThumbImage(url) {
            const img = document.createElement('img');
            img.className = 'album-list-thumb has-artwork';
            img.src = url;
            img.alt = '';
            img.loading = 'lazy';
            return img;
        }

        async function fetchAlbumListArtwork(targets, artistName) {
            if (!artistName || !targets || !targets.length) return;

            const lookups = [];
            for (const t of targets) {
                if (!t.title) continue;
                const key = albumArtworkKey(artistName, t.title);
                const cached = albumArtworkCache.get(key);
                if (cached) {
                    if (t.thumbEl && t.thumbEl.isConnected) t.thumbEl.replaceWith(_albumListThumbImage(cached));
                    continue;
                }
                lookups.push({ thumbEl: t.thumbEl, title: t.title, key });
            }

            for (let i = 0; i < lookups.length; i += ALBUM_ARTWORK_MAX_LOOKUPS) {
                const batch = lookups.slice(i, i + ALBUM_ARTWORK_MAX_LOOKUPS);
                await Promise.all(batch.map(async ({ thumbEl, title, key }) => {
                    try {
                        const resp = await apiFetch(
                            `/api/search/artwork?artist=${encodeURIComponent(artistName)}&album=${encodeURIComponent(title)}`
                        );
                        if (!resp.ok) return;
                        const data = await resp.json();
                        if (!data.url) return;
                        albumArtworkCache.set(key, data.url);
                        // The row may have been rebuilt (new artist picked, list
                        // reloaded) while this was in flight; a detached element
                        // just quietly drops the swap.
                        if (thumbEl && thumbEl.isConnected) thumbEl.replaceWith(_albumListThumbImage(data.url));
                    } catch (e) {
                        // Covers are decoration; a missing one never blocks the album list
                    }
                }));
            }
        }

        // Show related search suggestions based on artists, plus album suggestion if available
        function showRelatedSuggestions(results, albumSuggestion) {
            if (!results || results.length === 0) return;

            // Extract unique artists, falling back to the uploader only where there is
            // no artist at all. Soulseek usernames make for hopeless search suggestions:
            // nobody has ever wanted to see more tracks by "2jqll9htuy62asp1wu".
            const artists = [...new Set(
                results
                    .map(r => (r.source === 'soulseek' ? r.artist : (r.artist || r.channel)))
                    .map(name => (name || '').trim())
                    .filter(Boolean)
            )].slice(0, 5);

            if (artists.length === 0 && !albumSuggestion) return;

            // Album suggestion section (shown first when the backend found a matching album)
            let albumHtml = '';
            if (albumSuggestion) {
                albumHtml = `
                    <div class="related-title">Artist and Album</div>
                    <div class="suggestion-chips">
                        <button class="suggestion-chip album-suggestion-chip"
                            data-artist="${escapeAttr(albumSuggestion.artist_name)}"
                            data-artist-mbid="${escapeAttr(albumSuggestion.artist_mbid)}"
                            data-album="${escapeAttr(albumSuggestion.album_title)}"
                            data-release-mbid="${escapeAttr(albumSuggestion.release_mbid)}">
                            <i class="fa-solid fa-compact-disc"></i> ${escapeHtml(albumSuggestion.artist_name)} \u2013 ${escapeHtml(albumSuggestion.album_title)}
                        </button>
                    </div>
                `;
            }

            let artistHtml = '';
            if (artists.length > 0) {
                artistHtml = `
                    <div class="related-title">Related searches</div>
                    <div class="suggestion-chips">
                        ${artists.map(artist => `
                            <button class="suggestion-chip" data-query="${escapeHtml(artist)}">
                                ${escapeHtml(artist)}
                            </button>
                        `).join('')}
                    </div>
                `;
            }

            relatedSuggestions.innerHTML = `<div class="related-suggestions">${albumHtml}${artistHtml}</div>`;

            // Wire artist chip click handlers
            relatedSuggestions.querySelectorAll('.suggestion-chip:not(.album-suggestion-chip)').forEach(chip => {
                chip.addEventListener('click', () => {
                    setSearchValue(chip.dataset.query);
                    search();
                });
            });

            // Wire album suggestion chip click handler
            const albumChip = relatedSuggestions.querySelector('.album-suggestion-chip');
            if (albumChip) {
                albumChip.addEventListener('click', () => {
                    openAlbumFromSearch({
                        artistName: albumChip.dataset.artist,
                        albumTitle: albumChip.dataset.album,
                        artistMbid: albumChip.dataset.artistMbid,
                        releaseMbid: albumChip.dataset.releaseMbid,
                    });
                });
            }

            relatedSuggestions.style.display = 'block';
        }

        // -----------------------------------------------------------------------
        // Explore similar artists via ListenBrainz
        // -----------------------------------------------------------------------

        let _exploreOriginalResults = null;  // stash so Back restores them
        let _exploreResolvedResults = null;  // the actual search results from the explore run

        const exploreBar = document.getElementById('exploreBar');

        async function exploreSimilar(artist) {
            if (!artist) return;
            stopPreview();

            // The search that put these results on screen may still be streaming
            // (Soulseek takes its sweet time), and its later source events would
            // cheerfully re-render the original query straight over the top of
            // our similar-artist results. Bumping the token retires it exactly
            // as starting a new search would: the stream, its per-source retries
            // and the artwork fetches all check this before touching the DOM.
            const runToken = ++currentSearchToken;
            hideSearchProgress();

            // Stash current results so "Back" can restore them
            _exploreOriginalResults = lastResults ? [...lastResults] : [];

            // Show the explore bar with a loading state
            _showExploreBar(artist, null);

            // Show a spinner in results while we fetch
            resultsTab.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            relatedSuggestions.style.display = 'none';

            let tracks;
            const MAX_RETRIES = 3;
            const RETRY_DELAY_MS = 1500;
            let lastError;
            for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
                if (attempt > 0) await new Promise(r => setTimeout(r, RETRY_DELAY_MS));
                try {
                    const resp = await apiFetch('/api/explore/similar', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ artist, mode: 'easy', limit: 25 })
                    });
                    if (!resp.ok) throw new Error('Could not reach similar-artists service');
                    const data = await resp.json();
                    tracks = data.artists || [];
                    lastError = null;
                    break;
                } catch (e) {
                    lastError = e;
                }
            }
            if (runToken !== currentSearchToken) return;  // user moved on
            if (lastError) {
                resultsTab.innerHTML = `<div class="empty-state"><p>Could not load similar artists: ${escapeHtml(lastError.message)}</p></div>`;
                return;
            }

            if (!tracks.length) {
                resultsTab.innerHTML = `<div class="empty-state"><p>No similar artists found for "${escapeHtml(artist)}"</p></div>`;
                return;
            }

            // Update bar now we know the count
            _showExploreBar(artist, tracks);

            // Search each similar artist in parallel (batches of 5) and render as results arrive
            resultsTab.innerHTML = '';
            const exploreResults = [];

            async function searchOne(track) {
                // track is {artist} - search by artist name to get their top result
                const query = track.artist;
                try {
                    const resp = await apiFetch('/api/search', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ query, limit: 1, source: currentSource })
                    });
                    if (!resp.ok) return null;
                    const data = await resp.json();
                    return data.results && data.results[0] ? data.results[0] : null;
                } catch { return null; }
            }

            // Batch into groups of 5 to avoid hammering the backend
            for (let i = 0; i < tracks.length; i += 5) {
                const batch = tracks.slice(i, i + 5);
                const batchResults = await Promise.all(batch.map(searchOne));
                if (runToken !== currentSearchToken) return;  // a new search (or explore) owns the pane now
                batchResults.forEach(r => {
                    if (r) {
                        exploreResults.push(r);
                        // Render incrementally - append each card as it arrives
                        const tmp = document.createElement('div');
                        tmp.innerHTML = _renderOneResult(r, exploreResults.length - 1);
                        const item = tmp.firstElementChild;
                        resultsTab.appendChild(item);
                        _attachResultHandlers(item, r, exploreResults.length - 1);
                    }
                });
            }

            // Update lastResults so individual downloads work, and stash for Download All
            lastResults = exploreResults;
            _exploreResolvedResults = exploreResults;
            applyQualityFilter();

            // All batches done - enable the Download All button now it has real data
            const dlBtn = document.getElementById('exploreDownloadAllBtn');
            if (dlBtn) { dlBtn.disabled = false; dlBtn.textContent = 'Download All'; }

            if (!exploreResults.length) {
                resultsTab.innerHTML = `<div class="empty-state"><p>Couldn't find playable tracks for similar artists</p></div>`;
            }
        }

        function _showExploreBar(artist, tracks) {
            const trackCount = tracks ? tracks.length : null;
            const countText = trackCount ? ` (${trackCount} similar artists)` : '';
            exploreBar.innerHTML = `
                <div class="explore-bar">
                    <span class="explore-bar-label">~ Similar to <strong>${escapeHtml(artist)}</strong>${escapeHtml(countText)}</span>
                    <div class="explore-bar-actions">
                        ${tracks ? `
                            <label class="explore-playlist-label">
                                <input type="checkbox" id="explorePlaylistCheckbox" checked>
                                <span>Save as playlist</span>
                            </label>
                            <button class="explore-download-all-btn" id="exploreDownloadAllBtn" disabled>Loading...</button>
                        ` : ''}
                        <button class="explore-back-btn" id="exploreBackBtn">&#x2715; Back</button>
                    </div>
                </div>
            `;
            exploreBar.style.display = 'block';

            document.getElementById('exploreBackBtn').addEventListener('click', () => {
                exploreBar.style.display = 'none';
                stopPreview();
                if (_exploreOriginalResults) {
                    renderResults(_exploreOriginalResults);
                    showRelatedSuggestions(_exploreOriginalResults);
                }
                _exploreOriginalResults = null;
                _exploreResolvedResults = null;
            });

            const dlAllBtn = document.getElementById('exploreDownloadAllBtn');
            if (dlAllBtn && tracks) {
                dlAllBtn.addEventListener('click', () => _exploreDownloadAll(artist, tracks));
            }
        }

        async function _exploreDownloadAll(artist, tracks) {
            const dlAllBtn = document.getElementById('exploreDownloadAllBtn');
            if (dlAllBtn) { dlAllBtn.disabled = true; dlAllBtn.textContent = 'Queuing...'; }

            // Use the dedicated explore results (not lastResults, which may still hold the original search).
            const resolvedResults = _exploreResolvedResults && _exploreResolvedResults.length ? _exploreResolvedResults : null;
            let songs;
            if (resolvedResults) {
                songs = resolvedResults.map(r => {
                    const a = (r.artist || r.channel || '').trim();
                    const t = (r.title || '').trim();
                    return a && t ? `${a} - ${t}` : (a || t);
                }).filter(Boolean).join('\n');
            } else {
                songs = tracks.map(t => `${t.artist} - top track`).join('\n');
            }
            const now = new Date();
            const dateSuffix = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
            const playlistName = `Similar to ${artist} (${dateSuffix})`;
            const makePlaylist = document.getElementById('explorePlaylistCheckbox')?.checked ?? true;

            const requestBody = { songs, convert_audio: true };
            if (makePlaylist) {
                requestBody.create_playlist = true;
                requestBody.playlist_name = playlistName;
                requestBody.use_playlists_dir = true;
            }

            try {
                const resp = await apiFetch('/api/bulk-import-async', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });
                if (!resp.ok) throw new Error('Bulk import failed');
                if (dlAllBtn) { dlAllBtn.textContent = 'Queued!'; }
                // Switch to the Queue tab so they can watch progress
                setTimeout(() => {
                    document.querySelector('[data-tab="queue"]')?.click();
                    document.querySelector('#queueModePills .pill[data-value="queue"]')?.click();
                }, 800);
            } catch (e) {
                if (dlAllBtn) { dlAllBtn.disabled = false; dlAllBtn.textContent = 'Download All'; }
                showToast(`Could not queue downloads: ${e.message}`, true);
            }
        }

        // ---------------------------------------------------------------
        // Minimum-quality filter
        //
        // Only Soulseek, Monochrome, FreeMp3Cloud and JioSaavn declare a quality before
        // download; YouTube and SoundCloud say nothing at all, so they arrive as
        // tier 0 ("undeclared"). Asking for "Lossless only" and still being handed
        // a YouTube rip is not what anybody meant, so undeclared results are hidden
        // once a minimum is set. "Keep undeclared" brings them back for anyone who
        // wants the safety net. With the filter on "Any quality" nothing is hidden.
        //
        // Worth knowing: the list is ordered by relevance_score (title/artist match,
        // views, duration and source bonus), not by audio quality. YouTube
        // tends to top it because it has the exact title, which is precisely why an
        // undeclared result could otherwise sit above real lossless ones.
        //
        // Filtering hides cards rather than removing them, because every download
        // and preview handler is bound to the result's index in lastResults.
        // Re-indexing a filtered list is exactly the kind of clever that ends up
        // downloading the wrong song.
        // ---------------------------------------------------------------
        function applyQualityFilter() {
            const row = document.getElementById('qualityFilterRow');
            const select = document.getElementById('qualityFilterSelect');
            const keepUnknownEl = document.getElementById('qualityFilterKeepUnknown');
            const countEl = document.getElementById('qualityFilterCount');
            if (!row || !select) return;

            const items = resultsTab.querySelectorAll('.result-item');
            row.style.display = items.length ? '' : 'none';
            if (!items.length) return;

            const minTier = parseInt(select.value, 10) || 0;
            const keepUnknown = !!(keepUnknownEl && keepUnknownEl.checked);
            let hidden = 0;

            items.forEach(item => {
                const tier = parseInt(item.dataset.qualityTier, 10) || 0;
                const passes = minTier === 0
                    ? true
                    : (tier === 0 ? keepUnknown : tier >= minTier);
                item.style.display = passes ? '' : 'none';
                if (!passes) hidden++;
            });

            if (countEl) {
                countEl.textContent = hidden
                    ? `${items.length - hidden} of ${items.length} shown`
                    : '';
            }
        }

        // Each source says whether it can preview (has_preview from /api/sources, loaded
        // at start-up). Soulseek is the holdout: there is no streamable URL until the
        // file has already been downloaded, at which point previewing it is rather
        // beside the point. Unknown until the list lands means "try it".
        const sourceHasPreview = source => {
            const meta = (_cachedSources || []).find(s => s.id === source);
            return meta ? meta.has_preview : true;
        };

        // Render a single result card as an HTML string (mirrors the main renderResults template)
        function _renderOneResult(r, index) {
            const safeSource = escapeHtml(r.source || '');
            const safeVideoId = escapeHtml(r.video_id || '');
            const previewable = sourceHasPreview(r.source);
            return `
                <div class="result-item ${downloadingIds.has(r.video_id) ? 'downloading' : ''} ${r.source === 'soulseek' ? 'soulseek' : ''}"
                     data-video-id="${safeVideoId}"
                     data-quality-tier="${Number(r.quality_tier) || 0}"
                     data-index="${index}"
                     data-title="${escapeHtml(r.title)}"
                     data-tooltip="${resultTooltip(previewable)}">
                    ${previewable ? '<div class="preview-indicator">▶</div>' : ''}
                    ${r.thumbnail ? `<img class="result-thumb" src="${escapeHtml(r.thumbnail)}" alt="" loading="lazy">` : '<div class="result-thumb"></div>'}
                    <div class="result-info">
                        <div class="result-title">${escapeHtml(r.title)}</div>
                        <div class="result-meta">${formatResultMeta(r)}</div>
                        <div class="result-badges">
                            <span class="source-badge ${safeSource}">${getSourceBadge(r.source)}</span>
                            ${r.quality ? `<span class="quality-badge ${getQualityBadgeClass(r.quality)}">${formatQualityLabel(r.quality)}</span>` : ''}
                            ${r.duration ? `<span class="result-duration">${r.duration}</span>` : ''}
                        </div>
                    </div>
                    ${previewable ? `<div class="mobile-actions"><button class="preview-btn" data-video-id="${safeVideoId}" data-index="${index}" title="Preview">Preview &#9654;</button></div>` : ''}
                </div>
            `;
        }

        // Attach download/preview handlers to a single result card element
        function _attachResultHandlers(item, result, index) {
            const videoId = item.dataset.videoId;

            item.addEventListener('click', () => {
                if (!downloadingIds.has(videoId)) {
                    stopPreview();
                    downloadTrack(result, item);
                }
            });

            item.addEventListener('mouseenter', () => {
                if (!downloadingIds.has(videoId) && sourceHasPreview(result.source)) {
                    startHoverTimer(videoId, item, result);
                }
            });

            item.addEventListener('mouseleave', () => stopHoverPreview());

            const previewBtn = item.querySelector('.preview-btn');
            if (previewBtn) {
                previewBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (downloadingIds.has(videoId)) return;
                    if (previewIsActiveOrLoading(videoId, result)) {
                        stopPreview();
                    } else {
                        startPreview(videoId, item, result);
                    }
                });
            }
        }

        function renderResults(results) {
            // Store results for later access (needed for slskd fields on download)
            lastResults = results;

            if (!results.length) {
                resultsTab.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon"><i class="fa-solid fa-magnifying-glass"></i></div>
                        <p>No results found</p>
                    </div>
                `;
                return;
            }

            // Show the destination picker row now that there are results to act on
            const _destRow2 = document.getElementById('destinationPickerRow');
            if (_destRow2) _destRow2.style.display = '';

            resultsTab.innerHTML = results.map((r, index) => {
                const safeSource = escapeHtml(r.source || '');
                const safeVideoId = escapeHtml(r.video_id || '');
                const previewable = sourceHasPreview(r.source);
                return `
                <div class="result-item ${downloadingIds.has(r.video_id) ? 'downloading' : ''} ${r.source === 'soulseek' ? 'soulseek' : ''}"
                     data-video-id="${safeVideoId}"
                     data-quality-tier="${Number(r.quality_tier) || 0}"
                     data-index="${index}"
                     data-title="${escapeHtml(r.title)}"
                     data-tooltip="${resultTooltip(previewable)}">
                    ${previewable ? '<div class="preview-indicator">▶</div>' : ''}
                    ${r.thumbnail ? `<img class="result-thumb" src="${escapeHtml(r.thumbnail)}" alt="" loading="lazy">` : '<div class="result-thumb"></div>'}
                    <div class="result-info">
                        <div class="result-title">${escapeHtml(r.title)}</div>
                        <div class="result-meta">${formatResultMeta(r)}</div>
                        <div class="result-badges">
                            <span class="source-badge ${safeSource}">${getSourceBadge(r.source)}</span>
                            ${r.quality ? `<span class="quality-badge ${getQualityBadgeClass(r.quality)}">${formatQualityLabel(r.quality)}</span>` : ''}
                            ${r.duration ? `<span class="result-duration">${r.duration}</span>` : ''}
                            ${r.bitrate ? `<span class="result-detail">${Number(r.bitrate)} kbps</span>` : ''}
                            ${r.size_bytes ? `<span class="result-detail">${formatFileSize(r.size_bytes)}</span>` : ''}
                            ${r.source === 'soulseek' && Number.isInteger(r.queue_length) ? `<span class="result-detail" title="Number of uploads already queued by this Soulseek peer">Peer queue: ${r.queue_length}</span>` : ''}
                            ${r.source === 'soulseek' && r.channel ? `<span class="result-uploader" title="The Soulseek user sharing this file">via ${escapeHtml(r.channel)}</span>` : ''}
                        </div>
                    </div>
                    ${renderMatchBadge(r)}
                    <div class="mobile-actions">
                        ${previewable ? `<button class="preview-btn" data-video-id="${safeVideoId}" data-index="${index}" title="Preview">Preview &#9654;</button>` : ''}
                        <button class="explore-btn" data-artist="${escapeAttr(r.artist || r.channel)}" title="Find similar artists via ListenBrainz">~ Similar</button>
                    </div>
                </div>
                `;
            }).join('');

            applyQualityFilter();
            applyCachedAlbumArtwork();

            // Add click and hover handlers
            resultsTab.querySelectorAll('.result-item').forEach(item => {
                const videoId = item.dataset.videoId;
                const index = parseInt(item.dataset.index);
                const result = lastResults[index];

                // Click to download
                item.addEventListener('click', () => {
                    if (!downloadingIds.has(videoId)) {
                        stopPreview();
                        downloadTrack(result, item);
                    }
                });

                // Hover to preview (desktop only, not for sources with no preview endpoint)
                item.addEventListener('mouseenter', () => {
                    if (!downloadingIds.has(videoId) && sourceHasPreview(result.source)) {
                        startHoverTimer(videoId, item, result);
                    }
                });

                item.addEventListener('mouseleave', () => {
                    stopHoverPreview();
                });

                // Mobile preview button - tap to preview without triggering download
                const previewBtn = item.querySelector('.preview-btn');
                if (previewBtn) {
                    previewBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (downloadingIds.has(videoId)) return;
                        if (previewIsActiveOrLoading(videoId, result)) {
                            stopPreview();
                        } else {
                            startPreview(videoId, item, result);
                        }
                    });
                }

                // Similar artists button - explore via ListenBrainz
                const exploreBtn = item.querySelector('.explore-btn');
                if (exploreBtn) {
                    exploreBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        exploreSimilar(exploreBtn.dataset.artist);
                    });
                }

                // Album link - click to open in the Artists tab's album browser
                const albumLink = item.querySelector('.album-link');
                if (albumLink) {
                    albumLink.addEventListener('click', (e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        openAlbumFromSearch({
                            artistName: albumLink.dataset.artist,
                            albumTitle: albumLink.dataset.album,
                            sourceId: albumLink.dataset.source,
                            sourceAlbumId: albumLink.dataset.albumId,
                        });
                    });
                }
            });
        }

        function resultDurationSeconds(value) {
            if (typeof value === 'number') {
                return Number.isFinite(value) && value > 0 ? value : null;
            }
            const text = String(value || '').trim();
            if (!text) return null;
            if (/^\d+$/.test(text)) return Number(text) || null;
            const parts = text.split(':');
            if (parts.length < 2 || parts.length > 3 || parts.some(part => !/^\d+$/.test(part))) {
                return null;
            }
            const seconds = parts.reduce((total, part) => total * 60 + Number(part), 0);
            return seconds > 0 ? seconds : null;
        }

        async function downloadTrack(result, element) {
            const repairSelection = _albumRepairSelection;
            // Check queue size limit
            const queueSize = await getQueueSize();
            if (queueSize >= MAX_QUEUE_SIZE) {
                showToast(`Queue limit reached (max ${MAX_QUEUE_SIZE})`, true);
                return;
            }

            downloadingIds.add(result.video_id);
            element.classList.add('downloading');

            showToast(`Processing (${getSourceLabel(result.source)})...`, false);

            try {
                let queuedTitle = result.title;
                const payload = {
                    video_id: result.video_id,
                    title: queuedTitle,
                    convert_audio: convertAudioCheckbox.checked,
                    source: result.source || 'youtube',
                    search_token: currentSearchLogToken
                };
                const selectedDurationSecs = resultDurationSeconds(result.duration);
                if (selectedDurationSecs) {
                    payload.selected_duration_secs = selectedDurationSecs;
                }
                if (result.artist || result.channel) {
                    payload.artist = result.artist || result.channel;
                }

                // URL-identified sources need the full URL for downloading. The server
                // checks it belongs to the source, and ignores it where the source
                // identifies results another way (YouTube by video ID).
                if (result.source_url) {
                    payload.source_url = result.source_url;
                }

                // Add slskd-specific fields if this is a Soulseek peer's file
                if (result.slskd_username) {
                    payload.slskd_username = result.slskd_username;
                    payload.slskd_filename = result.slskd_filename;
                    payload.slskd_size = result.slskd_size || result.size || null;
                    if (result.artist) {
                        payload.artist = result.artist;
                    }
                }

                if (repairSelection) payload.album_repair = repairSelection;
                const albumRoute = repairSelection ? null : getSelectedAlbumRoute();
                if (_destinationMode === 'album' && !albumRoute) {
                    throw new Error('Select an artist and album folder before downloading.');
                }
                if (albumRoute) {
                    if (albumRoute.mode === 'no_mbid') {
                        // Folder routing only, no .albuminfo found so no track metadata enrichment
                        payload.album_artist = albumRoute.album_artist;
                        payload.album_name = albumRoute.album_name;
                    } else {
                        let matchedTrack = null;
                        if (albumRoute.mode === 'manual') {
                            matchedTrack = {
                                track_title: albumRoute.track_title,
                                track_number: albumRoute.track_number,
                                track_total: albumRoute.track_total,
                                disc_number: albumRoute.disc_number,
                                disc_total: albumRoute.disc_total,
                            };
                        } else {
                            const matchResp = await apiFetch(`/api/albums/release/${encodeURIComponent(albumRoute.release_mbid)}/match-track`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    artist: result.artist || result.channel || '',
                                    title: result.title || '',
                                    album_artist: albumRoute.album_artist || '',
                                })
                            });
                            if (!matchResp.ok) {
                                const err = await matchResp.json().catch(() => ({}));
                                throw new Error(err.detail || 'No album-track match found');
                            }
                            matchedTrack = await matchResp.json();
                        }

                        queuedTitle = matchedTrack.track_title || queuedTitle;
                        payload.title = queuedTitle;
                        payload.album_release_mbid = albumRoute.release_mbid;
                        payload.album_artist = albumRoute.album_artist;
                        payload.album_name = albumRoute.album_name;
                        payload.album_track_title = matchedTrack.track_title || queuedTitle;
                        payload.album_track_number = matchedTrack.track_number || null;
                        payload.album_track_total = matchedTrack.track_total || albumRoute.track_total || null;
                        // Only a multi-disc release needs the disc said; one disc is the default.
                        if ((matchedTrack.disc_total || 1) > 1) {
                            payload.album_disc_number = matchedTrack.disc_number || null;
                            payload.album_disc_total = matchedTrack.disc_total;
                        }
                    }
                }

                // Playlist routing - attach target playlist if one is selected
                const selectedPlaylist = getSelectedPlaylist();
                if (selectedPlaylist && albumRoute) {
                    throw new Error('Choose either Add to playlist or Add to album, not both');
                }
                if (selectedPlaylist) {
                    payload.playlist_name = selectedPlaylist.name;
                    payload.use_playlists_dir = true;
                }

                const response = await apiFetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    const error = await response.json().catch(() => ({}));
                    throw new Error(error.detail || 'Download failed');
                }

                const data = await response.json();

                // Update toast with success message
                const formatMsg = convertAudioCheckbox.checked ? ` (${conversionChoiceLabel(true)})` : ' (original format)';
                const qualityMsg = result.quality ? ` [${formatQualityLabel(result.quality)}]` : '';
                const pl = getSelectedPlaylist();
                const playlistMsg = pl ? ` → ${pl.name}` : '';
                const al = getSelectedAlbumRoute();
                const albumMsg = repairSelection ? ` → ${repairSelection.album_title} (album repair)` : (al ? ` → ${al.album_name}` : '');
                showToast(`Added to queue${qualityMsg}${formatMsg}${playlistMsg}${albumMsg}`);
                if (repairSelection && _albumRepairSelection === repairSelection) _resetDestination();
            } catch (error) {
                downloadingIds.delete(result.video_id);
                element.classList.remove('downloading');
                showToast(error?.message ? `Failed to queue: ${error.message}` : 'Failed to queue', true);
            }
        }

        // Event listeners
        searchBtn.addEventListener('click', search);
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                search();
            }
        });
        searchInput.addEventListener('focus', () => {
            if (searchInput.value.trim() === '') {
                showSearchHistory();
            }
        });
        searchInput.addEventListener('blur', hideSearchHistory);
        searchInput.addEventListener('input', () => {
            searchClearBtn.style.display = searchInput.value ? '' : 'none';
            if (searchInput.value.trim() === '') {
                showSearchHistory();
            } else {
                hideSearchHistory();
            }
        });
        searchClearBtn.addEventListener('click', () => {
            setSearchValue('');
            searchInput.focus();
            // Reset results back to the empty state
            stopPreview();
            lastCompletedSearchQuery = '';
            lastResults = [];
            relatedSuggestions.style.display = 'none';
            exploreBar.style.display = 'none';
            const _destRow3 = document.getElementById('destinationPickerRow');
            if (_destRow3) _destRow3.style.display = 'none';
            resultsTab.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"><i class="fa-solid fa-headphones"></i></div>
                    <p>Search for music to get started</p>
                    <p style="font-size: 12px; margin-top: 8px; opacity: 0.6;">Hover over results to preview</p>
                </div>
            `;
            showSearchHistory();
        });
        // Minimum-quality filter: remembered between searches, since somebody who
        // only wants lossless generally still only wants lossless five minutes later.
        const qualityFilterSelect = document.getElementById('qualityFilterSelect');
        const qualityFilterKeepUnknown = document.getElementById('qualityFilterKeepUnknown');
        if (qualityFilterSelect) {
            const savedTier = localStorage.getItem('mg_min_quality_tier');
            if (savedTier !== null) qualityFilterSelect.value = savedTier;
            qualityFilterSelect.addEventListener('change', () => {
                localStorage.setItem('mg_min_quality_tier', qualityFilterSelect.value);
                applyQualityFilter();
            });
        }
        if (qualityFilterKeepUnknown) {
            const savedKeep = localStorage.getItem('mg_quality_keep_unknown');
            if (savedKeep !== null) qualityFilterKeepUnknown.checked = savedKeep === '1';
            qualityFilterKeepUnknown.addEventListener('change', () => {
                localStorage.setItem('mg_quality_keep_unknown', qualityFilterKeepUnknown.checked ? '1' : '0');
                applyQualityFilter();
            });
        }

        // Preview button on desktop: off by default, so hover-to-preview stays the
        // behaviour everybody already knows.
        const desktopPreviewButtonToggle = document.getElementById('settingDesktopPreviewButton');
        if (desktopPreviewButtonToggle) {
            desktopPreviewButtonToggle.addEventListener('change', () => {
                localStorage.setItem(
                    userStorageKey('desktopPreviewButton'),
                    desktopPreviewButtonToggle.checked ? '1' : '0'
                );
                stopPreview();  // whatever was playing belonged to the old rules
                applyDesktopPreviewButton();
            });
        }
        applyDesktopPreviewButton();

        // Close search history when clicking outside
        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !searchHistory.contains(e.target)) {
                searchHistory.classList.remove('show');
            }
        });

        // Initial empty state
        resultsTab.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">~</div>
                <p>Search for music to get started</p>
                <p style="font-size: 12px; margin-top: 8px; opacity: 0.6;">Hover over results to preview</p>
            </div>
        `;
