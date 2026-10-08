---
name: musik-story-workflow
description: Arbeits-Workflow des musik-Projekts (MusicBrainz-automated) — Anforderungen immer zuerst in Stories übersetzen und gemäß festem Ablauf abarbeiten (Zielcheck, Redundanzcheck, Implementierung, Testmatrix, Doku same-commit). Nutze dieses Skill, sobald eine neue Anforderung, ein Feature-Wunsch, Bugreport, Fix-Request oder Audit-Ergebnis reinkommt — bevor irgendetwas implementiert wird, und auch bei der Planung größerer Vorhaben.
---

# musik — Story-Workflow

## Anforderungen werden zu Stories

Jede eingehende Anforderung (Feature, Fix, Refactoring, Config-Change,
Audit-Befund) wird **zuerst in Stories übersetzt**, nicht sofort
implementiert:

- Eine Story ist klein genug für einen zusammenhängenden Commit-Kontext,
  testbar (Akzeptanzkriterium formuliert) und priorisiert.
- Das Backlog lebt ausschließlich in ToDo.md (EPIC-/Story-Struktur;
  Deploy-Gates markieren). Nicht im Chat-Verlauf verlieren.
- Audits und Reviews (z. B. Code-Revisionen) erwirtschaften ihre Befunde
  als Stories im Backlog — keine Ad-hoc-Fixserien abseits des Plans.

## Fester Ablauf pro Story

1. **Zielcheck (Nordstern):** Dient die Story direkt dem Projektziel —
   Beschaffung, Organisation oder Bereitstellung mit weniger Interaktion
   oder besserer Qualität — oder behebt sie nur ein Symptom?
2. **Redundanzcheck:** Existiert die Lösung schon? Code, Doku, git-History
   und bestehende Regeln durchsuchen und wiederverwenden; nur bauen, was
   fehlt. **Redundanz ist zu verhindern** — außer sie dient nachweislich
   dem Projektziel; dann bewusst akzeptieren und dokumentieren.
3. **Implementieren** nach `musik-dev-prinzipien`: global gültige Regeln
   statt Einzelfall-Tuning; „Was macht der Fix bei 1000 anderen Alben?"
4. **Testen** nach `musik-testdaten`: Matrix oder begründete Teilmenge;
   fehlende Testdaten in ToDo.md vermerken und beim Nutzer anfragen statt
   degeneriert zu testen.
5. **Doku same-commit** nach `musik-doku-hygiene`: README/PI-SETUP/SCOPE/
   ToDo aktuell halten, obsolete Dateien im selben Change löschen.
6. **Abschluss:** ToDo-Story abhaken, Commit (deutsch, Themenpräfix),
   Push — der Pi zieht per `git pull`.

## Reihenfolge

Stories werden nach Deploy-Gates und Risiko sortiert: funktionalkritische
Fixes (falsches Verhalten, Datenverlust-Risiko) vor einem Deploy,
Struktur-/Dedup-Arbeit danach, Kosmetik zuletzt. Eine Story gilt erst als
fertig, wenn Schritt 4 und 5 durchlaufen sind.
