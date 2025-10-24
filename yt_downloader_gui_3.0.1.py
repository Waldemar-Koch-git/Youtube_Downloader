# -*- coding: utf-8 -*-

__version__ = '3.0.1'

"""
YouTube Downloader GUI - Modernisierte Version

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

Author: Waldemar Koch
Updated: 2025 Oktober 17
Modernisiert: Version 3.0.1

License: MIT License (Modified: Non-Commercial Use Only) (CC BY-NC)
"""
# pip install imageio-ffmpeg pytubefix

import imageio_ffmpeg as ffmpeg
from pytubefix import YouTube
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from threading import Thread
from os import path, remove, environ, rename, system
from subprocess import Popen, run
import ssl

system(f"title YouTube Downloader - Version {__version__}")

if (not environ.get('PYTHONHTTPSVERIFY', '') and
        getattr(ssl, '_create_unverified_context', None)):
    ssl._create_default_https_context = ssl._create_unverified_context


class YouTubeDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"YouTube Downloader v{__version__}")
        self.ui_WEITE = 690
        self.ui_HOEHE = 920
        string_Aufloesung = str(self.ui_WEITE) + "x" + str(self.ui_HOEHE)
        #self.root.geometry("690x900")
        self.root.geometry(string_Aufloesung)

        try:
            self.root.iconbitmap("yt_symbol_small.ico")
        except:
            pass

        # --- Variablen ----------------------------------------------------
        self.url_var = StringVar()
        self.audio_path_var = StringVar()
        self.video_path_var = StringVar()
        self.use_po_token_var = BooleanVar(value=True)
        self.allow_oauth_cache_var = BooleanVar(value=True)
        self.audio_to_mp3_var = BooleanVar(value=True)
        self.video_to_mp4_var = BooleanVar(value=True)

        self.clicked_stream_video = StringVar()
        self.clicked_stream_audio = StringVar()
        self.stream_options_v = []
        self.stream_options_a = []

        # Default paths
        parent_dir = path.dirname(path.abspath(__file__))
        self.audio_path_var.set(path.join(parent_dir, "Downloads", "audio"))
        self.video_path_var.set(path.join(parent_dir, "Downloads", "video"))

        # --- UI ---------------------------------------------------------
        self.setup_styles()
        self.create_widgets()

    # --------------------------------------------------------------------
    def setup_styles(self):
        """Moderne Styles definieren"""
        style = ttk.Style()
        style.theme_use('clam')

        bg_color = "#f0f0f0"
        accent_color = "#FF0000"  # YouTube Rot
        button_color = "#2196F3"
        success_color = "#4CAF50"

        style.configure('Primary.TButton',
                        padding=10,
                        font=('Segoe UI', 10, 'bold'),
                        background=button_color)

        style.configure('Action.TButton',
                        padding=15,
                        font=('Segoe UI', 12, 'bold'),
                        background=success_color)

        style.configure('Secondary.TButton',
                        padding=8,
                        font=('Segoe UI', 9))

        style.configure('Title.TLabel',
                        font=('Segoe UI', 16, 'bold'),
                        foreground=accent_color)

        style.configure('Subtitle.TLabel',
                        font=('Segoe UI', 11, 'bold'))

        style.configure('Info.TLabel',
                        font=('Segoe UI', 9),
                        foreground='#666666')

    # --------------------------------------------------------------------
    def create_widgets(self):
        """UI Komponenten erstellen (optimiert für gleichmäßige Verteilung)"""

        # ----- Haupt‑Frame ----------------------------------------------------
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky='nsew')
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # ----- Titel ----------------------------------------------------------
        title_label = ttk.Label(main_frame,
                                text="🎬 YouTube Downloader",
                                style='Title.TLabel')
        title_label.grid(row=0, column=0, pady=(0, 20), sticky='n')

        # ----------------------------------------------------------------------
        # URL‑EINGABE (ein Zeilenlayout mit Spaltengewicht)
        url_frame = ttk.LabelFrame(main_frame,
                                   text="YouTube URL",
                                   padding="15")
        url_frame.grid(row=1, column=0, sticky='ew', pady=(0, 15))
        url_frame.columnconfigure(0, weight=1)  # Entry erstreckt sich
        url_frame.columnconfigure(1, weight=0)  # Button‑Spalte bleibt fest

        ttk.Entry(url_frame,
                  textvariable=self.url_var,
                  font=('Segoe UI', 10)).grid(row=0, column=0,
                                              sticky='ew')

        btn_sub = ttk.Frame(url_frame)
        btn_sub.grid(row=0, column=1, padx=(5, 0))
        ttk.Button(btn_sub, text="Link einfügen",
                   command=self.paste_link).pack(side='left', padx=2)
        ttk.Button(btn_sub, text="Link Analysieren",
                   command=self.analyze_url,
                   style='Primary.TButton').pack(side='left', padx=2)
        ttk.Button(btn_sub, text="Feld Löschen",
                   command=self.clear_link).pack(side='left', padx=2)

        oauth_frame = ttk.Frame(url_frame)
        oauth_frame.grid(row=1, column=0,
                         columnspan=2, sticky='w',
                         pady=(10, 0))
        ttk.Checkbutton(oauth_frame,
                        text="Po-Token verwenden",
                        variable=self.use_po_token_var).grid(row=0,
                                                             column=0,
                                                             padx=(0, 15))
        ttk.Checkbutton(oauth_frame,
                        text="Authentifizierung zwischenspeichern",
                        variable=self.allow_oauth_cache_var).grid(row=0,
                                                                  column=1)

        # Titel‑Anzeige des Videos
        self.title_label = ttk.Label(main_frame,
                                     text="",
                                     font=('Segoe UI', 16, 'italic'),
                                     foreground='red',
                                     wraplength=self.ui_WEITE)
        self.title_label.grid(row=2, column=0,
                              pady=(0, 15), sticky='w')

        # ----------------------------------------------------------------------
        # Schnell‑Downloads
        quick_frame = ttk.LabelFrame(main_frame,
                                     text="Schnell-Download",
                                     padding="15")
        quick_frame.grid(row=3, column=0, sticky='ew', pady=(0, 15))
        quick_frame.columnconfigure(0, weight=1)

        btn_row = ttk.Frame(quick_frame)
        btn_row.grid(row=0, column=0, sticky='n')
        for txt in ["🎵 Audio (MP3)", "🎬 Video (MP4)", "⭐ Video Max Quality"]:
            ttk.Button(btn_row,
                       text=txt,
                       style='Primary.TButton',
                       command={
                           "🎵 Audio (MP3)": self.download_audio,
                           "🎬 Video (MP4)": self.download_video,
                           "⭐ Video Max Quality": self.download_video_max
                       }[txt],
                       width=20).pack(side='left', padx=5)

        ttk.Label(quick_frame,
                  text="Lädt mit optimalen Standardeinstellungen herunter",
                  style='Info.TLabel').grid(row=1, column=0,
                                            pady=(10, 0),
                                            sticky='n')

        # ----------------------------------------------------------------------
        # Erweiterte Optionen
        advanced_frame = ttk.LabelFrame(main_frame,
                                        text="Erweiterte Optionen",
                                        padding="15")
        advanced_frame.grid(row=4, column=0, sticky='ew', pady=(0, 15))
        advanced_frame.columnconfigure(0, weight=3)
        advanced_frame.columnconfigure(1, weight=1)

        ttk.Label(advanced_frame,
                  text="Video Stream:",
                  style='Subtitle.TLabel').grid(row=0, column=0,
                                                sticky='w', pady=(0, 5))
        self.video_combo = ttk.Combobox(advanced_frame,
                                        textvariable=self.clicked_stream_video,
                                        width=70,
                                        state='readonly')
        self.video_combo.grid(row=1, column=0, pady=(0, 10), sticky='ew')
        self.video_combo['values'] = ['Bitte zuerst URL analysieren']
        self.video_combo.current(0)

        ttk.Checkbutton(advanced_frame,
                        text="Video zu MP4 konvertieren",
                        variable=self.video_to_mp4_var).grid(row=1,
                                                             column=1,
                                                             padx=(10, 0),
                                                             sticky='w')

        ttk.Label(advanced_frame,
                  text="Audio Stream:",
                  style='Subtitle.TLabel').grid(row=2, column=0,
                                                sticky='w', pady=(0, 5))
        self.audio_combo = ttk.Combobox(advanced_frame,
                                        textvariable=self.clicked_stream_audio,
                                        width=70,
                                        state='readonly')
        self.audio_combo.grid(row=3, column=0, pady=(0, 10), sticky='ew')
        self.audio_combo['values'] = ['Bitte zuerst URL analysieren']
        self.audio_combo.current(0)

        ttk.Checkbutton(advanced_frame,
                        text="Audio zu MP3 konvertieren",
                        variable=self.audio_to_mp3_var).grid(row=3,
                                                             column=1,
                                                             padx=(10, 0),
                                                             sticky='w')

        ttk.Button(advanced_frame,
                   text="📥 Mit Auswahl herunterladen",
                   command=self.download_custom,
                   style='Action.TButton').grid(row=4,
                                                column=0,
                                                columnspan=2,
                                                pady=(15, 0))

        # ----------------------------------------------------------------------
        # Speicherorte
        paths_frame = ttk.LabelFrame(main_frame,
                                     text="Speicherorte",
                                     padding="15")
        paths_frame.grid(row=5, column=0, sticky='ew', pady=(0, 15))
        paths_frame.columnconfigure(1, weight=1)

        ttk.Label(paths_frame, text="Audio:").grid(row=0,
                                                   column=0,
                                                   sticky='w',
                                                   pady=5)
        ttk.Entry(paths_frame,
                  textvariable=self.audio_path_var,
                  width=60).grid(row=0,
                                 column=1,
                                 padx=(10, 10),
                                 sticky='ew')
        ttk.Button(paths_frame,
                   text="📁 Durchsuchen",
                   command=lambda: self.browse_folder('audio'),
                   style='Secondary.TButton').grid(row=0,
                                                   column=2)

        ttk.Label(paths_frame, text="Video:").grid(row=1,
                                                   column=0,
                                                   sticky='w',
                                                   pady=5)
        ttk.Entry(paths_frame,
                  textvariable=self.video_path_var,
                  width=60).grid(row=1,
                                 column=1,
                                 padx=(10, 10),
                                 sticky='ew')
        ttk.Button(paths_frame,
                   text="📁 Durchsuchen",
                   command=lambda: self.browse_folder('video'),
                   style='Secondary.TButton').grid(row=1,
                                                   column=2)

        # ----------------------------------------------------------------------
        # Status‑Bar
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=6, column=0, sticky='ew', pady=(10, 0))
        status_frame.columnconfigure(1, weight=1)  # Status‑Text breiter

        # 1️⃣  <---  STATUS‑VARIABLE HIER ERSTELLEN
        self.status_var = StringVar(value="Bereit")

        ttk.Label(status_frame,
                  text="Status:").grid(row=0,
                                       column=0,
                                       sticky='w')
        self.status_label = ttk.Label(status_frame,
                                      textvariable=self.status_var,
                                      relief=SUNKEN,
                                      padding=5)
        self.status_label.grid(row=0,
                               column=1,
                               sticky='ew',
                               padx=(10, 0))

        # ----------------------------------------------------------------------
        # Progressbar
        self.progress = ttk.Progressbar(main_frame,
                                        mode='indeterminate')
        self.progress.grid(row=7,
                           column=0,
                           sticky='ew',
                           pady=(10, 0))

    # --------------------------------------------------------------------
    def set_status(self, message, show_progress=False):
        """Status aktualisieren"""
        self.status_var.set(message)
        if show_progress:
            self.progress.start(10)
        else:
            self.progress.stop()
        self.root.update()

    # --------------------------------------------------------------------
    def browse_folder(self, folder_type):
        """Ordner auswählen"""
        folder = filedialog.askdirectory(
            title=f"{folder_type.capitalize()} - Zielordner wählen")
        if folder:
            if folder_type == 'audio':
                self.audio_path_var.set(folder)
            else:
                self.video_path_var.set(folder)

    # --------------------------------------------------------------------
    def paste_link(self):
        """Link aus Zwischenablage einfügen"""
        try:
            clip_text = self.root.clipboard_get()
            self.url_var.set(clip_text.strip())
            self.set_status("Link aus Zwischenablage eingefügt.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Kein Text in der Zwischenablage:\n{str(e)}")

    # --------------------------------------------------------------------
    def clear_link(self):
        """URL-Feld leeren"""
        self.url_var.set('')
        self.title_label.config(text='')
        self.set_status("URL-Feld geleert.")

    # --------------------------------------------------------------------
    def analyze_url(self):
        """URL analysieren und Streams laden"""

        def analyze_thread():
            url = self.url_var.get().strip()

            if len(url) < 8:
                messagebox.showwarning(
                    "Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            self.set_status("Analysiere YouTube Video...", True)

            try:
                yt = YouTube(url,
                             use_oauth=self.use_po_token_var.get(),
                             allow_oauth_cache=self.allow_oauth_cache_var.get())

                # Titel anzeigen
                self.title_label.config(text=f"📹 {yt.title}")

                # ---------- Video‑Streams ----------
                video_streams = yt.streams.filter(
                    only_video=True).order_by("resolution")
                mp_videos, other_videos = [], []

                for stream in video_streams:
                    if stream.subtype == 'mp4':
                        mp_videos.append(stream)
                    else:
                        other_videos.append(stream)

                # beste Qualität oben (absteigend) – deshalb reverse()
                mp_videos.reverse()
                other_videos.reverse()

                all_video_streams = mp_videos + other_videos

                video_options = []
                for stream in all_video_streams:
                    size_mb = round(stream.filesize / (1024 * 1024), 2)
                    option = f"{stream.subtype}  •  {stream.resolution}  •  {stream.video_codec}  •  {stream.fps}fps  •  {size_mb}MB"
                    video_options.append(option)

                video_options.append("-Kein Video-")
                self.stream_options_v = video_options
                self.video_combo['values'] = video_options
                self.video_combo.current(0)

                # ---------- Audio‑Streams ----------
                audio_streams = yt.streams.filter(
                    only_audio=True).order_by("abr")
                mp_audios, other_audios = [], []

                for stream in audio_streams:
                    if stream.subtype == 'mp4':
                        mp_audios.append(stream)
                    else:
                        other_audios.append(stream)

                # beste Qualität oben (absteigend) – reverse()
                mp_audios.reverse()
                other_audios.reverse()

                all_audio_streams = mp_audios + other_audios

                audio_options = []
                for stream in all_audio_streams:
                    size_mb = round(stream.filesize / (1024 * 1024), 2)
                    option = f"{stream.subtype}  •  {stream.abr}  •  {stream.audio_codec}  •  {size_mb}MB"
                    audio_options.append(option)

                audio_options.append("-Kein Audio-")
                self.stream_options_a = audio_options
                self.audio_combo['values'] = audio_options
                self.audio_combo.current(0)

                self.set_status("Analyse abgeschlossen! Stream-Optionen verfügbar.")
                #messagebox.showinfo(
                #    "Erfolg",
                #    "Video erfolgreich analysiert!\n\nSie können nun einen Stream auswählen oder direkt herunterladen.")

            except Exception as e:
                self.set_status("Fehler bei der Analyse")
                messagebox.showerror(
                    "Fehler", f"Fehler beim Analysieren:\n{str(e)}")

        Thread(target=analyze_thread, daemon=True).start()

    # --------------------------------------------------------------------
    def download_audio(self):
        """Audio mit Standardeinstellungen herunterladen"""

        def download_thread():
            url = self.url_var.get().strip()
            if len(url) < 8:
                messagebox.showwarning(
                    "Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            self.set_status("Lade Audio herunter...", True)

            try:
                yt = YouTube(url,
                             use_oauth=self.use_po_token_var.get(),
                             allow_oauth_cache=self.allow_oauth_cache_var.get())

                audio = yt.streams.filter(only_audio=True).last()
                destination = self.audio_path_var.get()

                audio_file = audio.download(output_path=destination)
                audio_f_name = path.splitext(audio_file)
                audio_file_mp3 = audio_f_name[0] + '.mp3'
                audio_tmp = audio_file + '_tmp'

                rename(audio_file, audio_tmp)

                self.set_status("Konvertiere zu MP3...", True)

                run([ffmpeg.get_ffmpeg_exe(),
                     '-i', audio_tmp,
                     '-loglevel', 'quiet',
                     '-y',
                     '-c:a', 'mp3',
                     audio_file_mp3])

                remove(audio_tmp)

                self.set_status("Download abgeschlossen!")
                messagebox.showinfo(
                    "Erfolg", f"Audio erfolgreich heruntergeladen!\n\n{audio_file_mp3}")
                Popen(f'explorer "{destination}"')

            except Exception as e:
                self.set_status("Fehler beim Download")
                messagebox.showerror(
                    "Fehler", f"Fehler beim Herunterladen:\n{str(e)}")

        Thread(target=download_thread, daemon=True).start()

    # --------------------------------------------------------------------
    def download_video(self):
        """Video mit Standardeinstellungen herunterladen"""

        def download_thread():
            url = self.url_var.get().strip()
            if len(url) < 8:
                messagebox.showwarning(
                    "Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            self.set_status("Lade Video herunter...", True)

            try:
                yt = YouTube(url,
                             use_oauth=self.use_po_token_var.get(),
                             allow_oauth_cache=self.allow_oauth_cache_var.get())

                video = yt.streams.order_by(
                    "resolution").filter(file_extension='mp4', progressive=False).last()
                audio = yt.streams.filter(only_audio=True).last()
                destination = self.video_path_var.get()

                video_file = video.download(output_path=destination)
                video_tmp = video_file + '_video_tmp'
                rename(video_file, video_tmp)

                self.set_status("Lade Audio herunter...", True)
                audio_file = audio.download(output_path=destination)

                video_f_name = path.splitext(video_file)
                video_file_mp4 = video_f_name[0] + '.mp4'

                self.set_status("Kombiniere Video und Audio...", True)

                run([ffmpeg.get_ffmpeg_exe(),
                     '-i', video_tmp,
                     '-i', audio_file,
                     '-y',
                     '-loglevel', 'quiet',
                     '-c:v', 'copy',
                     '-c:a', 'mp3',
                     video_file_mp4])

                remove(audio_file)
                remove(video_tmp)

                self.set_status("Download abgeschlossen!")
                messagebox.showinfo(
                    "Erfolg", f"Video erfolgreich heruntergeladen!\n\n{video_file_mp4}")
                Popen(f'explorer "{destination}"')

            except Exception as e:
                self.set_status("Fehler beim Download")
                messagebox.showerror(
                    "Fehler", f"Fehler beim Herunterladen:\n{str(e)}")

        Thread(target=download_thread, daemon=True).start()

    # --------------------------------------------------------------------
    def download_video_max(self):
        """Video mit maximaler Qualität herunterladen"""

        def download_thread():
            url = self.url_var.get().strip()
            if len(url) < 8:
                messagebox.showwarning(
                    "Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            self.set_status("Lade Video in maximaler Qualität herunter...", True)

            try:
                yt = YouTube(url,
                             use_oauth=self.use_po_token_var.get(),
                             allow_oauth_cache=self.allow_oauth_cache_var.get())

                video = yt.streams.order_by(
                    "resolution").filter(only_video=True).last()
                audio = yt.streams.filter(only_audio=True).last()
                destination = self.video_path_var.get()

                video_file = video.download(output_path=destination)
                video_f_name = path.splitext(video_file)
                video_ext = video_f_name[1]
                video_tmp = video_file + '_video_tmp'
                rename(video_file, video_tmp)

                self.set_status("Lade Audio herunter...", True)
                audio_file = audio.download(output_path=destination)

                video_file_mp4 = video_f_name[0] + '.mp4'
                video_codec = 'libx264' if video_ext != '.mp4' else 'copy'

                self.set_status("Kombiniere Video und Audio...", True)

                run([ffmpeg.get_ffmpeg_exe(),
                     '-i', video_tmp,
                     '-i', audio_file,
                     '-y',
                     '-loglevel', 'quiet',
                     '-c:v', video_codec,
                     '-c:a', 'mp3',
                     video_file_mp4])

                remove(audio_file)
                remove(video_tmp)

                self.set_status("Download abgeschlossen!")
                messagebox.showinfo(
                    "Erfolg", f"Video in max. Qualität heruntergeladen!\n\n{video_file_mp4}")
                Popen(f'explorer "{destination}"')

            except Exception as e:
                self.set_status("Fehler beim Download")
                messagebox.showerror(
                    "Fehler", f"Fehler beim Herunterladen:\n{str(e)}")

        Thread(target=download_thread, daemon=True).start()

    # --------------------------------------------------------------------
    def download_custom(self):
        """Download mit benutzerdefinierten Stream-Optionen"""

        def download_thread():
            url = self.url_var.get().strip()
            stream_video = self.clicked_stream_video.get()
            stream_audio = self.clicked_stream_audio.get()

            if len(url) < 8:
                messagebox.showwarning(
                    "Fehler", "Bitte gültige YouTube URL eingeben!")
                return

            # Prüfen ob Streams ausgewählt wurden
            if (stream_video in ['Bitte zuerst URL analysieren', '-Kein Video-'] and
                    stream_audio in ['Bitte zuerst URL analysieren', '-Kein Audio-']):
                messagebox.showwarning(
                    "Fehler", "Bitte wählen Sie mindestens einen Video- oder Audio-Stream aus!")
                return

            self.set_status("Starte benutzerdefinierten Download...", True)

            try:
                yt = YouTube(url,
                             use_oauth=self.use_po_token_var.get(),
                             allow_oauth_cache=self.allow_oauth_cache_var.get())

                # Variablen initialisieren
                video_file = None
                audio_file = None
                video_tmp = None
                audio_tmp = None
                final_output = None
                destination = None

                # === VIDEO VERARBEITUNG ===
                if stream_video not in ['Bitte zuerst URL analysieren', '-Kein Video-']:
                    self.set_status("Lade Video herunter...", True)

                    parts = stream_video.split("  •  ")
                    video_format = parts[0].strip()
                    resolution = parts[1].strip()
                    video_codec = parts[2].strip()

                    video_stream = yt.streams.filter(
                        only_video=True,
                        file_extension=video_format,
                        resolution=resolution,
                        video_codec=video_codec
                    ).first()

                    if not video_stream:
                        raise Exception("Video-Stream mit den gewählten Parametern nicht gefunden!")

                    destination = self.video_path_var.get()
                    video_file = video_stream.download(output_path=destination)

                    video_f_name = path.splitext(video_file)
                    video_ext = video_f_name[1]
                    video_tmp = video_file + '_video.tmp'

                    rename(video_file, video_tmp)

                    if self.video_to_mp4_var.get() and video_ext != '.mp4':
                        video_codec_out = 'libx264'
                        final_video_name = video_f_name[0] + '.mp4'
                    else:
                        video_codec_out = 'copy'
                        final_video_name = video_file

                # === AUDIO VERARBEITUNG ===
                if stream_audio not in ['Bitte zuerst URL analysieren', '-Kein Audio-']:
                    self.set_status("Lade Audio herunter...", True)

                    parts = stream_audio.split("  •  ")
                    audio_format = parts[0].strip()
                    abr = parts[1].strip()
                    audio_codec = parts[2].strip()

                    audio_stream = yt.streams.filter(
                        only_audio=True,
                        file_extension=audio_format,
                        abr=abr,
                        audio_codec=audio_codec
                    ).first()

                    if not audio_stream:
                        raise Exception("Audio-Stream mit den gewählten Parametern nicht gefunden!")

                    if not destination:
                        destination = self.audio_path_var.get()

                    audio_file = audio_stream.download(output_path=destination)

                    audio_f_name = path.splitext(audio_file)
                    audio_ext = audio_f_name[1]
                    audio_tmp = audio_file + '_audio.tmp'

                    rename(audio_file, audio_tmp)

                    if self.audio_to_mp3_var.get():
                        audio_codec_out = 'mp3'
                        final_audio_name = audio_f_name[0] + '.mp3'
                    else:
                        audio_codec_out = 'copy'
                        final_audio_name = audio_f_name[0] + audio_ext

                # === VERARBEITUNG MIT FFMPEG ===
                if video_tmp and audio_tmp:          # Fall 1: Video UND Audio
                    self.set_status("Kombiniere Video und Audio...", True)
                    final_output = final_video_name

                    run([ffmpeg.get_ffmpeg_exe(),
                         '-i', video_tmp,
                         '-i', audio_tmp,
                         '-y',
                         '-loglevel', 'quiet',
                         '-c:v', video_codec_out,
                         '-c:a', audio_codec_out,
                         final_output])

                    remove(video_tmp)
                    remove(audio_tmp)

                elif video_tmp:                      # Fall 2: Nur Video
                    self.set_status("Verarbeite Video...", True)
                    final_output = final_video_name

                    if video_codec_out == 'libx264':
                        run([ffmpeg.get_ffmpeg_exe(),
                             '-i', video_tmp,
                             '-y',
                             '-loglevel', 'quiet',
                             '-c:v', video_codec_out,
                             final_output])
                        remove(video_tmp)
                    else:
                        rename(video_tmp, final_output)

                elif audio_tmp:                      # Fall 3: Nur Audio
                    self.set_status("Verarbeite Audio...", True)
                    final_output = final_audio_name

                    run([ffmpeg.get_ffmpeg_exe(),
                         '-i', audio_tmp,
                         '-y',
                         '-loglevel', 'quiet',
                         '-c:a', audio_codec_out,
                         final_output])

                    remove(audio_tmp)

                self.set_status("Download abgeschlossen!")
                messagebox.showinfo(
                    "Erfolg", f"Download erfolgreich abgeschlossen!\n\n{final_output}")

                if destination:
                    Popen(f'explorer "{destination}"')

            except Exception as e:
                self.set_status("Fehler beim Download")
                messagebox.showerror(
                    "Fehler", f"Fehler beim Herunterladen:\n{str(e)}")

                # Cleanup bei Fehler
                try:
                    if video_tmp and path.exists(video_tmp):
                        remove(video_tmp)
                    if audio_tmp and path.exists(audio_tmp):
                        remove(audio_tmp)
                except:
                    pass

        Thread(target=download_thread, daemon=True).start()


# --------------------------------------------------------------------
if __name__ == "__main__":
    root = Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()
