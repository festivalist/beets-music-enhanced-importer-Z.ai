---
name: musik-dev-prinzipien
description: Kernprinzipien für alle Entwicklungsarbeit am musik-Projekt (MusicBrainz-automated). Nutze dieses Skill bei JEDEM Feature, Fix, Refactoring oder Konfig-Change in diesem Repo — auch wenn der Nutzer nur "mach das mal" sagt. Kern: konsistente Musik-Datenbank zuerst, Anwender automatisiert entlasten, Regeln global statt für Einzelfälle.
---

# musik — Entwicklungsprinzipien

## Nordstern — Zielcheck vor jeder Aktion

Projektziel (in AGENTS.md verankert, beschlossen 2026-10-08): effizient und mit
möglichst wenig Nutzerinteraktion qualitativ hochwertige Musik beschaffen
(bevorzugt lossless, sonst bestverfügbare lossy Qualität), konsistent nach
config.yaml organisieren und über Plexamp bereitstellen.

Vor jeder geplanten Änderung prüfen: **Dient sie direkt diesem Ziel — oder
behebt sie nur ein Symptom?** Symptom-Fixes nur, wenn sie den Weg freimachen;
strukturelle Lösungen vorziehen und als datierten Scope-Change in SCOPE.md
dokumentieren. Beschaffungs-Engines schreiben nur ins Staging; beets bleibt die
einzige schreibende Instanz der Bibliothek.

## Rangfolge: konsistente Datenbank zuerst

Ziel des Projekts ist eine korrekt getaggte, konsistent abgelegte Bibliothek
(Pfade, Naming, Metadaten exakt nach `config.yaml`). Jede Entscheidung wird an
zwei Fragen gemessen:

1. Trägt das zur Konsistenz der Datenbank bei?
2. Wie viel Arbeit nimmt es dem Anwender?

**Anwender entlasten heißt: Automatik vor Interaktion.** Interaktives Review
(`import-here.bat`, beets-Review) ist die Ausnahme, nicht der Standard. Kleine
Abweichungen (Jahr ±1, Remaster/Release-Varianten, falsche Quelle-Tags) werden
automatisch akzeptiert statt in die Review-Queue zu stellen; widersprechen
ALLE Top-Kandidaten der erwarteten Identität, wird as-is importiert. Neue
Features müssen diesen Kurs halten — niemals zusätzliche manuelle
Entscheidungspunkte einführen, ohne dass der Nutzer es ausdrücklich verlangt.

## Global statt Einzelfall

Das System ist ein Katalogisierungswerkzeug für ~1000+ Alben, kein Editor für
einzelne Fälle. Explizit NICHT auf Einzelfallentscheidungen optimieren:

- Keine Heuristik, die nur den gerade betrachteten Album-/Track-Fall trifft
  (hardgecodete Titel, MB-IDs, Pfade, Sonderregeln für einen Artist).
- Eine Beobachtung aus einem Einzelfall wird verallgemeinert: als allgemeine
  Regel (z. B. Distanz-Penalty, Format-Erkennung, Ordner-Signale wie .nfo
  auswerten), die für die ganze Bibliothek gilt — oder sie wird verworfen.
- Vor dem Umsetzen prüfen: "Was macht dieser Fix bei 1000 anderen Alben?"
  Ist er dort wirkungslos, falsch oder unangebracht → andere Regel suchen.
- Lässt sich ein Sonderfall nicht verallgemeinern, gehört er als dokumentierte
  Fallklasse in README.md ("How decisions are made" / "Mixed batches"), nicht
  als Code-Zweig für einen konkreten Release.

## Scope

Der gültige Scope steht in SCOPE.md. Erweiterungen werden — wie 2026-09-17,
2026-09-19, 2026-09-21 — als datierter Scope-Change dort eingetragen, nicht
still in Code und Doku eingeschmuggelt.
