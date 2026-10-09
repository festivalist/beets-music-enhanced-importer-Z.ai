# PI-SETUP — Raspberry-Pi-Aufbau: Link → Download → beets → Plexamp

> **Zielgerät:** Raspberry Pi 5, `192.168.50.47` (SSH-Port 22 offen; Stand 2026-09-20)
> **Annahme:** Raspberry Pi OS (64-bit, Bookworm oder trixie) mit SSH-Zugang.
>
> **Dieses Dokument pflegen:** Es muss *immer* den aktuellen Stand von
> `install.sh`, den `config.yaml`-Schlüsseln (`musik: fetch:/plex:/bot_allowlist`),
> dem Bot-Ablauf und der Cookie-Handhabung widerspiegeln. Wer etwas an diesen
> Teilen ändert, aktualisiert diese Anleitung im selben Zug.

Die Kette, die hier aufgebaut wird:

```
Handy (unterwegs) ──Link──> Telegram-Bot (auf dem Pi)
   ├─ spotDL (Spotify-Links) / SomeDL (YouTube-Links, Suchtext)
   │    └─ Download als .m4a (mit Premium-Cookies: 256 kbps) → _incoming/
   └─ MusicGrabber (Phase 9 — zweite Beschaffungs-Engine: Suche, Watched
        Playlists/Artists, auch lossless) → _incoming/musicgrabber/
             └─ musik-Pipeline: scan → import (MusicBrainz) → Genre/Cover
                  └─ Plex-Scan (lokaler PMS) → Album erscheint in Plexamp
```

---

## Phase 0 — Voraussetzungen

- [ ] Pi ist per SSH erreichbar: `ssh <user>@192.168.50.47`
- [ ] Internet auf dem Pi (Downloads + MusicBrainz + Telegram)
- [ ] Optional: USB-Festplatte für die Musik (empfohlen bei größeren Libraries)
- [ ] Diese Dinge bereithalten: Telegram-Bot-Token, YouTube-Cookies (Phase 3),
      Plex-Account

## Phase 1 — Pi vorbereiten

**Noch frisch geflasht?** Raspberry Pi Imager: *Raspberry Pi OS (64-bit, Lite
reicht)* wählen, im Zahnrad-Settings Hostname (z. B. `musikpi`), **SSH
aktivieren**, User/Passwort setzen → flashen, booten. Dann:
`ssh <user>@192.168.50.47`.

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git
```

**Optional: USB-Platte als Musik-Ziel dauerhaft mounten** (ext4 empfohlen;
NTFS funktioniert, ist aber langsamer und mäßiger bei Berechtigungen):

```bash
lsblk -f                                   # UUID der Platte finden
sudo mkfs.ext4 /dev/sda1                   # NUR wenn Platte leer/neu ist!
sudo mkdir -p /mnt/music
sudo nano /etc/fstab                       # Zeile ergänzen:
#   ext4:  UUID=<die-uuid>      /mnt/music  ext4    defaults,nofail            0 2
#   NTFS:  /dev/sda1            /mnt/music  ntfs-3g defaults,nofail,uid=1000,gid=1000 0 0
sudo mount -a
sudo chown -R $USER:$USER /mnt/music
```

**Alternativ NAS-Share (SMB):**

```bash
sudo apt install -y cifs-utils && sudo mkdir -p /mnt/music
# /etc/fstab:  //192.168.50.10/music  /mnt/music  cifs  credentials=/root/.smbcred,uid=1000,nofail  0 0
sudo mount -a
```

> **Wichtig:** Imports *verschieben* Dateien — der Quelldownload-Ordner muss
> beschreibbar sein. Ein nur-lesendes Share taugt als Bibliotheks-Ziel, aber
> nicht als Import-Quelle.

Ohne USB-Platte: einfach `~/Music` nutzen (Standard) und in Phase 2 den
`--library`-Parameter weglassen.

## Phase 2 — Repo holen und installieren

```bash
git clone https://github.com/festivalist/beets-music-enhanced-importer-Z.ai.git ~/musik
cd ~/musik
bash install.sh --library /mnt/music      # oder ohne Parameter → ~/Music
```

`install.sh` erledigt automatisch: Systempakete (ffmpeg, fpcalc, flac),
Python-venv, alle Abhängigkeiten (beets, spotDL, SomeDL, Telegram-Bot),
**Deno-Runtime** (wichtig für manche YouTube-Videos), Setup-Wizard,
systemd-Dienst `musik-bot.service`.

**Wizard-Fragen:**

| Frage | Antwort |
|---|---|
| Music library root | Enter (= `/mnt/music`, per `--library` gesetzt) |
| Beets database file | Enter (Standard: `/mnt/music/beets-library.db`) |
| Discogs personal access token | einfügen oder Enter (= später nachholen) |
| Telegram bot token (BotFather) | **einfügen** (wird in `telegram_token.json` gespeichert) |

Am Ende muss der **Self-Test grün** sein:

```bash
.venv/bin/python musik.py fetch --self-test
# spotdl / somedl / ffmpeg müssen Versionen zeigen
```

## Phase 3 — YouTube-Premium-Cookies (256 kbps)

Cookies gehören auf den **Pi** (dort laufen die Downloads), Dateiname `cookies.txt`
im Repo-Ordner (`~/musik/cookies.txt`). Config ist bereits vorbereitet
(`musik: fetch: cookies_file: cookies.txt`).

**Export am PC/Mac (einmalig, ~5 Minuten):**

1. **Empfohlen: eigenes Browser-Profil anlegen** (Chrome/Firefox: Profil
   „musik-bot" o. ä.). Das isoliert die Session: Sollte YouTube sie je
   invalidieren, bleibt dein Alltags-Browser unberührt. *Kein zweiter
   Account nötig — gleicher Premium-Account, anderes Profil.*
2. Im neuen Profil bei **youtube.com / music.youtube.com** mit dem
   Premium-Account einloggen und `https://music.youtube.com` öffnen.
