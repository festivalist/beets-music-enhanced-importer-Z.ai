---
name: musik-testdaten
description: Test-Policy des musik-Projekts (MusicBrainz-automated). Nutze dieses Skill immer, wenn Features getestet oder verifiziert werden, Import-/Fetch-/Plex-Ketten geprüft werden oder Testläufe geplant werden. Kern: feste Testmatrix (Alben, Singles/EPs, Top-100-Releases, Spotify- und YouTube-Playlists, 0-day) und bei fehlenden Testdaten aktiv beim Anwender nachfragen statt degeneriert zu testen.
---

# musik — Testdaten-Policy

## Testmatrix: jede Änderung an Import/Tagging/Fetch gegen echte Formate prüfen

Ein Feature gilt erst als getestet, wenn es über die repräsentativen
Erscheinungsformate der Bibliothek gelaufen ist — nicht nur über einen
einzigen Convenience-Fall:

| Format | Warum |
|---|---|
| Vollständiges Album | Normalfall: Tracklist, Release-Match, Cover, Ordnerlayout |
| Einzeltrack / Single | Singles-Pfad, abweichende Metadaten |
| EP | Zwischenformat, oft andere Release-Typen |
| Top-100 / Chart-Compilation | VA, viele kurze Tracks, Dubletten-Risiko |
| Spotify-Playlist-Link | Fetch-Kette spotDL, Reihenfolge, m3u/Plex-Playlist |
| YouTube-Playlist-Link | Fetch-Kette yt-dlp/SomeDL, n-challenge, Cookies, Bitrate |
| 0-day / ohne MusicBrainz-Eintrag | asis-Pfad |

Je nach Feature genügt eine begründete Teilmenge — die Auswahl explizit
begründen, nicht stillschweigend auf einen Fall reduzieren. Das Ergebnis
(Import-Pfad, getaggte Werte, auffällige Review-Entscheidungen) kurz
protokollieren, wie in den bisherigen Import-Sitzungen.

## Nicht genug Testdaten? Nachfragen — nicht degeneriert testen

Fehlt ein benötigtes Format aus der Matrix (keine Links, keine Ordner, keine
Cookies), dann:

1. Den Test in ToDo.md als offen vermerken (welches Format fehlt, welcher
   Test steht aus).
2. Am Ende der Runde konkret beim Anwender anfragen: Links (Spotify/YouTube)
   oder Ordnerpfade mit Beispielmaterial.

Ein Feature niemals als "fertig/getestet" melden, wenn die Matrix aus
Testdatenmangel unerledigt blieb.

## Praktisch

- Vorhandene Smoke-Tests nutzen statt neue zu erfinden:
  `manual_tests/smoke_playlists.py`, `manual_tests/smoke_plex_upload.py`.
- Destruktive oder Bulk-Läufe zuerst gegen eine Kopie bzw. den `_trash`-
  Staging-Bereich — nie ungefragt gegen die echte Bibliothek. Längere Läufe
  (große Imports, Batch-Moves) vorher ankündigen.
- Testartefakte (heruntergeladene Testdateien, Log-Auswürfe, Screenshots)
  nach dem Test aufräumen — siehe Skill `musik-doku-hygiene`.
