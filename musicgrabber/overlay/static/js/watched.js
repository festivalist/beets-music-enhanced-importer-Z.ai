        // Watched tab: playlists, Upgrades, the provenance Audit, M3U files and the
        // library picker.

        const watchedRefreshPending = new Map();
        let watchedRefreshPollInterval = null;
        let watchedLoadInFlight = false;
        document.getElementById('watchedModePills')
            ?.addEventListener('pillchange', (e) => setWatchedMode(e.detail.value));
        watchedList.addEventListener('click', (e) => {
            const btn = e.target.closest('button[data-action]');
            if (!btn || !watchedList.contains(btn)) return;

            const action = btn.dataset.action;
            if (action === 'retry-missing-track') {
                retryMissingTrack(
                    btn.dataset.playlistId || '',
                    btn.dataset.artist || '',
                    btn.dataset.title || '',
                    btn.dataset.rowId || ''
                );
                return;
            }

            if (action === 'search-missing-track') {
                searchMissingTrack(
                    btn.dataset.playlistId || '',
                    btn.dataset.playlistName || '',
                    btn.dataset.artist || '',
                    btn.dataset.title || ''
                );
                return;
            }

            if (action === 'match-missing-track-library') {
                matchMissingTrackFromLibrary(
                    btn.dataset.playlistId || '',
                    btn.dataset.trackHash || '',
                    btn.dataset.artist || '',
                    btn.dataset.title || '',
                    btn.dataset.rowId || ''
                );
                return;
            }

            if (action === 'find-missing-track-versions') {
                openMissingTrackVersionsModal(
                    btn.dataset.playlistId || '',
                    btn.dataset.playlistName || '',
                    btn.dataset.artist || '',
                    btn.dataset.title || '',
                    btn.dataset.rowId || ''
                );
                return;
            }

            if (action === 'replace-watched-track') {
                replaceTrack(
                    btn.dataset.playlistId || '',
                    btn.dataset.playlistName || '',
                    btn.dataset.artist || '',
                    btn.dataset.title || '',
                    btn.dataset.trackHash || '',
                    btn.dataset.rowId || ''
                );
                return;
            }

            if (action === 'refresh-watched-playlist') {
                refreshWatchedPlaylist(btn.dataset.playlistId || '');
                return;
            }

            if (action === 'toggle-missing-tracks') {
                toggleMissingTracks(btn.dataset.playlistId || '');
                return;
            }

            if (action === 'toggle-watched-playlist') {
                toggleWatchedPlaylist(
                    btn.dataset.playlistId || '',
                    btn.dataset.enabled === 'true' ? 'false' : 'true'
                );
                return;
            }

            if (action === 'toggle-playlist-track-list') {
                toggleTrackList(
                    btn.dataset.playlistId || '',
                    btn.dataset.playlistName || ''
                );
                return;
            }

            if (action === 'rename-watched-playlist') {
                renameWatchedPlaylist(
                    btn.dataset.playlistId || '',
                    btn.dataset.playlistName || '',
                    btn.dataset.customName || ''
                );
                return;
            }

            if (action === 'copy-watched-playlist-url') {
                copyWatchedPlaylistUrl(btn.dataset.url || '');
                return;
            }

            if (action === 'delete-watched-playlist') {
                deleteWatchedPlaylist(
                    btn.dataset.playlistId || '',
                    btn.dataset.playlistName || ''
                );
            }
        });
        // =============================================================================
        // Watched Playlists
        // =============================================================================

        // A re-render replaces the list's innerHTML, which would slam every open
        // Missing/Tracks panel shut and put "Loading..." back. Lift the open ones out
        // first and drop the same DOM nodes back over their fresh placeholders, so
        // content, button states, and any fetch still in flight (it holds the node)
        // all carry on as if nothing happened.
        function liftOpenPanels(listEl) {
            const open = [];
            listEl.querySelectorAll('.watched-card-expanded, .watched-singles-start').forEach(el => {
                if (el.id && el.style.display !== 'none') open.push(el);
            });
            return open;
        }

        function dropOpenPanelsBack(open) {
            for (const el of open) {
                const fresh = document.getElementById(el.id);
                if (fresh && fresh !== el) fresh.replaceWith(el);
            }
        }

        async function loadWatchedPlaylists(showLoading = true) {
            if (watchedLoadInFlight) return;
            watchedLoadInFlight = true;
            if (showLoading) {
                watchedList.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            }

            try {
                // Fetch schedule info and playlists in parallel
                const [scheduleRes, playlistsRes] = await Promise.all([
                    apiFetch('/api/watched-playlists/schedule'),
                    apiFetch('/api/watched-playlists')
                ]);

                // Update schedule info
                if (scheduleRes.ok) {
                    const schedule = await scheduleRes.json();
                    if (schedule.enabled) {
                        const hours = schedule.check_interval_hours;
                        let intervalText = `${hours} hours`;
                        if (hours === 24) intervalText = 'daily';
                        else if (hours === 168) intervalText = 'weekly';
                        else if (hours >= 720) intervalText = 'monthly';
                        watchedScheduleInfo.textContent = `Automatic checks follow each playlist's own interval. The global ${intervalText} setting is only the maximum time between scheduler sweeps.`;
                    } else {
                        watchedScheduleInfo.textContent = 'Automatic checks disabled. Use "Check All Now" or set WATCHED_PLAYLIST_CHECK_HOURS.';
                    }
                }

                if (!playlistsRes.ok) throw new Error('Failed to load watched playlists');

                const data = await playlistsRes.json();
                renderWatchedPlaylists(data.playlists);
                populateSourceChips();
            } catch (error) {
                if (showLoading) {
                    watchedList.innerHTML = `
                        <div class="empty-state">
                            <p style="color: var(--error);">Failed to load watched playlists</p>
                        </div>
                    `;
                }
            } finally {
                watchedLoadInFlight = false;
            }
        }

        function renderWatchedPlaylists(playlists) {
            if (!playlists || playlists.length === 0) {
                if (watchedRefreshPollInterval) {
                    clearInterval(watchedRefreshPollInterval);
                    watchedRefreshPollInterval = null;
                }
                watchedList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon"><i class="fa-solid fa-eye"></i></div>
                        <p>No watched playlists yet</p>
                        <p style="font-size: 12px; margin-top: 8px; opacity: 0.6;">Add a Spotify or YouTube playlist above</p>
                    </div>
                `;
                return;
            }

            const openPanels = liftOpenPanels(watchedList);
            const scrollY = window.scrollY;
            watchedList.innerHTML = playlists.map(p => {
                const refreshState = p.refresh_state || 'idle';
                const localRefresh = watchedRefreshPending.get(p.id);
                const isRefreshing = refreshState === 'running' || !!localRefresh;
                const refreshStage = (refreshState === 'running' ? p.refresh_stage : null) || (localRefresh ? localRefresh.stage : null);
                const refreshStartedAt = (refreshState === 'running' ? p.refresh_started_at : null)
                    || (localRefresh ? localRefresh.startedAt : null);
                const platformIcons = {
                    spotify: '<i class="fa-brands fa-spotify" title="Spotify"></i>',
                    youtube: '<i class="fa-brands fa-youtube" title="YouTube"></i>',
                    apple: '<i class="fa-brands fa-apple" title="Apple Music"></i>',
                    amazon: '<i class="fa-brands fa-amazon" title="Amazon Music"></i>',
                    listenbrainz: '<img src="/static/images/ListenBrainzLogo.svg" title="ListenBrainz" style="width:1em;height:1em;vertical-align:-0.125em;">',
                    soundcloud: '<i class="fa-brands fa-soundcloud" title="SoundCloud"></i>',
                    tidal: '<img src="/static/images/tidal-round-black-icon.svg" title="Tidal" style="width:1em;height:1em;vertical-align:-0.125em;">',
                    monochrome: '<span title="Monochrome" style="font-size:0.75em;font-weight:700;">MONO</span>',
                    beatport: '<img src="/static/images/BeatPortLogo.svg" title="Beatport" style="width:1em;height:1em;vertical-align:-0.125em;">',
                    officialcharts: '<i class="fa-solid fa-ranking-star" title="UK Official Charts"></i>',
                    qobuz: '<span title="Qobuz" style="font-size:0.75em;font-weight:700;">QOBUZ</span>'
                };
                const platformIcon = platformIcons[p.platform] || '<i class="fa-solid fa-list"></i>';
                const lastChecked = p.last_checked ? formatTimeAgo(p.last_checked) : 'Never';
                const lastCheckedExact = p.last_checked ? formatTimeExact(p.last_checked) : '';
                const statusColor = p.enabled ? 'var(--accent)' : 'var(--text-secondary)';
                const intervalText = p.refresh_interval_hours >= 720 ? 'monthly' :
                                     p.refresh_interval_hours === 168 ? 'weekly' :
                                     p.refresh_interval_hours === 24 ? 'daily' :
                                     p.refresh_interval_hours === 12 ? 'every 12h' :
                                     p.refresh_interval_hours === 6 ? 'every 6h' :
                                     p.refresh_interval_hours === 1 ? 'hourly' :
                                     p.refresh_interval_hours === 0.5 ? 'every 30min' :
                                     `every ${p.refresh_interval_hours}h`;
                const refreshLabel = isRefreshing
                    ? formatRefreshStage(refreshStage, refreshStartedAt, p.platform)
                    : '';
                // Tracks that have left the upstream playlist. Mirror mode has stopped
                // listing them, append mode is keeping them on purpose; either way they
                // are not part of "how big is this playlist", which is what the first
                // two figures answer.
                const departedCount = p.departed_count || 0;
                const departedText = departedCount
                    ? ` &middot; ${departedCount} ${p.sync_mode === 'mirror' ? 'no longer upstream' : 'kept from earlier'}`
                    : '';

                return `
                    <div class="watched-card">
                        <div class="watched-card-header">
                            <span>${platformIcon}</span>
                            <span class="watched-card-name"${p.custom_name ? ` title="Originally ${escapeAttr(p.name)}"` : ''}>${escapeHtml(p.custom_name || p.name)}</span>
                            ${isRefreshing ? `<span class="watched-card-refreshing"><span class="watched-refresh-spinner"></span>${escapeHtml(refreshLabel)}</span>` : ''}
                            ${!p.enabled ? '<span class="watched-card-paused">Paused</span>' : ''}
                        </div>
                        <div class="watched-card-meta">
                            ${p.tracked_count} tracks · ${p.downloaded_count || 0} downloaded${departedText} · ${intervalText} · Last checked: <span title="${escapeAttr(lastCheckedExact)}">${escapeHtml(lastChecked)}</span>
                        </div>
                        ${refreshState === 'error' && p.refresh_error && !isRefreshing ? `
                        <div class="watched-card-refresh-error">
                            <i class="fa-solid fa-circle-exclamation"></i>
                            <span>${escapeHtml(p.refresh_error)}</span>
                        </div>` : ''}
                        <div class="watched-card-settings">
                            <label class="watched-card-toggle" title="Choose whether new tracks keep their source format or are converted">
                                ${conversionChoiceLabel(p.convert_audio)}
                                <div class="toggle-switch">
                                    <input type="checkbox" ${p.convert_audio ? 'checked' : ''} ${uiAction('updateWatchedPlaylistConversion', [p.id], 'change')}>
                                    <span class="toggle-slider"></span>
                                </div>
                            </label>
                            <label class="watched-card-toggle" title="Generate and update a .m3u playlist file as tracks are downloaded. Switching this off stops MusicGrabber updating it; any .m3u already written stays where it is, for you to keep or delete. With auto-album routing on, the M3U is also what lets tracks go off to their album folders: without one they stay in the playlist folder.">
                                M3U
                                <div class="toggle-switch">
                                    <input type="checkbox" ${p.make_m3u ? 'checked' : ''} ${uiAction('updateWatchedPlaylistM3u', [p.id], 'change')}>
                                    <span class="toggle-slider"></span>
                                </div>
                            </label>
                            ${serverConfig.playlists_subdir ? `
                            <label class="watched-card-toggle" title="Save downloaded tracks to the Playlists folder instead of Singles">
                                Playlists folder
                                <div class="toggle-switch">
                                    <input type="checkbox" ${p.use_playlists_dir ? 'checked' : ''} ${uiAction('updateWatchedPlaylistUsePlaylists', [p.id], 'change')}>
                                    <span class="toggle-slider"></span>
                                </div>
                            </label>` : ''}
                            <label class="watched-card-toggle" title="Append: M3U grows as new tracks arrive. Mirror: M3U stays in sync with upstream - removed tracks drop out (audio files kept).">
                                Sync
                                <select ${uiAction('updateWatchedPlaylistSyncMode', [p.id], 'change')} class="watched-card-select">
                                    <option value="append" ${(p.sync_mode || 'append') === 'append' ? 'selected' : ''}>Append</option>
                                    <option value="mirror" ${p.sync_mode === 'mirror' ? 'selected' : ''}>Mirror</option>
                                </select>
                            </label>
                            <label class="watched-card-toggle" title="Choose whether this playlist inherits the global missing-file policy, re-downloads vanished files, or leaves downloads alone after an external organiser moves them.">
                                Missing files
                                <select ${uiAction('updateWatchedPlaylistRedownloadMissing', [p.id], 'change')} class="watched-card-select">
                                    <option value="inherit" ${p.redownload_missing_files == null ? 'selected' : ''}>Global setting</option>
                                    <option value="true" ${p.redownload_missing_files === 1 || p.redownload_missing_files === true ? 'selected' : ''}>Re-download</option>
                                    <option value="false" ${p.redownload_missing_files === 0 || p.redownload_missing_files === false ? 'selected' : ''}>Leave alone</option>
                                </select>
                            </label>
                            <label class="watched-card-toggle" title="Which search sources to use when downloading new tracks for this playlist. Deselect all to search everything.">
                                Sources
                                <div class="watched-sources-chips" data-playlist-id="${p.id}" data-preferred="${escapeAttr(p.preferred_sources || 'all')}">
                                    ${renderSourceChips(p.id, p.preferred_sources || 'all')}
                                </div>
                            </label>
                            <label class="watched-card-toggle" title="Break ties in favour of this source within the same quality tier. Allowed lossless results still come before lossy ones.">
                                Preferred
                                <select ${uiAction('updateWatchedPlaylistPrioritySource', [p.id], 'change')} class="watched-card-select" data-priority-source="${escapeAttr(p.priority_source || '')}">
                                    ${renderPrioritySourceOptions(p.priority_source || '')}
                                </select>
                            </label>
                        </div>
                        ${p.unresolved_tracks > 0 ? `
                        <div class="watched-card-stale-warning">
                            <i class="fa-solid fa-circle-info"></i>
                            <span><strong>${p.unresolved_tracks} downloaded track${p.unresolved_tracks === 1 ? '' : 's'}</strong> can no longer be found on disk. This playlist's missing-file policy is leaving them alone rather than fetching duplicates, so they will not appear in the M3U. They are listed under Missing: if another tool has moved or renamed them, From Library points the playlist at their new home; if you deleted them on purpose, Retry fetches one back.</span>
                        </div>` : ''}
                        ${p.stale_navidrome_paths > 0 ? `
                        <div class="watched-card-stale-warning">
                            <i class="fa-solid fa-triangle-exclamation"></i>
                            <span><strong>${p.stale_navidrome_paths} track${p.stale_navidrome_paths === 1 ? '' : 's'}</strong> in the M3U point to files that no longer exist on disk but are still in Navidrome's database. To fix: open Navidrome, go to <strong>Settings &gt; Missing Files</strong>, select all, and click <strong>Remove from Database</strong>. Then trigger a library scan and refresh this playlist.</span>
                        </div>` : ''}
                        <div class="watched-card-actions">
                            <button type="button"
                                data-action="refresh-watched-playlist"
                                data-playlist-id="${escapeAttr(p.id)}"
                                class="watched-action-btn" title="${isRefreshing ? `Refresh in progress: ${escapeAttr(refreshLabel)}` : 'Check for new tracks now'}" ${isRefreshing ? 'disabled' : ''}>${isRefreshing ? 'Checking...' : 'Refresh'}</button>
                            <button type="button"
                                data-action="toggle-missing-tracks"
                                data-playlist-id="${escapeAttr(p.id)}"
                                class="watched-action-btn" title="Show tracks that failed to download, or whose file has gone">Missing</button>
                            <button type="button"
                                data-action="toggle-playlist-track-list"
                                data-playlist-id="${escapeAttr(p.id)}"
                                data-playlist-name="${escapeAttr(p.custom_name || p.name)}"
                                class="watched-action-btn" title="Show all tracks and their download status">Tracks</button>
                            <button type="button"
                                data-action="rename-watched-playlist"
                                data-playlist-id="${escapeAttr(p.id)}"
                                data-playlist-name="${escapeAttr(p.name)}"
                                data-custom-name="${escapeAttr(p.custom_name || '')}"
                                class="watched-action-btn" title="Give this playlist a name of your own. Its M3U takes the new name; its folder keeps the original">Rename</button>
                            <button type="button"
                                data-action="copy-watched-playlist-url"
                                data-url="${escapeAttr(p.url)}"
                                class="watched-action-btn" title="Copy playlist URL">Copy URL</button>
                            <button type="button"
                                data-action="toggle-watched-playlist"
                                data-playlist-id="${escapeAttr(p.id)}"
                                data-enabled="${p.enabled ? 'true' : 'false'}"
                                class="watched-action-btn watched-action-pause">${p.enabled ? 'Pause' : 'Resume'}</button>
                            <button type="button"
                                data-action="delete-watched-playlist"
                                data-playlist-id="${escapeAttr(p.id)}"
                                data-playlist-name="${escapeAttr(p.custom_name || p.name)}"
                                class="watched-action-btn watched-action-delete">Delete</button>
                        </div>
                        <div id="missing-${p.id}" class="watched-card-expanded" style="display: none;">Loading...</div>
                        <div id="tracks-${p.id}" class="watched-card-expanded" style="display: none;">Loading...</div>
                    </div>
                `;
            }).join('');
            dropOpenPanelsBack(openPanels);
            if (window.scrollY !== scrollY) window.scrollTo(0, scrollY);

            const anyRunning = playlists.some(p => p.refresh_state === 'running') || watchedRefreshPending.size > 0;
            if (currentTab === 'watched' && anyRunning && !watchedRefreshPollInterval) {
                watchedRefreshPollInterval = setInterval(() => {
                    loadWatchedPlaylists(false);
                }, 2000);
            } else if ((!anyRunning || currentTab !== 'watched') && watchedRefreshPollInterval) {
                clearInterval(watchedRefreshPollInterval);
                watchedRefreshPollInterval = null;
            }
        }

        function formatRefreshStage(stage, startedAt = null, platform = null) {
            const labels = {
                starting: 'Starting...',
                fetching: 'Fetching playlist...',
                diffing: 'Comparing tracks...',
                queueing: 'Queueing downloads...',
                finalizing: 'Finalizing...',
                rebuilding_m3u: 'Rebuilding M3U...',
                done: 'Done',
                failed: 'Failed'
            };
            const base = !stage ? 'Checking...' : (labels[stage] || stage.replace(/_/g, ' '));

            if (!startedAt) return base;
            const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(startedAt) ? startedAt : `${String(startedAt).replace(' ', 'T')}Z`;
            const startedMs = new Date(normalized).getTime();
            if (Number.isNaN(startedMs)) return base;
            const elapsedSec = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
            const mins = Math.floor(elapsedSec / 60);
            const secs = elapsedSec % 60;
            const elapsedText = mins > 0 ? `${mins}m ${String(secs).padStart(2, '0')}s` : `${secs}s`;

            if (stage === 'fetching' && platform === 'spotify' && elapsedSec >= 90) {
                return `${base} ${elapsedText} (large playlists can take a few minutes)`;
            }
            return `${base} ${elapsedText}`;
        }

        function formatTimeAgo(isoString) {
            if (!isoString) return '';
            const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(isoString) ? isoString : `${String(isoString).replace(' ', 'T')}Z`;
            const date = new Date(normalized);
            if (Number.isNaN(date.getTime())) return '';
            const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
            if (seconds < 60) return 'just now';
            if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
            if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
            if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
            return formatDateYmd(isoString);
        }

        function formatTimeExact(isoString) {
            if (!isoString) return '';
            const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(isoString) ? isoString : `${String(isoString).replace(' ', 'T')}Z`;
            const date = new Date(normalized);
            return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
        }

        async function addWatchedPlaylist() {
            const url = watchedUrlInput.value.trim();
            if (!url) {
                watchedError.textContent = 'Please enter a playlist URL';
                watchedError.style.display = 'block';
                return;
            }

            // Detect platform so we can show helpful hints (e.g. Spotify large playlist warning)
            let platform = null;
            if (url.includes('spotify.com')) platform = 'spotify';
            else if (url.includes('youtube.com') || url.includes('youtu.be')) platform = 'youtube';
            else if (url.includes('music.apple.com')) platform = 'apple';
            else if (url.includes('amazon.') || url.includes('music.amazon')) platform = 'amazon';

            watchedError.style.display = 'none';
            addWatchedBtn.disabled = true;
            addWatchedBtn.textContent = 'Watch';

            const statusEl = document.getElementById('watchedAddStatus');
            const startedAt = new Date().toISOString();
            let timerInterval = null;

            function updateStatus(stage) {
                statusEl.innerHTML = `<span class="watched-card-refreshing"><span class="watched-refresh-spinner"></span>${escapeHtml(formatRefreshStage(stage, startedAt, platform))}</span>`;
                statusEl.style.display = 'block';
            }

            // Tick the elapsed timer every second while in-flight
            updateStatus('fetching');
            timerInterval = setInterval(() => updateStatus('fetching'), 1000);

            try {
                const response = await apiFetch('/api/watched-playlists', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: url,
                        refresh_interval_hours: parseFloat(watchedIntervalSelect.value),
                        convert_audio: watchedConvertAudio ? watchedConvertAudio.checked : convertAudioCheckbox.checked,
                        make_m3u: document.getElementById('watchedMakeM3u') ? document.getElementById('watchedMakeM3u').checked : false,
                        use_playlists_dir: document.getElementById('watchedUsePlaylistsDir') ? document.getElementById('watchedUsePlaylistsDir').checked : false,
                        sync_mode: document.getElementById('watchedSyncModeSelect') ? document.getElementById('watchedSyncModeSelect').value : 'append',
                        preferred_sources: getWatchedPreferredSources(),
                        priority_source: (document.getElementById('watchedPrioritySource')?.value || '') || null,
                        custom_subdir: (document.getElementById('watchedCustomSubdir')?.value || '').trim() || null
                    })
                });

                if (!response.ok) {
                    const ct = response.headers.get('content-type') || '';
                    if (ct.includes('application/json')) {
                        const error = await response.json();
                        if (error.detail === 'spotify_cookies_expired') {
                            throw new Error('Spotify cookies have expired. Go to Settings to update them.');
                        }
                        throw new Error(error.detail || 'Failed to add playlist');
                    }
                    const text = (await response.text()).slice(0, 200);
                    throw new Error(`Server error ${response.status}: ${text || response.statusText}`);
                }

                const data = await response.json();
                if (data.warning) {
                    watchedError.textContent = `Warning: ${data.warning}`;
                    watchedError.style.color = 'var(--warning, #f59e0b)';
                    watchedError.style.display = 'block';
                    showToast(`Now watching "${data.name}" (${data.track_count} tracks, truncated)`, true);
                } else {
                    showToast(`Now watching "${data.name}" (${data.track_count} tracks)`);
                }
                watchedUrlInput.value = '';
                const customSubdirInput = document.getElementById('watchedCustomSubdir');
                if (customSubdirInput) { customSubdirInput.value = ''; clearWatchedCustomSubdir(); }
                loadWatchedPlaylists();
            } catch (error) {
                watchedError.textContent = error.message;
                watchedError.style.color = 'var(--error)';
                watchedError.style.display = 'block';
            } finally {
                clearInterval(timerInterval);
                statusEl.style.display = 'none';
                addWatchedBtn.disabled = false;
                addWatchedBtn.textContent = 'Watch';
            }
        }

        function toggleLbRow() {
            const row = document.getElementById('lbRow');
            const btn = document.getElementById('lbToggleBtn');
            const visible = row.style.display !== 'none';
            row.style.display = visible ? 'none' : 'flex';
            btn.textContent = visible ? '+ ListenBrainz "Created for You" playlists' : '− ListenBrainz "Created for You" playlists';
            if (!visible) document.getElementById('lbUsernameInput').focus();
        }

        // The easy-add for people starting out: a UK chart in one tap.
        function toggleChartsRow() {
            const row = document.getElementById('chartsRow');
            const btn = document.getElementById('chartsToggleBtn');
            const visible = row.style.display !== 'none';
            row.style.display = visible ? 'none' : 'block';
            btn.textContent = visible ? '+ UK Official Charts' : '− UK Official Charts';
        }

        // A chart changes every week, so its playlist mirrors it: the settings
        // change in the form where they can be seen, then it is watched as if
        // the link had been pasted.
        function watchChartPreset(url) {
            if (addWatchedBtn.disabled) return;
            watchedUrlInput.value = url;
            const syncMode = document.getElementById('watchedSyncModeSelect');
            if (syncMode) syncMode.value = 'mirror';
            const makeM3u = document.getElementById('watchedMakeM3u');
            if (makeM3u) makeM3u.checked = true;
            addWatchedPlaylist();
        }

        // ---------------------------------------------------------------
        // Orphaned playlist tracks (mirror-mode leftovers)
        // ---------------------------------------------------------------
        async function findPlaylistOrphans() {
            const btn = document.getElementById('findOrphansBtn');
            const panel = document.getElementById('orphansResult');
            btn.disabled = true;
            btn.textContent = 'Scanning...';
            try {
                const response = await apiFetch('/api/watched-playlists/orphans');
                if (!response.ok) throw new Error('Scan failed');
                const data = await response.json();
                renderOrphans(data.orphans || []);
            } catch (e) {
                panel.style.display = 'block';
                panel.innerHTML = `<div class="form-error">Orphan scan failed: ${escapeHtml(e.message)}</div>`;
            } finally {
                btn.disabled = false;
                btn.textContent = 'Find Orphans';
            }
        }

        function renderOrphans(orphans) {
            const panel = document.getElementById('orphansResult');
            panel.style.display = 'block';
            if (!orphans.length) {
                panel.innerHTML = '<p class="watched-panel-text" style="margin-top:10px;">No orphans found. Every file in your playlist folders is claimed by a playlist, as it should be.</p>';
                return;
            }
            const rows = orphans.map(o => `
                <div class="orphan-row" data-file="${escapeAttr(o.file)}" style="display:flex; align-items:center; gap:10px; padding:6px 0; border-bottom:1px solid var(--border);">
                    <div style="flex:1; min-width:0;">
                        <div style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeAttr(o.file)}">${escapeHtml(o.name)}</div>
                        <div style="font-size:12px; color:var(--text-secondary);">${escapeHtml(o.playlist)}${o.size_mb ? ` &middot; ${o.size_mb} MB` : ''}</div>
                    </div>
                    <button class="btn" data-ui-click="moveOrphan">Move to Singles</button>
                </div>`).join('');
            panel.innerHTML = `
                <div style="display:flex; align-items:center; justify-content:space-between; margin:10px 0 4px;">
                    <strong>${orphans.length} orphaned track${orphans.length === 1 ? '' : 's'}</strong>
                    <button class="btn btn-primary" data-ui-click="moveAllOrphans">Move All to Singles</button>
                </div>
                ${rows}`;
        }

        async function moveOrphans(files) {
            if (!files.length) return;
            try {
                const response = await apiFetch('/api/watched-playlists/orphans/move', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ files })
                });
                if (!response.ok) throw new Error('Move failed');
                const data = await response.json();
                const bits = [];
                if (data.moved.length) bits.push(`${data.moved.length} moved`);
                if (data.skipped.length) bits.push(`${data.skipped.length} skipped`);
                if (data.errors.length) bits.push(`${data.errors.length} failed`);
                showToast(`Orphans: ${bits.join(', ') || 'nothing to do'}`);
                findPlaylistOrphans(); // rescan so the list reflects reality
            } catch (e) {
                showToast(`Orphan move failed: ${e.message}`);
            }
        }

        async function addListenBrainzPlaylists() {
            const username = document.getElementById('lbUsernameInput').value.trim();
            if (!username) {
                watchedError.textContent = 'Please enter a ListenBrainz username';
                watchedError.style.display = 'block';
                return;
            }

            watchedError.style.display = 'none';
            const btn = document.getElementById('addLbBtn');
            btn.disabled = true;
            btn.textContent = 'Add';

            const statusEl = document.getElementById('watchedAddStatus');
            const startedAt = new Date().toISOString();
            let timerInterval = null;

            function updateStatus(stage) {
                statusEl.innerHTML = `<span class="watched-card-refreshing"><span class="watched-refresh-spinner"></span>${escapeHtml(formatRefreshStage(stage, startedAt, 'listenbrainz'))}</span>`;
                statusEl.style.display = 'block';
            }

            updateStatus('fetching');
            timerInterval = setInterval(() => updateStatus('fetching'), 1000);

            try {
                const response = await apiFetch('/api/watched-playlists', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: username,
                        refresh_interval_hours: parseFloat(watchedIntervalSelect.value),
                        convert_audio: watchedConvertAudio ? watchedConvertAudio.checked : convertAudioCheckbox.checked,
                        make_m3u: document.getElementById('watchedMakeM3u') ? document.getElementById('watchedMakeM3u').checked : false,
                        use_playlists_dir: document.getElementById('watchedUsePlaylistsDir') ? document.getElementById('watchedUsePlaylistsDir').checked : false,
                        sync_mode: 'mirror',
                        custom_subdir: (document.getElementById('watchedCustomSubdir')?.value || '').trim() || null
                    })
                });

                if (!response.ok) {
                    const ct = response.headers.get('content-type') || '';
                    if (ct.includes('application/json')) {
                        const error = await response.json();
                        throw new Error(error.detail || 'Failed to add ListenBrainz playlists');
                    }
                    const text = (await response.text()).slice(0, 200);
                    throw new Error(`Server error ${response.status}: ${text || response.statusText}`);
                }

                const data = await response.json();
                showToast(`Added ${data.created} ListenBrainz playlist(s)` + (data.skipped ? ` (${data.skipped} already watched)` : ''));
                document.getElementById('lbUsernameInput').value = '';
                toggleLbRow();
                loadWatchedPlaylists();
            } catch (error) {
                watchedError.textContent = error.message;
                watchedError.style.display = 'block';
            } finally {
                clearInterval(timerInterval);
                statusEl.style.display = 'none';
                btn.disabled = false;
                btn.textContent = 'Add';
            }
        }

        async function refreshWatchedPlaylist(playlistId) {
            if (watchedRefreshPending.has(playlistId)) return;
            watchedRefreshPending.set(playlistId, { stage: 'starting', startedAt: new Date().toISOString() });
            loadWatchedPlaylists(false);
            try {
                showToast('Checking for new tracks...');
                const response = await apiFetch(`/api/watched-playlists/${playlistId}/refresh`, {
                    method: 'POST'
                });

                if (!response.ok) throw new Error('Refresh failed');

                const data = await response.json();
                if (data.already_running) {
                    showToast('Refresh already in progress');
                } else if (data.error) {
                    showToast(`Error: ${data.error}`, true);
                } else {
                    const newCount = data.new_tracks || 0;
                    const missingCount = data.missing_tracks || 0;
                    if (newCount > 0 || missingCount > 0) {
                        const parts = [];
                        if (newCount > 0) parts.push(`${newCount} new`);
                        if (missingCount > 0) parts.push(`${missingCount} missing`);
                        showToast(`Found ${parts.join(' + ')} tracks, queued ${data.queued} for download`);
                    } else {
                        showToast('No new tracks found');
                    }
                }
            } catch (error) {
                showToast('Failed to refresh playlist', true);
            } finally {
                watchedRefreshPending.delete(playlistId);
                loadWatchedPlaylists();
            }
        }

        async function copyWatchedPlaylistUrl(url) {
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    await navigator.clipboard.writeText(url);
                } else {
                    const tempInput = document.createElement('input');
                    tempInput.value = url;
                    document.body.appendChild(tempInput);
                    tempInput.select();
                    document.execCommand('copy');
                    document.body.removeChild(tempInput);
                }
                showToast('Playlist URL copied');
            } catch (error) {
                showToast('Failed to copy playlist URL', true);
            }
        }

        async function toggleWatchedPlaylist(playlistId, enabled) {
            const isEnabled = enabled === true || enabled === 'true';
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: isEnabled })
                });

                if (!response.ok) throw new Error('Update failed');

                loadWatchedPlaylists();
                showToast(isEnabled ? 'Playlist watching resumed' : 'Playlist watching paused');
            } catch (error) {
                showToast('Failed to update playlist', true);
            }
        }

        async function updateWatchedPlaylistConversion(playlistId, convertAudio) {
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ convert_audio: convertAudio })
                });

                if (!response.ok) throw new Error('Update failed');

                showToast(conversionChoiceLabel(convertAudio));
            } catch (error) {
                showToast('Failed to update format setting', true);
                loadWatchedPlaylists();
            }
        }

        async function updateWatchedPlaylistM3u(playlistId, makeM3u) {
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ make_m3u: makeM3u })
                });

                if (!response.ok) throw new Error('Update failed');

                showToast(makeM3u ? 'M3U generation enabled' : 'M3U generation disabled');
            } catch (error) {
                showToast('Failed to update M3U setting', true);
                loadWatchedPlaylists();
            }
        }

        async function updateWatchedPlaylistUsePlaylists(playlistId, usePlaylists) {
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ use_playlists_dir: usePlaylists })
                });

                if (!response.ok) throw new Error('Update failed');

                showToast(usePlaylists ? 'Downloads going to Playlists folder' : 'Downloads going to Singles folder');
            } catch (error) {
                showToast('Failed to update Playlists folder setting', true);
                loadWatchedPlaylists();
            }
        }

        async function updateWatchedPlaylistRedownloadMissing(playlistId, value) {
            const setting = value === 'inherit' ? null : value === 'true';
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ redownload_missing_files: setting })
                });
                if (!response.ok) throw new Error('Update failed');
                showToast(value === 'inherit'
                    ? 'Missing files now follow the global setting'
                    : setting ? 'Missing files will be re-downloaded' : 'Missing files will be left alone');
                loadWatchedPlaylists(false);
            } catch (error) {
                showToast('Failed to update missing-file setting', true);
                loadWatchedPlaylists();
            }
        }

        // Downloaded once, file since vanished; listed under Missing, where it can be relinked.
        const FILE_GONE_CHIP = '<span class="track-status-chip track-status-fail" title="Downloaded once, but the file can no longer be found. Relink or retry it from Missing.">not on disk</span>';

        async function toggleMissingTracks(playlistId) {
            const panel = document.getElementById(`missing-${playlistId}`);
            if (!panel) return;

            if (panel.style.display !== 'none') {
                panel.style.display = 'none';
                return;
            }

            panel.style.display = 'block';
            panel.textContent = 'Loading...';

            try {
                const resp = await apiFetch(`/api/watched-playlists/${playlistId}/missing`);
                if (!resp.ok) throw new Error('Failed to fetch');
                const data = await resp.json();

                if (!data.count) {
                    panel.textContent = 'No missing tracks - everything downloaded successfully.';
                    return;
                }

                const rows = data.missing.map((t, i) => {
                    const removed = t.removed_at ? ' <span style="color: var(--text-secondary); font-size: 10px;">(removed upstream)</span>' : '';
                    const trackId = `missing-track-${playlistId}-${i}`;
                    return `<div id="${trackId}" style="padding: 4px 0; display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
                        <span style="flex: 1; min-width: 0;">${escapeHtml(t.artist)} &ndash; ${escapeHtml(t.title)}${removed}</span>
                        <div style="display: flex; gap: 4px; align-items: center; flex-shrink: 0;">
                            <span style="font-size: 10px; color: var(--text-secondary); white-space: nowrap;"${t.file_missing_at ? ' title="Downloaded once, but the file can no longer be found"' : ''}>${t.file_missing_at ? 'not on disk' : (t.job_status || 'not attempted')}</span>
                            <button type="button"
                                data-action="retry-missing-track"
                                data-playlist-id="${escapeAttr(playlistId)}"
                                data-artist="${escapeAttr(t.artist)}"
                                data-title="${escapeAttr(t.title)}"
                                data-row-id="${escapeAttr(trackId)}"
                                style="padding: 3px 8px; font-size: 11px; font-family: inherit; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; white-space: nowrap;"
                                title="Auto-search and re-queue this track">Retry</button>
                            <button type="button"
                                data-action="search-missing-track"
                                data-playlist-id="${escapeAttr(playlistId)}"
                                data-playlist-name="${escapeAttr(data.playlist_name)}"
                                data-artist="${escapeAttr(t.artist)}"
                                data-title="${escapeAttr(t.title)}"
                                style="padding: 3px 8px; font-size: 11px; font-family: inherit; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; white-space: nowrap;"
                                title="Search manually and pick a result">Search</button>
                            <button type="button"
                                data-action="match-missing-track-library"
                                data-playlist-id="${escapeAttr(playlistId)}"
                                data-track-hash="${escapeAttr(t.track_hash)}"
                                data-artist="${escapeAttr(t.artist)}"
                                data-title="${escapeAttr(t.title)}"
                                data-row-id="${escapeAttr(trackId)}"
                                style="padding: 3px 8px; font-size: 11px; font-family: inherit; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); border-radius: 4px; cursor: pointer; white-space: nowrap;"
                                title="Already own it? Pick the file from your library">From Library</button>
                        </div>
                    </div>`;
                }).join('');

                panel.innerHTML = `<div style="font-weight: 600; margin-bottom: 6px;">${data.count} missing track${data.count !== 1 ? 's' : ''}:</div>${rows}`;
            } catch (e) {
                panel.textContent = 'Could not load missing tracks.';
            }
        }

        async function retryMissingTrack(playlistId, artist, title, rowId) {
            const row = document.getElementById(rowId);
            const retryBtn = row?.querySelector('button');
            if (retryBtn) { retryBtn.disabled = true; retryBtn.textContent = 'Searching...'; }

            try {
                const resp = await apiFetch(`/api/watched-playlists/${playlistId}/retry-track`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ artist, title })
                });
                if (!resp.ok) throw new Error('Failed');
                showToast(`Queued search for ${artist} - ${title}`);
                if (retryBtn) { retryBtn.textContent = 'Queued'; }
            } catch (e) {
                showToast('Failed to retry track', true);
                if (retryBtn) { retryBtn.disabled = false; retryBtn.textContent = 'Retry'; }
            }
        }

        document.getElementById('cancelAlbumRepairBtn')?.addEventListener('click', _resetDestination);

        async function startAlbumTrackRepair(selection, track, button) {
            if (track.exists && !confirm(`Move the current copy of "${track.title}" to Trash and search for a replacement? You can restore it through Queue if you change your mind.`)) return;
            button.disabled = true;
            button.textContent = 'Preparing…';
            try {
                const response = await apiFetch('/api/albums/repair-track', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ...selection, trash_existing: !!track.exists }),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || 'Could not prepare album repair');
                _resetDestination();
                _albumRepairSelection = data.selection;
                const context = data.context;
                document.getElementById('albumRepairLabel').textContent = `Repairing ${context.album_artist} / ${context.album_name}: disc ${context.disc_number}, track ${context.track_number}, ${context.track_title}`;
                document.getElementById('albumRepairBanner').style.display = 'block';
                track.exists = false;
                button.closest('li')?.classList.replace('album-track-existing', 'album-track-missing');
                setSearchValue(`${context.track_artist} - ${context.track_title}`);
                document.querySelector('.tab[data-tab="results"]')?.click();
                showToast(data.trashed ? 'Current copy moved to Trash. Choose the replacement below.' : 'Searching for this album track.');
                // An album rescue supersedes any Tracks search still in flight.
                ++currentSearchToken;
                searchBtn.disabled = false;
                search();
            } catch (error) {
                showToast(error.message || 'Could not prepare album repair', true);
            } finally {
                button.disabled = false;
                button.textContent = 'Search replacement';
            }
        }

        async function searchMissingTrack(playlistId, playlistName, artist, title) {
            _resetDestination();
            // Pre-fill the search input
            setSearchValue(`${artist} - ${title}`);

            // Open the destination picker in playlist mode and pre-select this playlist,
            // so the user can immediately download straight back into the right playlist.
            const sel = document.getElementById('playlistSelectorInput');
            const playlistPanel = document.getElementById('playlistSelector');
            const modePanel = document.getElementById('destinationModePanel');
            const pickerToggle = document.getElementById('destinationPickerToggle');
            if (sel && playlistName) {
                await loadPlaylists();
                let found = false;
                for (const opt of sel.options) {
                    if (opt.value === playlistName) {
                        sel.value = playlistName;
                        found = true;
                        break;
                    }
                }
                _destinationMode = 'playlist';
                if (modePanel) modePanel.style.display = 'none';
                if (playlistPanel) playlistPanel.style.display = 'flex';
                if (pickerToggle) {
                    pickerToggle.textContent = 'Adding to playlist';
                    pickerToggle.classList.add('active');
                }
                if (!found) sel.value = '';
                _updatePlaylistSelectorWarning();
            }

            // Switch to the Tracks tab (data-tab is still "results") and fire the search
            const resultsTabBtn = document.querySelector('.tab[data-tab="results"]');
            if (resultsTabBtn) resultsTabBtn.click();

            search();
        }

        async function toggleTrackList(playlistId, playlistName) {
            const panel = document.getElementById(`tracks-${playlistId}`);
            if (!panel) return;

            if (panel.style.display !== 'none') {
                panel.style.display = 'none';
                return;
            }

            panel.style.display = 'block';
            panel.textContent = 'Loading...';

            try {
                const resp = await apiFetch(`/api/watched-playlists/${playlistId}/tracks`);
                if (!resp.ok) throw new Error('Failed to fetch');
                const data = await resp.json();

                if (!data.total && !data.departed) {
                    panel.textContent = 'No tracks tracked yet.';
                    return;
                }

                const tracks = data.tracks;
                // Sections are mutually exclusive: a departed track belongs in its own
                // group whatever its download state, so the headings add up to the
                // summary line instead of counting the same track twice.
                const sections = {
                    downloaded: tracks.filter(t => t.downloaded_at && !t.removed_at),
                    failed: tracks.filter(t => !t.downloaded_at && ['failed', 'completed_with_errors', null].includes(t.job_status) && !t.removed_at),
                    pending: tracks.filter(t => !t.downloaded_at && ['queued', 'downloading', 'unsure'].includes(t.job_status) && !t.removed_at),
                    removed: tracks.filter(t => t.removed_at),
                };

                const departedSummary = data.departed
                    ? ` &middot; ${data.departed} ${data.sync_mode === 'mirror' ? 'no longer upstream' : 'kept from earlier'}`
                    : '';
                let html = `<div class="track-list-summary">${data.downloaded} downloaded &middot; ${data.failed} failed &middot; ${data.pending} pending${departedSummary}</div>`;

                function trackRow(t, i, actions) {
                    const rowId = `tl-track-${playlistId}-${i}`;
                    return `<div id="${rowId}" class="track-list-row">
                        <span class="track-list-label">${escapeHtml(t.artist)} &ndash; ${escapeHtml(t.title)}</span>
                        <div class="track-list-actions">${actions(t, rowId)}</div>
                    </div>`;
                }

                if (sections.downloaded.length) {
                    html += `<div class="track-list-section-header">Downloaded (${sections.downloaded.length})</div>`;
                    html += sections.downloaded.map((t, i) => trackRow(t, `d${i}`, (t, rowId) =>
                        `${t.file_missing_at ? FILE_GONE_CHIP : '<span class="track-status-chip track-status-ok">&#10003;</span>'}
                         ${t.job_id ? `<button ${uiAction('saveJobToDevice', [t.job_id])} title="Save this track to your device" class="track-action-btn">
                             <i class="fa-solid fa-download"></i></button>` : ''}
                         <button type="button"
                             data-action="replace-watched-track"
                             data-playlist-id="${escapeAttr(playlistId)}"
                             data-playlist-name="${escapeAttr(data.playlist_name)}"
                             data-artist="${escapeAttr(t.artist)}"
                             data-title="${escapeAttr(t.title)}"
                             data-track-hash="${escapeAttr(t.track_hash)}"
                             data-row-id="${escapeAttr(rowId)}"
                             class="track-replace-btn" title="Delete this file and search for the correct version">Replace</button>`
                    )).join('');
                }

                if (sections.failed.length) {
                    html += `<div class="track-list-section-header">Failed / Missing (${sections.failed.length})</div>`;
                    html += sections.failed.map((t, i) => trackRow(t, `f${i}`, (t, rowId) =>
                        `<span class="track-status-chip track-status-fail">&#10007;</span>
                         <button type="button"
                             data-action="retry-missing-track"
                             data-playlist-id="${escapeAttr(playlistId)}"
                             data-playlist-name="${escapeAttr(data.playlist_name)}"
                             data-artist="${escapeAttr(t.artist)}"
                             data-title="${escapeAttr(t.title)}"
                             data-row-id="${escapeAttr(rowId)}"
                             class="track-action-btn" title="Auto-search and re-queue">Retry</button>
                         <button type="button"
                             data-action="find-missing-track-versions"
                             data-playlist-id="${escapeAttr(playlistId)}"
                             data-playlist-name="${escapeAttr(data.playlist_name)}"
                             data-artist="${escapeAttr(t.artist)}"
                             data-title="${escapeAttr(t.title)}"
                             data-row-id="${escapeAttr(rowId)}"
                             class="track-action-btn" title="Preview and pick from the top alternatives">Find Versions</button>
                         <button type="button"
                             data-action="search-missing-track"
                             data-playlist-id="${escapeAttr(playlistId)}"
                             data-playlist-name="${escapeAttr(data.playlist_name)}"
                             data-artist="${escapeAttr(t.artist)}"
                             data-title="${escapeAttr(t.title)}"
                             class="track-action-btn" title="Search manually">Search</button>
                         <button type="button"
                             data-action="match-missing-track-library"
                             data-playlist-id="${escapeAttr(playlistId)}"
                             data-track-hash="${escapeAttr(t.track_hash)}"
                             data-artist="${escapeAttr(t.artist)}"
                             data-title="${escapeAttr(t.title)}"
                             data-row-id="${escapeAttr(rowId)}"
                             class="track-action-btn" title="Already own it? Pick the file from your library">From Library</button>`
                    )).join('');
                }

                if (sections.pending.length) {
                    html += `<div class="track-list-section-header">In Progress (${sections.pending.length})</div>`;
                    html += sections.pending.map((t, i) => trackRow(t, `p${i}`, () =>
                        `<span class="track-status-chip track-status-pending">&#8987;</span>`
                    )).join('');
                }

                if (sections.removed.length) {
                    const removedHeading = data.sync_mode === 'mirror'
                        ? `Removed Upstream (${sections.removed.length})`
                        : `No Longer Upstream, Kept (${sections.removed.length})`;
                    html += `<div class="track-list-section-header">${removedHeading}</div>`;
                    html += sections.removed.map((t, i) => trackRow(t, `r${i}`, (t) =>
                        t.file_missing_at && t.downloaded_at
                            ? FILE_GONE_CHIP
                            : `<span class="track-status-chip track-status-removed">${t.downloaded_at ? 'kept' : 'gone'}</span>`
                    )).join('');
                }

                panel.innerHTML = html;
            } catch (e) {
                panel.textContent = 'Could not load tracks.';
            }
        }

        async function replaceTrack(playlistId, playlistName, artist, title, trackHash, rowId) {
            const row = document.getElementById(rowId);
            const btn = row?.querySelector('.track-replace-btn');
            if (btn) { btn.disabled = true; btn.textContent = 'Trashing...'; }

            try {
                // Trash (or unlink from playlist) the bad file and clear downloaded_at
                const resp = await apiFetch(
                    `/api/watched-playlists/${encodeURIComponent(playlistId)}/tracks/${encodeURIComponent(trackHash)}/file`,
                    { method: 'DELETE' }
                );
                if (!resp.ok) {
                    // A generic "Failed to trash file" told nobody anything. Pass on
                    // whatever the backend actually said instead.
                    const body = await resp.json().catch(() => null);
                    throw new Error(body?.detail || `HTTP ${resp.status}`);
                }
                const data = await resp.json();

                // Nothing left on disk to bin is reported in message; say that rather
                // than claim a trashing that never happened.
                showToast(!data.trashed && data.message
                    ? data.message
                    : `Trashed ${artist} - ${title}. Pick the correct version below.`);

                // Update the row to show missing state with retry/search options
                if (row) {
                    const actionsEl = row.querySelector('.track-list-actions');
                    if (actionsEl) {
                        actionsEl.innerHTML = `<span class="track-status-chip track-status-fail">missing</span>
                            <button type="button"
                                data-action="retry-missing-track"
                                data-playlist-id="${escapeAttr(playlistId)}"
                                data-playlist-name="${escapeAttr(playlistName)}"
                                data-artist="${escapeAttr(artist)}"
                                data-title="${escapeAttr(title)}"
                                data-row-id="${escapeAttr(rowId)}"
                                class="track-action-btn">Retry</button>
                            <button type="button"
                                data-action="find-missing-track-versions"
                                data-playlist-id="${escapeAttr(playlistId)}"
                                data-playlist-name="${escapeAttr(playlistName)}"
                                data-artist="${escapeAttr(artist)}"
                                data-title="${escapeAttr(title)}"
                                data-row-id="${escapeAttr(rowId)}"
                                class="track-action-btn">Find Versions</button>
                            <button type="button"
                                data-action="search-missing-track"
                                data-playlist-id="${escapeAttr(playlistId)}"
                                data-playlist-name="${escapeAttr(playlistName)}"
                                data-artist="${escapeAttr(artist)}"
                                data-title="${escapeAttr(title)}"
                                class="track-action-btn">Search</button>
                            <button type="button"
                                data-action="match-missing-track-library"
                                data-playlist-id="${escapeAttr(playlistId)}"
                                data-track-hash="${escapeAttr(trackHash)}"
                                data-artist="${escapeAttr(artist)}"
                                data-title="${escapeAttr(title)}"
                                data-row-id="${escapeAttr(rowId)}"
                                class="track-action-btn">From Library</button>`;
                    }
                }

                // Route to search tab pre-filled with this track + playlist selected
                searchMissingTrack(playlistId, playlistName, artist, title);
            } catch (e) {
                showToast(`Failed to trash file: ${e.message || e}`, true);
                if (btn) { btn.disabled = false; btn.textContent = 'Replace'; }
            }
        }

        async function updateWatchedPlaylistSyncMode(playlistId, syncMode) {
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sync_mode: syncMode })
                });

                if (!response.ok) throw new Error('Update failed');

                showToast(syncMode === 'mirror' ? 'Sync mode: Mirror (M3U tracks upstream)' : 'Sync mode: Append (M3U grows over time)');
            } catch (error) {
                showToast('Failed to update sync mode', true);
                loadWatchedPlaylists();
            }
        }

        function clearWatchedCustomSubdir() {
            const input = document.getElementById('watchedCustomSubdir');
            const btn = document.getElementById('watchedClearDestBtn');
            const display = document.getElementById('watchedDestDisplay');
            if (input) input.value = '';
            if (btn) btn.style.display = 'none';
            if (display) display.textContent = '';
        }

        function updateWatchedDestDisplay() {
            const val = (document.getElementById('watchedCustomSubdir')?.value || '').trim();
            const display = document.getElementById('watchedDestDisplay');
            const clearBtn = document.getElementById('watchedClearDestBtn');
            const musicRoot = (serverConfig?.music_dir || '/music').replace(/\/+$/, '');
            if (display) display.textContent = val ? `${musicRoot}/${val}` : '';
            if (clearBtn) clearBtn.style.display = val ? 'inline-flex' : 'none';
        }

        async function updateWatchedPlaylistCustomSubdir(playlistId, value) {
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ custom_subdir: value || null })
                });
                if (!response.ok) throw new Error('Update failed');
                showToast(value ? `Destination: ${value}` : 'Destination reset to default');
                loadWatchedPlaylists();
            } catch (error) {
                showToast('Failed to update destination', true);
                loadWatchedPlaylists();
            }
        }

        // Source chips: render per-source toggle chips for a watched playlist card or the add form.
        // Switched-on sources that can fetch a single track. Albums-only ones
        // (Prowlarr) have no say in a playlist's tracks or a tie-break between them.
        function _trackSources() {
            return (_cachedSources || []).filter(s => s.enabled && !s.albums_only);
        }

        function renderSourceChips(playlistId, preferredSources) {
            // Only show globally-enabled track sources; repopulate once sources load if cache is empty
            const sources = _trackSources();
            const active = preferredSources === 'all' ? [] : preferredSources.split(',').map(s => s.trim());
            return sources.map(s => {
                const on = active.length === 0 || active.includes(s.id);
                return `<button type="button" class="source-chip ${on ? 'on' : 'off'}" data-source="${escapeAttr(s.id)}"
                    ${uiAction('toggleSourceChip', [playlistId])}
                    title="${escapeAttr(s.label)}">${escapeHtml(s.badge)}</button>`;
            }).join('');
        }

        async function populateSourceChips() {
            await _fetchSources();
            // Re-render any chips containers that used stale/empty data
            document.querySelectorAll('.watched-sources-chips[data-playlist-id]').forEach(el => {
                const pid = el.dataset.playlistId;
                // Use the authoritative preferred_sources from the API, not the DOM chip state
                const pref = el.dataset.preferred || 'all';
                el.innerHTML = renderSourceChips(pid, pref);
            });
            // Same dance for per-playlist priority-source dropdowns: they may have
            // been rendered before _cachedSources populated, so the only option was
            // "No preference". Re-fill them now using the stored value as the default.
            document.querySelectorAll('select[data-priority-source]').forEach(sel => {
                const current = sel.dataset.prioritySource || '';
                sel.innerHTML = renderPrioritySourceOptions(current);
            });
            // Populate the add-form selector (only globally-enabled sources, all on by default)
            const formSel = document.getElementById('watchedSourcesSelector');
            if (formSel && formSel.children.length === 0) {
                const sources = _trackSources();
                formSel.innerHTML = sources.map(s =>
                    `<button type="button" class="source-chip on" data-source="${escapeAttr(s.id)}"
                        data-ui-click="toggleSourceClasses"
                        title="${escapeAttr(s.label)}">${escapeHtml(s.badge)}</button>`
                ).join('');
            }
            // Populate priority-source dropdowns (one in bulk import, one in watched add form)
            populatePrioritySourceDropdowns();
        }

        function populatePrioritySourceDropdowns() {
            const sources = _trackSources();
            const targets = ['bulkPrioritySource', 'watchedPrioritySource'];
            for (const id of targets) {
                const sel = document.getElementById(id);
                if (!sel || sel.options.length > 1) continue;  // already populated
                for (const s of sources) {
                    const opt = document.createElement('option');
                    opt.value = s.id;
                    opt.textContent = s.label;
                    sel.appendChild(opt);
                }
            }
        }

        function toggleSourceChip(btn, playlistId) {
            btn.classList.toggle('on');
            btn.classList.toggle('off');
            // Collect current state for this playlist
            const container = btn.closest('.watched-sources-chips');
            const chips = [...container.querySelectorAll('.source-chip')];
            const on = chips.filter(c => c.classList.contains('on')).map(c => c.dataset.source);
            // "all on" = send "all"; partial = comma list; none = "all" (fallback, don't allow locking out)
            const preferred = (on.length === 0 || on.length === chips.length) ? 'all' : on.join(',');
            container.dataset.preferred = preferred;
            updateWatchedPlaylistPreferredSources(playlistId, preferred);
        }

        function getWatchedPreferredSources() {
            const chips = [...document.querySelectorAll('#watchedSourcesSelector .source-chip')];
            if (chips.length === 0) return 'all';
            const on = chips.filter(c => c.classList.contains('on')).map(c => c.dataset.source);
            return (on.length === 0 || on.length === chips.length) ? 'all' : on.join(',');
        }

        function setWatchedPreferredSource(sourceId) {
            // Flip the add-form source chips to a single source, leaving others off
            const chips = [...document.querySelectorAll('#watchedSourcesSelector .source-chip')];
            chips.forEach(c => {
                const match = c.dataset.source === sourceId;
                c.classList.toggle('on', match);
                c.classList.toggle('off', !match);
            });
        }

        async function updateWatchedPlaylistPreferredSources(playlistId, preferred) {
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ preferred_sources: preferred })
                });
                if (!response.ok) throw new Error('Update failed');
                const label = preferred === 'all' ? 'all sources' : preferred;
                showToast(`Sources: ${label}`);
            } catch (error) {
                showToast('Failed to update sources', true);
                loadWatchedPlaylists();
            }
        }

        function renderPrioritySourceOptions(current) {
            const sources = _trackSources();
            const cur = (current || '').toLowerCase();
            const opts = [`<option value="" ${cur ? '' : 'selected'}>No preference</option>`];
            for (const s of sources) {
                const sel = cur === s.id ? 'selected' : '';
                opts.push(`<option value="${escapeAttr(s.id)}" ${sel}>${escapeHtml(s.label)}</option>`);
            }
            return opts.join('');
        }

        async function updateWatchedPlaylistPrioritySource(playlistId, priority) {
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ priority_source: priority || '' })
                });
                if (!response.ok) throw new Error('Update failed');
                showToast(priority ? `Preferred source: ${priority}` : 'Preferred source cleared');
            } catch (error) {
                showToast('Failed to update preferred source', true);
                loadWatchedPlaylists();
            }
        }

        // A name of your own (GitLab #110): the card and the M3U take it, the folder
        // keeps the source's. Empty goes back to the original.
        async function renameWatchedPlaylist(playlistId, sourceName, customName) {
            const current = customName || sourceName;
            const answer = prompt(`Name this playlist (leave it empty to go back to "${sourceName}"):`, current);
            if (answer === null || answer.trim() === current) return;
            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ custom_name: answer.trim() })
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(typeof data.detail === 'string' ? data.detail
                        : response.status === 422 ? 'That name is too long; 200 characters at most' : 'Rename failed');
                }
                const p = data.playlist || {};
                showToast(p.custom_name ? `Renamed to "${p.custom_name}"` : `Back to "${p.name || sourceName}"`);
                loadWatchedPlaylists(false);
                if (typeof loadPlaylists === 'function') loadPlaylists();
            } catch (error) {
                showToast(error.message || 'Failed to rename playlist', true);
            }
        }

        async function deleteWatchedPlaylist(playlistId, name) {
            if (!confirm(`Stop watching "${name}"? This won't delete any downloaded files.`)) {
                return;
            }

            try {
                const response = await apiFetch(`/api/watched-playlists/${playlistId}`, {
                    method: 'DELETE'
                });

                if (!response.ok) throw new Error('Delete failed');

                showToast(`Stopped watching "${name}"`);
                loadWatchedPlaylists();
            } catch (error) {
                showToast('Failed to delete playlist', true);
            }
        }

        async function refreshAllWatched() {
            refreshAllWatchedBtn.disabled = true;
            refreshAllWatchedBtn.textContent = 'Checking...';

            try {
                const response = await apiFetch('/api/watched-playlists/check-all', {
                    method: 'POST'
                });

                if (!response.ok) throw new Error('Check failed');

                const data = await response.json();
                if (data.checked === 0) {
                    showToast('No playlists due for refresh');
                } else if (data.total_new_tracks > 0) {
                    showToast(`Checked ${data.checked} playlists: ${data.total_new_tracks} new tracks, ${data.total_queued} queued`);
                } else {
                    showToast(`Checked ${data.checked} playlists: no new tracks`);
                }
                loadWatchedPlaylists();
            } catch (error) {
                showToast('Failed to check playlists', true);
            } finally {
                refreshAllWatchedBtn.disabled = false;
                refreshAllWatchedBtn.textContent = 'Check All Now';
            }
        }

        // Event listeners for watched playlists
        addWatchedBtn.addEventListener('click', addWatchedPlaylist);
        watchedUrlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') addWatchedPlaylist();
        });
        document.getElementById('lbUsernameInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') addListenBrainzPlaylists();
        });
        refreshAllWatchedBtn.addEventListener('click', refreshAllWatched);

        // Watched Upgrades controls (pager + rescan)
        (function wireUpgradeControls() {
            const prev = document.getElementById('upgradesPrevBtn');
            const next = document.getElementById('upgradesNextBtn');
            const rescan = document.getElementById('rescanUpgradesBtn');
            if (prev) prev.addEventListener('click', () => { if (upgradesPage > 1) { upgradesPage--; loadWatchedUpgrades(); } });
            if (next) next.addEventListener('click', () => { upgradesPage++; loadWatchedUpgrades(); });
            if (rescan) rescan.addEventListener('click', async () => {
                rescan.disabled = true;
                const original = rescan.textContent;
                rescan.textContent = 'Scanning...';
                try {
                    const resp = await apiFetch('/api/upgrades/rescan', { method: 'POST' });
                    if (resp.ok) {
                        const data = await resp.json();
                        const t = data.totals || {};
                        showToast(`Scan done: ${t.below_target || 0} below target across ${t.eligible || 0} files`);
                        upgradesPage = 1;
                        loadWatchedUpgrades();
                    } else if (resp.status === 400) {
                        showToast('Enable Track Upgrades in Settings first', true);
                    } else if (resp.status === 403) {
                        showToast('Admin only', true);
                    }
                } catch (e) {
                    showToast('Scan failed', true);
                } finally {
                    rescan.disabled = false;
                    rescan.textContent = original;
                }
            });
        })();

        // Quarantine panel: files a Track Upgrade swap displaced. Collapsed by
        // default; loaded on every open so it never shows stale state.
        (function wireQuarantineControls() {
            const toggle = document.getElementById('quarantineToggleBtn');
            const panel = document.getElementById('quarantinePanel');
            if (!toggle || !panel) return;
            toggle.addEventListener('click', () => {
                const opening = panel.style.display === 'none';
                panel.style.display = opening ? '' : 'none';
                if (opening) loadQuarantine();
            });
        })();

        // =====================================================================
        // Watched Upgrades (track-upgrades Phase 2a: search + display, no swap yet)
        // =====================================================================
        const UPGRADES_PER_PAGE = 10;
        let upgradesPage = 1;
        let upgradesSearchToken = 0;  // bumped to abort an in-flight lazy-search sweep

        function upgradeTierLabel(tier) {
            return { 5: 'Lossless', 4: '320', 3: '256', 2: '192', 1: '128' }[tier] || '?';
        }

        function upgradeCurrentQuality(item) {
            const codec = (item.codec || '?').toUpperCase();
            const storedRate = item.bitrate_kbps ? `${item.bitrate_kbps}kbps` : '';
            const stored = [codec, storedRate].filter(Boolean).join(' ');
            const sourceCodec = (item.source_codec || '').toUpperCase();
            const sourceRate = item.source_bitrate_kbps ? `${item.source_bitrate_kbps}kbps` : '';

            if (item.file_tier === 5) {
                return `${stored} stored · lossless source`;
            }

            // A lossless container can preserve a lossy input perfectly, but it cannot
            // restore quality the input had already discarded. Show both sides so a
            // FLAC-from-MP3 candidate does not look like FLAC is being compared by bitrate.
            if (sourceCodec && sourceCodec !== codec) {
                const source = [sourceCodec, sourceRate].filter(Boolean).join(' ');
                return `${stored} stored · source ${source} · effective ${upgradeTierLabel(item.file_tier)} tier`;
            }

            const legacyOrigin = (item.source_quality || '').match(/\bfrom\s+([^)]*)/i);
            if (legacyOrigin) {
                return `${stored} stored · source ${legacyOrigin[1].trim()} · effective ${upgradeTierLabel(item.file_tier)} tier`;
            }

            return `${stored} · effective ${upgradeTierLabel(item.file_tier)} tier`;
        }

        async function loadWatchedUpgrades() {
            const list = document.getElementById('watchedUpgradesList');
            const pager = document.getElementById('upgradesPager');
            const disabledNote = document.getElementById('upgradesDisabledNote');
            if (!list) return;
            upgradesSearchToken++;  // abort any previous sweep
            try {
                const resp = await apiFetch(`/api/upgrades/candidates?page=${upgradesPage}&per_page=${UPGRADES_PER_PAGE}`);
                if (!resp.ok) { list.innerHTML = ''; return; }
                const data = await resp.json();
                if (data.enabled === false) {
                    if (disabledNote) disabledNote.style.display = '';
                    list.innerHTML = '';
                    if (pager) pager.style.display = 'none';
                    return;
                }
                if (disabledNote) disabledNote.style.display = 'none';

                if (!data.items.length) {
                    list.innerHTML = '<p class="watched-empty-text">No upgrade candidates. Either everything is already at target quality, or the library has not been scanned yet (try Rescan Library).</p>';
                    if (pager) pager.style.display = 'none';
                    return;
                }

                list.innerHTML = data.items.map(renderUpgradeRow).join('');
                data.items.forEach(item => {
                    if (item.found_searched) {
                        renderProposedUpgrade(item);
                    }
                });

                // Pager
                if (pager) {
                    const info = document.getElementById('upgradesPageInfo');
                    if (info) info.textContent = `Page ${data.page} of ${data.pages} (${data.total} below target)`;
                    document.getElementById('upgradesPrevBtn').disabled = data.page <= 1;
                    document.getElementById('upgradesNextBtn').disabled = data.page >= data.pages;
                    pager.style.display = data.pages > 1 ? '' : 'none';
                }

                // Lazily search the rows that have no fresh cached result, ~1/s, this page only.
                lazySearchUpgrades(data.items, ++upgradesSearchToken);
            } catch (e) {
                list.innerHTML = '';
            }
        }

        function renderUpgradeRow(item) {
            const title = escapeHtml(item.title || item.filename || '');
            const artist = escapeHtml(item.artist || '');
            const current = escapeHtml(upgradeCurrentQuality(item));
            return `
                <div class="result-item upgrade-row" id="upgrade-row-${item.id}" data-id="${item.id}">
                    <div class="upgrade-current">
                        <div class="upgrade-track"><strong>${artist}</strong>${artist ? ' &ndash; ' : ''}${title}</div>
                        <div class="upgrade-meta">Current: <span class="upgrade-quality-now">${current}</span></div>
                    </div>
                    <div class="upgrade-proposed" id="upgrade-proposed-${item.id}">
                        <span class="upgrade-searching">Checking for a better copy&hellip;</span>
                    </div>
                    <div class="upgrade-actions">
                        <button class="btn btn-ghost btn-sm" ${uiAction('dismissUpgrade', [item.id])} title="Stop suggesting this one">Dismiss</button>
                    </div>
                </div>`;
        }

        function renderProposedUpgrade(item) {
            const cell = document.getElementById(`upgrade-proposed-${item.id}`);
            if (!cell) return;
            // Stash the source_url on the row so the preview handler can reach it
            // (url-based sources need it; it isn't safe to inline into an attribute).
            const rowEl = document.getElementById(`upgrade-row-${item.id}`);
            if (rowEl) rowEl._foundSourceUrl = item.found_source_url || null;
            if (!item.found_source) {
                cell.innerHTML = '<span class="upgrade-none">No better copy found</span>';
                // Nothing to offer; the server won't list it again once this search is
                // cached, so drop the row now instead of leaving a permanent dead end.
                setTimeout(() => {
                    if (rowEl) rowEl.remove();
                    if (!document.querySelectorAll('#watchedUpgradesList .upgrade-row').length) loadWatchedUpgrades();
                }, 1500);
                return;
            }
            const badge = getSourceBadge(item.found_source);
            const tier = upgradeTierLabel(item.found_tier);
            const qual = escapeHtml(item.found_quality || tier);
            const output = escapeHtml(item.upgrade_output_label || 'Keep source format');
            const sourceDescription = `${qual} source`;
            const outputDescription = item.upgrade_conversion_enabled
                ? `${output} output`
                : 'kept in source format';
            const outputTitle = item.upgrade_conversion_enabled
                ? `MusicGrabber will convert this candidate and store ${output}. The source-quality label describes the download before conversion.`
                : 'Conversion is off, so MusicGrabber will keep the downloaded source format.';
            const conf = item.found_confidence != null ? Math.round(item.found_confidence * 100) + '%' : '';
            const verifiedBadge = item.found_verified
                ? '<span class="upgrade-verified" title="Quality confirmed by the source">verified</span>'
                : '<span class="upgrade-unverified" title="Estimated; confirmed only after download">needs download to confirm</span>';
            const canPreview = item.found_video_id && sourceHasPreview(item.found_source);
            const previewBtn = canPreview
                ? `<button class="btn btn-ghost btn-sm upgrade-preview"
                        ${uiAction('previewUpgrade', [item.found_video_id, item.found_source, item.id], 'mouseenter')}
                        data-ui-mouseleave="stopPreview"
                        ${uiAction('previewUpgrade', [item.found_video_id, item.found_source, item.id])}>&#9654; Preview</button>`
                : '';
            cell.innerHTML = `
                <span class="upgrade-arrow">&rarr;</span>
                <span class="source-badge ${item.found_source}">${badge}</span>
                <span class="upgrade-quality-new">${sourceDescription}</span>
                <span class="upgrade-conversion-arrow" aria-hidden="true">&rarr;</span>
                <span class="upgrade-output-label" title="${escapeAttr(outputTitle)}">${outputDescription}</span>
                ${conf ? `<span class="upgrade-conf" title="Match confidence">${conf}</span>` : ''}
                ${verifiedBadge}
                ${previewBtn}
                <button class="btn btn-primary btn-sm upgrade-go" ${uiAction('upgradeOne', [item.id])} title="Download, verify, and swap in this copy">Upgrade</button>`;
        }

        // Walk the visible rows one at a time (~1/s) searching for a better copy.
        // Aborts cleanly if the token changes (user paginated away or left the tab).
        async function lazySearchUpgrades(items, token) {
            for (const item of items) {
                if (token !== upgradesSearchToken) return;
                if (item.found_searched) continue;  // already have a cached result rendered
                try {
                    const resp = await apiFetch(`/api/upgrades/candidates/${item.id}/search`, { method: 'POST' });
                    if (token !== upgradesSearchToken) return;
                    if (resp.ok) {
                        const updated = await resp.json();
                        renderProposedUpgrade(updated);
                    }
                } catch (e) { /* leave the row as-is */ }
                await new Promise(r => setTimeout(r, 1000));  // rate limit, be kind to sources
            }
        }

        function previewUpgrade(videoId, source, element, id) {
            // Reuse the search-result preview machinery with a synthetic result object.
            const row = document.getElementById(`upgrade-row-${id}`);
            let sourceUrl = null;
            // source_url isn't in the DOM; the preview endpoint needs it for url-based sources.
            // For those, fall back to the cached candidate data attached to the row.
            if (row && row._foundSourceUrl) sourceUrl = row._foundSourceUrl;
            startPreview(videoId, element, { source, source_url: sourceUrl });
        }

        async function upgradeOne(id, btn, force = false) {
            const row = document.getElementById(`upgrade-row-${id}`);
            const cell = document.getElementById(`upgrade-proposed-${id}`);
            if (btn) { btn.disabled = true; btn.textContent = force ? 'Forcing...' : 'Upgrading...'; }
            stopPreview();
            try {
                const url = `/api/upgrades/candidates/${id}/upgrade${force ? '?force=true' : ''}`;
                const resp = await apiFetch(url, { method: 'POST' });
                const data = await resp.json().catch(() => ({}));
                if (resp.ok && data.status === 'upgraded') {
                    // A successful upgrade can still sit below your target tier (the
                    // fetched copy was better, then convert-audio re-encoded it back
                    // down). The backend keeps such a row on the list, so removing it
                    // here would just make it "reappear" on the next load, looking
                    // like the upgrade silently failed when it did no such thing.
                    const stillBelow = data.still_below_target;
                    if (row) {
                        const c = row.querySelector('.upgrade-current .upgrade-meta');
                        if (c) {
                            c.innerHTML = stillBelow
                                ? `<span class="upgrade-verified">Upgraded</span> to ${escapeHtml(data.new_quality || '')}, still below your target &middot; old file in quarantine`
                                : '<span class="upgrade-verified">Upgraded</span> old file moved to quarantine';
                        }
                        if (!stillBelow) {
                            row.style.transition = 'opacity 0.4s';
                            row.style.opacity = '0.5';
                        }
                    }
                    if (cell) {
                        cell.innerHTML = stillBelow
                            ? '<span class="upgrade-none">Still below target; search again for a better copy</span>'
                            : '<span class="upgrade-verified">Done</span>';
                    }
                    if (stillBelow) {
                        showToast('Upgraded, but the result is still below your target quality');
                    } else {
                        showToast(force ? 'Force-upgraded; old file is in quarantine' : 'Upgraded; old file is in quarantine');
                        setTimeout(() => { if (row) row.remove(); if (!document.querySelectorAll('#watchedUpgradesList .upgrade-row').length) loadWatchedUpgrades(); }, 1200);
                    }
                } else if (data.status === 'rejected') {
                    // Offer a force override; the old file still goes to quarantine, so it's recoverable.
                    if (cell) cell.innerHTML = `<span class="upgrade-none">Rejected: ${escapeHtml(data.reason || 'failed checks')}</span>
                        <button class="btn btn-ghost btn-sm upgrade-force" ${uiAction('forceUpgrade', [id])} title="Swap it in anyway. The old file still goes to quarantine, so you can undo it.">Force anyway</button>`;
                    showToast('Upgrade rejected: ' + (data.reason || 'failed checks'), true);
                } else {
                    showToast('Upgrade failed: ' + (data.reason || resp.status), true);
                    if (btn) { btn.disabled = false; btn.textContent = force ? 'Force anyway' : 'Upgrade'; }
                }
            } catch (e) {
                showToast('Upgrade failed', true);
                if (btn) { btn.disabled = false; btn.textContent = force ? 'Force anyway' : 'Upgrade'; }
            }
        }

        function forceUpgrade(id, btn) {
            if (!confirm('Force this upgrade? The proposed copy failed a same-recording check (e.g. different length), so it may be a different version. The old file goes to quarantine and can be restored.')) return;
            upgradeOne(id, btn, true);
        }

        async function upgradeAll() {
            if (!confirm('Download and swap in every proposed upgrade on this page set? Old files are moved to quarantine (recoverable), not deleted.')) return;
            const btn = document.getElementById('upgradeAllBtn');
            try {
                const resp = await apiFetch('/api/upgrades/upgrade-all', { method: 'POST' });
                if (resp.ok) {
                    showToast('Upgrading all in the background; this can take a while.');
                    pollUpgradeAll(btn);
                } else if (resp.status === 400) {
                    showToast('Enable Track Upgrades in Settings first', true);
                }
            } catch (e) { showToast('Could not start upgrade-all', true); }
        }

        // Watch the background run to completion and reload the list ourselves.
        // The old behaviour was a toast saying "Refresh to see progress", which is
        // easy to miss and left a finished run looking like a stuck one.
        async function pollUpgradeAll(btn) {
            if (btn) btn.disabled = true;
            const originalLabel = btn ? btn.textContent : '';
            const restore = () => { if (btn) { btn.disabled = false; btn.textContent = originalLabel; } };
            let misses = 0;
            while (true) {
                await new Promise(r => setTimeout(r, 3000));
                let data;
                try {
                    const resp = await apiFetch('/api/upgrades/upgrade-all/status');
                    if (!resp.ok) { restore(); return; }
                    data = await resp.json();
                } catch (e) {
                    // A blip shouldn't abandon a run that's still going; several in a
                    // row probably means we're not getting it back.
                    if (++misses >= 3) { restore(); return; }
                    continue;
                }
                misses = 0;
                if (btn && data.total) btn.textContent = `Upgrading ${data.done}/${data.total}...`;
                if (!data.running) {
                    restore();
                    showToast(`Upgrade All finished: ${data.upgraded || 0} upgraded, ${data.rejected || 0} rejected, ${data.errored || 0} errored`);
                    upgradesPage = 1;
                    loadWatchedUpgrades();
                    return;
                }
            }
        }

        async function dismissUpgrade(id) {
            try {
                const resp = await apiFetch(`/api/upgrades/candidates/${id}/dismiss`, { method: 'POST' });
                if (resp.ok) {
                    const row = document.getElementById(`upgrade-row-${id}`);
                    if (row) row.remove();
                    if (!document.querySelectorAll('#watchedUpgradesList .upgrade-row').length) {
                        loadWatchedUpgrades();
                    }
                }
            } catch (e) { showToast('Could not dismiss', true); }
        }

        async function loadQuarantine() {
            const list = document.getElementById('quarantineList');
            if (!list) return;
            list.innerHTML = '<p class="watched-empty-text">Loading&hellip;</p>';
            try {
                const resp = await apiFetch('/api/upgrades/quarantine');
                if (!resp.ok) { list.innerHTML = '<p class="watched-empty-text">Could not load quarantine.</p>'; return; }
                const data = await resp.json();
                if (!data.items.length) {
                    list.innerHTML = '<p class="watched-empty-text">Nothing in quarantine.</p>';
                    return;
                }
                list.innerHTML = data.items.map(renderQuarantineRow).join('');
            } catch (e) {
                list.innerHTML = '<p class="watched-empty-text">Could not load quarantine.</p>';
            }
        }

        function renderQuarantineRow(item) {
            const filename = item.quarantine_path.split('/').pop();
            const title = escapeHtml(item.title || filename);
            const artist = escapeHtml(item.artist || '');
            const size = item.file_size ? formatBytes(item.file_size) : '';
            const when = formatDateYmd(item.quarantined_at);
            const restoreBtn = item.restorable
                ? `<button class="btn btn-primary btn-sm" ${uiAction('restoreQuarantineEntry', [item.id])} title="Put this file back where it lived; whatever replaced it is quarantined in turn">Restore</button>`
                : `<span class="upgrade-none" title="No original library location was recorded for this file">no restore info</span>`;
            // Orphaned entries (no numeric id) carry their filename via a data
            // attribute rather than an inline-JS string argument: filenames routinely
            // contain apostrophes (e.g. "Breakin' Outta Hell"), which would otherwise
            // break out of the quoted data attribute.
            const deleteBtn = item.id != null
                ? `<button class="btn btn-danger btn-sm" ${uiAction('deleteQuarantineEntry', [item.id])} title="Delete this file for good">Delete</button>`
                : `<button class="btn btn-danger btn-sm" data-filename="${escapeAttr(filename)}" data-ui-click="deleteOrphanedQuarantineFile" title="Delete this file for good">Delete</button>`;
            return `
                <div class="result-item upgrade-row">
                    <div class="upgrade-current">
                        <div class="upgrade-track"><strong>${artist}</strong>${artist ? ' &ndash; ' : ''}${title}</div>
                        <div class="upgrade-meta">Quarantined ${when}${size ? ' · ' + size : ''}</div>
                    </div>
                    <div class="upgrade-actions">
                        ${restoreBtn}
                        ${deleteBtn}
                    </div>
                </div>`;
        }

        async function restoreQuarantineEntry(id, btn) {
            if (!confirm('Restore this file? Whatever replaced it will be quarantined in turn, so this can be undone too.')) return;
            if (btn) btn.disabled = true;
            try {
                const resp = await apiFetch(`/api/upgrades/quarantine/${id}/restore`, { method: 'POST' });
                const data = await resp.json().catch(() => ({}));
                if (resp.ok && data.status === 'restored') {
                    showToast('Restored');
                    loadQuarantine();
                    if (!document.querySelectorAll('#watchedUpgradesList .upgrade-row').length) loadWatchedUpgrades();
                } else {
                    showToast('Restore failed: ' + (data.reason || resp.status), true);
                    if (btn) btn.disabled = false;
                }
            } catch (e) {
                showToast('Restore failed', true);
                if (btn) btn.disabled = false;
            }
        }

        async function deleteQuarantineEntry(id, btn) {
            if (!confirm('Delete this file for good? There is no undo.')) return;
            if (btn) btn.disabled = true;
            try {
                const resp = await apiFetch(`/api/upgrades/quarantine/${id}`, { method: 'DELETE' });
                if (resp.ok) {
                    showToast('Deleted');
                    loadQuarantine();
                } else {
                    const data = await resp.json().catch(() => ({}));
                    showToast('Delete failed: ' + (data.detail || resp.status), true);
                    if (btn) btn.disabled = false;
                }
            } catch (e) {
                showToast('Delete failed', true);
                if (btn) btn.disabled = false;
            }
        }

        async function deleteOrphanedQuarantineFile(btn) {
            if (!confirm('Delete this file for good? There is no undo, and its original library location is not known.')) return;
            const filename = btn.dataset.filename;
            btn.disabled = true;
            try {
                const resp = await apiFetch(`/api/upgrades/quarantine/orphaned?filename=${encodeURIComponent(filename)}`, { method: 'DELETE' });
                if (resp.ok) {
                    showToast('Deleted');
                    loadQuarantine();
                } else {
                    const data = await resp.json().catch(() => ({}));
                    showToast('Delete failed: ' + (data.detail || resp.status), true);
                    if (btn) btn.disabled = false;
                }
            } catch (e) {
                showToast('Delete failed', true);
                if (btn) btn.disabled = false;
            }
        }

        // =====================================================================
        // Read-only Audio Provenance Audit
        // =====================================================================
        const AUDIO_AUDIT_PER_PAGE = 25;
        const AUDIO_AUDIT_CLASSIFICATIONS = {
            known_lossy_transcode: 'Known lossy transcode',
            native_lossy: 'Native lossy acquisition',
            lossy_derivative: 'Lossy derivative of recorded lossless',
            recorded_lossless: 'Recorded lossless acquisition',
            historical_unknown: 'Historical or unknown provenance',
            unreadable: 'Unreadable audio file',
        };
        const AUDIO_AUDIT_QUALITY_LABELS = {
            recorded_lossless: 'Recorded lossless',
            lossy_320: 'Lossy, up to 320 tier',
            lossy_256: 'Lossy, up to 256 tier',
            lossy_192: 'Lossy, up to 192 tier',
            lossy_128: 'Lossy, up to 128 tier',
            lossy_unknown: 'Lossy, bitrate unknown',
            unknown: 'Unknown',
        };
        let audioAuditPage = 1;
        let audioAuditPollTimer = null;
        let audioAuditLastStatus = null;

        function audioAuditFilters() {
            return {
                classification: document.getElementById('audioAuditClassification')?.value || '',
                container: document.getElementById('audioAuditContainer')?.value || '',
                codec: document.getElementById('audioAuditCodec')?.value || '',
                source: document.getElementById('audioAuditSource')?.value || '',
                effective_quality: document.getElementById('audioAuditEffective')?.value || '',
                lossless_only: document.getElementById('audioAuditLossless')?.value || '',
            };
        }

        function audioAuditQuery(includeFormat = null) {
            const params = new URLSearchParams();
            Object.entries(audioAuditFilters()).forEach(([key, value]) => {
                if (value) params.set(key, value);
            });
            if (includeFormat) params.set('format', includeFormat);
            return params.toString();
        }

        function fillAudioAuditSelect(id, values, labelForValue = value => value) {
            const select = document.getElementById(id);
            if (!select) return;
            const selected = select.value;
            const first = select.options[0];
            const placeholder = first ? first.textContent : 'All';
            select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` +
                (values || []).map(value =>
                    `<option value="${escapeHtml(String(value))}">${escapeHtml(String(labelForValue(value)))}</option>`
                ).join('');
            if ([...select.options].some(option => option.value === selected)) {
                select.value = selected;
            }
        }

        function populateAudioAuditFilters(status) {
            fillAudioAuditSelect(
                'audioAuditClassification',
                Object.keys(AUDIO_AUDIT_CLASSIFICATIONS),
                value => AUDIO_AUDIT_CLASSIFICATIONS[value]
            );
            const options = status.options || {};
            fillAudioAuditSelect('audioAuditContainer', options.container || [], value => String(value).toUpperCase());
            fillAudioAuditSelect('audioAuditCodec', options.codec || [], value => String(value).toUpperCase());
            fillAudioAuditSelect('audioAuditSource', options.source || []);
            fillAudioAuditSelect(
                'audioAuditEffective',
                options.effective_quality || [],
                value => AUDIO_AUDIT_QUALITY_LABELS[value] || value
            );
        }

        function renderAudioAuditSummary(summary) {
            const element = document.getElementById('audioAuditSummary');
            if (!element) return;
            if (!summary) {
                element.innerHTML = '';
                return;
            }
            const counts = summary.counts || {};
            const ordered = [
                'known_lossy_transcode',
                'native_lossy',
                'lossy_derivative',
                'recorded_lossless',
                'historical_unknown',
                'unreadable',
            ];
            element.innerHTML = ordered.map(key => `
                <div class="audio-audit-summary-card audit-${key}">
                    <span class="audio-audit-summary-count">${Number(counts[key] || 0).toLocaleString()}</span>
                    <span>${escapeHtml(AUDIO_AUDIT_CLASSIFICATIONS[key])}</span>
                </div>
            `).join('');
        }

        function renderAudioAuditStatus(status) {
            const element = document.getElementById('audioAuditStatus');
            const runButton = document.getElementById('runAudioAuditBtn');
            if (!element) return;
            const running = status.running;
            const current = status.current;
            if (runButton) {
                runButton.disabled = !!running;
                runButton.textContent = running ? 'Auditing...' : 'Run Audit';
            }
            if (running) {
                const scanned = Number(running.scanned_files || 0).toLocaleString();
                const total = Number(running.total_files || 0).toLocaleString();
                if (!running.total_files) {
                    element.innerHTML = '<strong>Discovering:</strong> walking the configured music directory for supported audio files. Nothing is being changed.';
                    return;
                }
                const progress = running.total_files ? ` (${running.progress_percent || 0}%)` : '';
                const oldReport = current ? ' The previous complete report remains below until this finishes.' : '';
                element.innerHTML = `<strong>Scanning:</strong> ${scanned} / ${total} files${progress}.${escapeHtml(oldReport)}`;
                return;
            }
            if (current) {
                const when = current.completed_at ? new Date(`${current.completed_at}Z`).toLocaleString() : 'unknown time';
                element.innerHTML = `<strong>Complete:</strong> ${Number(current.total_files || 0).toLocaleString()} supported audio files inspected at ${escapeHtml(when)}. ${escapeHtml(status.read_only_notice || '')}`;
                return;
            }
            if (status.last_failed) {
                element.innerHTML = `<strong>Last audit failed:</strong> ${escapeHtml(status.last_failed.error || 'Unknown error')}. No previous report was replaced.`;
                return;
            }
            element.textContent = 'No audit report yet. Run one when you fancy learning what the tags actually remember.';
        }

        function renderAudioAuditRow(item) {
            const classification = AUDIO_AUDIT_CLASSIFICATIONS[item.classification] || item.classification;
            const effective = AUDIO_AUDIT_QUALITY_LABELS[item.effective_quality] || item.effective_quality;
            const storedParts = [
                item.container ? String(item.container).toUpperCase() + ' container' : '',
                item.codec ? String(item.codec).toUpperCase() + ' codec' : '',
                item.bitrate_kbps ? `${item.bitrate_kbps} kbps observed` : '',
            ].filter(Boolean);
            const identity = [item.artist, item.title].filter(Boolean).join(' – ');
            const evidence = (item.evidence || []).map(entry => `
                <li>
                    <strong>${escapeHtml(String(entry.label || entry.field || 'Evidence'))}:</strong>
                    ${escapeHtml(String(entry.value || ''))}
                    <span>${escapeHtml(String(entry.meaning || ''))}</span>
                </li>
            `).join('');
            const caveats = (item.caveats || []).map(caveat =>
                `<li>${escapeHtml(String(caveat))}</li>`
            ).join('');
            return `
                <div class="result-item audio-audit-row">
                    <div class="audio-audit-main">
                        <div class="audio-audit-path">${escapeHtml(String(item.path || item.filename || 'Unknown file'))}</div>
                        ${identity ? `<div class="audio-audit-identity">${escapeHtml(identity)}</div>` : ''}
                        <div class="audio-audit-meta">${escapeHtml(storedParts.join(' · ') || 'Stored format unknown')}</div>
                        <div class="audio-audit-meta">
                            Effective: <strong>${escapeHtml(String(effective || 'Unknown'))}</strong>
                            ${item.source ? ` · Acquisition source: ${escapeHtml(String(item.source))}` : ''}
                        </div>
                    </div>
                    <div class="audio-audit-result">
                        <span class="audio-audit-badge audit-${escapeHtml(String(item.classification))}">${escapeHtml(String(classification))}</span>
                        <details class="audio-audit-evidence">
                            <summary>Why this classification?</summary>
                            <h4>Evidence used</h4>
                            <ul>${evidence}</ul>
                            <h4>Caveats</h4>
                            <ul class="audio-audit-caveats">${caveats}</ul>
                        </details>
                    </div>
                </div>
            `;
        }

        async function loadAudioAudit(refreshFilters = true) {
            const list = document.getElementById('audioAuditList');
            const pager = document.getElementById('audioAuditPager');
            if (!list || isPeon()) return;
            if (audioAuditPollTimer) {
                clearTimeout(audioAuditPollTimer);
                audioAuditPollTimer = null;
            }
            try {
                const statusResponse = await apiFetch('/api/audio-audit');
                if (!statusResponse.ok) throw new Error('Could not load audit status');
                const status = await statusResponse.json();
                audioAuditLastStatus = status;
                renderAudioAuditStatus(status);
                renderAudioAuditSummary(status.summary);
                if (refreshFilters) populateAudioAuditFilters(status);

                if (!status.current) {
                    list.innerHTML = status.running
                        ? '<p class="watched-empty-text">Building the first report. Audio files are being read, not touched.</p>'
                        : '<p class="watched-empty-text">No completed audit report yet.</p>';
                    if (pager) pager.style.display = 'none';
                } else {
                    const query = audioAuditQuery();
                    const separator = query ? '&' : '';
                    const filesResponse = await apiFetch(
                        `/api/audio-audit/files?page=${audioAuditPage}&per_page=${AUDIO_AUDIT_PER_PAGE}${separator}${query}`
                    );
                    if (!filesResponse.ok) throw new Error('Could not load audit files');
                    const data = await filesResponse.json();
                    if (!data.items.length) {
                        list.innerHTML = '<p class="watched-empty-text">No files match these filters.</p>';
                    } else {
                        list.innerHTML = data.items.map(renderAudioAuditRow).join('');
                    }
                    if (pager) {
                        const info = document.getElementById('audioAuditPageInfo');
                        if (info) info.textContent = `Page ${data.page} of ${data.pages} (${Number(data.total || 0).toLocaleString()} files)`;
                        document.getElementById('audioAuditPrevBtn').disabled = data.page <= 1;
                        document.getElementById('audioAuditNextBtn').disabled = data.page >= data.pages;
                        pager.style.display = data.pages > 1 ? 'flex' : 'none';
                    }
                }

                if (status.running && currentTab === 'watched' && watchedMode === 'audit') {
                    audioAuditPollTimer = setTimeout(() => loadAudioAudit(false), 2000);
                }
            } catch (error) {
                list.innerHTML = `<p class="watched-empty-text">Could not load the audit: ${escapeHtml(error.message || 'unknown error')}</p>`;
            }
        }

        async function runAudioAudit() {
            const button = document.getElementById('runAudioAuditBtn');
            if (button) {
                button.disabled = true;
                button.textContent = 'Starting...';
            }
            try {
                const response = await apiFetch('/api/audio-audit/scans', { method: 'POST' });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'Could not start audit');
                audioAuditPage = 1;
                showToast(data.status === 'already_running' ? 'An audio audit is already running' : 'Audio audit started');
                loadAudioAudit();
            } catch (error) {
                showToast(`Could not start audio audit: ${error.message}`, true);
                if (button) {
                    button.disabled = false;
                    button.textContent = 'Run Audit';
                }
            }
        }

        function audioAuditFiltersChanged() {
            audioAuditPage = 1;
            loadAudioAudit(false);
        }

        function changeAudioAuditPage(delta) {
            audioAuditPage = Math.max(1, audioAuditPage + delta);
            loadAudioAudit(false);
            document.getElementById('audioAudit')?.scrollIntoView({ behavior: 'smooth' });
        }

        async function exportAudioAudit(format) {
            if (!audioAuditLastStatus?.current) {
                showToast('Run an audio audit before exporting it', true);
                return;
            }
            try {
                const response = await apiFetch(`/api/audio-audit/export?${audioAuditQuery(format)}`);
                if (!response.ok) throw new Error('Export failed');
                const blob = await response.blob();
                const disposition = response.headers.get('Content-Disposition') || '';
                const match = disposition.match(/filename="([^"]+)"/);
                const filename = match ? match[1] : `musicgrabber-audio-audit.${format}`;
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(url);
            } catch (error) {
                showToast('Could not export the audio audit', true);
            }
        }

        // Audio format segmented buttons (FLAC/Opus) and header toggle are wired
        // through setAudioFormat() - no direct sync needed here.

        // =============================================================================
        // Watched tab pills: Playlists / Upgrades / Audit / M3U Files
        //
        // Same switch as the Artists tab. Each panel loads when you look at it
        // rather than all three firing every time the tab opens, which mattered
        // little until one of them was a census of the entire music library.
        // =============================================================================

        function loadWatchedMode(mode) {
            if (mode === 'playlists') {
                loadWatchedPlaylists();
                populateSourceChips();
            } else if (mode === 'upgrades') {
                loadWatchedUpgrades();
            } else if (mode === 'audit') {
                loadAudioAudit();
            } else if (mode === 'm3u') {
                loadM3uFiles();
            }
        }

        function setWatchedMode(mode) {
            watchedMode = mode;
            showPillMode(watchedTabContainer, mode);
            if (mode !== 'audit' && audioAuditPollTimer) {
                clearTimeout(audioAuditPollTimer);
                audioAuditPollTimer = null;
            }
            loadWatchedMode(mode);
        }

        async function _responseDetail(resp) {
            const body = await resp.json().catch(() => null);
            return body?.detail || `HTTP ${resp.status}`;
        }

        function _formatTrackLength(seconds) {
            const s = Math.round(Number(seconds) || 0);
            if (!s) return '';
            return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
        }

        // -----------------------------------------------------------------------
        // M3U Files pill: the list
        // -----------------------------------------------------------------------

        let m3uFiles = [];

        async function loadM3uFiles() {
            const list = document.getElementById('m3uFilesList');
            if (!list) return;
            if (!m3uFiles.length) list.innerHTML = '<p class="watched-empty-text">Loading&hellip;</p>';
            try {
                const resp = await apiFetch('/api/m3u');
                if (!resp.ok) throw new Error(await _responseDetail(resp));
                const data = await resp.json();
                m3uFiles = data.playlists || [];
                const info = document.getElementById('m3uFolderInfo');
                if (info) info.textContent = `New playlists are saved in ${data.default_dir}`;
                renderM3uFiles();
            } catch (e) {
                list.innerHTML = `<p class="watched-empty-text">Could not load playlist files: ${escapeHtml(e.message || 'unknown error')}</p>`;
            }
        }

        function renderM3uFiles() {
            const list = document.getElementById('m3uFilesList');
            if (!list) return;
            if (!m3uFiles.length) {
                list.innerHTML = '<p class="watched-empty-text">No M3U files yet. Name one above, or switch on Generate M3U for a watched playlist.</p>';
                return;
            }
            list.innerHTML = m3uFiles.map((f, i) => `
                <button type="button" class="m3u-file-row" data-index="${i}">
                    <span class="m3u-file-icon"><i class="fa-solid fa-list-ol"></i></span>
                    <span class="m3u-file-info">
                        <span class="m3u-file-name">${escapeHtml(f.name)}${f.watched ? ' <span class="m3u-badge" title="A watched playlist rebuilds this file on every refresh">watched</span>' : ''}</span>
                        <span class="m3u-file-meta">${escapeHtml(f.folder)} &middot; ${f.entries} track${f.entries === 1 ? '' : 's'}${f.missing ? ` &middot; <span class="m3u-missing-count">${f.missing} missing</span>` : ''}</span>
                    </span>
                    <span class="m3u-file-open">${f.watched ? 'View' : 'Edit'}</span>
                </button>`).join('');
        }

        document.getElementById('m3uFilesList')?.addEventListener('click', (e) => {
            const row = e.target.closest('.m3u-file-row');
            const file = row && m3uFiles[Number(row.dataset.index)];
            if (file) openM3uEditor(file.path);
        });

        document.getElementById('m3uNewNameInput')?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') createM3uFile();
        });

        async function createM3uFile() {
            const input = document.getElementById('m3uNewNameInput');
            const name = (input?.value || '').trim();
            if (!name) {
                input?.focus();
                showToast('Give the playlist a name first', true);
                return;
            }
            try {
                const resp = await apiFetch('/api/m3u', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name }),
                });
                if (!resp.ok) throw new Error(await _responseDetail(resp));
                const data = await resp.json();
                input.value = '';
                showToast(`Created ${data.name}. Now give it some tracks.`);
                await loadM3uFiles();
                openM3uEditor(data.path);
            } catch (e) {
                showToast(`Could not create the playlist: ${e.message}`, true);
            }
        }

        // -----------------------------------------------------------------------
        // M3U editor
        //
        // Rows remember where they came from: `index` for an entry already in
        // the file, `file` for one added from the library. Only those go back to
        // the server, which copies kept entries out of the file byte for byte,
        // so nothing we cannot display gets mangled on the round trip.
        // -----------------------------------------------------------------------

        const m3uEditor = { path: '', name: '', watched: false, mtime: '', rows: [], dirty: false, nextKey: 0 };

        async function openM3uEditor(path) {
            try {
                const resp = await apiFetch(`/api/m3u/file?path=${encodeURIComponent(path)}`);
                if (!resp.ok) throw new Error(await _responseDetail(resp));
                const data = await resp.json();
                Object.assign(m3uEditor, {
                    path: data.path,
                    name: data.name,
                    watched: !!data.watched,
                    mtime: data.mtime_ns,
                    dirty: false,
                    rows: data.entries.map(e => ({ ...e, key: m3uEditor.nextKey++ })),
                });
            } catch (e) {
                showToast(`Could not open the playlist: ${e.message}`, true);
                return;
            }
            const ro = m3uEditor.watched;
            document.getElementById('m3uEditorTitle').textContent = m3uEditor.name;
            const notice = document.getElementById('m3uEditorNotice');
            notice.style.display = ro ? '' : 'none';
            notice.textContent = ro
                ? 'A watched playlist rebuilds this file on every refresh, so any edit here would be quietly undone. Save as Copy gives you one of your own.'
                : '';
            ['m3uAddBtn', 'm3uPruneBtn', 'm3uDeleteBtn', 'm3uSaveBtn'].forEach(id => {
                document.getElementById(id).style.display = ro ? 'none' : '';
            });
            _setM3uError('');
            renderM3uEditor();
            document.getElementById('m3uEditorOverlay').style.display = 'flex';
            document.getElementById('m3uEditorList').scrollTop = 0;
        }

        function closeM3uEditor(force = false) {
            if (!force && m3uEditor.dirty && !confirm('Discard your changes to this playlist?')) return;
            m3uEditor.dirty = false;
            document.getElementById('m3uEditorOverlay').style.display = 'none';
        }

        function _setM3uError(message) {
            const el = document.getElementById('m3uEditorError');
            el.textContent = message;
            el.style.display = message ? '' : 'none';
        }

        function _markM3uDirty() {
            m3uEditor.dirty = true;
            document.getElementById('m3uSaveBtn').disabled = false;
        }

        function renderM3uEditor() {
            const ro = m3uEditor.watched;
            const rows = m3uEditor.rows;
            const missing = rows.filter(r => r.state === 'missing').length;
            const folder = m3uEditor.path.includes('/') ? m3uEditor.path.slice(0, m3uEditor.path.lastIndexOf('/')) : '';
            document.getElementById('m3uEditorMeta').innerHTML =
                `${escapeHtml(folder)} &middot; ${rows.length} track${rows.length === 1 ? '' : 's'}` +
                (missing ? ` &middot; <span class="m3u-missing-count">${missing} missing</span>` : '');
            document.getElementById('m3uPruneBtn').disabled = !missing;
            document.getElementById('m3uSaveBtn').disabled = !m3uEditor.dirty;

            const list = document.getElementById('m3uEditorList');
            if (!rows.length) {
                list.innerHTML = `<div class="m3u-editor-empty">${ro ? 'This playlist is empty.' : 'Empty. Add Tracks to fill it from your library.'}</div>`;
                return;
            }
            list.innerHTML = rows.map((r, i) => {
                const heading = r.title || r.label;
                const sub = [r.artist, r.album].filter(Boolean).join(' · ');
                const stateNote = r.state === 'missing'
                    ? '<span class="m3u-row-flag m3u-row-flag-missing">missing</span>'
                    : r.state === 'external'
                        ? '<span class="m3u-row-flag" title="Points outside your music folder (Navidrome or Lidarr wrote it), so it cannot be checked from here">not checked</span>'
                        : r.isNew ? '<span class="m3u-row-flag m3u-row-flag-new">new</span>' : '';
                return `<div class="m3u-row m3u-row-${r.state}" data-key="${r.key}" title="${escapeHtml(r.line || r.path || '').replace(/"/g, '&quot;')}">
                    ${ro ? '' : '<span class="m3u-drag-handle" title="Drag to reorder"><i class="fa-solid fa-grip-vertical"></i></span>'}
                    <span class="m3u-row-num">${i + 1}</span>
                    <span class="m3u-row-text">
                        <span class="m3u-row-title">${escapeHtml(heading)} ${stateNote}</span>
                        ${sub ? `<span class="m3u-row-sub">${escapeHtml(sub)}</span>` : ''}
                    </span>
                    <span class="m3u-row-duration">${_formatTrackLength(r.duration)}</span>
                    ${ro ? '' : `<span class="m3u-row-actions">
                        <button type="button" class="m3u-row-btn" data-act="up" title="Move up" ${i === 0 ? 'disabled' : ''}><i class="fa-solid fa-chevron-up"></i></button>
                        <button type="button" class="m3u-row-btn" data-act="down" title="Move down" ${i === rows.length - 1 ? 'disabled' : ''}><i class="fa-solid fa-chevron-down"></i></button>
                        <button type="button" class="m3u-row-btn m3u-row-remove" data-act="remove" title="Remove from playlist (the file stays put)"><i class="fa-solid fa-xmark"></i></button>
                    </span>`}
                </div>`;
            }).join('');
        }

        function _m3uRowIndex(key) {
            return m3uEditor.rows.findIndex(r => String(r.key) === String(key));
        }

        document.getElementById('m3uEditorList')?.addEventListener('click', (e) => {
            const btn = e.target.closest('.m3u-row-btn');
            if (!btn || m3uEditor.watched) return;
            const i = _m3uRowIndex(btn.closest('.m3u-row').dataset.key);
            if (i < 0) return;
            const rows = m3uEditor.rows;
            const act = btn.dataset.act;
            if (act === 'remove') {
                rows.splice(i, 1);
            } else {
                const j = act === 'up' ? i - 1 : i + 1;
                if (j < 0 || j >= rows.length) return;
                [rows[i], rows[j]] = [rows[j], rows[i]];
            }
            _markM3uDirty();
            renderM3uEditor();
            // Keep the keyboard where it was so you can keep nudging the same row.
            if (act !== 'remove') {
                document.querySelector(`#m3uEditorList .m3u-row[data-key="${rows[act === 'up' ? i - 1 : i + 1].key}"] [data-act="${act}"]`)?.focus();
            }
        });

        // Drag to reorder. Pointer events, so a finger works as well as a mouse;
        // the handle has touch-action: none, the rest of the row still scrolls.
        (function initM3uDrag() {
            const list = document.getElementById('m3uEditorList');
            if (!list) return;
            let dragged = null;
            let scrollTimer = null;
            let lastY = 0;

            function placeAt(y) {
                const others = [...list.querySelectorAll('.m3u-row:not(.m3u-row-dragging)')];
                const before = others.find(r => {
                    const box = r.getBoundingClientRect();
                    return y < box.top + box.height / 2;
                });
                if (before) {
                    if (dragged.nextElementSibling !== before) list.insertBefore(dragged, before);
                } else if (list.lastElementChild !== dragged) {
                    list.appendChild(dragged);
                }
            }

            function autoScroll() {
                const box = list.getBoundingClientRect();
                const edge = 40;
                let step = 0;
                if (lastY < box.top + edge) step = -Math.ceil((box.top + edge - lastY) / 4);
                else if (lastY > box.bottom - edge) step = Math.ceil((lastY - box.bottom + edge) / 4);
                if (step) {
                    list.scrollTop += step;
                    placeAt(lastY);
                }
            }

            list.addEventListener('pointerdown', (e) => {
                const handle = e.target.closest('.m3u-drag-handle');
                if (!handle || m3uEditor.watched) return;
                e.preventDefault();
                dragged = handle.closest('.m3u-row');
                dragged.classList.add('m3u-row-dragging');
                handle.setPointerCapture(e.pointerId);
                lastY = e.clientY;
                scrollTimer = setInterval(autoScroll, 16);
            });

            list.addEventListener('pointermove', (e) => {
                if (!dragged) return;
                lastY = e.clientY;
                placeAt(e.clientY);
            });

            function finish() {
                if (!dragged) return;
                clearInterval(scrollTimer);
                dragged.classList.remove('m3u-row-dragging');
                dragged = null;
                const order = [...list.querySelectorAll('.m3u-row')].map(r => r.dataset.key);
                const before = m3uEditor.rows.map(r => String(r.key)).join(',');
                if (order.join(',') !== before) {
                    const byKey = new Map(m3uEditor.rows.map(r => [String(r.key), r]));
                    m3uEditor.rows = order.map(k => byKey.get(k));
                    _markM3uDirty();
                }
                renderM3uEditor();
            }
            list.addEventListener('pointerup', finish);
            list.addEventListener('pointercancel', finish);
        })();

        function removeMissingM3uEntries() {
            const before = m3uEditor.rows.length;
            m3uEditor.rows = m3uEditor.rows.filter(r => r.state !== 'missing');
            const removed = before - m3uEditor.rows.length;
            if (!removed) return;
            _markM3uDirty();
            renderM3uEditor();
            showToast(`Removed ${removed} dead entr${removed === 1 ? 'y' : 'ies'}. Save to make it stick.`);
        }

        function addM3uEntryFromLibrary(result) {
            m3uEditor.rows.push({
                key: m3uEditor.nextKey++,
                file: result.path,
                path: result.path,
                state: 'ok',
                isNew: true,
                title: result.title || '',
                artist: result.artist || '',
                album: result.album || '',
                duration: result.duration || 0,
                label: result.relative_path.split('/').pop(),
            });
            _markM3uDirty();
            renderM3uEditor();
            const list = document.getElementById('m3uEditorList');
            list.scrollTop = list.scrollHeight;
            return true;
        }

        function _m3uEntryPicks() {
            return m3uEditor.rows.map(r => (r.file ? { file: r.file } : { index: r.index }));
        }

        async function saveM3uFile() {
            const btn = document.getElementById('m3uSaveBtn');
            btn.disabled = true;
            _setM3uError('');
            try {
                const resp = await apiFetch('/api/m3u/file', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: m3uEditor.path, mtime_ns: m3uEditor.mtime, entries: _m3uEntryPicks() }),
                });
                if (!resp.ok) throw new Error(await _responseDetail(resp));
                showToast(`Saved ${m3uEditor.name}`);
                closeM3uEditor(true);
                loadM3uFiles();
            } catch (e) {
                _setM3uError(e.message);
                btn.disabled = false;
            }
        }

        async function saveM3uAsCopy() {
            const name = prompt('Name for the copy:', `${m3uEditor.name} (copy)`);
            if (!name || !name.trim()) return;
            _setM3uError('');
            try {
                const resp = await apiFetch('/api/m3u', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: name.trim(),
                        copy_from: m3uEditor.path,
                        mtime_ns: m3uEditor.mtime,
                        entries: _m3uEntryPicks(),
                    }),
                });
                if (!resp.ok) throw new Error(await _responseDetail(resp));
                const data = await resp.json();
                showToast(`Saved a copy as ${data.name}`);
                m3uEditor.dirty = false;
                loadM3uFiles();
                openM3uEditor(data.path);
            } catch (e) {
                _setM3uError(e.message);
            }
        }

        async function deleteM3uFile() {
            if (!confirm(`Move the playlist "${m3uEditor.name}" to the trash? Only the playlist file goes; every track it lists stays exactly where it is.`)) return;
            try {
                const resp = await apiFetch(`/api/m3u/file?path=${encodeURIComponent(m3uEditor.path)}`, { method: 'DELETE' });
                if (!resp.ok) throw new Error(await _responseDetail(resp));
                showToast(`${m3uEditor.name} is in the trash. Restore it from Queue if you change your mind.`);
                closeM3uEditor(true);
                loadM3uFiles();
            } catch (e) {
                _setM3uError(e.message);
            }
        }

        // -----------------------------------------------------------------------
        // Library picker: find a file you already own
        //
        // Shared by the M3U editor (add tracks, picker stays open) and by
        // missing watched tracks (match one, picker closes). onPick returns
        // false to keep the picker open, for "are you sure?" moments.
        // -----------------------------------------------------------------------

        const libraryPicker = { onPick: null, keepOpen: false, timer: null, seq: 0, results: [] };

        function openLibraryPicker({ onPick, keepOpen = false, query = '', title = 'Pick from Your Library', meta = '' }) {
            Object.assign(libraryPicker, { onPick, keepOpen, results: [] });
            document.getElementById('libraryPickerTitle').textContent = title;
            document.getElementById('libraryPickerMeta').textContent = meta;
            const input = document.getElementById('libraryPickerInput');
            input.value = query;
            document.getElementById('libraryPickerOverlay').style.display = 'flex';
            input.focus();
            input.select();
            searchLibraryPicker(query);
        }

        function closeLibraryPicker() {
            clearTimeout(libraryPicker.timer);
            libraryPicker.seq++;
            document.getElementById('libraryPickerOverlay').style.display = 'none';
        }

        async function searchLibraryPicker(query) {
            const box = document.getElementById('libraryPickerResults');
            const seq = ++libraryPicker.seq;
            if (query.trim().length < 2) {
                libraryPicker.results = [];
                box.innerHTML = '<div class="m3u-editor-empty">Type a couple of letters: artist, title, album, or folder. Every word has to match somewhere.</div>';
                return;
            }
            try {
                const resp = await apiFetch(`/api/library/search?q=${encodeURIComponent(query)}`);
                if (!resp.ok) throw new Error(await _responseDetail(resp));
                const data = await resp.json();
                if (seq !== libraryPicker.seq) return;
                libraryPicker.results = data.results || [];
                if (!data.index_ready) {
                    box.innerHTML = '<div class="m3u-editor-empty">The library index is still being built. Give it a few minutes and try again.</div>';
                    return;
                }
                if (!libraryPicker.results.length) {
                    box.innerHTML = '<div class="m3u-editor-empty">Nothing in your library matches that.</div>';
                    return;
                }
                box.innerHTML = libraryPicker.results.map((r, i) => {
                    const name = r.relative_path.split('/').pop();
                    const sub = [r.artist, r.album, (r.codec || '').toUpperCase(), _formatTrackLength(r.duration)].filter(Boolean).join(' · ');
                    return `<button type="button" class="library-picker-row" data-index="${i}">
                        <span class="library-picker-title">${escapeHtml(r.title || name)}</span>
                        ${sub ? `<span class="library-picker-sub">${escapeHtml(sub)}</span>` : ''}
                        <span class="library-picker-path">${escapeHtml(r.relative_path)}</span>
                    </button>`;
                }).join('');
            } catch (e) {
                if (seq === libraryPicker.seq) {
                    box.innerHTML = `<div class="m3u-editor-empty">Search failed: ${escapeHtml(e.message)}</div>`;
                }
            }
        }

        async function _pickLibraryResult(index, row) {
            const result = libraryPicker.results[index];
            if (!result || !libraryPicker.onPick || row?.classList.contains('library-picker-busy')) return;
            // Say something the moment a row is picked, however long the answer takes.
            row?.classList.add('library-picker-busy');
            let keep;
            try {
                keep = await libraryPicker.onPick(result);
            } finally {
                row?.classList.remove('library-picker-busy');
            }
            if (keep === false) return;
            if (libraryPicker.keepOpen) {
                row?.classList.add('library-picker-picked');
            } else {
                closeLibraryPicker();
            }
        }

        document.getElementById('libraryPickerInput')?.addEventListener('input', (e) => {
            clearTimeout(libraryPicker.timer);
            libraryPicker.timer = setTimeout(() => searchLibraryPicker(e.target.value), 200);
        });

        document.getElementById('libraryPickerInput')?.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeLibraryPicker();
            } else if (e.key === 'Enter' && libraryPicker.results.length) {
                _pickLibraryResult(0, document.querySelector('#libraryPickerResults .library-picker-row'));
            }
        });

        document.getElementById('libraryPickerResults')?.addEventListener('click', (e) => {
            const row = e.target.closest('.library-picker-row');
            if (row) _pickLibraryResult(Number(row.dataset.index), row);
        });

        // -----------------------------------------------------------------------
        // Missing watched track -> a file you already have
        // -----------------------------------------------------------------------

        function _looseKey(text) {
            return String(text || '').toLowerCase().replace(/\(.*?\)|\[.*?\]/g, '').replace(/[^\p{L}\p{N}]+/gu, '');
        }

        function _looselySame(a, b) {
            const x = _looseKey(a);
            const y = _looseKey(b);
            return !x || !y || x.includes(y) || y.includes(x);
        }

        function matchMissingTrackFromLibrary(playlistId, trackHash, artist, title, rowId) {
            // Brackets and featured credits make the every-word search too picky
            // to be a helpful starting point, so they are left off the prefill.
            const clean = (s) => String(s || '').replace(/\(.*?\)|\[.*?\]/g, ' ').replace(/\b(feat|ft|featuring)\b.*$/i, ' ').trim();
            openLibraryPicker({
                title: 'Match from Your Library',
                meta: `Missing: ${artist} – ${title}`,
                query: `${clean(artist)} ${clean(title)}`.replace(/\s+/g, ' ').trim(),
                onPick: async (result) => {
                    if ((result.title && !_looselySame(result.title, title)) || (result.artist && !_looselySame(result.artist, artist))) {
                        const tagged = `${result.artist || '?'} - ${result.title || '?'}`;
                        if (!confirm(`That file is tagged "${tagged}", not "${artist} - ${title}". Use it for this playlist anyway?`)) return false;
                    }
                    const row = document.getElementById(rowId);
                    const actions = row?.querySelector('.track-list-actions') || row?.lastElementChild;
                    const before = actions?.innerHTML;
                    if (actions) actions.innerHTML = '<span class="track-status-chip track-status-pending">linking&hellip;</span>';
                    try {
                        const resp = await apiFetch(
                            `/api/watched-playlists/${encodeURIComponent(playlistId)}/tracks/${encodeURIComponent(trackHash)}/match`,
                            {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ path: result.path }),
                            }
                        );
                        if (!resp.ok) throw new Error(await _responseDetail(resp));
                    } catch (e) {
                        if (actions) actions.innerHTML = before;
                        showToast(`Could not match it: ${e.message}`, true);
                        return false;
                    }
                    // Linked already; the M3U catches up in the background.
                    showToast(`Matched ${artist} – ${title} to a file you already had`);
                    if (actions) actions.innerHTML = '<span class="track-status-chip track-status-ok">&#10003; matched</span>';
                    // The card's "can no longer be found" count comes from the same
                    // rows, so this is what makes the warning go once the last is done.
                    loadWatchedPlaylists(false);
                    return true;
                },
            });
        }