3. Browser-Erweiterung **„Get cookies.txt LOCALLY"** installieren
   (Chrome/Firefox Store — der Name enthält „LOCALLY", nicht die
   Cloud-Varianten!).
4. Auf der geöffneten music.youtube.com-Seite: Erweiterung → **Export** →
   Format **Netscape**. Es entsteht eine `music.youtube.com_cookies.txt`.
5. Datei nach `cookies.txt` umbenennen.

**Auf den Pi übertragen (vom PC aus, in PowerShell/cmd):**

```powershell
scp cookies.txt <user>@192.168.50.47:~/musik/cookies.txt
```

**Auf dem Pi absichern und prüfen:**

```bash
cd ~/musik
chmod 600 cookies.txt                      # enthält Session-Tokens!
grep -c "youtube" cookies.txt              # sollte > 0 Zeilen liefern
```

**Verhalten:** Cookies aktiv → 256 kbps, weniger Bot-Prüfungen,
altersbeschränkte Videos. Datei fehlt/abgelaufen → Warnung im Log und
anonymer Download mit 128 kbps (nichts bricht). **Neu exportieren** musst
du nach Logout oder Passwortwechsel — ansonsten halten Cookies lange.

**Risiko-Hinweis (Kurzfassung, Details im README-Runbook):** Die Pipeline ist
mit Cookies extra zahm (max. 2 Threads, Request-Pacing, lange Retry-Pausen,
Bot-Check-Erkennung mit 5-fach verlängerter Pause). Bei persönlichem Volumen
ist der realistische Worst Case eine invalidierte Session. Automatisiertes
Downloaden verstößt gegen YouTube-ToS — Restrisiko liegt beim Account-Inhaber.

## Phase 4 — Telegram-Bot auf dem Pi scharf schalten

**Wichtig zuerst:** Ein Bot-Token darf nur von **einem** Poller genutzt werden.
Läuft noch der Windows-Test-Bot, stoppe ihn vorher (Windows: die Python-Prozesse
mit `musik.py bot` beenden bzw. das Fenster schließen) — sonst gibt es
409-Konflikte.

```bash
# Token ist schon da (Phase 2, Wizard) — sonst:
#   nano ~/musik/telegram_token.json   →  {"token": "123:ABC..."}
sudo systemctl start musik-bot
sudo systemctl enable musik-bot           # startet beim Boot (Installer hat das schon)
journalctl -u musik-bot -f                # Log live mitverfolgen
```

**Chat-ID freischalten (einmalig):**

1. Dem Bot vom Handy aus eine Nachricht schicken (welcher Bot es ist, steht im Log: `journalctl -u musik-bot | grep listening`).
2. Antwort: „🚫 Nicht autorisiert. Deine Chat-ID ist **123456789** …"
   *(Die gleiche ID steht im Log: `journalctl -u musik-bot | grep unauthorized`)*
3. Auf dem Pi: `nano ~/musik/config.yaml` →
   `musik: bot_allowlist: [123456789]` → speichern.
4. `sudo systemctl restart musik-bot`

Danach: `/start` → Begrüßung, `/status` → „gerade läuft nichts", `/asis` →
wartende Import-Einheiten als Knöpfe. Fertig.

## Phase 5 — Plex Media Server (auf dem Pi) + Plexamp-Anbindung

**5.1 Installation (ARM64):**

> **Bekanntes Problem (Stand 2026-09-21), betrifft trixie:** Der
> Plex-Repo-Signatur-Key hat nur SHA1-Selbstsignaturen. Aktuelles Raspberry Pi
> OS (Debian trixie) prüft apt-Signaturen mit `sqv` (Sequoia), und seit dem
> 2026-02-01-Cutoff lehnt der SHA1 ab — `apt update` bricht ab mit „Signing
> key … is not bound … SHA1 is not considered secure since 2026-02-01". Der
> Key selbst ist echt. **Wichtig:** sqv akzeptiert als Key-Bindung nur
> **Selbstsignaturen** — der Key lässt sich nicht lokal neu signieren (auch
> nicht zurückdatiert; getestet, scheitert am selben Fehler). Nur Plex kann
> den Key heilen. Workaround bis dahin: die SHA1-Policy von sqv über eine
> Umgebungsvariable lockern (apt-secure bleibt an, es werden nur Alt-Keys
> wieder akzeptiert). Sobald Plex einen neuen Key veröffentlicht:
> Übersteuerung entfernen (`sudo sed -i '/SEQUOIA_CRYPTO_POLICY/d'
> /etc/environment` + Datei löschen) und Original-Key frisch importieren.

