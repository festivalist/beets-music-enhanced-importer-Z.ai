        // Settings tab: settings, maintenance, connection tests, cookies, the
        // blacklist and user management.

        // Settings pills. Every group stays in the page, so Save still saves the
        // lot; the pill only decides what you have to scroll past. Remembered in
        // this browser, since whoever was in Connections yesterday is usually
        // back for Connections today.
        const SETTINGS_MODE_KEY = 'mg_settings_mode';
        document.getElementById('settingsModePills')
            ?.addEventListener('pillchange', (e) => {
                showPillMode(settingsTabContainer, e.detail.value);
                try { localStorage.setItem(SETTINGS_MODE_KEY, e.detail.value); } catch {}
                // The pills stick to the top of the screen, so a switch from
                // halfway down Downloads would land halfway down Connections.
                // Start the new group from its top instead; the pills stay put.
                const tabTop = settingsTabContainer.getBoundingClientRect().top;
                if (tabTop < 0) window.scrollBy(0, tabTop);
            });
        try {
            const savedSettingsMode = localStorage.getItem(SETTINGS_MODE_KEY);
            const savedPill = savedSettingsMode
                && document.querySelector(`#settingsModePills .pill[data-value="${CSS.escape(savedSettingsMode)}"]`);
            if (savedPill) {
                document.querySelectorAll('#settingsModePills .pill')
                    .forEach(p => p.classList.toggle('active', p === savedPill));
                showPillMode(settingsTabContainer, savedSettingsMode);
            }
        } catch {}

        const _reasonLabels = {
            wrong_track: 'Wrong track',
            poor_quality: 'Poor quality',
            slowed_pitched: 'Slowed/pitched',
            contentid: 'ContentID dodge',
            other: 'Other'
        };

        async function loadBlacklist() {
            const container = document.getElementById('blacklistContent');
            if (!container) return;

            try {
                const response = await apiFetch('/api/blacklist?limit=200');
                if (!response.ok) throw new Error('Failed to load blacklist');

                const data = await response.json();
                const entries = data.entries || [];

                if (entries.length === 0) {
                    container.innerHTML = '<p style="color:var(--text-secondary); font-style:italic;">No blacklisted items yet. Use the Report button on queue items to flag bad tracks.</p>';
                    return;
                }

                container.innerHTML = `
                    <table style="width:100%; border-collapse:collapse; font-size:12px;">
                        <thead>
                            <tr style="text-align:left; color:var(--text-secondary); border-bottom:1px solid var(--border);">
                                <th style="padding:6px 8px;">Type</th>
                                <th style="padding:6px 8px;">Value</th>
                                <th style="padding:6px 8px;">Source</th>
                                <th style="padding:6px 8px;">Reason</th>
                                <th style="padding:6px 8px;">Date</th>
                                <th style="padding:6px 8px;"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${entries.map(e => {
                                const isUploader = !e.video_id && e.uploader;
                                const typeLabel = isUploader ? 'Uploader' : 'Video';
                                const value = isUploader ? e.uploader : (e.video_id || '?');
                                const reasonLabel = _reasonLabels[e.reason] || e.reason || '';
                                const dateStr = formatDateYmd(e.created_at);
                                return `<tr style="border-bottom:1px solid var(--border);">
                                    <td style="padding:6px 8px;"><span style="display:inline-block; padding:2px 6px; font-size:10px; font-weight:600; border-radius:4px; background:${isUploader ? 'var(--warning)' : 'var(--error)'}; color:#000;">${typeLabel}</span></td>
                                    <td style="padding:6px 8px; max-width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(value)}">${escapeHtml(value)}</td>
                                    <td style="padding:6px 8px;">${escapeHtml(e.source || '')}</td>
                                    <td style="padding:6px 8px;">${escapeHtml(reasonLabel)}</td>
                                    <td style="padding:6px 8px;">${dateStr}</td>
                                    <td style="padding:6px 8px;"><button ${uiAction('removeBlacklistEntry', [e.id])} style="padding:3px 8px; font-size:11px; font-family:inherit; font-weight:600; background:var(--bg-tertiary); color:var(--error); border:1px solid var(--border); border-radius:4px; cursor:pointer;">Remove</button></td>
                                </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                    <p style="margin-top:8px; color:var(--text-secondary); font-size:11px;">${entries.length} entr${entries.length === 1 ? 'y' : 'ies'}</p>
                `;
            } catch (error) {
                container.innerHTML = '<p style="color:var(--error);">Failed to load blacklist</p>';
            }
        }

        async function removeBlacklistEntry(entryId) {
            try {
                const response = await apiFetch(`/api/blacklist/${entryId}`, { method: 'DELETE' });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || 'Remove failed');
                }
                showToast('Blacklist entry removed');
                loadBlacklist();
            } catch (error) {
                showToast(error.message || 'Remove failed', true);
            }
        }

        // =============================================================================
        // Settings Management
        // =============================================================================

        // Mapping from setting keys to form element IDs
        const settingsFieldMap = {
            'skip_dupes': 'settingSkipDupes',
            'enable_musicbrainz': 'settingEnableMusicbrainz',
            'enable_deezer_metadata': 'settingEnableDeezerMetadata',
            'enable_lyrics': 'settingEnableLyrics',
            'update_check_enabled': 'settingUpdateCheckEnabled',
            'acoustid_api_key': 'settingAcoustidKey',
            'default_convert_audio': 'settingDefaultConvertAudio',
            'audio_format': 'settingAudioFormat',
            'mp3_bitrate': 'settingMp3Bitrate',
            'opus_bitrate': 'settingOpusBitrate',
            'alac_bitrate': 'settingAlacBitrate',
            'convert_lossless_only': 'settingConvertLosslessOnly',
            'normalise_lossy_audio': 'settingNormaliseLossyAudio',
            'enable_replaygain': 'settingEnableReplaygain',
            'replaygain_replace_existing': 'settingReplaygainReplaceExisting',
            'min_audio_bitrate': 'settingMinBitrate',
            'reject_live_versions': 'settingRejectLiveVersions',
            'reject_version_keywords': 'settingRejectVersionKeywords',
            'playlist_comment_tagging': 'settingPlaylistCommentTagging',
            'redownload_missing_files': 'settingRedownloadMissingFiles',
            'enable_track_upgrades': 'settingEnableTrackUpgrades',
            'upgrade_scan_interval_hours': 'settingUpgradeScanInterval',
            'singles_subdir': 'settingSinglesSubdir',
            'playlists_subdir': 'settingPlaylistsSubdir',
            'albums_subdir': 'settingAlbumsSubdir',
            'auto_import_dir': 'settingAutoImportDir',
            'organise_by_artist': 'settingOrganiseByArtist',
            'include_track_number_in_filename': 'settingIncludeTrackNumberInFilename',
            'auto_album_singles': 'settingAutoAlbumSingles',
            'album_folder_year': 'settingAlbumFolderYear',
            'playlist_album_as_name': 'settingPlaylistAlbumAsName',
            'singles_only_mode': 'settingSinglesOnlyMode',
            'album_tracks_from_library': 'settingAlbumTracksFromLibrary',
            'source_youtube_enabled': 'settingSourceYoutube',
            'source_soundcloud_enabled': 'settingSourceSoundcloud',
            'soundcloud_device_file': 'settingSoundcloudDeviceFile',
            'source_zvu4no_enabled': 'settingSourceZvu4no',
            'source_freemp3cloud_enabled': 'settingSourceFreemp3cloud',
            'source_jiosaavn_enabled': 'settingSourceJiosaavn',
            'source_soulseek_enabled': 'settingSourceSoulseek',
            'source_monochrome_enabled': 'settingSourceMonochrome',
            'source_zarz_enabled': 'settingSourceZarz',
            'source_prowlarr_enabled': 'settingSourceProwlarr',
            'source_torrents_enabled': 'settingSourceTorrents',
            'source_offline_fallback': 'settingSourceOfflineFallback',
            'youtube_requested_video_fallback': 'settingYoutubeRequestedVideoFallback',
            'source_health_checks_enabled': 'settingSourceHealthChecks',
            'source_health_check_interval_minutes': 'settingSourceHealthInterval',
            'source_health_cooldown_minutes': 'settingSourceHealthCooldown',
            'search_concurrency': 'settingSearchConcurrency',
            'slskd_url': 'settingSlskdUrl',
            'slskd_user': 'settingSlskdUser',
            'slskd_pass': 'settingSlskdPass',
            'slskd_downloads_path': 'settingSlskdDownloads',
            'slskd_move_completed': 'settingSlskdMoveCompleted',
            'prowlarr_url': 'settingProwlarrUrl',
            'prowlarr_api_key': 'settingProwlarrApiKey',
            'sabnzbd_url': 'settingSabnzbdUrl',
            'sabnzbd_api_key': 'settingSabnzbdApiKey',
            'sabnzbd_downloads_path': 'settingSabnzbdDownloads',
            'qbittorrent_url': 'settingQbittorrentUrl',
            'qbittorrent_username': 'settingQbittorrentUser',
            'qbittorrent_password': 'settingQbittorrentPass',
            'qbittorrent_downloads_path': 'settingQbittorrentDownloads',
            'navidrome_url': 'settingNavidromeUrl',
            'navidrome_user': 'settingNavidromeUser',
            'navidrome_pass': 'settingNavidromePass',
            'jellyfin_url': 'settingJellyfinUrl',
            'jellyfin_api_key': 'settingJellyfinApiKey',
            'plex_url': 'settingPlexUrl',
            'plex_token': 'settingPlexToken',
            'lidarr_url': 'settingLidarrUrl',
            'lidarr_api_key': 'settingLidarrApiKey',
            'notify_on': 'settingNotifyOn',
            'telegram_webhook_url': 'settingTelegramUrl',
            'webhook_url': 'settingWebhookUrl',
            'apprise_url': 'settingAppriseUrl',
            'smtp_host': 'settingSmtpHost',
            'smtp_port': 'settingSmtpPort',
            'smtp_user': 'settingSmtpUser',
            'smtp_pass': 'settingSmtpPass',
            'smtp_from': 'settingSmtpFrom',
            'smtp_to': 'settingSmtpTo',
            'smtp_tls': 'settingSmtpTls',
            'youtube_cookies': 'settingYoutubeCookies',
            'spotify_cookies': 'settingSpotifyCookies',
            'apple_music_user_token': 'settingAppleMusicUserToken',
            'spotify_browser_timeout_seconds': 'settingSpotifyBrowserTimeout',
            'spotify_browser_stall_seconds': 'settingSpotifyBrowserStall',
            'file_permissions': 'settingFilePermissions',
            'api_key': 'settingApiKey'
        };

        // Track which fields are locked by env vars
        let envOverrides = [];
        let sensitiveFields = [];
        let settingsLoaded = false;
        let originalValues = {}; // Track original values to detect changes

        async function loadSettings() {
            if (settingsLoaded) return; // Only load once per session

            try {
                const response = await apiFetch('/api/settings');
                if (!response.ok) throw new Error('Failed to load settings');

                const data = await response.json();
                const settings = data.settings;
                envOverrides = data.env_overrides || [];
                sensitiveFields = data.sensitive_fields || [];

                // Populate form fields and track original values
                for (const [key, elementId] of Object.entries(settingsFieldMap)) {
                    const element = document.getElementById(elementId);
                    if (!element) continue;

                    const value = settings[key];
                    const isLocked = envOverrides.includes(key);

                    // Store original value for change detection
                    if (!element.dataset.defaultPlaceholder) {
                        element.dataset.defaultPlaceholder = element.placeholder || '';
                    }

                    if (element.type === 'checkbox') {
                        originalValues[key] = value === true || value === 'true';
                    } else if (sensitiveFields.includes(key) && value === '••••••••') {
                        originalValues[key] = null; // Indicates "configured but hidden"
                    } else {
                        // As the field will read it back: a string, so a saved 96
                        // and the box's "96" agree, and Save stops resending it.
                        originalValues[key] = String(value || '');
                    }

                    if (element.type === 'checkbox') {
                        element.checked = value === true || value === 'true';
                    } else {
                        // For sensitive fields, only show placeholder if value is masked
                        if (sensitiveFields.includes(key) && value === '••••••••') {
                            element.placeholder = 'Configured (hidden)';
                            element.value = '';
                        } else {
                            element.value = value || '';
                        }
                        // Sync format and quality picker buttons when their settings load
                        if (key === 'audio_format') setAudioFormat(value);
                        if (key === 'mp3_bitrate')  setMp3Bitrate(value);
                        if (key === 'opus_bitrate') setOpusBitrate(value);
                        if (key === 'alac_bitrate') setAlacBitrate(value);
                    }

                    // Mark fields locked by env vars
                    if (isLocked) {
                        element.disabled = true;
                        const row = element.closest('.settings-row') || element.closest('.settings-label');
                        if (row) {
                            row.classList.add('env-locked');
                            row.title = 'Set via environment variable (e.g., docker-compose.yml)';
                        }
                    }
                }

                // The conversion-mode buttons are the visible control for the
                // hidden persisted checkbox.
                setDefaultConversionMode(document.getElementById('settingDefaultConvertAudio').checked);

                settingsLoaded = true;

                // Sync notify_on checkboxes from the hidden field value
                _syncNotifyOnCheckboxes();

                // Populate singles subfolder dropdown from actual directories
                await _populateSubdirDropdown(settings['singles_subdir'] || 'Singles');
                // Populate playlists subfolder dropdown
                await _populatePlaylistsSubdirDropdown(settings['playlists_subdir'] || '');
                // Populate albums subfolder dropdown
                await _populateAlbumsSubdirDropdown(settings['albums_subdir'] || 'Albums');

                // Live path preview: update whenever filename layout toggles change
                const organiseToggle = document.getElementById('settingOrganiseByArtist');
                if (organiseToggle) organiseToggle.onchange = _updatePathPreviews;
                const trackNumberToggle = document.getElementById('settingIncludeTrackNumberInFilename');
                if (trackNumberToggle) trackNumberToggle.onchange = _updatePathPreviews;

                // Update browser API key status
                updateBrowserApiKeyStatus();

                // Inject clear buttons into settings rows
                _injectSettingsClearButtons();

                // Show cookie expiry status if cookies are configured
                _updateCookieExpiryHint();
                _updateSpotifyCookieHint(settings);
                await loadMaintenancePreview();
            } catch (error) {
                console.error('Failed to load settings:', error);
                showToast('Failed to load settings', true);
            }
        }

        async function loadMaintenancePreview() {
            const preview = document.getElementById('maintenancePreview');
            if (!preview || !isAdmin()) return;
            try {
                const response = await apiFetch('/api/settings/maintenance');
                if (!response.ok) throw new Error('Preview failed');
                const data = await response.json();
                const history = data.queue_history || {};
                preview.textContent = `${data.orphan_imports || 0} orphan import(s); `
                    + `${history.completed || 0} completed, ${history.completed_with_errors || 0} completed with issues, `
                    + `${history.failed || 0} failed, ${history.cancelled || 0} cancelled Queue row(s); `
                    + `${data.indexed_paths || 0} exact library path(s) indexed.`;
            } catch (error) {
                preview.textContent = 'Could not load the maintenance preview.';
            }
        }

        async function _postMaintenance(payload, confirmation) {
            if (!confirm(confirmation + ' Library audio will not be deleted or moved.')) return;
            const result = document.getElementById('maintenanceResult');
            if (result) result.textContent = 'Working...';
            try {
                const response = await apiFetch('/api/settings/maintenance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ...payload, confirm: true })
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || 'Maintenance failed');
                if (result) result.textContent = Object.entries(data)
                    .map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}`)
                    .join('; ');
                showToast('Maintenance complete');
                await loadMaintenancePreview();
                loadJobs();
            } catch (error) {
                if (result) {
                    result.textContent = error.message || 'Maintenance failed';
                    result.classList.add('error');
                }
                showToast(error.message || 'Maintenance failed', true);
            }
        }

        function runMaintenanceAction(action) {
            const labels = {
                purge_orphans: 'Remove imports whose watched playlist or artist no longer exists?',
                reconcile: 'Check indexed files and mark missing ones as deleted in Queue history?',
                clean_rebuild: 'Remove orphan imports, reconcile missing files, and index untracked audio beneath configured library folders?'
            };
            return _postMaintenance({ action }, labels[action] || 'Run maintenance?');
        }

        function clearSelectedQueueHistory() {
            const statuses = Array.from(document.querySelectorAll('.maintenance-history input:checked'))
                .map(input => input.value);
            if (!statuses.length) {
                showToast('Select at least one Queue history type', true);
                return;
            }
            return _postMaintenance(
                { action: 'clear_history', statuses },
                `Permanently remove ${statuses.length} selected Queue history type(s) from the database?`
            );
        }

        const SUBDIR_CUSTOM_VALUE = '__custom__';

        function _normaliseSubdirPath(rawValue) {
            const raw = String(rawValue || '').trim();
            if (!raw) return '';
            if (raw === '.') return '.';

            const parts = raw
                .replace(/\\/g, '/')
                .split('/')
                .map(part => part.trim())
                .filter(part => part && part !== '.');

            if (parts.some(part => part === '..')) return '';
            return parts.join('/');
        }

        async function _populateSubdirDropdown(currentValue) {
            const select = document.getElementById('settingSinglesSubdir');
            const customRow = document.getElementById('customSubdirRow');
            const customInput = document.getElementById('customSubdirInput');
            if (!select || !customRow || !customInput) return;

            const currentRaw = (currentValue || 'Singles').trim();
            const current = currentRaw === '.' ? '.' : (_normaliseSubdirPath(currentRaw) || 'Singles');

            let dirs = [];
            try {
                const resp = await apiFetch('/api/music-dirs?recursive=true&max_depth=2');
                if (resp.ok) {
                    const data = await resp.json();
                    dirs = Array.isArray(data.directories) ? data.directories : [];
                }
            } catch (e) {
                console.warn('Could not fetch music directories:', e);
            }

            const unique = new Set();
            for (const dir of dirs) {
                const normalised = _normaliseSubdirPath(dir);
                if (normalised && normalised !== '.') {
                    unique.add(normalised);
                }
            }

            // Keep defaults/current value available even if folder disappeared.
            unique.add('Singles');
            if (current !== '.') {
                unique.add(current);
            }

            const sortedDirs = Array.from(unique).sort((a, b) =>
                a.localeCompare(b, undefined, { sensitivity: 'base' })
            );

            select.innerHTML = '';

            const musicRoot = (serverConfig && serverConfig.music_dir) ? serverConfig.music_dir.replace(/\/+$/, '') : '/music';

            const rootOpt = document.createElement('option');
            rootOpt.value = '.';
            rootOpt.textContent = `${musicRoot} (root)`;
            select.appendChild(rootOpt);

            for (const relPath of sortedDirs) {
                const opt = document.createElement('option');
                opt.value = relPath;
                opt.textContent = `${musicRoot}/${relPath}`;
                select.appendChild(opt);
            }

            const customOpt = document.createElement('option');
            customOpt.value = SUBDIR_CUSTOM_VALUE;
            customOpt.textContent = 'Custom path\u2026';
            select.appendChild(customOpt);

            const currentIsKnown = current === '.' || sortedDirs.includes(current);
            customInput.disabled = !!select.disabled;
            if (currentIsKnown) {
                select.value = current;
                customRow.style.display = 'none';
                customInput.value = '';
            } else {
                select.value = SUBDIR_CUSTOM_VALUE;
                customRow.style.display = 'block';
                customInput.value = current;
            }

            select.onchange = () => {
                if (select.value === SUBDIR_CUSTOM_VALUE) {
                    customRow.style.display = 'block';
                    customInput.focus();
                    _updatePathPreviews();
                    return;
                }
                customRow.style.display = 'none';
                customInput.value = '';
                _updatePathPreviews();
            };
            customInput.oninput = _updatePathPreviews;
            _updatePathPreviews();
        }

        async function _populatePlaylistsSubdirDropdown(currentValue) {
            const select = document.getElementById('settingPlaylistsSubdir');
            const customRow = document.getElementById('customPlaylistsSubdirRow');
            const customInput = document.getElementById('customPlaylistsSubdirInput');
            if (!select || !customRow || !customInput) return;

            const currentRaw = String(currentValue || '').trim();
            const current = currentRaw === '.' ? '.' : (_normaliseSubdirPath(currentRaw) || '');

            let dirs = [];
            try {
                const resp = await apiFetch('/api/music-dirs?recursive=true&max_depth=2');
                if (resp.ok) {
                    const data = await resp.json();
                    dirs = Array.isArray(data.directories) ? data.directories : [];
                }
            } catch (e) {
                console.warn('Could not fetch music directories:', e);
            }

            const unique = new Set();
            for (const dir of dirs) {
                const normalised = _normaliseSubdirPath(dir);
                if (normalised && normalised !== '.') {
                    unique.add(normalised);
                }
            }

            // Always include "Playlists" as a sensible default option
            unique.add('Playlists');
            if (current && current !== '.') {
                unique.add(current);
            }

            const sortedDirs = Array.from(unique).sort((a, b) =>
                a.localeCompare(b, undefined, { sensitivity: 'base' })
            );

            select.innerHTML = '';

            // First option: disabled (feature off)
            const disabledOpt = document.createElement('option');
            disabledOpt.value = '';
            disabledOpt.textContent = '(disabled)';
            select.appendChild(disabledOpt);

            const musicRoot = (serverConfig && serverConfig.music_dir) ? serverConfig.music_dir.replace(/\/+$/, '') : '/music';

            // Second option: musicRoot/Playlists as the obvious default
            const playlistsOpt = document.createElement('option');
            playlistsOpt.value = 'Playlists';
            playlistsOpt.textContent = `${musicRoot}/Playlists`;
            select.appendChild(playlistsOpt);

            const rootOpt = document.createElement('option');
            rootOpt.value = '.';
            rootOpt.textContent = `${musicRoot} (root)`;
            select.appendChild(rootOpt);

            for (const relPath of sortedDirs.filter(d => d !== 'Playlists')) {
                const opt = document.createElement('option');
                opt.value = relPath;
                opt.textContent = `${musicRoot}/${relPath}`;
                select.appendChild(opt);
            }

            const customOpt = document.createElement('option');
            customOpt.value = SUBDIR_CUSTOM_VALUE;
            customOpt.textContent = 'Custom path\u2026';
            select.appendChild(customOpt);

            const currentIsKnown = !current || current === '.' || sortedDirs.includes(current);
            customInput.disabled = !!select.disabled;
            if (currentIsKnown) {
                select.value = current;
                customRow.style.display = 'none';
                customInput.value = '';
            } else {
                select.value = SUBDIR_CUSTOM_VALUE;
                customRow.style.display = 'block';
                customInput.value = current;
            }

            select.onchange = () => {
                if (select.value === SUBDIR_CUSTOM_VALUE) {
                    customRow.style.display = 'block';
                    customInput.focus();
                    _updatePathPreviews();
                    return;
                }
                customRow.style.display = 'none';
                customInput.value = '';
                _updatePathPreviews();
            };
            customInput.oninput = _updatePathPreviews;
            _updatePathPreviews();
        }

        async function _populateAlbumsSubdirDropdown(currentValue) {
            const select = document.getElementById('settingAlbumsSubdir');
            const customRow = document.getElementById('customAlbumsSubdirRow');
            const customInput = document.getElementById('customAlbumsSubdirInput');
            if (!select || !customRow || !customInput) return;

            const currentRaw = String(currentValue || 'Albums').trim();
            const current = currentRaw === '.' ? '.' : (_normaliseSubdirPath(currentRaw) || 'Albums');

            let dirs = [];
            try {
                const resp = await apiFetch('/api/music-dirs?recursive=true&max_depth=2');
                if (resp.ok) {
                    const data = await resp.json();
                    dirs = Array.isArray(data.directories) ? data.directories : [];
                }
            } catch (e) {
                console.warn('Could not fetch music directories:', e);
            }

            const unique = new Set();
            for (const dir of dirs) {
                const normalised = _normaliseSubdirPath(dir);
                if (normalised && normalised !== '.') unique.add(normalised);
            }
            unique.add('Albums');
            if (current && current !== '.') unique.add(current);

            const sortedDirs = Array.from(unique).sort((a, b) =>
                a.localeCompare(b, undefined, { sensitivity: 'base' })
            );

            select.innerHTML = '';

            const musicRoot = (serverConfig && serverConfig.music_dir) ? serverConfig.music_dir.replace(/\/+$/, '') : '/music';

            const rootOpt = document.createElement('option');
            rootOpt.value = '.';
            rootOpt.textContent = `${musicRoot} (root)`;
            select.appendChild(rootOpt);

            for (const relPath of sortedDirs) {
                const opt = document.createElement('option');
                opt.value = relPath;
                opt.textContent = `${musicRoot}/${relPath}`;
                select.appendChild(opt);
            }

            const customOpt = document.createElement('option');
            customOpt.value = SUBDIR_CUSTOM_VALUE;
            customOpt.textContent = 'Custom path\u2026';
            select.appendChild(customOpt);

            const currentIsKnown = current === '.' || sortedDirs.includes(current);
            customInput.disabled = !!select.disabled;
            if (currentIsKnown) {
                select.value = current;
                customRow.style.display = 'none';
                customInput.value = '';
            } else {
                select.value = SUBDIR_CUSTOM_VALUE;
                customRow.style.display = 'block';
                customInput.value = current;
            }

            select.onchange = () => {
                if (select.value === SUBDIR_CUSTOM_VALUE) {
                    customRow.style.display = 'block';
                    customInput.focus();
                    _updatePathPreviews();
                    return;
                }
                customRow.style.display = 'none';
                customInput.value = '';
                _updatePathPreviews();
            };
            customInput.oninput = _updatePathPreviews;
            _updatePathPreviews();
        }

        async function _updateCookieExpiryHint() {
            const hint = document.getElementById('cookieExpiryHint');
            if (!hint) return;
            try {
                const resp = await apiFetch('/api/settings/youtube-cookies/status');
                if (!resp.ok) return;
                const data = await resp.json();
                if (!data.has_setting || !data.auth_cookie_expiry) {
                    hint.style.display = 'none';
                    return;
                }
                const expiryMs = data.auth_cookie_expiry * 1000;
                const now = Date.now();
                const daysLeft = Math.floor((expiryMs - now) / 86400000);
                const expiryDate = new Date(expiryMs).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });

                hint.style.display = 'block';
                if (now > expiryMs) {
                    hint.style.color = 'var(--error-color, #e53e3e)';
                    hint.textContent = `Cookies expired on ${expiryDate} - re-export them`;
                } else if (daysLeft <= 7) {
                    hint.style.color = 'var(--warning-color, #d97706)';
                    hint.textContent = `Cookies expire in ${daysLeft} day${daysLeft !== 1 ? 's' : ''} (${expiryDate}) - consider re-exporting soon`;
                } else {
                    hint.style.color = 'var(--text-secondary)';
                    hint.textContent = `Cookies valid until ${expiryDate}`;
                }
            } catch (e) {
                // Status fetch failing is not the end of the world
            }
        }

        function _updateSpotifyCookieHint(settings) {
            const banner = document.getElementById('spotifyCookiesExpiredBanner');
            const hint = document.getElementById('spotifyCookieExpiryHint');

            // Show expired banner when the flag is set and cookies are still present
            if (banner) {
                const expired = settings && settings['spotify_cookies_expired'] === true;
                const hasCookies = settings && settings['spotify_cookies'];
                banner.style.display = (expired && hasCookies) ? 'block' : 'none';
            }

            // Expiry hint: parse sp_dc expiry from the Netscape cookie text
            if (!hint) return;
            const cookiesText = settings && settings['spotify_cookies'];
            if (!cookiesText) {
                hint.style.display = 'none';
                return;
            }
            // Find sp_dc expiry from cookie lines
            let spDcExpiry = null;
            for (const line of cookiesText.split('\n')) {
                const l = line.trim();
                if (!l || l.startsWith('#')) continue;
                const parts = l.split('\t');
                if (parts.length >= 7 && parts[5] === 'sp_dc') {
                    const exp = parseInt(parts[4], 10);
                    if (exp > 0) spDcExpiry = exp;
                    break;
                }
            }
            if (!spDcExpiry) {
                hint.style.display = 'none';
                return;
            }
            const now = Date.now();
            const expiryMs = spDcExpiry * 1000;
            const daysLeft = Math.floor((expiryMs - now) / 86400000);
            const expiryDate = new Date(expiryMs).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
            hint.style.display = 'block';
            if (now > expiryMs) {
                hint.style.color = 'var(--error-color, #e53e3e)';
                hint.textContent = `sp_dc expired on ${expiryDate} - re-export cookies`;
            } else if (daysLeft <= 30) {
                hint.style.color = 'var(--warning-color, #d97706)';
                hint.textContent = `sp_dc expires in ${daysLeft} day${daysLeft !== 1 ? 's' : ''} (${expiryDate})`;
            } else {
                hint.style.color = 'var(--text-secondary)';
                hint.textContent = `sp_dc valid until ${expiryDate}`;
            }
        }

        function _updatePathPreviews() {
            const singlesEl = document.getElementById('singlesPathPreview');
            const playlistsEl = document.getElementById('playlistsPathPreview');
            const albumsEl = document.getElementById('albumsPathPreview');
            if (!singlesEl && !playlistsEl && !albumsEl) return;

            const singlesSelect = document.getElementById('settingSinglesSubdir');
            const singlesCustom = document.getElementById('customSubdirInput');
            const playlistsSelect = document.getElementById('settingPlaylistsSubdir');
            const playlistsCustom = document.getElementById('customPlaylistsSubdirInput');
            const albumsSelect = document.getElementById('settingAlbumsSubdir');
            const albumsCustom = document.getElementById('customAlbumsSubdirInput');
            const organiseToggle = document.getElementById('settingOrganiseByArtist');
            const trackNumberToggle = document.getElementById('settingIncludeTrackNumberInFilename');

            const singlesVal = singlesSelect && singlesSelect.value === SUBDIR_CUSTOM_VALUE
                ? (singlesCustom ? singlesCustom.value.trim() : '')
                : (singlesSelect ? singlesSelect.value : '');
            const playlistsVal = playlistsSelect && playlistsSelect.value === SUBDIR_CUSTOM_VALUE
                ? (playlistsCustom ? playlistsCustom.value.trim() : '')
                : (playlistsSelect ? playlistsSelect.value : '');
            const organise = organiseToggle ? organiseToggle.checked : true;
            const includeTrackNumber = trackNumberToggle ? trackNumberToggle.checked : false;
            const titleExample = includeTrackNumber ? '01 - Track Title.flac' : 'Track Title.flac';
            const flatTitleExample = includeTrackNumber ? 'Artist Name - 01 - Track Title.flac' : 'Artist Name - Track Title.flac';

            const musicRoot = (serverConfig && serverConfig.music_dir) ? serverConfig.music_dir.replace(/\/+$/, '') : '/music';

            if (singlesEl) {
                let p = musicRoot;
                if (singlesVal && singlesVal !== '.') p += '/' + singlesVal;
                if (organise) {
                    p += '/Artist Name/' + titleExample;
                } else {
                    p += '/' + flatTitleExample;
                }
                singlesEl.textContent = 'Files saved to: ' + p;
            }

            if (playlistsEl) {
                if (!playlistsVal || playlistsVal === '') {
                    playlistsEl.textContent = '(playlist tracks go to Singles folder)';
                } else {
                    let p = musicRoot;
                    if (playlistsVal !== '.') p += '/' + playlistsVal;
                    p += '/Playlist Name/' + (includeTrackNumber ? 'Artist - 01 - Title.flac' : 'Artist - Title.flac');
                    playlistsEl.textContent = 'Files saved to: ' + p;
                }
            }

            const albumsVal = albumsSelect && albumsSelect.value === SUBDIR_CUSTOM_VALUE
                ? (albumsCustom ? albumsCustom.value.trim() : '')
                : (albumsSelect ? albumsSelect.value : '');
            if (albumsEl) {
                let p = musicRoot;
                if (albumsVal && albumsVal !== '.') p += '/' + albumsVal;
                p += '/Artist/Album/' + (includeTrackNumber ? '01 - Track.flac' : 'Track.flac');
                albumsEl.textContent = 'Files saved to: ' + p;
            }
        }

        function _injectSettingsClearButtons() {
            // Skip these - they already have dedicated clear mechanisms
            const skipIds = new Set([
                'settingYoutubeCookies', 'settingSpotifyCookies', 'settingSmtpPort', 'settingMinBitrate',
                'settingSpotifyBrowserTimeout', 'settingSpotifyBrowserStall',
                'customSubdirInput', 'customPlaylistsSubdirInput', 'customAlbumsSubdirInput'
            ]);

            for (const row of document.querySelectorAll('.settings-row')) {
                const input = row.querySelector('input[type="text"], input[type="password"], input[type="number"]');
                if (!input || skipIds.has(input.id)) continue;
                if (input.disabled) continue; // env-locked

                const clearBtn = document.createElement('button');
                clearBtn.type = 'button';
                clearBtn.className = 'btn btn-sm btn-danger setting-clear-btn';
                clearBtn.textContent = 'Clear';

                // Find the settings key for this input
                const settingsKey = Object.entries(settingsFieldMap).find(([, id]) => id === input.id)?.[0];

                clearBtn.addEventListener('click', async () => {
                    input.value = '';
                    if (settingsKey && sensitiveFields.includes(settingsKey)) {
                        input.dataset.forceClear = 'true';
                        input.placeholder = input.defaultValue || '';
                    }
                    await saveSettings();
                });

                // Wrap input (or password-field div) and clear button together
                const passwordField = row.querySelector('.password-field');
                const target = passwordField || input;

                const wrapper = document.createElement('div');
                wrapper.className = 'setting-input-group';
                target.parentNode.insertBefore(wrapper, target);
                wrapper.appendChild(target);
                wrapper.appendChild(clearBtn);
            }
        }

        function updateBrowserApiKeyStatus() {
            // In session mode the browser API key row isn't really relevant, but we keep
            // the element around for backward compatibility. Show a polite "N/A" message.
            const statusEl = document.getElementById('browserApiKeyStatus');
            const clearBtn = document.getElementById('clearApiKeyBtn');
            if (!statusEl) return;

            if (serverConfig && serverConfig.users_exist) {
                const user = getCurrentUser();
                statusEl.textContent = user ? `Signed in as ${user.username}` : 'Session mode';
                statusEl.style.color = 'var(--text-secondary)';
                if (clearBtn) clearBtn.style.display = 'none';
            } else {
                // Legacy single-user API key mode
                const storedKey = localStorage.getItem('apiKey') || '';
                if (storedKey) {
                    statusEl.textContent = `Key stored (${storedKey.length} chars)`;
                    statusEl.style.color = 'var(--success)';
                    if (clearBtn) clearBtn.style.display = 'inline-block';
                } else {
                    statusEl.textContent = 'No key stored';
                    statusEl.style.color = 'var(--text-secondary)';
                    if (clearBtn) clearBtn.style.display = 'none';
                }
            }
        }

        // Clear stored (legacy) API key button
        document.getElementById('clearApiKeyBtn')?.addEventListener('click', () => {
            localStorage.removeItem('apiKey');
            updateBrowserApiKeyStatus();
            showToast('Stored API key cleared');
        });

        function _syncNotifyOnCheckboxes() {
            const val = document.getElementById('settingNotifyOn')?.value || '';
            const parts = val.split(',').map(s => s.trim());
            document.getElementById('settingNotifyOnSingles').checked  = parts.includes('singles');
            document.getElementById('settingNotifyOnPlaylists').checked = parts.includes('playlists');
            document.getElementById('settingNotifyOnBulk').checked     = parts.includes('bulk');
            document.getElementById('settingNotifyOnErrors').checked   = parts.includes('errors');
        }

        function _syncNotifyOnHidden() {
            const parts = [];
            if (document.getElementById('settingNotifyOnSingles').checked)  parts.push('singles');
            if (document.getElementById('settingNotifyOnPlaylists').checked) parts.push('playlists');
            if (document.getElementById('settingNotifyOnBulk').checked)     parts.push('bulk');
            if (document.getElementById('settingNotifyOnErrors').checked)   parts.push('errors');
            document.getElementById('settingNotifyOn').value = parts.join(',');
        }

        async function saveSettings() {
            const saveBtn = document.getElementById('saveSettingsBtn');
            const resultDiv = document.getElementById('settingsSaveResult');

            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
            resultDiv.textContent = '';
            resultDiv.classList.remove('error');

            // Build the hidden notify_on value from checkboxes before reading it
            _syncNotifyOnHidden();

            try {
                const updates = {};

                for (const [key, elementId] of Object.entries(settingsFieldMap)) {
                    // Skip env-locked fields
                    if (envOverrides.includes(key)) continue;

                    const element = document.getElementById(elementId);
                    if (!element) continue;

                    if (element.type === 'checkbox') {
                        const currentValue = element.checked;
                        // Only include if changed from original
                        if (currentValue !== originalValues[key]) {
                            updates[key] = currentValue;
                        }
                    } else {
                        let value = element.value.trim();
                        // Singles subfolder: use direct picker value or custom path
                        if (key === 'singles_subdir') {
                            if (value === '.') {
                                value = '.';
                            } else if (value === SUBDIR_CUSTOM_VALUE) {
                                const customInput = document.getElementById('customSubdirInput');
                                value = _normaliseSubdirPath(customInput?.value || '') || 'Singles';
                            } else {
                                value = _normaliseSubdirPath(value) || 'Singles';
                            }
                            updates[key] = value;
                            continue;
                        }
                        // Playlists subfolder: same pattern, empty string = disabled
                        if (key === 'playlists_subdir') {
                            if (value === '' || value === '.') {
                                // keep as-is (empty = disabled, '.' = root)
                            } else if (value === SUBDIR_CUSTOM_VALUE) {
                                const customInput = document.getElementById('customPlaylistsSubdirInput');
                                value = _normaliseSubdirPath(customInput?.value || '') || 'Playlists';
                            } else {
                                value = _normaliseSubdirPath(value);
                            }
                            updates[key] = value;
                            continue;
                        }
                        // Albums subfolder: always enabled, defaults to 'Albums'
                        if (key === 'albums_subdir') {
                            if (value === '.') {
                                value = '.';
                            } else if (value === SUBDIR_CUSTOM_VALUE) {
                                const customInput = document.getElementById('customAlbumsSubdirInput');
                                value = _normaliseSubdirPath(customInput?.value || '') || 'Albums';
                            } else {
                                value = _normaliseSubdirPath(value) || 'Albums';
                            }
                            // Always include subdir fields; change detection fails when the
                            // saved value is itself a custom path (originalValues holds the
                            // resolved string, resolved value matches, gets skipped as "no change")
                            updates[key] = value;
                            continue;
                        }
                        // For sensitive fields with hidden values (null), only send if user entered something
                        if (sensitiveFields.includes(key)) {
                            if (originalValues[key] === null) {
                                // Field was "configured (hidden)" - only send if user typed something new
                                if (value && value !== '') {
                                    updates[key] = value;
                                } else if (element.dataset.forceClear === 'true') {
                                    updates[key] = '';
                                }
                            } else if (value !== originalValues[key]) {
                                // Field had visible value - send if changed (including to empty)
                                updates[key] = value;
                            }
                        } else {
                            // Non-sensitive field - only send if changed from original
                            if (value !== originalValues[key]) {
                                updates[key] = value;
                            }
                        }
                    }
                }

                // Don't make API call if nothing changed
                if (Object.keys(updates).length === 0) {
                    resultDiv.textContent = 'No changes to save';
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Save Settings';
                    return;
                }

                const response = await apiFetch('/api/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updates)
                });

                if (!response.ok) throw new Error('Failed to save settings');

                const data = await response.json();
                resultDiv.textContent = `Saved ${data.updated.length} setting(s)`;
                showToast('Settings saved');

                // Refresh Spotify cookie status (expired banner + expiry hint)
                if (data.settings) _updateSpotifyCookieHint(data.settings);

                // Update original values and clear sensitive fields after save
                for (const [key, value] of Object.entries(updates)) {
                    if (sensitiveFields.includes(key)) {
                        const elementId = settingsFieldMap[key];
                        if (elementId) {
                            const element = document.getElementById(elementId);
                            if (element && element.type !== 'checkbox') {
                                if (value === '') {
                                    originalValues[key] = '';
                                    element.value = '';
                                    element.placeholder = element.dataset.defaultPlaceholder || '';
                                } else {
                                    // Mark as "configured but hidden" and clear the field
                                    originalValues[key] = null;
                                    element.value = '';
                                    element.placeholder = 'Configured (hidden)';
                                }
                                element.dataset.forceClear = '';
                            }
                        }
                    } else {
                        // Update tracked original value
                        originalValues[key] = value;

                        // Sync header toggle when default_convert_audio is saved
                        if (key === 'default_convert_audio') {
                            convertAudioCheckbox.checked = value;
                            localStorage.setItem(userStorageKey('convertAudio'), value);
                            if (watchedConvertAudio && !watchedConversionTouched) {
                                watchedConvertAudio.checked = value;
                            }
                            setDefaultConversionMode(value);
                            updateConversionLabels();
                        }
                        // Sync format picker when audio_format is saved
                        if (key === 'audio_format') {
                            setAudioFormat(value);
                        }
                        // Sync playlists_subdir in serverConfig so watched/bulk-import UI updates
                        if (key === 'playlists_subdir') {
                            serverConfig.playlists_subdir = value;
                            const watchedToggle = document.getElementById('watchedPlaylistsDirToggle');
                            if (watchedToggle) watchedToggle.style.display = value ? 'flex' : 'none';
                            const watchedUsePlaylistsDir = document.getElementById('watchedUsePlaylistsDir');
                            if (watchedUsePlaylistsDir) watchedUsePlaylistsDir.checked = !!value;
                            const usePlaylistsDirCheckbox = document.getElementById('usePlaylistsDirCheckbox');
                            if (usePlaylistsDirCheckbox && value) usePlaylistsDirCheckbox.checked = true;
                        }
                    }
                }

                // Not awaited: Save is done, and the check reports when it is ready.
                checkSavedSettings(Object.keys(updates));
            } catch (error) {
                console.error('Failed to save settings:', error);
                resultDiv.textContent = 'Failed to save settings';
                resultDiv.classList.add('error');
                showToast('Failed to save settings', true);
            } finally {
                saveBtn.disabled = false;
                saveBtn.textContent = 'Save Settings';
            }
        }

        // The result line beside a Test button, from the button or from Check my config.
        function showTestResult(service, resultDiv, data) {
            if (data.success) {
                resultDiv.textContent = data.message;
                resultDiv.className = data.warning ? 'test-result warning' : 'test-result success';
                // For Navidrome, show a second status line about real path support
                if (service === 'navidrome') {
                    const rpDiv = document.getElementById('navidromeRealPathStatus');
                    if (rpDiv) {
                        if (data.real_path === true) {
                            rpDiv.textContent = 'Real file paths enabled; M3U playlist entries will use accurate paths';
                            rpDiv.className = 'test-result success';
                        } else {
                            rpDiv.textContent = data.real_path_hint || '';
                            rpDiv.className = 'test-result warning';
                        }
                        rpDiv.style.display = 'block';
                    }
                }
            } else {
                resultDiv.textContent = data.message || 'Connection failed';
                resultDiv.className = 'test-result error';
            }
            resultDiv.style.display = 'block';
        }

        async function testConnection(service) {
            const idMap = {
                'youtube-cookies': { btn: 'testYoutubeCookiesBtn', result: 'youtubeCookiesTestResult', label: 'Test Cookies' },
                'spotify-cookies': { btn: 'testSpotifyCookiesBtn', result: 'spotifyCookiesTestResult', label: 'Test Cookies' },
                'apprise': { btn: 'testAppriseBtn', result: 'appriseTestResult', label: 'Test Apprise' },
                'prowlarr': { btn: 'testProwlarrBtn', result: 'prowlarrTestResult', label: 'Test Prowlarr' },
                'sabnzbd': { btn: 'testSabnzbdBtn', result: 'sabnzbdTestResult', label: 'Test SABnzbd' },
                'qbittorrent': { btn: 'testQbittorrentBtn', result: 'qbittorrentTestResult', label: 'Test qBittorrent' },
                'email': { btn: 'testEmailBtn', result: 'emailTestResult', label: 'Send Test Email' },
            };
            const ids = idMap[service] || { btn: `test${service.charAt(0).toUpperCase() + service.slice(1)}Btn`, result: `${service}TestResult`, label: 'Test Connection' };
            const btn = document.getElementById(ids.btn);
            const resultDiv = document.getElementById(ids.result);

            const btnLabel = ids.label;
            btn.disabled = true;
            btn.textContent = 'Testing...';
            resultDiv.className = 'test-result';
            resultDiv.style.display = 'none';
            // Reset Navidrome real-path status on each new test
            if (service === 'navidrome') {
                const rpDiv = document.getElementById('navidromeRealPathStatus');
                if (rpDiv) rpDiv.style.display = 'none';
            }

            // Gather current form values to test with (before saving)
            let body = {};
            if (service === 'slskd') {
                body = {
                    url: document.getElementById('settingSlskdUrl').value.trim(),
                    username: document.getElementById('settingSlskdUser').value.trim(),
                    password: document.getElementById('settingSlskdPass').value.trim(),
                    downloads_path: document.getElementById('settingSlskdDownloads').value.trim()
                };
            } else if (service === 'prowlarr') {
                body = {
                    url: document.getElementById('settingProwlarrUrl').value.trim(),
                    api_key: document.getElementById('settingProwlarrApiKey').value.trim()
                };
            } else if (service === 'sabnzbd') {
                body = {
                    url: document.getElementById('settingSabnzbdUrl').value.trim(),
                    api_key: document.getElementById('settingSabnzbdApiKey').value.trim(),
                    downloads_path: document.getElementById('settingSabnzbdDownloads').value.trim()
                };
            } else if (service === 'qbittorrent') {
                body = {
                    url: document.getElementById('settingQbittorrentUrl').value.trim(),
                    username: document.getElementById('settingQbittorrentUser').value.trim(),
                    password: document.getElementById('settingQbittorrentPass').value.trim(),
                    downloads_path: document.getElementById('settingQbittorrentDownloads').value.trim()
                };
            } else if (service === 'navidrome') {
                body = {
                    url: document.getElementById('settingNavidromeUrl').value.trim(),
                    username: document.getElementById('settingNavidromeUser').value.trim(),
                    password: document.getElementById('settingNavidromePass').value.trim()
                };
            } else if (service === 'jellyfin') {
                body = {
                    url: document.getElementById('settingJellyfinUrl').value.trim(),
                    api_key: document.getElementById('settingJellyfinApiKey').value.trim()
                };
            } else if (service === 'plex') {
                body = {
                    url: document.getElementById('settingPlexUrl').value.trim(),
                    token: document.getElementById('settingPlexToken').value.trim()
                };
            } else if (service === 'lidarr') {
                body = {
                    url: document.getElementById('settingLidarrUrl').value.trim(),
                    api_key: document.getElementById('settingLidarrApiKey').value.trim()
                };
            } else if (service === 'youtube-cookies') {
                body = {
                    cookies: document.getElementById('settingYoutubeCookies').value
                };
            } else if (service === 'spotify-cookies') {
                body = {
                    cookies: document.getElementById('settingSpotifyCookies').value
                };
            } else if (service === 'apprise') {
                body = {
                    url: document.getElementById('settingAppriseUrl').value.trim()
                };
            } else if (service === 'email') {
                body = {
                    smtp_host: document.getElementById('settingSmtpHost').value.trim(),
                    smtp_port: Number(document.getElementById('settingSmtpPort').value),
                    smtp_user: document.getElementById('settingSmtpUser').value.trim(),
                    smtp_from: document.getElementById('settingSmtpFrom').value.trim(),
                    smtp_to: document.getElementById('settingSmtpTo').value.trim(),
                    smtp_tls: document.getElementById('settingSmtpTls').checked
                };
                const smtpPassword = document.getElementById('settingSmtpPass').value;
                // A blank password field can mean "configured, but masked". Let
                // the server use the saved secret unless a replacement was typed.
                if (smtpPassword) body.smtp_pass = smtpPassword;
            }

            try {
                const response = await apiFetch(`/api/settings/test/${service}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                showTestResult(service, resultDiv, await response.json());
            } catch (error) {
                resultDiv.textContent = 'Connection test failed';
                resultDiv.className = 'test-result error';
                resultDiv.style.display = 'block';
            } finally {
                btn.disabled = false;
                btn.textContent = btnLabel;
            }
        }

        // The Monochrome test reports a whole ladder of legs rather than a single
        // yes/no, so it gets its own renderer instead of squeezing into testConnection.
        async function testSourceDownloads(sourceId, buttonId, resultId, stepsId) {
            const btn = document.getElementById(buttonId);
            const resultDiv = document.getElementById(resultId);
            const stepsDiv = document.getElementById(stepsId);

            btn.disabled = true;
            btn.textContent = 'Testing (this can take a minute)...';
            resultDiv.className = 'test-result';
            resultDiv.style.display = 'none';
            stepsDiv.hidden = true;
            stepsDiv.innerHTML = '';

            try {
                const response = await apiFetch(`/api/sources/${sourceId}/diagnostic`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}'
                });
                const data = await response.json();

                const steps = Array.isArray(data.steps) ? data.steps : [];
                const anyWarning = steps.some(step => step.status === 'warn');
                resultDiv.textContent = data.elapsed
                    ? `${data.message} (${data.elapsed}s)`
                    : (data.message || 'Test failed');
                resultDiv.className = data.success
                    ? (anyWarning ? 'test-result warning' : 'test-result success')
                    : 'test-result error';
                resultDiv.style.display = 'block';

                if (steps.length || data.hint) {
                    stepsDiv.innerHTML = '';
                    steps.forEach(step => {
                        const row = document.createElement('div');
                        row.className = `diag-step ${step.status || 'skip'}`;
                        const status = document.createElement('span');
                        status.className = 'diag-step-status';
                        status.textContent = step.status || '';
                        const body = document.createElement('div');
                        body.className = 'diag-step-body';
                        const name = document.createElement('span');
                        name.className = 'diag-step-name';
                        name.textContent = step.name || '';
                        body.appendChild(name);
                        if (step.detail) {
                            const detail = document.createElement('span');
                            detail.className = 'diag-step-detail';
                            detail.textContent = step.detail;
                            body.appendChild(detail);
                        }
                        row.appendChild(status);
                        row.appendChild(body);
                        stepsDiv.appendChild(row);
                    });
                    if (data.hint) {
                        const hint = document.createElement('div');
                        hint.className = 'diag-hint';
                        hint.textContent = `Likely cause: ${data.hint}`;
                        stepsDiv.appendChild(hint);
                    }
                    stepsDiv.hidden = false;
                }
            } catch (error) {
                resultDiv.textContent = 'Download test failed to run; check the server logs';
                resultDiv.className = 'test-result error';
                resultDiv.style.display = 'block';
            } finally {
                btn.disabled = false;
                btn.textContent = 'Test Downloads';
            }
        }

        // Password field toggle
        document.querySelectorAll('.password-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const targetId = btn.dataset.target;
                const input = document.getElementById(targetId);
                if (input) {
                    if (input.type === 'password') {
                        input.type = 'text';
                        btn.textContent = 'Hide';
                    } else {
                        input.type = 'password';
                        btn.textContent = 'Show';
                    }
                }
            });
        });

        // =============================================================================
        // Check my config
        // =============================================================================

        // Where each check belongs in the page: the line beside its Test button,
        // where it has one, and otherwise the setting to jump to.
        const CONFIG_CHECK_INLINE = {
            'slskd': 'slskdTestResult',
            'prowlarr': 'prowlarrTestResult',
            'sabnzbd': 'sabnzbdTestResult',
            'qbittorrent': 'qbittorrentTestResult',
            'navidrome': 'navidromeTestResult',
            'jellyfin': 'jellyfinTestResult',
            'plex': 'plexTestResult',
            'lidarr': 'lidarrTestResult',
            'youtube-cookies': 'youtubeCookiesTestResult',
            'spotify-cookies': 'spotifyCookiesTestResult',
            'apprise': 'appriseTestResult',
            'email': 'emailTestResult',
        };
        const CONFIG_CHECK_JUMP = {
            'folders': 'settingSinglesSubdir',
            'auto-import': 'settingAutoImportDir',
            'sources': 'settingSourceYoutube',
            'notify': 'settingNotifyOnSingles',
            'telegram': 'settingTelegramUrl',
            'webhook': 'settingWebhookUrl',
        };
        const CONFIG_CHECK_ICONS = { error: 'fa-circle-xmark', warn: 'fa-triangle-exclamation', ok: 'fa-circle-check' };

        // Whether the form differs from what is saved. The folder pickers are left
        // out: Save always sends them, so they would always look changed.
        function hasUnsavedSettings() {
            if (!settingsLoaded) return false;
            _syncNotifyOnHidden();
            return Object.entries(settingsFieldMap).some(([key, elementId]) => {
                if (envOverrides.includes(key) || key.endsWith('_subdir')) return false;
                const element = document.getElementById(elementId);
                if (!element) return false;
                if (element.type === 'checkbox') return element.checked !== originalValues[key];
                const value = element.value.trim();
                if (sensitiveFields.includes(key) && originalValues[key] === null) return value !== '';
                return value !== originalValues[key];
            });
        }

        // Shows a check beside its Test button, as the button would. False when
        // the check has no Test button to sit beside.
        function showConfigCheckInline(item) {
            const resultDiv = document.getElementById(CONFIG_CHECK_INLINE[item.id] || '');
            if (!resultDiv || item.status === 'off') return false;
            showTestResult(item.id, resultDiv, {
                success: item.status !== 'error',
                warning: item.status === 'warn',
                message: item.message,
                real_path: item.real_path,
                real_path_hint: item.real_path_hint,
            });
            return true;
        }

        function closeConfigCheck() {
            document.getElementById('configCheckPanel').hidden = true;
        }

        // Switch to the setting's pill, bring it into view and give it a nudge.
        function jumpToSetting(elementId) {
            const element = document.getElementById(elementId);
            if (!element) return;
            const mode = element.closest('.mode-panel')?.dataset.mode;
            const pill = mode && document.querySelector(`#settingsModePills .pill[data-value="${CSS.escape(mode)}"]`);
            if (pill && !pill.classList.contains('active')) pill.click();
            closeConfigCheck();
            requestAnimationFrame(() => {
                element.scrollIntoView({ behavior: 'smooth', block: 'center' });
                element.classList.remove('config-check-flash');
                void element.offsetWidth;
                element.classList.add('config-check-flash');
            });
        }

        function configCheckNote(text) {
            const note = document.createElement('div');
            note.className = 'config-check-note';
            note.textContent = text;
            return note;
        }

        function configCheckRow(item) {
            const row = document.createElement('div');
            row.className = `config-check-row ${item.status}`;
            const icon = document.createElement('i');
            icon.className = `fa-solid ${CONFIG_CHECK_ICONS[item.status]}`;
            const text = document.createElement('div');
            text.className = 'config-check-text';
            const label = document.createElement('strong');
            label.textContent = item.label;
            const message = document.createElement('span');
            message.textContent = item.real_path === false && item.real_path_hint
                ? `${item.message}. ${item.real_path_hint}`
                : item.message;
            text.append(label, message);
            row.append(icon, text);
            const target = CONFIG_CHECK_INLINE[item.id] || CONFIG_CHECK_JUMP[item.id];
            if (target && item.status !== 'ok') {
                const go = document.createElement('button');
                go.type = 'button';
                go.className = 'btn btn-ghost config-check-go';
                go.textContent = 'Go';
                go.addEventListener('click', () => jumpToSetting(target));
                row.append(go);
            }
            return row;
        }

        function renderConfigCheck(data, unsaved) {
            const order = { error: 0, warn: 1, ok: 2 };
            const shown = data.checks.filter(item => item.status in order)
                .sort((a, b) => order[a.status] - order[b.status]);
            const notSetUp = data.checks.filter(item => item.status === 'off').map(item => item.label);
            const count = (status) => shown.filter(item => item.status === status).length;
            const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
            const errors = count('error');
            const warnings = count('warn');
            const verdict = [errors && plural(errors, 'problem'), warnings && plural(warnings, 'warning')]
                .filter(Boolean).join(', ') || 'All good';

            const summary = document.getElementById('configCheckSummary');
            summary.textContent = `${verdict} · ${data.elapsed}s`;
            summary.className = `config-check-summary ${errors ? 'error' : warnings ? 'warn' : 'ok'}`;

            const list = document.getElementById('configCheckList');
            list.replaceChildren();
            if (unsaved) {
                list.append(configCheckNote('You have unsaved changes, so this checked what is saved. Save to check them too.'));
            }
            shown.forEach(item => list.append(configCheckRow(item)));
            if (notSetUp.length) list.append(configCheckNote(`Not set up: ${notSetUp.join(', ')}`));
        }

        async function runConfigCheck() {
            const btn = document.getElementById('checkConfigBtn');
            const summary = document.getElementById('configCheckSummary');
            const list = document.getElementById('configCheckList');
            const unsaved = hasUnsavedSettings();

            btn.disabled = true;
            summary.textContent = 'Checking...';
            summary.className = 'config-check-summary';
            list.replaceChildren(configCheckNote('Asking every saved connection whether it works. Cookies can take a few seconds.'));
            document.getElementById('configCheckPanel').hidden = false;

            try {
                const response = await apiFetch('/api/settings/check', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}'
                });
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                data.checks.forEach(showConfigCheckInline);
                renderConfigCheck(data, unsaved);
            } catch (error) {
                console.error('Config check failed:', error);
                summary.textContent = 'Check failed';
                summary.className = 'config-check-summary error';
                list.replaceChildren(configCheckNote('The check could not run. Try again, or look in the server logs.'));
            } finally {
                btn.disabled = false;
            }
        }

        // After a save, check whatever was just changed, beside its Test button.
        // The toast is for anything wrong, since it may be on another pill.
        async function checkSavedSettings(keys) {
            if (!keys.length || isPeon()) return;
            try {
                const response = await apiFetch('/api/settings/check', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ changed: keys })
                });
                if (!response.ok) return;
                const { checks } = await response.json();
                checks.forEach(showConfigCheckInline);
                const wrong = checks.filter(item => item.status === 'error' || item.status === 'warn');
                if (wrong.length === 1) {
                    showToast(`Saved, but ${wrong[0].label}: ${wrong[0].message}`, wrong[0].status === 'error');
                } else if (wrong.length) {
                    showToast(`Saved, but ${wrong.map(item => item.label).join(', ')} need a look. Check my config has the details.`,
                        wrong.some(item => item.status === 'error'));
                }
            } catch (error) {
                console.error('Post-save check failed:', error);
            }
        }

        // Settings event listeners
        document.getElementById('saveSettingsBtn').addEventListener('click', saveSettings);
        document.getElementById('checkConfigBtn').addEventListener('click', runConfigCheck);
        document.getElementById('configCheckClose').addEventListener('click', closeConfigCheck);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeConfigCheck();
        });
        document.getElementById('testSlskdBtn').addEventListener('click', () => testConnection('slskd'));
        document.getElementById('testProwlarrBtn').addEventListener('click', () => testConnection('prowlarr'));
        document.getElementById('testSabnzbdBtn').addEventListener('click', () => testConnection('sabnzbd'));
        document.getElementById('testQbittorrentBtn').addEventListener('click', () => testConnection('qbittorrent'));
        document.getElementById('testNavidromeBtn').addEventListener('click', () => testConnection('navidrome'));
        document.getElementById('testJellyfinBtn').addEventListener('click', () => testConnection('jellyfin'));
        document.getElementById('testPlexBtn').addEventListener('click', () => testConnection('plex'));
        document.getElementById('testLidarrBtn').addEventListener('click', () => testConnection('lidarr'));
        document.getElementById('testYoutubeCookiesBtn').addEventListener('click', () => testConnection('youtube-cookies'));
        document.getElementById('testSpotifyCookiesBtn').addEventListener('click', () => testConnection('spotify-cookies'));
        document.getElementById('testMonochromeBtn').addEventListener('click', () => testSourceDownloads('monochrome', 'testMonochromeBtn', 'monochromeTestResult', 'monochromeTestSteps'));
        document.getElementById('testSoundcloudBtn').addEventListener('click', () => testSourceDownloads('soundcloud', 'testSoundcloudBtn', 'soundcloudTestResult', 'soundcloudTestSteps'));
        document.getElementById('testAppriseBtn').addEventListener('click', () => testConnection('apprise'));
        document.getElementById('testEmailBtn').addEventListener('click', () => testConnection('email'));
        const uploadYoutubeCookiesBtn = document.getElementById('uploadYoutubeCookiesBtn');
        const youtubeCookiesFile = document.getElementById('youtubeCookiesFile');
        const youtubeCookiesTextarea = document.getElementById('settingYoutubeCookies');
        const clearYoutubeCookiesBtn = document.getElementById('clearYoutubeCookiesBtn');

        uploadYoutubeCookiesBtn?.addEventListener('click', () => {
            if (envOverrides.includes('youtube_cookies')) {
                showToast('YouTube cookies are locked by environment settings', true);
                return;
            }
            youtubeCookiesFile?.click();
        });

        youtubeCookiesFile?.addEventListener('change', async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            try {
                const text = await file.text();
                if (youtubeCookiesTextarea) {
                    youtubeCookiesTextarea.value = text;
                }
                showToast('Cookies loaded, saving...');
                await saveSettings();
                showToast('Cookies updated');
                _updateCookieExpiryHint();
            } catch (error) {
                console.error('Failed to read cookies file:', error);
                showToast('Failed to read cookies file', true);
            } finally {
                event.target.value = '';
            }
        });

        clearYoutubeCookiesBtn?.addEventListener('click', async () => {
            if (envOverrides.includes('youtube_cookies')) {
                showToast('YouTube cookies are locked by environment settings', true);
                return;
            }
            if (!youtubeCookiesTextarea) return;
            youtubeCookiesTextarea.value = '';
            youtubeCookiesTextarea.dataset.forceClear = 'true';
            showToast('Clearing cookies...');
            await saveSettings();
            _updateCookieExpiryHint();
        });

        const uploadSpotifyCookiesBtn = document.getElementById('uploadSpotifyCookiesBtn');
        const spotifyCookiesFile = document.getElementById('spotifyCookiesFile');
        const spotifyCookiesTextarea = document.getElementById('settingSpotifyCookies');
        const clearSpotifyCookiesBtn = document.getElementById('clearSpotifyCookiesBtn');

        uploadSpotifyCookiesBtn?.addEventListener('click', () => {
            spotifyCookiesFile?.click();
        });

        spotifyCookiesFile?.addEventListener('change', async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            try {
                const text = await file.text();
                if (spotifyCookiesTextarea) {
                    spotifyCookiesTextarea.value = text;
                }
                showToast('Cookies loaded, saving...');
                await saveSettings();
                showToast('Spotify cookies updated');
            } catch (error) {
                console.error('Failed to read Spotify cookies file:', error);
                showToast('Failed to read cookies file', true);
            } finally {
                event.target.value = '';
            }
        });

        clearSpotifyCookiesBtn?.addEventListener('click', async () => {
            if (!spotifyCookiesTextarea) return;
            spotifyCookiesTextarea.value = '';
            spotifyCookiesTextarea.dataset.forceClear = 'true';
            showToast('Clearing Spotify cookies...');
            await saveSettings();
            _updateSpotifyCookieHint(null);
        });

        document.getElementById('userInfoToggle')?.addEventListener('click', () => {
            const panel = document.getElementById('userInfoPanel');
            const btn = document.getElementById('userInfoToggle');
            if (!panel || !btn) return;
            const open = panel.hasAttribute('hidden');
            if (open) {
                panel.removeAttribute('hidden');
                btn.setAttribute('aria-expanded', 'true');
            } else {
                panel.setAttribute('hidden', '');
                btn.setAttribute('aria-expanded', 'false');
            }
        });

        async function loadUsers() {
            if (!isAdmin()) return;
            try {
                const resp = await apiFetch('/api/users');
                if (!resp.ok) return;
                const data = await resp.json();
                const listEl = document.getElementById('userList');
                const warningEl = document.getElementById('firstUserWarning');
                const roleEl = document.getElementById('newUserRole');
                if (!listEl) return;
                const currentUser = getCurrentUser();
                const noUsers = !data.users || data.users.length === 0;

                // Show the "point of no return" warning and lock role to Admin when
                // no users exist yet; the first account must always be admin.
                if (warningEl) warningEl.style.display = noUsers ? 'block' : 'none';
                if (roleEl) {
                    if (noUsers) roleEl.value = 'admin';
                    Array.from(roleEl.options).forEach(o => {
                        o.disabled = noUsers && o.value !== 'admin';
                    });
                }

                listEl.innerHTML = data.users.map(u => `
                    <div style="display:flex; align-items:center; gap:12px; padding:10px 0; border-bottom:1px solid var(--border);">
                        <span style="flex:1; font-weight:${u.id === currentUser?.id ? '600' : '400'};">${escapeHtml(u.username)}</span>
                        <span style="color:var(--text-secondary); font-size:13px;">${u.role}</span>
                        ${u.id !== currentUser?.id
                            ? `<button class="user-action-btn warning" ${uiAction('forcePasswordReset', [u.id, u.username])}>Force reset</button>
                               <button class="user-action-btn" ${uiAction('deleteUser', [u.id, u.username])}>Remove</button>`
                            : `<span style="color:var(--text-secondary); font-size:13px;">(you)</span>`}
                    </div>
                `).join('') || '<p style="color:var(--text-secondary); font-size:13px;">No users yet.</p>';
            } catch {}
        }

        async function createUser() {
            const username = document.getElementById('newUserUsername').value.trim();
            const password = document.getElementById('newUserPassword').value;
            const role = document.getElementById('newUserRole').value;
            const errorEl = document.getElementById('createUserError');

            if (!username || !password) {
                errorEl.textContent = 'Username and password are required.';
                errorEl.style.display = 'block';
                return;
            }

            try {
                const resp = await apiFetch('/api/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, role }),
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) {
                    errorEl.textContent = data.detail || 'Failed to create user.';
                    errorEl.style.display = 'block';
                    return;
                }
                errorEl.style.display = 'none';
                document.getElementById('newUserUsername').value = '';
                document.getElementById('newUserPassword').value = '';
                // Going from 0 to 1 users (first_user) or 1 to 2 (requires_login)
                // both flip into session-required mode. The current admin has no
                // session, so further requests will 401; clear state and bounce
                // to login rather than leaving the UI stuck on a stale view.
                if (data.first_user || data.requires_login) {
                    localStorage.clear();
                    sessionStorage.clear();
                    window.location.reload();
                    return;
                }
                await loadUsers();
            } catch {
                errorEl.textContent = 'Error creating user.';
                errorEl.style.display = 'block';
            }
        }

        async function deleteUser(userId, username) {
            if (!confirm(`Remove user "${username}"? This cannot be undone.`)) return;
            try {
                const resp = await apiFetch(`/api/users/${userId}`, { method: 'DELETE' });
                if (!resp.ok) {
                    const data = await resp.json().catch(() => ({}));
                    alert(data.detail || 'Failed to remove user.');
                    return;
                }
                await loadUsers();
            } catch {
                alert('Error removing user.');
            }
        }

        async function forcePasswordReset(userId, username) {
            if (!confirm(`Force "${username}" to set a new password on next login?\n\nTheir current sessions will be terminated immediately.`)) return;
            try {
                const resp = await apiFetch(`/api/users/${userId}/force-password-change`, { method: 'PUT' });
                if (!resp.ok) {
                    const data = await resp.json().catch(() => ({}));
                    alert(data.detail || 'Failed to flag user for password reset.');
                    return;
                }
                await loadUsers();
            } catch {
                alert('Error flagging user for password reset.');
            }
        }
