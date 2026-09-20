# Deploying musik on a fresh Raspberry Pi

A from-scratch walkthrough for a headless Pi: flash the OS, run one
installer script, do your first import. The installer (`install.sh`) is
CI-tested on **ubuntu arm64** — the exact architecture of a Pi — so the
steps below track what is actually tested.

## What you need

- A Raspberry Pi **3B+ / 4 / 5** (64-bit recommended; a Pi Zero works but
  fingerprinting is slow).
- **Raspberry Pi OS Bookworm, 64-bit Lite** is enough (headless, no GUI).
- Terminal access via SSH (or a directly attached screen/keyboard).
- Music storage: a USB disk or a network share, plus the folder where the
  managed library should live (can be the same disk).

## 1. Flash the OS

Use the official **Raspberry Pi Imager**:

1. Choose *Raspberry Pi OS (64-bit)* — Lite is fine.
2. In the imager's settings (gear icon): set a hostname (e.g. `musikpi`),
   enable **SSH**, create your user and password, optionally WLAN.
3. Flash, insert the SD card, boot the Pi.

## 2. First login

```bash
ssh <user>@musikpi.local        # or the IP address
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git
```

## 3. Get musik

```bash
git clone https://github.com/festivalist/beets-music-enhanced-importer-Z.ai.git
cd beets-music-enhanced-importer-Z.ai
```

## 4. Run the installer

```bash
bash install.sh --library /home/pi/Music
```

Options: `--library <path>` pre-answers the wizard's library-root prompt;
`--no-systemd` skips the Telegram bot service.

What it does, in order:

1. apt packages: `python3-venv`, `ffmpeg`, `libchromaprint-tools` (the
   `fpcalc` fingerprinter), `flac`
2. Python ≥ 3.10 check, `.venv` creation
3. `pip install -r requirements.txt` (beets, spotDL, SomeDL, bot)
4. Deno runtime download (yt-dlp needs it for some YouTube videos)
5. **Setup wizard** (skipped if `config.yaml` already exists)
6. Self test: `musik.py fetch --self-test` (spotdl / somedl / ffmpeg / fpcalc)
7. systemd unit `musik-bot.service` (enabled on boot) for the Telegram bot

## 5. The setup wizard

The wizard asks (all answers land in the local, git-ignored `config.yaml`):

| Prompt | Meaning |
|---|---|
| Music library root | Where tagged music lives, e.g. `/home/pi/Music` or `/mnt/music` |
| Beets database file | Enter for `<root>/beets-library.db` |
| Discogs token | Optional but recommended ([create one](https://www.discogs.com/settings/developers), scope *database*) |
| Telegram bot token | Optional — enables the link→download bot (step 9) |

Re-run `python musik.py setup` any time to regenerate the config.

## 6. Verify

```bash
.venv/bin/python musik.py doctor           # tool + config health check
.venv/bin/python musik.py fetch --self-test
```

## 7. External storage (optional)

**USB disk:** find it with `lsblk`, then mount it and add an `fstab` line so
it survives reboots:

```bash
sudo mkdir -p /mnt/music
# ext4 disk:           /dev/sda1  /mnt/music  ext4  defaults,nofail  0 2
# NTFS disk:           /dev/sda1  /mnt/music  ntfs-3g defaults,nofail,uid=1000,gid=1000  0 0
sudo mount -a
```

**NAS (SMB) share:**

```bash
sudo apt install -y cifs-utils
sudo mkdir -p /mnt/music
# /etc/fstab:  //192.168.1.50/music  /mnt/music  cifs  credentials=/root/.smbcred,uid=1000,nofail  0 0
sudo mount -a
```

Important: imports **move** files, so the *source* folder must also be
writable. A read-only share works only as the library target; import from a
local copy instead.

## 8. Your first import (headless, over SSH)

Tip: add an alias once — `alias musik='/home/pi/beets-music-enhanced-importer-Z.ai/.venv/bin/python /home/pi/beets-music-enhanced-importer-Z.ai/musik.py'`
(or `source .venv/bin/activate` before working).

```bash
musik snapshot                                  # optional: backup the library DB first
musik scan --root /mnt/incoming/some-album      # classify (read-only)
musik import --dry-run --unit /mnt/incoming/some-album
musik import --unit /mnt/incoming/some-album    # the real run (resumable; Ctrl+C safe)
musik review --unit /mnt/incoming/some-album    # decide the doubtful ones
musik cleanup --root /mnt/incoming/some-album   # archive leftovers, remove emptied folders
musik summary                                   # totals of this action
musik report --verify                           # library sanity check
```

Everything is interactive-friendly over SSH — `review` walks the queue with
the usual choices (accept candidate / override / by MBID / as-is / skip /
ignore / abort).

## 9. Telegram bot (remote control from your phone)

If you entered a bot token in the wizard, the service is already enabled:

```bash
systemctl start musik-bot        # first start (enabled at boot already)
journalctl -u musik-bot -f       # watch the log
```

Open your bot in the Telegram app and send any message. It replies with
your chat id; add that id to `config.yaml`:

```yaml
musik:
  bot_allowlist: [<your-chat-id>]
```

then `sudo systemctl restart musik-bot`. From now on, sending a
Spotify/YouTube link to the bot downloads, tags and files it into the
library automatically — from anywhere.

## 10. Updating

```bash
cd beets-music-enhanced-importer-Z.ai
git pull
.venv/bin/pip install -r requirements.txt
sudo systemctl restart musik-bot
```

## Notes & limits

- The Windows drag & drop files (`*.bat`) don't apply here — the CLI and
  the Telegram bot are the interfaces.
- Performance: acoustic fingerprinting is CPU-heavy. A Pi 4/5 is
  comfortable (~25 s/album plus downloads); a Pi Zero/1 will feel slow.
- Back up `config.yaml`, `discogs_token.json`, `telegram_token.json` —
  they are machine-local and intentionally not in git. `musik snapshot`
  covers the beets database.
- Everything decided is journaled in `state/state.json`; reports land in
  `reports/`.
