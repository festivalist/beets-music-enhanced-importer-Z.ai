# Domain Docs

Wie die Engineering-Skills die Domain-Dokumentation dieses Repos beim
Erkunden des Codes konsumieren.

## Vor dem Explorieren lesen

- **`GLOSSARY.md`** im Repo-Root (Single-Context-Repo; kein
  `GLOSSARY-MAP.md` konfiguriert).
- **`docs/adr/`**: ADRs lesen, die den Arbeitsbereich betreffen.
- Zusätzlich die bereits existierenden Entscheidungs-Dokumente dieses
  Repos: **`SCOPE.md`** (datierte Scope-Changes) und
  **`BEETS-DEVIATION.md`** (bewusste Abweichungen vom beets-Verhalten).
  Sie nehmen die Rolle früher Entscheidungsrecords wahr; neue, allgemeine
  Design-Entscheidungen gehören in `docs/adr/` (von `/domain-modeling`
  lazy angelegt), projektweite Geltungsbereichs-Änderungen weiter in
  `SCOPE.md`.

Falls `GLOSSARY.md` oder `docs/adr/` noch fehlen: **still
weiterarbeiten**. Ihr Fehlen nicht anmerken und nicht vorab vorschlagen.
`/domain-modeling` (erreichbar über `/grill-with-docs` und
`/improve-codebase-architecture`) legt sie an, sobald Begriffe oder
Entscheidungen tatsächlich geklärt werden.

## Dateistruktur

```
/
├── GLOSSARY.md
├── docs/
│   ├── adr/
│   │   ├── 0001-….md
│   │   └── 0002-….md
│   └── agents/          ← diese Konfigurationsdateien
├── SCOPE.md
├── BEETS-DEVIATION.md
├── ToDo.md
├── musik/  musicgrabber/  install.d/  …
```

## Vokabular des Glossars verwenden

Wenn eine Ausgabe ein Domänen-Konzept benennt (Story-Titel,
Refactor-Vorschlag, Hypothese, Testname), den in `GLOSSARY.md` definierten
Begriff verwenden. Nicht auf Synonyme ausweichen, die das Glossar explizit
vermeidet.

Fehlt das benötigte Konzept im Glossar, ist das ein Signal: Entweder es
wird Sprache erfunden, die das Projekt nicht nutzt (nochmal überdenken),
oder es gibt eine echte Lücke (für `/domain-modeling` notieren).

## ADR-Konflikte markieren

Widerspricht die eigene Ausgabe einem bestehenden ADR, das explizit
benennen statt still übersteuern:

> _Widerspricht ADR-0007 (…), aber wert wiederzueröffnen, weil …_