```bash
sudo apt install -y curl gnupg
echo deb https://downloads.plex.tv/repo/deb public main | sudo tee /etc/apt/sources.list.d/plexmediaserver.list
curl -fsSL https://downloads.plex.tv/plex-keys/PlexSign.key | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/plex.gpg

# 1) Policy-Übersteuerung anlegen: vorhandene Standard-Policy kopieren und
#    darin den SHA1-Cutoff hochsetzen; fehlt sie, eine Minimal-Policy schreiben:
sudo cp /etc/crypto-policies/back-ends/apt-sequoia.config /etc/sequoia-plex-allow-sha1.config 2>/dev/null \
  && sudo sed -i '/sha1/Is/2026-02-01/2066-01-01/g' /etc/sequoia-plex-allow-sha1.config \
  || printf '[hash_algorithms]\nsha1.collision_resistance = "always"\nsha1.second_preimage_resistance = "always"\n' \
      | sudo tee /etc/sequoia-plex-allow-sha1.config
#    (Keys exakt so — sqv erwartet: second_preimage_resistance, collision_resistance,
#     default_disposition. Bei Parse-Fehlern schlägt sqv für ALLE Repos fehl!)

# 2) Testen — welche der beiden Variablen sqv liest, variiert je nach Stand:
sudo SEQUOIA_CRYPTO_POLICY=/etc/sequoia-plex-allow-sha1.config apt update \
  || sudo APT_SEQUOIA_CRYPTO_POLICY=/etc/sequoia-plex-allow-sha1.config apt update
#    Läuft der Plex-Eintrag jetzt ohne Err durch? → weiter zu 3).
#    Immer noch SHA1-Fehler? Diagnose:  sudo SEQUOIA_CRYPTO_POLICY="" apt update
#    (leere Policy = völlig ohne Limit, NUR als Einmal-Test!)
#      - das geht, die Policy-Datei oben aber nicht → Datei-Format anpassen
#      - das geht auch nicht → env erreicht sqv nicht → Plan B unten

# 3) Dauerhaft machen (gilt nach Neu-Anmeldung) + installieren:
echo 'SEQUOIA_CRYPTO_POLICY=/etc/sequoia-plex-allow-sha1.config' | sudo tee -a /etc/environment
sudo apt install -y plexmediaserver
```

**Plan B — ganz ohne Repo** (falls die Policy-Übersteuerung auf deinem System
nicht greift; Updates dann manuell über denselben Block):

```bash
sudo mv /etc/apt/sources.list.d/plexmediaserver.list{,.disabled}
URL=$(curl -fsSL https://plex.tv/api/downloads/5.json | python3 -c \
  "import json,sys;d=json.load(sys.stdin)['computer']['Program'];print(next(r['url'] for r in d['releases'] if r['distro']=='debian' and 'arm64' in r.get('build','')))")
cd /tmp && curl -fsSLO "$URL" && sudo apt install ./"${URL##*/}"
```

**5.2 Server claimen:** Am PC im Netzwerk `http://192.168.50.47:32400/web`
öffnen, mit dem Plex-Account anmelden.

