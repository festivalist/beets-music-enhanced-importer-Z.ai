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
   └─ spotDL (Spotify-Links) / SomeDL (YouTube-Links, Suchtext)
        └─ Download als .m4a (mit Premium-Cookies: 256 kbps) → _incoming/
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
```

Dann der Bot-Live-Test vom Handy: Album-Link an @<dein-bot-name>
schicken und die Meldungen verfolgen (`⬇️ → 📦 → importiert → 🎧 Plex-Scan`).
Nach kurzer Zeit muss das Album in **Plexamp** auftauchen.

## Phase 7 — Betrieb & Wartung

| Aufgabe | Befehl |
|---|---|
| Bot-Status | `systemctl status musik-bot` |
| Bot-Log live | `journalctl -u musik-bot -f` |
| Bot neu starten | `sudo systemctl restart musik-bot` |
| Toolchain aktualisieren (bei YouTube-Ausfällen) | `cd ~/musik && git pull && .venv/bin/python -m pip install -U spotdl somedl && sudo systemctl restart musik-bot` |
| Komplett-Reinstall nach Repo-Update | `bash install.sh --library /mnt/music` (idempotent, hält config.yaml) |
| Cookies neu (nach Logout/Passwortwechsel) | Phase 3 wiederholen (nur Schritt 4-5 + scp) |
| Review-Einheiten auf eigene Tags importieren | Handy: Bot-`/asis` (Knöpfe antippen) · Terminal: `musik.py asis --pending` |
| Plex-Scan manuell anstoßen | `.venv/bin/python musik.py plex` (meldet die konkrete Ursache, falls es hakt) |
| apt update: Plex-Key-Fehler („not bound", SHA1) | Workaround-Block in Phase 5.1 erneut ausführen (solange Plex den Key nicht neu signiert hat) |
| Backup (DB + Config + Tokens) | `.venv/bin/python musik.py snapshot` |
| Monats-Check | `.venv/bin/python musik.py doctor --quick` |
| Download-Logs | `~/musik/reports/fetch/<job>.log` / `.errors` |

**Playlist-Link (Best Of) landet im Review — das ist normal:** Eine Playlist
ist kein Album für MusicBrainz. Die Auflösung braucht keine ID-Eingabe:

- **Vom Handy:** dem Bot **`/asis`** schicken → wartende Einheiten erscheinen
  als Knöpfe („Lebanon Hanover · 30 Tracks (review)") → **antippen** → Import
  läuft, Ergebnis + Plex-Scan kommen als Nachricht zurück.
- **Am Terminal:** `.venv/bin/python musik.py asis --pending` (alle
  tag-vollständigen Einheiten auf eigene Tags; `--dry-run` zeigt vorher nur
  die Liste) oder interaktiv `musik.py review` → `W`.

Die Tracks wandern dabei Track-für-Track in ihre echten Spotify-Alben.
Bei fehlendem Genre/Cover danach: `.venv/bin/python musik.py doctor --fix`.

**Fehlersuche:** einzelne Track-Fehler → erstes Mittel ist immer ein Re-Fetch
des Albums (Gap-Fill ergänzt nur fehlende Tracks); Massen-Ausfall → Tools
aktualisieren (Zeile oben); Bot antwortet nicht → `journalctl -u musik-bot -n 50`.

## Phase 8 — Abnahme (der komplette Durchlauf)

- [ ] Handy im **Mobilfunk** (WLAN aus): Link an den Bot geschickt
- [ ] Bot meldet Download → Import → „in Plexamp verfügbar"
- [ ] Album erscheint in Plexamp, Cover + Genre sichtbar, ReplayGain aktiv
- [ ] Zweiter Link: Album existiert schon → Meldung „bereits vorhanden /
      fehlende Tracks ergänzt"
- [ ] `ffprobe` zeigt 256 kbps (Cookies wirksam)
- [ ] Windows-Test-Bot ist aus; einziges aktives System ist der Pi

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
