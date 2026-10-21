"""Smoke test (Story 10.1): Versteckte Verzeichnisse sind für den Ingest unsichtbar.

MusicGrabber 4.4 arbeitet pro Download-Job in `{music_dir}/.mg_staging/<job>/`
= `_incoming/musicgrabber/.mg_staging/…`. Ohne Guard würde der Ingest
halbfertige Downloads als Units sehen, der Scene-Packaging-Sweep MGs
Staging-Metadaten in den Trash befördern und der Leerordner-Pruner MGs
frisch angelegte, noch leere Job-Dirs löschen. Regel (global): Verzeichnisse
mit Dot-Präfix werden vom Ingest weder eingelesen noch angefasst.
"""
import os
import shutil
import struct
import sys

sys.path.insert(0, r"C:\Users\olive\Documents\MusicBrainz-automated")

root = os.path.join(os.environ["TEMP"], "musik_dotdirs_test")
shutil.rmtree(root, ignore_errors=True)

def touch(*parts):
    p = os.path.join(root, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        # minimal valid 8-bit mono PCM WAV so scan's readability check passes
        data = b"\x80" * 64
        header = (
            b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8)
            + b"data" + struct.pack("<I", len(data))
        )
        f.write(header + data)
    return p

# --- Szene: MG-Staging neben einem fertigen Drop (exakt das 4.4-Bild) ---
real = touch("Albums", "The Beatles", "1965 - Help!", "01 - Help.wav")
staged = touch(".mg_staging", "job-abc", "Singles", "An Artist", "01 - Half Done.wav")
touch(".mg_staging", "job-abc", ".meta.json")
touch(".mg_staging", "job-def", "cover.nfo")
touch("Albums", "The Beatles", "1965 - Help!", "cover.nfo")  # junk-Sweep-Futter

from musik import scan

# 1) classify: nur die echte Unit — nichts aus .mg_staging
units, notes = scan.classify(root)
assert len(units) == 1, f"erwartet 1 Unit, got {len(units)}: {units}"
assert "The Beatles" in units[0]["path"] and ".mg_staging" not in units[0]["path"]
assert all(".mg_staging" not in f for u in units for f in u["files"])
print("classify ok: .mg_staging erzeugt keine Units")

# 2) collect_audio_tree: nur sichtbare Audio-Dateien
tree = scan.collect_audio_tree(root)
assert tree == [os.path.normcase(os.path.normpath(real))] or tree == [real], f"collect_audio_tree falsch: {tree}"
print("collect_audio_tree ok: versteckte Audio-Dateien unsichtbar")

# 3) Junk-Sweep (Scene-Packaging): .nfo in .mg_staging bleibt unangetastet
from musik import ingest
junk = ingest._scene_packaging_junk(root)
assert any("cover.nfo" in j and "Beatles" in j for j in junk), f"echtes Packaging fehlt: {junk}"
assert not any(".mg_staging" in j for j in junk), f"MG-Staging angefasst: {junk}"
print("junk-sweep ok: .mg_staging wird nicht in den Trash gesweept")

# 4) Pruner: sichtbare leere Kinder weg, versteckte bleiben (auch leer)
os.remove(staged)
hidden_dir = os.path.join(root, ".mg_staging", "job-xyz")
os.makedirs(hidden_dir)  # MG legt den Job-Dir an, VOR dem ersten File
visible_empty = os.path.join(root, "Albums", "leere Hülle")
os.makedirs(visible_empty)
ingest._prune_empty_children(root)
assert not os.path.isdir(visible_empty), "sichtbare leere Hülle wurde nicht gepräunt"
assert os.path.isdir(hidden_dir), "leeres MG-Job-Dir wurde gelöscht (Race!)"
assert os.path.isdir(os.path.join(root, ".mg_staging"))
assert os.path.isdir(root)
print("pruner ok: versteckte Dirs werden weder betreten noch gelöscht")

# 5) keep-Semantik: verschachtelte (konfigurierte) Roots bleiben verankert —
# wie im Pruner vor Story 10.1
nested_root = os.path.join(root, "Albums", "musicgrabber")
os.makedirs(nested_root)
ingest._prune_empty_children(root, keep={nested_root})
assert os.path.isdir(nested_root), "verschachtelter Keep-Root wurde gepräunt"
print("pruner keep ok: konfigurierte Roots überleben den Lauf")

shutil.rmtree(root, ignore_errors=True)
print("INGEST DOT-DIRS SMOKE TEST PASSED")
