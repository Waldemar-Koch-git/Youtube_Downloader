# -*- coding: utf-8 -*-

__version__ = '4.0.0'

"""
YouTube Downloader GUI - Modernisierte Version

Eine benutzerfreundliche grafische Oberfläche zum Herunterladen von Audio und Video
aus YouTube-Links mit modernem Design und verbessertem Workflow.

* **Audio** kann als MP3 heruntergeladen und konvertiert werden.
* **Video** wird als MP4 (höchste verfügbare Auflösung oder maximale Qualität) gespeichert.
* Es gibt ein Analyse-Modul, das alle verfügbaren Audio-/Videostreams anzeigt und dem Nutzer die
  Auswahl eines konkreten Streams ermöglicht.

Die Anwendung nutzt:
- `yt-dlp` für die Abfrage der Stream-Informationen und den Download,
- `ffmpeg` (von `imageio-ffmpeg`) zur Konvertierung von Audio und Video,
- `threading.Thread`, damit die GUI während des Downloads nicht einfriert.

Author: Waldemar Koch
Updated: 2025 Oktober 17
Modernisiert: Version 3.0.1
Bugfix v3.0.2: pytubefix auf >= 10.x aktualisiert; use_po_token Parameter korrekt übergeben
Bugfix v3.0.3: use_po_token (deprecated) ersetzt durch WEB-Client; OAuth standardmäßig aktiv
Refactor v4.0.0: Backend von pytubefix auf yt-dlp umgestellt (stabiler, aktiv gepflegt)
License: MIT
"""
# pip install imageio-ffmpeg yt-dlp

import imageio_ffmpeg as ffmpeg
import yt_dlp
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from threading import Thread
from os import path, makedirs, system
from subprocess import Popen

system(f"title YouTube Downloader - Version {__version__}")


class YouTubeDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"YouTube Downloader v{__version__}")
        self.ui_WEITE = 690
        self.ui_HOEHE = 920
        self.root.geometry(f"{self.ui_WEITE}x{self.ui_HOEHE}")

        try:
            self.root.iconbitmap("yt_symbol_small.ico")
        except:
            pass

        # --- Variablen ----------------------------------------------------
        self.url_var = StringVar()
        self.audio_path_var = StringVar()
        self.video_path_var = StringVar()
        self.audio_to_mp3_var = BooleanVar(value=True)
        self.video_to_mp4_var = BooleanVar(value=True)

        self.clicked_stream_video = StringVar()
        self.clicked_stream_audio = StringVar()

        # Interne Stream-Listen: liste von dicts mit label, format_id, ext
        self._video_formats = []
        self._audio_formats = []

        # Default paths
        parent_dir = path.dirname(path.abspath(__file__))
        self.audio_path_var.set(path.join(parent_dir, "Downloads", "audio"))
        self.video_path_var.set(path.join(parent_dir, "Downloads", "video"))

        # --- UI -----------------------------------------------------------
        self.setup_styles()
        self.create_widgets()

    # --------------------------------------------------------------------
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        accent_color = "#FF0000"
        button_color = "#2196F3"
        success_color = "#4CAF50"

        style.configure('Primary.TButton',
                        padding=10, font=('Segoe UI', 10, 'bold'), background=button_color)
        style.configure('Action.TButton',
                        padding=15, font=('Segoe UI', 12, 'bold'), background=success_color)
        style.configure('Secondary.TButton',
                        padding=8, font=('Segoe UI', 9))
        style.configure('Title.TLabel',
                        font=('Segoe UI', 16, 'bold'), foreground=accent_color)
        style.configure('Subtitle.TLabel',
                        font=('Segoe UI', 11, 'bold'))
        style.configure('Info.TLabel',
                        font=('Segoe UI', 9), foreground='#666666')

    # --------------------------------------------------------------------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky='nsew')
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Titel
        ttk.Label(main_frame, text="🎬 YouTube Downloader",
                  style='Title.TLabel').grid(row=0, column=0, pady=(0, 20), sticky='n')

        # --- URL-Eingabe ---
        url_frame = ttk.LabelFrame(main_frame, text="YouTube URL", padding="15")
        url_frame.grid(row=1, column=0, sticky='ew', pady=(0, 15))
        url_frame.columnconfigure(0, weight=1)

        ttk.Entry(url_frame, textvariable=self.url_var,
                  font=('Segoe UI', 10)).grid(row=0, column=0, sticky='ew')

        btn_sub = ttk.Frame(url_frame)
        btn_sub.grid(row=0, column=1, padx=(5, 0))
        ttk.Button(btn_sub, text="Link einfügen",
                   command=self.paste_link).pack(side='left', padx=2)
        ttk.Button(btn_sub, text="Link Analysieren",
                   command=self.analyze_url,
                   style='Primary.TButton').pack(side='left', padx=2)
        ttk.Button(btn_sub, text="Feld Löschen",
                   command=self.clear_link).pack(side='left', padx=2)

        # Video-Titel
        self.title_label = ttk.Label(main_frame, text="",
                                     font=('Segoe UI', 16, 'italic'),
                                     foreground='red',
                                     wraplength=self.ui_WEITE)
        self.title_label.grid(row=2, column=0, pady=(0, 15), sticky='w')

        # --- Schnell-Download ---
        quick_frame = ttk.LabelFrame(main_frame, text="Schnell-Download", padding="15")
        quick_frame.grid(row=3, column=0, sticky='ew', pady=(0, 15))
        quick_frame.columnconfigure(0, weight=1)

        btn_row = ttk.Frame(quick_frame)
        btn_row.grid(row=0, column=0, sticky='n')
        for txt, cmd in [
            ("🎵 Audio (MP3)", self.download_audio),
            ("🎬 Video (MP4)", self.download_video),
            ("⭐ Video Max Quality", self.download_video_max),
        ]:
            ttk.Button(btn_row, text=txt, style='Primary.TButton',
                       command=cmd, width=20).pack(side='left', padx=5)

        ttk.Label(quick_frame,
                  text="Lädt mit optimalen Standardeinstellungen herunter",
                  style='Info.TLabel').grid(row=1, column=0, pady=(10, 0), sticky='n')

        # --- Erweiterte Optionen ---
        advanced_frame = ttk.LabelFrame(main_frame, text="Erweiterte Optionen", padding="15")
        advanced_frame.grid(row=4, column=0, sticky='ew', pady=(0, 15))
        advanced_frame.columnconfigure(0, weight=3)
        advanced_frame.columnconfigure(1, weight=1)

        ttk.Label(advanced_frame, text="Video Stream:",
                  style='Subtitle.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 5))
        self.video_combo = ttk.Combobox(advanced_frame,
                                        textvariable=self.clicked_stream_video,
                                        width=70, state='readonly')
        self.video_combo.grid(row=1, column=0, pady=(0, 10), sticky='ew')
        self.video_combo['values'] = ['Bitte zuerst URL analysieren']
        self.video_combo.current(0)

        ttk.Checkbutton(advanced_frame, text="Video zu MP4 konvertieren",
                        variable=self.video_to_mp4_var).grid(
            row=1, column=1, padx=(10, 0), sticky='w')

        ttk.Label(advanced_frame, text="Audio Stream:",
                  style='Subtitle.TLabel').grid(row=2, column=0, sticky='w', pady=(0, 5))
        self.audio_combo = ttk.Combobox(advanced_frame,
                                        textvariable=self.clicked_stream_audio,
                                        width=70, state='readonly')
        self.audio_combo.grid(row=3, column=0, pady=(0, 10), sticky='ew')
        self.audio_combo['values'] = ['Bitte zuerst URL analysieren']
        self.audio_combo.current(0)

        ttk.Checkbutton(advanced_frame, text="Audio zu MP3 konvertieren",
                        variable=self.audio_to_mp3_var).grid(
            row=3, column=1, padx=(10, 0), sticky='w')

        ttk.Button(advanced_frame, text="📥 Mit Auswahl herunterladen",
                   command=self.download_custom,
                   style='Action.TButton').grid(
            row=4, column=0, columnspan=2, pady=(15, 0))

        # --- Speicherorte ---
        paths_frame = ttk.LabelFrame(main_frame, text="Speicherorte", padding="15")
        paths_frame.grid(row=5, column=0, sticky='ew', pady=(0, 15))
        paths_frame.columnconfigure(1, weight=1)

        ttk.Label(paths_frame, text="Audio:").grid(row=0, column=0, sticky='w', pady=5)
        ttk.Entry(paths_frame, textvariable=self.audio_path_var,
                  width=60).grid(row=0, column=1, padx=(10, 10), sticky='ew')
        ttk.Button(paths_frame, text="📁 Durchsuchen",
                   command=lambda: self.browse_folder('audio'),
                   style='Secondary.TButton').grid(row=0, column=2)

        ttk.Label(paths_frame, text="Video:").grid(row=1, column=0, sticky='w', pady=5)
        ttk.Entry(paths_frame, textvariable=self.video_path_var,
                  width=60).grid(row=1, column=1, padx=(10, 10), sticky='ew')
        ttk.Button(paths_frame, text="📁 Durchsuchen",
                   command=lambda: self.browse_folder('video'),
                   style='Secondary.TButton').grid(row=1, column=2)

        # --- Status ---
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=6, column=0, sticky='ew', pady=(10, 0))
        status_frame.columnconfigure(1, weight=1)

        self.status_var = StringVar(value="Bereit")
        ttk.Label(status_frame, text="Status:").grid(row=0, column=0, sticky='w')
        ttk.Label(status_frame, textvariable=self.status_var,
                  relief=SUNKEN, padding=5).grid(
            row=0, column=1, sticky='ew', padx=(10, 0))

        # --- Progressbar ---
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=7, column=0, sticky='ew', pady=(10, 0))

    # --------------------------------------------------------------------
    def set_status(self, message, show_progress=False):
        self.status_var.set(message)
        if show_progress:
            self.progress.start(10)
        else:
            self.progress.stop()
        self.root.update()

    # --------------------------------------------------------------------
    def browse_folder(self, folder_type):
        folder = filedialog.askdirectory(title=f"{folder_type.capitalize()} - Zielordner wählen")
        if folder:
            if folder_type == 'audio':
                self.audio_path_var.set(folder)
            else:
                self.video_path_var.set(folder)

    # --------------------------------------------------------------------
    def paste_link(self):
        try:
            self.url_var.set(self.root.clipboard_get().strip())
            self.set_status("Link aus Zwischenablage eingefügt.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Kein Text in der Zwischenablage:\n{str(e)}")

    # --------------------------------------------------------------------
    def clear_link(self):
        self.url_var.set('')
        self.title_label.config(text='')
        self.set_status("URL-Feld geleert.")

    # --------------------------------------------------------------------
    def _base_opts(self):
        """Basis yt-dlp Optionen"""
        return {
            'ffmpeg_location': ffmpeg.get_ffmpeg_exe(),
            'quiet': True,
            'no_warnings': True,
        }

    def _ensure_dir(self, folder):
        if not path.exists(folder):
            makedirs(folder)

    # --------------------------------------------------------------------
    def analyze_url(self):
        def analyze_thread():
            url = self.url_var.get().strip()
            if len(url) < 8:
                messagebox.showwarning("Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            self.set_status("Analysiere YouTube Video...", True)
            try:
                with yt_dlp.YoutubeDL(self._base_opts()) as ydl:
                    info = ydl.extract_info(url, download=False)

                self.title_label.config(text=f"📹 {info.get('title', '')}")

                video_formats = []
                audio_formats = []

                for f in info.get('formats', []):
                    vcodec = f.get('vcodec', 'none')
                    acodec = f.get('acodec', 'none')
                    fmt_id = f.get('format_id', '?')
                    ext = f.get('ext', '?')
                    filesize = f.get('filesize') or f.get('filesize_approx') or 0
                    size_mb = round(filesize / (1024 * 1024), 1) if filesize else 0
                    size_str = f"  •  {size_mb}MB" if size_mb else ""

                    if vcodec != 'none' and acodec == 'none':
                        res = f.get('resolution') or str(f.get('height', '?')) + 'p'
                        fps = f.get('fps') or ''
                        fps_str = f"  •  {fps}fps" if fps else ""
                        label = f"{ext}  •  {res}{fps_str}  •  {vcodec}{size_str}  [id:{fmt_id}]"
                        video_formats.append({'label': label, 'format_id': fmt_id,
                                              'ext': ext, 'height': f.get('height', 0) or 0})

                    elif acodec != 'none' and vcodec == 'none':
                        abr = f.get('abr') or 0
                        abr_str = f"{abr}kbps" if abr else '?kbps'
                        label = f"{ext}  •  {abr_str}  •  {acodec}{size_str}  [id:{fmt_id}]"
                        audio_formats.append({'label': label, 'format_id': fmt_id,
                                              'ext': ext, 'abr': abr})

                # Beste Qualität oben
                video_formats.sort(key=lambda x: (-x['height'], x['ext'] != 'mp4'))
                audio_formats.sort(key=lambda x: (-x['abr'], x['ext'] not in ('m4a',)))

                self._video_formats = video_formats
                self._audio_formats = audio_formats

                self.video_combo['values'] = [f['label'] for f in video_formats] + ['-Kein Video-']
                self.video_combo.current(0)
                self.audio_combo['values'] = [f['label'] for f in audio_formats] + ['-Kein Audio-']
                self.audio_combo.current(0)

                self.set_status(
                    f"Analyse abgeschlossen! "
                    f"{len(video_formats)} Video- / {len(audio_formats)} Audio-Streams gefunden.")

            except Exception as e:
                self.set_status("Fehler bei der Analyse")
                messagebox.showerror("Fehler", f"Fehler beim Analysieren:\n{str(e)}")

        Thread(target=analyze_thread, daemon=True).start()

    # --------------------------------------------------------------------
    def download_audio(self):
        def download_thread():
            url = self.url_var.get().strip()
            if len(url) < 8:
                messagebox.showwarning("Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            destination = self.audio_path_var.get()
            self._ensure_dir(destination)
            self.set_status("Lade Audio herunter und konvertiere zu MP3...", True)

            try:
                opts = self._base_opts()
                opts.update({
                    'format': 'bestaudio/best',
                    'outtmpl': path.join(destination, '%(title)s.%(ext)s'),
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url)
                    title = info.get('title', 'audio')

                self.set_status("Download abgeschlossen!")
                messagebox.showinfo("Erfolg", f"Audio erfolgreich heruntergeladen!\n\n{title}.mp3")
                Popen(f'explorer "{destination}"')

            except Exception as e:
                self.set_status("Fehler beim Download")
                messagebox.showerror("Fehler", f"Fehler beim Herunterladen:\n{str(e)}")

        Thread(target=download_thread, daemon=True).start()

    # --------------------------------------------------------------------
    def download_video(self):
        def download_thread():
            url = self.url_var.get().strip()
            if len(url) < 8:
                messagebox.showwarning("Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            destination = self.video_path_var.get()
            self._ensure_dir(destination)
            self.set_status("Lade Video (MP4) herunter...", True)

            try:
                opts = self._base_opts()
                opts.update({
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
                    'outtmpl': path.join(destination, '%(title)s.%(ext)s'),
                    'merge_output_format': 'mp4',
                })
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url)
                    title = info.get('title', 'video')

                self.set_status("Download abgeschlossen!")
                messagebox.showinfo("Erfolg", f"Video erfolgreich heruntergeladen!\n\n{title}.mp4")
                Popen(f'explorer "{destination}"')

            except Exception as e:
                self.set_status("Fehler beim Download")
                messagebox.showerror("Fehler", f"Fehler beim Herunterladen:\n{str(e)}")

        Thread(target=download_thread, daemon=True).start()

    # --------------------------------------------------------------------
    def download_video_max(self):
        def download_thread():
            url = self.url_var.get().strip()
            if len(url) < 8:
                messagebox.showwarning("Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            destination = self.video_path_var.get()
            self._ensure_dir(destination)
            self.set_status("Lade Video in maximaler Qualität herunter...", True)

            try:
                opts = self._base_opts()
                opts.update({
                    'format': 'bestvideo+bestaudio/best',
                    'outtmpl': path.join(destination, '%(title)s.%(ext)s'),
                    'merge_output_format': 'mp4',
                })
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url)
                    title = info.get('title', 'video')

                self.set_status("Download abgeschlossen!")
                messagebox.showinfo("Erfolg",
                    f"Video in max. Qualität heruntergeladen!\n\n{title}.mp4")
                Popen(f'explorer "{destination}"')

            except Exception as e:
                self.set_status("Fehler beim Download")
                messagebox.showerror("Fehler", f"Fehler beim Herunterladen:\n{str(e)}")

        Thread(target=download_thread, daemon=True).start()

    # --------------------------------------------------------------------
    def download_custom(self):
        def download_thread():
            url = self.url_var.get().strip()
            v_label = self.clicked_stream_video.get()
            a_label = self.clicked_stream_audio.get()

            if len(url) < 8:
                messagebox.showwarning("Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            no_video = v_label in ['Bitte zuerst URL analysieren', '-Kein Video-']
            no_audio = a_label in ['Bitte zuerst URL analysieren', '-Kein Audio-']

            if no_video and no_audio:
                messagebox.showwarning("Fehler",
                    "Bitte wählen Sie mindestens einen Video- oder Audio-Stream aus!")
                return

            self.set_status("Starte benutzerdefinierten Download...", True)

            try:
                video_fmt_id = None
                audio_fmt_id = None
                video_ext = 'mp4'

                if not no_video:
                    for f in self._video_formats:
                        if f['label'] == v_label:
                            video_fmt_id = f['format_id']
                            video_ext = f['ext']
                            break

                if not no_audio:
                    for f in self._audio_formats:
                        if f['label'] == a_label:
                            audio_fmt_id = f['format_id']
                            break

                # Format-String und Zielordner
                if video_fmt_id and audio_fmt_id:
                    fmt_str = f"{video_fmt_id}+{audio_fmt_id}"
                    destination = self.video_path_var.get()
                elif video_fmt_id:
                    fmt_str = video_fmt_id
                    destination = self.video_path_var.get()
                else:
                    fmt_str = audio_fmt_id
                    destination = self.audio_path_var.get()

                self._ensure_dir(destination)

                opts = self._base_opts()
                opts.update({
                    'format': fmt_str,
                    'outtmpl': path.join(destination, '%(title)s.%(ext)s'),
                })

                # Merge zu MP4 wenn Video vorhanden
                if video_fmt_id:
                    merge_fmt = 'mp4' if self.video_to_mp4_var.get() else video_ext
                    opts['merge_output_format'] = merge_fmt

                # Audio-only zu MP3 konvertieren wenn gewünscht
                if not video_fmt_id and self.audio_to_mp3_var.get():
                    opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url)
                    title = info.get('title', 'download')

                self.set_status("Download abgeschlossen!")
                messagebox.showinfo("Erfolg", f"Download erfolgreich abgeschlossen!\n\n{title}")
                Popen(f'explorer "{destination}"')

            except Exception as e:
                self.set_status("Fehler beim Download")
                messagebox.showerror("Fehler", f"Fehler beim Herunterladen:\n{str(e)}")

        Thread(target=download_thread, daemon=True).start()


# --------------------------------------------------------------------
if __name__ == "__main__":
    root = Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()