**5.3 Musik-Bibliothek anlegen:** Plex Web → Settings → Libraries →
**Add Library → Music** → Ordner **`/mnt/music`** wählen (der Library-Root
aus Phase 2). Name merken (z. B. „Musik").

**5.4 X-Plex-Token besorgen** (auf dem Pi):

```bash
sudo cat "/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Preferences.xml" \
  | grep -oP 'PlexOnlineToken="[^"]+"'
```

**5.5 In musik eintragen:** `nano ~/musik/config.yaml`, im `musik:`-Block:

```yaml
    plex:
        url: http://127.0.0.1:32400      # PMS läuft auf demselben Pi
        token: DER-TOKEN-AUS-SCHRITT-5.4
        section: Musik                    # exakt der Library-Name aus 5.3
```

**5.6 Für „von unterwegs" wichtig:** In Plex Web → Settings → **Remote Access**
aktivieren (UPnP oder Portfreigabe 32400 im Router). Ohne das funktioniert
Plexamp nur im Heimnetz — Downloads gehen trotzdem (Bot läuft über Telegram).

**Berechtigungs-Falle:** Läuft der Bot als dein User und Plex als
`plex`-User, braucht Plex Leserechte auf `/mnt/music`:
`sudo chmod -R o+rX /mnt/music` (oder Gruppe `plex` ergänzen).

**5.7 Playlists in Plexamp (automatisch):** Ein **Playlist-Link** (Spotify
„…/playlist/…" oder YouTube „…list=…") erzeugt zusätzlich zur Album-Import-Kette
eine echte **Plex-Playlist** — gleiche Reihenfolge, gleicher Name wie in
Spotify/YouTube, sofort in Plexamp sichtbar. Dazu läuft nach dem Import:

1. spotDL schreibt beim Download eine `.m3u8` (Reihenfolge + Name) in den
   Job-Ordner,
2. nach dem Import werden die finalen Bibliothekspfade der Tracks ermittelt
   (beets-DB-Diff) und als `.m3u` nach **`/mnt/music/_playlists/`** geschrieben,
3. die Datei wird an PMS hochgeladen (`POST /playlists/upload`; der Import
   matcht per Dateipfad und wiederholt sich, bis der gescannte Scan die
   Tracks kennt).

Nichts zu tun — es reicht der `plex:`-Block aus 5.5. Feintuning (optional)
in config.yaml: `playlists: false` (aus), `playlist_attempts`/`playlist_wait`
(Retry-Verhalten beim Scan), `playlist_dir` (anderer Ablageort). Tracks, die
noch im Review parken, fehlen in der Playlist zunächst — ein späterer
`/asis`-Import ergänzt sie und lädt die Playlist neu hoch. Manueller
Retry: `.venv/bin/python musik.py plex --playlist "Name"` (oder `all`).

**YouTube-Playlists:** SomeDL schreibt keine m3u — Name und Reihenfolge
kommen stattdessen per yt-dlp (im spotDL-Bundle enthalten; Cookies aus
Phase 3 werden mitgenutzt, falls vorhanden). Gemischte
`watch?v=…&list=…`-Links laden jetzt die komplette Playlist
(`--get-playlist`). Nur wenn yt-dlp die Playlist nicht lesen kann
(privat/gelöscht), greift die Download-Reihenfolge (Datei-Zeitstempel)
als Näherung.

**5.7b Wichtig — Pfad-Trenner (Vorfall 2026-10-08):** Die `paths:`-
Templates in config.yaml müssen **Forward-Slashes** haben. Das Setup-
Wizard erzeugt sie seit dem Fix plattformkorrekt; die vor dem Fix
erzeugten Pi-Configs hatten Windows-Backslashes — beets flacht die auf
Linux zu `_` im Dateinamen ab, und die **gesamte Bibliothek lag flach im
Root** (`Grauzone_1981 - Grauzone_01 ….m4a`). Behoben durch: Templates in
config.yaml auf `/`, dann alle Items per `Item.move()` re-gehomed (DB-
Pfade wandern mit), Playlist-m3us aus den item_ids regeneriert und
`plex --playlist all` neu hochgeladen. Phase 5b (Windows-Bestand) darf
erst mit korrekten Templates laufen — vorherige Imports wären flach
gelanden.

## Phase 5b — Bestand vom Windows-PC übernehmen (Migration)

> **AUSGEFÜHRT 2026-10-09 (per Agent/SSH, Protokoll im ToDo):** SMB+rsync
> wurde durch **tar-over-ssh** ersetzt (SMB-Freigabe ist ohne Admin-Rechte
> nicht skriptbar; tar-Streams laufen über plink, pro Ordner chunked und
> damit abbruchfest). Ablauf: Windows verify+snapshot → tar-Transfer
> (269 Ordner / 4.137 Dateien / 39 GB, 0 Fehler) → Vollständigkeits-Diff
> → Trockenlauf (780 Units, 751 would-as-is) → Echtlauf asis →
> **Nachkorrektur Singles**: Windows-Singletons kamen als Ein-Track-
> Alben herein (Singles-Ordner = eine Unit, beets gruppiert per Album-
> Tag) — 438 zu Singletons konvertiert und ins Singles/-Layout verschoben,
> 34 echte Ein-Track-Alben per Windows-DB-Abgleich geschützt. Endstand:
> 322 Alben / 4.005 Items / 720 Künstler / 38,8 GB, 0 tote Pfade. Die 29
> verbliebenen Units (77 Dateien unter `Singles/<Artist>/`, je Datei ihr
> wahres Ursprungsalbum im Tag) wurden am Abend per neuer Singles-Tree-
> Regel als Singletons importiert (Scan splittet unter dem konfigurierten
> Singleton-Root, siehe README) — Staging `win-lib` damit vollständig
> aufgelöst, Endstand 323 Alben / 4.087 Items.
> Beim manuellen Nachvollziehen bleibt die folgende rsync-Variante gültig:

Wer schon eine getaggte musik-Bibliothek auf dem Windows-PC hat
(`C:\Users\olive\Music` samt Alben/Singles/Compilations-Baum), trägt sie
einmalig rüber — danach ist das **Pi die alleinige Wahrheit** und der
Windows-Ordner bleibt als Sicherungskopie eingefroren (keine Imports
mehr auf Windows; unverarbeitete Quellordner wie `D:\Musik` bleiben
zunächst dort und kommen später normal durch die Pipeline).

**Warum Neu-Import statt DB-Kopieren:** Die Windows-`beets-library.db`
speichert Pfade als Windows-Bytes — auf dem Pi nutzlos. Alles
Wichtige (Genre, ReplayGain, Cover, Jahre) steckt in den **Tags** der
Dateien, und der asis-Import rechnet die Pfade auf `/mnt/music` nach
dem identischen Template um (Duplikate gegen bisherige Pi-Downloads
klärt der eingebaute Qualitätsvergleich automatisch).

**1. Auf Windows — Vorbereitung:**

```bat
cd /d C:\Users\olive\Documents\MusicBrainz-automated
python musik.py report --verify        & rem 0 tote Pfade erwartet
python musik.py snapshot               & rem DB-Archiv als Fallback
ipconfig                               & rem IPv4-Adresse des PCs notieren
```

Dann `C:\Users\olive\Music` freigeben: Rechtsklick → Eigenschaften →
Freigabe → „Freigeben …" → eigenen User mit **Lesen**. (Windows fragt
beim ersten Freigeben nach der Freigabe-Firewall-Regel → zulassen.)

**2. Auf dem Pi — Bot anhalten und Bibliothek ziehen:**

```bash
sudo systemctl stop musik-bot          # kein paralleler Import in dieselbe DB!
sudo apt install -y cifs-utils rsync
sudo mkdir -p /mnt/winmusic /mnt/music/_incoming/win-lib
sudo mount -t cifs //<PC-IP>/Music /mnt/winmusic \
    -o username=olive,uid=$(id -u),gid=$(id -g),ro
rsync -a --info=progress2 \
    --exclude '_trash/' --exclude '_backups/' --exclude '_incoming/' \
    --exclude 'unsorted/' --exclude 'beets-library.db' --exclude '*.log' \
    /mnt/winmusic/ /mnt/music/_incoming/win-lib/
sudo umount /mnt/winmusic
```

(~20–40 GB; rsync ist fortsetzbar — einfach erneut ausführen.)

**3. Trockenlauf:** Klassifizieren und auflisten, nichts wird bewegt:

```bash
cd ~/musik
.venv/bin/python musik.py scan --root /mnt/music/_incoming/win-lib
.venv/bin/python musik.py asis --pending --unit /mnt/music/_incoming/win-lib --dry-run
```

