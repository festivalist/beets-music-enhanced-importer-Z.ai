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
from collections import Counter

import mutagen

from .scan import (
    artist_present,
    from_fetch,
    openable,
    tag_of,
    tags_complete,
    token_seq,
    token_seq_in,
)


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


def _majority_identity(infos: list[dict]) -> tuple[str, str]:
    """Häufigster echter Artist + häufigstes Album über die Datei-Tags
    (Story 10.9). Leere/Junk-Artists (artist_present) zählen nicht;
    Mehrheit = Modalwert, nicht Konsens."""
    artists = Counter(
        (i["artist"] or i["aartist"]) for i in infos
        if artist_present(i["artist"] or i["aartist"]))
    albums = Counter(i["album"] for i in infos if i["album"])
    return (artists.most_common(1)[0][0] if artists else "",
            albums.most_common(1)[0][0] if albums else "")


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
    fortlaufend nummeriert; Discs aus CD/LP-Suffixen. Story 10.9: bei
    Serien-/Label-Ordnern gewinnt die korroborierte Datei-Mehrheit
    (Artist UND Album als Tokenfolgen im RAW-Ordnernamen) gegen fehlenden
    oder Junk-Parse. Ein Trockenlauf plant nur und schreibt nichts.
    Liefert (erfolg, hinweis).
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

    # Story 10.9 (Serienordner): Label-/Serien-Konventionen wie
    # '2019 - Essential Albums - Artist • Album' zerlegt der Parser nicht
    # zuverlässig (Artist fehlt, oder das Serien-Label wird zum Artist).
    # Trägt die Datei-Mehrheit eine saubere Identität und enthält der
    # RAW-Ordnername Artist UND Album als kontinuierliche Tokenfolgen
    # (10.7-Korroboration), gewinnt die Mehrheit — gegen fehlenden wie
    # gegen Junk-Parse. Ohne korroborierte Mehrheit (leere Vinyl-Tags,
    # Tom-Waits/Willie-Fall) gilt unverändert der Parse.
    folder = os.path.basename((unit.get("path") or "").rstrip("\\/"))
    major_artist, major_album = _majority_identity(infos)
    if (major_artist and major_album
            and token_seq_in(folder, major_artist)
            and token_seq_in(folder, major_album)
            and (token_seq(folder_artist) != token_seq(major_artist)
                 or token_seq(album) != token_seq(major_album))):
        folder_artist, album = major_artist, major_album
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
    from .engine import fill_empty_original_years, restrict_sources
    from .session import MusikSession, va_gate_unit

    # as-is imports perform no lookups — never load metadata source
    # plugins (a broken beatport4 token must not be able to kill an
    # asis run through its import_begin setup).
    restrict_sources([])
    setup_beets()
    st = state_mod.load()
    want = state_mod.norm_key(only) if only else None
    statuses = ("review", "unmatched", "network")
    if include_pending:
        statuses += ("pending",)

    from beets import config as beets_config
    from beets.importer.session import ImportSession

    lib = open_library()

    selected = []
    repaired: dict[str, str] = {}
    for u in state_mod.units(st).values():
        if u.get("status") not in statuses:
            continue
        if want:
            upath = state_mod.norm_key(u["path"])
            if not state_mod.path_under(upath, want):
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

            _engine.trash_unreadable(unit, "asis")

            unit["decision_kind"] = _engine.release_kind(unit)
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

    fixed = fill_empty_original_years(lib)
    if fixed:
        print(f"filled empty original_year on {fixed} album(s)/item(s)")
    print(f"asis: {done} unit(s) imported with their own tags")
    return 0
