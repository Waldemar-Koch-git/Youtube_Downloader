# Install
## Externe Bibliotheken
* yt-dlp
* imageio-ffmpeg
### Installation via pip
```
pip install imageio-ffmpeg yt-dlp
```

# GUI
![Gui Front Image](./images_/GUI.jpg)

# Beschreibung
## YouTube Downloader GUI - Modernisierte Version (v4.0.0)

Eine benutzerfreundliche grafische Oberfläche zum Herunterladen von Audio und Video
aus YouTube-Links mit modernem Design und verbessertem Workflow.

Dieses Skript bietet eine einfache grafische Oberfläche zum Herunterladen von Audio und Video
aus YouTube-Links.
* **Audio** kann als MP3 heruntergeladen und konvertiert werden.
* **Video** wird als MP4 (höchste verfügbare Auflösung oder maximale Qualität) gespeichert.
* Es gibt ein Analyse-Modul, das alle verfügbaren Audio-/Videostreams anzeigt und dem Nutzer die
  Auswahl eines konkreten Streams ermöglicht.

Die Anwendung nutzt:
- `yt-dlp` für die Abfrage der Stream-Informationen und den Download,
- `ffmpeg` (von `imageio-ffmpeg`) zur Konvertierung von Audio und Video,
- `threading.Thread`, damit die GUI während des Downloads nicht einfriert.

Alle Optionen können über das Tkinter-GUI gesteuert werden; Pfade und Format-Auswahl
werden als Einstellungen angeboten.

# _Beta_
![Gui Front Image](./images_/_gui_beta.jpg)

Viele neue features wie 
* Multi-URL
* playlists 
* Cover (*Thumbnails*)
* Automatische Einstellung Abspeicherung
* ...

## Install

### Externe Bibliotheken
* yt-dlp[default] → YT-Bib
* imageio-ffmpeg → Konverter
* mutagen → (Tags platzsparend beschreiben inkl. verkleinerter Cover-größe)

### Für Nutzung der Cookies aus den Browsern:
* node → https://nodejs.org
Man muss in ein beliebigen Browser *(z.B.: Firefox)* eingeloggt sein und dann in dieser GUI unter `Speicherorte & Optionen` ganz unten den jeweiligen Browser auswählen für den Import.

#### Installation via pip
```
pip install mutagen imageio-ffmpeg yt-dlp[default]
```