Erwartung: eine Einheit je Album (Windows-Library hat konsistente
Album-Tags), Singles als Einzeldateien, fast alles „would-as-is".

**4. Echtlauf:** verschiebt alles per Rename (gleiches Dateisystem,
schnell) in die finale Struktur unter `/mnt/music`:

```bash
.venv/bin/python musik.py asis --pending --unit /mnt/music/_incoming/win-lib
```

**5. Aufräumen, Gesundcheck, verifizieren:**

```bash
.venv/bin/python musik.py cleanup --root /mnt/music/_incoming/win-lib --dry-run
.venv/bin/python musik.py cleanup --root /mnt/music/_incoming/win-lib
.venv/bin/python musik.py doctor --fix          # Art/Genre-Backfill
.venv/bin/python musik.py stats                 # ~300+ Alben / ~3800 Items erwartet
.venv/bin/python musik.py report --verify       # 0 tote Pfade
.venv/bin/python musik.py plex                  # Plex-Scan: alles in Plexamp
.venv/bin/python musik.py snapshot
sudo systemctl start musik-bot
```

**Grenzen/Hinweise:**
- Externe Cover-Dateien (cover.jpg in Albenordnern) kann cleanup ins
  `_trash`-Archiv verschieben — `doctor --fix` holt sie via fetchart
  zurück (eingebettete Cover sind ohnehin in den Dateien).
- `%aunique{}`-Namenszusätze, die auf Windows durch damalige Duplikate
  entstanden, können beim Import entfallen (Datei wird leicht
  umbenannt — Layout bleibt äquivalent).
- Plexamp startet danach die Sonic Analysis über den kompletten
  Bestand (Hintergrund, dauert).
- Download-Playlists (m3u), die auf Pi-Tracks zeigen, die hierbei als
  Duplikat ersetzt wurden: einmal `.venv/bin/python musik.py plex
  --playlist all` neu hochladen.
- `doctor --quick` ohne Limit decode-testet beim ersten Lauf ALLES
  (Stunden) — für den Anfang `--limit 200` als Spot-Check nutzen.

## Phase 6 — Erst-Test (Checkliste)

**Tipp für SSH-Alltag** — einmalig den Alias setzen:

```bash
echo "alias musik='$HOME/musik/.venv/bin/python $HOME/musik/musik.py'" >> ~/.bashrc && source ~/.bashrc
```

```bash
cd ~/musik
# 1) Werkzeuge
.venv/bin/python musik.py fetch --self-test

# 2) CLI-Kompletttest mit einem Track-Link (ohne Bot):
.venv/bin/python musik.py fetch --import "https://open.spotify.com/track/<id>"
#    → Datei muss unter /mnt/music/Singles/<Artist>/<Jahr> - <Title>.m4a liegen

# 3) Bitrate prüfen (Cookie-Effekt): muss ~256000 statt ~128000 zeigen
ffprobe -v quiet -show_entries format=bit_rate -of csv "/mnt/music/Singles/<Artist>/<file>.m4a"

# 4) Optional — Playlist-Kette (ohne Bot; der Bot macht 4b/4c automatisch):
.venv/bin/python musik.py fetch --import "https://open.spotify.com/playlist/<id>"
#    → /mnt/music/_playlists/<Name>.m3u entsteht (N/N Tracks zugeordnet)
.venv/bin/python musik.py plex && .venv/bin/python musik.py plex --playlist "<Name>"
#    → Playlist liegt in Plex und taucht in Plexamp auf
```

Dann der Bot-Live-Test vom Handy: Album-Link an @<dein-bot-name>
schicken und die Meldungen verfolgen (`⬇️ → 📦 → importiert → 🎧 Plex-Scan`).
Nach kurzer Zeit muss das Album in **Plexamp** auftauchen.

## Phase 7 — Betrieb & Wartung

