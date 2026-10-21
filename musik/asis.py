"""`musik asis`: file already-tagged units without a MusicBrainz match.

For review/unmatched units whose files carry complete, consistent tags
(scene rips usually do), this imports them "as-is" into the configured
layout. Via the ingest's asis fallback it also runs in the automatic
pipeline (Story 9.6), and since Story 9.9 it repairs defective tags from
the folder identity before giving up on a unit. Duplicates are still
resolved by quality, cover art and genres are still fetched, and
everything is logged.
"""

import os
import re
import time

import mutagen

from .scan import openable


def _tag(f: str, field: str) -> str:
    try:
        m = mutagen.File(openable(f), easy=True)
        if m is None:
            return ""
        vals = m.get(field) or []
        return str(vals[0]).strip() if vals else ""
    except Exception:
        return ""


def from_fetch(unit: dict) -> bool:
    """Downloader staging unit (bot fetch jobs, MusicGrabber output).

    Per-track tags come from the streaming catalog (fetch jobs) or
    MusicGrabber's own AcoustID/MusicBrainz tagging and are authoritative
    per file; the album tag intentionally differs between tracks (a best-of
    playlist spans many releases; MG's Singles/ tree holds one release per
    track). Beets groups these by album tag on import, landing every track
    in its own release's folder. The staging folder name is job metadata,
    never release identity.
    """
    p = os.path.basename(unit.get("path") or "")
    if p.startswith("fetch-"):
        return True
    parts = os.path.normpath(unit.get("path") or "").split(os.sep)
    return "musicgrabber" in parts


def tags_complete(unit: dict) -> tuple[bool, str]:
    """Every file needs artist/album/title; album must be consistent.

    Singleton units (chart dumps etc.) and fetch-staging units (playlists,
    multi-release downloads) carry a different release album tag per track
    by design — there the album tag is neither compared across files nor
    strictly required per file (matches the singleton behavior).
    """
    if not unit.get("files"):
        return False, "no files"
    per_track = bool(
        unit.get("singleton") or unit.get("split_into_singletons")
        or from_fetch(unit)
    )
    album = None
    for f in unit["files"]:
        if not os.path.isfile(openable(f)):
            return False, f"missing file {os.path.basename(f)}"
        artist = _tag(f, "albumartist") or _tag(f, "artist")
        title = _tag(f, "title")
        fa = _tag(f, "album")
        if not artist or not title or (not fa and not per_track):
            return False, (
                f"incomplete tags in {os.path.basename(f)} "
                f"(artist={artist!r}, album={fa!r}, title={title!r})"
            )
        if album is None:
            album = fa.lower() if fa else ""
        elif not per_track and fa and fa.lower() != album:
            return False, "inconsistent album tags across files"
    return True, ""


# --- VA-Survivor-Normalisierung (Story 10.6) -----------------------------

