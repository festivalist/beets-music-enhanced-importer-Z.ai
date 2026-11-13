        // Bulk Import tab: track lists, playlist and album URLs, album matching and
        // long-form YouTube splitting.

        let currentBulkImportId = null;
        let bulkImportPollInterval = null;
        let longformSplitPollInterval = null;
        let longformDetectedContext = null;
        async function bulkImport() {
            const songs = bulkInput.value.trim();
            if (!songs) {
                showToast('Please enter some songs', true);
                return;
            }

            // Validate playlist name if checkbox is checked
            const createPlaylist = createPlaylistCheckbox.checked;
            const playlistName = playlistNameInput.value.trim();

            if (createPlaylist && !playlistName) {
                showToast('Please enter a playlist name', true);
                playlistNameInput.focus();
                return;
            }

            bulkImportBtn.disabled = true;
            bulkImportBtn.textContent = 'Starting...';
            bulkResults.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

            try {
                const requestBody = {
                    songs,
                    convert_audio: convertAudioCheckbox.checked
                };
                if (createPlaylist) {
                    requestBody.create_playlist = true;
                    requestBody.playlist_name = playlistName;
                    if (playlistNameInput.dataset.sourceUrl) {
                        requestBody.playlist_source_url = playlistNameInput.dataset.sourceUrl;
                    }
                    const usePlaylistsDirCheckbox = document.getElementById('usePlaylistsDirCheckbox');
                    if ((usePlaylistsDirCheckbox && usePlaylistsDirCheckbox.checked) || (!usePlaylistsDirCheckbox && serverConfig.playlists_subdir)) {
                        requestBody.use_playlists_dir = true;
                    }
                }
                if (bulkInput.dataset.originalYoutubeVideoMap) {
                    const originalRows = JSON.parse(bulkInput.dataset.originalYoutubeVideoMap);
                    const idsByTrack = new Map(originalRows.map(row => [row.track, row.video_id]));
                    requestBody.original_youtube_video_ids = songs.split('\n')
                        .map(line => idsByTrack.get(line.trim()) || null);
                }
                const bulkPriority = document.getElementById('bulkPrioritySource');
                if (bulkPriority && bulkPriority.value) {
                    requestBody.priority_source = bulkPriority.value;
                }

                // Start the async import
                const response = await apiFetch('/api/bulk-import-async', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });

                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Bulk import failed');
                }

                const data = await response.json();
                currentBulkImportId = data.import_id;
                localStorage.setItem(userStorageKey('activeBulkImportId'), data.import_id);

                // Clear the textarea
                bulkInput.value = '';
                playlistNameInput.value = '';
                delete playlistNameInput.dataset.sourceUrl;
                delete bulkInput.dataset.originalYoutubeVideoMap;
                createPlaylistCheckbox.checked = false;
                playlistNameInput.style.display = 'none';
                const usePlaylistsDirCheckboxCleared = document.getElementById('usePlaylistsDirCheckbox');
                if (usePlaylistsDirCheckboxCleared) usePlaylistsDirCheckboxCleared.checked = false;
                const usePlaylistsDirRowCleared = document.getElementById('usePlaylistsDirRow');
                if (usePlaylistsDirRowCleared) usePlaylistsDirRowCleared.style.display = 'none';
                updatePlaylistNameHint();
                updateLineCounter();

                // Show initial progress
                showBulkImportProgress({
                    status: 'pending',
                    total_tracks: data.total_tracks,
                    searched: 0,
                    queued: 0,
                    failed: 0
                });

                // Start polling for progress
                startBulkImportPolling(data.import_id);

            } catch (error) {
                bulkResults.innerHTML = '';
                showToast(error.message || 'Bulk import failed', true);
                bulkImportBtn.disabled = false;
                bulkImportBtn.textContent = 'Import & Download All';
            }
        }

        function showBulkImportProgress(data) {
            const searchDone = ['completed', 'cancelled', 'error'].includes(data.status);
            // Show search progress while searching, download progress once searches are done
            const percent = data.total_tracks > 0
                ? (searchDone
                    ? Math.round(((data.completed + data.failed + (data.skipped || 0) + (data.unsure || 0)) / data.total_tracks) * 100)
                    : Math.round((data.searched / data.total_tracks) * 100))
                : 0;
            const isComplete = data.complete;

            let statusText = 'Processing...';
            let statusColor = 'var(--accent)';
            if (data.rate_limited) {
                statusText = 'Rate limited - waiting...';
                statusColor = 'var(--warning)';
            } else if (data.status === 'cancelling') {
                statusText = 'Cancelling after active files...';
                statusColor = 'var(--warning)';
            } else if (data.status === 'cancelled') {
                statusText = 'Cancelled';
                statusColor = 'var(--text-secondary)';
            } else if (data.complete) {
                statusText = 'Complete';
                statusColor = 'var(--accent)';
            } else if (data.status === 'completed' && data.queued > 0) {
                statusText = `Downloading... (${data.queued} remaining)`;
                statusColor = 'var(--accent)';
            } else if (data.status === 'error') {
                statusText = 'Error';
                statusColor = 'var(--error)';
            }

            let html = `
                <div style="padding: 14px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="font-size: 14px; font-weight: 600;">Import Progress</div>
                        <div style="display:flex;align-items:center;gap:8px;">
                            <div style="font-size: 12px; color: ${statusColor};">${statusText}</div>
                            ${!isComplete && data.status !== 'cancelling' ? '<button type="button" class="btn btn-ghost" style="padding:4px 8px;font-size:11px;" data-ui-click="cancelBulkImport">Cancel</button>' : ''}
                        </div>
                    </div>

                    <!-- Progress bar -->
                    <div style="background: var(--bg-tertiary); border-radius: 4px; height: 8px; margin-bottom: 12px; overflow: hidden;">
                        <div style="background: ${data.rate_limited ? 'var(--warning)' : 'var(--accent)'}; height: 100%; width: ${percent}%; transition: width 0.3s ease;"></div>
                    </div>

                    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; text-align: center;">
                        <div>
                            <div style="font-size: 16px; font-weight: 600;">${data.searched}</div>
                            <div style="font-size: 10px; color: var(--text-secondary);">Searched</div>
                        </div>
                        <div>
                            <div style="font-size: 16px; font-weight: 600; color: var(--warning);">${data.queued}</div>
                            <div style="font-size: 10px; color: var(--text-secondary);">Queued</div>
                        </div>
                        <div>
                            <div style="font-size: 16px; font-weight: 600; color: var(--accent);">${data.completed || 0}</div>
                            <div style="font-size: 10px; color: var(--text-secondary);">Done</div>
                        </div>
                        <div>
                            <div style="font-size: 16px; font-weight: 600; color: var(--error);">${data.failed}</div>
                            <div style="font-size: 10px; color: var(--text-secondary);">Failed</div>
                        </div>
                        <div>
                            <div style="font-size: 16px; font-weight: 600;">${data.total_tracks}</div>
                            <div style="font-size: 10px; color: var(--text-secondary);">Total</div>
                        </div>
                    </div>
                </div>
            `;

            // Show error if any
            if (data.error) {
                html += `
                    <div style="padding: 14px; background: var(--bg-secondary); border: 1px solid var(--error); border-radius: 12px; margin-top: 12px;">
                        <div style="font-size: 13px; color: var(--error);">${escapeHtml(data.error)}</div>
                    </div>
                `;
            }

            bulkResults.innerHTML = html;

            // Update button state
            if (isComplete) {
                bulkImportBtn.disabled = false;
                bulkImportBtn.textContent = 'Import & Download All';
                if (data.status === 'completed') {
                    showToast(`Import complete: ${data.queued} queued, ${data.failed} failed`);
                } else if (data.status === 'cancelled') {
                    showToast('Import cancelled. Completed files and Queue history were kept.');
                }
            } else {
                bulkImportBtn.disabled = true;
                bulkImportBtn.textContent = `Processing ${data.searched}/${data.total_tracks}...`;
            }
        }

        async function cancelBulkImport() {
            if (!currentBulkImportId) return;
            try {
                const response = await apiFetch(`/api/bulk-import/${currentBulkImportId}/cancel`, {
                    method: 'POST'
                });
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Could not cancel import');
                }
                showToast('Cancellation requested. Up to two active files may finish.');
            } catch (error) {
                showToast(error.message || 'Could not cancel import', true);
            }
        }

        // Draws each bulk import track as the exact same job card the Queue tab
        // uses (same retry/report/edit-tags buttons, same click wiring), rather
        // than a second copy of that UI. A track that hasn't reached a job yet
        // (still being searched) has nothing for renderJobs to draw, so it gets
        // a plain placeholder row instead; it swaps for the real card the moment
        // a job_id shows up on the next poll.
        async function renderBulkImportJobList(importId, tracks, stage = null) {
            if (!bulkImportJobsContainer) return;
            bulkImportShownId = importId;
            if (!tracks || !tracks.length) {
                bulkImportJobsContainer.innerHTML = '';
                return;
            }

            let jobsById = new Map();
            try {
                const resp = await apiFetch(`/api/jobs?import_id=${encodeURIComponent(importId)}`);
                if (resp.ok) {
                    const data = await resp.json();
                    jobsById = new Map((data.jobs || []).map(j => [String(j.id), j]));
                }
            } catch {
                // Transient; the next poll tick tries the fetch again.
            }

            const pending = tracks.filter(t => !t.job_id || !jobsById.has(String(t.job_id)));
            const jobsInOrder = tracks
                .filter(t => t.job_id && jobsById.has(String(t.job_id)))
                .map(t => jobsById.get(String(t.job_id)));

            const pendingLabels = { pending: 'Waiting to search…', searching: 'Searching…', cancelled: 'Cancelled', skipped: 'Already in your library' };
            // Before any track is searched, the album as a whole may be on its way
            // (a Usenet release downloading); say so once, above the waiting rows.
            const stageHtml = stage ? albumFetchNoticeHtml('The whole album', stage) : '';
            const pendingHtml = pending.length ? `
                <div class="bulk-import-pending-list">
                    ${stageHtml}
                    ${pending.map(track => `
                        <div class="job-item bulk-import-pending-row">
                            <div class="job-status ${track.status === 'failed' ? 'failed' : track.status === 'skipped' ? 'completed' : 'queued'}"></div>
                            <div class="job-info">
                                <div class="job-title">${escapeHtml(track.artist ? `${track.artist} - ${track.song}` : (track.song || ''))}</div>
                                <div class="job-meta"><span class="job-status-label">${escapeHtml(pendingLabels[track.status] || track.status || 'Waiting…')}</span></div>
                                ${track.error ? `<div class="job-error">${escapeHtml(track.status === 'skipped' ? track.error.replace(/^Already in your library: /, '') : track.error)}</div>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>` : '';

            // Skip handing an empty array to renderJobs here: its empty state is
            // sized for a whole quiet Queue tab, not a gap under a live pending
            // list, and every track starts with no job_id anyway.
            bulkImportJobsContainer.innerHTML = jobsInOrder.length
                ? pendingHtml + '<div id="bulkImportJobCards"></div>'
                : pendingHtml;
            if (jobsInOrder.length) {
                renderJobs(jobsInOrder, document.getElementById('bulkImportJobCards'));
            }
        }

        function startBulkImportPolling(importId) {
            // Clear any existing polling
            if (bulkImportPollInterval) {
                clearInterval(bulkImportPollInterval);
            }

            // Poll every 2 seconds
            bulkImportPollInterval = setInterval(async () => {
                try {
                    const response = await apiFetch(`/api/bulk-import/${importId}/status`);
                    if (!response.ok) {
                        throw new Error('Failed to get status');
                    }

                    const data = await response.json();
                    showBulkImportProgress(data);
                    renderBulkImportJobList(importId, data.tracks, data.stage);

                    // Stop polling when complete
                    if (data.complete) {
                        clearInterval(bulkImportPollInterval);
                        bulkImportPollInterval = null;
                        currentBulkImportId = null;
                        localStorage.removeItem(userStorageKey('activeBulkImportId'));
                    }
                } catch (error) {
                    console.error('Polling error:', error);
                    // Keep polling, might be a transient error
                }
            }, 2000);
        }

        // The import whose tracks are on screen. Polling stops once an import is
        // complete, but an Unsure question answered after that should still show.
        let bulkImportShownId = null;

        async function refreshShownBulkImport() {
            if (!bulkImportShownId || currentTab !== 'bulk') return;
            try {
                const response = await apiFetch(`/api/bulk-import/${bulkImportShownId}/status`);
                if (!response.ok) return;
                const data = await response.json();
                showBulkImportProgress(data);
                renderBulkImportJobList(bulkImportShownId, data.tracks, data.stage);
            } catch {
                // Transient; the cards are only a little out of date.
            }
        }

        // A reload used to lose track of an import that was still running in
        // the background entirely: the download carried on fine, the UI just
        // forgot it was ever watching anything. currentBulkImportId now has a
        // localStorage backup, so this picks the thread back up on load if
        // there's one to find, rather than leaving it to be discovered by
        // accident in the Queue tab.
        async function reattachBulkImportIfActive() {
            const storedId = localStorage.getItem(userStorageKey('activeBulkImportId'));
            if (!storedId) return;
            try {
                const response = await apiFetch(`/api/bulk-import/${storedId}/status`);
                if (!response.ok) {
                    localStorage.removeItem(userStorageKey('activeBulkImportId'));
                    return;
                }
                const data = await response.json();
                if (data.complete) {
                    localStorage.removeItem(userStorageKey('activeBulkImportId'));
                    return;
                }
                currentBulkImportId = storedId;
                showBulkImportProgress(data);
                renderBulkImportJobList(storedId, data.tracks, data.stage);
                startBulkImportPolling(storedId);
            } catch {
                // Transient; leave the stored id alone and try again next load.
            }
        }

        // -------------------------------------------------------------------
        // Bulk Import's copy of the same browser. The Albums tab is gone, so
        // its artist/release browsing lives here as well as on Artists; one
        // component, mounted twice, rather than two things to keep in step.
        // -------------------------------------------------------------------

        let bulkAlbumBrowserHandle = null;

        function ensureBulkAlbumBrowser() {
            if (bulkAlbumBrowserHandle) return bulkAlbumBrowserHandle;
            const mountEl = document.getElementById('bulkAlbumBrowserMount');
            if (!mountEl) return null;
            bulkAlbumBrowserHandle = mountAlbumBrowser(mountEl, { showArtistSearch: true });
            return bulkAlbumBrowserHandle;
        }

        document.getElementById('bulkAlbumBrowseToggleBtn')?.addEventListener('click', () => {
            const section = document.getElementById('bulkAlbumBrowseSection');
            const toggleBtn = document.getElementById('bulkAlbumBrowseToggleBtn');
            if (!section || !toggleBtn) return;
            const visible = section.style.display !== 'none';
            if (visible) {
                section.style.display = 'none';
                toggleBtn.textContent = "+ Browse an artist's albums";
            } else {
                section.style.display = 'block';
                toggleBtn.textContent = "− Browse an artist's albums";
                ensureBulkAlbumBrowser();
            }
        });

        // Line counter (no limit)
        function updateLineCounter() {
            const lines = bulkInput.value.split('\n').filter(line => line.trim());
            const count = lines.length;
            lineCounter.textContent = `${count} line${count !== 1 ? 's' : ''}`;
            lineCounter.style.color = 'var(--text-secondary)';
            lineCounter.style.background = 'var(--bg-tertiary)';
        }

        bulkInput.addEventListener('input', updateLineCounter);

        // File upload handler
        fileUpload.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;

            fileName.textContent = file.name;

            const reader = new FileReader();
            reader.onload = (event) => {
                bulkInput.value = event.target.result;
                updateLineCounter();
            };
            reader.readAsText(file);
        });

        bulkImportBtn.addEventListener('click', bulkImport);
        // =============================================================
        // Album name / URL routing (Bulk Import as the general acquisition
        // input). Three album-shaped things share one confirmation panel:
        //   - Spotify/Apple album URLs, via resolve-album-url (confidence gate)
        //   - MusicBrainz search-release results (artist optional; soundtracks,
        //     compilations etc. are first-class, see "Trainspotting" test case)
        //   - The candidate a user picks from either of the above needs its
        //     release_mbid resolved before /api/albums/download will take it.
        // All three end up at queueAlbumAndShowProgress(), which is the only
        // place that actually calls the download endpoint, so there is exactly
        // one code path doing the queueing bit.
        // =============================================================

        function hideAlbumMatchPanel() {
            if (!albumMatchPanel) return;
            albumMatchPanel.style.display = 'none';
            albumMatchPanel.innerHTML = '';
        }

        // A search-release / resolve-album-url candidate: {title, artist, year,
        // release_group_mbid, release_mbid, primary_type, secondary_types, score}.
        // release_mbid is null by design for search-release results (resolving
        // one costs a rate-limited MusicBrainz request per candidate); it's
        // usually present for resolve-album-url's single best match.
        function _albumCandidateTypeLabel(c) {
            const parts = [c.primary_type, ...(Array.isArray(c.secondary_types) ? c.secondary_types : [])].filter(Boolean);
            return parts.join(' · ');
        }

        function renderAlbumCandidates(candidates, headerText) {
            if (!albumMatchPanel) return;
            albumMatchPanel.style.display = 'block';
            albumMatchPanel.innerHTML = '';

            const heading = document.createElement('p');
            heading.className = 'bulk-intro-text';
            heading.textContent = headerText;
            albumMatchPanel.appendChild(heading);

            const list = document.createElement('div');
            list.className = 'album-list';
            for (const c of candidates) {
                const title = c.title || 'Unknown album';
                const typeLabel = _albumCandidateTypeLabel(c);
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'album-list-btn';
                btn.innerHTML = `<span class="album-list-title">${escapeHtml(title)}</span>`
                    + (c.artist ? ` <span class="album-artist-disambig">${escapeHtml(c.artist)}</span>` : '')
                    + (c.year ? ` <span class="album-list-year">${escapeHtml(String(c.year))}</span>` : '')
                    + (typeLabel ? ` <span class="album-list-year">(${escapeHtml(typeLabel)})</span>` : '');
                btn.addEventListener('click', () => resolveAndQueueCandidate(c, btn));
                list.appendChild(btn);
            }
            albumMatchPanel.appendChild(list);

            const cancelBtn = document.createElement('button');
            cancelBtn.type = 'button';
            cancelBtn.className = 'btn btn-ghost';
            cancelBtn.textContent = 'None of these';
            cancelBtn.addEventListener('click', hideAlbumMatchPanel);
            albumMatchPanel.appendChild(cancelBtn);
        }

        // fields: {artist, album (or album_title), release_mbid}. Shows what's
        // about to be queued and requires an explicit click either way; the
        // confidence gate isn't a licence to skip showing the match, it just
        // decides whether the user also has to pick from alternatives first.
        function renderAlbumConfirmCard(fields, headerText) {
            if (!albumMatchPanel) return;
            albumMatchPanel.style.display = 'block';
            albumMatchPanel.innerHTML = '';

            const wrap = document.createElement('div');
            wrap.className = 'album-existing-warning';

            const p = document.createElement('p');
            p.style.margin = '0 0 8px';
            p.textContent = headerText;
            wrap.appendChild(p);

            if (!fields.release_mbid) {
                const warn = document.createElement('p');
                warn.style.margin = '0';
                warn.textContent = "MusicBrainz didn't settle on a specific release for this one just now; try again in a moment.";
                wrap.appendChild(warn);
                albumMatchPanel.appendChild(wrap);
                return;
            }

            const btnRow = document.createElement('div');
            btnRow.style.display = 'flex';
            btnRow.style.gap = '8px';
            btnRow.style.marginTop = '4px';

            const queueBtn = document.createElement('button');
            queueBtn.type = 'button';
            queueBtn.className = 'btn btn-primary';
            queueBtn.textContent = 'Queue Album';
            queueBtn.addEventListener('click', () => queueAlbumAndShowProgress(fields, queueBtn));

            const cancelBtn = document.createElement('button');
            cancelBtn.type = 'button';
            cancelBtn.className = 'btn btn-ghost';
            cancelBtn.textContent = 'Not this one';
            cancelBtn.addEventListener('click', hideAlbumMatchPanel);

            btnRow.appendChild(queueBtn);
            btnRow.appendChild(cancelBtn);
            wrap.appendChild(btnRow);
            albumMatchPanel.appendChild(wrap);
        }

        // A candidate from search-release (release_mbid always null) or from
        // resolve-album-url's `candidates` list (usually null too, same reason).
        // Either way, resolve-release-group is the bridge to a real release_mbid
        // before /api/albums/download will take it.
        async function resolveAndQueueCandidate(candidate, btnEl) {
            if (candidate.release_mbid) {
                renderAlbumConfirmCard(
                    { artist: candidate.artist, album: candidate.title, release_mbid: candidate.release_mbid },
                    `Queue: ${candidate.artist ? candidate.artist + ' – ' : ''}${candidate.title}?`
                );
                return;
            }
            if (!candidate.release_group_mbid) {
                showToast('Not enough information to queue this album.', true);
                return;
            }
            if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Resolving…'; }
            try {
                const resp = await apiFetch('/api/albums/resolve-release-group', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ release_group_mbid: candidate.release_group_mbid }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.detail || 'Could not resolve that release');
                renderAlbumConfirmCard(
                    { artist: data.artist || candidate.artist, album: data.album_title || candidate.title, release_mbid: data.release_mbid },
                    `Queue: ${data.artist || candidate.artist} – ${data.album_title || candidate.title}?`
                );
            } catch (e) {
                showToast(e.message, true);
                if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Retry'; }
            }
        }

        // The one place that actually calls POST /api/albums/download for
        // everything routed through this panel (album URLs, search-release
        // picks). fields: {artist, album, release_mbid}.
        async function queueAlbumAndShowProgress(fields, btnEl) {
            if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Queuing…'; }
            const makeM3u = createPlaylistCheckbox.checked;
            try {
                const resp = await apiFetch('/api/albums/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        artist: fields.artist,
                        album_title: fields.album,
                        release_mbid: fields.release_mbid,
                        make_m3u: makeM3u,
                        m3u_name: makeM3u ? (playlistNameInput.value.trim() || null) : null,
                        convert_audio: convertAudioCheckbox.checked,
                    }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.detail || 'Failed to queue album');

                const label = `${fields.artist} - ${fields.album}`;
                if (!data.import_id) {
                    showToast(data.already_queued ? `"${label}" is already queued` : `"${label}" is already complete, nothing to fetch`);
                } else {
                    const queued = data.queued_count ?? 0;
                    showToast(`Queued ${queued} track${queued === 1 ? '' : 's'} from "${label}"`);
                }
                hideAlbumMatchPanel();
                spotifyUrlInput.value = '';
            } catch (e) {
                showToast(e.message, true);
                if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Queue Album'; }
            }
        }

        // ALBUM url -> resolve-album-url -> confidence gate. Handles Spotify,
        // Apple Music, YouTube Music, Beatport, Tidal, Monochrome and Qobuz.
        // recognised:false falls through to the ordinary playlist path silently
        // (it means "not actually an album url", not an error).
        async function fetchAlbumUrl(url) {
            spotifyError.style.display = 'none';
            spotifyError.style.color = '';
            hideAlbumMatchPanel();
            fetchSpotifyBtn.disabled = true;
            fetchSpotifyBtn.textContent = 'Looking up album…';
            try {
                const resp = await apiFetch('/api/albums/resolve-album-url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url }),
                });
                if (resp.status === 404) {
                    spotifyError.textContent = 'Album URL matching is not available on this server yet.';
                    spotifyError.style.display = 'block';
                    return;
                }
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.detail || 'Could not resolve that album URL');

                if (!data.recognised) {
                    // Not actually an album url after all (or the service call
                    // fell over); ordinary playlist path, same url.
                    await doPlaylistFetch(url, false);
                    return;
                }

                if (data.confident && data.match) {
                    renderAlbumConfirmCard(
                        { artist: data.match.artist, album: data.match.title, release_mbid: data.match.release_mbid },
                        `Matched: ${data.match.artist} – ${data.match.title}`
                    );
                } else if (Array.isArray(data.candidates) && data.candidates.length) {
                    renderAlbumCandidates(data.candidates, `Not confident which album that is. Pick one:`);
                } else if (data.service === 'youtube') {
                    // OLAK5uy_ album playlists were importable as ordinary
                    // playlists before album support existed; an unmatched
                    // one falls back to that rather than dead-ending, since
                    // (unlike Spotify/Apple album urls) it's a genuine
                    // playlist url too.
                    await doPlaylistFetch(url, false);
                } else {
                    spotifyError.textContent = `Couldn't confidently match that to a MusicBrainz album (scraped as "${data.artist || '?'} - ${data.album || '?'}"). Try typing the album name in this box instead.`;
                    spotifyError.style.display = 'block';
                }
            } catch (e) {
                spotifyError.textContent = e.message;
                spotifyError.style.display = 'block';
            } finally {
                fetchSpotifyBtn.disabled = false;
                fetchSpotifyBtn.textContent = 'Fetch';
            }
        }

        // Plain text, no URL: search MusicBrainz release-groups by name. "Artist
        // - Album" splits on the same dash convention as the bulk track list;
        // bare text with no separator searches by album title alone, on purpose
        // (an artist is not required, see search_release_groups' docstring).
        async function searchReleaseByName(query) {
            let artist = '';
            let album = query;
            const dashMatch = query.match(/^(.+?)\s+[-–—]\s+(.+)$/);
            if (dashMatch) {
                artist = dashMatch[1].trim();
                album = dashMatch[2].trim();
            }

            spotifyError.style.display = 'none';
            spotifyError.style.color = '';
            hideAlbumMatchPanel();
            fetchSpotifyBtn.disabled = true;
            fetchSpotifyBtn.textContent = 'Searching…';
            try {
                const params = new URLSearchParams({ q: album });
                if (artist) params.set('artist', artist);
                const resp = await apiFetch(`/api/albums/search-release?${params.toString()}`);
                if (resp.status === 404) {
                    spotifyError.textContent = 'Album search is not available on this server yet.';
                    spotifyError.style.display = 'block';
                    return;
                }
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.detail || 'Album search failed');

                const releases = data.releases || [];
                if (!releases.length) {
                    spotifyError.textContent = `No albums found matching "${query}". Paste it into the song list below to search it as a track instead.`;
                    spotifyError.style.display = 'block';
                    return;
                }
                renderAlbumCandidates(releases, `Found ${releases.length} album${releases.length === 1 ? '' : 's'} matching "${query}":`);
            } catch (e) {
                spotifyError.textContent = e.message;
                spotifyError.style.display = 'block';
            } finally {
                fetchSpotifyBtn.disabled = false;
                fetchSpotifyBtn.textContent = 'Fetch';
            }
        }

        // MusicBrainz release URL -> straight into the album download pipeline.
        // No scraping, no fuzzy matching: the MBID is in the URL, so we resolve it
        // to artist/title and queue the album properly rather than flattening it
        // into a list of "Artist - Title" lines that lands in Singles.
        async function fetchMusicBrainzRelease(url) {
            spotifyError.style.display = 'none';
            fetchSpotifyBtn.disabled = true;
            fetchSpotifyBtn.textContent = 'Looking up release…';
            try {
                const resolveResp = await apiFetch('/api/albums/resolve-url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url }),
                });
                const album = await resolveResp.json().catch(() => ({}));
                if (!resolveResp.ok) {
                    throw new Error(album.detail || 'Could not resolve that MusicBrainz URL');
                }

                fetchSpotifyBtn.textContent = 'Queuing album…';
                const makeM3u = createPlaylistCheckbox.checked;
                const dlResp = await apiFetch('/api/albums/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        artist: album.artist,
                        album_title: album.album_title,
                        release_mbid: album.release_mbid,
                        make_m3u: makeM3u,
                        m3u_name: makeM3u ? (playlistNameInput.value.trim() || null) : null,
                        convert_audio: convertAudioCheckbox.checked,
                    }),
                });
                const data = await dlResp.json().catch(() => ({}));
                if (!dlResp.ok) {
                    throw new Error(data.detail || 'Failed to queue album');
                }

                const label = `${album.artist} - ${album.album_title}`;
                if (!data.import_id) {
                    showToast(`"${label}" is already complete, nothing to fetch`);
                } else {
                    const queued = data.queued_count ?? album.track_count ?? 0;
                    showToast(`Queued ${queued} track${queued === 1 ? '' : 's'} from "${label}"`);
                }
                spotifyUrlInput.value = '';
            } catch (error) {
                spotifyError.textContent = error.message;
                spotifyError.style.color = '';
                spotifyError.style.display = 'block';
            } finally {
                fetchSpotifyBtn.disabled = false;
                fetchSpotifyBtn.textContent = 'Fetch';
            }
        }

        // =============================================================
        // Long-form YouTube splitting (Bulk Import Fetch box only). A single
        // video over the length threshold gets cut into tagged tracks via
        // ffmpeg instead of downloaded whole. Detection never guesses blind:
        // it prefers YouTube's own chapters, falls back to a cue sheet hunted
        // out of the comments, and always lands on an editable table the user
        // confirms before anything downloads.
        // =============================================================

        function hideLongformPanel() {
            if (!longformSplitPanel) return;
            longformSplitPanel.style.display = 'none';
            longformSplitPanel.innerHTML = '';
            longformDetectedContext = null;
            if (longformSplitPollInterval) {
                clearInterval(longformSplitPollInterval);
                longformSplitPollInterval = null;
            }
        }

        function _longformDetectedViaLabel(detectedVia) {
            if (detectedVia === 'chapters') return 'Detected from YouTube chapters';
            if (detectedVia === 'description') return 'Detected from a cue sheet in the video description';
            if (detectedVia === 'comments') return 'Detected from a comment cue sheet';
            return 'No cue points found automatically, so enter them manually below';
        }

        function _formatTimestamp(totalSeconds) {
            const s = Math.max(0, Math.round(totalSeconds || 0));
            const h = Math.floor(s / 3600);
            const m = Math.floor((s % 3600) / 60);
            const sec = s % 60;
            const pad = n => String(n).padStart(2, '0');
            return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
        }

        function _parseTimestampInput(text) {
            const parts = String(text || '').trim().split(':').map(p => parseInt(p, 10));
            if (!parts.length || parts.some(isNaN)) return 0;
            let seconds = 0;
            for (const p of parts) seconds = seconds * 60 + p;
            return seconds;
        }

        // Mirrors longform_split.py's parse_cue_sheet_text/_fill_end_times, for
        // the "paste your own cue sheet" fallback so it doesn't need a round
        // trip to re-parse text the user already typed.
        function _parseCueSheetTextJs(text, duration) {
            const lineRe = /^\s*(?:\d+[.)]\s*)?[\[(]?(\d{1,2}(?::\d{2}){1,2})[\])]?\s*[-–—:]?\s*(.+?)\s*$/;
            const points = [];
            for (const line of String(text || '').split('\n')) {
                const m = lineRe.exec(line);
                if (!m) continue;
                const title = m[2].replace(/^[-–—:\s]+|[-–—:\s]+$/g, '');
                if (!title) continue;
                points.push({ start_seconds: _parseTimestampInput(m[1]), title });
            }
            const segments = [];
            for (let i = 0; i < points.length; i++) {
                const end = i + 1 < points.length ? points[i + 1].start_seconds : (duration || points[i].start_seconds);
                segments.push({ start_seconds: points[i].start_seconds, end_seconds: end, title: points[i].title, artist: '' });
            }
            return segments;
        }

        function _buildLongformRow(segment) {
            const row = document.createElement('div');
            row.className = 'longform-row';

            const startInput = document.createElement('input');
            startInput.type = 'text';
            startInput.className = 'longform-row-input longform-start';
            startInput.placeholder = '0:00';
            startInput.value = _formatTimestamp(segment.start_seconds || 0);

            const endInput = document.createElement('input');
            endInput.type = 'text';
            endInput.className = 'longform-row-input longform-end';
            endInput.placeholder = '0:00';
            endInput.value = _formatTimestamp(segment.end_seconds || 0);

            const titleInput = document.createElement('input');
            titleInput.type = 'text';
            titleInput.className = 'longform-row-input longform-title';
            titleInput.placeholder = 'Track title';
            titleInput.value = segment.title || '';

            const artistInput = document.createElement('input');
            artistInput.type = 'text';
            artistInput.className = 'longform-row-input longform-artist';
            artistInput.placeholder = 'Artist';
            artistInput.value = segment.artist || '';

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-ghost btn-sm longform-row-remove';
            removeBtn.title = 'Remove this row';
            removeBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
            removeBtn.addEventListener('click', () => row.remove());

            row.appendChild(startInput);
            row.appendChild(endInput);
            row.appendChild(titleInput);
            row.appendChild(artistInput);
            row.appendChild(removeBtn);
            return row;
        }

        function _collectLongformSegments() {
            if (!longformSplitPanel) return [];
            const rows = longformSplitPanel.querySelectorAll('.longform-row');
            const segments = [];
            rows.forEach(row => {
                const start = _parseTimestampInput(row.querySelector('.longform-start').value);
                const end = _parseTimestampInput(row.querySelector('.longform-end').value);
                const title = row.querySelector('.longform-title').value.trim();
                const artist = row.querySelector('.longform-artist').value.trim();
                if (!title) return;
                segments.push({ start_seconds: start, end_seconds: end, title, artist: artist || null });
            });
            return segments;
        }

        function renderLongformPanel(data, sourceUrl) {
            if (!longformSplitPanel) return;
            hideAlbumMatchPanel();
            longformDetectedContext = {
                url: sourceUrl,
                video_title: data.video_title,
                thumbnail: data.thumbnail,
                duration: data.duration,
            };
            longformSplitPanel.style.display = 'block';
            longformSplitPanel.innerHTML = '';

            const header = document.createElement('div');
            header.className = 'longform-video-header';
            if (data.thumbnail) {
                const img = document.createElement('img');
                img.className = 'longform-video-thumb';
                img.src = data.thumbnail;
                img.alt = '';
                header.appendChild(img);
            }
            const titleWrap = document.createElement('div');
            const titleEl = document.createElement('div');
            titleEl.className = 'longform-video-title';
            titleEl.textContent = data.video_title || 'Untitled';
            const viaEl = document.createElement('div');
            viaEl.className = 'longform-detected-via';
            viaEl.textContent = _longformDetectedViaLabel(data.detected_via);
            titleWrap.appendChild(titleEl);
            titleWrap.appendChild(viaEl);
            header.appendChild(titleWrap);
            longformSplitPanel.appendChild(header);

            const artistRow = document.createElement('div');
            artistRow.className = 'longform-field-row';
            const artistLabel = document.createElement('span');
            artistLabel.textContent = 'Album Artist:';
            const artistInput = document.createElement('input');
            artistInput.type = 'text';
            artistInput.id = 'longformAlbumArtist';
            artistInput.className = 'longform-row-input';
            artistInput.style.maxWidth = '260px';
            const segArtists = new Set((data.segments || []).map(s => (s.artist || '').trim()).filter(Boolean));
            artistInput.value = segArtists.size === 1 ? [...segArtists][0] : 'Various Artists';
            artistRow.appendChild(artistLabel);
            artistRow.appendChild(artistInput);
            longformSplitPanel.appendChild(artistRow);

            const rowsWrap = document.createElement('div');
            rowsWrap.className = 'longform-rows-wrap';
            const segments = (data.segments && data.segments.length)
                ? data.segments
                : [{ start_seconds: 0, end_seconds: data.duration || 0, title: '', artist: '' }];
            for (const seg of segments) {
                rowsWrap.appendChild(_buildLongformRow(seg));
            }
            longformSplitPanel.appendChild(rowsWrap);

            const addRowBtn = document.createElement('button');
            addRowBtn.type = 'button';
            addRowBtn.className = 'btn btn-ghost btn-sm';
            addRowBtn.textContent = '+ Add row';
            addRowBtn.addEventListener('click', () => {
                rowsWrap.appendChild(_buildLongformRow({ start_seconds: 0, end_seconds: 0, title: '', artist: '' }));
            });
            longformSplitPanel.appendChild(addRowBtn);

            const pasteWrap = document.createElement('div');
            pasteWrap.className = 'longform-paste-wrap';
            const pasteLabel = document.createElement('p');
            pasteLabel.className = 'bulk-intro-text';
            pasteLabel.textContent = 'Or paste your own cue sheet (one "0:00 Track Title" per line) to replace the rows above:';
            const pasteTextarea = document.createElement('textarea');
            pasteTextarea.className = 'longform-paste-textarea';
            pasteTextarea.placeholder = '0:00 Track One\n3:45 Track Two';
            const pasteBtn = document.createElement('button');
            pasteBtn.type = 'button';
            pasteBtn.className = 'btn btn-ghost btn-sm';
            pasteBtn.textContent = 'Use this cue sheet';
            pasteBtn.addEventListener('click', () => {
                const parsed = _parseCueSheetTextJs(pasteTextarea.value, data.duration || 0);
                if (!parsed.length) {
                    showToast('Could not find any cue points in that text', true);
                    return;
                }
                rowsWrap.innerHTML = '';
                for (const seg of parsed) rowsWrap.appendChild(_buildLongformRow(seg));
            });
            pasteWrap.appendChild(pasteLabel);
            pasteWrap.appendChild(pasteTextarea);
            pasteWrap.appendChild(pasteBtn);
            longformSplitPanel.appendChild(pasteWrap);

            const actions = document.createElement('div');
            actions.className = 'longform-actions';
            const confirmBtn = document.createElement('button');
            confirmBtn.type = 'button';
            confirmBtn.className = 'btn btn-primary';
            confirmBtn.textContent = 'Split & Download';
            confirmBtn.addEventListener('click', () => confirmLongformSplit(confirmBtn));
            const cancelBtn = document.createElement('button');
            cancelBtn.type = 'button';
            cancelBtn.className = 'btn btn-ghost';
            cancelBtn.textContent = 'Cancel';
            cancelBtn.addEventListener('click', hideLongformPanel);
            actions.appendChild(confirmBtn);
            actions.appendChild(cancelBtn);
            longformSplitPanel.appendChild(actions);
        }

        async function confirmLongformSplit(btnEl) {
            if (!longformDetectedContext) return;
            const segments = _collectLongformSegments();
            if (!segments.length) {
                showToast('Add at least one track with a title first', true);
                return;
            }
            const albumArtistInput = document.getElementById('longformAlbumArtist');
            const albumArtist = (albumArtistInput && albumArtistInput.value.trim()) || 'Various Artists';

            if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Starting…'; }
            try {
                const response = await apiFetch('/api/longform/split', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: longformDetectedContext.url,
                        video_title: longformDetectedContext.video_title,
                        album_artist: albumArtist,
                        segments,
                    }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(data.detail || 'Could not start the split');
                }
                showLongformSplitProgress({
                    status: 'pending', total_segments: data.total_segments,
                    completed_segments: 0, failed_segments: 0,
                    video_title: longformDetectedContext.video_title, complete: false,
                }, data.split_id);
                startLongformSplitPolling(data.split_id);
                spotifyUrlInput.value = '';
            } catch (error) {
                showToast(error.message || 'Could not start the split', true);
                if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Split & Download'; }
            }
        }

        function startLongformSplitPolling(splitId) {
            if (longformSplitPollInterval) {
                clearInterval(longformSplitPollInterval);
            }
            longformSplitPollInterval = setInterval(async () => {
                try {
                    const response = await apiFetch(`/api/longform/${splitId}/status`);
                    if (!response.ok) throw new Error('Failed to get status');
                    const data = await response.json();
                    showLongformSplitProgress(data, splitId);
                    if (data.complete) {
                        clearInterval(longformSplitPollInterval);
                        longformSplitPollInterval = null;
                    }
                } catch (error) {
                    console.error('Long-form split polling error:', error);
                }
            }, 2000);
        }

        function showLongformSplitProgress(data, splitId) {
            if (!longformSplitPanel) return;
            longformSplitPanel.style.display = 'block';
            longformSplitPanel.innerHTML = '';

            const total = data.total_segments || 0;
            const done = (data.completed_segments || 0) + (data.failed_segments || 0);
            const percent = total > 0 ? Math.round((done / total) * 100) : 0;

            let statusText = 'Downloading and splitting…';
            let statusColor = 'var(--accent)';
            if (data.status === 'completed') {
                statusText = 'Complete';
            } else if (data.status === 'completed_with_errors') {
                statusText = 'Complete, with some failures';
                statusColor = 'var(--warning)';
            } else if (data.status === 'failed') {
                statusText = data.error || 'Failed';
                statusColor = 'var(--error)';
            }

            const wrap = document.createElement('div');
            wrap.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <div style="font-weight:600;">${escapeHtml(data.video_title || 'Splitting video')}</div>
                    <div style="font-size:12px;color:${statusColor};">${escapeHtml(statusText)}</div>
                </div>
                <div style="background: var(--bg-tertiary); border-radius: 4px; height: 8px; margin-bottom: 10px; overflow: hidden;">
                    <div style="background: ${statusColor}; height: 100%; width: ${percent}%; transition: width 0.3s ease;"></div>
                </div>
                <div style="font-size:12px;color:var(--text-secondary);">${done} / ${total} segment${total === 1 ? '' : 's'} processed</div>
            `;
            longformSplitPanel.appendChild(wrap);

            if (!data.complete && splitId) {
                const cancelBtn = document.createElement('button');
                cancelBtn.type = 'button';
                cancelBtn.className = 'btn btn-ghost btn-sm';
                cancelBtn.style.marginTop = '8px';
                cancelBtn.textContent = 'Cancel';
                cancelBtn.addEventListener('click', async () => {
                    cancelBtn.disabled = true;
                    try {
                        await apiFetch(`/api/longform/${splitId}/cancel`, { method: 'POST' });
                        showToast('Cancellation requested. The current segment may finish.');
                    } catch (error) {
                        showToast('Could not cancel', true);
                    }
                });
                longformSplitPanel.appendChild(cancelBtn);
            } else if (data.complete) {
                const dismissBtn = document.createElement('button');
                dismissBtn.type = 'button';
                dismissBtn.className = 'btn btn-ghost btn-sm';
                dismissBtn.style.marginTop = '8px';
                dismissBtn.textContent = 'Dismiss';
                dismissBtn.addEventListener('click', hideLongformPanel);
                longformSplitPanel.appendChild(dismissBtn);
            }
        }

        // Only the Bulk Import Fetch box triggers long-form detection - never
        // Search, never bulk-textarea lines. Returns true when the panel took
        // over (caller should stop), false when the caller should fall through
        // to its normal handling for this URL.
        async function tryLongformDetect(url) {
            fetchSpotifyBtn.disabled = true;
            fetchSpotifyBtn.textContent = 'Checking video…';
            const slowHint = setTimeout(() => {
                fetchSpotifyBtn.textContent = 'Hunting for a cue sheet…';
            }, 4000);
            try {
                const response = await apiFetch('/api/longform/detect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.eligible) {
                    return false;
                }
                spotifyError.style.display = 'none';
                renderLongformPanel(data, url);
                return true;
            } catch (error) {
                return false;
            } finally {
                clearTimeout(slowHint);
                fetchSpotifyBtn.disabled = false;
                fetchSpotifyBtn.textContent = 'Fetch';
            }
        }

        // The ordinary playlist scrape (/api/fetch-playlist), factored out of
        // fetchSpotifyPlaylist so both the normal routing path and the "turned
        // out not to be an album after all" fallback from fetchAlbumUrl can
        // call it without duplicating the button-state dance.
        async function doPlaylistFetch(url, isAmazon) {
            spotifyError.style.display = 'none';
            fetchSpotifyBtn.disabled = true;
            fetchSpotifyBtn.textContent = isAmazon ? 'Scraping...' : 'Fetching...';

            // For Spotify, the embed scrape returns in seconds; if the playlist
            // is large or private, the server falls back to a headless browser
            // which takes longer. Nudge the button text after a few seconds
            // so the user knows we haven't ghosted them.
            const isSpotify = /^https?:\/\/open\.spotify\.com\//.test(url);
            const slowHints = [];
            if (isSpotify) {
                slowHints.push(setTimeout(() => {
                    fetchSpotifyBtn.textContent = 'Spinning up browser...';
                }, 6000));
                slowHints.push(setTimeout(() => {
                    fetchSpotifyBtn.textContent = 'Scrolling playlist (large lists take a minute)...';
                }, 15000));
            }

            try {
                const response = await apiFetch('/api/fetch-playlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });

                // Check content type before parsing
                const contentType = response.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    throw new Error('Server error - please check if the app is running');
                }

                const data = await response.json();

                if (!response.ok) {
                    if (data.detail === 'spotify_cookies_expired') {
                        throw new Error('Spotify cookies have expired. Go to Settings to update them.');
                    }
                    throw new Error(data.detail || 'Failed to fetch playlist');
                }

                if (data.tracks && data.tracks.length > 0) {
                    // Populate the textarea with all tracks (no limit)
                    bulkInput.value = data.tracks.join('\n');
                    if (Array.isArray(data.original_youtube_video_ids)) {
                        bulkInput.dataset.originalYoutubeVideoMap = JSON.stringify(
                            data.tracks.map((track, index) => ({
                                track,
                                video_id: data.original_youtube_video_ids[index] || null
                            }))
                        );
                    } else {
                        delete bulkInput.dataset.originalYoutubeVideoMap;
                    }
                    updateLineCounter();

                    // Auto-fill playlist name if checkbox is checked
                    if (createPlaylistCheckbox.checked && data.playlist_name) {
                        playlistNameInput.value = data.playlist_name;
                        playlistNameInput.dataset.sourceUrl = url;
                        updatePlaylistNameHint();
                    }

                    // For SoundCloud playlists, default source chips to SC only - the tracks
                    // are already on SoundCloud, so there's no reason to go hunting elsewhere
                    if (data.platform === 'soundcloud') {
                        setWatchedPreferredSource('soundcloud');
                    }

                    // Show toast with result (include warning if present)
                    if (data.warning) {
                        spotifyError.textContent = `Warning: ${data.warning}`;
                        spotifyError.style.color = 'var(--warning, #f59e0b)';
                        spotifyError.style.display = 'block';
                        showToast(`Loaded ${data.tracks.length} tracks (truncated) - ${data.warning}`, true);
                    } else {
                        showToast(`Loaded ${data.tracks.length} tracks from "${data.playlist_name}"`);
                    }

                    // Clear the URL input
                    spotifyUrlInput.value = '';
                } else {
                    throw new Error('No tracks found in playlist');
                }
                return true;
            } catch (error) {
                spotifyError.textContent = error.message;
                spotifyError.style.color = 'var(--error)';
                spotifyError.style.display = 'block';
                return false;
            } finally {
                slowHints.forEach(clearTimeout);
                fetchSpotifyBtn.disabled = false;
                fetchSpotifyBtn.textContent = 'Fetch';
            }
        }

        // Single input, works out what it was given: playlist URL, MusicBrainz
        // release URL, Spotify/Apple album URL, or plain text to search
        // MusicBrainz for by name. This is the whole point of unifying Bulk
        // Import; nobody should have to pick from a dropdown before they've
        // even typed anything.
        async function fetchSpotifyPlaylist() {
            const url = spotifyUrlInput.value.trim();
            if (!url) {
                spotifyError.textContent = 'Please enter a URL, or an album name to search';
                spotifyError.style.display = 'block';
                return;
            }
            hideLongformPanel();

            // Long-form YouTube splitting: only for a single video, so it never
            // touches a genuine curated playlist (list=PL.../OLAK5uy...). A bare
            // watch URL (no list=) or YouTube's own auto-generated "RD..." radio
            // list both qualify - RD gets appended to normal watch URLs and isn't
            // something a user deliberately curated. When the video turns out
            // not to be a split candidate (too short, or lookup failed), this
            // falls straight through to the unchanged behaviour below: a bare
            // watch URL hits "Unsupported URL", an RD-list URL goes through the
            // ordinary playlist-import path.
            if (/^https?:\/\/(?:www\.|music\.)?youtube\.com\/watch\?/i.test(url)) {
                let listParam = null;
                try {
                    listParam = new URL(url).searchParams.get('list');
                } catch (e) { /* not a parseable absolute URL; fall through */ }
                const isRealPlaylist = listParam && !listParam.startsWith('RD');
                if (!isRealPlaylist) {
                    const handled = await tryLongformDetect(url);
                    if (handled) return;
                }
            }

            // URL validation - Spotify playlists/albums, Amazon Music playlists, Apple Music, YouTube/YT Music playlists, SoundCloud sets/likes, ListenBrainz, Tidal/Monochrome, Beatport, Official Charts, Qobuz
            const isSpotifyAlbum = url.match(/^https?:\/\/open\.spotify\.com\/album\//);
            const isSpotify = isSpotifyAlbum || url.match(/^https?:\/\/open\.spotify\.com\/playlist\//);
            const isAmazon = url.match(/^https?:\/\/music\.amazon\.[a-z.]+\/(user-playlists|playlists)\//);
            const isAppleAlbum = url.match(/^https?:\/\/music\.apple\.com\/(?:[a-z]{2}|library)\/album\//i);
            const isApple = isAppleAlbum || url.match(/^https?:\/\/music\.apple\.com\/(?:[a-z]{2}|library)\/playlist\//i);
            const isYouTube = url.match(/^https?:\/\/(www\.|music\.)?youtube\.com\/(playlist|watch)\?[^"]*list=/i);
            const isSoundCloud = url.match(/^https?:\/\/soundcloud\.com\/[^/]+\/(sets\/[^/?]+|likes)/i);
            // The bare "^[a-zA-Z0-9_-]+$" alternative is a bare ListenBrainz
            // username (no URL at all) - existing behaviour. It happens to also
            // match a one-word album title ("Trainspotting"), which is exactly
            // the ambiguity handled below: try ListenBrainz first, and only if
            // that comes back empty does it get treated as an album search.
            const isListenBrainzUrl = url.match(/^https?:\/\/listenbrainz\.org\/(playlist|user)\//i);
            const isBareWord = url.match(/^[a-zA-Z0-9_-]+$/);
            const isListenBrainz = isListenBrainzUrl || isBareWord;
            const isTidalAlbum = url.match(/^https?:\/\/(?:www\.)?tidal\.com\/(?:browse\/)?album\/\d+/i);
            const isTidal = isTidalAlbum || url.match(/^https?:\/\/tidal\.com\/(?:browse\/)?playlist\//i);
            const isMonochromeAlbum = url.match(/^https?:\/\/(?:www\.)?(?:monochrome\.tf|monochrome\.st|monochrome\.samidy\.com)\/album\/(?:(?:t|tracks|mono|monochrome)\/)?\d+/i);
            const isMonochrome = isMonochromeAlbum || url.match(/^https?:\/\/(?:www\.)?(?:monochrome\.tf|monochrome\.st|monochrome\.samidy\.com)\/playlist\//i);
            // Beatport calls an album a "release"; charts and Top 100 are not albums.
            const isBeatportRelease = url.match(/^https?:\/\/(?:www\.)?beatport\.com\/release\/[^/?#]+\/\d+/i);
            const isBeatport = isBeatportRelease || url.match(/^https?:\/\/(?:www\.)?beatport\.com\/(top-100|genre\/[^/]+\/\d+\/top-100|chart\/[^/]+\/\d+)/i);
            // Song charts read as playlists; the server turns an album chart away with its reason.
            const isOfficialCharts = url.match(/^https?:\/\/(?:www\.)?officialcharts\.com\/charts\/[a-z0-9-]+\//i);
            // Qobuz store pages carry a store (gb-en) and a slug; open. and play. share links only the id.
            const isQobuzAlbum = url.match(/^https?:\/\/(?:(?:www\.)?qobuz\.com\/[a-z]{2}-[a-z]{2}\/album\/[^/?#]+|(?:open|play)\.qobuz\.com\/album)\/[a-z0-9]+/i);
            const isQobuz = isQobuzAlbum || url.match(/^https?:\/\/(?:(?:www\.)?qobuz\.com\/[a-z]{2}-[a-z]{2}\/playlists\/(?:[^/?#]+\/)?|(?:open|play)\.qobuz\.com\/playlist\/)\d+/i);
            // YouTube's auto-generated album playlists are the OLAK5uy_ ones. An
            // ordinary PL... playlist or an RD... mix is not an album.
            const isYouTubeAlbum = url.match(/^https?:\/\/(?:www\.|music\.)?youtube\.com\/(?:playlist|watch)\?[^"]*list=OLAK5uy_/i);
            // MusicBrainz release/release-group URLs carry the MBID already, so they
            // skip the track-list textarea entirely and go straight to the proper
            // album pipeline: Albums/Artist/Album/, cover art, the works.
            const isMusicBrainz = url.match(/^https?:\/\/(?:beta\.)?musicbrainz\.org\/(release|release-group)\/[0-9a-f-]{36}/i);
            const looksLikeUrl = /^https?:\/\//i.test(url);

            if (isMusicBrainz) {
                await fetchMusicBrainzRelease(url);
                return;
            }
            // ALBUM url on any supported service: resolve-album-url first
            // (confidence gate), NOT the ordinary playlist scrape, or the whole
            // album flattens into a track list and loses its
            // folder/artwork/.albuminfo/track numbers.
            if (isSpotifyAlbum || isAppleAlbum || isYouTubeAlbum || isBeatportRelease
                || isTidalAlbum || isMonochromeAlbum || isQobuzAlbum) {
                await fetchAlbumUrl(url);
                return;
            }
            if (!isSpotify && !isAmazon && !isApple && !isYouTube && !isSoundCloud && !isListenBrainz && !isTidal && !isMonochrome && !isBeatport && !isOfficialCharts && !isQobuz) {
                if (!looksLikeUrl) {
                    // No scheme at all, and not a bare ListenBrainz-shaped word:
                    // this is somebody typing an album (or "Artist - Album") name.
                    await searchReleaseByName(url);
                    return;
                }
                spotifyError.textContent = 'Unsupported URL. Paste a Spotify, YouTube, Apple Music, Amazon Music, SoundCloud sets/likes, ListenBrainz, Tidal, Monochrome, Qobuz, MusicBrainz release, Beatport, or UK Official Charts link, or type an artist/album name to search.';
                spotifyError.style.display = 'block';
                return;
            }

            const ok = await doPlaylistFetch(url, isAmazon);
            if (!ok && isBareWord && !isListenBrainzUrl) {
                // The bare word didn't resolve as a ListenBrainz username (blame
                // ListenBrainz for having such relaxed rules on those); it is
                // far more likely to be a one-word album title, so have a go at
                // that instead, quietly, rather than leaving the user staring
                // at a ListenBrainz error for an album search.
                await searchReleaseByName(url);
            }
        }

        fetchSpotifyBtn.addEventListener('click', fetchSpotifyPlaylist);
        spotifyUrlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                fetchSpotifyPlaylist();
            }
        });

        // Show/hide playlist name input (and Playlists folder checkbox) when checkbox is toggled
        createPlaylistCheckbox.addEventListener('change', () => {
            playlistNameInput.style.display = createPlaylistCheckbox.checked ? 'block' : 'none';
            const playlistsDirRow = document.getElementById('usePlaylistsDirRow');
            const usePlaylistsDirCheckbox = document.getElementById('usePlaylistsDirCheckbox');
            if (playlistsDirRow) {
                playlistsDirRow.style.display = (createPlaylistCheckbox.checked && serverConfig.playlists_subdir) ? 'flex' : 'none';
            }
            if (usePlaylistsDirCheckbox && createPlaylistCheckbox.checked && serverConfig.playlists_subdir) {
                // Default playlist-creation imports to the Playlists folder when configured.
                usePlaylistsDirCheckbox.checked = true;
            }
            if (createPlaylistCheckbox.checked) {
                playlistNameInput.focus();
                // Fresh suggestions each time: the last import may have made a playlist.
                loadPlaylists().then(updatePlaylistNameHint);
            }
            updatePlaylistNameHint();
        });

        // Typing an existing name adds to that playlist, which used to happen
        // without a word. Say what a name will do before it does it. An exact
        // match only: the file system is case-sensitive, so "rock mix" would be
        // a new playlist beside "Rock Mix", not more of it.
        function updatePlaylistNameHint() {
            const hint = document.getElementById('playlistNameHint');
            if (!hint) return;
            const name = playlistNameInput.value.trim();
            const existing = createPlaylistCheckbox.checked && name
                ? _playlists.find(pl => pl.name === name)
                : null;
            if (!existing) {
                hint.style.display = 'none';
                hint.textContent = '';
                hint.classList.remove('is-warning');
                return;
            }
            const intoPlaylistsFolder = Boolean(serverConfig.playlists_subdir)
                && document.getElementById('usePlaylistsDirCheckbox')?.checked;
            let text;
            if (existing.is_watched) {
                text = `"${name}" is a watched playlist. Its M3U is rebuilt from the source on every refresh, so tracks added here would drop off it again.`;
            } else if (intoPlaylistsFolder) {
                text = `Adds these to your existing "${name}" playlist.`;
            } else {
                text = `Saves a separate "${name}" in Singles. Tick "Save files to Playlists folder" to add to the existing one.`;
            }
            hint.textContent = text;
            hint.classList.toggle('is-warning', !!existing.is_watched);
            hint.style.display = 'block';
        }

        playlistNameInput.addEventListener('input', updatePlaylistNameHint);
        document.getElementById('usePlaylistsDirCheckbox')?.addEventListener('change', updatePlaylistNameHint);
