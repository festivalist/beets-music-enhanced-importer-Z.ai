---
name: musik-doku-hygiene
description: Doku- und Aufräum-Regeln für das musik-Projekt (MusicBrainz-automated). Nutze dieses Skill beim Abschließen von Arbeiten und Commits, beim Ändern von README/PI-SETUP/SCOPE/ToDo, beim Anlegen neuer Dateien und beim Aufräumen des Repos. Kern: Fortschritt, offene Aufgaben und Installation (Unix UND Windows) stets am selben Ort dokumentieren; obsolete Test- und Hilfsdateien im selben Change löschen.
---

# musik — Doku & Repo-Hygiene

## Feste Doku-Orte — keine neuen Parallel-Dokumente

| Thema | Datei |
|---|---|
| Projekt, Nutzung, Windows-Install, Runbook, Entscheidungslogik | README.md |
| Pi/Unix-Deployment (Phasen 0–8), Betrieb & Wartung | PI-SETUP.md |
| Gültiger Scope + datierte Scope-Changes | SCOPE.md |
| Offene Aufgaben, offene Testfälle, bekannte Lücken | ToDo.md |

- Fortschritt und offene Aufgaben werden NUR in diesen Dateien gepflegt —
  keine `NOTES-*.md`, keine feature-eigenen Doku-Dateien, keine Duplikate
  in Unterordnern.
- Installation wird für BEIDE Plattformen gepflegt: Windows in README.md
  (`install.ps1` / `install.bat`), Unix/Pi in PI-SETUP.md (`install.sh`).
  Eine Plattform-Änderung ohne die andere ist unvollständig.
- PI-SETUP.md wird bei jeder Änderung an Installer, config, Bot, Cookies
  oder Plex im SELBEN Commit mitgepflegt (etablierte Praxis).
- Commit-Stil des Repos beachten: deutsche, prägnante Messages mit
  Themenpräfix (`docs:`, `install.sh:`, `plex:`, `fetch:` …).

## Repo-Hygiene

- Obsolete Artefakte im selben Change löschen, der sie überflüssig macht:
  weggefallene Testdateien und Testskripte, ausgediente Hilfsskripte,
  Report-/Log-Auswürfe, alternative Versionen derselben Datei. Vor dem
  Löschen prüfen, ob README/PI-SETUP noch darauf verweisen — Verweis dann
  mitentfernen.
- Vor jedem Commit kurz scannen: Was ist durch diesen Change obsolet
  geworden? `git status` auf Dateien prüfen, die nur Test-Zwischenstand sind.
- Testmaterial und Debug-Ausgaben gehören nicht dauerhaft ins Repo; Ergebnisse
  als Text in Commit-Body oder Doku. Screenshots nur, wenn sie einen
  dokumentierten UI-Zustand zeigen (wie `manual_tests/*.PNG`) — und weg, sobald
  der dokumentierte Zustand entfällt.
- Runtime-Artefakte (`state/`, `reports/`, `__pycache__`, Tokens) stehen bzw.
  gehören in `.gitignore`, nicht ins Repo.
