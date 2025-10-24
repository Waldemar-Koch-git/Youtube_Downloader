# Install
## Externe Bibliotheken
* pytubefix
* imageio-ffmpeg
### Installation via pip
```
pip install imageio-ffmpeg pytubefix
```


# Beschreibung
## YouTube Downloader GUI - Modernisierte Version (v3.0.1)

Eine benutzerfreundliche grafische Oberfläche zum Herunterladen von Audio und Video
aus YouTube‑Links mit modernem Design und verbessertem Workflow.

Dieses Skript bietet eine einfache grafische Oberfläche zum Herunterladen von Audio und Video
aus YouTube‑Links.
* **Audio** kann als MP3 heruntergeladen und konvertiert werden.
* **Video** wird als MP4 (höchste verfügbare Auflösung oder maximale Qualität) gespeichert.
* Es gibt ein Analyse‑Modul, das alle verfügbaren Audio‑/Videostreams anzeigt und dem Nutzer die
  Auswahl eines konkreten Streams ermöglicht.

Die Anwendung nutzt:
- `pytubefix` für die Abfrage der Stream‑Informationen,
- `ffmpeg` (von `imageio-ffmpeg`) zur Konvertierung von Audio und Video,
- `threading.Thread`, damit die GUI während des Downloads nicht einfriert.

Alle Optionen können über das Tkinter‑GUI gesteuert werden; Pfade, Format‑Auswahl und OAuth‑Token
werden als Einstellungen angeboten.
