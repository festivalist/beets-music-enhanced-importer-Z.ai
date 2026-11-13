        // Helpers and dialogs more than one tab uses: badges and formatters, hover
        // previews and library playback, the tag editor, the report dialog and the
        // missing-track versions picker.

        let activeTagEditor = null;

        const tagEditorOverlay = document.getElementById('tagEditorOverlay');
        const tagEditorArtist = document.getElementById('tagEditorArtist');
        const tagEditorTitle = document.getElementById('tagEditorTitle');
        const tagEditorAlbum = document.getElementById('tagEditorAlbum');
        const tagEditorAlbumArtist = document.getElementById('tagEditorAlbumArtist');
        const tagEditorYear = document.getElementById('tagEditorYear');
        const tagEditorTrackNumber = document.getElementById('tagEditorTrackNumber');
        const tagEditorTrackTotal = document.getElementById('tagEditorTrackTotal');
        const tagEditorMeta = document.getElementById('tagEditorMeta');
        const tagEditorPreview = document.getElementById('tagEditorPreview');
        const tagEditorError = document.getElementById('tagEditorError');
        const tagEditorGuessBtn = document.getElementById('tagEditorGuessBtn');
        const tagEditorResetBtn = document.getElementById('tagEditorResetBtn');
        const tagEditorSaveBtn = document.getElementById('tagEditorSaveBtn');

        // Preview state
        const previewAudio = document.getElementById('previewAudio');
        let hoverTimeout = null;
        let currentPreviewKey = null;
        let previewRequestKey = null;
        let previewRequestSerial = 0;
        let previewAbortController = null;
        let previewCache = new Map(); // Short-lived cache of resolved preview URLs
        const MAX_PREVIEW_CACHE = 100;
        const PREVIEW_CACHE_TTL = 2 * 60 * 1000;
        const HOVER_DELAY = 2000; // 2 seconds before preview starts
        let _previewFadeInterval = null;
        const PREVIEW_FADE_DURATION = 5000; // ms to ramp from 0 to target volume

        const previewVolume = 0.8; // Fixed preview volume - fade-in handles the ramp

        // Desktop preview button: some folk would rather press a button than have
        // music start up because the mouse paused on its way to the biscuit tin.
        // Kept in localStorage rather than on the server, since which machine you
        // happen to be sat at is the entire point of the setting.
        function desktopPreviewButtonEnabled() {
            return localStorage.getItem(userStorageKey('desktopPreviewButton')) === '1';
        }

        function resultTooltip(previewable) {
            if (!previewable) return 'Click to download';
            return desktopPreviewButtonEnabled()
                ? 'Press Preview to listen, click to download'
                : 'Hover to preview, click to download';
        }

        function applyDesktopPreviewButton() {
            const on = desktopPreviewButtonEnabled();
            document.body.classList.toggle('desktop-preview-button', on);
            const toggle = document.getElementById('settingDesktopPreviewButton');
            if (toggle) toggle.checked = on;
            // Cards already on screen would otherwise carry on promising a hover
            // preview that is never coming, which is just rude.
            document.querySelectorAll('.result-item').forEach(item => {
                if (item.querySelector('.preview-btn')) item.dataset.tooltip = resultTooltip(true);
            });
        }

        // The button's own label doubles as its status light. A four second yt-dlp
        // resolve is otherwise indistinguishable from a button that does nothing,
        // and people press it again, which helps nobody.
        const PREVIEW_BTN_LABELS = {
            idle: 'Preview \u25B6',
            loading: 'Loading...',
            playing: 'Stop \u25A0',
        };

        function setPreviewBtnLabel(element, state) {
            const btn = element && element.querySelector && element.querySelector('.preview-btn');
            if (btn) btn.textContent = PREVIEW_BTN_LABELS[state];
        }

        function resetPreviewBtnLabels() {
            document.querySelectorAll('.preview-btn').forEach(btn => {
                btn.textContent = PREVIEW_BTN_LABELS.idle;
            });
        }

        function previewKey(videoId, result) {
            const source = (result && result.source) || 'youtube';
            const identity = (result && result.source_url) || videoId;
            return `${source}:${identity}`;
        }

        function previewIsActiveOrLoading(videoId, result) {
            const key = previewKey(videoId, result);
            return currentPreviewKey === key || previewRequestKey === key;
        }

        // Leaving a card cancels a hover-started preview. With the button on, the
        // preview was a deliberate press, so it carries on until told otherwise.
        function stopHoverPreview() {
            if (desktopPreviewButtonEnabled()) return;
            stopPreview();
        }

        // Preview functions
        function startHoverTimer(videoId, element, result) {
            clearHoverTimer();
            // With the button on, previews are strictly opt-in: a resting mouse is
            // no longer taken as consent.
            if (desktopPreviewButtonEnabled()) return;
            hoverTimeout = setTimeout(() => {
                startPreview(videoId, element, result);
            }, HOVER_DELAY);
        }

        function clearHoverTimer() {
            if (hoverTimeout) {
                clearTimeout(hoverTimeout);
                hoverTimeout = null;
            }
        }

        async function startPreview(videoId, element, result) {
            // Don't preview if already downloading
            if (downloadingIds.has(videoId)) return;

            const cacheKey = previewKey(videoId, result);
            // Upgrade previews can invoke this from both mouseenter and click.
            // One in-flight request for a result is plenty.
            if (previewRequestKey === cacheKey) return;

            // Stop any current preview
            stopPreview();
            const requestId = ++previewRequestSerial;
            previewRequestKey = cacheKey;
            previewAbortController = new AbortController();

            element.classList.add('loading-preview');
            setPreviewBtnLabel(element, 'loading');

            try {
                const cachedPreview = previewCache.get(cacheKey);
                let audioUrl = null;
                if (cachedPreview && Date.now() - cachedPreview.cachedAt < PREVIEW_CACHE_TTL) {
                    audioUrl = cachedPreview.url;
                } else if (cachedPreview) {
                    previewCache.delete(cacheKey);
                }

                if (!audioUrl) {
                    // Build preview URL with source params
                    const previewSource = (result && result.source) || 'youtube';
                    const params = new URLSearchParams({ source: previewSource });
                    // Hand over everything the result knows; each source takes what it
                    // needs (Monochrome resolves by artist and title, YouTube by ID alone).
                    if (result && result.source_url) {
                        params.set('url', result.source_url);
                    }
                    if (result) {
                        params.set('artist', result.channel || result.artist || '');
                        params.set('title', result.title || '');
                    }
                    const response = await apiFetch(`/api/preview/${encodeURIComponent(videoId)}?${params}`, {
                        signal: previewAbortController.signal,
                    });
                    if (requestId !== previewRequestSerial) return;
                    if (!response.ok) throw new Error('Failed to get preview');

                    const data = await response.json();
                    if (requestId !== previewRequestSerial) return;
                    audioUrl = data.url;
                    previewCache.set(cacheKey, { url: audioUrl, cachedAt: Date.now() });
                    if (previewCache.size > MAX_PREVIEW_CACHE) {
                        const oldestKey = previewCache.keys().next().value;
                        previewCache.delete(oldestKey);
                    }
                }

                if (requestId !== previewRequestSerial) return;

                // An HLS preview comes back as one of our own addresses, which an
                // <audio> element can only reach with the playback cookie.
                if (audioUrl.startsWith('/')) {
                    await _ensurePlaybackCookie();
                    if (requestId !== previewRequestSerial) return;
                }

                element.classList.remove('loading-preview');
                element.classList.add('previewing');
                setPreviewBtnLabel(element, 'playing');
                currentPreviewKey = cacheKey;
                previewRequestKey = null;

                previewAudio.onerror = () => {
                    previewCache.delete(cacheKey);
                    if (currentPreviewKey === cacheKey) stopPreview();
                };
                // A preview that runs to the end used to leave the card looking as
                // though it were still going. Now that the button says "Stop", that
                // particular fib is a bit too obvious to leave in.
                previewAudio.onended = () => {
                    if (currentPreviewKey === cacheKey) stopPreview();
                };
                previewAudio.src = audioUrl;
                previewAudio.volume = 0;
                previewAudio.play().catch(() => {
                    // Autoplay blocked or other error
                    previewCache.delete(cacheKey);
                    if (currentPreviewKey === cacheKey) stopPreview();
                });

                // Fade in to target volume over PREVIEW_FADE_DURATION
                if (_previewFadeInterval) clearInterval(_previewFadeInterval);
                const fadeSteps = 30;
                const fadeStepMs = PREVIEW_FADE_DURATION / fadeSteps;
                let step = 0;
                _previewFadeInterval = setInterval(() => {
                    step++;
                    previewAudio.volume = Math.min(previewVolume, (step / fadeSteps) * previewVolume);
                    if (step >= fadeSteps) clearInterval(_previewFadeInterval);
                }, fadeStepMs);


            } catch (error) {
                if (requestId !== previewRequestSerial) return;
                element.classList.remove('loading-preview');
                setPreviewBtnLabel(element, 'idle');
                // Silently fail - preview is a nice-to-have
            } finally {
                if (requestId === previewRequestSerial) {
                    previewRequestKey = null;
                    previewAbortController = null;
                }
            }
        }

        function stopPreview() {
            clearHoverTimer();
            previewRequestSerial++;
            if (previewAbortController) previewAbortController.abort();
            previewAbortController = null;
            previewRequestKey = null;
            if (_previewFadeInterval) { clearInterval(_previewFadeInterval); _previewFadeInterval = null; }
            previewAudio.onerror = null;
            previewAudio.onended = null;
            previewAudio.pause();
            previewAudio.src = '';
            currentPreviewKey = null;

            // Remove previewing class from all items
            document.querySelectorAll('.result-item.previewing').forEach(item => {
                item.classList.remove('previewing');
            });
            document.querySelectorAll('.result-item.loading-preview').forEach(item => {
                item.classList.remove('loading-preview');
            });
            resetPreviewBtnLabels();
        }

        function _renderMissingTrackCandidate(result, index) {
            const rescueNote = missingTrackVersionsState.mode === 'job' && result.attempted
                ? '<span class="missing-track-candidate-note">Tried automatically</span>'
                : '';
            const selectable = result.selectable !== false;
            return `
                <div class="missing-track-candidate">
                    ${_renderOneResult(result, index)}
                    <div class="missing-track-candidate-actions">
                        ${rescueNote}
                        <button type="button"
                            class="missing-track-candidate-btn"
                            data-action="queue-missing-track-candidate"
                            data-index="${index}" ${selectable ? '' : 'disabled'}>${selectable ? 'Use This' : 'Search again'}</button>
                    </div>
                </div>
            `;
        }

        function _attachMissingTrackCandidateHandlers(wrapper, result, index) {
            const item = wrapper.querySelector('.result-item');
            if (item) {
                const videoId = item.dataset.videoId;
                item.addEventListener('mouseenter', () => {
                    if (sourceHasPreview(result.source)) {
                        startHoverTimer(videoId, item, result);
                    }
                });
                item.addEventListener('mouseleave', () => stopHoverPreview());

                const previewBtn = item.querySelector('.preview-btn');
                if (previewBtn) {
                    previewBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        if (previewIsActiveOrLoading(videoId, result)) {
                            stopPreview();
                        } else {
                            startPreview(videoId, item, result);
                        }
                    });
                }
            }

            const btn = wrapper.querySelector('[data-action="queue-missing-track-candidate"]');
            if (btn) {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    queueMissingTrackCandidate(index, btn);
                });
            }
        }

        // Each source's badge, label and colour come from the source itself, via
        // /api/sources, so a new one arrives dressed. Retired sources keep theirs
        // here, since old jobs and upgrade rows name them long after they've gone.
        let _cachedSources = null;
        const RETIRED_SOURCES = {
            mp3phoenix: { id: 'mp3phoenix', label: 'MP3Phoenix', badge: 'PX', colour: '#e05c00' },
            qbdlx: { id: 'qbdlx', label: 'qbdlx', badge: 'QB', colour: '' },
        };

        async function _fetchSources() {
            if (_cachedSources) return _cachedSources;
            try {
                const res = await apiFetch('/api/sources');
                if (res.ok) {
                    _cachedSources = (await res.json()).sources || [];
                    paintSourceBadges();
                }
            } catch {}
            return _cachedSources || [];
        }

        function sourceMeta(source) {
            return (_cachedSources || []).find(s => s.id === source) || RETIRED_SOURCES[source] || null;
        }

        function getSourceBadge(source) {
            return sourceMeta(source)?.badge || (source || '').toUpperCase().slice(0, 3);
        }

        function getSourceLabel(source) {
            return sourceMeta(source)?.label || source;
        }

        function getSourceColour(source) {
            return sourceMeta(source)?.colour || '';
        }

        // One .source-badge rule per source, from its colour. White text unless
        // the colour is plainly pale (JioSaavn's teal); brand badges are
        // white-on-colour by habit, so this leans white rather than splitting
        // the difference.
        function paintSourceBadges() {
            const linear = channel => {
                const c = channel / 255;
                return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
            };
            const rules = [...(_cachedSources || []), ...Object.values(RETIRED_SOURCES)]
                .filter(s => /^#[0-9a-f]{6}$/i.test(s.colour || ''))
                .map(s => {
                    const [r, g, b] = [1, 3, 5].map(i => linear(parseInt(s.colour.slice(i, i + 2), 16)));
                    const pale = 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4;
                    return `.source-badge.${CSS.escape(s.id)} { background: ${s.colour}; color: ${pale ? '#000' : '#fff'}; }`;
                });
            let sheet = document.getElementById('sourceBadgeColours');
            if (!sheet) {
                sheet = document.createElement('style');
                sheet.id = 'sourceBadgeColours';
                document.head.appendChild(sheet);
            }
            sheet.textContent = rules.join('\n');
        }

        function getQualityBadgeClass(quality) {
            if (!quality) return '';
            const q = quality.toUpperCase();
            if (q === 'HI_RES_LOSSLESS') return 'hires';
            if (q === 'LOSSLESS' || q.includes('FLAC')) return 'flac';
            if (q === 'HIGH' || q.includes('320') || q.includes('256')) return 'mp3-high';
            return '';
        }

        function formatQualityLabel(quality) {
            if (!quality) return '';
            const labels = {
                'HI_RES_LOSSLESS': 'Hi-Res',
                'LOSSLESS': 'Lossless',
                'HIGH': 'HQ',
            };
            return labels[quality] || quality;
        }

        function formatResultMeta(result) {
            const parts = [];
            const artist = (result.artist || '').trim();
            const uploader = (result.channel || '').trim();

            // For Soulseek the "channel" is whichever stranger happens to be sharing
            // the file, not the performer, so it goes down with the badges instead of
            // sitting up here impersonating an artist.
            if (result.source === 'soulseek') {
                if (artist) parts.push(escapeHtml(artist));
            } else if (artist) {
                parts.push(uploader && uploader !== artist
                    ? `${escapeHtml(artist)} • ${escapeHtml(uploader)}`
                    : escapeHtml(artist));
            } else if (uploader) {
                parts.push(escapeHtml(uploader));
            }

            // Show album if known - clickable to open in the Artists tab's album browser
            if (result.album) {
                const albumArtist = escapeAttr(artist || uploader);
                const albumTitle = escapeAttr(result.album);
                const year = result.year ? ` <span class="result-year">(${escapeHtml(String(result.year))})</span>` : '';
                // A source that lists albums itself (JioSaavn) names the album it means, so the
                // link can open that tracklist and does not depend on MusicBrainz knowing it.
                const ownAlbum = result.album_id && result.source
                    ? ` data-source="${escapeAttr(result.source)}" data-album-id="${escapeAttr(result.album_id)}"` : '';
                parts.push(`<span class="album-link" data-artist="${albumArtist}" data-album="${albumTitle}"${ownAlbum} title="View album in Artists tab">${escapeHtml(result.album)}</span>${year}`);
            }
            return parts.filter(Boolean).join(' • ');
        }

        // Soulseek results carry a real 0-1 confidence from the path scorer, so the
        // number means something. Colour it, because "62%" and "97%" deserve rather
        // different levels of enthusiasm.
        function matchStrengthClass(confidence) {
            if (confidence >= 0.9) return 'match-strong';
            if (confidence >= 0.75) return 'match-fair';
            return 'match-weak';
        }

        function renderMatchBadge(result) {
            if (typeof result.match_confidence !== 'number') return '';
            const percent = Math.round(result.match_confidence * 100);
            return `<div class="result-match ${matchStrengthClass(result.match_confidence)}" title="How closely this file's path matches what you searched for">${percent}%<span class="result-match-caption">match</span></div>`;
        }

        async function loadMissingTrackVersions() {
            const body = document.getElementById('missingTrackVersionsBody');
            const meta = document.getElementById('missingTrackVersionsMeta');
            if (!body || !meta) return;

            const isJobRescue = missingTrackVersionsState.mode === 'job';
            meta.textContent = isJobRescue
                ? `Failed download • ${missingTrackVersionsState.artist} - ${missingTrackVersionsState.title}`
                : `${missingTrackVersionsState.playlistName || 'Watched playlist'} • ${missingTrackVersionsState.artist} - ${missingTrackVersionsState.title}`;
            body.innerHTML = `<div class="missing-track-modal-empty">${isJobRescue ? 'Loading saved alternatives...' : 'Searching for alternatives...'}</div>`;

            try {
                let resp;
                if (isJobRescue) {
                    resp = await apiFetch(`/api/jobs/${encodeURIComponent(missingTrackVersionsState.jobId)}/rescue-candidates`);
                } else {
                    const params = new URLSearchParams({
                        artist: missingTrackVersionsState.artist,
                        title: missingTrackVersionsState.title,
                        limit: '4',
                    });
                    resp = await apiFetch(`/api/watched-playlists/${encodeURIComponent(missingTrackVersionsState.playlistId)}/track-candidates?${params.toString()}`);
                }
                if (!resp.ok) throw new Error('Search failed');
                const data = await resp.json();
                if (isJobRescue) {
                    missingTrackVersionsState.artist = data.artist || '';
                    missingTrackVersionsState.title = data.title || '';
                    meta.textContent = `Failed download • ${missingTrackVersionsState.artist} - ${missingTrackVersionsState.title}`;
                }
                const results = Array.isArray(isJobRescue ? data.candidates : data.results)
                    ? (isJobRescue ? data.candidates : data.results)
                    : [];
                missingTrackVersionsState.results = results;

                if (!results.length) {
                    body.innerHTML = `<div class="missing-track-modal-empty">${isJobRescue ? 'No saved alternatives remain. Use Search Again to ask the allowed sources for fresh options.' : 'No alternatives found. Retry will still run the automatic watched-playlist search, or Search will open the full Tracks tab.'}</div>`;
                    return;
                }

                body.innerHTML = results.map((result, index) => _renderMissingTrackCandidate(result, index)).join('');
                body.querySelectorAll('.missing-track-candidate').forEach((wrapper, index) => {
                    _attachMissingTrackCandidateHandlers(wrapper, results[index], index);
                });
            } catch (error) {
                body.innerHTML = '<div class="missing-track-modal-empty">Could not load alternatives right now.</div>';
            }
        }

        async function openMissingTrackVersionsModal(playlistId, playlistName, artist, title, rowId) {
            missingTrackVersionsState.mode = 'watched';
            missingTrackVersionsState.jobId = '';
            missingTrackVersionsState.playlistId = playlistId;
            missingTrackVersionsState.playlistName = playlistName;
            missingTrackVersionsState.artist = artist;
            missingTrackVersionsState.title = title;
            missingTrackVersionsState.rowId = rowId || '';
            missingTrackVersionsState.results = [];
            document.getElementById('missingTrackVersionsOverlay').style.display = 'flex';
            await loadMissingTrackVersions();
        }

        async function openJobRescueVersions(jobId) {
            missingTrackVersionsState.mode = 'job';
            missingTrackVersionsState.jobId = jobId;
            missingTrackVersionsState.playlistId = '';
            missingTrackVersionsState.playlistName = '';
            missingTrackVersionsState.artist = '';
            missingTrackVersionsState.title = '';
            missingTrackVersionsState.rowId = '';
            missingTrackVersionsState.results = [];
            document.querySelector('#missingTrackVersionsOverlay .modal-title').textContent = 'Choose Another Version';
            document.getElementById('missingTrackVersionsRefreshBtn').textContent = 'Search Again';
            document.getElementById('missingTrackVersionsOverlay').style.display = 'flex';
            await loadMissingTrackVersions();
        }

        function closeMissingTrackVersionsModal() {
            stopPreview();
            missingTrackVersionsState.mode = 'watched';
            missingTrackVersionsState.jobId = '';
            missingTrackVersionsState.playlistId = '';
            missingTrackVersionsState.playlistName = '';
            missingTrackVersionsState.artist = '';
            missingTrackVersionsState.title = '';
            missingTrackVersionsState.rowId = '';
            missingTrackVersionsState.results = [];
            document.querySelector('#missingTrackVersionsOverlay .modal-title').textContent = 'Find Versions';
            document.getElementById('missingTrackVersionsRefreshBtn').textContent = 'Refresh Results';
            document.getElementById('missingTrackVersionsOverlay').style.display = 'none';
        }

        async function queueMissingTrackCandidate(index, btn) {
            const result = missingTrackVersionsState.results[index];
            if (!result) return;

            const originalText = btn ? btn.textContent : '';
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Queueing...';
            }

            try {
                if (missingTrackVersionsState.mode === 'job') {
                    const resp = await apiFetch(`/api/jobs/${encodeURIComponent(missingTrackVersionsState.jobId)}/rescue-candidate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ candidate_key: result.candidate_key })
                    });
                    if (!resp.ok) {
                        const err = await resp.json().catch(() => ({}));
                        throw new Error(err.detail || 'Failed to queue candidate');
                    }
                    showToast(`Queued ${missingTrackVersionsState.artist} - ${missingTrackVersionsState.title}`);
                    closeMissingTrackVersionsModal();
                    loadJobs(false);
                    return;
                }
                const payload = {
                    artist: missingTrackVersionsState.artist,
                    title: missingTrackVersionsState.title,
                    video_id: result.video_id || '',
                    source: result.source || 'youtube',
                    source_url: result.source_url || null,
                    slskd_username: result.slskd_username || null,
                    slskd_filename: result.slskd_filename || null,
                    slskd_size: result.slskd_size || result.size || null,
                };
                const resp = await apiFetch(`/api/watched-playlists/${encodeURIComponent(missingTrackVersionsState.playlistId)}/queue-track-candidate`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.detail || 'Failed to queue candidate');
                }

                const row = missingTrackVersionsState.rowId ? document.getElementById(missingTrackVersionsState.rowId) : null;
                if (row) {
                    const retryBtn = row.querySelector('[data-action="retry-missing-track"]');
                    if (retryBtn) {
                        retryBtn.disabled = true;
                        retryBtn.textContent = 'Queued';
                    }
                }

                showToast(`Queued ${missingTrackVersionsState.artist} - ${missingTrackVersionsState.title}`);
                closeMissingTrackVersionsModal();
                if (document.querySelector('.tab.active[data-tab="queue"]')) {
                    loadJobs(false);
                }
            } catch (error) {
                showToast(error?.message || 'Failed to queue candidate', true);
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = originalText || 'Use This';
                }
            }
        }

        function renderTagEditorPreview() {
            if (!activeTagEditor) return;
            const artist = (tagEditorArtist.value || '').trim();
            const title = (tagEditorTitle.value || '').trim();
            const album = (tagEditorAlbum.value || '').trim();
            const albumArtist = (tagEditorAlbumArtist.value || '').trim();
            const year = (tagEditorYear.value || '').trim();
            const trackNumber = (tagEditorTrackNumber.value || '').trim();
            const trackTotal = (tagEditorTrackTotal.value || '').trim();
            const filename = [artist, title].filter(Boolean).join(' - ') || 'Untitled track';
            tagEditorPreview.innerHTML = `
                <div><strong>Filename preview:</strong> ${escapeHtmlText(filename)}${escapeHtmlText(activeTagEditor.extension || '')}</div>
                <div><strong>Album tag:</strong> ${album ? escapeHtmlText(album) : '<em>empty</em>'}</div>
                <div><strong>Album artist:</strong> ${albumArtist ? escapeHtmlText(albumArtist) : '<em>empty</em>'}</div>
                <div><strong>Track:</strong> ${trackNumber ? `${escapeHtmlText(trackNumber)}${trackTotal ? ` / ${escapeHtmlText(trackTotal)}` : ''}` : '<em>empty</em>'}</div>
                <div><strong>Year:</strong> ${year ? escapeHtmlText(year) : '<em>empty</em>'}</div>
            `;
        }

        function resetTagEditorDraft() {
            if (!activeTagEditor) return;
            tagEditorArtist.value = activeTagEditor.original.artist || '';
            tagEditorTitle.value = activeTagEditor.original.title || '';
            tagEditorAlbum.value = activeTagEditor.original.album || '';
            tagEditorAlbumArtist.value = activeTagEditor.original.album_artist || '';
            tagEditorYear.value = activeTagEditor.original.year || '';
            tagEditorTrackNumber.value = activeTagEditor.original.track_number || '';
            tagEditorTrackTotal.value = activeTagEditor.original.track_total || '';
            tagEditorError.style.display = 'none';
            tagEditorError.textContent = '';
            renderTagEditorPreview();
        }

        function openTagEditor({ jobId, artist, title, album, albumArtist = '', year = '', trackNumber = '', trackTotal = '' }) {
            const job = allQueueJobs.find(j => String(j.id) === String(jobId));
            activeTagEditor = {
                jobId: String(jobId || ''),
                extension: job?.file_path ? (job.file_path.match(/\.[^.\/\\]+$/)?.[0] || '') : '',
                sourceLabel: getSourceLabel(job?.source || 'youtube'),
                guessArtistSeed: (artist || '').trim(),
                guessTitleSeed: (title || '').trim(),
                guessOffset: 0,
                original: {
                    artist: artist || '',
                    title: title || '',
                    album: album || '',
                    album_artist: albumArtist || '',
                    year: year || '',
                    track_number: trackNumber || '',
                    track_total: trackTotal || '',
                },
            };
            tagEditorMeta.textContent = [activeTagEditor.sourceLabel, activeTagEditor.jobId].filter(Boolean).join(' • ');
            resetTagEditorDraft();
            tagEditorOverlay.style.display = 'flex';
            setTimeout(() => tagEditorArtist.focus(), 0);
            fillTagEditorFromFile(activeTagEditor.jobId);
        }

        // The job only remembers artist, title and album. The rest comes from the
        // file, or the editor shows blanks that saving then quietly leaves alone.
        async function fillTagEditorFromFile(jobId) {
            let tags;
            try {
                const res = await apiFetch(`/api/jobs/${jobId}/tags`);
                if (!res.ok) return;
                tags = await res.json();
            } catch (_) {
                return;
            }
            if (!activeTagEditor || activeTagEditor.jobId !== jobId) return;
            [
                ['album', tagEditorAlbum],
                ['album_artist', tagEditorAlbumArtist],
                ['year', tagEditorYear],
                ['track_number', tagEditorTrackNumber],
                ['track_total', tagEditorTrackTotal],
            ].forEach(([key, input]) => {
                const value = tags[key] == null ? '' : String(tags[key]);
                if (!value || activeTagEditor.original[key]) return;
                activeTagEditor.original[key] = value;
                // Typed into while the file was being read: the typing wins.
                if (!input.value) input.value = value;
            });
            renderTagEditorPreview();
        }

        function closeTagEditor() {
            activeTagEditor = null;
            tagEditorOverlay.style.display = 'none';
            tagEditorError.style.display = 'none';
            tagEditorError.textContent = '';
            tagEditorGuessBtn.disabled = false;
            tagEditorGuessBtn.textContent = 'Guess from MusicBrainz';
            tagEditorSaveBtn.disabled = false;
            tagEditorSaveBtn.textContent = 'Save Tags';
        }

        async function saveTagEditor() {
            if (!activeTagEditor) return;

            const artist = (tagEditorArtist.value || '').trim();
            const title = (tagEditorTitle.value || '').trim();
            const album = (tagEditorAlbum.value || '').trim();
            const albumArtist = (tagEditorAlbumArtist.value || '').trim();
            const year = (tagEditorYear.value || '').trim();
            const rawTrackNumber = tagEditorTrackNumber.value ? parseInt(tagEditorTrackNumber.value, 10) : null;
            const rawTrackTotal = tagEditorTrackTotal.value ? parseInt(tagEditorTrackTotal.value, 10) : null;
            const trackNumber = Number.isFinite(rawTrackNumber) ? rawTrackNumber : null;
            const trackTotal = Number.isFinite(rawTrackTotal) ? rawTrackTotal : null;

            if (!artist || !title) {
                tagEditorError.textContent = 'Artist and title are required.';
                tagEditorError.style.display = 'block';
                return;
            }
            if (year && !/^\d{4}$/.test(year)) {
                tagEditorError.textContent = 'Year must be four digits.';
                tagEditorError.style.display = 'block';
                return;
            }
            if (trackNumber && trackTotal && trackNumber > trackTotal) {
                tagEditorError.textContent = 'Track number cannot be greater than total tracks.';
                tagEditorError.style.display = 'block';
                return;
            }

            const originalText = tagEditorSaveBtn.textContent;
            tagEditorSaveBtn.disabled = true;
            tagEditorSaveBtn.textContent = 'Saving...';
            tagEditorError.style.display = 'none';

            try {
                const res = await apiFetch(`/api/jobs/${activeTagEditor.jobId}/tags`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        artist,
                        title,
                        album,
                        album_artist: albumArtist,
                        year,
                        track_number: trackNumber,
                        track_total: trackTotal,
                    }),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'Failed to save tags');
                }

                const card = queueTab.querySelector(`.job-item[data-job-id="${activeTagEditor.jobId}"]`);
                if (card) {
                    const titleEl = card.querySelector('.job-title');
                    if (titleEl) titleEl.firstChild.textContent = artist ? `${artist} - ${title}` : title;
                    const editBtn = card.querySelector('.edit-tags-btn');
                    if (editBtn) {
                        editBtn.dataset.artist = artist;
                        editBtn.dataset.title = title;
                        editBtn.dataset.album = album;
                    }
                }
                const queueJob = allQueueJobs.find(j => String(j.id) === String(activeTagEditor.jobId));
                if (queueJob) {
                    queueJob.artist = artist;
                    queueJob.title = title;
                    queueJob.album_name = album;
                }

                showToast('Tags updated');
                closeTagEditor();
            } catch (e) {
                tagEditorError.textContent = e.message || 'Failed to save tags.';
                tagEditorError.style.display = 'block';
                tagEditorSaveBtn.disabled = false;
                tagEditorSaveBtn.textContent = originalText;
            }
        }

        async function guessTagEditorFromMusicBrainz() {
            if (!activeTagEditor) return;
            const artist = (tagEditorArtist.value || '').trim();
            const title = (tagEditorTitle.value || '').trim();
            if (!artist || !title) {
                tagEditorError.textContent = 'Enter artist and title before guessing.';
                tagEditorError.style.display = 'block';
                return;
            }

            const originalText = tagEditorGuessBtn.textContent;
            tagEditorGuessBtn.disabled = true;
            tagEditorGuessBtn.textContent = 'Guessing...';
            tagEditorError.style.display = 'none';

            try {
                if (artist !== activeTagEditor.guessArtistSeed || title !== activeTagEditor.guessTitleSeed) {
                    activeTagEditor.guessArtistSeed = artist;
                    activeTagEditor.guessTitleSeed = title;
                    activeTagEditor.guessOffset = 0;
                }
                const res = await apiFetch(`/api/jobs/${activeTagEditor.jobId}/musicbrainz-guess?artist=${encodeURIComponent(artist)}&title=${encodeURIComponent(title)}&offset=${activeTagEditor.guessOffset}`);
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || 'No more suitable MusicBrainz matches found');
                }
                const guess = await res.json();
                tagEditorArtist.value = guess.artist || artist;
                tagEditorTitle.value = guess.title || title;
                tagEditorAlbum.value = guess.album || '';
                tagEditorAlbumArtist.value = guess.album_artist || '';
                tagEditorYear.value = guess.year || '';
                tagEditorTrackNumber.value = guess.track_number || '';
                tagEditorTrackTotal.value = guess.track_total || '';
                activeTagEditor.guessOffset = (guess.candidate_index || 0) + 1;
                renderTagEditorPreview();
                if ((guess.candidate_count || 0) > 1) {
                    tagEditorGuessBtn.textContent = activeTagEditor.guessOffset < guess.candidate_count ? 'Guess Again' : 'No More Guesses';
                } else {
                    tagEditorGuessBtn.textContent = 'Guess Again';
                }
                showToast(`MusicBrainz metadata applied${guess.candidate_count ? ` (${(guess.candidate_index || 0) + 1}/${guess.candidate_count})` : ''}`);
            } catch (e) {
                tagEditorError.textContent = e.message || 'MusicBrainz lookup failed.';
                tagEditorError.style.display = 'block';
                tagEditorGuessBtn.textContent = 'Guess Again';
            } finally {
                tagEditorGuessBtn.disabled = false;
                if (tagEditorGuessBtn.textContent === 'Guessing...') {
                    tagEditorGuessBtn.textContent = originalText;
                }
            }
        }

        function formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
            if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
            return (bytes / 1073741824).toFixed(2) + ' GB';
        }

        // =============================================================================
        // Library / Trash Playback
        // =============================================================================

        let _libraryPlayingId = null;
        let _streamCookieRefreshAt = 0;
        let _streamCookieRequest = null;
        let _streamRefreshTimer = null;

        async function _ensurePlaybackCookie() {
            // The browser carries the HttpOnly cookie on audio requests. Only its
            // expiry is visible here; no credential goes into the URL or JS state.
            if (Date.now() < _streamCookieRefreshAt) return;
            if (_streamCookieRequest) return _streamCookieRequest;
            _streamCookieRequest = (async () => {
                const response = await apiFetch('/api/auth/stream-token', { method: 'POST' });
                if (!response.ok) throw new Error('Could not authorise playback');
                const data = await response.json();
                const ttl = data.expires_in ? data.expires_in * 1000 : 3600000;
                _streamCookieRefreshAt = Date.now() + ttl * 0.6;
            })();
            try {
                await _streamCookieRequest;
            } finally {
                _streamCookieRequest = null;
            }
        }

        function refreshPlaybackCookie() {
            if (_libraryPlayingId) _ensurePlaybackCookie().catch(() => {
                _streamCookieRefreshAt = 0;
            });
        }

        // Active audio still emits these when a background tab's timers slow down.
        previewAudio.addEventListener('timeupdate', refreshPlaybackCookie);

        async function _startLibraryStream(id, url, btn) {
            stopPreview();
            stopLibraryPlayback();
            _libraryPlayingId = id;
            if (btn) btn.innerHTML = '<i class="fa-solid fa-stop"></i>';

            let src;
            try {
                await _ensurePlaybackCookie();
                src = withRootPath(url);
            } catch (error) {
                stopLibraryPlayback();
                showToast('Could not play file', true);
                return;
            }
            // They may have hit stop, or started something else, while we were away.
            if (_libraryPlayingId !== id) return;

            previewAudio.oncanplay = () => {
                previewAudio.oncanplay = null;
                previewAudio.play().catch(() => {});
            };
            previewAudio.onended = () => stopLibraryPlayback();
            previewAudio.onerror = (e) => {
                // Ignore aborted loads (caused by stopLibraryPlayback clearing src)
                if (previewAudio.error && previewAudio.error.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED) {
                    // Could be an expired token rather than a duff file; bin it so the
                    // next attempt starts with a fresh one.
                    _streamCookieRefreshAt = 0;
                    stopLibraryPlayback();
                    showToast('Could not play file', true);
                }
            };
            previewAudio.volume = previewVolume;
            _streamRefreshTimer = setInterval(refreshPlaybackCookie, 15000);
            previewAudio.src = src;
            previewAudio.load();
        }

        function playJobAudio(jobId, btn) {
            if (_libraryPlayingId === jobId) { stopLibraryPlayback(); return; }
            _startLibraryStream(jobId, `/api/jobs/${jobId}/stream`, btn);
        }

        function playTrashAudio(path, btn) {
            if (_libraryPlayingId === 'trash:' + path) { stopLibraryPlayback(); return; }
            _startLibraryStream('trash:' + path, `/api/trash/stream?path=${encodeURIComponent(path)}`, btn);
        }

        function stopLibraryPlayback() {
            clearInterval(_streamRefreshTimer);
            _streamRefreshTimer = null;
            if (!_libraryPlayingId) return;
            previewAudio.oncanplay = null;
            previewAudio.onended = null;
            previewAudio.onerror = null;
            previewAudio.pause();
            previewAudio.src = '';
            // Reset all play buttons back to the play icon
            document.querySelectorAll('.library-play-btn').forEach(b => {
                b.innerHTML = '<i class="fa-solid fa-play"></i>';
            });
            _libraryPlayingId = null;
        }

        // =============================================================================
        // Report / Blacklist
        // =============================================================================

        function openReportDialog(jobId, videoId, uploader, source) {
            document.getElementById('reportJobId').value = jobId;
            document.getElementById('reportVideoId').value = videoId;
            document.getElementById('reportSource').value = source;
            document.getElementById('reportUploader').value = uploader;
            document.getElementById('reportReason').value = 'wrong_track';
            document.getElementById('reportNote').value = '';
            document.getElementById('reportBlockUploader').checked = false;

            const uploaderRow = document.getElementById('reportUploaderRow');
            const uploaderName = document.getElementById('reportUploaderName');
            if (uploader) {
                uploaderName.textContent = uploader;
                uploaderRow.style.display = 'block';
            } else {
                uploaderRow.style.display = 'none';
            }

            const overlay = document.getElementById('reportOverlay');
            overlay.style.display = 'flex';
        }

        function closeReportDialog() {
            document.getElementById('reportOverlay').style.display = 'none';
        }

        tagEditorOverlay.addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeTagEditor();
        });
        tagEditorGuessBtn.addEventListener('click', guessTagEditorFromMusicBrainz);
        tagEditorResetBtn.addEventListener('click', resetTagEditorDraft);
        tagEditorSaveBtn.addEventListener('click', saveTagEditor);
        [tagEditorArtist, tagEditorTitle, tagEditorAlbum, tagEditorAlbumArtist, tagEditorYear, tagEditorTrackNumber, tagEditorTrackTotal].forEach((input) => {
            input.addEventListener('input', () => {
                if (tagEditorError.style.display !== 'none') {
                    tagEditorError.style.display = 'none';
                    tagEditorError.textContent = '';
                }
                renderTagEditorPreview();
            });
            input.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                    event.preventDefault();
                    saveTagEditor();
                } else if (event.key === 'Escape') {
                    event.preventDefault();
                    closeTagEditor();
                }
            });
        });

        // Close on overlay click (not the dialog itself)
        document.getElementById('reportOverlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeReportDialog();
        });
        document.getElementById('missingTrackVersionsOverlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) closeMissingTrackVersionsModal();
        });
        document.getElementById('missingTrackVersionsRefreshBtn').addEventListener('click', async () => {
            if (missingTrackVersionsState.mode !== 'job') {
                loadMissingTrackVersions();
                return;
            }
            const body = document.getElementById('missingTrackVersionsBody');
            if (body) body.innerHTML = '<div class="missing-track-modal-empty">Searching allowed sources...</div>';
            try {
                const resp = await apiFetch(`/api/jobs/${encodeURIComponent(missingTrackVersionsState.jobId)}/rescue-candidates/refresh`, { method: 'POST' });
                if (!resp.ok) throw new Error('Search failed');
                const data = await resp.json();
                const results = Array.isArray(data.candidates) ? data.candidates : [];
                missingTrackVersionsState.results = results;
                if (!body) return;
                body.innerHTML = results.length
                    ? results.map((result, index) => _renderMissingTrackCandidate(result, index)).join('')
                    : '<div class="missing-track-modal-empty">No suitable alternatives found on the allowed sources.</div>';
                body.querySelectorAll('.missing-track-candidate').forEach((wrapper, index) => {
                    _attachMissingTrackCandidateHandlers(wrapper, results[index], index);
                });
            } catch (error) {
                if (body) body.innerHTML = '<div class="missing-track-modal-empty">Could not refresh alternatives right now.</div>';
            }
        });

        async function submitReport() {
            const btn = document.getElementById('reportSubmitBtn');
            btn.disabled = true;
            btn.textContent = 'Reporting...';

            try {
                const payload = {
                    job_id: document.getElementById('reportJobId').value || null,
                    video_id: document.getElementById('reportVideoId').value || null,
                    uploader: document.getElementById('reportUploader').value || null,
                    source: document.getElementById('reportSource').value || 'youtube',
                    reason: document.getElementById('reportReason').value,
                    note: document.getElementById('reportNote').value || null,
                    block_uploader: document.getElementById('reportBlockUploader').checked
                };

                const response = await apiFetch('/api/blacklist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || 'Report failed');
                }

                showToast('Track reported and blacklisted');
                closeReportDialog();
            } catch (error) {
                showToast(error.message || 'Report failed', true);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Report';
            }
        }

        function formatTimeFull(isoString) {
            return formatDateYmd(isoString);
        }

        function formatDuration(startIso, endIso) {
            if (!startIso || !endIso) return '';
            const start = new Date(startIso);
            const end = new Date(endIso);
            const diffMs = end - start;
            if (diffMs < 0) return '';
            const secs = Math.floor(diffMs / 1000);
            if (secs < 60) return `${secs}s`;
            const mins = Math.floor(secs / 60);
            const remainSecs = secs % 60;
            if (mins < 60) return `${mins}m ${remainSecs}s`;
            const hrs = Math.floor(mins / 60);
            const remainMins = mins % 60;
            return `${hrs}h ${remainMins}m`;
        }
