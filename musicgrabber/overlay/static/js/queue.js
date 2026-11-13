        // Queue tab: the download queue, Save to Device, Trash, and the per-job
        // actions and score rationale on queue cards.

        const expandedJobIds = new Set();
        const MAX_QUEUE_SIZE = 100;
        // Cards take one line on a computer (style.css, from 1024px), so a page
        // there can hold more of them without anybody reaching for the scroll wheel.
        const QUEUE_PAGE_SIZE_PHONE = 10;
        const QUEUE_PAGE_SIZE_DESKTOP = 25;
        const queueDesktopQuery = window.matchMedia?.('(min-width: 1024px)');
        let queuePage = 1;
        // Only the page on screen, already in the server's order. The rest of the
        // history stays on the server until somebody pages to it.
        let allQueueJobs = [];
        // How many jobs match the current search and filter, across all of it.
        let queueTotalMatches = 0;
        // A job a "later succeeded on retry" link asked for, until its page lands.
        let queueJumpTarget = null;
        let queueHistorySortMode = 'recent';
        let queueSearchTerm = '';
        let queueSearchDebounce = null;
        // One exact job status, filtered server-side. Only Stats sets it, so it
        // only ever says 'failed' for now, and the status line offers the way out.
        let queueStatusFilter = '';
        // What Stats counted when it sent us here. Stats sees every account; the
        // Queue sees yours, and a mismatch deserves a sentence, not a shrug.
        let queueStatsFailedCount = null;
        // Whole-queue status counts from the server, so the live summary keeps
        // telling the truth while a search has the visible list down to one card.
        let queueTotals = null;
        // Album imports busy before any of their tracks has a card: a Usenet
        // release downloading, say. Drawn above the cards so the Queue never
        // looks idle while something is 93% of the way through.
        let queueAlbumFetches = [];
        let queuePollInterval = null;
        let queueElapsedInterval = null;
        let queueLoadInFlight = false;
        let queueLastUpdatedAt = 0;
        let queueSummarySignature = '';
        document.getElementById('queueModePills')
            ?.addEventListener('pillchange', (e) => setQueueMode(e.detail.value));
        function activeCountFromTotals() {
            if (!queueTotals) return null;
            return (queueTotals.queued || 0) + (queueTotals.downloading || 0);
        }

        async function getQueueSize() {
            // Server totals, always: the loaded jobs are one page, not the queue.
            if (activeCountFromTotals() === null) {
                try {
                    const response = await apiFetch('/api/jobs?page=1&per_page=1');
                    if (response.ok) queueTotals = (await response.json()).queue_totals || null;
                } catch {}
            }
            return activeCountFromTotals() ?? 0;
        }

        function queuePageSize() {
            return queueDesktopQuery?.matches ? QUEUE_PAGE_SIZE_DESKTOP : QUEUE_PAGE_SIZE_PHONE;
        }

        // Crossing the breakpoint changes the page size; keep the first job on
        // screen on screen rather than jumping to whatever page N now means.
        queueDesktopQuery?.addEventListener?.('change', (event) => {
            const previousSize = event.matches ? QUEUE_PAGE_SIZE_PHONE : QUEUE_PAGE_SIZE_DESKTOP;
            queuePage = Math.floor(((queuePage - 1) * previousSize) / queuePageSize()) + 1;
            if (currentTab === 'queue' && queueMode === 'queue') loadJobs(false);
        });

        function stopQueuePolling() {
            if (queuePollInterval) {
                clearTimeout(queuePollInterval);
                queuePollInterval = null;
            }
            if (queueElapsedInterval) {
                clearInterval(queueElapsedInterval);
                queueElapsedInterval = null;
            }
        }

        function setQueueMode(mode) {
            queueMode = mode;
            showPillMode(queueTabContainer, mode);
            loadQueueMode();
        }

        // Loads whichever Queue pill is showing. Only the Download Queue polls;
        // the other two hold still until you come back to them.
        function loadQueueMode() {
            stopQueuePolling();
            if (queueMode === 'queue') {
                loadJobs().finally(scheduleQueuePoll);
                queueElapsedInterval = setInterval(updateLiveQueueTimes, 1000);
            } else if (queueMode === 'downloadable') {
                loadDownloadable();
            } else if (queueMode === 'trash') {
                loadTrash();
            }
        }

        function scheduleQueuePoll() {
            // An in-flight poll lands after you have switched pill, so check
            // both, or it re-arms itself behind your back.
            if (currentTab !== 'queue' || queueMode !== 'queue') return;
            if (queuePollInterval) clearTimeout(queuePollInterval);
            const activeTotal = activeCountFromTotals();
            const hasActiveJobs = queueAlbumFetches.length > 0 || (activeTotal !== null
                ? activeTotal > 0
                : allQueueJobs.some(job => ['queued', 'downloading'].includes(job.status)));
            // Stay snappy while work is moving, then back off when the queue is idle.
            const delay = hasActiveJobs ? 1500 : 5000;
            queuePollInterval = setTimeout(async () => {
                queuePollInterval = null;
                await loadJobs(false);
                scheduleQueuePoll();
            }, delay);
        }

        async function loadJobs(showLoading = true) {
            if (queueLoadInFlight) return;
            queueLoadInFlight = true;
            const requestedTerm = queueSearchTerm;
            const requestedStatus = queueStatusFilter;
            const requestedSort = queueHistorySortMode;
            const requestedSize = queuePageSize();
            let requestedPage = queuePage;
            let requestedFind = queueJumpTarget;
            const isOutdated = () => requestedTerm !== queueSearchTerm || requestedStatus !== queueStatusFilter
                || requestedSort !== queueHistorySortMode || requestedSize !== queuePageSize()
                || requestedPage !== queuePage || requestedFind !== queueJumpTarget;
            if (showLoading) {
                queueTab.innerHTML = `
                    <div class="loading loading-with-copy" role="status">
                        <div class="spinner"></div>
                        <span>Taking attendance…</span>
                    </div>
                `;
            }

            try {
                let url = `/api/jobs?page=${requestedPage}&per_page=${requestedSize}`
                    + `&sort=${encodeURIComponent(requestedSort)}`;
                if (requestedTerm) url += `&q=${encodeURIComponent(requestedTerm)}`;
                if (requestedStatus) url += `&status=${encodeURIComponent(requestedStatus)}`;
                if (requestedFind) url += `&find=${encodeURIComponent(requestedFind)}`;
                // Background polls drop the columns this tab never reads.
                if (!showLoading) url += '&slim=1';
                const response = await apiFetch(url);
                if (!response.ok) throw new Error('Failed to load jobs');

                const data = await response.json();
                if (isOutdated()) return;
                allQueueJobs = data.jobs;
                queueTotals = data.queue_totals || null;
                queueAlbumFetches = data.album_fetches || [];
                queueTotalMatches = data.total ?? data.jobs.length;
                // The server clamps a page past the end (jobs cleared under us),
                // and picks the page itself when it was asked to find a job.
                queuePage = requestedPage = data.page || 1;
                queueLastUpdatedAt = Date.now();
                const jumpedTo = requestedFind;
                if (jumpedTo) {
                    queueJumpTarget = requestedFind = null;
                    if (data.found) {
                        expandedJobIds.add(jumpedTo);
                    } else {
                        showToast(requestedTerm || requestedStatus
                            ? 'That entry is hidden by the current search or filter'
                            : 'That entry is no longer in the queue history', true);
                    }
                }
                renderQueueSummary();
                renderQueuePage();
                if (jumpedTo && data.found) highlightQueueJob(jumpedTo);
            } catch (error) {
                if (showLoading && !isOutdated()) {
                    queueTab.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon"><i class="fa-solid fa-circle-exclamation"></i></div>
                            <p>${error && error.status === 429
                                ? 'Too many requests, so the queue is being rate limited. Give it a moment and try again.'
                                : 'Failed to load queue'}</p>
                        </div>
                    `;
                }
            } finally {
                queueLoadInFlight = false;
                // A search or filter changed while we waited; fetch it now, however
                // long the previous request took to make up its mind.
                if (isOutdated()) await loadJobs(false);
            }
        }

        function secondsSince(isoString) {
            if (!isoString) return 0;
            const time = new Date(isoString).getTime();
            return Number.isFinite(time) ? Math.max(0, Math.floor((Date.now() - time) / 1000)) : 0;
        }

        function formatElapsedSeconds(seconds) {
            const secs = Math.max(0, Math.floor(seconds || 0));
            if (secs < 60) return `${secs}s`;
            const mins = Math.floor(secs / 60);
            if (mins < 60) return `${mins}m ${String(secs % 60).padStart(2, '0')}s`;
            const hours = Math.floor(mins / 60);
            return `${hours}h ${String(mins % 60).padStart(2, '0')}m`;
        }

        function _queueQuip(section, fallback) {
            const pool = (typeof QUEUE_QUIPS !== 'undefined' && QUEUE_QUIPS[section]) || null;
            return _randomQuip(pool, fallback);
        }

        function renderQueueSummary() {
            if (!queueLiveSummary) return;
            const totalJobs = queueTotals
                ? Object.values(queueTotals).reduce((sum, n) => sum + n, 0)
                : allQueueJobs.length;
            // A whole-album Usenet or torrent fetch has no jobs until it lands,
            // but it is very much not "all caught up".
            const fetching = queueAlbumFetches.length;
            if (!totalJobs && !fetching) {
                queueLiveSummary.style.display = 'none';
                queueSummarySignature = '';
                return;
            }
            const downloading = queueTotals
                ? (queueTotals.downloading || 0)
                : allQueueJobs.filter(job => job.status === 'downloading').length;
            const queued = queueTotals
                ? (queueTotals.queued || 0)
                : allQueueJobs.filter(job => job.status === 'queued').length;
            const active = downloading + queued + fetching;
            const signature = `${downloading}:${queued}:${fetching}`;
            if (signature !== queueSummarySignature) {
                const albums = `${fetching} album${fetching === 1 ? '' : 's'} arriving whole`;
                let headline;
                let aside;
                if (!downloading && !queued && fetching) {
                    headline = albums;
                    aside = _queueQuip('downloading', 'Tiny hammers, serious business.');
                } else if (downloading && queued) {
                    headline = `${downloading} on the workbench · ${queued} waiting`;
                    aside = _queueQuip('both', 'The conveyor belt is earning its keep.');
                } else if (downloading) {
                    headline = `${downloading} track${downloading === 1 ? '' : 's'} on the workbench`;
                    aside = _queueQuip('downloading', 'Tiny hammers, serious business.');
                } else if (queued) {
                    headline = `${queued} track${queued === 1 ? '' : 's'} waiting its turn`;
                    aside = _queueQuip('queued', 'Forming an orderly queue, naturally.');
                } else {
                    headline = 'All caught up';
                    aside = _queueQuip('idle', 'The queue has put its feet up.');
                }
                if (fetching && (downloading || queued)) headline += ` · ${albums}`;
                queueLiveSummary.innerHTML = `
                    <span class="queue-live-dot ${active ? 'active' : ''}" aria-hidden="true"></span>
                    <span class="queue-live-copy">
                        <strong>${headline}</strong>
                        <span>${aside}</span>
                    </span>
                    <span class="queue-live-updated" aria-hidden="true">Live · checked just now</span>
                `;
                queueSummarySignature = signature;
            }
            queueLiveSummary.style.display = 'flex';
            updateLiveQueueTimes();
        }

        function updateLiveQueueTimes() {
            document.querySelectorAll('.job-elapsed[data-start]').forEach(element => {
                element.textContent = formatElapsedSeconds(secondsSince(element.dataset.start));
            });
            const updated = queueLiveSummary?.querySelector('.queue-live-updated');
            if (updated && queueLastUpdatedAt) {
                const age = Math.floor((Date.now() - queueLastUpdatedAt) / 1000);
                const nextText = age < 2 ? 'Live · checked just now' : `Live · checked ${age}s ago`;
                if (updated.textContent !== nextText) {
                    updated.classList.add('is-changing');
                    setTimeout(() => {
                        if (!updated.isConnected) return;
                        updated.textContent = nextText;
                        updated.classList.remove('is-changing');
                    }, 140);
                }
            }
        }

        function renderQueuePage() {
            renderQueueAlbumFetches();
            renderJobs(allQueueJobs);

            const totalPages = Math.max(1, Math.ceil(queueTotalMatches / queuePageSize()));
            const pagerEl = document.getElementById('queuePager');
            const infoEl = document.getElementById('queuePagerInfo');
            const prevBtn = document.getElementById('queuePrevBtn');
            const nextBtn = document.getElementById('queueNextBtn');
            if (queueTotalMatches > 1) {
                pagerEl.style.display = 'flex';
                const noun = queueSearchTerm || queueStatusFilter ? 'matches' : 'jobs';
                infoEl.textContent = `Page ${queuePage} of ${totalPages} (${queueTotalMatches} ${noun})`;
                prevBtn.disabled = queuePage <= 1;
                nextBtn.disabled = queuePage >= totalPages;
            } else {
                pagerEl.style.display = 'none';
            }

            renderQueueSearchStatus();
        }

        function renderQueueAlbumFetches() {
            const el = document.getElementById('queueAlbumFetches');
            if (!el) return;
            // A search or a filter is about jobs, so these only join the plain view.
            const fetches = queueSearchTerm || queueStatusFilter ? [] : queueAlbumFetches;
            if (!fetches.length) {
                el.style.display = 'none';
                el.innerHTML = '';
                return;
            }
            el.innerHTML = fetches.map(fetch => albumFetchNoticeHtml(
                [fetch.artist, fetch.album].filter(Boolean).join(' - ') || 'An album', fetch.stage
            )).join('');
            el.style.display = '';
        }

        // One album import's "what I'm doing" line, shared with Bulk Import so
        // the two say it the same way.
        function albumFetchNoticeHtml(name, stage) {
            return `
                <div class="job-item album-fetch-notice">
                    <div class="job-status downloading"></div>
                    <div class="job-info">
                        <div class="job-title">${escapeHtml(name)}</div>
                        <div class="job-meta"><span class="job-status-label">${escapeHtml(stage || '')}</span></div>
                    </div>
                </div>`;
        }

        function renderQueueSearchStatus() {
            const statusEl = document.getElementById('queueSearchStatus');
            if (!statusEl) return;
            if (queueStatusFilter) {
                statusEl.innerHTML = queueStatusFilter === 'unsure'
                    ? queueUnsureFilterStatus()
                    : queueFailedFilterStatus();
                statusEl.style.display = 'block';
                return;
            }
            if (!queueSearchTerm) {
                // Unsure jobs wait on a human, so the plain view says they are there.
                const unsure = queueTotals ? (queueTotals.unsure || 0) : 0;
                if (unsure) {
                    statusEl.innerHTML = `<strong>${unsure}</strong> track${unsure === 1 ? '' : 's'} might already be in your library.`
                        + ' <button type="button" class="queue-search-status-action" data-queue-show-unsure>Sort them out</button>';
                    statusEl.style.display = 'block';
                    return;
                }
                statusEl.style.display = 'none';
                statusEl.innerHTML = '';
                return;
            }
            const count = queueTotalMatches;
            const term = escapeHtml(queueSearchTerm);
            if (!count) {
                statusEl.innerHTML = `Nothing in the queue matches &ldquo;${term}&rdquo;.`;
            } else {
                statusEl.innerHTML = `<strong>${count}</strong> match${count === 1 ? '' : 'es'} for &ldquo;${term}&rdquo; across the whole queue.`;
            }
            statusEl.style.display = 'block';
        }

        function queueFailedFilterStatus() {
            const count = queueTotalMatches;
            const forTerm = queueSearchTerm ? ` matching &ldquo;${escapeHtml(queueSearchTerm)}&rdquo;` : '';
            let text;
            if (!count) {
                text = `No failed downloads${forTerm}.`;
            } else {
                text = `<strong>${count}</strong> failed download${count === 1 ? '' : 's'}${forTerm} across your whole queue.`;
            }
            const yours = queueTotals ? (queueTotals.failed || 0) : null;
            if (queueStatsFailedCount !== null && yours !== null && queueStatsFailedCount > yours) {
                text += " Stats counts every account's failures; this list only holds yours.";
            }
            return `${text} <button type="button" class="queue-search-status-action" data-queue-clear-status>Show everything</button>`;
        }

        function queueUnsureFilterStatus() {
            const count = queueTotalMatches;
            const forTerm = queueSearchTerm ? ` matching &ldquo;${escapeHtml(queueSearchTerm)}&rdquo;` : '';
            const back = '<button type="button" class="queue-search-status-action" data-queue-clear-status>Show everything</button>';
            if (!count) return `Nothing left to decide${forTerm}. ${back}`;
            // The all-at-once answers are for every Unsure job, not this page or
            // this search, so they only appear when the list is everything.
            const all = queueSearchTerm ? '' : `
                <button type="button" class="queue-search-status-action" data-queue-resolve-all="same">Keep all mine</button>
                <button type="button" class="queue-search-status-action" data-queue-resolve-all="different">Download them all</button>`;
            return `<strong>${count}</strong> track${count === 1 ? '' : 's'}${forTerm} might already be in your library.`
                + ` Play your copy to check, then say.${all} ${back}`;
        }

        function showQueueUnsure() {
            queueStatusFilter = 'unsure';
            queueStatsFailedCount = null;
            queuePage = 1;
            loadJobs(false);
        }

        function showQueueFailures(statsCount) {
            queueStatusFilter = 'failed';
            queueStatsFailedCount = Number.isFinite(statsCount) ? statsCount : null;
            queuePage = 1;
            document.querySelector('[data-tab="queue"]')?.click();
            // The failures are on the Download Queue pill, whichever pill was last left up.
            document.querySelector('#queueModePills .pill[data-value="queue"]')?.click();
        }

        function clearQueueStatusFilter() {
            queueStatusFilter = '';
            queueStatsFailedCount = null;
            queuePage = 1;
            loadJobs(false);
        }

        function qualityDetailRows(quality) {
            if (!quality) return '';
            const match = String(quality).match(/^(.*?)\s+\(from\s+(.+)\)$/i);
            if (!match) {
                return `<div class="job-details-row"><span class="job-details-label">Stored:</span> ${escapeHtml(quality)}</div>`;
            }
            return `
                <div class="job-details-row"><span class="job-details-label">Stored:</span> ${escapeHtml(match[1])}</div>
                <div class="job-details-row"><span class="job-details-label">Original:</span> ${escapeHtml(match[2])}</div>
                <div class="job-details-row"><span class="job-details-label">Class:</span> Lossy source, transcoded</div>`;
        }

        function changeQueuePage(delta) {
            const totalPages = Math.max(1, Math.ceil(queueTotalMatches / queuePageSize()));
            const next = Math.max(1, Math.min(totalPages, queuePage + delta));
            if (next === queuePage) return;
            queuePage = next;
            loadJobs(false);
        }

        // Last rendered card per job id, per container: { html, el }.
        const jobCardCache = new WeakMap();

        function wireJobCard(card) {
            card.querySelectorAll('.delete-file-btn').forEach((btn) => {
                btn.addEventListener('click', (event) => {
                    event.stopPropagation();
                    deleteJobFile(btn.dataset.jobId || '', btn.dataset.trackName || '');
                });
            });

            card.querySelectorAll('.report-btn').forEach((btn) => {
                btn.addEventListener('click', (event) => {
                    event.stopPropagation();
                    openReportDialog(
                        btn.dataset.jobId || '',
                        btn.dataset.videoId || '',
                        btn.dataset.uploader || '',
                        btn.dataset.source || 'youtube'
                    );
                });
            });

            card.querySelectorAll('.edit-tags-btn').forEach((btn) => {
                btn.addEventListener('click', (event) => {
                    event.stopPropagation();
                    openTagEditor({
                        jobId: btn.dataset.jobId || '',
                        artist: btn.dataset.artist || '',
                        title: btn.dataset.title || '',
                        album: btn.dataset.album || '',
                    });
                });
            });
        }

        function renderJobs(jobs, container = queueTab) {
            if (!jobs.length) {
                if (container === queueTab) expandedJobIds.clear();
                // A search that found nothing is not an empty queue, and saying so
                // has sent more than one person hunting for a bug that isn't there.
                if (container === queueTab && queueStatusFilter === 'unsure') {
                    container.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon"><i class="fa-solid fa-circle-check"></i></div>
                            <p>Nothing left to decide${queueSearchTerm ? ` matching &ldquo;${escapeHtml(queueSearchTerm)}&rdquo;` : ''}</p>
                            <small>Every question answered. Decisive, aren't we?</small>
                        </div>
                    `;
                    return;
                }
                if (container === queueTab && queueStatusFilter) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon"><i class="fa-solid fa-circle-check"></i></div>
                            <p>No failed downloads${queueSearchTerm ? ` matching &ldquo;${escapeHtml(queueSearchTerm)}&rdquo;` : ''}</p>
                            <small>Either everything worked or somebody tidied up. Both are fine.</small>
                        </div>
                    `;
                    return;
                }
                if (container === queueTab && queueSearchTerm) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-state-icon"><i class="fa-solid fa-magnifying-glass"></i></div>
                            <p>No matches for &ldquo;${escapeHtml(queueSearchTerm)}&rdquo;</p>
                            <small>Try less of the title, or check the spelling. We all do it.</small>
                        </div>
                    `;
                    return;
                }
                // An album on its way has its own notice above; "suspiciously
                // quiet" underneath it would be a lie.
                if (container === queueTab && queueAlbumFetches.length) {
                    container.innerHTML = '';
                    return;
                }
                container.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon"><i class="fa-solid fa-inbox"></i></div>
                        <p>No downloads yet</p>
                        <small>Quiet in here. Suspiciously quiet.</small>
                    </div>
                `;
                return;
            }

            const visibleJobIds = new Set(jobs.map(j => j.id));
            if (container === queueTab) {
                // expandedJobIds tracks the Queue tab's own card state; a render
                // into a different container (e.g. Bulk Import) must not prune
                // ids just because they're not part of its own smaller job set.
                for (const id of Array.from(expandedJobIds)) {
                    if (!visibleJobIds.has(id)) expandedJobIds.delete(id);
                }
            }

            const renderCard = job => {
                if (job.status === 'unsure') return unsureCardHtml(job);
                const hasDetails = job.status === 'completed' || job.status === 'completed_with_errors' || job.status === 'failed';
                const sourceLabel = getSourceLabel(job.source || 'youtube');
                const sourceUrl = job.source_url || '';
                const isClickableUrl = sourceUrl.startsWith('https://');
                const fileDeleted = Number(job.file_deleted || 0) === 1;
                const isActive = job.status === 'queued' || job.status === 'downloading';
                const alreadyInLibrary = (job.error || '').startsWith('Already exists');
                const activeStage = job.status === 'queued'
                    ? 'Waiting its turn'
                    : (job.progress_stage || 'Getting organised');
                const elapsedHtml = isActive
                    ? `<span class="job-elapsed-wrap">for <span class="job-elapsed" data-start="${escapeAttr(job.created_at || '')}"></span></span>`
                    : '';
                const acquisitionAttempts = Array.isArray(job.acquisition_attempts)
                    ? job.acquisition_attempts.filter(a => a && a.source)
                    : [];
                const sourceJourney = acquisitionAttempts.length
                    ? acquisitionAttempts.map(a => a.source)
                    : (Array.isArray(job.source_history) ? job.source_history.filter(Boolean) : []);
                const journeyHtml = sourceJourney.length > 1
                    ? sourceJourney.map((source, index) =>
                        `${index ? '<span class="job-journey-arrow">→</span>' : ''}<span class="source-badge ${escapeHtml(source)}">${getSourceBadge(source)}</span>`
                    ).join('')
                    : '';
                const attemptHistoryHtml = acquisitionAttempts.length
                    ? acquisitionAttempts.slice(-8).map(attempt => `
                        <div class="job-details-row">
                            <span class="job-details-label">Cycle ${escapeHtml(String(attempt.cycle_number || '?'))}:</span>
                            <span class="source-badge ${escapeHtml(attempt.source || '')}">${getSourceBadge(attempt.source || '')}</span>
                            ${escapeHtml(attempt.status || '')}${attempt.error ? `: ${escapeHtml(attempt.error)}` : ''}
                        </div>`).join('')
                    : '';
                return `
                <div class="job-item ${hasDetails ? 'has-details' : ''}" data-job-id="${escapeHtml(job.id || '')}" ${hasDetails ? 'data-ui-click="toggleJobDetails"' : ''}>
                    <div class="job-status ${job.status}"></div>
                    <div class="job-info">
                        <div class="job-head">
                            <div class="job-title">${escapeHtml(job.artist ? `${job.artist} - ${job.title}` : job.title)}${job.status === 'completed_with_errors' ? '<span class="job-warning-badge">ISSUES</span>' : ''}${job.download_type === 'upgrade' ? '<span class="job-upgrade-badge">UPGRADE</span>' : ''}</div>
                            <div class="job-meta">
                                <span class="job-status-label">${escapeHtml(formatJobStatus(job.status))}</span>
                                ${isActive ? `<span class="job-progress-stage">${escapeHtml(activeStage)}</span>${elapsedHtml}` : ''}
                                <span class="job-date">· ${formatTime(job.created_at)}</span>
                            </div>
                            ${alreadyInLibrary ? '<div class="job-error job-note">Already in library</div>' : ''}
                            <span class="source-badge job-source-badge ${job.source || 'youtube'}">${getSourceBadge(job.source || 'youtube')}</span>
                        </div>
                        ${job.error && !alreadyInLibrary ? `<div class="job-error">${escapeHtml(job.error)}</div>` : ''}
                        ${hasDetails ? `
                        <div class="job-details" style="display:none;">
                            ${qualityDetailRows(job.audio_quality)}
                            ${alreadyInLibrary ? `<div class="job-details-row"><span class="job-details-label">Path:</span> <span class="job-details-url">${escapeHtml(job.error.replace(/^Already exists(?: in [^:]+)?:\s*/, '').replace(/ \(added to playlist\)$/, ''))}</span></div>` : ''}
                            <div class="job-details-row"><span class="job-details-label">Source:</span> ${escapeHtml(sourceLabel)}</div>
                            ${journeyHtml ? `<div class="job-details-row job-journey"><span class="job-details-label">Journey:</span> ${journeyHtml}</div>` : ''}
                            ${job.acquisition_attempt_count ? `<div class="job-details-row"><span class="job-details-label">Acquisition:</span> ${escapeHtml(String(job.acquisition_cycle_count || 0))} cycle${Number(job.acquisition_cycle_count || 0) === 1 ? '' : 's'} · ${escapeHtml(String(job.acquisition_attempt_count))} source attempt${Number(job.acquisition_attempt_count) === 1 ? '' : 's'}${job.acquisition_last_attempt_at ? ` · last ${formatTime(job.acquisition_last_attempt_at)}` : ''}</div>` : ''}
                            ${attemptHistoryHtml}
                            ${job.acquisition_superseded_by ? `<div class="job-details-row job-superseded-note"><i class="fa-solid fa-circle-check"></i> Later succeeded on retry; <a href="#" ${uiAction('jumpToJobStopped', [job.acquisition_superseded_by])}>jump to completed entry</a></div>` : ''}
                            ${job.metadata_source ? `<div class="job-details-row"><span class="job-details-label">Metadata:</span> ${escapeHtml(formatMetadataSource(job.metadata_source))}</div>` : ''}
                            ${job.requested_video_fallback ? '<div class="job-details-row"><span class="job-details-label">Fallback:</span> Used the video from the original YouTube playlist after no confident alternative succeeded.</div>' : ''}
                            ${sourceUrl ? `<div class="job-details-row"><span class="job-details-label">URL:</span> ${isClickableUrl ? `<a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener" data-ui-click="stopPropagation">${escapeHtml(sourceUrl)}</a>` : `<span class="job-details-url">${escapeHtml(sourceUrl)}</span>`}</div>` : ''}
                            <div class="job-details-row"><span class="job-details-label">Queued:</span> ${formatTimeFull(job.created_at)}</div>
                            ${job.completed_at ? `<div class="job-details-row"><span class="job-details-label">Completed:</span> ${formatTimeFull(job.completed_at)}</div>` : ''}
                            ${job.completed_at && job.created_at ? `<div class="job-details-row"><span class="job-details-label">Took:</span> ${formatDuration(job.created_at, job.completed_at)}</div>` : ''}
                            ${['failed', 'completed_with_errors'].includes(job.status) || (job.error || '').includes('mismatch') ? `
                            <div id="score-rationale-link-${escapeHtml(job.id || '')}" class="job-details-row" style="margin-top:4px;">
                                <a href="#" ${uiAction('loadScoreRationaleStopped', [job.id || ''])} style="font-size:12px; color:var(--accent); text-decoration:none;">Why this result?</a>
                                <button class="score-rationale-copy" ${uiAction('copyScoreRationaleStopped', [job.id || ''])} style="margin-left:8px;" title="Copy scoring rationale to clipboard"><i class="fa-solid fa-clipboard"></i> Copy</button>
                            </div>
                            <div id="score-rationale-${escapeHtml(job.id || '')}" style="display:none;"></div>
                            ` : ''}
                            <div style="display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap;">
                                ${job.status !== 'failed' && !fileDeleted ? `<button class="library-play-btn" aria-label="Play or pause" title="Play or pause" ${uiAction('playJobAudioStopped', [job.id || ''])} style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--accent); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;"><i class="fa-solid fa-play"></i></button>` : ''}
                                ${job.status === 'failed' && job.acquisition_mode === 'automatic'
                                    ? `<button ${uiAction('retryNextJobStopped', [job.id || ''])} style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--accent); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;">Retry next option</button>
                                       <button ${uiAction('openJobRescueVersionsStopped', [job.id || ''])} style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;">Choose version</button>`
                                    : (job.download_type === 'upgrade' ? '' : `<button ${uiAction('redownloadJobStopped', [job.id || ''])} style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--accent); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;">Re-download</button>`)}
                                <button class="report-btn" data-job-id="${escapeHtml(job.id || '')}" data-video-id="${escapeHtml(job.video_id || '')}" data-uploader="${escapeHtml(job.uploader || '')}" data-source="${escapeHtml(job.source || 'youtube')}" data-ui-click="stopPropagation" style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--warning); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;">Report</button>
                                ${(job.status === 'completed' || job.status === 'completed_with_errors') && !fileDeleted ? `<button class="edit-tags-btn" data-job-id="${escapeHtml(job.id || '')}" data-artist="${escapeAttr(job.artist || '')}" data-title="${escapeAttr(job.title || '')}" data-album="${escapeAttr(job.album_name || '')}" data-ui-click="stopPropagation" style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--accent); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;">Edit Tags</button>` : ''}
                                ${job.status !== 'failed' ? (fileDeleted
                                    ? `<button disabled style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-secondary); color: var(--text-muted); border: 1px solid var(--border); border-radius: 6px; cursor: not-allowed; opacity: 0.8;">Trashed</button>`
                                    : `<button class="delete-file-btn" data-job-id="${escapeHtml(job.id || '')}" data-track-name="${escapeHtml(job.artist ? job.artist + ' - ' + job.title : job.title)}" data-ui-click="stopPropagation" style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--error); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;"><i class="fa-solid fa-trash-can"></i> Trash</button>
                                      <button ${uiAction('saveJobToDeviceStopped', [job.id || ''])} style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;"><i class="fa-solid fa-download"></i> Save to device</button>`) : ''}
                            </div>
                        </div>` : ''}
                    </div>
                </div>`;
            };

            // Swap only the cards whose markup changed. Rebuilding the whole list
            // every poll cost you text selection, keyboard focus, and any click
            // whose press and release straddled a refresh. The elapsed clock is
            // left empty in the markup (updateLiveQueueTimes fills it), so a
            // ticking second is not a reason to replace a card.
            let cards = jobCardCache.get(container);
            const cachedNodes = cards ? Array.from(cards.values()) : [];
            if (!cards || container.children.length !== cards.size
                || cachedNodes.some(c => c.el.parentNode !== container)) {
                // Something else wrote to the container (spinner, empty state), so
                // start again from a clean slate rather than trust the cache.
                container.innerHTML = '';
                cards = new Map();
            }
            const next = new Map();
            const template = document.createElement('template');
            jobs.forEach((job, index) => {
                let key = String(job.id);
                if (next.has(key)) key += `#${index}`;
                const html = renderCard(job).trim();
                const previous = cards.get(key);
                if (previous && previous.html === html) {
                    next.set(key, previous);
                } else {
                    template.innerHTML = html;
                    const el = template.content.firstElementChild;
                    wireJobCard(el);
                    next.set(key, { html, el });
                }
                // Expansion lives in expandedJobIds and the DOM, not in the markup,
                // so clicking a card open does not make it look "changed".
                const card = next.get(key).el;
                const details = card.querySelector('.job-details');
                if (details) {
                    const open = expandedJobIds.has(job.id);
                    details.style.display = open ? 'block' : 'none';
                    card.classList.toggle('expanded', open);
                }
            });
            // Clear out what is gone or replaced first, then slot everything into
            // order; cards that are already in the right place are never touched.
            const keep = new Set(Array.from(next.values(), c => c.el));
            for (const c of cachedNodes) {
                if (!keep.has(c.el) && c.el.parentNode === container) c.el.remove();
            }
            let cursor = container.firstElementChild;
            for (const { el } of next.values()) {
                if (el === cursor) cursor = cursor.nextElementSibling;
                else container.insertBefore(el, cursor);
            }
            jobCardCache.set(container, next);

            updateLiveQueueTimes();
        }

        function formatJobStatus(status) {
            if (status === 'completed_with_errors') {
                return 'completed (with errors)';
            }
            return status;
        }

        // An import found something in the library that might be this track
        // (GitLab #109). Play is the library's copy, so it can be judged by ear.
        function unsureCardHtml(job) {
            const id = job.id || '';
            const name = job.artist ? `${job.artist} - ${job.title}` : (job.title || '');
            const has = (job.error || '').replace(/^Might already be in your library as /, '');
            return `
                <div class="job-item has-details job-unsure" data-job-id="${escapeHtml(id)}" data-ui-click="toggleJobDetails">
                    <div class="job-status unsure"></div>
                    <div class="job-info">
                        <div class="job-head">
                            <div class="job-title">${escapeHtml(name)}</div>
                            <div class="job-meta">
                                <span class="job-status-label">unsure</span>
                                <span class="job-date">· ${formatTime(job.created_at)}</span>
                            </div>
                        </div>
                        <div class="job-error job-note">Your library has ${escapeHtml(has || 'something close')}. Same track?</div>
                        <div class="job-unsure-actions">
                            <button type="button" class="btn btn-sm library-play-btn" aria-label="Play your copy" title="Play your copy" ${uiAction('playJobAudioStopped', [id])}><i class="fa-solid fa-play"></i></button>
                            <button type="button" class="btn btn-sm" ${uiAction('resolveUnsureStopped', [id, 'same'])}>Same, keep mine</button>
                            <button type="button" class="btn btn-sm" ${uiAction('resolveUnsureStopped', [id, 'different'])}>Different, download it</button>
                        </div>
                        <div class="job-details" style="display:none;">
                            ${job.library_copy ? `<div class="job-details-row"><span class="job-details-label">Your copy:</span> <span class="job-details-url">${escapeHtml(job.library_copy)}</span></div>` : ''}
                            <div class="job-details-row"><span class="job-details-label">Asked:</span> ${formatTimeFull(job.created_at)}</div>
                        </div>
                    </div>
                </div>`;
        }

        // job_ids null means every Unsure job you can see, not just this page.
        async function resolveUnsure(jobIds, verdict) {
            try {
                const response = await apiFetch('/api/jobs/unsure/resolve', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(jobIds ? { verdict, job_ids: jobIds } : { verdict }),
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.detail || 'That answer did not go in');
                const n = data.resolved || 0;
                if (!n) {
                    showToast('Already answered, by the look of it');
                } else if (verdict === 'same') {
                    showToast(n === 1 ? 'Kept the copy you have' : `Kept the ${n} copies you have`);
                } else {
                    showToast(n === 1 ? 'Off to find it' : `Off to find all ${n}`);
                }
            } catch (error) {
                showToast(error.message || 'That answer did not go in', true);
            }
            if (currentTab === 'queue') loadJobs(false);
            if (typeof refreshShownBulkImport === 'function') refreshShownBulkImport();
        }

        function formatMetadataSource(metadataSource) {
            const source = (metadataSource || '').toLowerCase();
            const labels = {
                'acoustid_fingerprint': 'AcoustID fingerprint',
                'musicbrainz_text': 'MusicBrainz text match',
                'musicbrainz_tracklist': 'MusicBrainz tracklist',
                'youtube_guessed': 'YouTube embedded/guessed',
                'soundcloud_guessed': 'SoundCloud embedded/guessed',
                'mp3phoenix_guessed': 'MP3Phoenix embedded/guessed',
                'zvu4no_guessed': 'zvu4no embedded/guessed',
                'freemp3cloud_guessed': 'FreeMp3Cloud embedded/guessed',
                'jiosaavn_guessed': 'JioSaavn embedded/guessed',
                'soulseek_guessed': 'Soulseek embedded/guessed',
            };
            return labels[source] || metadataSource;
        }

        function formatDateYmd(isoString) {
            if (!isoString) return '';
            const normalized = /Z$|[+-]\d{2}:\d{2}$/.test(isoString) ? isoString : `${isoString.replace(' ', 'T')}Z`;
            const date = new Date(normalized);
            if (Number.isNaN(date.getTime())) return '';
            const y = date.getFullYear();
            const m = String(date.getMonth() + 1).padStart(2, '0');
            const d = String(date.getDate()).padStart(2, '0');
            return `${y}-${m}-${d}`;
        }

        function formatTime(isoString) {
            return formatDateYmd(isoString);
        }

        function toggleJobDetails(el) {
            const details = el.querySelector('.job-details');
            if (details) {
                const isOpen = details.style.display !== 'none';
                details.style.display = isOpen ? 'none' : 'block';
                el.classList.toggle('expanded', !isOpen);
                const jobId = el.dataset.jobId;
                if (jobId) {
                    if (isOpen) expandedJobIds.delete(jobId);
                    else expandedJobIds.add(jobId);
                }
            }
        }

        // Follows a "later succeeded on retry" pointer from an old failed card to
        // the job that actually finished the download. Retries always land on a
        // new Queue row, so this may be on a different page or sorted elsewhere.
        function jumpToJob(jobId) {
            if (!allQueueJobs.some(j => String(j.id) === String(jobId))) {
                // Not on this page; the server knows which one it is on.
                queueJumpTarget = String(jobId);
                loadJobs(false);
                return;
            }
            expandedJobIds.add(String(jobId));
            renderQueuePage();
            highlightQueueJob(jobId);
        }

        function highlightQueueJob(jobId) {
            requestAnimationFrame(() => {
                const el = queueTab.querySelector(`.job-item[data-job-id="${jobId}"]`);
                if (!el) return;
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                el.classList.add('job-jump-highlight');
                setTimeout(() => el.classList.remove('job-jump-highlight'), 1600);
            });
        }

        // =============================================================================
        // Score Rationale (why the scorer picked a particular result)
        // =============================================================================

        const SCORE_LABELS = {
            "base": null,
            "official_title": "Official title tag",
            "official_channel": "Official channel",
            "official_video": "Official music video",
            "official_audio": "Official audio",
            "topic_channel": "Topic channel",
            "live_requested": "Live version (requested)",
            "live_variant": "Live/session penalty",
            "live_channel": "Live channel penalty",
            "junk_variant": "Junk variant (karaoke/nightcore/etc.)",
            "bootleg_edit": "Bootleg/fan edit",
            "cover_or_variant": "Cover/remix/instrumental",
            "lyric_video": "Lyric video",
            "unofficial_title": "Unofficial/fan upload",
            "unofficial_channel": "Fan/tribute channel",
            "copyright_dodge": "Copyright-dodging upload",
            "channel_in_title": "Channel name in title",
            "query_full_coverage": "All search terms matched",
            "query_good_coverage": "Most search terms matched",
            "query_poor_coverage": "Few search terms matched",
            "title_match": "Exact title match",
            "title_overlap_full": "Strong title overlap",
            "title_overlap_strong": "Good title overlap",
            "title_mismatch": "Title mismatch",
            "artist_in_title": "Artist in title",
            "artist_in_channel": "Artist matches channel",
            "artist_match": "Artist matched",
            "artist_overlap": "Partial artist match",
            "artist_mismatch": "Artist mismatch",
            "artist_title_phrase": "Artist + title phrase match",
            "plain_title": "Plain studio title",
            "variant_suffix": "Variant suffix penalty",
            "reaction_or_compilation": "Reaction/compilation",
            "compilation_album": "Compilation album",
            "extended_version": "Extended version",
            "non_song_result": "Non-song result",
            "reverb": "Reverb edit",
            "duration_too_short": "Way too short",
            "duration_short": "Very short",
            "duration_brief": "Slightly short",
            "duration_sweet_spot": "Good duration",
            "duration_long": "Suspiciously long",
            "duration_very_long": "Way too long",
            "low_views": "Low views",
            "good_views": "Decent view count",
            "huge_views": "Very popular",
            "mb_duration_exact": "MusicBrainz duration match",
            "mb_duration_close": "Close to MusicBrainz duration",
            "mb_duration_off": "Duration doesn't match MusicBrainz",
            "mb_duration_way_off": "Duration way off MusicBrainz",
            "mb_search_duration": "MusicBrainz duration scoring",
            "source_quality": "Source quality bonus",
            "free_slot": "Free download slot",
            "fast_uploader": "Fast uploader",
            "popularity": "Popularity bonus",
        };

        function parseBreakdownEntry(entry) {
            // "live_variant=-180" → { key: "live_variant", delta: -180, label: "Live/session penalty" }
            const m = (entry || '').match(/^([a-z_]+)=([+-]?\d+)$/);
            if (!m) return null;
            const key = m[1];
            if (SCORE_LABELS[key] === null) return null;  // hidden (e.g. "base")
            return {
                key,
                delta: parseInt(m[2], 10),
                label: SCORE_LABELS[key] || key.replace(/_/g, ' '),
            };
        }

        function humaniseBreakdown(breakdown, topN) {
            const parsed = (breakdown || [])
                .map(parseBreakdownEntry)
                .filter(Boolean)
                .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
            const items = topN ? parsed.slice(0, topN) : parsed;
            return items.map(p => {
                const cls = p.delta >= 0 ? 'score-reason-positive' : 'score-reason-negative';
                const sign = p.delta >= 0 ? '+' : '';
                return `<span class="${cls}">${escapeHtml(p.label)} (${sign}${p.delta})</span>`;
            }).join(', ');
        }

        function renderRationalePanel(data) {
            const d = data.decision || {};
            const selected = d.selected;
            const runnersUp = d.runners_up || [];
            if (!selected) return '';

            let html = '<div class="score-rationale">';
            html += '<div class="score-rationale-header">';
            if (data.query) {
                html += `<span class="score-rationale-query">Search: ${escapeHtml(data.query)}</span>`;
            }
            html += '</div>';

            // Winner
            html += '<div class="score-rationale-candidate score-rationale-picked">';
            html += '<div class="score-rationale-candidate-header">';
            html += `<span class="score-rationale-label">Picked</span>`;
            html += `<span class="source-badge ${escapeHtml(selected.source || 'youtube')}" style="font-size:10px;padding:1px 6px;">${getSourceBadge(selected.source || 'youtube')}</span>`;
            html += `<span class="score-rationale-title">${escapeHtml(selected.channel || '')}${selected.channel ? ' \u2013 ' : ''}${escapeHtml(selected.title || '')}</span>`;
            html += `<span class="score-rationale-score">score ${selected.score != null ? selected.score : '?'}</span>`;
            html += '</div>';
            const selectedReasons = humaniseBreakdown(selected.breakdown, 5);
            if (selectedReasons) {
                html += `<div class="score-rationale-reasons">${selectedReasons}</div>`;
            }
            html += '</div>';

            // Runners-up
            runnersUp.forEach((ru, i) => {
                html += '<div class="score-rationale-candidate score-rationale-runnerup">';
                html += '<div class="score-rationale-candidate-header">';
                html += `<span class="score-rationale-label">#${i + 2}</span>`;
                html += `<span class="source-badge ${escapeHtml(ru.source || 'youtube')}" style="font-size:10px;padding:1px 6px;">${getSourceBadge(ru.source || 'youtube')}</span>`;
                html += `<span class="score-rationale-title">${escapeHtml(ru.channel || '')}${ru.channel ? ' \u2013 ' : ''}${escapeHtml(ru.title || '')}</span>`;
                html += `<span class="score-rationale-score">score ${ru.score != null ? ru.score : '?'}</span>`;
                html += '</div>';
                const ruReasons = humaniseBreakdown(ru.breakdown, 3);
                if (ruReasons) {
                    html += `<div class="score-rationale-reasons">${ruReasons}</div>`;
                }
                html += '</div>';
            });

            // Raw scoring expander
            const allBreakdowns = [];
            allBreakdowns.push(`Picked: ${(selected.breakdown || []).join(', ')}`);
            runnersUp.forEach((ru, i) => {
                allBreakdowns.push(`#${i + 2}: ${(ru.breakdown || []).join(', ')}`);
            });
            html += '<details class="score-rationale-raw">';
            html += '<summary>Raw scoring</summary>';
            html += `<pre>${escapeHtml(allBreakdowns.join('\n'))}</pre>`;
            html += '</details>';

            html += '</div>';
            return html;
        }

        async function loadScoreRationale(jobId) {
            const container = document.getElementById(`score-rationale-${jobId}`);
            const link = document.getElementById(`score-rationale-link-${jobId}`);
            if (!container) return;

            // Already loaded?
            if (container.dataset.loaded === 'true') {
                container.style.display = container.style.display === 'none' ? 'block' : 'none';
                return;
            }

            try {
                const res = await apiFetch(`/api/jobs/${jobId}/score-rationale`);
                if (!res.ok) {
                    // No data for this job; hide the link entirely
                    if (link) link.style.display = 'none';
                    return;
                }
                const data = await res.json();
                container.innerHTML = renderRationalePanel(data);
                container.dataset.loaded = 'true';
                container.style.display = 'block';
            } catch {
                if (link) link.style.display = 'none';
            }
        }

        function copyScoreRationale(jobId) {
            // Fetches fresh rather than relying on the "Why this result?" panel
            // having been opened first; Copy used to silently do nothing if you
            // reached for it before that click had populated the cache.
            apiFetch(`/api/jobs/${jobId}/score-rationale`)
                .then(res => res.ok ? res.json() : null)
                .then(data => {
                    if (!data) { showToast('No scoring rationale recorded for this job', true); return; }
                    const d = data.decision || {};
                    const sel = d.selected;
                    if (!sel) { showToast('No scoring rationale recorded for this job', true); return; }

                    let text = '';
                    if (data.query) text += `Search: ${data.query}\n`;
                    text += `\nPicked: [${sel.source}] ${sel.channel} - ${sel.title}\n`;
                    text += `Score: ${sel.score}\n`;
                    text += `Breakdown: ${(sel.breakdown || []).join(', ')}\n`;

                    const runners = d.runners_up || [];
                    if (runners.length) {
                        text += `\nRunners-up:\n`;
                        runners.forEach((ru, i) => {
                            text += `  #${i + 2}: [${ru.source}] ${ru.channel} - ${ru.title} (score ${ru.score})\n`;
                            text += `  Breakdown: ${(ru.breakdown || []).join(', ')}\n`;
                        });
                    }

                    navigator.clipboard.writeText(text.trim()).then(() => {
                        showToast('Score rationale copied');
                    });
                })
                .catch(() => showToast('Could not fetch scoring rationale', true));
        }

        async function redownloadJob(jobId) {
            try {
                showToast('Re-downloading...');
                const response = await apiFetch(`/api/jobs/${jobId}/retry`, { method: 'POST' });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || 'Re-download failed');
                }
                showToast('Queued for re-download');
                loadJobs();
            } catch (error) {
                showToast(error.message || 'Re-download failed', true);
            }
        }

        async function retryNextJob(jobId) {
            try {
                showToast('Finding the next allowed option...');
                const response = await apiFetch(`/api/jobs/${jobId}/retry-next`, { method: 'POST' });
                if (!response.ok) {
                    const data = await response.json().catch(() => ({}));
                    throw new Error(data.detail || 'Retry failed');
                }
                showToast('Queued a new rescue attempt');
                loadJobs();
            } catch (error) {
                showToast(error.message || 'Retry failed', true);
            }
        }

        async function deleteJobFile(jobId, trackName) {
            if (!confirm(`Move "${trackName}" to trash?`)) return;

            try {
                const response = await apiFetch(`/api/jobs/${jobId}/file`, { method: 'DELETE' });
                if (!response.ok) {
                    // 409 (left alone, it no longer vets) and 500 (the bin refused)
                    // both explain themselves in detail; pass that on as it is.
                    const data = await response.json().catch(() => ({}));
                    throw new Error(data.detail || 'Delete failed');
                }
                const data = await response.json();
                if (data.trashed) {
                    showToast(`Moved to trash (${data.deleted.length} file(s))`);
                } else if (data.deleted.length > 0) {
                    showToast(`Deleted ${data.deleted.length} file(s)`);
                } else {
                    showToast(data.message || 'File was already missing, marked as deleted');
                }
                loadJobs();
                loadTrash();
            } catch (error) {
                showToast(error.message || 'Delete failed', true);
                loadJobs();
            }
        }

        // =============================================================================
        // Trash Bin
        // =============================================================================

        async function loadTrash() {
            const list = document.getElementById('trashList');
            const emptyBtn = document.getElementById('emptyTrashBtn');
            try {
                const response = await apiFetch('/api/trash');
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.detail || 'Failed to load trash');
                }

                emptyBtn.disabled = !data.files.length;
                if (!data.files.length) {
                    list.innerHTML = '<div class="empty-state"><p>The bin is empty. Anything you delete waits here first, in case you change your mind.</p></div>';
                    return;
                }

                const sizeLabel = formatFileSize(data.total_size);

                list.innerHTML = `
                    <div style="margin-bottom: 8px; font-size: 12px; color: var(--text-muted);">
                        ${data.files.length} file(s), ${sizeLabel} total
                    </div>
                    ${data.files.map(f => `
                        <div class="job-item" style="cursor: default;">
                            <div class="job-status completed"></div>
                            <div class="job-info">
                                <div class="job-title">${escapeHtml(f.name)}</div>
                                <div class="job-meta">${escapeHtml(f.path)} &middot; ${formatFileSize(f.size)}</div>
                            </div>
                            <div style="display: flex; gap: 6px; align-items: center; flex-shrink: 0;">
                                <button class="library-play-btn" aria-label="Play or pause" title="Play or pause" ${uiAction('playTrashAudio', [f.path])} style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--accent); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;"><i class="fa-solid fa-play"></i></button>
                                <button ${uiAction('restoreTrashFile', [f.path])} style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--accent); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;">Restore</button>
                                <button ${uiAction('deleteTrashFile', [f.path, f.name])} style="padding: 6px 12px; font-size: 11px; font-family: inherit; font-weight: 600; background: var(--bg-tertiary); color: var(--error); border: 1px solid var(--border); border-radius: 6px; cursor: pointer;">Delete</button>
                            </div>
                        </div>
                    `).join('')}
                `;
            } catch (e) {
                console.error('Failed to load trash', e);
                list.innerHTML = `
                    <div class="job-item" style="cursor: default;">
                        <div class="job-info">
                            <div class="job-title">Trash unavailable</div>
                            <div class="job-meta">${escapeHtml(e?.message || 'Failed to load trash')}</div>
                        </div>
                    </div>
                `;
            }
        }

        async function restoreTrashFile(path) {
            try {
                const response = await apiFetch(`/api/trash/restore?path=${encodeURIComponent(path)}`, { method: 'POST' });
                if (!response.ok) {
                    // 409 means something already sits at the original path.
                    const data = await response.json().catch(() => ({}));
                    throw new Error(data.detail || 'Restore failed');
                }
                const data = await response.json();
                showToast(`Restored: ${data.restored}`);
                loadTrash();
            } catch (error) {
                showToast(error.message || 'Restore failed', true);
            }
        }

        async function deleteTrashFile(path, name) {
            if (!confirm(`Permanently delete "${name}"? This cannot be undone.`)) return;
            try {
                const response = await apiFetch(`/api/trash/file?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || 'Delete failed');
                }
                showToast('Permanently deleted');
                loadTrash();
            } catch (error) {
                showToast(error.message || 'Delete failed', true);
            }
        }

        async function emptyTrash() {
            if (!confirm('Permanently delete everything in the trash? This cannot be undone.')) return;
            try {
                const response = await apiFetch('/api/trash', { method: 'DELETE' });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || 'Failed to empty trash');
                }
                const data = await response.json();
                showToast(`Trash emptied (${data.deleted} file(s) removed)`);
                loadTrash();
            } catch (error) {
                showToast(error.message || 'Failed to empty trash', true);
            }
        }

        let downloadablePage = 1;

        async function loadDownloadable(delta = 0) {
            downloadablePage = Math.max(1, downloadablePage + delta);
            const listEl = document.getElementById('downloadableList');
            const pagerEl = document.getElementById('downloadablePager');
            const infoEl = document.getElementById('downloadablePagerInfo');
            const prevBtn = document.getElementById('downloadablePrevBtn');
            const nextBtn = document.getElementById('downloadableNextBtn');
            if (!listEl) return;
            listEl.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
            try {
                const res = await apiFetch(`/api/jobs/downloadable?page=${downloadablePage}&per_page=15`);
                const data = await res.json();
                if (!data.jobs || data.jobs.length === 0) {
                    listEl.innerHTML = '<div class="empty-state"><p>No completed downloads yet.</p></div>';
                    pagerEl.style.display = 'none';
                    return;
                }
                listEl.innerHTML = data.jobs.map(job => {
                    const label = job.artist ? `${escapeHtml(job.artist)} \u2013 ${escapeHtml(job.title)}` : escapeHtml(job.title);
                    const date = job.completed_at ? formatTimeAgo(job.completed_at) : '';
                    return `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px;">
                        <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(job.artist||'')} - ${escapeHtml(job.title)}">${label}</span>
                        ${date ? `<span style="font-size:11px;color:var(--text-secondary);white-space:nowrap;flex-shrink:0;">${date}</span>` : ''}
                        <button ${uiAction('saveJobToDevice', [job.id || ''])} style="flex-shrink:0;padding:4px 10px;font-size:11px;font-family:inherit;font-weight:600;background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:6px;cursor:pointer;white-space:nowrap;">
                            <i class="fa-solid fa-download"></i> Save
                        </button>
                    </div>`;
                }).join('');
                if (data.pages > 1) {
                    pagerEl.style.display = 'flex';
                    infoEl.textContent = `Page ${data.page} of ${data.pages} (${data.total} tracks)`;
                    prevBtn.disabled = data.page <= 1;
                    nextBtn.disabled = data.page >= data.pages;
                } else {
                    pagerEl.style.display = 'none';
                }
            } catch (e) {
                listEl.innerHTML = '<div class="empty-state"><p>Failed to load downloads.</p></div>';
            }
        }

        async function clearQueue() {
            if (!confirm('Clear all completed, failed, and stale downloads from the queue?')) {
                return;
            }

            clearQueueBtn.disabled = true;

            try {
                const response = await apiFetch('/api/jobs/cleanup?confirm=true', {
                    method: 'DELETE'
                });

                if (!response.ok) throw new Error('Failed to clear queue');

                const data = await response.json();
                showToast(`Cleared ${data.deleted} job(s)`);
                loadJobs();
            } catch (error) {
                showToast('Failed to clear queue', true);
            } finally {
                clearQueueBtn.disabled = false;
            }
        }

        clearQueueBtn.addEventListener('click', clearQueue);
        document.getElementById('emptyTrashBtn').addEventListener('click', emptyTrash);
        if (queueHistorySort) {
            const savedQueueSort = localStorage.getItem(userStorageKey('queueHistorySort'));
            if (savedQueueSort && Array.from(queueHistorySort.options).some(option => option.value === savedQueueSort)) {
                queueHistorySort.value = savedQueueSort;
                queueHistorySortMode = savedQueueSort;
            }
            queueHistorySort.addEventListener('change', () => {
                queueHistorySortMode = queueHistorySort.value;
                localStorage.setItem(userStorageKey('queueHistorySort'), queueHistorySortMode);
                queuePage = 1;
                loadJobs(false);
            });
        }

        // Queue search. Deliberately not remembered between visits: a sticky filter
        // you forgot you set is how an empty Queue tab starts looking like a crisis.
        const queueSearchInput = document.getElementById('queueSearchInput');
        const queueSearchClearBtn = document.getElementById('queueSearchClearBtn');
        if (queueSearchInput) {
            const applyQueueSearch = (term) => {
                const next = (term || '').trim();
                if (next === queueSearchTerm) return;
                queueSearchTerm = next;
                queuePage = 1;
                if (queueSearchClearBtn) {
                    queueSearchClearBtn.style.display = queueSearchTerm ? 'flex' : 'none';
                }
                loadJobs(false);
            };

            queueSearchInput.addEventListener('input', () => {
                if (queueSearchClearBtn) {
                    queueSearchClearBtn.style.display = queueSearchInput.value ? 'flex' : 'none';
                }
                clearTimeout(queueSearchDebounce);
                // Long enough not to hammer SQLite on every keystroke, short enough
                // that it still feels like typing rather than posting a letter.
                queueSearchDebounce = setTimeout(() => applyQueueSearch(queueSearchInput.value), 250);
            });

            queueSearchInput.addEventListener('keydown', (event) => {
                if (event.key === 'Escape') {
                    clearTimeout(queueSearchDebounce);
                    queueSearchInput.value = '';
                    applyQueueSearch('');
                } else if (event.key === 'Enter') {
                    clearTimeout(queueSearchDebounce);
                    applyQueueSearch(queueSearchInput.value);
                }
            });

            if (queueSearchClearBtn) {
                queueSearchClearBtn.addEventListener('click', () => {
                    clearTimeout(queueSearchDebounce);
                    queueSearchInput.value = '';
                    applyQueueSearch('');
                    queueSearchInput.focus();
                });
            }
        }

        // The status line's "Show everything" drops the failed or unsure filter
        // but leaves any search alone, since that was typed on purpose.
        document.getElementById('queueSearchStatus')?.addEventListener('click', (event) => {
            if (event.target.closest('[data-queue-clear-status]')) clearQueueStatusFilter();
            if (event.target.closest('[data-queue-show-unsure]')) showQueueUnsure();
            const all = event.target.closest('[data-queue-resolve-all]');
            if (all) resolveUnsure(null, all.dataset.queueResolveAll);
        });
