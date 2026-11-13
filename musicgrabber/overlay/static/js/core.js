        // Foundations every tab leans on: the UI action allowlist, auth and apiFetch,
        // login, theme, the shared DOM handles, tab switching, pills, toasts, the
        // header's convert toggle, and initApp (started by boot.js, loaded last).

        // Only these named actions can run from UI markup. Arguments are JSON
        // data, never JavaScript; no inline handlers, eval or global-name lookup.
        const uiActions = Object.freeze({
            focusLoginPassword: function(event, args) { if(event.key==='Enter') document.getElementById('loginPassword').focus(); },
            loginOnEnter: function(event, args) { if(event.key==='Enter') doLogin(); },
            doLogin: function(event, args) { doLogin(); },
            changePasswordOnEnter: function(event, args) { if(event.key==='Enter') doChangePassword(); },
            doChangePassword: function(event, args) { doChangePassword(); },
            doLogout: function(event, args) { doLogout(); },
            dismissUpdateBanner: function(event, args) { dismissUpdateBanner(); },
            reloadPage: function(event, args) { location.reload(); },
            dismissReloadBanner: function(event, args) { dismissReloadBanner(); },
            upgradeAll: function(event, args) { upgradeAll(); },
            exportAudioAuditCsv: function(event, args) { exportAudioAudit('csv'); },
            exportAudioAuditJson: function(event, args) { exportAudioAudit('json'); },
            runAudioAudit: function(event, args) { runAudioAudit(); },
            loadM3uFiles: function(event, args) { loadM3uFiles(); },
            toggleLbRow: function(event, args) { toggleLbRow(); },
            addListenBrainzPlaylists: function(event, args) { addListenBrainzPlaylists(); },
            toggleChartsRow: function(event, args) { toggleChartsRow(); },
            watchChartPreset: function(event, args) { watchChartPreset(args[0]); },
            chooseWatchedCustomFolder: function(event, args) { openDestPicker(document.getElementById('watchedCustomSubdir').value, v => { document.getElementById('watchedCustomSubdir').value = v; updateWatchedDestDisplay(); }); },
            clearWatchedCustomSubdir: function(event, args) { clearWatchedCustomSubdir(); },
            findPlaylistOrphans: function(event, args) { findPlaylistOrphans(); },
            audioAuditFiltersChanged: function(event, args) { audioAuditFiltersChanged(); },
            changeAudioAuditPagePrevious: function(event, args) { changeAudioAuditPage(-1); },
            changeAudioAuditPageNext: function(event, args) { changeAudioAuditPage(1); },
            createM3uFile: function(event, args) { createM3uFile(); },
            changeQueuePagePrevious: function(event, args) { changeQueuePage(-1); },
            changeQueuePageNext: function(event, args) { changeQueuePage(1); },
            loadDownloadablePrevious: function(event, args) { loadDownloadable(-1); },
            loadDownloadableNext: function(event, args) { loadDownloadable(1); },
            setDefaultConversionModeOff: function(event, args) { setDefaultConversionMode(false); saveSettings(); },
            setDefaultConversionModeOn: function(event, args) { setDefaultConversionMode(true); saveSettings(); },
            setAudioFormatFlac: function(event, args) { setAudioFormat('flac'); saveSettings(); },
            setAudioFormatAiff: function(event, args) { setAudioFormat('aiff'); saveSettings(); },
            setAudioFormatAlac: function(event, args) { setAudioFormat('alac'); saveSettings(); },
            setAudioFormatOpus: function(event, args) { setAudioFormat('opus'); saveSettings(); },
            setAudioFormatMp3: function(event, args) { setAudioFormat('mp3');  saveSettings(); },
            setMp3BitrateV2: function(event, args) { setMp3Bitrate('v2');  saveSettings(); },
            setMp3BitrateV0: function(event, args) { setMp3Bitrate('v0');  saveSettings(); },
            setMp3Bitrate320k: function(event, args) { setMp3Bitrate('320k'); saveSettings(); },
            setMp3Bitrate256k: function(event, args) { setMp3Bitrate('256k'); saveSettings(); },
            setMp3Bitrate192k: function(event, args) { setMp3Bitrate('192k'); saveSettings(); },
            setMp3Bitrate128k: function(event, args) { setMp3Bitrate('128k'); saveSettings(); },
            setOpusBitrate256k: function(event, args) { setOpusBitrate('256k'); saveSettings(); },
            setOpusBitrate192k: function(event, args) { setOpusBitrate('192k'); saveSettings(); },
            setOpusBitrate128k: function(event, args) { setOpusBitrate('128k'); saveSettings(); },
            setOpusBitrate96k: function(event, args) { setOpusBitrate('96k');  saveSettings(); },
            setAlacBitrateLossless: function(event, args) { setAlacBitrate('lossless'); saveSettings(); },
            setAlacBitrate320k: function(event, args) { setAlacBitrate('320k');     saveSettings(); },
            setAlacBitrate256k: function(event, args) { setAlacBitrate('256k');     saveSettings(); },
            setAlacBitrate192k: function(event, args) { setAlacBitrate('192k');     saveSettings(); },
            setAlacBitrate128k: function(event, args) { setAlacBitrate('128k');     saveSettings(); },
            saveSettings: function(event, args) { saveSettings(); },
            createUser: function(event, args) { createUser(); },
            showChangePasswordScreenOff: function(event, args) { showChangePasswordScreen(false); },
            purgeOrphanedRows: function(event, args) { runMaintenanceAction('purge_orphans'); },
            runMaintenanceActionReconcile: function(event, args) { runMaintenanceAction('reconcile'); },
            cleanRebuildLibrary: function(event, args) { runMaintenanceAction('clean_rebuild'); },
            clearSelectedQueueHistory: function(event, args) { clearSelectedQueueHistory(); },
            showReleaseNotes: function(event, args) { showReleaseNotes(serverConfig.version); },
            closeReleaseNotes: function(event, args) { closeReleaseNotes(); },
            showOlderReleaseNotes: function(event, args) { showOlderReleaseNotes(); },
            showNewerReleaseNotes: function(event, args) { showNewerReleaseNotes(); },
            stopPropagation: function(event, args) { event.stopPropagation(); },
            closeTagEditor: function(event, args) { closeTagEditor(); },
            closeReportDialog: function(event, args) { closeReportDialog(); },
            submitReport: function(event, args) { submitReport(); },
            closeMissingTrackVersionsModal: function(event, args) { closeMissingTrackVersionsModal(); },
            closeM3uEditor: function(event, args) { closeM3uEditor(); },
            openLibraryPickerOn: function(event, args) { openLibraryPicker({ onPick: addM3uEntryFromLibrary, keepOpen: true }); },
            removeMissingM3uEntries: function(event, args) { removeMissingM3uEntries(); },
            deleteM3uFile: function(event, args) { deleteM3uFile(); },
            saveM3uAsCopy: function(event, args) { saveM3uAsCopy(); },
            saveM3uFile: function(event, args) { saveM3uFile(); },
            closeLibraryPicker: function(event, args) { closeLibraryPicker(); },
            closeDestPicker: function(event, args) { closeDestPicker(); },
            destPickerOnCustomInput: function(event, args) { destPickerOnCustomInput(this.value); },
            confirmDestPicker: function(event, args) { confirmDestPicker(); },
            toggleJobDetails: function(event, args) { toggleJobDetails(this); },
            cancelBulkImport: function(event, args) { cancelBulkImport(); },
            jumpToJobStopped: function(event, args) { event.preventDefault(); event.stopPropagation(); jumpToJob(args[0]); },
            loadScoreRationaleStopped: function(event, args) { event.preventDefault(); event.stopPropagation(); loadScoreRationale(args[0]); },
            copyScoreRationaleStopped: function(event, args) { event.stopPropagation(); copyScoreRationale(args[0]); },
            playJobAudioStopped: function(event, args) { event.stopPropagation(); playJobAudio(args[0], this); },
            retryNextJobStopped: function(event, args) { event.stopPropagation(); retryNextJob(args[0]); },
            resolveUnsureStopped: function(event, args) { event.stopPropagation(); resolveUnsure([args[0]], args[1]); },
            openJobRescueVersionsStopped: function(event, args) { event.stopPropagation(); openJobRescueVersions(args[0]); },
            redownloadJobStopped: function(event, args) { event.stopPropagation(); redownloadJob(args[0]); },
            saveJobToDeviceStopped: function(event, args) { event.stopPropagation(); saveJobToDevice(args[0]); },
            playTrashAudio: function(event, args) { playTrashAudio(args[0], this); },
            restoreTrashFile: function(event, args) { restoreTrashFile(args[0]); },
            deleteTrashFile: function(event, args) { deleteTrashFile(args[0], args[1]); },
            removeBlacklistEntry: function(event, args) { removeBlacklistEntry(args[0]); },
            dismissVolumeWarning: function(event, args) { dismissVolumeWarning(this.parentElement); },
            saveJobToDevice: function(event, args) { saveJobToDevice(args[0]); },
            updateWatchedPlaylistConversion: function(event, args) { updateWatchedPlaylistConversion(args[0], this.checked); },
            updateWatchedPlaylistM3u: function(event, args) { updateWatchedPlaylistM3u(args[0], this.checked); },
            updateWatchedPlaylistUsePlaylists: function(event, args) { updateWatchedPlaylistUsePlaylists(args[0], this.checked); },
            updateWatchedPlaylistSyncMode: function(event, args) { updateWatchedPlaylistSyncMode(args[0], this.value); },
            updateWatchedPlaylistRedownloadMissing: function(event, args) { updateWatchedPlaylistRedownloadMissing(args[0], this.value); },
            updateWatchedPlaylistPrioritySource: function(event, args) { updateWatchedPlaylistPrioritySource(args[0], this.value); },
            moveOrphan: function(event, args) { moveOrphans([this.closest('.orphan-row').dataset.file]); },
            moveAllOrphans: function(event, args) { moveOrphans(Array.from(document.querySelectorAll('#orphansResult .orphan-row')).map(r => r.dataset.file)); },
            browseDestinationRoot: function(event, args) { _destPickerBrowse(''); },
            browseDestination: function(event, args) { _destPickerBrowse(args[0]); },
            toggleSourceChip: function(event, args) { toggleSourceChip(this, args[0]); },
            toggleSourceClasses: function(event, args) { this.classList.toggle('on'); this.classList.toggle('off'); },
            selectArtist: function(event, args) { selectArtist(args[0],args[1]); },
            dismissUpgrade: function(event, args) { dismissUpgrade(args[0]); },
            previewUpgrade: function(event, args) { previewUpgrade(args[0], args[1], this, args[2]); },
            stopPreview: function(event, args) { stopPreview(); },
            upgradeOne: function(event, args) { upgradeOne(args[0], this); },
            forceUpgrade: function(event, args) { forceUpgrade(args[0], this); },
            restoreQuarantineEntry: function(event, args) { restoreQuarantineEntry(args[0], this); },
            deleteQuarantineEntry: function(event, args) { deleteQuarantineEntry(args[0], this); },
            deleteOrphanedQuarantineFile: function(event, args) { deleteOrphanedQuarantineFile(this); },
            updateArtistSingles: function(event, args) { updateArtistSingles(args[0], this.checked); },
            updateArtistFromDate: function(event, args) { updateArtistFromDate(args[0], this.value); },
            updateArtistConversion: function(event, args) { updateArtistConversion(args[0], this.checked); },
            updateArtistInterval: function(event, args) { updateArtistInterval(args[0], this.value); },
            confirmArtistSingles: function(event, args) { confirmArtistSingles(args[0]); },
            cancelArtistSingles: function(event, args) { cancelArtistSingles(args[0]); },
            loadArtistTrackPage: function(event, args) { loadArtistTrackPage(args[0], args[1]); },
            showQueueFailures: function(event, args) { showQueueFailures(args[0]); },
            forcePasswordReset: function(event, args) { forcePasswordReset(args[0], args[1]); },
            deleteUser: function(event, args) { deleteUser(args[0], args[1]); },
        });

        function uiAction(name, args, event = 'click') {
            return `data-ui-${event}="${name}" data-ui-${event}-args="${escapeAttr(JSON.stringify(args))}"`;
        }

        function dispatchUiAction(event) {
            // Walk from the clicked control to its parents, preserving the old
            // stopPropagation behaviour for cards and modal backdrops.
            for (let element = event.target; element instanceof Element; element = element.parentElement) {
                const name = element.getAttribute(`data-ui-${event.type}`);
                if (name && Object.hasOwn(uiActions, name) && !element.matches(':disabled')) {
                    const args = JSON.parse(element.getAttribute(`data-ui-${event.type}-args`) || '[]');
                    uiActions[name].call(element, event, args);
                }
                if (event.cancelBubble || event.type === 'mouseenter' || event.type === 'mouseleave') break;
            }
        }

        for (const event of ['click', 'change', 'input', 'keydown']) {
            document.addEventListener(event, dispatchUiAction);
        }
        // These two events do not bubble. Capture only the element they belong to.
        for (const event of ['mouseenter', 'mouseleave']) {
            document.addEventListener(event, dispatchUiAction, true);
        }

        // =============================================================================
        // Release Notes
        // =============================================================================
        // RELEASE_NOTES is defined in release-notes.js, loaded before this file.
        // To update release notes for a new version, edit static/release-notes.js only.

        const releaseNotesVersions = Object.keys(RELEASE_NOTES).sort((a, b) => {
            const aParts = a.split('.').map(n => parseInt(n, 10) || 0);
            const bParts = b.split('.').map(n => parseInt(n, 10) || 0);
            const maxLen = Math.max(aParts.length, bParts.length);
            for (let i = 0; i < maxLen; i++) {
                const av = aParts[i] || 0;
                const bv = bParts[i] || 0;
                if (av !== bv) return bv - av;
            }
            return 0;
        });
        let currentReleaseNotesIndex = -1;

        function updateReleaseNotesPager() {
            const olderBtn = document.getElementById('releaseNotesOlderBtn');
            const newerBtn = document.getElementById('releaseNotesNewerBtn');
            if (!olderBtn || !newerBtn) return;

            const atNewest = currentReleaseNotesIndex <= 0;
            const atOldest = currentReleaseNotesIndex >= releaseNotesVersions.length - 1;

            olderBtn.disabled = atOldest;
            newerBtn.disabled = atNewest;
        }

        function renderReleaseNotes(index) {
            if (index < 0 || index >= releaseNotesVersions.length) return;

            const version = releaseNotesVersions[index];
            const notes = RELEASE_NOTES[version];
            if (!notes) return;

            currentReleaseNotesIndex = index;

            const overlay = document.getElementById('releaseNotesOverlay');
            const titleEl = document.getElementById('releaseNotesTitle');
            const bodyEl = document.getElementById('releaseNotesBody');

            titleEl.textContent = notes.title;

            bodyEl.innerHTML = notes.sections.map(section => {
                if (section.warning) {
                    return `<div style="margin-bottom:16px; padding:12px 14px; background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.4); border-radius:6px;">` +
                        `<div style="font-size:12px; font-weight:700; color:#f59e0b; margin-bottom:6px; text-transform:uppercase; letter-spacing:0.05em;">&#9888; ${escapeHtml(section.heading)}</div>` +
                        `<p style="margin:0; color:var(--text-secondary);">${escapeHtml(section.warning)}</p>` +
                        (section.items ? `<ul style="margin:8px 0 0; padding-left:18px; color:var(--text-secondary);">${section.items.map(item => `<li style="margin-bottom:4px;">${escapeHtml(item)}</li>`).join('')}</ul>` : '') +
                        `</div>`;
                }
                let html = `<div style="margin-bottom:16px;">`;
                html += `<div style="font-size:12px; font-weight:600; color:var(--text-primary); margin-bottom:6px; text-transform:uppercase; letter-spacing:0.05em;">${escapeHtml(section.heading)}</div>`;
                if (section.body) {
                    html += `<p style="margin:0; color:var(--text-secondary);">${escapeHtml(section.body)}</p>`;
                }
                if (section.items) {
                    html += `<ul style="margin:0; padding-left:18px; color:var(--text-secondary);">`;
                    html += section.items.map(item => `<li style="margin-bottom:4px;">${escapeHtml(item)}</li>`).join('');
                    html += `</ul>`;
                }
                html += `</div>`;
                return html;
            }).join('');

            updateReleaseNotesPager();
            overlay.style.display = 'flex';
        }

        function showReleaseNotes(version) {
            // Strip pre-release suffixes (-dev, -beta, -rc1, etc.) so dev builds
            // show the same notes as the release they're building toward.
            const baseVersion = (version || '').replace(/[-+].+$/, '');
            const targetIndex = releaseNotesVersions.indexOf(baseVersion);
            if (targetIndex === -1) return;
            renderReleaseNotes(targetIndex);
        }

        function showOlderReleaseNotes() {
            if (currentReleaseNotesIndex < releaseNotesVersions.length - 1) {
                renderReleaseNotes(currentReleaseNotesIndex + 1);
            }
        }

        function showNewerReleaseNotes() {
            if (currentReleaseNotesIndex > 0) {
                renderReleaseNotes(currentReleaseNotesIndex - 1);
            }
        }

        function closeReleaseNotes() {
            const overlay = document.getElementById('releaseNotesOverlay');
            overlay.style.display = 'none';
            // Store base version (strip -dev etc.) so the modal doesn't reappear for
            // the same release regardless of whether it was seen on a dev or release build.
            if (serverConfig.version) {
                localStorage.setItem('seen_version', serverConfig.version.replace(/[-+].+$/, ''));
            }
        }

        // Close on backdrop click
        document.getElementById('releaseNotesOverlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeReleaseNotes();
        });

        // =============================================================================
        // Session Authentication
        // =============================================================================

        let serverConfig = {}; // Populated from /api/config at startup

        function normaliseRootPath(path) {
            path = String(path || '').trim();
            if (!path || path === '/') return '';
            return '/' + path.replace(/^\/+|\/+$/g, '');
        }

        const APP_ROOT_PATH = (() => {
            const meta = document.querySelector('meta[name="musicgrabber-root-path"]')?.content || '';
            if (meta) return normaliseRootPath(meta);
            const path = window.location.pathname || '/';
            return normaliseRootPath(path.replace(/\/+$/, ''));
        })();

        function withRootPath(path) {
            const value = String(path || '');
            if (!value) return APP_ROOT_PATH || '/';
            if (/^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith('//')) return value;
            if (APP_ROOT_PATH && (value === APP_ROOT_PATH || value.startsWith(`${APP_ROOT_PATH}/`) || value.startsWith(`${APP_ROOT_PATH}?`))) {
                return value;
            }
            if (value.startsWith('/')) return `${APP_ROOT_PATH}${value}`;
            if (value.startsWith('?')) return `${APP_ROOT_PATH || ''}/${value}`;
            return APP_ROOT_PATH ? `${APP_ROOT_PATH}/${value.replace(/^\/+/, '')}` : `/${value.replace(/^\/+/, '')}`;
        }

        // Which Watched tab pill is showing (playlists, upgrades, audit or m3u).
        let watchedMode = 'playlists';
        // And the Queue tab's (queue, downloadable or trash).
        let queueMode = 'queue';

        const missingTrackVersionsState = {
            mode: 'watched',
            jobId: '',
            playlistId: '',
            playlistName: '',
            artist: '',
            title: '',
            rowId: '',
            results: [],
        };

        function getSessionToken() {
            return localStorage.getItem('sessionToken') || '';
        }

        function setSessionToken(token) {
            if (token) localStorage.setItem('sessionToken', token);
            else localStorage.removeItem('sessionToken');
        }

        function getCurrentUser() {
            try {
                return JSON.parse(localStorage.getItem('currentUser') || 'null');
            } catch { return null; }
        }

        function setCurrentUser(user) {
            if (user) localStorage.setItem('currentUser', JSON.stringify(user));
            else localStorage.removeItem('currentUser');
        }

        function isAdmin() {
            const user = getCurrentUser();
            // In single-user mode (no users_exist), user is null but we treat as admin.
            // In session mode, check the role.
            return !user || user.role === 'admin';
        }

        function isPeon() {
            const user = getCurrentUser();
            return !!(user && user.role === 'peon');
        }

        // Namespaced localStorage key, keeps per-user preferences separate on shared browsers.
        // Session-global keys (theme, seen_version, sessionToken, etc.) are NOT namespaced.
        function userStorageKey(key) {
            const user = getCurrentUser();
            return user && user.id ? `mg_${user.id}_${key}` : `mg_${key}`;
        }

        function buildJobDownloadPath(jobId) {
            return withRootPath(`/api/jobs/${encodeURIComponent(String(jobId || ''))}/download`);
        }

        async function getJobDownloadUrl(jobId) {
            if (!serverConfig?.users_exist) return buildJobDownloadPath(jobId);
            const resp = await apiFetch('/api/auth/download-token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: String(jobId || '') }),
            });
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                throw new Error(data.detail || 'Unable to issue download token');
            }
            const data = await resp.json();
            return data.url || buildJobDownloadPath(jobId);
        }

        async function saveJobToDevice(jobId) {
            try {
                const url = await getJobDownloadUrl(jobId);
                const a = document.createElement('a');
                a.href = withRootPath(url);
                a.download = '';
                a.rel = 'noopener';
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                a.remove();
            } catch (error) {
                showToast('Failed to start download', true);
            }
        }

        async function apiFetch(url, options = {}) {
            const token = getSessionToken();
            const headers = { ...options.headers };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            const response = await fetch(withRootPath(url), { ...options, headers });

            if (response.status === 401) {
                // Session expired or invalid; clear local state and show login screen
                if (token === getSessionToken() && serverConfig && serverConfig.users_exist) {
                    setSessionToken(null);
                    setCurrentUser(null);
                    showLoginScreen();
                }
                throw new Error('Authentication required');
            }

            if (response.status === 429) {
                const data = await response.json().catch(() => ({}));
                const err = new Error(data.detail || 'Rate limit exceeded');
                err.status = 429;
                throw err;
            }

            return response;
        }

        // =============================================================================
        // Login / Logout / Password Change
        // =============================================================================

        function showLoginScreen() {
            document.getElementById('loginScreen').style.display = 'flex';
            document.getElementById('app').style.display = 'none';
            document.getElementById('loginError').style.display = 'none';
            document.getElementById('loginPassword').value = '';
            setTimeout(() => document.getElementById('loginUsername').focus(), 50);
        }

        function hideLoginScreen() {
            document.getElementById('loginScreen').style.display = 'none';
            document.getElementById('app').style.display = '';
        }

        async function doLogin() {
            const username = document.getElementById('loginUsername').value.trim();
            const password = document.getElementById('loginPassword').value;
            const errorDiv = document.getElementById('loginError');
            const btn = document.getElementById('loginBtn');

            if (!username || !password) {
                errorDiv.textContent = 'Please enter username and password.';
                errorDiv.style.display = 'block';
                return;
            }

            btn.disabled = true;
            errorDiv.style.display = 'none';

            try {
                const resp = await fetch(withRootPath('/api/auth/login'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password }),
                });

                if (!resp.ok) {
                    const data = await resp.json().catch(() => ({}));
                    errorDiv.textContent = data.detail || 'Invalid username or password.';
                    errorDiv.style.display = 'block';
                    return;
                }

                const data = await resp.json();
                setSessionToken(data.token);
                setCurrentUser(data.user);
                hideLoginScreen();

                if (data.user.force_password_change) {
                    showChangePasswordScreen(true);
                    return;
                }

                // Reinitialise the app now that we're logged in
                location.reload();
            } catch (e) {
                errorDiv.textContent = 'Login failed. Please try again.';
                errorDiv.style.display = 'block';
            } finally {
                btn.disabled = false;
            }
        }

        async function doLogout() {
            try {
                const token = getSessionToken();
                if (token) {
                    await fetch(withRootPath('/api/auth/logout'), {
                        method: 'POST',
                        headers: { 'Authorization': `Bearer ${token}` },
                    });
                }
            } catch {}
            setSessionToken(null);
            setCurrentUser(null);
            location.reload();
        }

        function showChangePasswordScreen(forced = false) {
            document.getElementById('changePasswordScreen').style.display = 'flex';
            document.getElementById('app').style.display = 'none';
            document.getElementById('changePasswordForced').style.display = forced ? 'block' : 'none';
            document.getElementById('changePasswordError').style.display = 'none';
        }

        function hideChangePasswordScreen() {
            document.getElementById('changePasswordScreen').style.display = 'none';
            document.getElementById('app').style.display = '';
        }

        async function doChangePassword() {
            const currentPw = document.getElementById('changePasswordCurrent').value;
            const newPw = document.getElementById('changePasswordNew').value;
            const confirmPw = document.getElementById('changePasswordConfirm').value;
            const errorDiv = document.getElementById('changePasswordError');

            if (newPw !== confirmPw) {
                errorDiv.textContent = 'Passwords do not match.';
                errorDiv.style.display = 'block';
                return;
            }
            if (newPw.length < 8) {
                errorDiv.textContent = 'Password must be at least 8 characters.';
                errorDiv.style.display = 'block';
                return;
            }

            try {
                const resp = await apiFetch('/api/auth/password', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
                });
                if (!resp.ok) {
                    const data = await resp.json().catch(() => ({}));
                    errorDiv.textContent = data.detail || 'Failed to change password.';
                    errorDiv.style.display = 'block';
                    return;
                }
                // Update stored user to clear force_password_change
                const user = getCurrentUser();
                if (user) {
                    user.force_password_change = false;
                    setCurrentUser(user);
                }
                hideChangePasswordScreen();
                location.reload();
            } catch (e) {
                // apiFetch turns a 429 into a thrown error; say so rather than blaming the password.
                errorDiv.textContent = e && e.status === 429
                    ? 'Too many attempts, so password changes are being rate limited. Give it a moment and try again.'
                    : 'Error changing password.';
                errorDiv.style.display = 'block';
            }
        }

        // =============================================================================
        // Theme Toggle - System, Day and Night Modes
        // =============================================================================

        // 'system' follows the OS colour scheme, including when it changes mid-session.
        // Dark comes after light so a dark user is one click from 'system'.
        const THEME_ORDER = ['system', 'light', 'dark'];
        const THEME_ICONS = { system: 'fa-circle-half-stroke', light: 'fa-sun', dark: 'fa-moon' };
        const systemLightQuery = window.matchMedia?.('(prefers-color-scheme: light)');

        function getTheme() {
            const theme = localStorage.getItem('theme');
            return THEME_ORDER.includes(theme) ? theme : 'system';
        }

        function nextTheme(theme) {
            return THEME_ORDER[(THEME_ORDER.indexOf(theme) + 1) % THEME_ORDER.length];
        }

        function setTheme(theme) {
            const shown = theme === 'system' ? (systemLightQuery?.matches ? 'light' : 'dark') : theme;
            document.documentElement.setAttribute('data-theme', shown);
            localStorage.setItem('theme', theme);
            const btn = document.getElementById('themeToggle');
            if (btn) {
                btn.innerHTML = `<i class="fa-solid ${THEME_ICONS[theme]}"></i>`;
                const label = theme === 'system' ? `following your system (${shown})` : theme;
                btn.title = `Theme: ${label}. Click for ${nextTheme(theme)}.`;
            }
        }

        // Apply saved theme immediately
        setTheme(getTheme());

        systemLightQuery?.addEventListener('change', () => {
            if (getTheme() === 'system') setTheme('system');
        });

        document.getElementById('themeToggle').addEventListener('click', () => {
            setTheme(nextTheme(getTheme()));
        });

        // =============================================================================
        // DOM Elements
        // =============================================================================

        const searchInput = document.getElementById('searchInput');
        const searchBtn = document.getElementById('searchBtn');
        const searchClearBtn = document.getElementById('searchClearBtn');

        function setSearchValue(val) {
            searchInput.value = val;
            searchClearBtn.style.display = val ? '' : 'none';
        }
        const searchHistory = document.getElementById('searchHistory');
        const relatedSuggestions = document.getElementById('relatedSuggestions');
        const resultsTab = document.getElementById('resultsTab');
        const bulkTabContainer = document.getElementById('bulkTabContainer');
        const artistsTabContainer = document.getElementById('artistsTabContainer');
        const bulkInput = document.getElementById('bulkInput');
        const bulkImportBtn = document.getElementById('bulkImportBtn');
        const bulkResults = document.getElementById('bulkResults');
        const bulkImportJobsContainer = document.getElementById('bulkImportJobsContainer');
        const fileUpload = document.getElementById('fileUpload');
        const fileName = document.getElementById('fileName');
        const spotifyUrlInput = document.getElementById('spotifyUrlInput');
        const fetchSpotifyBtn = document.getElementById('fetchSpotifyBtn');
        const spotifyError = document.getElementById('spotifyError');
        const albumMatchPanel = document.getElementById('albumMatchPanel');
        const longformSplitPanel = document.getElementById('longformSplitPanel');
        const queueTabContainer = document.getElementById('queueTabContainer');
        const queueTab = document.getElementById('queueTab');
        const queueLiveSummary = document.getElementById('queueLiveSummary');
        const queueHistorySort = document.getElementById('queueHistorySort');
        const clearQueueBtn = document.getElementById('clearQueueBtn');
        const resetStatsBtn = document.getElementById('resetStatsBtn');
        const watchedTabContainer = document.getElementById('watchedTabContainer');
        const watchedList = document.getElementById('watchedList');
        const watchedUrlInput = document.getElementById('watchedUrlInput');
        const addWatchedBtn = document.getElementById('addWatchedBtn');
        const watchedIntervalSelect = document.getElementById('watchedIntervalSelect');
        const watchedError = document.getElementById('watchedError');
        const refreshAllWatchedBtn = document.getElementById('refreshAllWatchedBtn');
        const watchedScheduleInfo = document.getElementById('watchedScheduleInfo');
        const watchedConvertAudio = document.getElementById('watchedConvertAudio');
        const toast = document.getElementById('toast');
        const tabs = document.querySelectorAll('.tab');
        const lineCounter = document.getElementById('lineCounter');
        const statsTabContainer = document.getElementById('statsTabContainer');
        const statsContent = document.getElementById('statsContent');
        const settingsTabContainer = document.getElementById('settingsTabContainer');
        const monitorTabContainer = document.getElementById('monitorTabContainer'); // musik-monitor (EPIC 9, ADR-0001)
        const createPlaylistCheckbox = document.getElementById('createPlaylistCheckbox');
        const playlistNameInput = document.getElementById('playlistNameInput');
        const convertAudioCheckbox = document.getElementById('convertAudio');
        let watchedConversionTouched = false;

        // audioFormat tracks which format to use when conversion is on.
        let audioFormat = 'opus';

        function conversionChoiceLabel(enabled) {
            if (!enabled) return 'Keep source';
            const labels = { flac: 'FLAC', aiff: 'AIFF', alac: 'ALAC', opus: 'Opus', mp3: 'MP3' };
            return `Convert to ${labels[audioFormat] || 'Opus'}`;
        }

        function updateConversionLabels() {
            // Text only; the warning triangle is a sibling element and would not
            // survive being written over.
            const headerText = document.getElementById('headerFormatText');
            if (headerText) headerText.textContent = conversionChoiceLabel(convertAudioCheckbox.checked);

            const watchedLabel = document.getElementById('watchedFormatLabel');
            if (watchedLabel && watchedConvertAudio) {
                watchedLabel.textContent = conversionChoiceLabel(watchedConvertAudio.checked);
            }

            const artistLabel = document.getElementById('artistFlacLabel');
            const artistCheckbox = document.getElementById('artistConvertAudio');
            if (artistLabel && artistCheckbox) {
                artistLabel.textContent = conversionChoiceLabel(artistCheckbox.checked);
            }

            updateLossyConversionWarning();
        }

        function conversionTargetIsLossy() {
            if (audioFormat === 'opus' || audioFormat === 'mp3') return true;
            if (audioFormat === 'alac') {
                return (document.getElementById('settingAlacBitrate')?.value || 'lossless') !== 'lossless';
            }
            return false;
        }

        function conversionTargetName() {
            const labels = { flac: 'FLAC', aiff: 'AIFF', alac: 'ALAC', opus: 'Opus', mp3: 'MP3' };
            if (audioFormat === 'alac' && conversionTargetIsLossy()) return 'AAC in an M4A container';
            return labels[audioFormat] || 'Opus';
        }

        function updateLossyConversionWarning() {
            const warning = document.getElementById('lossyConversionWarning');
            const conversionEnabled = document.getElementById('settingDefaultConvertAudio')?.checked ?? false;
            const message = `Warning: converting a lossless source to ${conversionTargetName()} is a quality downgrade. Choose Keep source to preserve the original audio.`;
            if (warning) {
                warning.textContent = message;
                warning.style.display = conversionEnabled && conversionTargetIsLossy() ? 'block' : 'none';
            }

            // Only meaningful when there's a lossy target to potentially skip
            // re-encoding into; a lossless target (FLAC, real ALAC) has nothing
            // for this toggle to do.
            const losslessOnlyRow = document.getElementById('convertLosslessOnlyRow');
            if (losslessOnlyRow) {
                losslessOnlyRow.style.display = conversionEnabled && conversionTargetIsLossy() ? 'block' : 'none';
            }

            const headerControl = document.querySelector('.header-format-label');
            const headerWouldDowngrade = convertAudioCheckbox?.checked && conversionTargetIsLossy();
            // The label itself does the warning: amber, bold, and wearing a triangle.
            // A separate badge simply would not fit next to everything else up there.
            document.getElementById('headerFormatLabel')?.classList.toggle('is-lossy', !!headerWouldDowngrade);
            if (headerControl) {
                headerControl.title = headerWouldDowngrade
                    ? message
                    : 'Choose whether downloads keep their source format or are converted to the format selected in Settings.';
            }
        }

        function setDefaultConversionMode(enabled) {
            const input = document.getElementById('settingDefaultConvertAudio');
            if (!input) return;
            if (input.disabled && input.checked !== Boolean(enabled)) return;

            input.checked = Boolean(enabled);

            const keepBtn = document.getElementById('conversionModeKeep');
            const convertBtn = document.getElementById('conversionModeConvert');
            if (keepBtn) {
                keepBtn.classList.toggle('active', !input.checked);
                keepBtn.disabled = input.disabled;
            }
            if (convertBtn) {
                convertBtn.classList.toggle('active', input.checked);
                convertBtn.disabled = input.disabled;
            }

            const targets = document.getElementById('conversionTargetOptions');
            if (targets) targets.style.display = input.checked ? 'flex' : 'none';

            // Format-specific notes and quality rows should not remain visible
            // while "Keep source" is selected.
            setAudioFormat(audioFormat);
        }

        function setAudioFormat(format) {
            audioFormat = ['flac', 'aiff', 'alac', 'opus', 'mp3'].includes(format) ? format : 'opus';

            const btnFlac = document.getElementById('formatBtnFlac');
            const btnAiff = document.getElementById('formatBtnAiff');
            const btnAlac = document.getElementById('formatBtnAlac');
            const btnOpus = document.getElementById('formatBtnOpus');
            const btnMp3  = document.getElementById('formatBtnMp3');
            if (btnFlac) btnFlac.classList.toggle('active', audioFormat === 'flac');
            if (btnAiff) btnAiff.classList.toggle('active', audioFormat === 'aiff');
            if (btnAlac) btnAlac.classList.toggle('active', audioFormat === 'alac');
            if (btnOpus) btnOpus.classList.toggle('active', audioFormat === 'opus');
            if (btnMp3)  btnMp3.classList.toggle('active',  audioFormat === 'mp3');

            updateConversionLabels();

            const conversionEnabled = document.getElementById('settingDefaultConvertAudio')?.checked ?? false;
            const alacNote = document.getElementById('alacFormatNote');
            const aiffNote = document.getElementById('aiffFormatNote');
            if (aiffNote) aiffNote.style.display = conversionEnabled && audioFormat === 'aiff' ? 'block' : 'none';
            if (alacNote) alacNote.style.display = conversionEnabled && audioFormat === 'alac' ? 'block' : 'none';
            const mp3Note = document.getElementById('mp3FormatNote');
            if (mp3Note) mp3Note.style.display = conversionEnabled && audioFormat === 'mp3' ? 'block' : 'none';

            // Show quality sub-rows only for the relevant format
            const mp3QualityRow = document.getElementById('mp3QualityRow');
            if (mp3QualityRow) mp3QualityRow.style.display = conversionEnabled && audioFormat === 'mp3' ? '' : 'none';
            const opusQualityRow = document.getElementById('opusQualityRow');
            if (opusQualityRow) opusQualityRow.style.display = conversionEnabled && audioFormat === 'opus' ? '' : 'none';
            const alacQualityRow = document.getElementById('alacQualityRow');
            if (alacQualityRow) alacQualityRow.style.display = conversionEnabled && audioFormat === 'alac' ? '' : 'none';

            // Keep hidden input in sync so settings save picks it up
            const hiddenInput = document.getElementById('settingAudioFormat');
            if (hiddenInput) hiddenInput.value = audioFormat;

            localStorage.setItem(userStorageKey('audioFormat'), audioFormat);
        }

        function setMp3Bitrate(val) {
            const valid = ['v2', 'v0', '320k', '256k', '192k', '128k'];
            if (!valid.includes(val)) val = 'v2';
            const ids = { v2: 'mp3QualityBtnV2', v0: 'mp3QualityBtnV0', '320k': 'mp3QualityBtn320',
                          '256k': 'mp3QualityBtn256', '192k': 'mp3QualityBtn192', '128k': 'mp3QualityBtn128' };
            for (const [k, id] of Object.entries(ids)) {
                const btn = document.getElementById(id);
                if (btn) btn.classList.toggle('active', k === val);
            }
            const input = document.getElementById('settingMp3Bitrate');
            if (input) input.value = val;
            localStorage.setItem(userStorageKey('mp3Bitrate'), val);
        }

        function setOpusBitrate(val) {
            const valid = ['256k', '192k', '128k', '96k'];
            if (!valid.includes(val)) val = '256k';
            const ids = { '256k': 'opusQualityBtn256',
                          '192k': 'opusQualityBtn192', '128k': 'opusQualityBtn128', '96k': 'opusQualityBtn96' };
            for (const [k, id] of Object.entries(ids)) {
                const btn = document.getElementById(id);
                if (btn) btn.classList.toggle('active', k === val);
            }
            const input = document.getElementById('settingOpusBitrate');
            if (input) input.value = val;
            localStorage.setItem(userStorageKey('opusBitrate'), val);
        }

        function setAlacBitrate(val) {
            const valid = ['lossless', '320k', '256k', '192k', '128k'];
            if (!valid.includes(val)) val = 'lossless';
            const ids = { 'lossless': 'alacQualityBtnLossless', '320k': 'alacQualityBtn320',
                          '256k': 'alacQualityBtn256', '192k': 'alacQualityBtn192', '128k': 'alacQualityBtn128' };
            for (const [k, id] of Object.entries(ids)) {
                const btn = document.getElementById(id);
                if (btn) btn.classList.toggle('active', k === val);
            }
            const input = document.getElementById('settingAlacBitrate');
            if (input) input.value = val;
            localStorage.setItem(userStorageKey('alacBitrate'), val);
            updateLossyConversionWarning();
        }

        const versionLabel = document.getElementById('versionLabel');
        // Dismiss the pure-HTML boot panel from index.html. Called from initApp's
        // finally block, so it goes whether we land on the app, the login screen,
        // or a config fetch that fell over.
        function dismissBootPanel() {
            document.getElementById('bootPanel')?.remove();
        }

        // Load config from server then handle auth and app initialisation
        async function initApp() {
          try {
            let config = null;
            try {
                // Before login (or with no session) the server sends only what the
                // login screen needs; a session token gets the full payload. Plain
                // fetch rather than apiFetch, so a stale token can never bounce
                // anyone to the login screen from here.
                const sessionToken = getSessionToken();
                const resp = await fetch(
                    withRootPath('/api/config'),
                    sessionToken ? { headers: { 'Authorization': `Bearer ${sessionToken}` } } : undefined,
                );
                if (resp.ok) config = await resp.json();
            } catch {}

            if (config) {
                serverConfig = config;

                const bindLabel = document.getElementById('serverBindAddress');
                if (bindLabel && config.listen_addr && config.listen_port) {
                    const address = config.listen_addr.includes(':') ? `[${config.listen_addr}]` : config.listen_addr;
                    bindLabel.textContent = `${address}:${config.listen_port}`;
                }

                // Set version label
                if (config.version) {
                    versionLabel.textContent = `v${config.version}`;
                    // Show release notes once when the version changes (new install or update).
                    // Compare base versions (strip -dev etc.) so dev builds trigger correctly.
                    const baseVersion = config.version.replace(/[-+].+$/, '');
                    const seenVersion = localStorage.getItem('seen_version');
                    if (seenVersion !== baseVersion && RELEASE_NOTES[baseVersion]) {
                        showReleaseNotes(config.version);
                    }
                }

                // Set convert on/off from server if not saved locally
                if (localStorage.getItem(userStorageKey('convertAudio')) === null && typeof config.default_convert_audio === 'boolean') {
                    convertAudioCheckbox.checked = config.default_convert_audio;
                    if (watchedConvertAudio && !watchedConversionTouched) {
                        watchedConvertAudio.checked = config.default_convert_audio;
                    }
                    updateConversionLabels();
                }

                // Set audio format picker from server if not saved locally
                if (localStorage.getItem(userStorageKey('audioFormat')) === null && config.audio_format) {
                    setAudioFormat(config.audio_format);
                }

                // Multi-user: check if we need a login screen
                if (config.users_exist) {
                    const token = getSessionToken();
                    if (!token) {
                        showLoginScreen();
                        return;
                    }
                    // Validate existing session
                    try {
                        const meResp = await apiFetch('/api/auth/me');
                        if (!meResp.ok) {
                            setSessionToken(null);
                            setCurrentUser(null);
                            showLoginScreen();
                            return;
                        }
                        const user = await meResp.json();
                        setCurrentUser(user);
                        if (user.force_password_change) {
                            showChangePasswordScreen(true); // forced
                            return;
                        }
                    } catch {
                        showLoginScreen();
                        return;
                    }
                }

                // Show warning if music directory isn't mounted
                if (config.volume_mounted === false) {
                    showVolumeMountWarning();
                }

                // Show Playlists folder toggle in watched playlist add form if configured
                if (config.playlists_subdir) {
                    const toggle = document.getElementById('watchedPlaylistsDirToggle');
                    if (toggle) toggle.style.display = 'flex';
                    const watchedUsePlaylistsDir = document.getElementById('watchedUsePlaylistsDir');
                    if (watchedUsePlaylistsDir) watchedUsePlaylistsDir.checked = true;
                }
            }

            // Single-user mode OR successful session, apply role-based UI
            applyUserRoleToUI();
            populateSourceChips();
            startSourceHealthPolling();
            if (config) checkForUpdate();
            if (config) loadPlaylists();
            reattachBulkImportIfActive();
          } finally {
            dismissBootPanel();
          }
        }

        // Restore convert on/off from localStorage (namespaced per user)
        const legacyConvertPref = localStorage.getItem(userStorageKey('convertToFlac'));
        const savedConvertPref = localStorage.getItem(userStorageKey('convertAudio')) ?? legacyConvertPref;
        if (savedConvertPref !== null) {
            convertAudioCheckbox.checked = savedConvertPref === 'true';
            if (legacyConvertPref !== null) {
                localStorage.setItem(userStorageKey('convertAudio'), legacyConvertPref);
                localStorage.removeItem(userStorageKey('convertToFlac'));
            }
        }

        // Restore audio format picker from localStorage (namespaced per user)
        const savedAudioFormat = localStorage.getItem(userStorageKey('audioFormat'));
        if (savedAudioFormat) {
            setAudioFormat(savedAudioFormat);
        }
        updateConversionLabels();

        if (watchedConvertAudio) {
            watchedConvertAudio.addEventListener('change', () => {
                watchedConversionTouched = true;
                updateConversionLabels();
            });
        }
        const artistConvertAudio = document.getElementById('artistConvertAudio');
        if (artistConvertAudio) {
            artistConvertAudio.addEventListener('change', updateConversionLabels);
        }

        // Save convert preference when header toggle is flipped
        convertAudioCheckbox.addEventListener('change', () => {
            localStorage.setItem(userStorageKey('convertAudio'), convertAudioCheckbox.checked);
            if (watchedConvertAudio && !watchedConversionTouched) {
                watchedConvertAudio.checked = convertAudioCheckbox.checked;
            }
            updateConversionLabels();
        });

        let currentTab = 'results';
        // Tab switching
        const allTabPanels = [resultsTab, bulkTabContainer, artistsTabContainer, watchedTabContainer, queueTabContainer, statsTabContainer, settingsTabContainer, monitorTabContainer /* musik-monitor (EPIC 9, ADR-0001) */];
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                tabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentTab = tab.dataset.tab;

                // Remove visible from all panels, then re-add on the next frame so the
                // transition actually fires (display:none -> display:block needs a tick to paint)
                allTabPanels.forEach(p => p.classList.remove('tab-visible'));
                const panelMap = {
                    results: resultsTab,
                    bulk: bulkTabContainer,
                    artists: artistsTabContainer,
                    watched: watchedTabContainer,
                    queue: queueTabContainer,
                    stats: statsTabContainer,
                    settings: settingsTabContainer,
                    monitor: monitorTabContainer // musik-monitor (EPIC 9, ADR-0001)
                };
                const target = panelMap[currentTab];
                if (target) target.classList.add('tab-visible');

                // These controls sit above the tab panels in the DOM, so explicitly
                // scope them to Results instead of letting related-search chips (and
                // friends) wander into Artists, Queue, Settings, etc.
                [
                    document.getElementById('singleTrackSearch'),
                    document.getElementById('sourceHealthStrip'),
                    relatedSuggestions,
                    exploreBar,
                    document.getElementById('searchProgress'),
                    document.getElementById('destinationPickerRow')
                ].forEach(element => {
                    element?.classList.toggle('results-context-hidden', currentTab !== 'results');
                });

                // Stop preview when leaving results tab
                if (currentTab !== 'results') {
                    stopPreview();
                }
                // Same idea for the Find New Artists taster preview
                if (currentTab !== 'artists') {
                    _stopDiscoverPreview();
                }

                if (currentTab === 'artists') {
                    // Defer one tick so direct album links can populate their richer
                    // MBID-backed state first. A plain tab click remains pristine and
                    // inherits the artist from the last successful singles search.
                    setTimeout(primeAlbumSearchFromResults, 0);
                }

                if (currentTab === 'queue') {
                    initPillGroup(document.getElementById('queueModePills'));
                    loadQueueMode();
                } else {
                    stopQueuePolling();
                    stopLibraryPlayback();
                }

                if (currentTab === 'watched') {
                    // Measured now rather than at start-up: a hidden tab has no
                    // width, and the indicator would slide in at zero pixels.
                    initPillGroup(document.getElementById('watchedModePills'));
                    loadWatchedMode(watchedMode);
                } else if (watchedRefreshPollInterval) {
                    clearInterval(watchedRefreshPollInterval);
                    watchedRefreshPollInterval = null;
                }
                if (currentTab !== 'watched' && audioAuditPollTimer) {
                    clearTimeout(audioAuditPollTimer);
                    audioAuditPollTimer = null;
                }

                if (currentTab === 'artists') {
                    // Same reason as the Watched pills above: measure once visible.
                    initPillGroup(document.getElementById('artistsModePills'));
                    loadWatchedArtists();
                }

                if (currentTab === 'bulk') {
                    populateSourceChips();
                }

                if (currentTab === 'stats') {
                    initPillGroup(document.getElementById('statsModePills'));
                    loadStats();
                }

                if (currentTab === 'settings') {
                    initPillGroup(document.getElementById('settingsModePills'));
                    loadSettings();
                    loadBlacklist();
                    if (isAdmin()) loadUsers();
                }

                // Show floating save bar only on settings tab
                const floatingBar = document.getElementById('settingsFloatingBar');
                if (floatingBar) floatingBar.style.display = currentTab === 'settings' ? 'flex' : 'none';
            });
        });

        // The build token this page was served with; see noticeNewBuild()
        const PAGE_BUILD = document.querySelector('meta[name="musicgrabber-build"]')?.content || '';
        let dismissedReloadBuild = '';

        // -----------------------------------------------------------------------
        // Reusable pill / segmented control
        //
        // A .pill-group holds any number of .pill buttons plus one .pill-indicator
        // span. Clicking a pill toggles .active and slides the indicator underneath
        // it (measured in pixels, so it copes fine with pills of different widths,
        // narrow screens, whatever). Fires a "pillchange" CustomEvent on the group
        // with { value } set from the clicked pill's data-value, so callers don't
        // need to know or care how the control itself works.
        // -----------------------------------------------------------------------

        function initPillGroup(group) {
            if (!group || group.dataset.pillInit) return;
            group.dataset.pillInit = '1';

            const pills = Array.from(group.querySelectorAll('.pill'));
            const indicator = group.querySelector('.pill-indicator');

            function moveIndicator() {
                const active = group.querySelector('.pill.active');
                // Zero width means the tab is hidden; keep the last good size
                // rather than shrinking to nothing and growing back every visit.
                if (!active || !indicator || !active.offsetWidth) return;
                indicator.style.width = `${active.offsetWidth}px`;
                indicator.style.height = `${active.offsetHeight}px`;
                indicator.style.transform = `translate(${active.offsetLeft}px, ${active.offsetTop}px)`;
                const shown = pills.filter(p => p.offsetWidth);
                group.classList.toggle('pill-group-wrapped', shown.some(p => p.offsetTop !== shown[0].offsetTop));
            }

            pills.forEach(pill => {
                pill.addEventListener('click', () => {
                    if (pill.classList.contains('active')) return;
                    pills.forEach(p => p.classList.remove('active'));
                    pill.classList.add('active');
                    moveIndicator();
                    group.dispatchEvent(new CustomEvent('pillchange', { detail: { value: pill.dataset.value } }));
                });
            });

            // Pills can reflow at narrow widths, or grow when a label picks up a
            // count, so keep the indicator honest either way.
            window.addEventListener('resize', moveIndicator);
            const pillSizes = new ResizeObserver(moveIndicator);
            pills.forEach(pill => pillSizes.observe(pill));
            // Defer so layout has actually settled before we measure it.
            requestAnimationFrame(moveIndicator);
        }

        // Shows the panels and header buttons marked data-mode="<mode>" inside a
        // tab, and hides the rest of them. The pill bar says which mode you are in.
        function showPillMode(container, mode) {
            container.querySelectorAll('.mode-panel, .mode-actions')
                .forEach(el => el.classList.toggle('mode-hidden', el.dataset.mode !== mode));
        }

        function escapeHtmlText(value) {
            return escapeHtml(value == null ? '' : String(value));
        }

        let toastHideTimer = null;

        function showToast(message, isError = false) {
            if (toastHideTimer) clearTimeout(toastHideTimer);
            toast.textContent = message;
            toast.className = 'toast' + (isError ? ' error' : '');
            toast.setAttribute('role', isError ? 'alert' : 'status');
            toast.setAttribute('aria-live', isError ? 'assertive' : 'polite');
            toast.classList.add('show');
            const readingTime = Math.min(6000, Math.max(2800, String(message || '').length * 55));
            toastHideTimer = setTimeout(() => {
                toast.classList.remove('show');
                toastHideTimer = null;
            }, readingTime);
        }

        function showVolumeMountWarning() {
            // Don't show if user dismissed it
            if (localStorage.getItem('dismissedVolumeWarning') === 'true') return;

            const banner = document.createElement('div');
            banner.className = 'warning-banner';
            banner.innerHTML = `
                <div class="warning-content">
                    <strong>Warning:</strong> Music directory doesn't appear to be mounted.
                    Downloads will be lost when the container restarts.
                    <a href="https://gitlab.com/g33kphr33k/musicgrabber/-/blob/main/guide/troubleshooting.md#downloads-staying-inside-the-container-or-not-appearing-in-the-mounted-volume" target="_blank" rel="noopener">See setup guide</a>
                </div>
                <button class="warning-dismiss" data-ui-click="dismissVolumeWarning">&times;</button>
            `;
            document.body.insertBefore(banner, document.body.firstChild);
        }

        function dismissVolumeWarning(banner) {
            localStorage.setItem('dismissedVolumeWarning', 'true');
            banner.remove();
        }

        // Newer release on GitLab? The server caches the answer, so this is cheap.
        // Dismissing hides it until the next release rather than forever.
        async function checkForUpdate() {
            try {
                const resp = await apiFetch('/api/update-check');
                if (!resp.ok) return;
                const status = await resp.json();
                if (!status.update_available) return;
                if (localStorage.getItem('dismissed_update_version') === status.latest) return;

                document.getElementById('updateBannerLatest').textContent = `v${status.latest}`;
                document.getElementById('updateBannerCurrent').textContent = `v${status.current}`;
                if (status.changelog_url) {
                    document.getElementById('updateBannerChangelog').href = status.changelog_url;
                }
                const banner = document.getElementById('updateBanner');
                banner.dataset.version = status.latest;
                banner.style.display = 'flex';
            } catch {}
        }

        function dismissUpdateBanner() {
            const banner = document.getElementById('updateBanner');
            localStorage.setItem('dismissed_update_version', banner.dataset.version || '');
            banner.style.display = 'none';
        }

        // Cache-busting covers fresh page loads, not a tab that never reloads: it
        // carries on running the old scripts against the new server, rendering
        // fine right up until it sends a request the new server will not take.
        // The health poll brings the server's build token; differ from the one
        // this page was served with and we say so.
        function noticeNewBuild(build) {
            if (!build || !PAGE_BUILD || build === PAGE_BUILD || build === dismissedReloadBuild) return;
            const banner = document.getElementById('reloadBanner');
            banner.dataset.build = build;
            banner.style.display = 'flex';
        }

        function dismissReloadBanner() {
            const banner = document.getElementById('reloadBanner');
            dismissedReloadBuild = banner.dataset.build || '';
            banner.style.display = 'none';
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function escapeAttr(text) {
            // For a plain quoted attribute: data-title="${escapeAttr(val)}". The
            // value reads back from dataset exactly as it went in. innerHTML
            // leaves `"` alone, which is how Weird "Al" used to arrive as `Weird `.
            return escapeHtml(String(text)).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
        }

        // =============================================================================
        // Multi-User UI
        // =============================================================================

        function applyUserRoleToUI() {
            const admin = isAdmin();
            const peon = isPeon();

            // Toggle visibility of admin-only sections (set inline, no CSS class needed)
            document.querySelectorAll('.admin-only').forEach(el => {
                el.style.display = admin ? '' : 'none';
            });

            // Peons are kept on the happy path: no Settings, no Stats. Anything
            // else marked .peon-hide vanishes for them too. If they were sat on
            // a now-hidden tab, bounce them back to Results.
            document.querySelectorAll('.peon-hide').forEach(el => {
                el.style.display = peon ? 'none' : '';
            });
            if (peon) {
                const activeTab = document.querySelector('.tab.active');
                if (activeTab && activeTab.classList.contains('peon-hide')) {
                    const resultsTabBtn = document.querySelector('.tab[data-tab="results"]');
                    if (resultsTabBtn) resultsTabBtn.click();
                }
                if (document.querySelector(`#watchedModePills .pill.peon-hide[data-value="${watchedMode}"]`)) {
                    document.querySelector('#watchedModePills .pill[data-value="playlists"]')?.click();
                }
                // Pin the convert-to-format checkboxes to whatever the admin set
                // globally. The server overrides these on submit either way, but
                // mirroring the value here keeps the (hidden) UI honest if anyone
                // peeks via dev tools.
                const adminDefault = !!(serverConfig && (serverConfig.default_convert_audio ?? serverConfig.default_convert_to_flac));
                const conversion = document.getElementById('convertAudio');
                const watchedFlac = document.getElementById('watchedConvertAudio');
                if (conversion) conversion.checked = adminDefault;
                if (watchedFlac) watchedFlac.checked = adminDefault;
            }

            // Show logout button only in session mode
            const logoutBtn = document.getElementById('logoutBtn');
            if (logoutBtn) {
                logoutBtn.style.display = serverConfig && serverConfig.users_exist ? '' : 'none';
            }

            // Show current username in header if in session mode
            const userDisplay = document.getElementById('currentUserDisplay');
            if (userDisplay) {
                const user = getCurrentUser();
                if (user && serverConfig && serverConfig.users_exist) {
                    userDisplay.textContent = user.username;
                    userDisplay.style.display = '';
                } else {
                    userDisplay.style.display = 'none';
                }
            }

            // Show the "Change my password" button only when in session mode
            const changePwSection = document.getElementById('changePasswordSection');
            if (changePwSection) {
                changePwSection.style.display = (serverConfig && serverConfig.users_exist) ? '' : 'none';
            }

            // Singles-only mode used to hide the whole Albums tab; now that album
            // browsing lives inside Artists (alongside singles-following, which
            // singles-only mode should NOT hide), just tuck away the album bits:
            // the one-off browser and, per card, the per-artist album panel.
            const singlesOnlyMode = !!(serverConfig && serverConfig.singles_only_mode);
            // Two of the three chooser options are album work, so they go; "Follow
            // for Singles" stays, which leaves the chooser a slightly lonely but
            // perfectly functional one-button affair.
            document.querySelectorAll('#artistModeChooser [data-artist-mode]').forEach(btn => {
                if (btn.dataset.artistMode !== 'singles') {
                    btn.style.display = singlesOnlyMode ? 'none' : '';
                }
            });
            if (singlesOnlyMode) {
                for (const id of ['artistAlbumsFollowPanel', 'artistOneOffPanel']) {
                    const el = document.getElementById(id);
                    if (el) el.style.display = 'none';
                }
            }
            const artistAlbumPanel = document.getElementById('artistAlbumPanel');
            if (singlesOnlyMode && artistAlbumPanel) artistAlbumPanel.style.display = 'none';
            // Bulk Import hosts the same browser, so it hides on the same terms;
            // otherwise singles-only mode is just a suggestion with a side door.
            const bulkAlbumBrowseWrap = document.getElementById('bulkAlbumBrowseWrap');
            if (bulkAlbumBrowseWrap) bulkAlbumBrowseWrap.style.display = singlesOnlyMode ? 'none' : '';
        }
