# Import-Monitor als Overlay-Fork im gepinnten MusicGrabber-Image

Der Import-Monitor (Weboberfläche für Import-Status, EPIC 9) lebt als Tab
in der MusicGrabber-UI. Statt eines Voll-Forks oder einer eigenen
Neben-Anwendung (Sidecar) überlagern Bind-Mounts aus diesem Repo nur die
statischen Dateien des gepinnten Upstream-Images (4.3.1; Upstream-Lizenz
The Unlicense). Das Upstream-Backend bleibt unangetastet — alle Aktionen
laufen über den Bot-Executor (ADR-0002) —, ein eigener multi-arch-
Image-Build (Chromium-Stack) entfällt, und Updates sind bewusste
Tag-Bumps mit Overlay-Verträglichkeitscheck statt stiller latest-Züge.

## Considered Options

- **Voll-Fork** (eigenes Repo, eigene Builds): maximale Freiheit, aber bei
  ~13 Upstream-Releases in 9 Wochen dauerhafter Merge- und CI-Aufwand.
- **Sidecar** (eigene Mini-UI neben MG): null Kopplung, aber eine zweite
  Oberfläche statt einer; vom Nutzer 2026-10-19 zugunsten „ein Ort“
  abgelehnt.

Ein Upgrade zum Voll-Fork bleibt jederzeit möglich, falls der Overlay an
Grenzen stößt.
