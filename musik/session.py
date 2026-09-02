"""The import engine's decision layer.

MusikSession subclasses beets' ImportSession so that every decision is
made programmatically instead of interactively:

- strong recommendations (name/track agreement, duration within the
  configured grace) are applied automatically;
- everything weaker lands in the review queue (files stay untouched);
- *no* candidate is ever applied "as-is": silent acceptance is banned;
- a lookup that failed (rate limit, network) is recorded as `network`,
  never as "no match found";
- duplicates are resolved by audio quality: the loser goes to _trash.
"""

import logging
import os
import re
import threading

from beets.autotag import Recommendation, tag_album, tag_item
from beets.importer.actions import Action, DuplicateAction
from beets.importer.session import ImportSession

from . import quality

_PLUGIN_ERROR_RE = re.compile(r"Error in '([^']+)'")


class NetworkErrorRecorder(logging.Handler):
    """Capture beets' swallowed plugin errors during candidate lookup.

    beets catches exceptions raised by metadata plugins and only logs
    them ("Error in '<source>.<method>': ..."). Without this recorder a
    rate-limited MusicBrainz would look identical to "no match found".
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._lock = threading.Lock()
        self.errors: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        m = _PLUGIN_ERROR_RE.search(msg)
        if m:
            with self._lock:
                self.errors.append((m.group(1), msg))

    def install(self) -> None:
        logging.getLogger("beets").addHandler(self)

    def clear(self) -> None:
        with self._lock:
            self.errors.clear()

    def snapshot(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self.errors)

    @staticmethod
    def errors_from(errors: list[tuple[str, str]], source_part: str) -> list[str]:
        return [
            msg
            for src, msg in errors
            if source_part.lower() in src.lower()
        ]


def candidate_preview(match, max_len: int = 80) -> dict:
    info = match.info
    return {
        "source": getattr(info, "data_source", ""),
        "artist": (getattr(info, "artist", "") or "")[:max_len],
        "album": (getattr(info, "album", "") or "")[:max_len],
        "id": getattr(info, "album_id", "") or getattr(info, "track_id", ""),
        "year": getattr(info, "year", None),
        "n_tracks": len(getattr(info, "tracks", []) or []),
        "distance": round(float(match.distance), 4),
    }


def chosen_info(match) -> dict:
    info = match.info
    out = candidate_preview(match)
    out["track_title"] = (getattr(info, "title", "") or "")[:120]
    return out


class Decider:
    """Pure decision logic shared by the real pipeline and dry runs."""

    def __init__(self, netrec: NetworkErrorRecorder, auto_accept_distance: float,
                 review_candidates: int = 3,
                 forced_album_id: str | None = None,
                 forced_track_id: str | None = None,
                 override_artist: str | None = None,
                 override_album: str | None = None,
                 unit: dict | None = None) -> None:
        self.netrec = netrec
        self.auto_accept_distance = auto_accept_distance
        self.review_candidates = review_candidates
        self.forced_album_id = forced_album_id
        self.forced_track_id = forced_track_id
        self.override_artist = override_artist
        self.override_album = override_album
        self.unit = unit or {}

    # -- classification of an empty candidate list -------------------------

    def _classify_empty(self) -> tuple[str, str]:
        errors = self.netrec.snapshot()
        mb_errors = NetworkErrorRecorder.errors_from(errors, "musicbrainz")
        if mb_errors:
            msg = mb_errors[0]
            if len(msg) > 300:
                msg = msg[:300] + "..."
            return "network", f"MusicBrainz lookup failed: {msg}"
        other = errors[0][1] if errors else ""
        return "unmatched", (
            f"no candidates from any source"
            + (f" (other source errors: {other[:200]})" if other else "")
        )

    @staticmethod
    def _guessed(task) -> dict:
        artist = getattr(task, "cur_artist", None)
        album = getattr(task, "cur_album", None)
        if not artist and getattr(task, "item", None) is not None:
            artist = task.item.artist
            album = task.item.title
        return {"artist": artist or "", "album": album or ""}

    def _guessed_with_folder(self, task) -> dict:
        g = self._guessed(task)
        if not g.get("artist") and not g.get("album"):
            folder = self.unit.get("guessed") or {}
            g = {"artist": folder.get("artist", ""), "album": folder.get("album", "")}
        return g

    # Identity is checked component-wise, not via beets' aggregated
    # penalty (which punishes multi-artist credit formatting like
    # '5MIINUST' vs '5MIINUST, nublu' as a partial mismatch):
    # - album title must essentially match (strict),
    # - artist must match, with token overlap counting as a match
    #   (multi-artist credits, featured artists),
    # - track-title/credit penalties are informational (formatting noise),
    # - the distance cap absorbs all remaining structural noise
    #   (durations, media, label, vinyl side numbering, ...).
    ALBUM_TOLERANCE = 0.05
    ARTIST_TOLERANCE = 0.2
    TRACK_TITLE_TOLERANCE = 0.3
    # Missing/extra tracks up to ~this normalized penalty (≈1-3 tracks on
    # a typical album) are minor: the album imports, leftover local files
    # go to _trash\unmapped-track\. Bigger deviations mean a different
    # tracklist and stay in review. Roughly 0.019 per track.
    TRACK_COUNT_TOLERANCE = 0.06
    FOLDER_NAME_TOLERANCE = 0.2
    YEAR_TOLERANCE = 3
    CANDIDATE_SCAN = 6  # how deep to look for a fully-passing candidate

    # On a big year gap, candidate titles introducing these tokens
    # (absent from the folder name) are *different recordings*, not
    # reissues: reject. Reissue years, subtitles ("...: The Adventurers"),
    # remaster labels etc. are minor things and auto-accept.
    DIFFERENT_RECORDING_TOKENS = {
        "live", "concert", "unplugged", "session", "sessions", "bbc",
        "broadcast", "radio", "remix", "remixes", "remixed", "demo",
        "demos", "outtakes", "rarities", "alternate", "alternates",
    }

    @staticmethod
    def _tokens(text: str) -> set[str]:
        import re

        return {
            t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t
        }

    def _year_ok(self, info) -> bool:
        """True unless the candidate looks like a *different recording*
        that inherited the album title: big year gap plus live/broadcast/
        demo-style extra tokens (or a completely different title)."""
        guess = self.unit.get("year_guess")
        if not guess:
            return True
        year = getattr(info, "year", None) or getattr(info, "original_year", None)
        if not year or abs(int(year) - int(guess)) <= self.YEAR_TOLERANCE:
            return True
        # Big gap: tolerate reissues/subtitles, reject different recordings.
        g = self.unit.get("guessed") or {}
        if not (g.get("artist") and g.get("album")):
            return True  # no reliable folder guess; other checks decide
        g_tokens = self._tokens(g["album"])
        c_tokens = self._tokens(getattr(info, "album", "") or "")
        if g_tokens and not (g_tokens <= c_tokens):
            return False  # candidate title lost part of the album name
        extra = c_tokens - g_tokens
        if extra & self.DIFFERENT_RECORDING_TOKENS:
            return False
        return True

    def _artist_ok(self, cur: str, info) -> tuple[bool, str]:
        """Artist agreement: direct string distance against any credited
        variant, or token overlap (handles '5MIINUST' vs
        '5MIINUST, nublu', featured credits, etc.)."""
        from beets.autotag import string_dist

        variants = [v for v in [getattr(info, "artist", None)] + list(
            getattr(info, "artists", None) or []) if v]
        cur = (cur or "").strip()
        cur_tokens = self._tokens(cur)
        for v in variants:
            if string_dist(cur, v) <= self.ARTIST_TOLERANCE:
                return True, ""
            if cur_tokens and cur_tokens <= self._tokens(v):
                return True, ""
        return False, f"artist mismatch ('{cur}' vs '{getattr(info, 'artist', '')}')"

    def _names_ok(self, task, match) -> tuple[bool, str]:
        """Verify album identity: title strict, artist via variants."""
        info = match.info
        pen = dict(match.distance)
        album_pen = pen.get("album", 0)
        if album_pen > self.ALBUM_TOLERANCE:
            return False, f"album title mismatch ({album_pen:.3f})"

        cur = (getattr(task, "cur_artist", "") or "").strip()
        if cur:
            return self._artist_ok(cur, info)

        # Untagged files: compare against the folder-name guess.
        g = self.unit.get("guessed") or {}
        if g.get("artist") and g.get("album"):
            from beets.autotag import string_dist

            da = string_dist(g["artist"], info.artist or "")
            db = string_dist(g["album"], info.album or "")
            if da > self.FOLDER_NAME_TOLERANCE or db > self.FOLDER_NAME_TOLERANCE:
                ok_artist, _ = self._artist_ok(g["artist"], info)
                if not ok_artist:
                    return False, (
                        f"folder name '{g['artist']} - {g['album']}' does not match"
                        f" candidate '{info.artist} - {info.album}'"
                        f" (dist {da:.2f}/{db:.2f})"
                    )
            return True, ""
        # No name source at all: only a strong beets recommendation
        # (which needs agreement across all files) may pass.
        if getattr(task, "rec", None) != Recommendation.strong:
            return False, "no names to verify against"
        return True, ""

    def _item_names_ok(self, task, cand) -> tuple[bool, str]:
        """Singleton identity: track title lenient, artist via variants."""
        info = cand.info
        pen = dict(cand.distance)
        title_pen = pen.get("track_title", 0)
        if title_pen > self.TRACK_TITLE_TOLERANCE:
            return False, f"track title mismatch ({title_pen:.3f})"
        item = getattr(task, "item", None)
        cur = (item.artist if item is not None else "") or ""
        if cur.strip():
            return self._artist_ok(cur, info)
        if getattr(task, "rec", None) != Recommendation.strong:
            return False, "no names to verify against"
        return True, ""

    def _passes_all(self, task, cand) -> bool:
        rec = getattr(task, "rec", None)
        penalties = dict(cand.distance)
        track_count_pen = (
            penalties.get("missing_tracks", 0)
            + penalties.get("unmatched_tracks", 0)
        )
        if track_count_pen > self.TRACK_COUNT_TOLERANCE:
            return False
        if rec is not None and rec < Recommendation.low:
            return False
        if float(cand.distance) > self.auto_accept_distance:
            return False
        if not self._year_ok(cand.info):
            return False
        ok, _why = self._names_ok(task, cand)
        return ok

    # -- album decisions ----------------------------------------------------

    def decide_album(self, task) -> tuple[str, dict]:
        """Return ('apply', match) or ('skip', decision_record)."""
        rec = getattr(task, "rec", None)
        candidates = list(getattr(task, "candidates", None) or [])
        guessed = self._guessed_with_folder(task)

        if self.forced_album_id:
            match = next(
                (c for c in candidates if c.info.album_id == self.forced_album_id),
                None,
            )
            if match is not None:
                return "apply", self._apply_record(
                    match, "review-apply", f"forced album id {self.forced_album_id}", guessed
                )
            return "skip", {
                "status": "review",
                "reason": f"forced id {self.forced_album_id} not among candidates",
                "candidates": [candidate_preview(c) for c in candidates[: self.review_candidates]],
                "guessed": guessed,
            }

        if self.override_artist or self.override_album:
            _artist, _album, prop = tag_album(
                task.items,
                search_artist=self.override_artist or None,
                search_name=self.override_album or None,
            )
            if prop.candidates:
                return "apply", self._apply_record(
                    prop.candidates[0], "review-apply",
                    f"override search '{self.override_artist}' - '{self.override_album}'",
                    guessed,
                )
            return "skip", {
                "status": "unmatched",
                "reason": "override search found nothing",
                "candidates": [],
                "guessed": guessed,
            }

        if not candidates:
            status, reason = self._classify_empty()
            return "skip", {"status": status, "reason": reason, "candidates": [], "guessed": guessed}

        # Prefer the highest-ranked candidate that passes *every* check
        # (names, no missing/unmatched tracks, year, distance cap). The
        # top-ranked candidate often differs only by release year/remaster.
        for cand in candidates[: self.CANDIDATE_SCAN]:
            if self._passes_all(task, cand):
                return "apply", self._apply_record(cand, "auto", "", guessed)

        best = candidates[0]
        dist = float(best.distance)
        penalties = dict(best.distance)
        reasons = [f"distance {dist:.3f}"]
        blocking = [
            key
            for key in ("missing_tracks", "unmatched_tracks")
            if penalties.get(key, 0) > 0
        ]
        if blocking:
            reasons.append(f"penalties: {', '.join(blocking)}")
        ok, why = self._names_ok(task, best)
        if not ok:
            reasons.append(why)
        if not self._year_ok(best.info):
            reasons.append(
                f"possible different recording (folder year {self.unit.get('year_guess')},"
                f" candidate {getattr(best.info, 'year', None)}:"
                f" '{getattr(best.info, 'album', '')}')"
            )
        return "skip", {
            "status": "review",
            "reason": "below auto-accept confidence: " + "; ".join(reasons),
            "candidates": [
                candidate_preview(c) for c in candidates[: self.review_candidates]
            ],
            "guessed": guessed,
        }

    # -- singleton decisions --------------------------------------------------

    def decide_item(self, task) -> tuple[str, dict]:
        rec = getattr(task, "rec", None)
        candidates = list(getattr(task, "candidates", None) or [])
        guessed = self._guessed_with_folder(task)

        if self.forced_track_id:
            match = next(
                (c for c in candidates if c.info.track_id == self.forced_track_id),
                None,
            )
            if match is not None:
                return "apply", self._apply_record(
                    match, "review-apply", f"forced track id {self.forced_track_id}", guessed
                )
            return "skip", {
                "status": "review",
                "reason": f"forced id {self.forced_track_id} not among candidates",
                "candidates": [candidate_preview(c) for c in candidates[: self.review_candidates]],
                "guessed": guessed,
            }

        if not candidates:
            status, reason = self._classify_empty()
            return "skip", {"status": status, "reason": reason, "candidates": [], "guessed": guessed}

        for cand in candidates[: self.CANDIDATE_SCAN]:
            pen = dict(cand.distance)
            title_pen = pen.get("track_title", 0)
            if (
                title_pen <= self.TRACK_TITLE_TOLERANCE
                and float(cand.distance) <= self.auto_accept_distance
                and (getattr(task, "rec", None) or Recommendation.none) >= Recommendation.low
            ):
                ok, _why = self._item_names_ok(task, cand)
                if ok:
                    return "apply", self._apply_record(cand, "auto", "", guessed)

        best = candidates[0]
        dist = float(best.distance)
        reasons = [f"distance {dist:.3f}"]
        ok, why = self._item_names_ok(task, best)
        if not ok:
            reasons.append(why)
        return "skip", {
            "status": "review",
            "reason": "below auto-accept confidence: " + "; ".join(reasons),
            "candidates": [candidate_preview(c) for c in candidates[: self.review_candidates]],
            "guessed": guessed,
        }

    def _apply_record(self, match, status: str, reason: str, guessed: dict | None = None) -> dict:
        return {
            "status": status,
            "reason": reason,
            "chosen": chosen_info(match),
            "candidates": [],
            "guessed": guessed or {},
        }


class MusikSession(ImportSession):
    """Non-interactive ImportSession driven by a Decider."""

    def __init__(self, lib, decider: Decider, import_paths: list[str],
                 singletons: bool) -> None:
        super().__init__(
            lib, None, [os.fsencode(p) for p in import_paths], None
        )
        self.decider = decider
        self.singletons_flag = singletons
        self.results: list[dict] = []
        self.duplicate_losers: list[str] = []   # new files that lost -> trash
        self.duplicate_replacements: list[dict] = []
        self.extra_files: list[str] = []        # unmapped tracks -> trash

    def set_config(self, config) -> None:
        super().set_config(config)
        self.config["singletons"] = self.singletons_flag

    # -- session contract ---------------------------------------------------

    def should_resume(self, path) -> bool:
        return False

    def choose_match(self, task):
        action, record = self.decider.decide_album(task)
        record["paths"] = [os.fsdecode(p) for p in task.paths]
        self.results.append(record)
        if action == "apply":
            match = self._match_for(task, record)
            # Tracks the release has that the rip doesn't map to (scene
            # bonus files, miscounted rips): the album still imports;
            # the leftovers are archived by the engine.
            extras = [
                os.fsdecode(i.path)
                for i in getattr(match, "extra_items", []) or []
            ]
            if extras:
                record["extra_files"] = extras
                self.extra_files.extend(extras)
            return match
        return Action.SKIP

    def choose_item(self, task):
        action, record = self.decider.decide_item(task)
        record["paths"] = [os.fsdecode(p) for p in task.paths]
        self.results.append(record)
        if action == "apply":
            return self._match_for(task, record)
        return Action.SKIP

    def _match_for(self, task, record):
        chosen = record.get("chosen") or {}
        candidates = list(task.candidates or [])
        for c in candidates:
            cid = getattr(c.info, "album_id", "") or getattr(c.info, "track_id", "")
            if cid and cid == chosen.get("id"):
                return c
        # Fall back to the best candidate; recording already happened.
        return candidates[0] if candidates else Action.SKIP

    # -- duplicates -----------------------------------------------------------

    def get_duplicate_action(self, task, found_duplicates):
        new_files = [os.fsdecode(i.path) for i in task.imported_items()] or [
            os.fsdecode(p) for p in task.paths
        ]
        old_files: list[str] = []
        old_models = []
        for dup in found_duplicates:
            items = list(dup.items()) if hasattr(dup, "items") else [dup]
            old_models.append((dup, items))
            old_files.extend(os.fsdecode(i.path) for i in items)

        if quality.better(new_files, old_files):
            # New copy wins: archive the old files, drop them from the DB,
            # let the new import proceed (KEEP does not block).
            from . import trash as trash_mod

            losers = [f for f in old_files if os.path.isfile(f)]
            detail = f"replaced by {new_files[0] if new_files else '?'} ({quality.describe(quality.score_files(new_files))})"
            trashed = trash_mod.trash_files(losers, "duplicate", detail)
            for dup, items in old_models:
                for item in items:
                    try:
                        item.remove(with_album=False)
                    except Exception:
                        pass
                try:
                    dup.remove(with_items=False)
                except Exception:
                    pass
            self.duplicate_replacements.append({
                "trashed": trashed,
                "detail": detail,
            })
            return DuplicateAction.KEEP

        # Existing copy wins: skip the new import; engine trashes the
        # losing new files afterwards so nothing lingers untagged.
        self.duplicate_losers.extend(
            f for f in new_files if os.path.isfile(f)
        )
        return DuplicateAction.SKIP


def aggregate_unit_status(unit: dict, results: list[dict]) -> tuple[str, str]:
    """Fold per-task decisions into the unit's overall status."""
    if unit.get("singleton") or unit.get("split_into_singletons"):
        statuses = [r.get("status", "unmatched") for r in results] or ["unmatched"]
        reasons = [r.get("reason") for r in results if r.get("reason")]
        if "network" in statuses:
            agg = "network"
        elif "error" in statuses:
            agg = "error"
        elif "review" in statuses:
            agg = "review"
        elif all(s in ("auto", "review-apply") for s in statuses):
            agg = "auto"
        else:
            agg = "unmatched"
        return agg, "; ".join(dict.fromkeys(reasons))[:500]

    r = results[0] if results else {"status": "error", "reason": "no decision recorded"}
    return r.get("status", "error"), r.get("reason", "no decision recorded")
