        // Where a download goes: the 'Add to...' playlist/album picker and the
        // destination folder browser.

        // =============================================================================
        // Destination Picker (unified "Add to..." for Playlist and Album)
        // =============================================================================

        let _playlists = [];
        let _destinationMode = null; // null | 'playlist' | 'album'
        let _albumDirArtist = null;
        let _albumDirAlbum = null;
        let _albumInfo = null; // response from /api/albums/dirs/{artist}/{album}/info
        let _albumRepairSelection = null;

        let playlistScanTimer = null;
        let playlistScanBusy = false;
        async function loadPlaylists() {
            if (playlistScanBusy) return;
            playlistScanBusy = true;
            clearTimeout(playlistScanTimer);
            try {
                const resp = await apiFetch('/api/playlists');
                if (!resp.ok) {
                    console.warn('GET /api/playlists returned', resp.status);
                    return;
                }
                const data = await resp.json();
                _playlists = data.playlists || [];
                _populatePlaylistSelector();
                _populatePlaylistNameSuggestions();
                const sel = document.getElementById('playlistSelectorInput');
                if (sel && data.scan_state !== 'ready') {
                    const status = document.createElement('option');
                    status.disabled = true;
                    status.textContent = data.scan_state === 'error'
                        ? 'Library playlist scan failed; try again shortly'
                        : 'Scanning library playlists…';
                    sel.appendChild(status);
                }
                if (data.scan_state === 'refreshing' && document.getElementById('app').style.display !== 'none') {
                    playlistScanTimer = setTimeout(loadPlaylists, 3000);
                }
            } catch (e) {
                console.warn('loadPlaylists failed:', e);
            } finally {
                playlistScanBusy = false;
            }
        }

        function _populatePlaylistSelector() {
            const sel = document.getElementById('playlistSelectorInput');
            if (!sel) return;
            const current = sel.value;
            while (sel.options.length > 1) sel.remove(1);
            for (const pl of _playlists) {
                const opt = document.createElement('option');
                opt.value = pl.name;
                opt.textContent = pl.is_watched ? `${pl.label || pl.name} (watched)` : pl.name;
                opt.dataset.isWatched = pl.is_watched ? '1' : '0';
                opt.dataset.syncMode = pl.sync_mode || 'append';
                sel.appendChild(opt);
            }
            const newOpt = document.createElement('option');
            newOpt.value = '__new__';
            newOpt.textContent = '+ New playlist...';
            sel.appendChild(newOpt);
            if (current && [...sel.options].some(o => o.value === current)) {
                sel.value = current;
            }
        }

        // Bulk Import's playlist name box suggests the M3U files it can add to.
        // Watched playlists stay out: their M3U is rebuilt from the source on every
        // refresh, so anything added by hand would quietly drop off it again.
        function _populatePlaylistNameSuggestions() {
            const list = document.getElementById('playlistNameSuggestions');
            if (!list) return;
            list.replaceChildren(..._playlists.filter(pl => !pl.is_watched).map(pl => {
                const opt = document.createElement('option');
                opt.value = pl.name;
                return opt;
            }));
        }

        function getSelectedPlaylist() {
            if (_destinationMode !== 'playlist') return null;
            const panel = document.getElementById('playlistSelector');
            const sel = document.getElementById('playlistSelectorInput');
            if (!sel || !sel.value || sel.value === '__new__' || !panel || panel.style.display === 'none') return null;
            const opt = sel.options[sel.selectedIndex];
            return { name: sel.value, is_watched: opt && opt.dataset.isWatched === '1' };
        }

        function _updatePlaylistSelectorWarning() {
            const sel = document.getElementById('playlistSelectorInput');
            const warn = document.getElementById('playlistSelectorWarn');
            if (!warn || !sel) return;
            const opt = sel.options[sel.selectedIndex];
            const isMirror = opt && opt.dataset.isWatched === '1' && opt.dataset.syncMode === 'mirror';
            warn.style.display = isMirror ? 'inline' : 'none';
        }

        function getSelectedAlbumRoute() {
            if (_destinationMode !== 'album') return null;
            if (!_albumDirArtist || !_albumDirAlbum) return null;

            const base = {
                album_artist: _albumDirArtist,
                album_name: _albumDirAlbum,
                release_mbid: _albumInfo ? _albumInfo.release_mbid : null,
                track_total: _albumInfo ? ((_albumInfo.tracks || []).length || null) : null,
            };

            if (!_albumInfo || !_albumInfo.release_mbid) {
                // Folder routing only, no MBID so no track metadata enrichment
                return { ...base, mode: 'no_mbid' };
            }

            const modeSel = document.getElementById('albumRouteMode');
            const trackSel = document.getElementById('albumRouteTrackSelect');
            const mode = modeSel ? modeSel.value : 'auto';

            if (mode !== 'manual') {
                return { ...base, mode: 'auto' };
            }
            if (!trackSel || trackSel.value === '') return null;

            const idx = Number(trackSel.value);
            const track = (_albumInfo.tracks || [])[idx];
            if (!track) return null;
            let trackNum = null;
            if (track.position && /^\d+$/.test(String(track.position).trim())) {
                trackNum = Number(String(track.position).trim());
            } else {
                trackNum = idx + 1;
            }
            return {
                ...base, mode: 'manual', track_title: track.title, track_number: trackNum,
                disc_number: track.disc_number || null, disc_total: track.disc_total || null,
            };
        }

        function _resetDestination() {
            _albumRepairSelection = null;
            const repairBanner = document.getElementById('albumRepairBanner');
            if (repairBanner) repairBanner.style.display = 'none';
            _destinationMode = null;
            _albumDirArtist = null;
            _albumDirAlbum = null;
            _albumInfo = null;
            const toggle = document.getElementById('destinationPickerToggle');
            const modePanel = document.getElementById('destinationModePanel');
            const playlistPanel = document.getElementById('playlistSelector');
            const albumPanel = document.getElementById('albumRoutePanel');
            if (toggle) { toggle.textContent = '+ Add to...'; toggle.classList.remove('active'); }
            if (modePanel) modePanel.style.display = 'none';
            if (playlistPanel) playlistPanel.style.display = 'none';
            if (albumPanel) albumPanel.style.display = 'none';
            const sel = document.getElementById('playlistSelectorInput');
            if (sel) sel.value = '';
            _updatePlaylistSelectorWarning();
        }

        async function _loadAlbumArtists() {
            const sel = document.getElementById('albumArtistSelect');
            if (!sel) return;
            sel.innerHTML = '<option value="">Loading...</option>';
            try {
                const resp = await apiFetch('/api/albums/dirs');
                if (!resp.ok) { sel.innerHTML = '<option value="">Error loading artists</option>'; return; }
                const data = await resp.json();
                sel.innerHTML = '<option value="">Select artist...</option>';
                for (const a of (data.artists || [])) {
                    const opt = document.createElement('option');
                    opt.value = a;
                    opt.textContent = a;
                    sel.appendChild(opt);
                }
                if (!(data.artists || []).length) {
                    sel.innerHTML = '<option value="">No albums on disk yet</option>';
                }
            } catch (e) {
                sel.innerHTML = '<option value="">Error loading artists</option>';
            }
        }

        async function _loadAlbumFolders(artist) {
            const sel = document.getElementById('albumFolderSelect');
            const statusEl = document.getElementById('albumRouteStatus');
            const modeSel = document.getElementById('albumRouteMode');
            const trackSel = document.getElementById('albumRouteTrackSelect');
            const warnEl = document.getElementById('albumRouteWarn');
            _albumInfo = null;
            _albumDirAlbum = null;
            if (statusEl) statusEl.style.display = 'none';
            if (modeSel) modeSel.style.display = 'none';
            if (trackSel) trackSel.style.display = 'none';
            if (warnEl) warnEl.style.display = 'none';
            if (!sel) return;
            sel.innerHTML = '<option value="">Loading...</option>';
            sel.style.display = '';
            try {
                const resp = await apiFetch(`/api/albums/dirs/${encodeURIComponent(artist)}`);
                if (!resp.ok) { sel.innerHTML = '<option value="">Error loading albums</option>'; return; }
                const data = await resp.json();
                sel.innerHTML = '<option value="">Select album...</option>';
                for (const al of (data.albums || [])) {
                    const opt = document.createElement('option');
                    opt.value = al;
                    opt.textContent = al;
                    sel.appendChild(opt);
                }
            } catch (e) {
                sel.innerHTML = '<option value="">Error loading albums</option>';
            }
        }

        async function _loadAlbumInfo(artist, album) {
            const statusEl = document.getElementById('albumRouteStatus');
            const modeSel = document.getElementById('albumRouteMode');
            const trackSel = document.getElementById('albumRouteTrackSelect');
            const warnEl = document.getElementById('albumRouteWarn');
            _albumDirArtist = artist;
            _albumDirAlbum = album;
            _albumInfo = null;
            if (statusEl) { statusEl.textContent = 'Loading...'; statusEl.style.display = ''; }
            if (modeSel) modeSel.style.display = 'none';
            if (trackSel) trackSel.style.display = 'none';
            if (warnEl) warnEl.style.display = 'none';
            try {
                const resp = await apiFetch(
                    `/api/albums/dirs/${encodeURIComponent(artist)}/${encodeURIComponent(album)}/info`
                );
                const data = await resp.json();
                if (data.found && data.release_mbid) {
                    _albumInfo = data;
                    if (statusEl) statusEl.textContent = `${data.artist} / ${data.album}`;
                    const tracks = data.tracks || [];
                    if (trackSel) {
                        trackSel.innerHTML = tracks.map((t, idx) => {
                            const num = t.position ? `${t.position}. ` : `${idx + 1}. `;
                            return `<option value="${idx}">${escapeHtml(num + (t.title || 'Unknown'))}</option>`;
                        }).join('');
                    }
                    if (modeSel) { modeSel.style.display = ''; modeSel.value = 'auto'; }
                    if (trackSel) trackSel.style.display = 'none';
                } else {
                    if (statusEl) statusEl.textContent = `${artist} / ${album}`;
                    if (warnEl) {
                        warnEl.textContent = 'Album info not found - track metadata will not be embedded.';
                        warnEl.style.display = '';
                    }
                }
            } catch (e) {
                if (statusEl) statusEl.textContent = 'Error loading album info.';
            }
        }

        function _initPlaylistPanelInternals() {
            const sel = document.getElementById('playlistSelectorInput');
            const clearBtn = document.getElementById('playlistSelectorClear');
            const newNameInput = document.getElementById('playlistNewNameInput');
            const newNameConfirm = document.getElementById('playlistNewNameConfirm');
            if (!sel) return;

            function _showNewPlaylistInput() {
                if (newNameInput) { newNameInput.style.display = ''; newNameInput.value = ''; newNameInput.focus(); }
                if (newNameConfirm) newNameConfirm.style.display = '';
            }
            function _hideNewPlaylistInput() {
                if (newNameInput) newNameInput.style.display = 'none';
                if (newNameConfirm) newNameConfirm.style.display = 'none';
            }
            function _confirmNewPlaylist() {
                const name = (newNameInput ? newNameInput.value : '').trim();
                if (!name) { newNameInput && newNameInput.focus(); return; }
                const existing = [...sel.options].find(o => o.value.toLowerCase() === name.toLowerCase() && o.value !== '__new__');
                if (existing) { sel.value = existing.value; _hideNewPlaylistInput(); _updatePlaylistSelectorWarning(); return; }
                const newOpt = document.createElement('option');
                newOpt.value = name;
                newOpt.textContent = name;
                newOpt.dataset.isWatched = '0';
                const sentinel = [...sel.options].find(o => o.value === '__new__');
                sel.insertBefore(newOpt, sentinel || null);
                sel.value = name;
                _hideNewPlaylistInput();
                _updatePlaylistSelectorWarning();
            }

            sel.addEventListener('change', () => {
                if (sel.value === '__new__') _showNewPlaylistInput();
                else { _hideNewPlaylistInput(); _updatePlaylistSelectorWarning(); }
            });
            if (newNameConfirm) newNameConfirm.addEventListener('click', _confirmNewPlaylist);
            if (newNameInput) {
                newNameInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') { e.preventDefault(); _confirmNewPlaylist(); }
                    if (e.key === 'Escape') { sel.value = ''; _hideNewPlaylistInput(); _updatePlaylistSelectorWarning(); }
                });
            }
            if (clearBtn) clearBtn.addEventListener('click', _resetDestination);
        }

        function _initAlbumPanelInternals() {
            const artistSel = document.getElementById('albumArtistSelect');
            const albumSel = document.getElementById('albumFolderSelect');
            const modeSel = document.getElementById('albumRouteMode');
            const trackSel = document.getElementById('albumRouteTrackSelect');
            const clearBtn = document.getElementById('albumRouteClear');

            if (artistSel) {
                artistSel.addEventListener('change', () => {
                    const artist = artistSel.value;
                    if (artist) _loadAlbumFolders(artist);
                    else {
                        if (albumSel) { albumSel.innerHTML = '<option value="">Select album...</option>'; albumSel.style.display = 'none'; }
                        const statusEl = document.getElementById('albumRouteStatus');
                        if (statusEl) statusEl.style.display = 'none';
                        if (modeSel) modeSel.style.display = 'none';
                        if (trackSel) trackSel.style.display = 'none';
                        _albumDirArtist = null; _albumDirAlbum = null; _albumInfo = null;
                    }
                });
            }
            if (albumSel) {
                albumSel.addEventListener('change', () => {
                    const album = albumSel.value;
                    if (album && artistSel && artistSel.value) _loadAlbumInfo(artistSel.value, album);
                });
            }
            if (modeSel) {
                modeSel.addEventListener('change', () => {
                    if (trackSel) trackSel.style.display = modeSel.value === 'manual' ? '' : 'none';
                });
            }
            if (clearBtn) clearBtn.addEventListener('click', _resetDestination);
        }

        function initDestinationPicker() {
            const toggle = document.getElementById('destinationPickerToggle');
            const modePanel = document.getElementById('destinationModePanel');
            const playlistPanel = document.getElementById('playlistSelector');
            const albumPanel = document.getElementById('albumRoutePanel');
            if (!toggle) return;

            toggle.addEventListener('click', () => {
                if (_destinationMode !== null || _albumRepairSelection) { _resetDestination(); return; }
                if (modePanel) modePanel.style.display = 'flex';
                toggle.classList.add('active');
            });

            const destModePlaylist = document.getElementById('destModePlaylist');
            if (destModePlaylist) {
                destModePlaylist.addEventListener('click', () => {
                    _destinationMode = 'playlist';
                    if (modePanel) modePanel.style.display = 'none';
                    if (playlistPanel) playlistPanel.style.display = 'flex';
                    toggle.textContent = 'Adding to playlist';
                    loadPlaylists();
                    const sel = document.getElementById('playlistSelectorInput');
                    if (sel) sel.focus();
                });
            }

            const destModeAlbum = document.getElementById('destModeAlbum');
            if (destModeAlbum) {
                destModeAlbum.addEventListener('click', () => {
                    _destinationMode = 'album';
                    if (modePanel) modePanel.style.display = 'none';
                    if (albumPanel) albumPanel.style.display = 'flex';
                    toggle.textContent = 'Adding to album';
                    _loadAlbumArtists();
                });
            }

            const pickerClear = document.getElementById('destinationPickerClear');
            if (pickerClear) pickerClear.addEventListener('click', _resetDestination);

            _initPlaylistPanelInternals();
            _initAlbumPanelInternals();
        }

        // =============================================================================
        // Destination folder picker modal
        // =============================================================================
        let _destPickerCallback = null;
        let _destPickerBrowsePath = '';   // directory currently being listed
        let _destPickerSelected = '';     // path currently selected (confirmed in input)

        async function openDestPicker(currentValue, callback) {
            _destPickerCallback = callback;
            _destPickerSelected = (currentValue || '').trim();
            _destPickerBrowsePath = _destPickerSelected
                ? _destPickerSelected.split('/').slice(0, -1).join('/')
                : '';
            const input = document.getElementById('destPickerCustomInput');
            if (input) input.value = _destPickerSelected;
            const overlay = document.getElementById('destPickerOverlay');
            if (overlay) overlay.style.display = 'flex';
            await _destPickerBrowse(_destPickerBrowsePath);
        }

        function closeDestPicker() {
            const overlay = document.getElementById('destPickerOverlay');
            if (overlay) overlay.style.display = 'none';
            _destPickerCallback = null;
        }

        function confirmDestPicker() {
            const raw = (document.getElementById('destPickerCustomInput')?.value || '').trim();
            if (_destPickerCallback) _destPickerCallback(raw);
            closeDestPicker();
        }

        function destPickerOnCustomInput(value) {
            _destPickerSelected = value.trim();
            _destPickerRenderBreadcrumb(_destPickerBrowsePath);
        }

        async function _destPickerBrowse(path) {
            _destPickerBrowsePath = path;
            _destPickerRenderBreadcrumb(path);
            const listEl = document.getElementById('destPickerList');
            if (!listEl) return;
            listEl.innerHTML = '<div class="dest-picker-loading">Loading...</div>';
            try {
                const encoded = path ? encodeURIComponent(path) : '';
                const resp = await apiFetch(`/api/music-dirs${encoded ? '?path=' + encoded : ''}`);
                if (!resp.ok) throw new Error('Failed to load directories');
                const data = await resp.json();
                const dirs = Array.isArray(data.directories) ? data.directories : [];
                listEl.innerHTML = '';
                if (path) {
                    const upBtn = document.createElement('button');
                    upBtn.className = 'dest-picker-item dest-picker-up';
                    upBtn.innerHTML = '<i class="fa-solid fa-arrow-left"></i> Up';
                    upBtn.onclick = () => {
                        const parent = path.includes('/') ? path.split('/').slice(0, -1).join('/') : '';
                        _destPickerBrowse(parent);
                    };
                    listEl.appendChild(upBtn);
                    // "Select this folder" button for the current browsed path
                    const selfBtn = document.createElement('button');
                    selfBtn.className = 'dest-picker-item dest-picker-self';
                    selfBtn.innerHTML = `<i class="fa-solid fa-check"></i> Use: <strong>${escapeHtml(path)}</strong>`;
                    selfBtn.onclick = () => _destPickerSetValue(path);
                    listEl.appendChild(selfBtn);
                } else {
                    const rootBtn = document.createElement('button');
                    rootBtn.className = 'dest-picker-item dest-picker-self';
                    rootBtn.innerHTML = '<i class="fa-solid fa-check"></i> Use: <strong>music root</strong>';
                    rootBtn.onclick = () => _destPickerSetValue('.');
                    listEl.appendChild(rootBtn);
                }
                if (dirs.length === 0) {
                    const empty = document.createElement('div');
                    empty.className = 'dest-picker-empty';
                    empty.textContent = 'No subdirectories here.';
                    listEl.appendChild(empty);
                }
                for (const dir of dirs) {
                    const btn = document.createElement('button');
                    btn.className = 'dest-picker-item';
                    const name = dir.split('/').pop();
                    btn.innerHTML = `<i class="fa-solid fa-folder"></i> ${escapeHtml(name)}`;
                    btn.onclick = () => _destPickerBrowse(dir);
                    listEl.appendChild(btn);
                }
            } catch (e) {
                listEl.innerHTML = '<div class="dest-picker-empty">Could not load directories.</div>';
            }
        }

        function _destPickerSetValue(path) {
            _destPickerSelected = path;
            const input = document.getElementById('destPickerCustomInput');
            if (input) input.value = path === '.' ? '.' : path;
        }

        function _destPickerRenderBreadcrumb(path) {
            const el = document.getElementById('destPickerBreadcrumb');
            if (!el) return;
            const musicRoot = (serverConfig?.music_dir || '/music').replace(/\/+$/, '');
            const parts = path ? path.split('/') : [];
            let html = `<span class="dest-crumb dest-crumb-root" data-ui-click="browseDestinationRoot">${escapeHtml(musicRoot)}</span>`;
            let cumulative = '';
            for (const part of parts) {
                cumulative = cumulative ? `${cumulative}/${part}` : part;
                const captured = cumulative;
                html += ` <span class="dest-crumb-sep">/</span> <span class="dest-crumb" ${uiAction('browseDestination', [captured])}>${escapeHtml(part)}</span>`;
            }
            el.innerHTML = html;
        }
