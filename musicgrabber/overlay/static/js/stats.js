        // Stats tab: statistics and watch mismatches.

        // Stats and Mismatches both load when the tab opens, so switching
        // between them is just a matter of which one you are looking at.
        document.getElementById('statsModePills')
            ?.addEventListener('pillchange', (e) => showPillMode(statsTabContainer, e.detail.value));

        async function resetStats() {
            if (!confirm('Reset all dashboard stats? This clears completed/failed job history and search history.')) {
                return;
            }

            resetStatsBtn.disabled = true;

            try {
                const response = await apiFetch('/api/stats?confirm=true', {
                    method: 'DELETE'
                });

                if (!response.ok) throw new Error('Failed to reset stats');

                const data = await response.json();
                showToast(`Stats reset (${data.deleted_jobs} jobs, ${data.deleted_searches} searches)`);
                loadJobs();
                loadStats();
            } catch (error) {
                showToast('Failed to reset stats', true);
            } finally {
                resetStatsBtn.disabled = false;
            }
        }

        resetStatsBtn.addEventListener('click', resetStats);

        // =============================================================================
        // Statistics Dashboard
        // =============================================================================

        let statsScanTimer = null;
        async function loadStats(refreshing = false) {
            clearTimeout(statsScanTimer);
            if (!refreshing) {
                statsContent.innerHTML = `
                    <div class="loading stats-loading" role="status">
                        <div class="stats-equaliser" aria-hidden="true">
                            <span></span><span></span><span></span>
                        </div>
                        <span>Crunching the numbers…</span>
                    </div>
                `;
            }

            try {
                // The sources' own names and colours, for the breakdown. Cached after the first time.
                const [response] = await Promise.all([apiFetch('/api/stats'), _fetchSources()]);
                if (!response.ok) throw new Error('Failed to load stats');

                const data = await response.json();
                renderStats(data);
                if (data.storage_scan_state === 'refreshing') {
                    statsScanTimer = setTimeout(() => {
                        if (statsTabContainer.classList.contains('tab-visible') && document.getElementById('app').style.display !== 'none') loadStats(true);
                    }, 3000);
                }
            } catch (error) {
                statsContent.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon"><i class="fa-solid fa-circle-exclamation"></i></div>
                        <p>Failed to load statistics</p>
                    </div>
                `;
            }

            loadMismatches();
        }

        // The count rides on the pill, so a fresh mismatch gets noticed without
        // anyone having to go and look.
        function setMismatchCount(content, count) {
            document.getElementById('mismatchCount').textContent = count ? String(count) : '';
            document.getElementById('clearMismatchesBtn').disabled = !count;
            if (!count) {
                content.innerHTML = '<div class="empty-state"><p>No mismatches logged. Everything the watched playlists asked for turned up as itself.</p></div>';
            }
        }

        async function loadMismatches() {
            const content = document.getElementById('mismatchContent');
            // The log is admin-only, and so is its pill.
            if (!content || !isAdmin()) return;

            try {
                const res = await apiFetch('/api/mismatches');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                const rows = data.mismatches || [];
                setMismatchCount(content, rows.length);
                if (rows.length === 0) return;

                content.innerHTML = rows.map(m => `
                    <div class="mismatch-row">
                        <div class="mismatch-meta">
                            <span class="mismatch-playlist">${escapeHtml(m.playlist_name || m.playlist_id || '-')}</span>
                            <span class="mismatch-date">${m.created_at ? m.created_at.slice(0, 16).replace('T', ' ') : ''}</span>
                        </div>
                        <div class="mismatch-pair">
                            <div class="mismatch-line mismatch-expected">
                                <span class="mismatch-tag">Expected</span>
                                <span>${escapeHtml(m.expected_artist)} &ndash; ${escapeHtml(m.expected_title)}</span>
                            </div>
                            <div class="mismatch-line mismatch-got">
                                <span class="mismatch-tag">Got</span>
                                <span>${escapeHtml(m.actual_artist || 'Unknown')} &ndash; ${escapeHtml(m.actual_title || 'Unknown')}</span>
                            </div>
                        </div>
                        <details class="mismatch-normalised">
                            <summary>Normalised</summary>
                            <div class="mismatch-norm-line"><span class="mismatch-tag">Exp</span> ${escapeHtml(m.exp_normalised)}</div>
                            <div class="mismatch-norm-line"><span class="mismatch-tag">Got</span> ${escapeHtml(m.got_normalised)}</div>
                        </details>
                        <div class="mismatch-actions">
                            ${m.copy ? `
                            <button class="mismatch-action-btn library-play-btn" data-mismatch-play="${m.id}" aria-label="Play or pause" title="Have a listen to the copy that came down">${_libraryPlayingId === `mismatch:${m.id}` ? '<i class="fa-solid fa-stop"></i>' : '<i class="fa-solid fa-play"></i>'}</button>
                            <button class="mismatch-action-btn" data-mismatch-action="restore" data-mismatch-id="${m.id}" title="Keep this copy: it goes into the playlist and the track is done">Restore</button>
                            ` : '<span class="mismatch-gone">This copy is no longer around, so Retry is the way forward.</span>'}
                            <button class="mismatch-action-btn" data-mismatch-action="retry" data-mismatch-id="${m.id}" title="${m.copy === 'library' ? 'Bin this copy and look for another' : 'Look for another copy'}. The name check stays on, so a wrong one turns up here again.">Retry</button>
                        </div>
                    </div>
                `).join('');

                content.querySelectorAll('[data-mismatch-play]').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const id = `mismatch:${btn.dataset.mismatchPlay}`;
                        if (_libraryPlayingId === id) { stopLibraryPlayback(); return; }
                        _startLibraryStream(id, `/api/mismatches/${btn.dataset.mismatchPlay}/stream`, btn);
                    });
                });

                // Listen first, then choose: Restore keeps that copy, Retry goes
                // and finds another.
                content.querySelectorAll('[data-mismatch-action]').forEach(btn => {
                    btn.addEventListener('click', async () => {
                        const mid = btn.dataset.mismatchId;
                        const action = btn.dataset.mismatchAction;
                        const row = btn.closest('.mismatch-row');
                        if (_libraryPlayingId === `mismatch:${mid}`) stopLibraryPlayback();
                        row.querySelectorAll('button').forEach(b => { b.disabled = true; });
                        try {
                            const res = await apiFetch(`/api/mismatches/${mid}/${action}`, { method: 'POST' });
                            const body = await res.json().catch(() => ({}));
                            if (res.status === 404 && body.detail === 'Mismatch not found') {
                                // Settled elsewhere already, by a Retry or a Restore from
                                // the Queue tab. Stale, not broken, so no crying wolf.
                                showToast('Already handled elsewhere');
                            } else if (!res.ok) {
                                throw new Error(body.detail || `HTTP ${res.status}`);
                            } else {
                                showToast(action === 'restore'
                                    ? 'Restored, and the playlist has it'
                                    : 'Gone looking for another copy');
                            }
                            row.remove();
                            setMismatchCount(content, content.querySelectorAll('.mismatch-row').length);
                        } catch (e) {
                            showToast(`${action === 'restore' ? 'Restore' : 'Retry'} failed: ${e.message}`, true);
                            row.querySelectorAll('button').forEach(b => { b.disabled = false; });
                        }
                    });
                });
            } catch {
                content.innerHTML = '<div class="empty-state"><p>Could not load the mismatch log.</p></div>';
            }
        }

        const clearMismatchesBtn = document.getElementById('clearMismatchesBtn');
        if (clearMismatchesBtn) {
            clearMismatchesBtn.addEventListener('click', async () => {
                if (!confirm('Clear the entire mismatch log?')) return;
                await apiFetch('/api/mismatches', { method: 'DELETE' });
                loadMismatches();
            });
        }

        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(1024));
            return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
        }

        function renderStats(data) {
            const successRate = data.total_jobs > 0
                ? Math.round((data.completed / data.total_jobs) * 100)
                : 0;
            const searchSuccessRate = data.total_searches > 0
                ? Math.round((data.successful_searches / data.total_searches) * 100)
                : 0;
            const searchToDownloadRate = data.total_searches > 0
                ? Math.round((data.converted_searches / data.total_searches) * 100)
                : 0;

            // Build daily chart (simple bar chart using divs)
            const maxDaily = Math.max(...data.daily.map(d => d.count), 1);
            const dailyBars = data.daily.length > 0
                ? data.daily.slice(-14).map(d => {
                    const height = Math.max(4, Math.round((d.count / maxDaily) * 80));
                    const dayLabel = d.day;
                    return `
                        <div style="display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; min-width: 0;">
                            <div style="font-size: 10px; color: var(--text-secondary);">${d.count}</div>
                            <div style="width: 100%; max-width: 24px; height: ${height}px; background: var(--accent); border-radius: 3px;"></div>
                            <div style="font-size: 9px; color: var(--text-secondary); white-space: nowrap;">${dayLabel}</div>
                        </div>
                    `;
                }).join('')
                : '<div style="text-align: center; color: var(--text-secondary); font-size: 13px; padding: 20px;">No downloads yet</div>';

            // Source breakdown: every source with downloads to its name, in the
            // registry's order, retired ones after; colours and names are the sources' own.
            const known = [...(_cachedSources || []).map(s => s.id), ...Object.keys(RETIRED_SOURCES)];
            const sourceOrder = id => (known.includes(id) ? known.indexOf(id) : known.length);
            const sourceCounts = Object.entries(data.sources || {})
                .filter(([, count]) => count > 0)
                .sort(([a], [b]) => sourceOrder(a) - sourceOrder(b));
            const swatch = id => escapeAttr(getSourceColour(id) || 'var(--text-secondary)');

            let html = `
                <!-- Summary cards -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 12px; margin-bottom: 16px;">
                    <div style="padding: 14px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; text-align: center;" title="Total downloads that completed successfully">
                        <div style="font-size: 22px; font-weight: 600;">${data.completed}</div>
                        <div style="font-size: 11px; color: var(--text-secondary);">Completed</div>
                    </div>
                    ${data.failed > 0 ? `
                    <button type="button" class="stats-card-link" ${uiAction('showQueueFailures', [Number(data.failed)])} title="Open the Queue showing only failed downloads, with their error details">
                        <div style="font-size: 22px; font-weight: 600; color: var(--error);">${data.failed}</div>
                        <div style="font-size: 11px; color: var(--text-secondary);">Failed <i class="fa-solid fa-arrow-right" aria-hidden="true"></i></div>
                    </button>` : `
                    <div style="padding: 14px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; text-align: center;" title="Downloads that failed. None, at the moment.">
                        <div style="font-size: 22px; font-weight: 600; color: var(--error);">0</div>
                        <div style="font-size: 11px; color: var(--text-secondary);">Failed</div>
                    </div>`}
                    <div style="padding: 14px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; text-align: center;" title="Percentage of all download attempts that completed successfully">
                        <div style="font-size: 22px; font-weight: 600;">${successRate}%</div>
                        <div style="font-size: 11px; color: var(--text-secondary);">Success rate</div>
                    </div>
                    ${data.scope === 'own' ? '' : `<div style="padding: 14px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; text-align: center;" title="Number of audio files in your library and total disk space used">
                        <div style="font-size: 22px; font-weight: 600;">${data.file_count == null ? (data.storage_scan_state === 'error' ? 'Unavailable' : 'Scanning…') : data.file_count}</div>
                        <div style="font-size: 11px; color: var(--text-secondary);">${data.storage_bytes == null ? (data.storage_scan_state === 'error' ? 'Scan failed; reopen Stats to retry' : 'Reading library storage') : formatBytes(data.storage_bytes)}${data.storage_bytes != null && data.storage_scan_state === 'refreshing' ? ' (refreshing)' : data.storage_bytes != null && data.storage_scan_state === 'error' ? ' (refresh failed)' : ''}</div>
                    </div>`}
                    <div style="padding: 14px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; text-align: center;" title="${searchSuccessRate}% of searches returned at least one result">
                        <div style="font-size: 22px; font-weight: 600;">${data.total_searches || 0}</div>
                        <div style="font-size: 11px; color: var(--text-secondary);">Searches</div>
                    </div>
                    <div style="padding: 14px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; text-align: center;" title="Percentage of searches that ended with you actually downloading something">
                        <div style="font-size: 22px; font-weight: 600;">${searchToDownloadRate}%</div>
                        <div style="font-size: 11px; color: var(--text-secondary);">Search → Download</div>
                    </div>
                </div>

                <!-- Search quality -->
                <div style="padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 16px;">
                    <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px;">Search Performance</div>
                    <div style="font-size: 13px; color: var(--text-secondary);">
                        Successful searches: <strong style="color: var(--text-primary);">${data.successful_searches || 0}</strong> /
                        ${data.total_searches || 0}
                        (${searchSuccessRate}% found at least one result)
                    </div>
                </div>

                <!-- Daily downloads chart -->
                <div style="padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 16px;">
                    <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 12px;">Downloads (last 14 days)</div>
                    <div style="display: flex; align-items: flex-end; gap: 4px; min-height: 100px;">
                        ${dailyBars}
                    </div>
                </div>

                <!-- Source breakdown -->
                <div style="padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 16px;">
                    <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 12px;">Sources</div>
                    <div style="display: flex; gap: var(--space-2); height: 8px; border-radius: 4px; overflow: hidden; margin-bottom: var(--space-2);">
                        ${sourceCounts.map(([id, count]) => `<div style="flex: ${count}; background: ${swatch(id)}; border-radius: 4px;"></div>`).join('')}
                    </div>
                    <div style="display: flex; gap: var(--space-4); font-size: 12px; flex-wrap: wrap;">
                        ${sourceCounts.map(([id, count]) => `<span style="color: var(--text-secondary);"><span style="display: inline-block; width: 8px; height: 8px; background: ${swatch(id)}; border-radius: 2px; margin-right: var(--space-1);"></span>${escapeHtml(getSourceLabel(id))}: ${count}</span>`).join('')}
                    </div>
                </div>
            `;

            // Top artists
            if (data.top_artists.length > 0) {
                const maxArtistCount = data.top_artists[0].count;
                html += `
                    <div style="padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 16px;">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 12px;">Top Artists</div>
                        ${data.top_artists.map((a, i) => `
                            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                                <span style="font-size: 11px; color: var(--text-secondary); width: 16px; text-align: right;">${i + 1}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(a.artist)}</span>
                                        <span style="font-size: 11px; color: var(--text-secondary); flex-shrink: 0;">${a.count}</span>
                                    </div>
                                    <div style="height: 4px; background: var(--bg-tertiary); border-radius: 2px; margin-top: 4px;">
                                        <div style="height: 100%; width: ${Math.round((a.count / maxArtistCount) * 100)}%; background: var(--accent); border-radius: 2px;"></div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            // Top searched artists
            if (data.top_searched_artists && data.top_searched_artists.length > 0) {
                const maxSearchCount = data.top_searched_artists[0].count;
                html += `
                    <div style="padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 16px;">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 12px;">Most Searched Artists</div>
                        ${data.top_searched_artists.map((a, i) => `
                            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                                <span style="font-size: 11px; color: var(--text-secondary); width: 16px; text-align: right;">${i + 1}</span>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(a.artist)}</span>
                                        <span style="font-size: 11px; color: var(--text-secondary); flex-shrink: 0;">${a.count}</span>
                                    </div>
                                    <div style="height: 4px; background: var(--bg-tertiary); border-radius: 2px; margin-top: 4px;">
                                        <div style="height: 100%; width: ${Math.round((a.count / maxSearchCount) * 100)}%; background: #f59e0b; border-radius: 2px;"></div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            // Recent downloads
            if (data.recent.length > 0) {
                html += `
                    <div style="padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px;">
                        <div style="font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 12px;">Recent Downloads</div>
                        ${data.recent.map(r => `
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 12px;">
                                <span class="source-badge ${escapeHtml(r.source || 'youtube')}" style="flex-shrink: 0;">${getSourceBadge(r.source || 'youtube')}</span>
                                <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(r.artist ? `${r.artist} - ${r.title}` : r.title)}</span>
                                <span style="margin-left: auto; color: var(--text-secondary); white-space: nowrap; flex-shrink: 0;">${r.completed_at ? formatTime(r.completed_at) : ''}</span>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            statsContent.innerHTML = `<div class="stats-reveal">${html}</div>`;
        }