| Aufgabe | Befehl |
|---|---|
| Bot-Status | `systemctl status musik-bot` |
| Bot-Log live | `journalctl -u musik-bot -f` (install.sh startet Python mit `-u`; ältere Units ohne `-u` zeigen Fortschritt erst nach Puffer-Flush — Live-Einblick dann über den Fetch-Log: `tail -f ~/musik/reports/fetch/$(ls -t ~/musik/reports/fetch | head -1)`) |
| Bot neu starten | `sudo systemctl restart musik-bot` |
| Toolchain aktualisieren (bei YouTube-Ausfällen) | `cd ~/musik && git pull && .venv/bin/python -m pip install -U spotdl somedl && sudo systemctl restart musik-bot` |
| Komplett-Reinstall nach Repo-Update | `bash install.sh --library /mnt/music` (idempotent, hält config.yaml) |
| Cookies neu (nach Logout/Passwortwechsel) | Phase 3 wiederholen (nur Schritt 4-5 + scp) |
| Review-Einheiten auf eigene Tags importieren | Handy: Bot-`/asis` (Knöpfe antippen) · Terminal: `musik.py asis --pending` |
| Windows-Bestand nachträglich übernehmen | Phase 5b (SMB + scan + `asis --pending --unit …`) |
| Plex-Scan manuell anstoßen | `.venv/bin/python musik.py plex` (meldet die konkrete Ursache, falls es hakt) |
| Plex-Playlist neu hochladen | `.venv/bin/python musik.py plex --playlist "Name"` (oder `all`) |
| apt update: Plex-Key-Fehler („not bound", SHA1) | Workaround-Block in Phase 5.1 erneut ausführen (solange Plex den Key nicht neu signiert hat) |
| YouTube schlägt komplett fehl („n challenge solving failed" → „Requested format is not available") | Fehlende JS-Runtime auf dem PATH (die yt-dlp-Warnung „No supported JavaScript runtime" ist das sichere Zeichen): `.venv/bin/python -m pip install -U "yt-dlp[default]"` + Deno installieren (`curl -fsSL https://deno.land/install.sh \| sh -s -- -y` — spotDLs eigener Deno-Download scheitert auf arm64!) + `sudo cp ~/.deno/bin/deno /usr/local/bin/deno`; Probe: `.venv/bin/python -m yt_dlp -F "<video-url>"` darf die Runtime-Warnung NICHT mehr zeigen |
| Backup (DB + Config + Tokens) | `.venv/bin/python musik.py snapshot` |
| Monats-Check | `.venv/bin/python musik.py doctor --quick` |
| Download-Logs | `~/musik/reports/fetch/<job>.log` / `.errors` |

**Playlist-Links importieren auf eigene Tags (asis):** Eine Playlist ist
kein Album für MusicBrainz — die Kette entscheidet Fetch-Einheiten deshalb
direkt auf den Download-Tags (Streaming-Katalog-Tags sind pro Track
autoritativ, der Job-Ordner ist kein Release-Ordner). Ein Playlist-Link
läuft damit **ohne Interaktion** durch: Download → asis-Import →
Plex-Playlist (5.7). Nur Tracks mit unvollständigen Tags (grobe
YouTube-Metadaten) parken im Review — die holst du so nach:

- **Vom Handy:** dem Bot **`/asis`** schicken → wartende Einheiten erscheinen
  als Knöpfe („Lebanon Hanover · 30 Tracks (review)") → **antippen** → Import
  läuft, Ergebnis + Plex-Scan kommen als Nachricht zurück.
- **Am Terminal:** `.venv/bin/python musik.py asis --pending` (alle
  tag-vollständigen Einheiten auf eigene Tags; `--dry-run` zeigt vorher nur
  die Liste) oder interaktiv `musik.py review` → `W`.

Die Tracks wandern dabei Track-für-Track in ihre echten Spotify-Alben;
eine zugehörige Plex-Playlist (5.7) wird automatisch ergänzt und neu
hochgeladen.
Bei fehlendem Genre/Cover danach: `.venv/bin/python musik.py doctor --fix`.

**Fehlersuche:** einzelne Track-Fehler → erstes Mittel ist immer ein Re-Fetch
des Albums (Gap-Fill ergänzt nur fehlende Tracks); Massen-Ausfall → Tools
aktualisieren (Zeile oben); Bot antwortet nicht → `journalctl -u musik-bot -n 50`.

## Phase 8 — Abnahme (der komplette Durchlauf)

- [ ] Handy im **Mobilfunk** (WLAN aus): Link an den Bot geschickt
- [ ] Bot meldet Download → Import → „in Plexamp verfügbar"
- [ ] Album erscheint in Plexamp, Cover + Genre sichtbar, ReplayGain aktiv
- [ ] Playlist-Link: Bot meldet „🎵 Plex-Playlist „<Name>“: N Track(s)" —
      Playlist in Plexamp mit Original-Name/Reihenfolge sichtbar
- [ ] Zweiter Link: Album existiert schon → Meldung „bereits vorhanden /
      fehlende Tracks ergänzt"
- [ ] `ffprobe` zeigt 256 kbps (Cookies wirksam)
- [ ] Windows-Test-Bot ist aus; einziges aktives System ist der Pi

## Phase 9 — MusicGrabber (Beschaffungs-Engine Nr. 2, Docker)

> **Rolle (Nordstern, SCOPE-Change 2026-10-08):** MusicGrabber (GitLab
> `g33kphr33k/musicgrabber`, Unlicense) ist die zweite Beschaffungs-Engine
> neben spotDL/SomeDL: Multi-Source-Suche (u. a. Monochrome-FLAC = lossless),
> Watched Playlists (Spotify/YouTube/…), MusicBrainz-Artist-Follow,
> Track-Upgrades. Sie schreibt **ausschließlich** nach
> `/mnt/music/_incoming/musicgrabber` (Staging) — beets/musik bleibt die
> einzige Instanz, die die echte Bibliothek schreibt. Der MG-eigene
> Library-Index zeigt deshalb **nicht** auf `/mnt/music`; Duplikat- und
> Qualitätshoheit liegen bei der musik-Pipeline (`_prepare_units`,
> Qualitäts-Tiers). Das Docker-Image ist multi-arch (amd64+arm64, Docker-Hub
> geprüft 2026-10-08) und läuft unverändert auf dem Pi 5.

**9.1 Docker installieren (einmalig, aus den Debian-Quellen — kein fremdes apt-Repo):**

> **trixie-Realität (Stand 2026-10-08, so deployed):** `docker-compose-v2` liegt
> nicht in den Debian-Quellen; das dortige `docker-compose` ist das EOL-v1-
> Python-Paket. Daher `docker.io` aus Debian + das Compose-v2-Plugin als
> Standalone-Binary von GitHub (offizielles Release-Artefakt, kein Zusatz-Repo,
> kein apt-Key-Thema). Nebenbeobachtung: `sudo` strippt
> `SEQUOIA_CRYPTO_POLICY` — `apt update` zeigt in Nicht-Login-Shells die
> Plex-SHA1-Warnung; für alle anderen Repos ist das harmlos (Warnung, kein
> Abbruch; dePLOYt wurde trotzdem problemlos).

```bash
sudo apt update && sudo apt install -y docker.io
sudo usermod -aG docker $USER     # danach neu anmelden oder `newgrp docker`
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -fsSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-aarch64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
sudo docker compose version       # muss eine v2-Version zeigen
```

**9.2 Compose + .env aus dem Repo:**

```bash
cd ~/musik && git pull
mkdir -p /mnt/music/_incoming/musicgrabber
cd musicgrabber
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # API-Key erzeugen
nano .env                        # MUSICGRABBER_API_KEY=… ; PUID/PGID = `id -u` / `id -g`
```

**9.3 Starten:**

> **Deployed 2026-10-08 per SSH** (Image 2,6 GB arm64, Health-Check Up,
> Mounts verifiziert: nur `./data` + Staging; Web-UI antwortet mit 200).

```bash
docker compose up -d              # als pi nach newgrp/Neuanmeldung, sonst sudo
docker compose logs -f           # Start beobachten (erste Init kann dauern)
```

Web-UI: `http://192.168.50.47:38274` — nur LAN, kein Port-Forwarding (von
unterwegs läuft alles über Telegram-Bot und Plexamp, nicht über MG).

**9.4 Grundeinstellungen (Settings-Tab):**

- Quellen: Monochrome, YouTube, SoundCloud, FreeMp3Cloud aktiv; JioSaavn
  optional. **slskd/Soulseek: aus** (SCOPE §8, später).
- Qualität lossless-first: Provider-Format behalten (kein Re-Encoding),
  untere Bitrate-Schwelle z. B. 192 kbps.
- YouTube-Cookies: dieselbe Export-Datei wie Phase 3 (liegt unter
  `~/musik/cookies.txt`), sofern MG sie verlangt.
- **Telegram-Notifications: NICHT den Token des musik-bots eintragen** —
  Telegram erlaubt pro Token nur einen Betriebstyp (Polling XOR Webhook), der
  musik-bot pollt bereits. Entweder eigenen BotFather-Bot für MG anlegen oder
  verzichten (der Import-Bericht kommt über den musik-bot).

**9.5 Erster Test (Akzeptanz Story 1.1):**

- [ ] Im UI einen Track suchen und laden → Dateien erscheinen unter
      `/mnt/music/_incoming/musicgrabber/Singles/…`
- [ ] Container schreibt nirgendwo sonst: `docker inspect musicgrabber`
      zeigt nur `./data` und das Staging als Mounts
- [ ] `ffprobe` zeigt FLAC (Monochrome-Quelle) bzw. ≥256 kbps

**9.6 Automatischer Import (musik ingest):** Der Staging-Ordner ist
transient — `musik-ingest.timer` (mit `install.sh` installiert, alle 15 min,
`flock`-gesichert) läuft die Kette scan → import (MusicBrainz) → asis →
cleanup → Genre/Cover → Plex-Scan über `_incoming/musicgrabber`. Manuell:
`.venv/bin/python musik.py ingest`. Damit landet MusicGrabber-Ausgabe
zuverlässig getagggt und nach config.yaml einsortiert in der Bibliothek
(MG-`Playlists/*.m3u` folgen mit Story 2.2). Hinweis: Der Timer kollidiert
selten mit einem laufenden Bot-Import (beide schreiben die beets-DB) — dann
errors einer Seite, der nächste Timer-Lauf holt nach.

**9.7 Betrieb:**

| Aufgabe | Befehl |
|---|---|
| Status / Logs | `docker compose ps` / `docker compose logs -f` |
| Update | `cd ~/musik/musicgrabber && docker compose pull && docker compose up -d` |
| Stop / Start | `docker compose down` / `docker compose up -d` |
| Backup | `musicgrabber/data/` mitsichern (sqlite-Index + Einstellungen) |
| Staging manuell importieren | `.venv/bin/python musik.py ingest` (macht der Timer sonst alle 15 min) |
| Ingest-Timer | `systemctl list-timers musik-ingest*` · Log: `journalctl -u musik-ingest.service -n 50` |

**9.8 Bot-Integration (Freitext → MusicGrabber):** Der Telegram-Bot
routet **Freitext-Suchen** („artist - title") zuerst an MusicGrabber —
mehrere Quellen inkl. Lossless, Qualitäts-Tiers, MusicBrainz-Dauerprüfung.
Die Auswahl-Regel im Bot bevorzugt Ergebnisse, deren Artist/Channel die
Artist-Tokens der Anfrage tragen (Rang 1 ist nicht immer das echte Lied —
beobachtet: ein „Party Mix" über dem offiziellen Video). **Links**
(Spotify/YouTube) bleiben bewusst auf der spotDL/SomeDL-Kette mit
Plex-Playlists. Liefert MG nichts (keine Ergebnisse, Dauer-Mismatch,
Container down), fällt der Bot automatisch auf die YouTube-Kette zurück
und meldet den Grund. Nach MG-Erfolg importiert der Bot sofort selbst
(`musik ingest` — kein Warten auf den 15-Min-Timer); Plex wird von ingest
aktualisiert. Config (Defaults reichen auf dem Pi): `musik: musicgrabber:
{url: http://127.0.0.1:38274, enabled: true, job_timeout: 600}`.

**Troubleshooting:** Container down → Bot meldet „nicht erreichbar" und
nutzt den Fallback (Downloads laufen weiter, nur mit YouTube-Qualität).
Crash-Loop mit `PermissionError: /music/Singles` → Staging-Root wurde
gelöscht und von Docker als root neu angelegt:
`sudo chown -R 1000:1000 /mnt/music/_incoming/musicgrabber && sudo docker
restart musicgrabber` (seit keep_root-Fix 4bc89fb dauerhaft verhindert).
MG-Job fehlschlägt mit `No such file or directory: '/music/Singles'` →
die Layout-Anker (`Singles/`, `Albums/`, `Playlists/`) fehlen im Staging;
MG legt sie NICHT selbst an. Ursache 2026-10-09: cleanup hatte das
geleerte Staging bis auf die Wurzel geräumt (keep_root schützte nur die
Wurzel). Doppelt gefixt: cleanup verschont seither leere Top-Level-
Ordner unter dem Staging-Root, und Bot/ingest rufen vor jedem MG-Download
bzw. nach jedem Cleanup `ensure_staging_layout()` auf (legt fehlende
Anker host-seitig als User pi neu an — NIEMALS im Container, sonst
root-owned → Crash-Loop). Manuelle Behebung:
`mkdir -p /mnt/music/_incoming/musicgrabber/{Singles,Albums,Playlists}`.

**9.9 Bot-Integration Track → Album (Story 2.5, 2026-10-09):** Nach jedem
erfolgreichen Freitext-Track-Import bietet der Bot das zugehörige Album /
die EP als Inline-Buttons an. Kandidaten liefert eine MusicBrainz-
Recording-Suche im musik-Tool (`musik/releases.py`): nur Album/EP-Release-
Groups, Kompilationen/Live-Alben/Soundtracks/Singles gefiltert, Cover-
Artists über Artist-Token-Guard ausgeschlossen, bis zu **5** Kandidaten —
Reihenfolge Score → Reissue-Gewicht → Jahr aufsteigend (Original-Album
zuerst; MB-Scores großer Kataloge sind reine 100-Gleichstände, daher
entscheidet das Jahr), die **neueste** Veröffentlichung ist garantiert
dabei (Nutzerregeln 2026-10-09; Bowie-„Heroes"-Befund: Soundtrack über
dem 1977er Album). Fehlende Jahre werden per EINEM gebündelten RG-Lookup
(`rgid:a OR rgid:b …`) nachgereicht — die Recording-Suche liefert
first-release-date kaum. ASCII-Schreibweisen werden automatisch zurück-
übersetzt („Eisbaer" → „Eisbär"; MBs Lucene-Suche faltet Umlaute nicht).
✓ markiert Alben, die schon in der Bibliothek sind (Tap = Gap-Fill
fehlender Tracks).

Der Button-Tap läuft über MGs native Album-Pipeline (Endpoints gegen
`127.0.0.1:38274`, alle live gegen 4.3.0 verifiziert):

| Schritt | Endpoint | Ergebnis |
|---|---|---|
| Release-Group → Release | `POST /api/albums/resolve-release-group` `{release_group_mbid}` | `{artist, album_title, release_mbid, year, track_count}` |
| Album queue | `POST /api/albums/download` `{artist, album_title, release_mbid}` | `{import_id, track_count, queued_count, album_dir}` |
| Fortschritt | `GET /api/bulk-import/{import_id}/status` bis `complete:true` | `{completed, failed, dupe_skipped, tracks[]}` |

MG lädt Per-Track-Bulk-Import (ISRC-first, bevorzugt Monochrome-FLAC =
16-bit/44.1-kHz-Lossless, Fallbacks m4a/mp3) ins Staging
`Albums/<Artist>/<Album>/` (`.albuminfo`-Sidecar mit release_mbid,
`.lrc`-Lyrics — cleanup räumt beides ab). Danach importiert der Bot sofort
via `musik ingest` (Gap-Fill/Qualitätsersetzung in vorhandene Alben
inklusive) und entfernt den Singleton der ursprünglichen Track-Anfrage,
sobald das Album denselben Song verifiziert enthält. Teilerfolge sind
normal: nicht lieferbare Tracks (Dauer-Mismatch, strenge Artist-Prüfung)
werden namentlich gemeldet — nochmal tippen holt Nachzügler per Gap-Fill
nach. Scheitert das Album komplett, gibt es KEINEN stillen Abstieg auf die
lossy spotDL-Kette (Nordstern lossless-first); stattdessen Hinweis auf
einen Spotify-Album-Link. `/status` zeigt bei laufenden Album-Jobs die
live N/M-Track-Zähler von MG. Config: `musik: musicgrabber:
{album_offer: true, album_job_timeout: 3600}` (Defaults; album_offer
schaltet die Buttons ganz ab).

**Noch offen (Stories 1.2–2.x, siehe ToDo.md):** Quellen-/Qualitäts-Fein-
konfiguration, Testmatrix-Abnahme (Single/Album/Spotify-Playlist/YouTube-
Playlist/0-day), MG-Playlists-M3U in die Plex-Playlist-Kette.

## Anmerkungen & Grenzen

- **Performance (Pi 5):** Fingerabdruck + Tagging ~25 s/Album zzgl. Download —
  komfortabel. Ein Pi Zero 1/2 wäre spürbar langsam.
- **Die Windows drag&drop-Bat-Dateien gelten hier nicht** — CLI und
  Telegram-Bot sind die Schnittstellen auf dem Pi.
- **Lokal schützen:** `config.yaml`, `discogs_token.json`,
  `telegram_token.json`, `cookies.txt` sind bewusst nicht in git — bei
  Neuinstallation sichern (oder `musik snapshot`, das deckt DB+Config+Tokens
  in einem ZIP unter `<library>/_backups/`).
- Alles Entscheidete steht in `state/state.json`, Reporte in `reports/`,
  Download-Logs in `reports/fetch/`.
