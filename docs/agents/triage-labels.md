# Triage Labels

Die Skills sprechen in fünf kanonischen Triage-Rollen. Diese Datei bildet
die Rollen auf die tatsächlichen Label-Strings dieses Trackers ab.

| Label in mattpocock/skills | Label in unserem Tracker | Bedeutung                                    |
| -------------------------- | ------------------------ | -------------------------------------------- |
| `needs-triage`             | `needs-triage`           | Muss erst bewertet werden                    |
| `needs-info`               | `needs-info`             | Wartet auf mehr Informationen (vom Nutzer)   |
| `ready-for-agent`          | `ready-for-agent`        | Vollständig spezifiziert, bereit für AFK-Agent |
| `ready-for-human`          | `ready-for-human`        | Braucht menschliche Umsetzung                |
| `wontfix`                  | `wontfix`                | Wird nicht umgesetzt                        |

Wenn ein Skill eine Rolle nennt (z. B. „apply the AFK-ready triage label"),
den Label-String aus dieser Tabelle verwenden.

Da der Tracker `ToDo.md` ist (kein GitHub Issues), werden keine Labels im
Remote angelegt — die Marker landen als `[label]` in der Story-Zeile
(siehe [`issue-tracker.md`](issue-tracker.md)).
