# Story 9.9: repair_from_folder — Tag-Reparatur aus Ordner-Identität.
# Echte Mini-MP3s (2 valide MPEG-Frames + ID3v2), keine Mocks an mutagen —
# gelesen/geschrieben wird über denselben Pfad wie in der Produktion.
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mutagen.easyid3 import EasyID3  # noqa: E402
from mutagen.id3 import ID3  # noqa: E402

from musik.asis import (  # noqa: E402
    _folder_identity,
    _split_disc_suffix,
    _title_from_filename,
    repair_from_folder,
)
from musik.scan import tags_complete  # noqa: E402  (Story 6.4: Gate lebt in scan)

FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413  # MPEG-1 L3, 128 kbit/s, 44.1 kHz

failures = []


def check(name, cond, detail=""):
    status = "OK  " if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def mk_mp3(path, tags=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(FRAME * 2)
    ID3().save(path, v2_version=3)  # ID3-Header anlegen
    if tags:
        e = EasyID3(path)
        for k, v in tags.items():
            e[k] = v
        e.save()


def read_tags(path, keys=("artist", "albumartist", "album", "title",
                          "date", "tracknumber", "discnumber")):
    e = EasyID3(path)
    out = {}
    for k in keys:
        vals = e.get(k) or []
        out[k] = str(vals[0]) if vals else ""
    return out


def unit(folder, files):
    return {"path": folder, "files": files}


# --- 1. Ordner-Identität (reale Konventionen) --------------------------
ident = _folder_identity(
    "2017 - GREATEST HITS • Breaking The Law- A Tribute To Judas Priest's "
    "Greatest Hits [US] [2CD]")
check("bullet: Jahr", ident.get("year") == "2017", str(ident))
check("bullet: Artist", ident.get("artist") == "Breaking The Law", str(ident))
check("bullet: Album",
      ident.get("album") == "A Tribute To Judas Priest's Greatest Hits",
      str(ident))

ident = _folder_identity("0134. The Beatles - White Album [1968]")
check("1001: Jahr", ident.get("year") == "1968", str(ident))
check("1001: Artist/Album",
      (ident.get("artist"), ident.get("album"))
      == ("The Beatles", "White Album"), str(ident))

ident = _folder_identity(
    "1977 - GREATEST HITS • Elton John - Elton John's Greatest Hits Vol. II "
    "[Germany Vinyl LP]")
check("Vol bleibt: Album",
      ident.get("album") == "Elton John's Greatest Hits Vol. II", str(ident))

# --- 2. Disc-Suffix-Strip ----------------------------------------------
base, disc = _split_disc_suffix("A Tribute To Judas Priest's Greatest Hits CD1")
check("disc: CD1", (base, disc)
      == ("A Tribute To Judas Priest's Greatest Hits", 1), f"{base!r} {disc}")
base, disc = _split_disc_suffix("All Time Greatest Hits(LP1)")
check("disc: (LP1)", (base, disc) == ("All Time Greatest Hits", 1),
      f"{base!r} {disc}")
base, disc = _split_disc_suffix("Buddy Holly(LP2).")
check("disc: (LP2).", (base, disc) == ("Buddy Holly", 2), f"{base!r} {disc}")
base, disc = _split_disc_suffix("Greatest Hits Vol. 2")
check("disc: Vol. 2 bleibt echt",
      (base, disc) == ("Greatest Hits Vol. 2", None), f"{base!r} {disc}")
base, disc = _split_disc_suffix("Greatest Hits 1972-1978")
check("disc: Jahresbereich bleibt echt",
      (base, disc) == ("Greatest Hits 1972-1978", None), f"{base!r} {disc}")

# --- 3. Titel aus Dateinamen -------------------------------------------
check("titel: dots",
      _title_from_filename("A1.watching.the.river.flow.mp3")
      == "Watching The River Flow",
      _title_from_filename("A1.watching.the.river.flow.mp3"))
check("titel: Apostroph",
      _title_from_filename("A2.don't.think.twice,.it's.all.right.mp3")
      == "Don't Think Twice, It's All Right",
      _title_from_filename("A2.don't.think.twice,.it's.all.right.mp3"))
check("titel: (NN)-Präfix",
      _title_from_filename(
          "(01) A Theme From The Threepenny Opera (Mack The Knife).mp3")
      == "A Theme From The Threepenny Opera (Mack The Knife)",
      _title_from_filename(
          "(01) A Theme From The Threepenny Opera (Mack The Knife).mp3"))
check("titel: A1-Leerzeichen",
      _title_from_filename("A1 Gimme Gimme Gimme (A Man After Midnight).mp3")
      == "Gimme Gimme Gimme (A Man After Midnight)",
      _title_from_filename("A1 Gimme Gimme Gimme (A Man After Midnight).mp3"))

tmp = tempfile.mkdtemp(prefix="smoke_repair_")
try:
    # --- 4. Vinyl-Rip: alle Tags leer (Dylan-Fall) ----------------------
    folder = os.path.join(
        tmp, "1971 - GREATEST HITS • Bob Dylan - Greatest Hits Vol. II "
             "[US Vinyl 2LP]")
    f1 = os.path.join(folder, "A1.watching.the.river.flow.mp3")
    f2 = os.path.join(folder, "B1.leopard.skin.pill.box.hat.mp3")
    mk_mp3(f1)
    mk_mp3(f2)
    u = unit(folder, [f1, f2])
    ok, why = tags_complete(u)
    check("dylan: davor incomplete", not ok, why)
    ok, note = repair_from_folder(u)
    check("dylan: repariert", ok, note)
    ok, why = tags_complete(u)
    check("dylan: danach complete", ok, why)
    t1, t2 = read_tags(f1), read_tags(f2)
    check("dylan: artist", t1["artist"] == "Bob Dylan", str(t1))
    check("dylan: album", t1["album"] == "Greatest Hits Vol. II", str(t1))
    check("dylan: jahr", t1["date"] == "1971", str(t1))
    check("dylan: titel 1",
          t1["title"] == "Watching The River Flow", str(t1))
    check("dylan: titel 2",
          t2["title"] == "Leopard Skin Pill Box Hat", str(t2))
    check("dylan: tracks fortlaufend",
          (t1["tracknumber"], t2["tracknumber"]) == ("1", "2"),
          f"{t1['tracknumber']!r} {t2['tracknumber']!r}")

    # --- 5. Album-Varianten (LP1/LP2, Beach-Boys-Fall) ------------------
    folder = os.path.join(
        tmp, "1974 - GREATEST HITS • The Beach Boys - All Time Greatest "
             "Hits [Netherlands Vinyl 2LP]")
    f1 = os.path.join(folder, "01. Surfin' Safari.mp3")
    f2 = os.path.join(folder, "02. 409.mp3")
    mk_mp3(f1, {"artist": "The Beach Boys", "albumartist": "The Beach Boys",
                "album": "All Time Greatest Hits(LP1)",
                "title": "Surfin' Safari", "tracknumber": "1"})
    mk_mp3(f2, {"artist": "The Beach Boys", "albumartist": "The Beach Boys",
                "album": "All Time Greatest Hits(LP2)",
                "title": "409", "tracknumber": "1"})
    u = unit(folder, [f1, f2])
    ok, why = tags_complete(u)
    check("beachboys: davor incomplete (Album-Varianten)", not ok, why)
    ok, note = repair_from_folder(u)
    check("beachboys: repariert", ok, note)
    ok, why = tags_complete(u)
    check("beachboys: danach complete", ok, why)
    t1, t2 = read_tags(f1), read_tags(f2)
    check("beachboys: Album vereinheitlicht",
          t1["album"] == "All Time Greatest Hits"
          and t2["album"] == "All Time Greatest Hits", str(t1) + str(t2))
    check("beachboys: disc 1/2",
          (t1["discnumber"], t2["discnumber"]) == ("1", "2"),
          f"{t1['discnumber']!r} {t2['discnumber']!r}")
    check("beachboys: Artist unangetastet",
          t1["artist"] == "The Beach Boys", str(t1))

    # --- 6. VA-Tribute (JP-Fall: viele echte Bands, Ordner-Artist falsch)
    folder = os.path.join(
        tmp, "2017 - GREATEST HITS • Breaking The Law- A Tribute To Judas "
             "Priest's Greatest Hits [US] [2CD]")
    files = []
    for i, (band, ttl, cd) in enumerate([
            ("British Steel", "Freewheel Burning", "CD1"),
            ("Cage", "Beyond The Realms Of Death", "CD1"),
            ("Berzon", "The Sentinel", "CD2"),
            ("Aaron Seals", "Breaking The Law", "CD2")], 1):
        p = os.path.join(folder, f"0{i}. {ttl}.mp3")
        mk_mp3(p, {"artist": band, "albumartist": band,
                   "album": f"A Tribute To Judas Priest's Greatest Hits {cd}",
                   "title": ttl, "tracknumber": str(i)})
        files.append(p)
    u = unit(folder, files)
    ok, note = repair_from_folder(u)
    check("tribute: repariert", ok, note)
    ok, why = tags_complete(u)
    check("tribute: danach complete", ok, why)
    t = read_tags(files[0])
    check("tribute: VA gesetzt",
          t["albumartist"] == "Various Artists", str(t))
    check("tribute: Band-Artist erhalten", t["artist"] == "British Steel",
          str(t))
    check("tribute: Album vereinheitlicht",
          t["album"] == "A Tribute To Judas Priest's Greatest Hits", str(t))
    t3 = read_tags(files[2])
    check("tribute: disc 2", t3["discnumber"] == "2", str(t3))

    # --- 7. Trockenlauf schreibt nichts ---------------------------------
    folder = os.path.join(
        tmp, "1980 - GREATEST HITS • Aerosmith - Greatest Hits [US Vinyl LP]")
    f1 = os.path.join(folder, "A1 Dream On.mp3")
    mk_mp3(f1)
    u = unit(folder, [f1])
    before = open(f1, "rb").read()
    ok, note = repair_from_folder(u, dry_run=True)
    check("dryrun: meldet Reparatur", ok, note)
    check("dryrun: Hinweis gekennzeichnet", "würde reparieren" in note, note)
    check("dryrun: Datei unverändert", open(f1, "rb").read() == before)
    ok, _ = tags_complete(u)
    check("dryrun: Gate weiterhin offen", not ok)

    # --- 8. Ausschlüsse -------------------------------------------------
    f1 = os.path.join(tmp, "dump", "01. Foo.mp3")
    mk_mp3(f1)
    u = {"path": os.path.join(tmp, "dump"), "files": [f1],
         "singleton": True}
    ok, note = repair_from_folder(u)
    check("singleton ausgenommen", not ok, note)
    u = {"path": os.path.join(tmp, "fetch-20260101-000000"),
         "files": [f1]}
    ok, note = repair_from_folder(u)
    check("fetch-staging ausgenommen", not ok, note)

    # --- 9. Junk-Artist wird vom Ordner überschrieben (Willie-Fall) -----
    folder = os.path.join(
        tmp, "0346. Willie Nelson - Red Headed Stranger [1975]")
    f1 = os.path.join(folder, "01. Blue Eyes Crying In The Rain.mp3")
    mk_mp3(f1, {"artist": "Tom Waits", "albumartist": "Tom Waits",
                "album": "Red Headed Stranger", "title": "Blue Eyes",
                "tracknumber": "1"})
    u = unit(folder, [f1])
    ok, note = repair_from_folder(u)
    check("willie: repariert", ok, note)
    t = read_tags(f1)
    check("willie: Junk-Artist ersetzt",
          t["artist"] == "Willie Nelson"
          and t["albumartist"] == "Willie Nelson", str(t))

    # --- 10. Serienordner: Mehrheit korroboriert (Story 10.9, Valli) ---
    # '2019 - Essential Albums - Artist • Album': der Parser findet
    # keinen Artist (Bullet trennt Artist/Album, Label steht vorn); die
    # Datei-Mehrheit trägt beide Identitätsteile und der RAW-Ordner
    # enthält sie als Tokenfolgen → Mehrheit gewinnt, abweichende
    # Einzeldatei wird auf sie gezogen.
    folder = os.path.join(
        tmp, "2019 - Essential Albums - Frankie Valli & The Four Seasons "
             "• Essential Collection")
    f1 = os.path.join(folder, "01. Frankie Valli & The Four Seasons - "
                              "Sherry.mp3")
    f2 = os.path.join(folder, "02. Frankie Valli & The Four Seasons - "
                              "Whatever You Say.mp3")
    mk_mp3(f1, {"artist": "Frankie Valli & The Four Seasons",
                "albumartist": "Frankie Valli & The Four Seasons",
                "album": "Essential Collection", "title": "Sherry",
                "tracknumber": "1", "date": "2019"})
    mk_mp3(f2, {"artist": "Frankie Valli & The Four Seasons",
                "albumartist": "Frankie Valli & The Four Seasons",
                "album": "Rarities (Volume 2)", "title": "Whatever You Say",
                "tracknumber": "2", "date": "2019"})
    u = unit(folder, [f1, f2])
    ok, why = tags_complete(u)
    check("valli: davor incomplete (Album-Variante)", not ok, why)
    ok, note = repair_from_folder(u)
    check("valli: repariert", ok, note)
    ok, why = tags_complete(u)
    check("valli: danach complete", ok, why)
    t1, t2 = read_tags(f1), read_tags(f2)
    check("valli: Album aus Mehrheit, nicht aus Parse-Rest",
          t2["album"] == "Essential Collection", str(t2))
    check("valli: Artist unangetastet",
          t1["artist"] == "Frankie Valli & The Four Seasons"
          and t2["artist"] == "Frankie Valli & The Four Seasons",
          str(t1) + str(t2))
    check("valli: kein Rarities-Rest",
          t1["album"] == "Essential Collection", str(t1))

    # --- 11. Junk-Parse wird nie geschrieben (Ray-Comma-Fall) ----------
    # '2014 - Essential Albums - Ray Charles, The Essential Collection':
    # der Parse setzt 'Essential Albums' als Artist — die korroborierte
    # Mehrheit (Artist UND Album als Tokenfolgen im RAW-Ordner) ersetzt
    # ihn, bevor irgendein Tag geschrieben wird.
    folder = os.path.join(
        tmp, "2014 - Essential Albums - Ray Charles, The Essential "
             "Collection [2CD]")
    f1 = os.path.join(folder, "01. Ray Charles - What'd I Say.mp3")
    f2 = os.path.join(folder, "02. Ray Charles - Georgia On My Mind.mp3")
    mk_mp3(f1, {"artist": "Ray Charles", "albumartist": "Essential Albums",
                "album": "The Essential Collection",
                "title": "What'd I Say", "tracknumber": "1",
                "date": "2014"})
    mk_mp3(f2, {"artist": "Ray Charles", "albumartist": "Essential Albums",
                "album": "The Essential Collection",
                "title": "Georgia On My Mind", "tracknumber": "2"})
    u = unit(folder, [f1, f2])
    ok, note = repair_from_folder(u)
    check("ray: repariert", ok, note)
    t1, t2 = read_tags(f1), read_tags(f2)
    check("ray: AA aus Mehrheit statt Junk-Parse",
          t1["albumartist"] == "Ray Charles"
          and t2["albumartist"] == "Ray Charles", str(t1) + str(t2))
    check("ray: kein 'Essential Albums' Rest",
          "Essential Albums" not in str(t1) + str(t2), str(t1) + str(t2))
    check("ray: date gefüllt aus Ordnerjahr", t2["date"] == "2014", str(t2))

    # --- 12. Mehrheit NICHT korroboriert → Parse gewinnt ---------------
    # Ohne Tokenfolgen-Unterstützung im Ordner bleibt es beim Parse
    # (Willie-Klasse bleibt grün; keine Teil-Korroboration).
    folder = os.path.join(tmp, "0347. Frankie Valli - Something Else")
    f1 = os.path.join(folder, "01. Something Else.mp3")
    mk_mp3(f1, {"artist": "Tom Waits", "albumartist": "Tom Waits",
                "album": "Something Else", "title": "Something Else",
                "tracknumber": "1"})
    u = unit(folder, [f1])
    ok, note = repair_from_folder(u)
    check("guard: repariert", ok, note)
    t = read_tags(f1)
    check("guard: Parse-Artist, nicht Mehrheit",
          t["artist"] == "Frankie Valli"
          and t["albumartist"] == "Frankie Valli", str(t))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if failures:
    print(f"SMOKE FEHLGESCHLAGEN: {len(failures)} — {failures}")
    sys.exit(1)
print("smoke_repair_folder: alle Checks grün")
