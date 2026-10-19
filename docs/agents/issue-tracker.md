# Issue tracker: ToDo.md

Issues und Specs für dieses Repo leben in **`ToDo.md`** im Repo-Root. Es gibt
kein GitHub-Issues-Tracking (das Remote `festivalist/beets-music-enhanced-importer-Z.ai`
dient nur Code/CI) und keine `.scratch/`-Konvention. Die Doktrin dahinter
steht in `.agents/skills/` (`musik-story-workflow`, `musik-doku-hygiene`).

## Konventionen von ToDo.md

- Struktur: `## EPIC N — Titel`, darunter eine Story pro Eintrag als
  Checkbox `- [ ] N.M Titel — Details/Anforderungen`.
- Eine Story = ein Commit-Kontext: Implementierung, Testmatrix
  (`musik-testdaten`) und Doku landen im selben Commit.
- Erledigte Stories bleiben in der Datei: Checkbox auf `[x]`, mit
  `**AUSGEFÜHRT <Datum>**: …` bzw. `**erledigt <Datum>**: …` datiert.
- Verworfene Stories werden nicht gelöscht, sondern mit Begründung
  abgehakt (z. B. `**ENTFALLEN (Redundanzcheck)**`).
- Echte Scope-Changes werden zusätzlich datiert in `SCOPE.md` vermerkt.

## Wenn ein Skill „publish to the issue tracker" sagt

- `/to-spec`: den Spec als ausgeformte Story (oder Erweiterung einer
  bestehenden Story) in den passenden EPIC-Abschnitt von `ToDo.md`
  schreiben; bei echtem Scope-Change zusätzlich datierter Eintrag in
  `SCOPE.md`.
- `/to-tickets`: eine Story pro Ticket als Checkbox-Eintrag unter dem
  passenden EPIC anlegen; Blocking-Edges als `Blockiert von N.M`-Vermerk
  am Anfang des Eintrags.
- Nicht in neue Dateien auslagern: `musik-doku-hygiene` verbietet das —
  Fortschritt und offene Punkte leben ausschließlich in README.md /
  PI-SETUP.md / SCOPE.md / ToDo.md.

## Wenn ein Skill „fetch the relevant ticket" sagt

Die Story über ihre Nummer (`N.M`) in `ToDo.md` suchen und den kompletten
Eintrag lesen (Zeile plus Folgezeilen bis zur nächsten Story/Überschrift).

## Wayfinding (`/wayfinder`)

Map und Tickets werden als eigener EPIC-Abschnitt in `ToDo.md` geführt:
die Map (Notes / Decisions-so-far / Fog) als Einleitungstext des
Abschnitts, die Tickets als Checkbox-Stories mit `Blockiert von`-Vermerken.
Es werden keine separaten Dateien angelegt.

## Triage-Rollen in ToDo.md

`ToDo.md` hat keine nativen Labels. Triage-Zustände werden als
`[label]`-Marker am Anfang der Story-Zeile geführt, z. B.
`- [ ] [ready-for-agent] 2.2 …`. Die Rollen-Strings stehen in
[`triage-labels.md`](triage-labels.md).
