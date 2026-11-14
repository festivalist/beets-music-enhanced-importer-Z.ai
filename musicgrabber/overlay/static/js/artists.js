        // Artists tab: Discover, following artists, and Follow for Albums.

        // -----------------------------------------------------------------------
        // Find New Artists (Artists tab -> "Find New Artists" pill)
        //
        // Three ways in: the auto-generated rows from /api/discover/rows (seeded
        // from Navidrome or Plex history, library contents, or past downloads, in that
        // order of preference), a manual "recommend based on" box that hits the
        // existing /api/explore/similar, and the rabbit hole - click an artist's
        // name and their own similar artists land in a new row underneath. Falling
        // down a Discogs hole at 1am, but on purpose and with a way back out.
        // -----------------------------------------------------------------------

        let _discoverLoaded = false;       // have we ever fetched /api/discover/rows
        let _discoverAudio = null;         // the one taster <audio> allowed to play at a time
        let _discoverPlayingCard = null;   // card element currently sounding off
        let _discoverBreadcrumb = [];      // trail of artist names for the rabbit hole

        function _stopDiscoverPreview() {
            if (_discoverAudio) {
                _discoverAudio.pause();
                _discoverAudio.src = '';
                _discoverAudio = null;
            }
            if (_discoverPlayingCard) {
                _discoverPlayingCard.classList.remove('discover-card-playing');
                _discoverPlayingCard = null;
            }
        }

        function setArtistsMode(mode) {
            const followedPanel = document.getElementById('followedArtistsPanel');
            const discoverPanel = document.getElementById('findNewArtistsPanel');
            const refreshBtn = document.getElementById('refreshAllArtistsBtn');
            if (!followedPanel || !discoverPanel) return;
            const isDiscover = mode === 'discover';
            followedPanel.style.display = isDiscover ? 'none' : '';
            discoverPanel.style.display = isDiscover ? '' : 'none';
            if (refreshBtn) refreshBtn.style.display = isDiscover ? 'none' : '';
            // The blurb above the pills describes whichever half you are looking
            // at; leaving the Followed wording up while showing discoveries just
            // reads as the page talking about something else entirely.
            const intro = document.getElementById('artistsIntroText');
            if (intro) {
                intro.textContent = isDiscover
                    ? "Artists you have not got yet, worked out from what you actually listen to. Have a listen, grab the good ones, and follow the trail as far as it goes."
                    : "Find an artist, then pick what you want from them: their singles as they land, their albums, or just one album right now.";
            }
            if (isDiscover) {
                initDiscoverPanel();
            } else {
                _stopDiscoverPreview();
            }
        }

        function initDiscoverPanel() {
            if (_discoverLoaded) return;
            _discoverLoaded = true;
            loadDiscoverRows();
        }

        async function loadDiscoverRows() {
            const container = document.getElementById('discoverRowsContainer');
            if (!container) return;
            container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            try {
                const resp = await apiFetch('/api/discover/rows?limit=5&per_row=10');
                if (!resp.ok) throw new Error('Could not reach the discovery service');
                const data = await resp.json();
                const rows = data.rows || [];
                if (data.signal === 'none' || !rows.length) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon">🔇</div>
                            <p>Nothing to go on yet, you've been suspiciously well-behaved.</p>
                            <small>Listen to something in Navidrome or Plex, or download a track or two, and we'll start digging up lookalikes for you.</small>
                        </div>`;
                    return;
                }
                container.innerHTML = '';
                rows.forEach(row => {
                    const rowEl = discoverCreateRow(row.reason || `Because you listen to ${row.seed}`, { seed: row.seed });
                    container.appendChild(rowEl);
                    discoverFillRow(rowEl, row.artists || []);
                });
            } catch (e) {
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">🕳️</div>
                        <p>Could not load recommendations: ${escapeHtml(e.message)}</p>
                        <button type="button" class="btn btn-primary" id="discoverRetryBtn">Try again</button>
                    </div>`;
                document.getElementById('discoverRetryBtn')?.addEventListener('click', () => {
                    _discoverLoaded = false;
                    initDiscoverPanel();
                });
            }
        }

        // Brings a newly-added row into view and says "over here" about it.
        //
        // scrollIntoView was doing two unhelpful things at once: putting the row
        // flush against the top of the window, which shoves the box you just
        // typed into off the screen, and moving so fast that the arrival was over
        // before the eye caught it. This lands the row a little way down instead,
        // takes its time getting there, and leaves the accent ring on it for a
        // moment so there is no doubt about which row is the new one.
        function discoverRevealRow(row, { offset = 110, duration = 850 } = {}) {
            if (!row) return;

            // Flag it first: even if the scroll is a no-op because the row is
            // already on screen, the highlight still has to happen.
            row.classList.add('discover-row-arrived');
            setTimeout(() => row.classList.remove('discover-row-arrived'), 2200);

            // Whichever ancestor actually scrolls, or the page if none does.
            let box = row.parentElement;
            while (box && box !== document.body) {
                const style = getComputedStyle(box);
                if (/(auto|scroll)/.test(style.overflowY) && box.scrollHeight > box.clientHeight) break;
                box = box.parentElement;
            }
            if (box === document.body) box = null;

            const from = box ? box.scrollTop : window.scrollY;
            const easy = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
            const frame = box ? box.getBoundingClientRect().top : 0;
            const to = Math.max(0, from + row.getBoundingClientRect().top - frame - offset);
            if (Math.abs(to - from) < 4) return;

            if (easy) {          // asked not to be swooshed about
                if (box) box.scrollTop = to; else window.scrollTo(0, to);
                return;
            }

            const start = performance.now();
            let lastSet = from;
            function step(now) {
                const here = box ? box.scrollTop : window.scrollY;
                // Somebody grabbed the wheel. Their scroll wins, always.
                if (Math.abs(here - lastSet) > 2) return;
                const t = Math.min(1, (now - start) / duration);
                // easeInOutCubic: unhurried at both ends, so the movement reads
                // as "look here" rather than as the page glitching.
                const eased = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
                lastSet = from + (to - from) * eased;
                if (box) box.scrollTop = lastSet; else window.scrollTo(0, lastSet);
                if (t < 1) requestAnimationFrame(step);
            }
            requestAnimationFrame(step);
        }

        // Builds an empty row shell (heading + spinner) ready for discoverFillRow
        // to drop cards into once the artists for it are known.
        function discoverCreateRow(heading, opts = {}) {
            const row = document.createElement('div');
            row.className = 'discover-row';
            if (opts.rabbitHole) row.dataset.rabbitHole = '1';
            if (opts.seed) row.dataset.seed = opts.seed;
            row.innerHTML = `
                <div class="discover-row-header">
                    <h3 class="discover-row-heading">${escapeHtml(heading)}</h3>
                    <button type="button" class="btn btn-sm discover-row-grab-btn" disabled
                            title="Queue every artist in this row as one playlist">Grab the lot</button>
                </div>
                <div class="discover-row-body"><div class="loading"><div class="spinner"></div></div></div>
            `;
            row.querySelector('.discover-row-grab-btn')
               .addEventListener('click', () => discoverRowGrabAll(row));
            return row;
        }

        function discoverFillRow(row, artists) {
            const body = row.querySelector('.discover-row-body');
            const grabBtn = row.querySelector('.discover-row-grab-btn');
            if (!body) return;
            if (!artists || !artists.length) {
                body.innerHTML = '<p class="discover-row-empty">Nothing came back for this one, dead end in the tunnel.</p>';
                if (grabBtn) grabBtn.remove();  // nothing to grab, so stop advertising it
                return;
            }
            const scroll = document.createElement('div');
            scroll.className = 'discover-row-scroll';
            artists.forEach(a => scroll.appendChild(discoverBuildCard(a)));
            body.innerHTML = '';
            body.appendChild(scroll);
            if (grabBtn) grabBtn.disabled = false;
        }

        function discoverRowError(row, message, retryFn) {
            const body = row.querySelector('.discover-row-body');
            if (!body) return;
            body.innerHTML = `<p class="discover-row-empty">Could not load this one: ${escapeHtml(message)}. <button type="button" class="btn btn-ghost btn-sm discover-row-retry-btn">Try again</button></p>`;
            const retryBtn = body.querySelector('.discover-row-retry-btn');
            if (retryBtn && retryFn) retryBtn.addEventListener('click', retryFn);
        }

        // One artist card: art (with a graceful fallback), name (the rabbit hole),
        // a play button for the 30-second taster, and a download button.
        function discoverBuildCard(a) {
            const wrap = document.createElement('div');
            wrap.className = 'discover-card';
            wrap._artist = a;  // the row-wide "Grab the lot" needs these back
            wrap.innerHTML = `
                <div class="discover-card-art">
                    <span class="discover-card-art-fallback">🎵</span>
                    ${a.picture ? `<img class="discover-card-img" src="${escapeHtml(a.picture)}" alt="" loading="lazy">` : ''}
                </div>
                <button type="button" class="discover-card-name" title="See what's similar to ${escapeHtml(a.artist)}">${escapeHtml(a.artist)}</button>
                <span class="discover-owned-badge" hidden>Already got it</span>
                <div class="discover-card-title"></div>
                <div class="discover-card-actions">
                    <button type="button" class="btn btn-sm discover-play-btn" title="Preview">&#9654;</button>
                    <button type="button" class="btn btn-sm btn-primary discover-dl-btn" title="Download">Grab it</button>
                </div>
            `;

            const img = wrap.querySelector('.discover-card-img');
            // A dud picture URL should just fall back to the music-note glyph
            // underneath, not sit there as a broken-image icon looking sorry for itself.
            if (img) img.addEventListener('error', () => img.remove());

            const playBtn = wrap.querySelector('.discover-play-btn');
            const dlBtn = wrap.querySelector('.discover-dl-btn');
            const nameBtn = wrap.querySelector('.discover-card-name');

            playBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                discoverPlayPreview(a.artist, a.deezer_id, wrap);
            });
            dlBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                discoverDownload(a.artist, a.deezer_id, wrap);
            });
            nameBtn.addEventListener('click', () => discoverRabbitHole(a.artist));

            return wrap;
        }

        // Resolves (and caches on the card itself) the taster for one artist.
        // Returns null on a 404 (no preview available), which callers treat as
        // "nothing to play", not as an error worth shouting about.
        async function discoverResolveTaster(artist, deezerId, cardEl) {
            if (cardEl._taster) return cardEl._taster;
            if (cardEl._taster404) return null;

            // No Deezer id is not a dead end. Suggestions that came from
            // ListenBrainz rather than Deezer arrive without one, and those are
            // precisely the artists Deezer had never heard of, so refusing to
            // look them up would leave the most obscure finds unplayable. The
            // backend resolves by name when no id is given.
            let url = `/api/discover/taster?artist=${encodeURIComponent(artist)}`;
            if (deezerId) url += `&deezer_id=${encodeURIComponent(deezerId)}`;
            const resp = await apiFetch(url);
            if (resp.status === 404) {
                cardEl._taster404 = true;
                return null;
            }
            if (!resp.ok) throw new Error('Lookup failed');
            const data = await resp.json();
            cardEl._taster = data;

            const titleEl = cardEl.querySelector('.discover-card-title');
            if (titleEl && data.title) titleEl.textContent = data.title;
            const badge = cardEl.querySelector('.discover-owned-badge');
            if (badge && data.owned) badge.hidden = false;

            return data;
        }

        async function discoverPlayPreview(artist, deezerId, cardEl) {
            const playBtn = cardEl.querySelector('.discover-play-btn');
            if (!playBtn || playBtn.disabled) return;

            const wasPlayingThis = _discoverPlayingCard === cardEl;
            stopPreview();          // only one thing gets to make noise at a time
            _stopDiscoverPreview();
            if (wasPlayingThis) return; // clicking the active card's play button again just stops it

            cardEl.classList.add('discover-card-loading');
            try {
                const data = await discoverResolveTaster(artist, deezerId, cardEl);
                cardEl.classList.remove('discover-card-loading');
                if (!data || !data.preview_url) {
                    playBtn.disabled = true;
                    playBtn.title = 'No preview available for this one';
                    return;
                }
                _discoverAudio = new Audio(data.preview_url);
                _discoverAudio.volume = 0.9;
                _discoverAudio.addEventListener('ended', () => {
                    if (_discoverPlayingCard === cardEl) _stopDiscoverPreview();
                });
                await _discoverAudio.play().catch(() => {});
                cardEl.classList.add('discover-card-playing');
                _discoverPlayingCard = cardEl;
            } catch (e) {
                cardEl.classList.remove('discover-card-loading');
                showToast(`Preview failed: ${e.message}`, true);
            }
        }

        // Resolve the taster for its title (if we don't already have it), search
        // for "{artist} - {title}", and hand the top result to the same download
        // call the main search results use. Same trick as exploreSimilar's
        // searchOne, just for one card instead of a whole batch.
        async function discoverDownload(artist, deezerId, cardEl) {
            const dlBtn = cardEl.querySelector('.discover-dl-btn');
            if (!dlBtn || dlBtn.disabled) return;
            const originalLabel = dlBtn.textContent;
            dlBtn.disabled = true;
            dlBtn.textContent = 'Queuing...';

            try {
                let title = cardEl._taster?.title;
                if (!title) {
                    const resolved = await discoverResolveTaster(artist, deezerId, cardEl).catch(() => null);
                    title = resolved?.title;
                }
                // Searching for a specific track rather than just a name is the
                // whole reason the taster exists: it gives the matcher something
                // precise to score against, and is how a discovery comes back as
                // a lossless copy instead of whatever turned up first.
                const query = title ? `${artist} - ${title}` : artist;

                const searchResp = await apiFetch('/api/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, limit: 1, source: currentSource })
                });
                if (!searchResp.ok) throw new Error('Search failed');
                const searchData = await searchResp.json();
                const top = searchData.results && searchData.results[0];
                if (!top) throw new Error('Nothing found to download');

                const payload = {
                    video_id: top.video_id,
                    title: top.title,
                    convert_audio: convertAudioCheckbox.checked,
                    source: top.source || 'youtube'
                };
                if (top.artist || top.channel) payload.artist = top.artist || top.channel;
                // The server checks the URL belongs to the source and ignores it
                // where the source identifies results another way.
                if (top.source_url) {
                    payload.source_url = top.source_url;
                }
                if (top.slskd_username) {
                    payload.slskd_username = top.slskd_username;
                    payload.slskd_filename = top.slskd_filename;
                    payload.slskd_size = top.slskd_size || top.size || null;
                }

                const downloadResp = await apiFetch('/api/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!downloadResp.ok) throw new Error('Download failed');

                dlBtn.textContent = 'Queued';
                showToast(`Queued ${artist}${title ? ` - ${title}` : ''}`);
            } catch (e) {
                dlBtn.disabled = false;
                dlBtn.textContent = originalLabel;
                showToast(`Could not queue: ${e.message}`, true);
            }
        }

        // "Grab the lot": resolve a track for every artist in the row and hand
        // the lot to bulk import as one playlist. The tasters are what make this
        // worth doing; a list of bare artist names would just fetch whatever each
        // source happened to think was their finest hour.
        async function discoverRowGrabAll(row) {
            const btn = row.querySelector('.discover-row-grab-btn');
            const cards = Array.from(row.querySelectorAll('.discover-card'));
            if (!btn || !cards.length) return;
            const originalLabel = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Rounding up...';

            try {
                const lines = [];
                // Five at a time, same as the Similar search. Deezer is free and
                // we would quite like it to stay that way.
                for (let i = 0; i < cards.length; i += 5) {
                    const batch = cards.slice(i, i + 5);
                    const resolved = await Promise.all(batch.map(async card => {
                        const a = card._artist || {};
                        // Already queued from its own button, or the only track we
                        // could find is one you already own: either way, skip it.
                        if (card.querySelector('.discover-dl-btn')?.textContent === 'Queued') return null;
                        const data = await discoverResolveTaster(a.artist, a.deezer_id, card).catch(() => null);
                        if (!data || !data.title || data.owned) return null;
                        return `${a.artist} - ${data.title}`;
                    }));
                    resolved.forEach(line => { if (line) lines.push(line); });
                    btn.textContent = `Rounding up... ${lines.length}`;
                }

                if (!lines.length) {
                    btn.disabled = false;
                    btn.textContent = originalLabel;
                    showToast('Nothing left to grab in that row, you have the lot already', true);
                    return;
                }

                const seed = row.dataset.seed || 'your taste';
                const now = new Date();
                const dateSuffix = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
                const playlistName = `Similar to ${seed} (${dateSuffix})`;

                const resp = await apiFetch('/api/bulk-import-async', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        songs: lines.join('\n'),
                        convert_audio: convertAudioCheckbox.checked,
                        create_playlist: true,
                        playlist_name: playlistName,
                        use_playlists_dir: true
                    })
                });
                if (!resp.ok) throw new Error('Bulk import failed');

                btn.textContent = `Queued ${lines.length}`;
                showToast(`Queued ${lines.length} track${lines.length === 1 ? '' : 's'} as "${playlistName}"`);
            } catch (e) {
                btn.disabled = false;
                btn.textContent = originalLabel;
                showToast(`Could not queue that row: ${e.message}`, true);
            }
        }

        // Fetches similar artists for one name and drops them into an existing
        // row shell. Used by the manual "recommend based on" box, the rabbit
        // hole, and both of their retry buttons.
        async function discoverLoadSimilarInto(row, artist) {
            try {
                const resp = await apiFetch('/api/explore/similar', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ artist, limit: 25 })
                });
                if (!resp.ok) throw new Error('Could not reach similar-artists service');
                const data = await resp.json();
                discoverFillRow(row, (data.artists || []).slice(0, 10));
            } catch (e) {
                discoverRowError(row, e.message, () => {
                    row.querySelector('.discover-row-body').innerHTML = '<div class="loading"><div class="spinner"></div></div>';
                    discoverLoadSimilarInto(row, artist);
                });
            }
        }

        async function discoverManualSearch() {
            const input = document.getElementById('discoverSimilarInput');
            const btn = document.getElementById('discoverSimilarBtn');
            const slot = document.getElementById('discoverManualRowSlot');
            const artist = input?.value.trim();
            if (!artist || !slot) return;

            btn.disabled = true;
            const row = discoverCreateRow(`Because you asked about ${artist}`, { seed: artist });
            slot.innerHTML = '';
            slot.appendChild(row);
            discoverRevealRow(row);
            try {
                await discoverLoadSimilarInto(row, artist);
            } finally {
                btn.disabled = false;
            }
        }

        // The fun bit: click an artist's name and their own similar artists
        // land in a new row at the bottom, with a breadcrumb trail so nobody
        // gets lost down there.
        function discoverRabbitHole(artist) {
            const container = document.getElementById('discoverRowsContainer');
            if (!container) return;

            _discoverBreadcrumb.push(artist);
            renderDiscoverBreadcrumb();

            const row = discoverCreateRow(`Because you liked the look of ${artist}`, { rabbitHole: true, seed: artist });
            container.appendChild(row);
            discoverRevealRow(row);
            discoverLoadSimilarInto(row, artist);
        }

        function renderDiscoverBreadcrumb() {
            const bc = document.getElementById('discoverBreadcrumb');
            if (!bc) return;
            if (!_discoverBreadcrumb.length) {
                bc.style.display = 'none';
                bc.innerHTML = '';
                return;
            }
            bc.style.display = 'flex';
            bc.innerHTML = `
                <span class="discover-breadcrumb-label">Down the rabbit hole:</span>
                ${_discoverBreadcrumb.map((name, i) => `<button type="button" class="discover-breadcrumb-item" data-depth="${i}">${escapeHtml(name)}</button>`).join('<span class="discover-breadcrumb-sep">/</span>')}
                <button type="button" class="btn btn-ghost btn-sm discover-breadcrumb-exit" id="discoverExitHoleBtn">Climb out</button>
            `;
            bc.querySelectorAll('.discover-breadcrumb-item').forEach(item => {
                item.addEventListener('click', () => discoverTrimTrail(parseInt(item.dataset.depth, 10)));
            });
            document.getElementById('discoverExitHoleBtn')?.addEventListener('click', () => discoverTrimTrail(-1));
        }

        // Trims the rabbit-hole rows (and breadcrumb) back to `depth`; -1 climbs
        // all the way out. Rabbit-hole rows are always appended in the same
        // order as the breadcrumb, so index-matching the two is safe.
        function discoverTrimTrail(depth) {
            const container = document.getElementById('discoverRowsContainer');
            if (!container) return;
            const rabbitRows = container.querySelectorAll('.discover-row[data-rabbit-hole="1"]');
            const keepCount = depth < 0 ? 0 : depth + 1;
            rabbitRows.forEach((row, i) => {
                if (i >= keepCount) row.remove();
            });
            _discoverBreadcrumb = _discoverBreadcrumb.slice(0, keepCount);
            renderDiscoverBreadcrumb();
            if (keepCount > 0) {
                discoverRevealRow(rabbitRows[keepCount - 1]);
            } else {
                document.getElementById('findNewArtistsPanel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }

        const artistsModePills = document.getElementById('artistsModePills');
        if (artistsModePills) {
            // Initialised when the Artists tab is first shown, not here: a hidden
            // tab measures zero pixels and the indicator never turns up.
            artistsModePills.addEventListener('pillchange', (e) => setArtistsMode(e.detail.value));
        }
        document.getElementById('discoverSimilarBtn')?.addEventListener('click', discoverManualSearch);
        document.getElementById('discoverSimilarInput')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') discoverManualSearch();
        });

        watchedArtistList.addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-action]');
            if (!btn || !watchedArtistList.contains(btn)) return;

            const action = btn.dataset.action;
            if (action === 'save-job-to-device') {
                saveJobToDevice(btn.dataset.jobId || '');
                return;
            }

            if (action === 'retry-all-artist-missing') {
                retryAllArtistMissing(
                    btn.dataset.artistId || '',
                    btn
                );
                return;
            }

            if (action === 'retry-artist-track') {
                retryArtistTrack(
                    btn.dataset.artistId || '',
                    btn.dataset.artist || '',
                    btn.dataset.title || '',
                    btn
                );
                return;
            }

            if (action === 'refresh-watched-artist') {
                refreshWatchedArtist(btn.dataset.artistId || '');
                return;
            }

            if (action === 'toggle-artist-missing-tracks') {
                toggleArtistMissingTracks(btn.dataset.artistId || '');
                return;
            }

            if (action === 'toggle-watched-artist') {
                toggleWatchedArtist(
                    btn.dataset.artistId || '',
                    btn.dataset.enabled === 'true' ? 'false' : 'true'
                );
                return;
            }

            if (action === 'toggle-artist-track-list') {
                toggleArtistTrackList(
                    btn.dataset.artistId || '',
                    btn.dataset.artistName || ''
                );
                return;
            }

            if (action === 'toggle-artist-albums') {
                openArtistAlbumPanel(btn.dataset.artistId || '');
                return;
            }

            if (action === 'delete-watched-artist') {
                deleteWatchedArtist(
                    btn.dataset.artistId || '',
                    btn.dataset.artistName || ''
                );
            }
        });
        // =============================================================================
        // Watched Artists
        // =============================================================================

        let selectedArtistMbid = null;
        let selectedArtistName = null;
        let artistRefreshPending = new Map(); // artist_id -> {stage, startedAt}
        let artistRefreshPollInterval = null;
        let artistLoadInFlight = false;
        let watchedArtistsById = new Map(); // artist_id -> full row, so the Albums panel can look up mbid/auto_add_albums

        function startArtistRefreshPolling() {
            if (artistRefreshPollInterval) return;
            artistRefreshPollInterval = setInterval(() => loadWatchedArtists(false), 2000);
        }

        function stopArtistRefreshPolling() {
            if (artistRefreshPollInterval) {
                clearInterval(artistRefreshPollInterval);
                artistRefreshPollInterval = null;
            }
        }

        async function searchArtist() {
            const q = document.getElementById('artistSearchInput').value.trim();
            if (!q) return;
            const resultsEl = document.getElementById('artistSearchResults');
            const addForm = document.getElementById('artistAddForm');
            resultsEl.style.display = 'block';
            resultsEl.innerHTML = '<div style="font-size:12px;color:var(--text-secondary);">Searching MusicBrainz...</div>';
            addForm.style.display = 'none';
            selectedArtistMbid = null;
            selectedArtistName = null;
            try {
                const res = await apiFetch(`/api/watched-artists/search?q=${encodeURIComponent(q)}`);
                // A 503 means MusicBrainz is down, not that the artist does not exist.
                // Without this it parsed happily, found no results, and said so.
                if (!res.ok) {
                    let detail = `HTTP ${res.status}`;
                    try { detail = (await res.json()).detail || detail; } catch (_) { /* not JSON, keep the status */ }
                    resultsEl.innerHTML = `<div style="font-size:12px;color:var(--error);">Search failed: ${escapeHtml(detail)}</div>`;
                    return;
                }
                const data = await res.json();
                if (!data.results || data.results.length === 0) {
                    resultsEl.innerHTML = '<div style="font-size:12px;color:var(--text-secondary);">No artists found on MusicBrainz.</div>';
                    return;
                }
                // Collapse to a single candidate only when exactly one artist owns
                // the name. Plenty of names are shared: four different acts answer
                // to "Raye", and quietly picking whichever MusicBrainz listed first
                // hands you an anonymous feature credit instead of the singer you
                // meant. When the name is contested, show the field and let the
                // disambiguation text do its job.
                const qLower = q.toLowerCase();
                const exactMatches = data.results.filter(a => (a.name || '').toLowerCase() === qLower);
                const candidates = exactMatches.length === 1
                    ? exactMatches
                    : data.results.slice(0, 5);
                resultsEl.innerHTML = candidates.map(a => `
                    <div style="display:flex;align-items:center;gap:10px;padding:6px 10px;margin-bottom:4px;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:8px;">
                        <div style="flex:1;">
                            <span style="font-size:13px;font-weight:600;color:var(--text-primary);">${escapeHtml(a.name)}</span>
                            ${a.disambiguation ? `<span style="font-size:11px;color:var(--text-secondary);margin-left:6px;">${escapeHtml(a.disambiguation)}</span>` : ''}
                        </div>
                        <button type="button" class="btn btn-sm" ${uiAction('selectArtist', [a.mbid, a.name])}>Select</button>
                    </div>
                `).join('');
            } catch (e) {
                resultsEl.innerHTML = '<div style="font-size:12px;color:var(--error);">Search failed. Check server logs.</div>';
            }
        }

        function selectArtist(mbid, name) {
            selectedArtistMbid = mbid;
            selectedArtistName = name;
            document.getElementById('selectedArtistName').textContent = name;
            // Default from_date to today in YYYY-MM-DD
            const today = new Date().toISOString().slice(0, 10);
            document.getElementById('artistFromDate').value = today;
            document.getElementById('artistSearchResults').style.display = 'none';

            // Picking the artist no longer commits you to anything. Ask what they
            // are actually here for: singles, albums, or one album and out.
            hideArtistModePanels();
            const chooserName = document.getElementById('artistChooserName');
            if (chooserName) chooserName.textContent = name;
            const chooser = document.getElementById('artistModeChooser');
            if (chooser) chooser.style.display = 'block';
        }

        // Everything the chooser can reveal, so switching mode never leaves two
        // panels arguing over the same bit of screen.
        function hideArtistModePanels() {
            for (const id of ['artistModeChooser', 'artistAddForm',
                              'artistAlbumsFollowPanel', 'artistOneOffPanel']) {
                const el = document.getElementById(id);
                if (el) el.style.display = 'none';
            }
            const status = document.getElementById('artistAddStatus');
            if (status) status.style.display = 'none';
        }

        // Back to a blank slate: no artist selected, no panel open, nothing half-done.
        function resetArtistChooser() {
            hideArtistModePanels();
            selectedArtistMbid = null;
            selectedArtistName = null;
            const results = document.getElementById('artistSearchResults');
            if (results) { results.style.display = 'none'; results.innerHTML = ''; }
            const input = document.getElementById('artistSearchInput');
            if (input) input.value = '';
        }

        function chooseArtistMode(mode) {
            if (!selectedArtistMbid) return;
            hideArtistModePanels();
            if (mode === 'singles') {
                const panel = document.getElementById('artistAddForm');
                if (panel) panel.style.display = 'block';
                const addBtn = document.getElementById('addArtistBtn');
                if (addBtn) addBtn.disabled = false;
            } else if (mode === 'albums') {
                const panel = document.getElementById('artistAlbumsFollowPanel');
                if (panel) panel.style.display = 'block';
                const nameEl = document.getElementById('artistAlbumsFollowName');
                if (nameEl) nameEl.textContent = selectedArtistName;
                const toggle = document.getElementById('artistFollowAlbumsToggle');
                if (toggle) toggle.checked = false;
                const progress = document.getElementById('artistAlbumBatchProgress');
                if (progress) { progress.style.display = 'none'; progress.textContent = ''; }
                const batchBtn = document.getElementById('artistAlbumBatchBtn');
                if (batchBtn) batchBtn.disabled = false;
                renderAlbumChecklist(selectedArtistMbid, selectedArtistName);
            } else if (mode === 'oneoff') {
                const handle = showOneOffAlbumSection(selectedArtistName);
                if (handle) handle.setArtist(selectedArtistMbid, selectedArtistName);
            }
        }

        // =====================================================================
        // Follow for Albums: the whole discography, tickable
        // =====================================================================

        let artistChecklistAlbums = [];

        function updateAlbumChecklistCount() {
            const countEl = document.getElementById('artistAlbumChecklistCount');
            if (!countEl) return;
            const ticked = document.querySelectorAll('#artistAlbumChecklist input[type="checkbox"]:checked').length;
            const total = artistChecklistAlbums.length;
            countEl.textContent = ticked
                ? `${ticked} of ${total} selected`
                : `${total} album${total === 1 ? '' : 's'}`;
        }

        async function renderAlbumChecklist(mbid, name) {
            const listEl = document.getElementById('artistAlbumChecklist');
            if (!listEl) return;
            artistChecklistAlbums = [];
            listEl.innerHTML = '<p class="bulk-intro-text">Loading albums from MusicBrainz…</p>';
            updateAlbumChecklistCount();
            try {
                const res = await apiFetch(
                    `/api/albums/artist/${encodeURIComponent(mbid)}/albums?artist_name=${encodeURIComponent(name || '')}`
                );
                if (!res.ok) {
                    let detail = `HTTP ${res.status}`;
                    try { detail = (await res.json()).detail || detail; } catch (_) { /* not JSON, keep the status */ }
                    renderAlbumChecklistError(listEl, detail, mbid, name);
                    return;
                }
                const data = await res.json();
                artistChecklistAlbums = data.albums || [];
                if (!artistChecklistAlbums.length) {
                    listEl.innerHTML = '<p class="bulk-intro-text">No studio albums found for this artist.</p>';
                    updateAlbumChecklistCount();
                    return;
                }
                listEl.innerHTML = '';
                artistChecklistAlbums.forEach((album, idx) => {
                    const row = document.createElement('div');
                    row.className = 'album-checklist-row' + (album.on_disk ? ' on-disk' : '');
                    const cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.dataset.albumIndex = String(idx);
                    cb.addEventListener('change', updateAlbumChecklistCount);
                    const title = document.createElement('span');
                    title.className = 'album-checklist-title';
                    title.textContent = album.title || '(untitled)';
                    // Clicking the title ticks the box; the tracklist preview still
                    // lives in the one-off browser for anyone who wants the detail.
                    title.addEventListener('click', () => { cb.checked = !cb.checked; updateAlbumChecklistCount(); });
                    row.appendChild(cb);
                    row.appendChild(title);
                    if (album.year) {
                        const year = document.createElement('span');
                        year.className = 'album-checklist-year';
                        year.textContent = album.year;
                        row.appendChild(year);
                    }
                    if (album.on_disk) {
                        const have = document.createElement('span');
                        have.className = 'album-checklist-have';
                        have.textContent = 'already have it';
                        row.appendChild(have);
                    }
                    listEl.appendChild(row);
                });
                updateAlbumChecklistCount();
            } catch (e) {
                renderAlbumChecklistError(listEl, e.message, mbid, name);
            }
        }

        // MusicBrainz has its off days; offer a retry rather than a dead end.
        function renderAlbumChecklistError(listEl, detail, mbid, name) {
            listEl.innerHTML = '';
            const msg = document.createElement('p');
            msg.className = 'bulk-intro-text error-text';
            msg.textContent = `Failed to load albums: ${detail}`;
            const retry = document.createElement('button');
            retry.className = 'btn btn-ghost';
            retry.type = 'button';
            retry.textContent = 'Retry';
            retry.addEventListener('click', () => renderAlbumChecklist(mbid, name));
            listEl.appendChild(msg);
            listEl.appendChild(retry);
            updateAlbumChecklistCount();
        }

        async function followArtistForAlbums() {
            if (!selectedArtistMbid) return;
            const followFuture = document.getElementById('artistFollowAlbumsToggle')?.checked;
            const progressEl = document.getElementById('artistAlbumBatchProgress');
            const batchBtn = document.getElementById('artistAlbumBatchBtn');
            // Same checkbox every other album download reads, so albums all behave
            // the same way regardless of which door you came in through.
            const convertAudio = document.getElementById('convertAudio')?.checked ?? false;

            const picked = Array.from(
                document.querySelectorAll('#artistAlbumChecklist input[type="checkbox"]:checked')
            ).map(cb => artistChecklistAlbums[parseInt(cb.dataset.albumIndex, 10)]).filter(Boolean);

            if (!picked.length && !followFuture) {
                showToast('Tick some albums, or switch on future albums. Otherwise there is nothing to do.', true);
                return;
            }

            if (batchBtn) batchBtn.disabled = true;
            if (progressEl) { progressEl.style.display = 'block'; progressEl.textContent = 'Working…'; }

            // Only create a follow when future albums were actually asked for.
            // Ticking a few albums with the toggle off is just shopping, and it
            // would be rude to sign them up to a watch list for it.
            let watchArtistId = null;
            if (followFuture) {
                try {
                    const res = await apiFetch('/api/watched-artists', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            mbid: selectedArtistMbid,
                            name: selectedArtistName,
                            from_date: new Date().toISOString().slice(0, 10),
                            refresh_interval_hours: 24,
                            convert_audio: convertAudio,
                            auto_add_albums: true,
                            watch_singles: false,
                        })
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || 'Failed to follow artist');
                    watchArtistId = data.id;
                    if (data.warning) showToast(data.warning, true);
                } catch (e) {
                    if (progressEl) progressEl.textContent = `Could not follow artist: ${e.message}`;
                    if (batchBtn) batchBtn.disabled = false;
                    return;
                }
            }

            // Queue the ticked albums one at a time. MusicBrainz allows a request a
            // second, so firing them all at once just gets us politely throttled.
            let queued = 0;
            const failures = [];
            for (let i = 0; i < picked.length; i++) {
                const album = picked[i];
                if (progressEl) progressEl.textContent = `Queueing ${i + 1} of ${picked.length}: ${album.title}…`;
                try {
                    let releaseMbid = album.release_mbid;
                    if (!releaseMbid && album.release_group_mbid) {
                        // The list only carries a release-group id now; resolve the
                        // actual pressing here, one album at a time, same pacing
                        // this loop already uses for MusicBrainz.
                        const resolveRes = await apiFetch('/api/albums/resolve-release-group', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ release_group_mbid: album.release_group_mbid }),
                        });
                        const resolveData = await resolveRes.json().catch(() => ({}));
                        if (!resolveRes.ok) throw new Error(resolveData.detail || 'Could not resolve a release for this album');
                        releaseMbid = resolveData.release_mbid;
                    }
                    const res = await apiFetch('/api/albums/download', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            artist: selectedArtistName,
                            album_title: album.title,
                            release_mbid: releaseMbid,
                            release_group_mbid: album.release_group_mbid || '',
                            convert_audio: convertAudio,
                            watch_artist_id: watchArtistId || undefined,
                        })
                    });
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.detail || 'Queue failed');
                    queued++;
                } catch (e) {
                    // One duff release should not abandon the other six.
                    failures.push(`${album.title}: ${e.message}`);
                }
            }

            let summary = picked.length
                ? `Queued ${queued} of ${picked.length} album${picked.length === 1 ? '' : 's'}.`
                : '';
            if (followFuture) {
                summary += `${summary ? ' ' : ''}Now following ${selectedArtistName} for new albums.`;
            }
            if (failures.length) summary += ` ${failures.length} failed: ${failures.join('; ')}`;
            if (progressEl) progressEl.textContent = summary;
            showToast(summary, failures.length > 0);

            if (followFuture) {
                loadWatchedArtists();
                resetArtistChooser();
            } else if (batchBtn) {
                batchBtn.disabled = false;
            }
        }

        async function addWatchedArtist() {
            if (!selectedArtistMbid) return;
            const fromDate = document.getElementById('artistFromDate').value;
            const intervalHours = parseInt(document.getElementById('artistIntervalSelect').value);
            const convertAudio = document.getElementById('artistConvertAudio').checked;
            const statusEl = document.getElementById('artistAddStatus');
            const addBtn = document.getElementById('addArtistBtn');

            addBtn.disabled = true;
            statusEl.style.display = 'block';
            statusEl.textContent = 'Adding artist and fetching singles from MusicBrainz...';

            try {
                const res = await apiFetch('/api/watched-artists', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        mbid: selectedArtistMbid,
                        name: selectedArtistName,
                        from_date: fromDate,
                        refresh_interval_hours: intervalHours,
                        convert_audio: convertAudio,
                        watch_singles: true,
                    })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || 'Failed to add artist');
                statusEl.style.display = 'none';
                document.getElementById('artistAddForm').style.display = 'none';
                document.getElementById('artistSearchInput').value = '';
                selectedArtistMbid = null;
                selectedArtistName = null;
                // Seeding now runs in the background. Mark it as refreshing so the
                // card shows progress and polling kicks in (avoids a race with the
                // background thread setting refresh_state).
                if (data.id) {
                    artistRefreshPending.set(data.id, { stage: 'starting', startedAt: new Date().toISOString() });
                }
                showToast(`Now watching ${data.name}. Fetching the back-catalogue from MusicBrainz...`);
                loadWatchedArtists();
            } catch (e) {
                statusEl.textContent = `Error: ${e.message}`;
                addBtn.disabled = false;
            }
        }

        async function loadWatchedArtists(showLoading = true) {
            // The 2s poll must not stack up behind a slow response. A deliberate
            // (showLoading) load is let through, so a click is never swallowed.
            if (artistLoadInFlight && !showLoading) return;
            artistLoadInFlight = true;
            const listEl = document.getElementById('watchedArtistList');
            if (showLoading) listEl.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            try {
                const res = await apiFetch('/api/watched-artists');
                const data = await res.json();
                renderWatchedArtists(data.artists || []);
            } catch (e) {
                listEl.innerHTML = '<div class="empty-state"><p>Failed to load watched artists</p></div>';
            } finally {
                artistLoadInFlight = false;
            }
        }

        function renderWatchedArtists(artists) {
            const listEl = document.getElementById('watchedArtistList');
            if (!artists || artists.length === 0) {
                stopArtistRefreshPolling();
                listEl.innerHTML = '<div class="empty-state" style="padding: 1.5rem 0;"><div class="empty-state-icon"><i class="fa-solid fa-heart-circle-plus"></i></div><p>No artists followed yet</p></div>';
                const albumPanel = document.getElementById('artistAlbumPanel');
                if (albumPanel) albumPanel.style.display = 'none';
                return;
            }
            let anyRunning = false;
            watchedArtistsById = new Map(artists.map(a => [a.id, a]));
            const singlesOnlyMode = !!(serverConfig && serverConfig.singles_only_mode);
            const openPanels = liftOpenPanels(listEl);
            const scrollY = window.scrollY;
            listEl.innerHTML = artists.map(artist => {
                // Reconcile the optimistic "pending" flag against backend state.
                // Once the backend reports the refresh as running it's authoritative,
                // so drop the optimistic flag (otherwise it would linger after the
                // refresh finishes and spin the card forever). A safety timeout
                // covers refreshes so quick we never caught them "running".
                const pend = artistRefreshPending.get(artist.id);
                if (pend) {
                    const pendAgeMs = Date.now() - new Date(pend.startedAt).getTime();
                    if (artist.refresh_state === 'running' || pendAgeMs > 20000) {
                        artistRefreshPending.delete(artist.id);
                    }
                }
                const isRunning = artist.refresh_state === 'running' || artistRefreshPending.has(artist.id);
                if (isRunning) anyRunning = true;
                const isError = artist.refresh_state === 'error';
                const isPaused = !artist.enabled;
                // Older rows predate the column; absent means singles, as it always did.
                const watchesSingles = artist.watch_singles === undefined || !!artist.watch_singles;
                const intervalLabel = artist.refresh_interval_hours >= 720 ? 'monthly'
                    : artist.refresh_interval_hours >= 168 ? 'weekly'
                    : artist.refresh_interval_hours >= 24 ? 'daily'
                    : artist.refresh_interval_hours >= 12 ? 'every 12h'
                    : artist.refresh_interval_hours >= 6 ? 'every 6h'
                    : artist.refresh_interval_hours >= 1 ? 'hourly'
                    : 'every 30min';
                const lastChecked = artist.last_checked
                    ? `Last checked: <span title="${escapeAttr(formatTimeExact(artist.last_checked))}">${escapeHtml(formatTimeAgo(artist.last_checked))}</span>`
                    : 'Never checked';
                let stageHtml = '';
                if (isRunning) {
                    const pending = artistRefreshPending.get(artist.id);
                    const startedAt = pending?.startedAt || artist.refresh_started_at;
                    const elapsed = startedAt ? Math.floor((Date.now() - new Date(startedAt + 'Z').getTime()) / 1000) : 0;
                    const stageLabel = {
                        starting: 'Starting', fetching: 'Fetching from MusicBrainz',
                        diffing: 'Comparing tracks', queueing: 'Queueing downloads', done: 'Done',
                    }[artist.refresh_stage] || 'Refreshing';
                    stageHtml = `<span class="watched-card-refreshing"><span class="watched-refresh-spinner"></span>${escapeHtml(stageLabel)}${elapsed > 0 ? ` (${elapsed}s)` : ''}</span>`;
                }
                return `
                <div class="watched-card" id="artist-card-${artist.id}">
                    <div class="watched-card-header">
                        <span><i class="fa-brands fa-creative-commons-sampling"></i></span>
                        <span class="watched-card-name">${escapeHtml(artist.name)}</span>
                        ${stageHtml}
                        ${watchesSingles ? '<span class="watched-card-mode">Singles</span>' : ''}
                        ${artist.auto_add_albums ? '<span class="watched-card-mode">Albums</span>' : ''}
                        ${isPaused ? '<span class="watched-card-paused">Paused</span>' : ''}
                    </div>
                    <div class="watched-card-meta">
                        ${watchesSingles
                            ? `${artist.tracked_count || 0} singles tracked &middot; ${artist.downloaded_count || 0} downloaded &middot; `
                            : 'Albums only &middot; '}${intervalLabel} &middot; ${lastChecked}
                    </div>
                    ${isError ? `<div class="watched-card-refresh-error"><i class="fa-solid fa-circle-exclamation"></i><span>${escapeHtml(artist.refresh_error || 'Refresh failed')}</span></div>` : ''}
                    ${artist.unresolved_tracks > 0 ? `
                    <div class="watched-card-stale-warning">
                        <i class="fa-solid fa-circle-info"></i>
                        <span><strong>${artist.unresolved_tracks} downloaded single${artist.unresolved_tracks === 1 ? '' : 's'}</strong> can no longer be found on disk. Re-download Missing Files is off, so ${artist.unresolved_tracks === 1 ? 'it is' : 'they are'} being left alone instead of fetched again.</span>
                    </div>` : ''}
                    <div class="watched-card-settings">
                        <label class="watched-card-toggle" title="Follow this artist's new singles. Switch off to keep them as an albums-only follow.">
                            Singles
                            <div class="toggle-switch">
                                <input type="checkbox" id="artist-singles-toggle-${artist.id}" ${watchesSingles ? 'checked' : ''}
                                    ${uiAction('updateArtistSingles', [artist.id], 'change')}>
                                <span class="toggle-slider"></span>
                            </div>
                        </label>
                        ${watchesSingles ? `
                        <label class="watched-card-toggle" title="Singles released before this date are ignored. Move it back to pick up older releases, forward to quieten things down.">
                            From:
                            <input type="date" class="watched-card-date" value="${escapeAttr(artist.from_date || '')}"
                                ${uiAction('updateArtistFromDate', [artist.id], 'change')}>
                        </label>` : ''}
                        <label class="watched-card-toggle" title="Choose whether new singles keep their source format or are converted">
                            ${conversionChoiceLabel(artist.convert_audio)}
                            <div class="toggle-switch">
                                <input type="checkbox" ${artist.convert_audio ? 'checked' : ''}
                                    ${uiAction('updateArtistConversion', [artist.id], 'change')}>
                                <span class="toggle-slider"></span>
                            </div>
                        </label>
                        <label class="watched-card-toggle">
                            Check:
                            <select class="watched-card-select" ${uiAction('updateArtistInterval', [artist.id], 'change')}>
                                <option value="0.5" ${artist.refresh_interval_hours == 0.5 ? 'selected' : ''}>Every 30 min</option>
                                <option value="1" ${artist.refresh_interval_hours == 1 ? 'selected' : ''}>Hourly</option>
                                <option value="6" ${artist.refresh_interval_hours == 6 ? 'selected' : ''}>Every 6 hours</option>
                                <option value="12" ${artist.refresh_interval_hours == 12 ? 'selected' : ''}>Every 12 hours</option>
                                <option value="24" ${artist.refresh_interval_hours == 24 ? 'selected' : ''}>Daily</option>
                                <option value="168" ${artist.refresh_interval_hours == 168 ? 'selected' : ''}>Weekly</option>
                                <option value="720" ${artist.refresh_interval_hours == 720 ? 'selected' : ''}>Monthly</option>
                            </select>
                        </label>
                    </div>
                    <div id="artist-singles-start-${artist.id}" class="watched-singles-start" style="display:none;"></div>
                    <div class="watched-card-actions">
                        <button class="watched-action-btn" type="button"
                            data-action="refresh-watched-artist"
                            data-artist-id="${escapeAttr(artist.id)}"
                            ${isRunning ? 'disabled' : ''}>Refresh</button>
                        <button class="watched-action-btn" type="button"
                            data-action="toggle-artist-missing-tracks"
                            data-artist-id="${escapeAttr(artist.id)}">Missing</button>
                        <button class="watched-action-btn" type="button"
                            data-action="toggle-artist-track-list"
                            data-artist-id="${escapeAttr(artist.id)}"
                            data-artist-name="${escapeAttr(artist.name)}">Tracks</button>
                        ${singlesOnlyMode ? '' : `<button class="watched-action-btn" type="button"
                            data-action="toggle-artist-albums"
                            data-artist-id="${escapeAttr(artist.id)}">Albums</button>`}
                        <button class="watched-action-btn watched-action-pause" type="button"
                            data-action="toggle-watched-artist"
                            data-artist-id="${escapeAttr(artist.id)}"
                            data-enabled="${artist.enabled ? 'true' : 'false'}">${isPaused ? 'Resume' : 'Pause'}</button>
                        <button class="watched-action-btn watched-action-delete" type="button"
                            data-action="delete-watched-artist"
                            data-artist-id="${escapeAttr(artist.id)}"
                            data-artist-name="${escapeAttr(artist.name)}">Delete</button>
                    </div>
                    <div id="artist-missing-${artist.id}" class="watched-card-expanded" style="display:none;"></div>
                    <div id="artist-tracks-${artist.id}" class="watched-card-expanded" style="display:none;"></div>
                </div>`;
            }).join('');
            dropOpenPanelsBack(openPanels);
            if (window.scrollY !== scrollY) window.scrollTo(0, scrollY);

            if (anyRunning) {
                startArtistRefreshPolling();
            } else {
                stopArtistRefreshPolling();
                artistRefreshPending.clear();
            }
        }

        async function refreshWatchedArtist(artistId) {
            artistRefreshPending.set(artistId, { stage: 'starting', startedAt: new Date().toISOString() });
            loadWatchedArtists(false);
            try {
                const res = await apiFetch(`/api/watched-artists/${artistId}/refresh`, { method: 'POST' });
                const data = await res.json();
                if (data.already_running) {
                    showToast('Refresh already in progress');
                } else {
                    // Refresh runs in the background now; the card polls for progress.
                    showToast('Refresh started');
                }
            } catch (e) {
                showToast('Refresh failed', true);
                artistRefreshPending.delete(artistId);
            } finally {
                loadWatchedArtists();
            }
        }

        async function toggleWatchedArtist(artistId, enabled) {
            try {
                await apiFetch(`/api/watched-artists/${artistId}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ enabled })
                });
                loadWatchedArtists();
                showToast(enabled ? 'Artist watching resumed' : 'Artist watching paused');
            } catch (e) {
                showToast('Failed to update artist', true);
            }
        }

        async function updateArtistConversion(artistId, convertAudio) {
            try {
                await apiFetch(`/api/watched-artists/${artistId}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ convert_audio: convertAudio })
                });
            } catch (e) {
                showToast('Failed to update format setting', true);
                loadWatchedArtists();
            }
        }

        // Switching singles ON needs a date before it does anything, because the
        // stored from_date on an albums-only follow is simply the day you followed
        // them, which could be a year of singles ago. Ask first, send nothing until
        // asked; switching OFF is harmless and goes straight through.
        function updateArtistSingles(artistId, watchSingles) {
            const panel = document.getElementById(`artist-singles-start-${artistId}`);
            if (!watchSingles || !panel) return _sendArtistSingles(artistId, watchSingles);

            const today = new Date().toISOString().slice(0, 10);
            panel.style.display = 'block';
            panel.innerHTML = `
                <span class="watched-singles-start-label">Watch singles released from:</span>
                <input type="date" class="watched-card-date" id="artist-singles-from-${artistId}" value="${today}">
                <button class="watched-action-btn" type="button"
                    ${uiAction('confirmArtistSingles', [artistId])}>Start watching</button>
                <button class="watched-action-btn" type="button"
                    ${uiAction('cancelArtistSingles', [artistId])}>Cancel</button>`;
            document.getElementById(`artist-singles-from-${artistId}`)?.focus();
        }

        function cancelArtistSingles(artistId) {
            const panel = document.getElementById(`artist-singles-start-${artistId}`);
            if (panel) { panel.style.display = 'none'; panel.innerHTML = ''; }
            // Put the toggle back where it was, since nothing was actually saved.
            const toggle = document.getElementById(`artist-singles-toggle-${artistId}`);
            if (toggle) toggle.checked = false;
        }

        function confirmArtistSingles(artistId) {
            const input = document.getElementById(`artist-singles-from-${artistId}`);
            const fromDate = input ? input.value : '';
            if (!fromDate) {
                showToast('Pick a date first, otherwise there is nothing to start from.', true);
                return;
            }
            return _sendArtistSingles(artistId, true, fromDate);
        }

        async function updateArtistFromDate(artistId, fromDate) {
            if (!fromDate) return;
            try {
                const res = await apiFetch(`/api/watched-artists/${artistId}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ from_date: fromDate })
                });
                if (!res.ok) throw new Error('rejected');
                showToast(`Now watching singles released from ${fromDate}`);
            } catch (e) {
                showToast('Failed to update the singles start date', true);
            }
            loadWatchedArtists();
        }

        async function _sendArtistSingles(artistId, watchSingles, fromDate) {
            try {
                const payload = { watch_singles: watchSingles };
                if (fromDate) payload.from_date = fromDate;
                const res = await apiFetch(`/api/watched-artists/${artistId}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                // The server refuses to leave an artist following nothing at all,
                // so surface that rather than silently bouncing the toggle back.
                if (!res.ok) {
                    let detail = 'Failed to update singles following';
                    try { detail = (await res.json()).detail || detail; } catch (_) { /* keep the default */ }
                    showToast(detail, true);
                }
            } catch (e) {
                showToast('Failed to update singles following', true);
            }
            loadWatchedArtists();
        }

        async function updateArtistInterval(artistId, hours) {
            try {
                await apiFetch(`/api/watched-artists/${artistId}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ refresh_interval_hours: parseFloat(hours) })
                });
            } catch (e) {
                showToast('Failed to update interval', true);
                loadWatchedArtists();
            }
        }

        async function deleteWatchedArtist(artistId, name) {
            if (!confirm(`Stop watching "${name}"? Downloaded tracks will not be deleted.`)) return;
            try {
                await apiFetch(`/api/watched-artists/${artistId}`, { method: 'DELETE' });
                showToast(`Stopped watching "${name}"`);
                loadWatchedArtists();
            } catch (e) {
                showToast('Failed to delete artist', true);
            }
        }

        async function toggleArtistMissingTracks(artistId) {
            const panel = document.getElementById(`artist-missing-${artistId}`);
            if (panel.style.display !== 'none') { panel.style.display = 'none'; return; }
            panel.style.display = 'block';
            panel.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            try {
                const res = await apiFetch(`/api/watched-artists/${artistId}/missing`);
                const data = await res.json();
                if (!data.tracks || data.tracks.length === 0) {
                    panel.innerHTML = '<p style="font-size:12px;color:var(--text-secondary);padding:8px 0;">No missing singles.</p>';
                    return;
                }
                panel.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <span style="font-size:12px;color:var(--text-secondary);">${data.tracks.length} missing single(s)</span>
                        <button type="button"
                            data-action="retry-all-artist-missing"
                            data-artist-id="${escapeAttr(artistId)}"
                            style="padding:4px 12px;font-size:12px;font-family:inherit;font-weight:600;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;">
                            Queue All
                        </button>
                    </div>` +
                    data.tracks.map(t => `
                        <div style="padding:4px 0;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
                            <span style="flex:1;min-width:0;font-size:12px;">${escapeHtml(t.artist || '')} &ndash; ${escapeHtml(t.title)}</span>
                            <div style="display:flex;gap:4px;align-items:center;flex-shrink:0;">
                                ${t.release_date ? `<span style="font-size:11px;color:var(--text-secondary);white-space:nowrap;">${t.release_date}</span>` : ''}
                                <button type="button"
                                    data-action="retry-artist-track"
                                    data-artist-id="${escapeAttr(artistId)}"
                                    data-artist="${escapeAttr(t.artist || '')}"
                                    data-title="${escapeAttr(t.title)}"
                                    style="padding:3px 8px;font-size:11px;font-family:inherit;background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;cursor:pointer;white-space:nowrap;"
                                    title="Auto-search and re-queue this track">Retry</button>
                            </div>
                        </div>`).join('');
            } catch (e) {
                panel.innerHTML = '<p style="font-size:12px;color:var(--error);">Failed to load missing tracks.</p>';
            }
        }

        const ARTIST_TRACKS_PAGE_SIZE = 50;

        async function toggleArtistTrackList(artistId, artistName) {
            const panel = document.getElementById(`artist-tracks-${artistId}`);
            if (panel.style.display !== 'none') { panel.style.display = 'none'; return; }
            panel.style.display = 'block';
            await loadArtistTrackPage(artistId, 0);
        }

        // Prolific artists run to hundreds of singles, so the track list is paged
        // ('cycles'). Prev/Next reload the panel at a new offset.
        async function loadArtistTrackPage(artistId, offset) {
            const panel = document.getElementById(`artist-tracks-${artistId}`);
            if (!panel) return;
            offset = Math.max(0, offset);
            panel.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            try {
                const res = await apiFetch(`/api/watched-artists/${artistId}/tracks?limit=${ARTIST_TRACKS_PAGE_SIZE}&offset=${offset}`);
                const data = await res.json();
                const total = data.total || 0;
                if (total === 0) {
                    panel.innerHTML = '<p style="font-size:12px;color:var(--text-secondary);padding:8px 0;">No tracks tracked yet.</p>';
                    return;
                }
                const tracksHtml = (data.tracks || []).map(t => {
                    const statusIcon = t.downloaded_at
                        ? '<i class="fa-solid fa-check" style="color:var(--success);"></i>'
                        : t.job_status === 'queued' || t.job_status === 'downloading'
                            ? '<i class="fa-solid fa-clock" style="color:var(--text-secondary);"></i>'
                            : '<i class="fa-solid fa-xmark" style="color:var(--error);"></i>';
                    const dlBtn = t.downloaded_at && t.job_id
                        ? `<button type="button"
                            data-action="save-job-to-device"
                            data-job-id="${escapeAttr(t.job_id)}"
                            style="padding:2px 8px;font-size:11px;font-family:inherit;background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;cursor:pointer;white-space:nowrap;"><i class="fa-solid fa-download"></i></button>`
                        : '';
                    return `<div style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12px;">
                        ${statusIcon}
                        <span style="flex:1;">${escapeHtml(t.artist || '')} &ndash; ${escapeHtml(t.title)}</span>
                        ${t.release_date ? `<span style="color:var(--text-secondary);font-size:11px;">${t.release_date}</span>` : ''}
                        ${dlBtn}
                    </div>`;
                }).join('');

                const start = offset + 1;
                const end = Math.min(offset + ARTIST_TRACKS_PAGE_SIZE, total);
                const hasPrev = offset > 0;
                const hasNext = end < total;
                const btnStyle = 'padding:3px 10px;font-size:11px;font-family:inherit;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:4px;cursor:pointer;';
                const pager = total > ARTIST_TRACKS_PAGE_SIZE
                    ? `<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:8px;">
                            <button type="button" ${hasPrev ? '' : 'disabled'} ${uiAction('loadArtistTrackPage', [artistId, offset - ARTIST_TRACKS_PAGE_SIZE])} style="${btnStyle}${hasPrev ? '' : 'opacity:0.4;cursor:default;'}">&larr; Prev</button>
                            <span style="font-size:11px;color:var(--text-secondary);">${start}&ndash;${end} of ${total}</span>
                            <button type="button" ${hasNext ? '' : 'disabled'} ${uiAction('loadArtistTrackPage', [artistId, offset + ARTIST_TRACKS_PAGE_SIZE])} style="${btnStyle}${hasNext ? '' : 'opacity:0.4;cursor:default;'}">Next &rarr;</button>
                        </div>`
                    : '';

                panel.innerHTML = `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:8px;">${total} single(s) tracked:</div>` + tracksHtml + pager;
            } catch (e) {
                panel.innerHTML = '<p style="font-size:12px;color:var(--error);">Failed to load tracks.</p>';
            }
        }

        async function retryArtistTrack(artistId, artist, title, btn) {
            btn.disabled = true;
            btn.textContent = 'Queued';
            try {
                await apiFetch(`/api/watched-artists/${artistId}/retry-track`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ artist, title })
                });
                showToast(`Queued: ${artist} - ${title}`);
            } catch (e) {
                btn.disabled = false;
                btn.textContent = 'Retry';
                showToast('Retry failed', true);
            }
        }

        async function retryAllArtistMissing(artistId, btn) {
            btn.disabled = true;
            btn.textContent = 'Queuing...';
            try {
                const res = await apiFetch(`/api/watched-artists/${artistId}/retry-all-missing`, { method: 'POST' });
                const data = await res.json();
                showToast(`Queued ${data.queued} track(s)`);
                btn.textContent = `${data.queued} queued`;
                // Disable all individual retry buttons too
                const panel = document.getElementById(`artist-missing-${artistId}`);
                if (panel) panel.querySelectorAll('button[data-action="retry-artist-track"]').forEach(b => { b.disabled = true; b.textContent = 'Queued'; });
            } catch (e) {
                btn.disabled = false;
                btn.textContent = 'Queue All';
                showToast('Failed to queue tracks', true);
            }
        }

        async function refreshAllArtists() {
            const btn = document.getElementById('refreshAllArtistsBtn');
            btn.disabled = true;
            try {
                const res = await apiFetch('/api/watched-artists/check-all', { method: 'POST' });
                const data = await res.json();
                if (data.checked === 0) {
                    showToast('No artists due for refresh');
                } else {
                    showToast(`Checked ${data.checked} artist(s), ${data.total_new_tracks} new single(s) found`);
                }
                loadWatchedArtists();
            } catch (e) {
                showToast('Check failed', true);
            } finally {
                btn.disabled = false;
            }
        }

        // Event listeners for watched artists
        document.getElementById('searchArtistBtn').addEventListener('click', searchArtist);
        document.getElementById('artistSearchInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') searchArtist();
        });
        document.getElementById('addArtistBtn').addEventListener('click', addWatchedArtist);
        document.getElementById('refreshAllArtistsBtn').addEventListener('click', refreshAllArtists);

        // The three-way chooser. Cancel on any panel goes back to a clean slate
        // rather than to the previous panel; half-open forms are nobody's friend.
        document.querySelectorAll('#artistModeChooser [data-artist-mode]').forEach(btn => {
            btn.addEventListener('click', () => chooseArtistMode(btn.dataset.artistMode));
        });
        for (const id of ['cancelArtistBtn', 'cancelArtistChooserBtn',
                          'cancelArtistAlbumsBtn', 'cancelArtistOneOffBtn']) {
            document.getElementById(id)?.addEventListener('click', resetArtistChooser);
        }

        document.getElementById('artistAlbumBatchBtn')?.addEventListener('click', followArtistForAlbums);
        document.getElementById('artistAlbumSelectAllBtn')?.addEventListener('click', () => {
            document.querySelectorAll('#artistAlbumChecklist input[type="checkbox"]')
                .forEach(cb => { cb.checked = true; });
            updateAlbumChecklistCount();
        });
        document.getElementById('artistAlbumSelectNoneBtn')?.addEventListener('click', () => {
            document.querySelectorAll('#artistAlbumChecklist input[type="checkbox"]')
                .forEach(cb => { cb.checked = false; });
            updateAlbumChecklistCount();
        });

        // -----------------------------------------------------------------------
        // Per-artist album panel: one shared mount, re-targeted to whichever
        // followed artist's "Albums" button was last tapped. Backs onto the
        // shared album browser from the "Shared album browser" section above.
        // -----------------------------------------------------------------------

        let artistAlbumBrowserHandle = null;

        function openArtistAlbumPanel(artistId) {
            const artist = watchedArtistsById.get(artistId);
            const panel = document.getElementById('artistAlbumPanel');
            const heading = document.getElementById('artistAlbumPanelHeading');
            const autoAddToggle = document.getElementById('artistAutoAddToggle');
            const mountEl = document.getElementById('artistAlbumBrowserMount');
            if (!artist || !panel || !mountEl) return;

            panel.style.display = 'block';
            panel.dataset.artistId = artistId;
            if (heading) heading.textContent = `Albums by ${artist.name}`;
            // auto_add_albums may not exist yet on this deployment; default unchecked.
            if (autoAddToggle) autoAddToggle.checked = !!artist.auto_add_albums;

            loadArtistKnownAlbums(artistId);

            if (artistAlbumBrowserHandle) {
                artistAlbumBrowserHandle.setArtist(artist.mbid, artist.name);
            } else {
                artistAlbumBrowserHandle = mountAlbumBrowser(mountEl, {
                    artist: { mbid: artist.mbid, name: artist.name },
                    showArtistSearch: false,
                    onQueued: () => {
                        const pid = document.getElementById('artistAlbumPanel')?.dataset.artistId;
                        if (pid) loadArtistKnownAlbums(pid);
                    },
                });
            }

            panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        async function loadArtistKnownAlbums(artistId) {
            const el = document.getElementById('artistKnownAlbums');
            if (!el) return;
            el.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            try {
                const res = await apiFetch(`/api/watched-artists/${artistId}/albums`);
                if (!res.ok) {
                    // Not landed on this deployment yet (or a genuine error) - degrade
                    // quietly rather than spamming the console, the browser below still works.
                    el.innerHTML = '<p style="font-size:12px;color:var(--text-secondary);padding:4px 0;">Album status tracking isn’t available yet.</p>';
                    return;
                }
                const data = await res.json();
                const albums = data.albums || [];
                if (!albums.length) {
                    el.innerHTML = '<p style="font-size:12px;color:var(--text-secondary);padding:4px 0;">No albums seen yet.</p>';
                    return;
                }
                const statusLabel = {
                    seen: 'Seen',
                    queued: 'Queued',
                    processing: 'Retrying',
                    downloading: 'Downloading',
                    cancelling: 'Cancelling',
                    complete: 'Complete',
                    on_disk: 'On disk',
                    incomplete: 'Incomplete',
                    cancelled: 'Cancelled',
                    failed: 'Failed',
                };
                el.innerHTML = albums.map(a => `
                    <div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px;">
                        <span style="flex:1;">${escapeHtml(a.title)}${a.year ? ` <span style="color:var(--text-secondary);">(${escapeHtml(String(a.year))})</span>` : ''}</span>
                        ${a.display_status === 'complete' || a.display_status === 'on_disk'
                            ? `<i class="fa-solid fa-check" style="color:var(--success);" title="${escapeHtml(a.status_detail || 'On disk')}"></i>`
                            : a.display_status === 'incomplete'
                                ? `<i class="fa-solid fa-triangle-exclamation" style="color:var(--warning);" title="${escapeHtml(a.status_detail || 'Incomplete album')}"></i>`
                                : ''}
                        <span title="${escapeHtml(a.status_detail || '')}" style="color:${a.display_status === 'complete' || a.display_status === 'on_disk' ? 'var(--success)' : a.display_status === 'incomplete' || a.display_status === 'failed' ? 'var(--warning)' : 'var(--text-secondary)'};">${escapeHtml(statusLabel[a.display_status] || a.display_status || statusLabel[a.status] || a.status || '')}</span>
                    </div>
                `).join('');
            } catch (e) {
                el.innerHTML = '<p style="font-size:12px;color:var(--text-secondary);padding:4px 0;">Album status tracking isn’t available yet.</p>';
            }
        }

        document.getElementById('artistAlbumPanelCloseBtn')?.addEventListener('click', () => {
            const panel = document.getElementById('artistAlbumPanel');
            if (panel) panel.style.display = 'none';
        });

        document.getElementById('artistAutoAddToggle')?.addEventListener('change', async (e) => {
            const panel = document.getElementById('artistAlbumPanel');
            const artistId = panel?.dataset.artistId;
            if (!artistId) return;
            const checked = e.target.checked;
            try {
                await apiFetch(`/api/watched-artists/${artistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ auto_add_albums: checked }),
                });
                showToast(checked
                    ? 'New albums will be added automatically from now on (the back catalogue is left alone)'
                    : 'Automatic album adding switched off');
            } catch (err) {
                showToast('Failed to update album setting', true);
                e.target.checked = !checked;
            }
        });
