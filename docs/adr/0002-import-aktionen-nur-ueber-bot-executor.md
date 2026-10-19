# Import-Aktionen laufen ausschließlich über den Bot-Executor

Der Import-Monitor löst Aktionen (Review-Entscheidungen, Retry, asis,
manueller Ingest-Trigger) nicht in einem eigenen Web-Container aus,
sondern reicht sie an einen LAN-HTTP-Endpoint des bestehenden musik-Bots
weiter, der sie über seine Job-Queue unter dem ingest.lock ausführt —
derselbe Single-Executor, der schon Telegram bedient. Grund: Der Bot hat
Queue, flock-Koordination gegen den 15-min-Timer und Live-Fortschritt
bereits fertig; ein zweiter Ausführungspfad würde Bibliotheks-Mounts in
den Web-Container ziehen und Concurrency gegen state.json/beets-DB neu
erfinden. Browser und Telegram sind Trigger-Flächen — geschrieben wird
die Bibliothek weiterhin nur durch musik.