def plan_va_normalize(files: list, seen: list[str] | None = None) -> dict | None:
    """Decide whether a va_like album unit can import as a clean
    Various-Artists album on its own metadata (Story 10.6), and how.

    The files' own tags are authoritative — the live windows drop even
    carries CORRECT tags where the filename has the typo. A filename
    ('NN. Part A - Part B.ext') only FILLS missing artist/title tags;
    its orientation (artist first vs. title first) is majority-voted
    per unit against the fully tagged files. A junk release credit
    (albumartist matching none of `seen`, the >=3 real track artists)
    is REPLACED by Various Artists; an empty one is filled.

    Returns None (stay in review) when a file has neither complete tags
    nor a filename that can fill its gaps. Otherwise:
    {"fill": {path: (artist, title)}, "aa": bool, "aa_overwrite": bool}
    — "aa" says some file lacks albumartist, "aa_overwrite" says some
    file carries a junk credit that must be replaced."""
    from .scan import norm_name, openable, parse_track_filename, tag_of

    seen = {s.strip().lower() for s in (seen or [])}
    entries = []
    votes_artist = votes_title = 0
    for f in files:
        if not os.path.isfile(openable(f)):
            return None
        artist = tag_of(f, "artist")
        title = tag_of(f, "title")
        parsed = parse_track_filename(os.fsdecode(f))
        if artist and title and parsed:
            pa, pt = parsed
            if (norm_name(pa) == norm_name(artist)
                    and norm_name(pt) == norm_name(title)):
                votes_artist += 1
            elif (norm_name(pa) == norm_name(title)
                    and norm_name(pt) == norm_name(artist)):
                votes_title += 1
        entries.append((f, artist, title, parsed))

    orientation = None
    if votes_artist or votes_title:
        orientation = (
            "artist_first" if votes_artist >= votes_title else "title_first"
        )

    fill: dict[str, tuple[str, str]] = {}
    aa = aa_overwrite = 0
    for f, artist, title, parsed in entries:
        credit = tag_of(f, "albumartist")
        if not credit:
            aa += 1
        elif seen and len(seen) >= 3 and credit.strip().lower() not in seen \
                and credit.strip().lower() not in (
                    "various artists", "various", "va", "v.a."):
            aa_overwrite += 1
        if artist and title:
            continue
        if parsed is None or orientation is None:
            return None
        pa, pt = parsed
        fa, ft = (
            (pa, pt) if orientation == "artist_first" else (pt, pa)
        )
        fill[os.fsdecode(f)] = (
            fa if not artist else "", ft if not title else ""
        )
    return {"fill": fill, "aa": aa > 0, "aa_overwrite": aa_overwrite > 0}


def apply_va_plan(task, plan: dict) -> int:
    """Mutate the task's in-memory items per plan_va_normalize; beets
    writes the tags onto the imported copies (write: yes). Returns the
    number of fields touched."""
    touched = 0
    fills = plan.get("fill") or {}
    for item in task.imported_items():
        path = os.fsdecode(item.path)
        artist, title = fills.get(path, ("", ""))
        if artist and not (item.artist or "").strip():
            item.artist = artist
            touched += 1
        if title and not (item.title or "").strip():
            item.title = title
            touched += 1
        if plan.get("aa") and not (item.albumartist or "").strip():
            item.albumartist = "Various Artists"
            touched += 1
        elif plan.get("aa_overwrite") and (item.albumartist or "").strip() \
                and item.albumartist.strip().lower() != "various artists":
            item.albumartist = "Various Artists"
            touched += 1
    return touched


def apply_va_normalize_files(unit: dict, plan: dict) -> bool:
    """Write the Story-10.6 normalization onto the FILES (asis path,
    where beets re-reads tags from disk): fill artist/title gaps per the
    plan, set albumartist=Various Artists where empty. Returns False
    when a write failed (the unit then falls back to plain asis)."""
    import mutagen as _mutagen

    from .scan import openable

    for f in unit.get("files") or []:
        artist, title = plan.get("fill", {}).get(os.fsdecode(f), ("", ""))
        if not artist and not title and not plan.get("aa"):
            continue
        try:
            m = _mutagen.File(openable(f), easy=True)
        except Exception:
            m = None
        if m is None:
            continue
        changed = False
        if artist and not (m.get("artist") or [""])[0].strip():
            m["artist"] = artist
            changed = True
        if title and not (m.get("title") or [""])[0].strip():
            m["title"] = title
            changed = True
        credit = (m.get("albumartist") or [""])[0].strip()
        if plan.get("aa") and not credit:
            m["albumartist"] = "Various Artists"
            changed = True
        elif plan.get("aa_overwrite") and credit \
                and credit.lower() != "various artists":
            m["albumartist"] = "Various Artists"
            changed = True
        if changed:
            try:
                m.save()
            except Exception:
                return False
    return True


