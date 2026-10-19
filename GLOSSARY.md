# musik — Domänen-Glossar

Automatisierte Beschaffung, Organisation und Bereitstellung von Musik:
Beschaffungs-Engines laden in einen Staging-Bereich, der Ingest bewertet
und importiert, beets-DB ist die alleinige Wahrheit der Bibliothek.
Nordstern: qualitativ hochwertige Musik mit möglichst wenig
Nutzerinteraktion.

## Sprache

### Wahrheit & Bestand

**Bibliothek**:
Die echte, konsolidierte Musiksammlung, organisiert nach config.yaml.
_Avoid_: Medienordner, Plex-Ordner

**beets-DB**:
Die alleinige Wahrheit über Inhalt und Organisation der Bibliothek.
_Avoid_: Datenbank (zu allgemein)

### Beschaffung

**Beschaffungs-Engine**:
Ein externer Dienst, der Musik bis in den Staging-Bereich beschafft
(aktuell MusicGrabber, spotDL/SomeDL). Schreibt niemals die Bibliothek.
_Avoid_: Downloader

**Staging**:
Der Vorbereich (`_incoming`), in den Beschaffungs-Engines ausschließlich
schreiben; der einzige Weg hinein in die Bibliothek führt über den Ingest.
_Avoid_: Download-Ordner, Incoming (allein)

**Fetch**:
Ein durch einen Bot-Job ausgelöster Beschaffungslauf; erzeugt eine
Fetch-Unit-Menge im Staging.
_Avoid_: Download (als Substantiv für den Lauf)

### Ingest

**Ingest**:
Der Lauf, der Staging-Units bewertet, importiert (auto oder asis) oder in
die Review-Queue stellt; timer-getrieben und einzige Instanz, die die
Bibliothek schreibt.

**Timer-Lauf**:
Ein durch den periodischen Timer ausgelöster Ingest (im Unterschied zu
Bot- und manuell ausgelösten Läufen).

**Unit**:
Eine zusammenhängende Menge heruntergeladener Audiodateien, die der
Ingest als eine Einheit bewertet und importiert (typisch ein Album-Rip
als Ordner).
_Avoid_: Album (der musikalische Begriff), Ordner (der technische Behälter)

**Unit-Status**:
Einer von acht Zuständen einer Unit: `pending`, `auto`, `review`,
`unmatched`, `network`, `duplicate`, `ignored`, `error`.

**asis**:
Import einer Unit auf ihre eigenen vorhandenen Tags, ohne externen
Kandidatenvergleich.

**Auto-Annahme**:
Die Policy, Unit-Importe ohne Nutzerinteraktion zu akzeptieren, solange
kein Widerspruchssignal vorliegt.

**Contradiction-Signal**:
Ein Hinweis, dass die Top-Kandidaten der Identität der Unit widersprechen
(z. B. falscher Künstler); widersprüchliche Units werden policy-gemäß
as-is übernommen statt falsch auto-importiert.

**Review-Queue**:
Die Menge der Units, deren Import eine menschliche Entscheidung abwartet
(Unit-Status `review`).
_Avoid_: Review-Liste

### Überwachung

**Import-Monitor**:
Die Weboberfläche (Tab in der MusicGrabber-UI), die Laufstatus,
Unit-Status, Review-Queue und Stau zeigt und Import-Aktionen auslöst.
_Avoid_: Statusseite, MG-Status
