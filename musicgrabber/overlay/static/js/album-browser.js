        // The shared album browser (artist -> albums -> tracks), mounted by the
        // Tracks tab's album links, Bulk Import and the Artists tab.

        // =============================================================
        // Shared album browser
        // =============================================================
        // Search artist -> pick artist -> list albums -> pick album ->
        // tracklist with existing/missing legend -> M3U toggle -> download ->
        // progress. Used to be the whole of the old Albums tab; now it is a
        // mountable component so the Artists tab (and, from Bulk Import
        // onwards, another agent's tab) can each get their own independent
        // instance without stepping on each other's state.
        //
        // mountAlbumBrowser(containerEl, options) -> handle
        //   options.artist            {mbid, name} to pre-select, skipping the
        //                              search step (used when pinning to a
        //                              followed artist)
        //   options.showArtistSearch  show the artist search box; false when
        //                              options.artist pins the browser to one
        //                              artist and searching elsewhere makes no
        //                              sense (default true)
        //   options.onQueued          callback(data) fired once
        //                              POST /api/albums/download succeeds
        //
        //   handle.setArtist(mbid, name)  programmatically select an artist
        //   handle.openAlbum(opts)        the Tracks-tab handoff entry point;
        //                                 opts: {artistName, albumTitle, artistMbid?, releaseMbid?}
        //   handle.hasSelection()         true if the user has already started
        //                                 a search or picked something, so
        //                                 callers know not to clobber it
        //   handle.searchFor(name)        fills the artist search box and runs
        //                                 the search (only when showArtistSearch)
        //   handle.reset()                back to a blank form (pinned artist
        //                                 mode returns to that artist's album list)
        //   handle.destroy()              stop polling and empty the container

        let _albumBrowserInstanceCounter = 0;

        function mountAlbumBrowser(containerEl, options = {}) {
            if (!containerEl) return null;
            const {
                artist = null,
                showArtistSearch = true,
                onQueued = null,
            } = options;

            const uid = `ab${++_albumBrowserInstanceCounter}`;
            const eid = (name) => `${uid}-${name}`;

            containerEl.innerHTML = `
                ${showArtistSearch ? `
                <div class="search-box">
                    <input type="text" id="${eid('artistInput')}" class="search-input" placeholder="Search for an artist…" autocomplete="off">
                    <button id="${eid('artistSearchBtn')}" class="btn btn-primary search-btn">Search</button>
                </div>
                <div class="album-search-note">
                    Albums come down whole where they can, from Usenet, a Soulseek folder or a torrent, whichever you have switched on. Anything still missing is found track by track, so the odd song may come from a different pressing.
                </div>
                ` : ''}
                <div id="${eid('artistResults')}" class="album-artist-results" style="display:none;"></div>

                <div id="${eid('listSection')}" style="display:none;">
                    <h3 class="album-section-heading" id="${eid('listHeading')}"></h3>
                    <div id="${eid('list')}" class="album-list"></div>
                </div>

                <div id="${eid('tracklistSection')}" style="display:none;">
                    <h3 class="album-section-heading" id="${eid('tracklistHeading')}"></h3>
                    <div id="${eid('existingWarning')}" class="album-existing-warning" style="display:none;"></div>
                    <div id="${eid('trackLegend')}" class="album-track-legend" style="display:none;"></div>
                    <button id="${eid('tickAllBtn')}" class="btn btn-ghost btn-sm album-tick-all-btn" type="button" style="display:none;">Untick all</button>
                    <ol id="${eid('tracklist')}" class="album-tracklist"></ol>
                    <div class="bulk-playlist-row">
                        <input type="checkbox" id="${eid('makeM3u')}">
                        <label for="${eid('makeM3u')}">Generate M3U playlist</label>
                    </div>
                    <div id="${eid('m3uHint')}" class="album-m3u-hint" style="display:none;"></div>
                    <div id="${eid('atmosRow')}" class="bulk-playlist-row" style="display:none;">
                        <input type="checkbox" id="${eid('atmos')}">
                        <label for="${eid('atmos')}">Also the Dolby Atmos version, if Usenet or torrents have one</label>
                    </div>
                    <button id="${eid('downloadBtn')}" class="btn btn-primary btn-lg btn-block bulk-import-btn album-download-btn">
                        Download Album
                    </button>
                    <button id="${eid('resetBtn')}" class="btn btn-ghost album-reset-btn" type="button">
                        ${showArtistSearch ? 'Search Another Album' : 'Pick Another Album'}
                    </button>
                </div>

                <div id="${eid('progress')}" class="album-download-progress" style="display:none;"></div>
            `;

            const els = {
                artistInput: document.getElementById(eid('artistInput')),
                artistSearchBtn: document.getElementById(eid('artistSearchBtn')),
                artistResults: document.getElementById(eid('artistResults')),
                listSection: document.getElementById(eid('listSection')),
                list: document.getElementById(eid('list')),
                listHeading: document.getElementById(eid('listHeading')),
                tracklistSection: document.getElementById(eid('tracklistSection')),
                tracklistHeading: document.getElementById(eid('tracklistHeading')),
                existingWarning: document.getElementById(eid('existingWarning')),
                trackLegend: document.getElementById(eid('trackLegend')),
                tracklist: document.getElementById(eid('tracklist')),
                tickAllBtn: document.getElementById(eid('tickAllBtn')),
                makeM3u: document.getElementById(eid('makeM3u')),
                m3uHint: document.getElementById(eid('m3uHint')),
                atmosRow: document.getElementById(eid('atmosRow')),
                atmos: document.getElementById(eid('atmos')),
                downloadBtn: document.getElementById(eid('downloadBtn')),
                resetBtn: document.getElementById(eid('resetBtn')),
                progress: document.getElementById(eid('progress')),
            };

            const state = {
                selectedArtist: artist ? { mbid: artist.mbid, name: artist.name } : null,
                selectedRelease: null,
                selectedM3uName: null,
                pollInterval: null,
                // Set once Download is pressed, so a late tick cannot re-arm it.
                picksLocked: false,
            };

            function setResetVisible(visible) {
                if (els.resetBtn) els.resetBtn.classList.toggle('show', !!visible);
            }

            async function _readApiErrorDetail(resp) {
                // FastAPI puts errors in {detail: "..."}. Fall back to the status line if
                // the body is empty / not JSON.
                try {
                    const data = await resp.json();
                    if (data && data.detail) return String(data.detail);
                } catch {}
                return `HTTP ${resp.status}`;
            }

            function _renderRetryError(node, message, onRetry, asListItem = false) {
                if (!node) return;
                const wrap = document.createElement(asListItem ? 'li' : 'p');
                if (!asListItem) wrap.className = 'bulk-intro-text error-text';
                else wrap.className = 'album-track-item album-track-error';
                wrap.textContent = message + ' ';
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'album-retry-btn';
                btn.textContent = 'Retry';
                btn.addEventListener('click', () => { onRetry(); });
                wrap.appendChild(btn);
                node.innerHTML = '';
                node.appendChild(wrap);
            }

            function findMatchingAlbum(albums, searchTitle) {
                if (!searchTitle || !albums.length) return null;
                function normalise(s) {
                    return s.toLowerCase()
                        .replace(/\s*\(.*?\)\s*/g, ' ')
                        .replace(/\s*\[.*?\]\s*/g, ' ')
                        .replace(/[^\w\s]/g, '')
                        .replace(/\s+/g, ' ')
                        .trim();
                }
                const norm = normalise(searchTitle);
                for (const a of albums) if (a.title.toLowerCase() === searchTitle.toLowerCase()) return a;
                for (const a of albums) if (normalise(a.title) === norm) return a;
                for (const a of albums) {
                    const na = normalise(a.title);
                    if (na && norm && (na.includes(norm) || norm.includes(na))) return a;
                }
                return null;
            }

            async function searchArtist() {
                const q = els.artistInput ? els.artistInput.value.trim() : '';
                if (!q || !els.artistResults) return;

                els.artistResults.innerHTML = `<p class="bulk-intro-text">${escapeHtml(_musicbrainzQuip())}…</p>`;
                els.artistResults.style.display = '';
                if (els.listSection) els.listSection.style.display = 'none';
                if (els.tracklistSection) els.tracklistSection.style.display = 'none';
                if (els.progress) els.progress.style.display = 'none';
                setResetVisible(false);
                state.selectedArtist = null;
                state.selectedRelease = null;
                state.selectedM3uName = null;
                if (state.pollInterval) { clearInterval(state.pollInterval); state.pollInterval = null; }
                if (els.downloadBtn) { els.downloadBtn.disabled = false; els.downloadBtn.textContent = 'Download Album'; }

                try {
                    const resp = await apiFetch(`/api/albums/search-artist?q=${encodeURIComponent(q)}`);
                    if (!resp.ok) {
                        const detail = await _readApiErrorDetail(resp);
                        _renderRetryError(els.artistResults, `Search failed: ${detail}`, searchArtist);
                        return;
                    }
                    const data = await resp.json();
                    const artists = data.artists || [];
                    if (!artists.length) {
                        els.artistResults.innerHTML = '<p class="bulk-intro-text">No artists found.</p>';
                        return;
                    }
                    els.artistResults.innerHTML = '';
                    for (const a of artists) {
                        const btn = document.createElement('button');
                        btn.className = 'album-artist-btn';
                        btn.innerHTML = `<span class="album-artist-name">${escapeHtml(a.name)}</span>`
                            + (a.disambiguation ? ` <span class="album-artist-disambig">${escapeHtml(a.disambiguation)}</span>` : '');
                        btn.addEventListener('click', () => selectArtist(a, btn));
                        els.artistResults.appendChild(btn);
                    }
                } catch (e) {
                    _renderRetryError(els.artistResults, `Search failed: ${e.message}`, searchArtist);
                }
            }

            async function loadAlbums(a) {
                try {
                    const resp = await apiFetch(`/api/albums/artist/${encodeURIComponent(a.mbid)}/albums`);
                    if (!resp.ok) {
                        const detail = await _readApiErrorDetail(resp);
                        _renderRetryError(els.list, `Failed to load albums: ${detail}`, () => loadAlbums(a));
                        return;
                    }
                    const data = await resp.json();
                    const albums = data.albums || [];
                    if (!els.list) return albums;
                    if (!albums.length) {
                        els.list.innerHTML = '<p class="bulk-intro-text">No albums found.</p>';
                        return albums;
                    }
                    els.list.innerHTML = '';
                    const artworkTargets = [];
                    for (const album of albums) {
                        const albumBtn = document.createElement('button');
                        albumBtn.className = 'album-list-btn';
                        // EPs sit in this list alongside albums, so say so; some
                        // artists are basically all EPs and an untagged list of
                        // six identical-looking entries helps nobody.
                        albumBtn.innerHTML = '<div class="album-list-thumb"></div>'
                            + `<span class="album-list-title">${escapeHtml(album.title)}</span>`
                            + (album.year ? ` <span class="album-list-year">${escapeHtml(album.year)}</span>` : '')
                            + (album.primary_type === 'EP' ? ' <span class="album-list-year">(EP)</span>' : '');
                        albumBtn.addEventListener('click', () => selectAlbum(album, albumBtn));
                        els.list.appendChild(albumBtn);
                        artworkTargets.push({ thumbEl: albumBtn.querySelector('.album-list-thumb'), title: album.title });
                    }
                    // Text is on screen already; covers trickle in behind it so a
                    // slow iTunes/Deezer lookup never holds up the album list.
                    fetchAlbumListArtwork(artworkTargets, a.name);
                    return albums;
                } catch (e) {
                    _renderRetryError(els.list, `Failed to load albums: ${e.message}`, () => loadAlbums(a));
                }
            }

            async function selectArtist(a, btn) {
                state.selectedArtist = a;
                state.selectedRelease = null;
                state.selectedM3uName = null;
                containerEl.querySelectorAll('.album-artist-btn').forEach(b => b.classList.remove('selected'));
                if (btn) btn.classList.add('selected');

                if (els.listSection) els.listSection.style.display = 'block';
                if (els.tracklistSection) els.tracklistSection.style.display = 'none';
                setResetVisible(false);
                if (els.listHeading) els.listHeading.textContent = `Albums by ${a.name}`;
                if (els.list) els.list.innerHTML = `<p class="bulk-intro-text">${escapeHtml(_musicbrainzQuip())}…</p>`;

                await loadAlbums(a);
            }

            // The tick boxes of tracks that would download, in tracklist order.
            function trackPickBoxes() {
                return Array.from(els.tracklist.querySelectorAll('.album-track-pick:not(:disabled)'));
            }

            // Download takes the ticked tracks; the button says how many when
            // that is not the whole album, and refuses when it is none at all.
            function updateTrackPicks() {
                if (state.picksLocked) return;
                const boxes = trackPickBoxes();
                const ticked = boxes.filter(cb => cb.checked).length;
                if (els.tickAllBtn) {
                    els.tickAllBtn.style.display = boxes.length > 1 ? '' : 'none';
                    els.tickAllBtn.textContent = ticked === boxes.length ? 'Untick all' : 'Tick all';
                }
                if (!els.downloadBtn) return;
                els.downloadBtn.disabled = boxes.length > 0 && ticked === 0;
                els.downloadBtn.textContent = ticked === boxes.length
                    ? 'Download Album'
                    : ticked === 0
                        ? 'Tick a track to download'
                        : `Download ${ticked} Track${ticked === 1 ? '' : 's'}`;
            }

            // null when every track that would download is ticked, which asks
            // for the whole album just as it always has.
            function pickedTrackIndexes() {
                const boxes = trackPickBoxes();
                if (boxes.every(cb => cb.checked)) return null;
                return boxes.filter(cb => cb.checked).map(cb => Number(cb.dataset.trackIndex));
            }

            function renderAlbumTracks(album, tracks, statusData = null) {
                // Keep what was unticked while the on-disk check was running.
                const unticked = new Set(trackPickBoxes().filter(cb => !cb.checked).map(cb => cb.dataset.trackIndex));
                els.tracklist.innerHTML = '';
                tracks.forEach((track, index) => {
                    const li = document.createElement('li');
                    li.className = 'album-track-item';
                    if (statusData) li.classList.add(track.exists ? 'album-track-existing' : 'album-track-missing');
                    if (track.in_library) li.title = 'Already in your library, outside this album\'s folder';
                    const pick = document.createElement('label');
                    pick.className = 'album-track-pick-label';
                    const cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.className = 'album-track-pick';
                    cb.dataset.trackIndex = String(index);
                    // On disk already: Download never fetches it, so there is nothing to tick.
                    const onDisk = Boolean(statusData && track.exists);
                    cb.disabled = onDisk;
                    cb.checked = !onDisk && !unticked.has(String(index));
                    cb.addEventListener('change', updateTrackPicks);
                    const title = document.createElement('span');
                    title.className = 'album-track-title';
                    const disc = (track.disc_total || 1) > 1 ? `Disc ${track.disc_number}, ${track.position}. ` : '';
                    title.textContent = disc + track.title;
                    pick.appendChild(cb);
                    pick.appendChild(title);
                    li.appendChild(pick);
                    // Replacing a track means finding it again on a MusicBrainz release.
                    if (album.source_album_id) { els.tracklist.appendChild(li); return; }
                    const repairBtn = document.createElement('button');
                    repairBtn.type = 'button';
                    repairBtn.className = 'btn btn-ghost btn-sm album-track-repair-btn';
                    repairBtn.textContent = 'Search replacement';
                    repairBtn.setAttribute('aria-label', `Search replacement for ${disc}${track.title}`);
                    // Wait for the on-disk pressing and destination before enabling.
                    repairBtn.disabled = !statusData;
                    repairBtn.addEventListener('click', () => startAlbumTrackRepair({
                        artist: statusData.artist || state.selectedArtist.name,
                        album_title: statusData.album_title || album.title,
                        release_mbid: statusData.release_mbid || album.release_mbid,
                        track_index: index,
                        album_dir: statusData.album_dir,
                        track_title: track.title,
                        disc_number: track.disc_number || 1,
                        track_number: Number(track.position) || index + 1,
                    }, track, repairBtn));
                    li.appendChild(repairBtn);
                    els.tracklist.appendChild(li);
                });
            }

            async function selectAlbum(album, btn) {
                state.selectedRelease = album;
                state.picksLocked = false;
                containerEl.querySelectorAll('.album-list-btn').forEach(b => b.classList.remove('selected'));
                if (btn) btn.classList.add('selected');

                if (els.downloadBtn) { els.downloadBtn.disabled = false; els.downloadBtn.textContent = 'Download Album'; }
                setResetVisible(false);
                if (els.existingWarning) { els.existingWarning.style.display = 'none'; els.existingWarning.textContent = ''; }
                if (els.trackLegend) { els.trackLegend.style.display = 'none'; els.trackLegend.textContent = ''; }
                state.selectedM3uName = null;
                if (els.makeM3u) els.makeM3u.checked = false;
                if (els.m3uHint) { els.m3uHint.style.display = 'none'; els.m3uHint.textContent = ''; }
                if (els.atmos) els.atmos.checked = false;
                // Usenet and torrents look for an Atmos release by MusicBrainz's album.
                if (els.atmosRow) els.atmosRow.style.display = atmosAvailable && !album.source_album_id ? '' : 'none';
                if (els.tracklistSection) els.tracklistSection.style.display = 'block';
                if (els.tracklistHeading) els.tracklistHeading.textContent = `${album.title}${album.year ? ' (' + album.year + ')' : ''}`;
                if (els.tracklist) els.tracklist.innerHTML = '<li>Loading…</li>';
                if (els.tickAllBtn) els.tickAllBtn.style.display = 'none';
                if (els.downloadBtn) els.downloadBtn.disabled = true;

                try {
                    // The list only knows the release-group; the specific pressing
                    // to download is resolved here, lazily, for the one album the
                    // user actually opened (see fetch_artist_albums for why).
                    const resp = album.source_album_id
                        ? await apiFetch(`/api/albums/source/${encodeURIComponent(album.source_id)}/${encodeURIComponent(album.source_album_id)}/tracks`)
                        : album.release_mbid
                            ? await apiFetch(`/api/albums/release/${encodeURIComponent(album.release_mbid)}/tracks`)
                            : await apiFetch(`/api/albums/release-group/${encodeURIComponent(album.release_group_mbid)}/tracks`);
                    if (!resp.ok) {
                        const detail = await _readApiErrorDetail(resp);
                        _renderRetryError(els.tracklist, `Failed to load tracklist: ${detail}`, () => selectAlbum(album, btn), true);
                        return;
                    }
                    const data = await resp.json();
                    if (state.selectedRelease !== album) return;
                    if (!album.release_mbid && data.release_mbid) album.release_mbid = data.release_mbid;
                    const tracks = data.tracks || [];
                    if (!els.tracklist) return;
                    if (!tracks.length) {
                        els.tracklist.innerHTML = '<li>No tracks found.</li>';
                        return;
                    }
                    renderAlbumTracks(album, tracks);
                    if (state.selectedArtist && els.existingWarning) {
                        try {
                            const params = new URLSearchParams({
                                artist: state.selectedArtist.name,
                                album_title: album.title,
                            });
                            const statusResp = await apiFetch(album.source_album_id
                                ? `/api/albums/source/${encodeURIComponent(album.source_id)}/${encodeURIComponent(album.source_album_id)}/missing?${params.toString()}`
                                : `/api/albums/release/${encodeURIComponent(album.release_mbid)}/missing?${params.toString()}`
                            );
                            if (!statusResp.ok) throw new Error(await _readApiErrorDetail(statusResp));
                            if (statusResp.ok) {
                                const statusData = await statusResp.json();
                                if (state.selectedRelease !== album) return;
                                if (statusData.release_mbid) album.release_mbid = statusData.release_mbid;
                                const existing = Number(statusData.existing_count || 0);
                                const missing = Number(statusData.missing_count || 0);
                                const total = Number(statusData.total_tracks || tracks.length || 0);

                                if (Array.isArray(statusData.tracks)) renderAlbumTracks(album, statusData.tracks, statusData);

                                if (els.trackLegend && existing > 0) {
                                    els.trackLegend.style.display = 'block';
                                    els.trackLegend.innerHTML = `<span class="missing">Green</span> = missing (will queue) &nbsp;·&nbsp; <span class="existing">dim</span> = already on disk`;
                                }

                                // Albums as individual tracks: some of the songs live elsewhere in the library.
                                const elsewhere = Array.isArray(statusData.tracks)
                                    ? statusData.tracks.filter(t => t.in_library).length : 0;
                                if (existing > 0 && elsewhere > 0) {
                                    els.existingWarning.style.display = 'block';
                                    els.existingWarning.textContent = missing <= 0
                                        ? `All ${total} tracks are already in your library. Download will queue nothing.`
                                        : `${existing}/${total} track(s) are already in your library. Only ${missing} missing track(s) will be queued.`;
                                } else if (existing > 0) {
                                    els.existingWarning.style.display = 'block';
                                    if (missing <= 0) {
                                        els.existingWarning.textContent = `Album already exists in ${statusData.album_dir} (${existing}/${total} tracks). Download will queue nothing.`;
                                    } else {
                                        els.existingWarning.textContent = `${existing}/${total} track(s) already exist in ${statusData.album_dir}. Only ${missing} missing track(s) will be queued.`;
                                    }
                                }

                                const m3uFiles = Array.isArray(statusData.existing_m3u_files) ? statusData.existing_m3u_files : [];
                                if (statusData.has_existing_m3u && m3uFiles.length > 0) {
                                    state.selectedM3uName = m3uFiles[0];
                                    if (els.makeM3u) els.makeM3u.checked = true;
                                    if (els.m3uHint) {
                                        els.m3uHint.style.display = 'block';
                                        els.m3uHint.textContent = `Existing M3U found (${state.selectedM3uName}) - this will be updated.`;
                                    }
                                }
                            }
                        } catch (e) {
                            if (state.selectedRelease !== album) return;
                            els.existingWarning.style.display = 'block';
                            _renderRetryError(els.existingWarning, `Could not verify the album folder for replacement: ${e.message}`, () => selectAlbum(album, btn));
                        }
                    }
                    updateTrackPicks();
                } catch (e) {
                    _renderRetryError(els.tracklist, `Failed to load tracklist: ${e.message}`, () => selectAlbum(album, btn), true);
                }
            }

            function renderProgress(data) {
                const done = data.completed || 0;
                const total = data.total_tracks || 0;
                const failed = data.failed || 0;
                const pct = total > 0 ? Math.round((done / total) * 100) : 0;
                // Until the tracks have jobs, the album as a whole may be busy (a
                // Usenet release downloading), and 0/11 would look like nothing is.
                const statusText = data.complete
                    ? `Done: ${done}/${total} tracks${failed ? `, ${failed} failed` : ''}`
                    : (data.stage || `Downloading: ${done}/${total} tracks…`);
                return `<div class="bulk-progress-bar-container"><div class="bulk-progress-bar" style="width:${pct}%"></div></div>`
                    + `<p class="bulk-intro-text">${escapeHtml(statusText)}</p>`;
            }

            async function downloadAlbum() {
                if (!state.selectedArtist || !state.selectedRelease) return;
                const makeM3u = els.makeM3u?.checked || false;
                const atmos = Boolean(els.atmos?.checked && els.atmosRow?.style.display !== 'none');
                const trackIndexes = pickedTrackIndexes();
                const pickBoxes = trackPickBoxes();
                state.picksLocked = true;
                pickBoxes.forEach(cb => { cb.disabled = true; });
                if (els.tickAllBtn) els.tickAllBtn.style.display = 'none';
                setResetVisible(false);
                if (els.downloadBtn) { els.downloadBtn.disabled = true; els.downloadBtn.textContent = 'Queuing…'; }

                try {
                    const resp = await apiFetch('/api/albums/download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            artist: state.selectedArtist.name,
                            album_title: state.selectedRelease.title,
                            release_mbid: state.selectedRelease.release_mbid || '',
                            source_id: state.selectedRelease.source_id || null,
                            source_album_id: state.selectedRelease.source_album_id || null,
                            make_m3u: makeM3u,
                            m3u_name: makeM3u ? (state.selectedM3uName || null) : null,
                            convert_audio: convertAudioCheckbox.checked,
                            atmos,
                            track_indexes: trackIndexes,
                        }),
                    });
                    if (!resp.ok) {
                        const err = await resp.json().catch(() => ({}));
                        throw new Error(err.detail || 'Download failed');
                    }
                    const data = await resp.json();
                    // The Atmos version is its own import with its own line in the Queue.
                    const atmosNote = data.atmos_import_id
                        ? `Also looking for the Dolby Atmos version, into <code>${escapeHtml(data.atmos_dir)}</code>; it has its own line in the Queue.`
                        : (data.atmos_warning ? escapeHtml(data.atmos_warning) : '');
                    const atmosLine = atmosNote ? `<p class="settings-hint-sm" style="margin:0 0 8px;">${atmosNote}</p>` : '';
                    if (els.progress) {
                        els.progress.style.display = 'block';
                        const warningLine = data.warning
                            ? `<p class="settings-hint-sm" style="margin:0 0 8px;">${escapeHtml(data.warning)}</p>`
                            : '';
                        els.progress.innerHTML =
                            `${warningLine}<p class="settings-hint-sm" style="margin:0 0 8px;">Saving to: <code>${escapeHtml(data.album_dir)}</code></p>${atmosLine}`;
                    }

                    if (onQueued) { try { onQueued(data); } catch (e) {} }

                    if (!data.import_id) {
                        if (els.downloadBtn) { els.downloadBtn.disabled = true; els.downloadBtn.textContent = 'Already Complete'; }
                        setResetVisible(true);
                        return;
                    }

                    if (state.pollInterval) clearInterval(state.pollInterval);
                    const albumDirHint = `<p class="settings-hint-sm" style="margin:0 0 8px;">Saving to: <code>${escapeHtml(data.album_dir)}</code></p>${atmosLine}`;
                    state.pollInterval = setInterval(async () => {
                        try {
                            const statusResp = await apiFetch(`/api/bulk-import/${data.import_id}/status`);
                            if (!statusResp.ok) return;
                            const statusData = await statusResp.json();
                            if (els.progress) els.progress.innerHTML = albumDirHint + renderProgress(statusData);
                            if (statusData.complete) {
                                clearInterval(state.pollInterval);
                                state.pollInterval = null;
                                if (els.downloadBtn) { els.downloadBtn.disabled = true; els.downloadBtn.textContent = 'Downloaded'; }
                                setResetVisible(true);
                            }
                        } catch (e) { /* transient, keep polling */ }
                    }, 2000);

                } catch (e) {
                    // Nothing was queued, so the choice is the user's again.
                    pickBoxes.forEach(cb => { cb.disabled = false; });
                    state.picksLocked = false;
                    updateTrackPicks();
                    if (els.progress) {
                        els.progress.style.display = 'block';
                        els.progress.innerHTML = `<p class="error-text">Error: ${escapeHtml(e.message)}</p>`;
                    }
                }
            }

            function reset() {
                if (state.pollInterval) { clearInterval(state.pollInterval); state.pollInterval = null; }
                state.selectedRelease = null;
                state.selectedM3uName = null;

                if (els.artistInput) els.artistInput.value = '';
                if (els.artistResults) { els.artistResults.style.display = 'none'; els.artistResults.innerHTML = ''; }
                if (els.listSection) els.listSection.style.display = 'none';
                if (els.list) els.list.innerHTML = '';
                if (els.listHeading) els.listHeading.textContent = '';
                if (els.tracklistSection) els.tracklistSection.style.display = 'none';
                if (els.tracklist) els.tracklist.innerHTML = '';
                if (els.tracklistHeading) els.tracklistHeading.textContent = '';
                if (els.existingWarning) { els.existingWarning.style.display = 'none'; els.existingWarning.textContent = ''; }
                if (els.trackLegend) { els.trackLegend.style.display = 'none'; els.trackLegend.textContent = ''; }
                if (els.progress) { els.progress.style.display = 'none'; els.progress.innerHTML = ''; }
                if (els.downloadBtn) { els.downloadBtn.disabled = false; els.downloadBtn.textContent = 'Download Album'; }
                if (els.makeM3u) els.makeM3u.checked = false;
                if (els.m3uHint) { els.m3uHint.style.display = 'none'; els.m3uHint.textContent = ''; }
                setResetVisible(false);

                containerEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                if (els.artistInput) {
                    els.artistInput.focus({ preventScroll: true });
                    state.selectedArtist = null;
                } else if (artist) {
                    // Pinned artist, no search box to fall back on: hop straight
                    // back to their album list rather than showing a dead end.
                    state.selectedArtist = { mbid: artist.mbid, name: artist.name };
                    selectArtist(state.selectedArtist, null);
                } else {
                    state.selectedArtist = null;
                }
            }

            if (els.artistSearchBtn) els.artistSearchBtn.addEventListener('click', searchArtist);
            if (els.artistInput) els.artistInput.addEventListener('keydown', e => { if (e.key === 'Enter') searchArtist(); });
            if (els.downloadBtn) els.downloadBtn.addEventListener('click', downloadAlbum);
            if (els.tickAllBtn) els.tickAllBtn.addEventListener('click', () => {
                const boxes = trackPickBoxes();
                const tick = !boxes.every(cb => cb.checked);
                boxes.forEach(cb => { cb.checked = tick; });
                updateTrackPicks();
            });
            // Only Usenet and torrents ever carry an Atmos release, so the offer
            // waits for one of them to be switched on.
            let atmosAvailable = false;
            _fetchSources().then(list => {
                atmosAvailable = list.some(s => s.enabled && s.fetches_releases);
                if (els.atmosRow && atmosAvailable) els.atmosRow.style.display = '';
            });
            if (els.resetBtn) els.resetBtn.addEventListener('click', reset);

            const handle = {
                el: containerEl,
                hasSelection() {
                    return !!(state.selectedRelease
                        || (state.selectedArtist && !artist)
                        || (els.artistInput && els.artistInput.value.trim())
                        || (els.artistResults && els.artistResults.innerHTML.trim()));
                },
                setArtist(mbid, name) {
                    return selectArtist({ mbid, name }, null);
                },
                searchFor(name) {
                    if (!els.artistInput) return;
                    els.artistInput.value = name;
                    return searchArtist();
                },
                async openAlbum(opts) {
                    // opts: { artistName, albumTitle, artistMbid?, releaseMbid? }
                    if (!opts.artistName || !opts.albumTitle) return;
                    if (els.artistInput) els.artistInput.value = opts.artistName;
                    state.selectedArtist = null;
                    state.selectedRelease = null;
                    state.selectedM3uName = null;
                    if (state.pollInterval) { clearInterval(state.pollInterval); state.pollInterval = null; }
                    if (els.downloadBtn) { els.downloadBtn.disabled = false; els.downloadBtn.textContent = 'Download Album'; }
                    if (els.tracklistSection) els.tracklistSection.style.display = 'none';
                    if (els.progress) els.progress.style.display = 'none';
                    setResetVisible(false);

                    if (opts.sourceId && opts.sourceAlbumId) {
                        // A source's own album (JioSaavn's soundtracks): its tracklist, not MusicBrainz's.
                        if (els.artistResults) { els.artistResults.style.display = 'none'; els.artistResults.innerHTML = ''; }
                        if (els.listSection) els.listSection.style.display = 'none';
                        if (els.tracklistSection) els.tracklistSection.style.display = 'block';
                        if (els.tracklist) els.tracklist.innerHTML = '<li>Loading…</li>';
                        try {
                            const resp = await apiFetch(`/api/albums/source/${encodeURIComponent(opts.sourceId)}/${encodeURIComponent(opts.sourceAlbumId)}/tracks`);
                            if (!resp.ok) throw new Error(await _readApiErrorDetail(resp));
                            const album = await resp.json();
                            state.selectedArtist = { mbid: null, name: album.artist };
                            await selectAlbum({
                                title: album.title, year: album.year,
                                source_id: opts.sourceId, source_album_id: opts.sourceAlbumId,
                            }, null);
                        } catch (e) {
                            if (els.tracklist) els.tracklist.innerHTML = '';
                            showToast(`Could not open that album: ${e.message}`, true);
                        }
                        return;
                    }

                    if (opts.artistMbid && opts.releaseMbid) {
                        // Fast path: caller already resolved MBIDs (e.g. a MusicBrainz URL paste)
                        state.selectedArtist = { mbid: opts.artistMbid, name: opts.artistName };
                        if (els.artistResults) {
                            els.artistResults.style.display = '';
                            els.artistResults.innerHTML = '';
                            const btn = document.createElement('button');
                            btn.className = 'album-artist-btn selected';
                            btn.innerHTML = `<span class="album-artist-name">${escapeHtml(opts.artistName)}</span>`;
                            btn.addEventListener('click', () => selectArtist(state.selectedArtist, btn));
                            els.artistResults.appendChild(btn);
                        }
                        if (els.listSection) els.listSection.style.display = 'block';
                        if (els.listHeading) els.listHeading.textContent = `Albums by ${opts.artistName}`;
                        if (els.list) els.list.innerHTML = `<p class="bulk-intro-text">${escapeHtml(_musicbrainzQuip())}…</p>`;
                        const albums = await loadAlbums(state.selectedArtist) || [];
                        // The list only carries a release-group id, not the caller's
                        // specific release MBID, so preselect by title the same way
                        // the slow path below already does.
                        const matchedAlbum = findMatchingAlbum(albums, opts.albumTitle);
                        if (matchedAlbum) {
                            const matchedBtn = Array.from(els.list?.querySelectorAll('.album-list-btn') || [])
                                .find(b => b.querySelector('.album-list-title')?.textContent === matchedAlbum.title);
                            await selectAlbum(matchedAlbum, matchedBtn);
                        }
                    } else {
                        // Slow path: look up the artist, then fuzzy-match the album title
                        if (els.artistResults) {
                            els.artistResults.style.display = '';
                            els.artistResults.innerHTML = `<p class="bulk-intro-text">${escapeHtml(_musicbrainzQuip())}…</p>`;
                        }
                        try {
                            const artistResp = await apiFetch(`/api/albums/search-artist?q=${encodeURIComponent(opts.artistName)}`);
                            if (!artistResp.ok) throw new Error('Artist search failed');
                            const artistData = await artistResp.json();
                            const artists = artistData.artists || [];
                            if (!artists.length) {
                                if (els.artistResults) els.artistResults.innerHTML = '<p class="bulk-intro-text">No matching artist found on MusicBrainz.</p>';
                                return;
                            }
                            const bestArtist = artists[0];
                            state.selectedArtist = bestArtist;
                            if (els.artistResults) {
                                els.artistResults.innerHTML = '';
                                for (const a of artists) {
                                    const btn = document.createElement('button');
                                    btn.className = 'album-artist-btn';
                                    if (a.mbid === bestArtist.mbid) btn.classList.add('selected');
                                    btn.innerHTML = `<span class="album-artist-name">${escapeHtml(a.name)}</span>`
                                        + (a.disambiguation ? ` <span class="album-artist-disambig">${escapeHtml(a.disambiguation)}</span>` : '');
                                    btn.addEventListener('click', () => selectArtist(a, btn));
                                    els.artistResults.appendChild(btn);
                                }
                            }
                            if (els.listSection) els.listSection.style.display = 'block';
                            if (els.listHeading) els.listHeading.textContent = `Albums by ${bestArtist.name}`;
                            if (els.list) els.list.innerHTML = `<p class="bulk-intro-text">${escapeHtml(_musicbrainzQuip())}…</p>`;

                            const albums = await loadAlbums(bestArtist) || [];
                            if (!albums.length) return;

                            const matchedAlbum = findMatchingAlbum(albums, opts.albumTitle);
                            if (matchedAlbum) {
                                containerEl.querySelectorAll('.album-list-btn').forEach(b => b.classList.remove('selected'));
                                const matchedBtn = Array.from(els.list?.querySelectorAll('.album-list-btn') || [])
                                    .find(b => b.querySelector('.album-list-title')?.textContent === matchedAlbum.title);
                                await selectAlbum(matchedAlbum, matchedBtn);
                            } else {
                                showToast(`Album "${opts.albumTitle}" not found in MusicBrainz. Pick one manually.`, true);
                            }
                        } catch (e) {
                            if (els.artistResults) els.artistResults.innerHTML = `<p class="bulk-intro-text error-text">Failed: ${escapeHtml(e.message)}</p>`;
                        }
                    }
                },
                reset,
                destroy() {
                    if (state.pollInterval) clearInterval(state.pollInterval);
                    containerEl.innerHTML = '';
                },
            };

            if (state.selectedArtist) selectArtist(state.selectedArtist, null);

            return handle;
        }

        // -------------------------------------------------------------------
        // One-off album browsing (Artists tab, "browse without following") and
        // the Tracks-tab handoff into it.
        // -------------------------------------------------------------------

        // The one-off browser is the chooser's third option ("Download an Album").
        // It has no search box of its own: the artist has already been picked
        // upstairs, so a second search box would just be asking the same question
        // twice. The Tracks-tab handoff drives it through openAlbum() instead.

        let oneOffAlbumBrowserHandle = null;

        function ensureOneOffAlbumBrowser() {
            if (oneOffAlbumBrowserHandle) return oneOffAlbumBrowserHandle;
            const mountEl = document.getElementById('artistOneOffBrowserMount');
            if (!mountEl) return null;
            oneOffAlbumBrowserHandle = mountAlbumBrowser(mountEl, { showArtistSearch: false });
            return oneOffAlbumBrowserHandle;
        }

        function showOneOffAlbumSection(artistName) {
            hideArtistModePanels();
            const panel = document.getElementById('artistOneOffPanel');
            if (panel) panel.style.display = 'block';
            const nameEl = document.getElementById('artistOneOffName');
            if (nameEl) nameEl.textContent = artistName ? `Download an album by ${artistName}` : 'Download an album';
            return ensureOneOffAlbumBrowser();
        }

        function albumHandoffArtist() {
            const query = lastCompletedSearchQuery.trim();
            if (!query || !lastResults.length) return '';

            const parsed = parseArtistTitle(query);
            if (parsed?.artist) return parsed.artist;

            const resultWithArtist = lastResults.find(result => String(result.artist || '').trim());
            if (resultWithArtist) return String(resultWithArtist.artist).trim();

            // An artist-only search is already suitable input for MusicBrainz.
            return query.includes(' - ') ? '' : query;
        }

        function primeAlbumSearchFromResults() {
            if (currentTab !== 'artists') return;

            const artistName = albumHandoffArtist();
            if (!artistName) return;

            // Album work is deliberately sticky. Returning to a search or selected
            // release must never be replaced just because Tracks still has context.
            // The album browser lost its own search box to the chooser, so the
            // handoff now pre-fills the chooser's artist box instead. Only when it
            // is empty and nothing is mid-flight; inheriting context is a courtesy,
            // not a licence to type over what somebody is already doing.
            const input = document.getElementById('artistSearchInput');
            if (!input || input.value.trim()) return;
            if (document.getElementById('artistModeChooser')?.style.display !== 'none') return;
            if (oneOffAlbumBrowserHandle && oneOffAlbumBrowserHandle.hasSelection()) return;
            input.value = artistName;
        }

        async function openAlbumFromSearch(opts) {
            // opts: { artistName, albumTitle, artistMbid?, releaseMbid? }
            if (!opts.artistName || !opts.albumTitle) return;

            // Switch to the Artists tab and pop the one-off browser open; this
            // handoff never assumes you want to follow the artist, just download
            // one album.
            const artistsTabBtn = document.querySelector('[data-tab="artists"]');
            if (artistsTabBtn) artistsTabBtn.click();
            // A source's own album has its own artists, which the search result's singers are not.
            const handle = showOneOffAlbumSection(opts.sourceAlbumId ? '' : opts.artistName);
            if (!handle) return;
            await handle.openAlbum(opts);
            document.getElementById('artistOneOffPanel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