def va_gate_unit(unit: dict, lib, dry_run: bool = False) -> tuple[str, str]:
    """Asis-fallback gate for va_like album units (Stories 10.5/10.6).

    Returns ('ignored', reason) — the compilation is largely already in
    the library: archive it, don't import; ('normalize', reason) —
    mostly unique: normalize to a clean Various-Artists album (files
    written unless dry_run) and import; ('pass', '') — the gate does
    not apply (not va_like, no library, too few tagged files, or
    identity not resolvable)."""
    from .session import Decider, NetworkErrorRecorder

    decider = Decider(
        NetworkErrorRecorder(), auto_accept_distance=0.25,
        unit=unit, lib=lib,
    )
    if not decider._va_like():
        return "pass", ""
    plan, verdict = decider._va_assess()
    if verdict is not None and verdict[0]:
        reason = decider._va_ignored_record(
            verdict, unit.get("guessed")
        )["reason"]
        return "ignored", reason
    if plan is None or verdict is None:
        return "pass", ""
    note = (
        f"VA compilation, own metadata authoritative "
        f"({verdict[1]}/{verdict[2]} tracks already in library)"
    )
    if not dry_run and not apply_va_normalize_files(unit, plan):
        return "pass", ""
    return "normalize", note


def enrich_from_meta_files(unit: dict) -> int:
    """Fill missing artist/title tags from the release's .nfo/.txt.

    Scene rips ship .nfo files whose tracklist ('01. Artist - Title (4:23)')
    is authoritative when the sources don't know the release and the
    files' own tags are thin. Only EMPTY fields are filled; tracks are
    matched by track number (tag, else leading filename number).
    Returns the number of files touched.
    """
    metas = [m for m in (unit.get("meta_files") or [])
             if os.path.isfile(openable(m))]
    if not metas:
        return 0
    entries: dict[int, dict] = {}
    for mf in metas:
        try:
            with open(mf, "rb") as fh:
                raw = fh.read()
        except OSError:
            continue
        text = None
        for enc in ("utf-8", "cp437", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            continue
        for line in text.splitlines():
            m = re.match(r"^\s{0,6}(\d{1,2})[\.\)\-]\s+(\S.*?)\s*$", line)
            if not m:
                continue
            num = int(m.group(1))
            rest = re.sub(r"\s*[\(\[][0-9:]{3,5}[\)\]]?\s*$", "", m.group(2))
            if num not in entries and rest:
                if " - " in rest:
                    artist, title = rest.split(" - ", 1)
                    entries[num] = {"artist": artist.strip(), "title": title.strip()}
                else:
                    entries[num] = {"artist": "", "title": rest.strip()}
    if not entries:
        return 0

    def track_no(f: str) -> int | None:
        vals = _tag(f, "track")
        m = re.match(r"^(\d{1,2})", vals)
        if m:
            return int(m.group(1))
        m = re.match(r"^(\d{1,2})[\s\.\-_]", os.path.basename(f))
        return int(m.group(1)) if m else None

    touched = 0
    for f in unit.get("files") or []:
        need_artist = not _tag(f, "artist") and not _tag(f, "albumartist")
        need_title = not _tag(f, "title")
        if not (need_artist or need_title):
            continue
        num = track_no(f)
        entry = entries.get(num or -1)
        if not entry:
            continue
        m = mutagen.File(openable(f), easy=True)
        if m is None:
            continue
        changed = False
        if need_artist and entry["artist"]:
            m["artist"] = entry["artist"]
            if not _tag(f, "albumartist"):
                m["albumartist"] = entry["artist"]
            changed = True
        if need_title and entry["title"]:
            m["title"] = entry["title"]
            changed = True
        if changed:
            m.save()
            touched += 1
    return touched


# --- Tag-Reparatur aus Ordner-Identität (Story 9.9) --------------------

_BULLET = " • "
_PREFIX_RE = re.compile(r"^\s*\d{3,4}\s*[.\-_]\s+")
_ANY_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_BRACKET_TAIL_RE = re.compile(r"\s*[\[\(][^\]\)]*[\]\)]\s*$")
# Nur echte Datenträger-Suffixe; "Vol. 2" ist ein echter Albumnamenbestandteil
_DISC_SUFFIX_RE = re.compile(
    r"[\s.\-_]*[\(\[]?\s*(?:cd|lp|disc)\s*0?\d{1,2}\s*[\)\].]*\s*$", re.I)
_TRACK_PREFIX_RE = re.compile(r"^\s*[\(\[]?[A-Da-d]?\d{1,3}[\)\].]?[\s._\-:]*")
_BROWSER_DUP_RE = re.compile(r"\s*\(\d+\)\s*$")


def _folder_identity(name: str) -> dict:
    """Artist/Album/Jahr aus dem Unit-Ordnernamen ableiten.

    Unterstützt die real vorkommenden Konventionen:
    '2017 - GREATEST HITS • Artist - Album [US Vinyl LP] [2CD]',
    '0134. Artist - Album [1968]' und schlicht 'Artist - Album'.
    """
    ident: dict = {}
    m = re.match(r"^\s*((?:19|20)\d{2})\s*(?:[-–_.]|\b)", name)
    if m:
        ident["year"] = m.group(1)
    else:
        m = _ANY_YEAR_RE.search(name)
        if m:
            ident["year"] = m.group(1)
    rest = name
    if _BULLET in rest:
        rest = rest.rsplit(_BULLET, 1)[1]
    else:
        rest = _PREFIX_RE.sub("", rest)
    while True:
        stripped = _BRACKET_TAIL_RE.sub("", rest).strip()
        if stripped == rest.strip() or not stripped:
            break
        rest = stripped
    rest = rest.strip(" \t-_.")
    artist, album = "", rest
    for pat in (r"\s+[-–]\s+", r"\s*[-–]\s+"):
        parts = re.split(pat, rest, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            artist, album = parts[0].strip(), parts[1].strip()
            break
    if artist:
        ident["artist"] = artist
    if album:
        ident["album"] = album
    return ident


def _split_disc_suffix(album: str) -> tuple[str, int | None]:
    """'…Greatest Hits CD1' → (Basis, 1); '…(LP2).' → (Basis, 2)."""
    m = _DISC_SUFFIX_RE.search(album)
    if not m:
        return album.rstrip(" ."), None
    base = album[: m.start()].rstrip(" \t-_.")
    digits = re.search(r"\d{1,2}", m.group(0))
    disc = int(digits.group(0)) if digits else None
    return (base or album.rstrip(" .")), disc


def _natural_key(fname: str):
    base = os.path.basename(fname).lower()
    m = re.match(r"^\s*[\(\[]?([A-Da-d])?0*(\d{1,3})", base)
    if m:
        side = ord(m.group(1).lower()) - ord("a") if m.group(1) else 0
        return (0, side, int(m.group(2)), base)
    return (1, 0, 0, base)


def _title_from_filename(fname: str) -> str:
    base = os.path.splitext(os.path.basename(fname))[0].replace("_", " ")
    base = _TRACK_PREFIX_RE.sub("", base).strip(" .-")
    base = _BROWSER_DUP_RE.sub("", base).strip()
    base = re.sub(r"\s{2,}", " ", base.replace(".", " ")).strip()
    if not base:
        return ""
    titled = base.title()
    return re.sub(r"(['’])([A-Z])",
                  lambda m: m.group(1) + m.group(2).lower(), titled)


def repair_from_folder(unit: dict, dry_run: bool = False) -> tuple[bool, str]:
    """Defekte Tags einer Album-Unit aus der Ordner-Identität reparieren
    (Story 9.9) — die automatisierte Form der Hand-Waiter monitor-apply1/2.

    Gilt nur für Units, die am tags_complete-Gate scheitern: Vinyl-Rips
    mit leeren Tags, Album-Tag-Varianten je LP/CD („…(LP1)/(LP2)“,
    „…CD1/CD2“), fehlende Titel. Singletons und Fetch-Staging (per-track
    Autorität) sind bewusst ausgenommen. Identität: Album/Artist aus dem
    Ordnernamen (der Ripper-Namenskonvention folgt; Junk-Tags werden
    überschrieben — Beweisstand Coral/Willie Nelson); ≥2 verschiedene
    echte Datei-Artists ohne Treffer auf den Ordner-Artist → Various
    Artists (Tribute-/Sampler-Fall, Datei-Artists bleiben erhalten).
    Fehlende Titel/Tracknummern kommen aus dem Dateinamen bzw. werden
    fortlaufend nummeriert; Discs aus CD/LP-Suffixen. Ein Trockenlauf
    plant nur und schreibt nichts. Liefert (erfolg, hinweis).
    """
    if not unit.get("files"):
        return False, "no files"
    if (unit.get("singleton") or unit.get("split_into_singletons")
            or from_fetch(unit)):
        return False, "singleton/fetch-staging — Reparatur nicht anwendbar"
    files = [f for f in unit["files"] if os.path.isfile(openable(f))]
    if not files:
        return False, "no files on disk"

    infos = []
    for f in files:
        try:
            m = mutagen.File(openable(f), easy=True)
        except Exception:
            m = None
        if m is None:
            return False, f"unlesbar: {os.path.basename(f)}"

        def g(key, _m=m):
            vals = _m.get(key) or []
            return str(vals[0]).strip() if vals else ""

        infos.append({
            "path": f, "mg": m,
            "artist": g("artist"), "aartist": g("albumartist"),
            "album": g("album"), "title": g("title"),
            "year": g("date") or g("year"), "track": g("tracknumber"),
        })

    ident = _folder_identity(
        os.path.basename((unit.get("path") or "").rstrip("\\/")))
    folder_artist = ident.get("artist", "")
    album = ident.get("album", "")
    if not album:
        return False, "keine Album-Identität im Ordnernamen"

    # Disc-Zuordnung nur aus VARIANTEN der Datei-Album-Tags (CD1/LP2 …);
    # einheitliche Tags bleiben unangetastet (echte Albumnamen mit
    # solchen Bestandteilen nicht zerstören).
    file_albums = {i["album"] for i in infos if i["album"]}
    discs: dict[str, int] = {}
    if len(file_albums) > 1:
        for i in infos:
            if i["album"]:
                _, disc = _split_disc_suffix(i["album"])
                if disc:
                    discs[i["path"]] = disc

    # Artist: Ordner-Identität gewinnt; nur wenn ≥2 verschiedene echte
    # Datei-Artists vorliegen und KEINER den Ordner-Artist bestätigt,
    # ist es ein Sampler/Tribute → Various Artists (Datei-Artists keep).
    file_artists = {(i["artist"] or i["aartist"]) for i in infos} - {""}
    va = (len(file_artists) >= 2
          and not any(a.lower() == folder_artist.lower()
                      for a in file_artists))
    albumartist = "Various Artists" if va else folder_artist
    if not albumartist:
        return False, "keine Artist-Identität im Ordnernamen"

    year = ""
    if all(i["year"] for i in infos):
        year = infos[0]["year"]
    else:
        year = ident.get("year", "")

    plan = []
    changed = False
    order = sorted(range(len(infos)), key=lambda ix: _natural_key(infos[ix]["path"]))
    for seq, ix in enumerate(order, 1):
        i = infos[ix]
        tags: dict[str, str] = {}
        if not va:
            if i["artist"] != folder_artist:
                tags["artist"] = folder_artist
            if i["aartist"] != folder_artist:
                tags["albumartist"] = folder_artist
        elif i["aartist"].lower() != "various artists":
            tags["albumartist"] = "Various Artists"
        if i["album"] != album:
            tags["album"] = album
        if not i["title"]:
            t = _title_from_filename(i["path"])
            if t:
                tags["title"] = t
        if year and not i["year"]:
            tags["date"] = year
        if not i["track"] or not i["track"].split("/")[0].strip().isdigit():
            tags["tracknumber"] = str(seq)
        disc = discs.get(i["path"])
        if disc:
            tags["discnumber"] = str(disc)
        if tags:
            changed = True
        plan.append((i["path"], i["mg"], tags))

    if not changed:
        return False, "Reparatur hätte nichts zu korrigieren"

    label = f"{albumartist} – {album}" + (f" [{year}]" if year else "")
    if dry_run:
        return True, f"würde reparieren ({len(plan)} Dateien): {label}"
    for path, mg, tags in plan:
        for key, val in tags.items():
            mg[key] = val
        mg.save()
    return True, f"Tags repariert aus Ordner-Identität: {label}"


def _fill_empty_original_years(lib) -> int:
    """As-is imports have no MB data: derive original_year from year so
    the `$original_year` path templates work. Only fills empty fields."""
    fixed = 0
    for album in lib.albums():
        if not album.original_year and album.year:
            album.original_year = album.year
            album.store()
            fixed += 1
    for item in lib.items():
        if not item.original_year and item.year:
            item.original_year = item.year
            item.store()
            fixed += 1
    return fixed


def import_units(paths: list[str], progress=None) -> tuple[list[str], bool]:
    """Mehrere Units as-is importieren — gemeinsamer Kern der Telegram-
    /asis-Aktion und der Monitor-Aktion (Story 9.6). Pro Unit cmd_asis +
    Statusverifikation, danach Plex-Refresh und Playlist-Rebuild.
    Liefert (meldungszeilen, fehlgeschlagen?); Aufrufer koordiniert den
    ingest.lock."""
    from . import plex as plex_mod
    from . import playlists as playlists_mod
    from . import state as state_mod

    def say(m):
        if progress:
            progress(m)

    lines: list[str] = []
    for p in paths:
        label = os.path.basename(p) or p
        say(f"📦 as-is-Import läuft:\n{label}")
        try:
            cmd_asis(only=p, include_pending=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            lines.append(f"❌ {label}: {type(e).__name__}: {str(e)[:200]}")
            continue
        fresh = state_mod.get_unit(state_mod.load(), p)
        status = (fresh or {}).get("status")
        if status == "asis":
            lines.append(f"✅ {os.path.basename(p) or p} — importiert")
        else:
            why = ((fresh or {}).get("reason") or "")[:120]
            lines.append(f"⚠️ {os.path.basename(p) or p} — Status jetzt "
                         f"„{status}“ {('('+why+')') if why else ''}")
    ok, note = plex_mod.refresh_library()
    if ok:
        lines.append(f"🎧 {note}")
    elif note:
        lines.append(f"⚠️ {note}")
    # tracks that just arrived fill their playlist entries -> re-upload
    for msg in playlists_mod.upload(playlists_mod.rebuild(paths)):
        lines.append(msg)
    return lines, any(l.startswith("❌") for l in lines)


def _folder_repair_enabled() -> bool:
    from .paths import musik_config

    return bool(musik_config().get("asis_folder_repair", True))


def cmd_asis(only: str | None = None, dry_run: bool = False,
             include_pending: bool = False) -> int:
    from . import state as state_mod
    from . import trash as trash_mod
    from .engine import restrict_sources, setup_beets
    from .session import MusikSession

    # as-is imports perform no lookups — never load metadata source
    # plugins (a broken beatport4 token must not be able to kill an
    # asis run through its import_begin setup).
    restrict_sources([])
    setup_beets()
    st = state_mod.load()
    want = os.path.normcase(os.path.normpath(only)) if only else None
    statuses = ("review", "unmatched", "network")
    if include_pending:
        statuses += ("pending",)

    from beets import config as beets_config
    from beets.importer.session import ImportSession
    from beets.library import Library

    lib = Library(
        beets_config["library"].as_filename(),
        beets_config["directory"].as_filename(),
    )

    selected = []
    repaired: dict[str, str] = {}
    for u in state_mod.units(st).values():
        if u.get("status") not in statuses:
            continue
        if want:
            upath = os.path.normcase(os.path.normpath(u["path"]))
            if want != upath and not upath.startswith(want + os.sep):
                continue
        # stale entries (files already imported by a earlier partial run
        # of this unit) must not block the remaining files
        present = [f for f in (u.get("files") or []) if os.path.isfile(openable(f))]
        if present:
            u["files"] = present
            u["n_files"] = len(present)
        ok, _why = tags_complete(u)
        if not ok and _folder_repair_enabled():
            rok, rnote = repair_from_folder(u, dry_run=dry_run)
            if rok:
                repaired[u["path"]] = rnote
                # Trockenlauf vertraut dem Reparaturplan; Echtlauf
                # verifiziert unabhängig über den Gate-Lauf.
                ok = True if dry_run else tags_complete(u)[0]
        if ok:
            # VA gate (Stories 10.5/10.6): redundant compilations are
            # archived instead of imported; unique ones are normalized
            # to a clean Various-Artists album first. Singletons and
            # network-deferred units stay out of it.
            if u.get("status") != "network" \
                    and not (u.get("singleton")
                             or u.get("split_into_singletons")):
                gate, note = va_gate_unit(u, lib, dry_run=dry_run)
                if gate == "ignored":
                    if dry_run:
                        print(f"  VA-guard would ignore: "
                              f"{os.path.basename(u['path'])}")
                    else:
                        present = [
                            os.fsdecode(f) for f in u.get("files", [])
                            if os.path.isfile(os.fsdecode(f))
                        ]
                        if present:
                            trash_mod.trash_files(
                                present, "va-redundant", note
                            )
                            trash_mod.prune_empty_dirs(present, u["path"])
                        state_mod.set_status(u, "ignored", note)
                        state_mod.save(st)
                        print(f"  ignored (VA redundant): "
                              f"{os.path.basename(u['path'])}")
                    continue
                if gate == "normalize" and note:
                    print(f"  VA-guard: {note} — "
                          f"{os.path.basename(u['path'])}")
            selected.append(u)
    selected.sort(key=lambda u: u["path"])
    print(f"asis: {len(selected)} tag-complete unit(s) eligible"
          + (f" ({len(repaired)} aus Ordner-Identität repariert)"
             if repaired else "")
          + (" (DRY RUN — nothing done)" if dry_run else ""))
    if not selected:
        return 0

    # As-is items have no MB original_year; the album templates use it.
    # Swap in $year for this session, restore afterwards.
    paths_view = beets_config["paths"]
    saved_paths = {k: paths_view[k].as_str() for k in ("default", "comp", "singleton")}
    for k in saved_paths:
        paths_view[k] = saved_paths[k].replace("$original_year", "$year")

    class AsisSession(MusikSession):
        """Non-autotag session: beets' import_asis stage files everything
        with its current tags; our duplicate handling still applies."""

        def set_config(self, config) -> None:
            super().set_config(config)
            self.config["autotag"] = False

    done = 0
    try:
        for i, unit in enumerate(selected, 1):
            label = os.path.basename(unit["import_path"])
            if dry_run:
                print(f"[{i}/{len(selected)}] would-as-is  {label}")
                continue
            singletons = bool(unit.get("singleton") or unit.get("split_into_singletons"))
            session = AsisSession(lib, None, [unit["import_path"]], singletons)
            try:
                session.run()
            except KeyboardInterrupt:
                state_mod.save(st)
                print("\ninterrupted — state saved")
                return 130
            except Exception as exc:
                import traceback

                traceback.print_exc()
                state_mod.set_status(unit, "error", f"asis: {type(exc).__name__}: {exc}")
                state_mod.save(st)
                print(f"[{i}/{len(selected)}] ERROR   {label}: {exc}")
                continue
            finally:
                # set_config flipped the shared import view; restore it so
                # later regular imports keep autotagging.
                beets_config["import"]["autotag"] = True

            if session.duplicate_losers:
                trash_mod.trash_files(
                    [f for f in session.duplicate_losers if os.path.isfile(f)],
                    "duplicate", f"lost duplicate comparison (asis {unit['path']})",
                )
                trash_mod.prune_empty_dirs(session.duplicate_losers, unit["import_path"])

            from . import engine as _engine

            _engine._trash_unreadable(unit, "asis")

            unit["decision_kind"] = _engine._release_kind(unit)
            unit["decision_type"] = "own-tags"
            rnote = repaired.get(unit["path"])
            state_mod.set_status(
                unit, "asis",
                "imported as-is (user-invoked, tags complete)"
                + (f"; {rnote}" if rnote else ""))
            state_mod.save(st)
            done += 1
            print(f"[{i}/{len(selected)}] asis     {label}")
    finally:
        for k, v in saved_paths.items():
            paths_view[k] = v

    fixed = _fill_empty_original_years(lib)
    if fixed:
        print(f"filled empty original_year on {fixed} album(s)/item(s)")
    print(f"asis: {done} unit(s) imported with their own tags")
    return 0
