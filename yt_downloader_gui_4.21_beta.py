# -*- coding: utf-8 -*-

__version__ = '4.21.0'

"""
YouTube Downloader GUI

Eine benutzerfreundliche grafische Oberfläche zum Herunterladen von Audio und Video
aus YouTube-Links mit modernem Design und verbessertem Workflow.

License: MIT
"""
# pip install imageio-ffmpeg yt-dlp

import threading
import imageio_ffmpeg as ffmpeg
import yt_dlp
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from threading import Thread
from os import path, makedirs, system
from subprocess import Popen
from urllib.parse import urlparse, parse_qs

system(f"title YouTube Downloader - Version {__version__}")

# ─────────────────────────────────────────────────────────────────────────────
#  Konstanten
# ─────────────────────────────────────────────────────────────────────────────
_PLACEHOLDER_ANALYSE  = 'Bitte zuerst URL analysieren'
_PLACEHOLDER_PLAYLIST = '– Playlist erkannt (Auswahl beim Download) –'
_NO_VIDEO  = '-Kein Video-'
_NO_AUDIO  = '-Kein Audio-'

_SKIP_LABELS = {_PLACEHOLDER_ANALYSE, _PLACEHOLDER_PLAYLIST, _NO_VIDEO, _NO_AUDIO}

# Marker für nicht verfügbare Playlist-Einträge (einmalig definiert)
_UNAVAIL_TITLES = {
    '[deleted video]', '[private video]', '[unavailable]',
    '[privates video]', '[gelöschtes video]',
}

MODES = [
    ("🎵 Audio (MP3)",       "audio_mp3"),
    ("🎙 Audio (Opus)",      "audio_opus"),
    ("🎬 Video (MP4)",       "video_mp4"),
    ("⭐ Video (Best)",      "video_best"),
]
MODES_DICT = dict(MODES)


# ═════════════════════════════════════════════════════════════════════════════
#  Hilfsfunktionen
# ═════════════════════════════════════════════════════════════════════════════

def _unique_path(filepath: str, known_names: set | None = None) -> str:
    """
    Gibt einen eindeutigen Dateipfad zurück.
    Prüft sowohl gegen tatsächlich existierende Dateien auf der Festplatte
    als auch gegen *known_names* (ein Set aus Dateinamen ohne Extension,
    das beim Download-Start einmalig aus dem Zielordner befüllt wird).
    So werden Kollisionen auch dann erkannt, wenn mehrere Dateien in einer
    Session heruntergeladen werden, bevor die erste davon auf der Platte liegt.
    Beispiel: "Song.mp3" → "Song (1).mp3" → "Song (2).mp3" …
    """
    base, ext = path.splitext(filepath)
    stem = path.basename(base)

    def _is_taken(fp: str) -> bool:
        if path.exists(fp):
            return True
        if known_names is not None:
            return path.splitext(path.basename(fp))[0] in known_names
        return False

    if not _is_taken(filepath):
        if known_names is not None:
            known_names.add(stem)
        return filepath

    i = 1
    while True:
        candidate = f"{base} ({i}){ext}"
        cand_stem = f"{stem} ({i})"
        if not _is_taken(candidate):
            if known_names is not None:
                known_names.add(cand_stem)
            return candidate
        i += 1


def _scan_existing_stems(folder: str) -> set:
    """
    Gibt ein Set aller Dateinamen (ohne Extension) zurück, die im *folder* liegen.
    Wird einmalig beim Download-Start aufgerufen.
    """
    import os
    stems: set = set()
    try:
        for entry in os.scandir(folder):
            if entry.is_file():
                stems.add(os.path.splitext(entry.name)[0])
    except OSError:
        pass
    return stems


def _collect_final_path(opts: dict) -> tuple:
    """
    Hängt einen postprocessor_hook ein, der den finalen Dateipfad nach
    Abschluss aller Postprozessoren in eine 1-Element-Liste schreibt.
    Gibt (neue_opts, result_liste) zurück – result[0] ist nach dem Download befüllt.
    """
    result: list = [None]

    def _pp_hook(d):
        if d.get('status') != 'finished':
            return
        fp = (d.get('info_dict') or {}).get('filepath', '')
        if fp:
            result[0] = fp

    new_opts = dict(opts)
    pph = list(new_opts.get('postprocessor_hooks') or [])
    pph.append(_pp_hook)
    new_opts['postprocessor_hooks'] = pph
    new_opts['no_overwrites'] = False
    return new_opts, result


def _resolve_outtmpl_unique(url: str, base_opts: dict, known_names: set) -> dict:
    """
    Holt den Videotitel vorab (download=False), berechnet daraus einen
    eindeutigen Ziel-Dateinamen und setzt diesen als fixen outtmpl.
    """
    import os, re

    info_opts = dict(base_opts)
    info_opts['extract_flat'] = False
    info_opts['skip_download'] = True
    info_opts['quiet'] = True
    info_opts['no_warnings'] = True
    info_opts.pop('postprocessors', None)
    info_opts.pop('postprocessor_hooks', None)
    info_opts.pop('progress_hooks', None)

    title      = None
    ext        = None
    webpage_url = None
    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                title       = info.get('title') or info.get('id') or 'video'
                ext         = info.get('ext', 'mp3')
                webpage_url = info.get('webpage_url') or info.get('url') or ''
    except Exception:
        return base_opts

    if not title:
        return base_opts

    safe_title = re.sub(r'[\\/*?:"<>|]', '_', title).strip()

    outtmpl_template = base_opts.get('outtmpl', '%(title)s.%(ext)s')
    dest_dir = os.path.dirname(outtmpl_template)
    if not dest_dir:
        dest_dir = '.'

    # Finale Extension: FFmpegExtractAudio-Codec hat Vorrang
    final_ext = ext
    has_extract_audio = False
    for pp in (base_opts.get('postprocessors') or []):
        if pp.get('key') == 'FFmpegExtractAudio':
            codec = pp.get('preferredcodec', '')
            if codec:
                final_ext = codec
            has_extract_audio = True
            break

    candidate  = os.path.join(dest_dir, f"{safe_title}.{final_ext}")
    unique_path = _unique_path(candidate, known_names)

    new_opts = dict(base_opts)
    stem_path = os.path.splitext(unique_path)[0]
    new_opts['outtmpl'] = stem_path + '.%(ext)s'

    # Bei MP3-Konvertierung: webpage_url vorab in postprocessor_args injizieren.
    # FFmpegExtractAudio schneidet beim Schreiben des comment-Tags die URL am & ab.
    # Mit postprocessor_args übergeben wir -metadata comment=<url> direkt an FFmpeg,
    # was das Abschneiden verhindert.
    if has_extract_audio and webpage_url:
        existing = new_opts.get('postprocessor_args') or {}
        if isinstance(existing, dict):
            ppa = dict(existing)
        else:
            ppa = {}
        ppa['ExtractAudio'] = ['-metadata', f'comment={webpage_url}']
        new_opts['postprocessor_args'] = ppa

    return new_opts


def _rename_after_download(final_path_ref: list, known_names: set):
    """
    Trägt den fertigen Dateinamen in known_names ein.
    Sucht bei Extension-Wechsel (z.B. webm→mp3) nach dem tatsächlichen File.
    """
    import os
    fp = final_path_ref[0]
    if not fp:
        return
    stem = os.path.splitext(os.path.basename(fp))[0]
    if os.path.exists(fp):
        known_names.add(stem)
        return
    # Extension hat sich geändert (z.B. nach Re-encode) → Ordner durchsuchen
    folder = os.path.dirname(fp) or '.'
    try:
        for entry in os.scandir(folder):
            if entry.is_file() and os.path.splitext(entry.name)[0] == stem:
                known_names.add(stem)
                final_path_ref[0] = entry.path
                return
    except OSError:
        pass
    known_names.add(stem)



def _deduplicate_entries(entries: list) -> list:
    """Entfernt Duplikate aus einer yt-dlp-Eintrags-Liste (Schlüssel: Video-ID)."""
    seen: set = set()
    unique = []
    for e in entries:
        vid_id = (e.get('id') or e.get('url') or e.get('webpage_url') or '').strip()
        vid_id = _extract_video_id(vid_id)
        if vid_id and vid_id not in seen:
            seen.add(vid_id)
            unique.append(e)
    return unique


def _extract_video_id(s: str) -> str:
    """Normalisiert eine YouTube-URL oder ID auf die reine Video-ID."""
    if 'watch?v=' in s:
        return s.split('watch?v=')[1].split('&')[0]
    if 'youtu.be/' in s:
        return s.split('youtu.be/')[1].split('?')[0].split('&')[0]
    return s


def _entry_url(e: dict) -> str:
    """Gibt die beste abrufbare URL für einen Playlist-Eintrag zurück."""
    url = e.get('webpage_url') or e.get('url') or ''
    if url.startswith('http'):
        return url
    vid_id = e.get('id', '')
    if vid_id:
        return f"https://www.youtube.com/watch?v={vid_id}"
    return url


def _parse_yt_url(url: str) -> dict:
    """
    Analysiert eine YouTube-URL und gibt ein Dict zurück:
      {
        'video_id':    str | None,
        'list_id':     str | None,
        'index':       int | None,   # 1-basiert
        'is_playlist': bool,
        'is_video':    bool,
        'is_video_in_playlist': bool
      }
    """
    qs = parse_qs(urlparse(url).query)
    video_id = None
    if 'watch?v=' in url:
        video_id = url.split('watch?v=')[1].split('&')[0].split('?')[0]
    elif 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[1].split('?')[0].split('&')[0]
    list_id   = (qs.get('list') or [None])[0]
    index_raw = (qs.get('index') or [None])[0]
    index = int(index_raw) if index_raw and index_raw.isdigit() else None
    return {
        'video_id':             video_id,
        'list_id':              list_id,
        'index':                index,
        'is_playlist':          list_id is not None and video_id is None,
        'is_video':             video_id is not None,
        'is_video_in_playlist': video_id is not None and list_id is not None,
    }


def _resolve_entry_from_playlist(pl_entries: list, p_url: dict) -> str | None:
    """
    Löst aus einer Playlist-Eintrags-Liste die konkrete Video-URL auf.
    Priorität 1: index-Parameter (1-basiert)
    Priorität 2: Video-ID aus v=-Parameter
    Gibt None zurück wenn nichts gefunden.
    """
    if not pl_entries:
        return None
    # Priorität 1: Index
    if p_url['index'] is not None:
        idx_0 = p_url['index'] - 1
        if 0 <= idx_0 < len(pl_entries):
            return _entry_url(pl_entries[idx_0])
    # Priorität 2: Video-ID
    if p_url['video_id']:
        for e in pl_entries:
            eid = _extract_video_id(
                (e.get('id') or e.get('url') or '').strip())
            if eid == p_url['video_id']:
                return _entry_url(e)
    return None


def _is_unavailable_entry(entry: dict) -> bool:
    """Gibt True zurück wenn ein Playlist-Eintrag nicht downloadbar ist."""
    title = (entry.get('title') or '').lower().strip()
    return (
        title in _UNAVAIL_TITLES
        or title.startswith('[deleted')
        or title.startswith('[private')
        or title.startswith('[unavailable')
        or not entry.get('id')
    )


def _attach_scroll(canvas: 'Canvas'):
    """Bindet MouseWheel lokal an einen Canvas (kein bind_all)."""
    def _on_mw(event):
        canvas.yview_scroll(-1 * (event.delta // 120), 'units')
    canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _on_mw))
    canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))


# ═════════════════════════════════════════════════════════════════════════════
#  PlaylistDialog
# ═════════════════════════════════════════════════════════════════════════════
class PlaylistDialog(Toplevel):
    """
    Zeigt alle (bereits deduplizierten) Einträge einer Playlist.
    Ergebnis: dict {'indices': [...], 'mode': str, 'bitrate': str} oder None.
    """

    def __init__(self, parent, entries: list,
                 default_mode: str = "audio_mp3",
                 default_bitrate: str = "320",
                 title_prefix: str = "Playlist"):
        super().__init__(parent)
        self.title(f"{title_prefix} – Auswahl & Download-Einstellungen")
        self.resizable(True, True)
        self.grab_set()
        self.result = None
        self.configure(background='white')

        sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
        w = min(980, sw - 60)
        h = min(720, sh - 80)
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.minsize(700, 380)

        self._entries     = entries
        self._vars: list[BooleanVar] = []
        self._mode_var    = StringVar(value=default_mode)
        self._bitrate_var = StringVar(value=default_bitrate)
        self._use_max_bitrate = BooleanVar(value=True)

        self._build()

    def _build(self):
        head = ttk.Frame(self, padding=(12, 8))
        head.pack(fill='x')
        ttk.Label(head, text=f"📋  {len(self._entries)} Einträge",
                  font=('Segoe UI', 11, 'bold')).pack(side='left')
        sel_frame = ttk.Frame(head)
        sel_frame.pack(side='right')
        for lbl, cmd, w in [("Alle", self._all, 8), ("Keine", self._none, 8),
                             ("Umkehren", self._invert, 9),
                             ("✅ Nur Downloadbare", self._select_downloadable, 18)]:
            ttk.Button(sel_frame, text=lbl, width=w,
                       command=cmd).pack(side='left', padx=2)
        ttk.Separator(self).pack(fill='x')

        lf = ttk.Frame(self)
        lf.pack(fill='both', expand=True, padx=8, pady=4)
        canvas = Canvas(lf, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(lf, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>',
                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',
                    lambda e: canvas.itemconfig(inner_id, width=e.width))
        _attach_scroll(canvas)

        for i, entry in enumerate(self._entries):
            title  = entry.get('title') or f'Eintrag {i+1}'
            is_bad = _is_unavailable_entry(entry)
            var = BooleanVar(value=not is_bad)
            self._vars.append(var)
            row = ttk.Frame(inner)
            row.pack(fill='x', padx=4, pady=1)
            ttk.Checkbutton(row, variable=var).pack(side='left')
            ttk.Label(row, text=f"{i+1:>3}.", width=4,
                      font=('Segoe UI', 9), foreground='#888').pack(side='left')
            dur   = entry.get('duration') or 0
            dur_s = f"  [{int(dur//60)}:{int(dur%60):02d}]" if dur else ""
            fg     = '#CC0000' if is_bad else 'black'
            suffix = '  ⚠ nicht verfügbar' if is_bad else ''
            ttk.Label(row, text=f"{title}{dur_s}{suffix}",
                      font=('Segoe UI', 9), anchor='w', foreground=fg).pack(
                          side='left', fill='x', expand=True, padx=(4, 0))

        ttk.Separator(self).pack(fill='x', pady=(4, 0))

        cfg = ttk.LabelFrame(self,
            text="Download-Einstellungen (gilt für alle ausgewählten Einträge)",
            padding=(12, 6))
        cfg.pack(fill='x', padx=8, pady=6)
        mode_row = ttk.Frame(cfg)
        mode_row.pack(fill='x')
        ttk.Label(mode_row, text="Modus:", width=10).pack(side='left')
        for label, key in MODES:
            ttk.Radiobutton(mode_row, text=label, variable=self._mode_var,
                            value=key,
                            command=self._toggle_bitrate).pack(side='left', padx=6)
        self._br_frame = ttk.Frame(cfg)
        self._br_frame.pack(fill='x', pady=(4, 0))
        self._br_label = ttk.Label(self._br_frame, text="Bitrate:", width=10)
        self._br_label.pack(side='left')
        self._br_combo = ttk.Combobox(
            self._br_frame, textvariable=self._bitrate_var,
            values=["320", "256", "192", "160", "128", "96", "64"],
            width=7, state='readonly', style='Bitrate.TCombobox')
        self._br_combo.pack(side='left', padx=(0, 2))
        ttk.Label(self._br_frame, text="kbps",
                  font=('Segoe UI', 9), foreground='#666').pack(side='left')
        ttk.Radiobutton(self._br_frame, text="Feste Bitrate",
                        variable=self._use_max_bitrate, value=False,
                        command=self._toggle_bitrate).pack(side='left', padx=(14, 2))
        ttk.Radiobutton(self._br_frame, text="Max. Bitrate (automatisch je Datei)",
                        variable=self._use_max_bitrate, value=True,
                        command=self._toggle_bitrate).pack(side='left', padx=(2, 0))
        self._toggle_bitrate()

        ttk.Separator(self).pack(fill='x')

        foot = ttk.Frame(self, padding=(10, 8))
        foot.pack(fill='x')
        self._count_var = StringVar()
        self._upd_count()
        ttk.Label(foot, textvariable=self._count_var,
                  font=('Segoe UI', 9), foreground='#555').pack(side='left')
        for v in self._vars:
            v.trace_add('write', lambda *_: self._upd_count())
        ttk.Button(foot, text="✕ Abbrechen",
                   command=self._cancel).pack(side='right', padx=(6, 0))
        ttk.Button(foot, text="✔ Ausgewählte herunterladen",
                   style='Action.TButton', command=self._ok).pack(side='right')

    def _toggle_bitrate(self):
        mode = self._mode_var.get()
        if mode in ('audio_mp3', 'audio_opus'):
            use_max = self._use_max_bitrate.get()
            self._br_combo.configure(state='disabled' if use_max else 'readonly')
            self._br_label.configure(
                text="MP3-Bitrate:" if mode == 'audio_mp3' else "Opus-Bitrate:")
        else:
            self._br_combo.configure(state='disabled')

    def _upd_count(self):
        n = sum(v.get() for v in self._vars)
        self._count_var.set(f"{n} von {len(self._vars)} ausgewählt")

    def _all(self):    [v.set(True)  for v in self._vars]
    def _none(self):   [v.set(False) for v in self._vars]
    def _invert(self): [v.set(not v.get()) for v in self._vars]

    def _select_downloadable(self):
        """Wählt nur Einträge aus, die voraussichtlich downloadbar sind."""
        for var, entry in zip(self._vars, self._entries):
            var.set(not _is_unavailable_entry(entry))

    def _ok(self):
        sel = [i for i, v in enumerate(self._vars) if v.get()]
        if not sel:
            messagebox.showwarning("Hinweis",
                "Bitte mindestens einen Eintrag auswählen.", parent=self)
            return
        bitrate = '0' if self._use_max_bitrate.get() else self._bitrate_var.get()
        self.result = {'indices': sel, 'mode': self._mode_var.get(),
                       'bitrate': bitrate}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ═════════════════════════════════════════════════════════════════════════════
#  MultiURLDialog
# ═════════════════════════════════════════════════════════════════════════════
class MultiURLDialog(Toplevel):
    """
    Zeigt alle eingegebenen URLs in einer Vorschau-Liste.
    Ergebnis: dict {'urls': [...], 'mode': str, 'bitrate': str} oder None.
    """

    def __init__(self, parent, urls: list,
                 default_mode: str = "audio_mp3",
                 default_bitrate: str = "320"):
        super().__init__(parent)
        self.title("Multi-URL – Auswahl & Download-Einstellungen")
        self.resizable(True, True)
        self.grab_set()
        self.result = None

        sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
        w = min(860, sw - 60)
        h = min(640, sh - 80)
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.minsize(560, 360)

        self._urls   = urls
        self._vars: list[BooleanVar] = []
        self._mode_var    = StringVar(value=default_mode)
        self._bitrate_var = StringVar(value=default_bitrate)
        self._build()

    def _build(self):
        head = ttk.Frame(self, padding=(12, 8))
        head.pack(fill='x')
        ttk.Label(head, text=f"🔗  {len(self._urls)} URLs erkannt",
                  font=('Segoe UI', 11, 'bold')).pack(side='left')
        sel_frame = ttk.Frame(head)
        sel_frame.pack(side='right')
        for lbl, cmd in [("Alle", self._all), ("Keine", self._none),
                         ("Umkehren", self._invert)]:
            ttk.Button(sel_frame, text=lbl, width=8,
                       command=cmd).pack(side='left', padx=2)
        ttk.Separator(self).pack(fill='x')

        lf = ttk.Frame(self)
        lf.pack(fill='both', expand=True, padx=8, pady=4)
        canvas = Canvas(lf, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(lf, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>',
                   lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',
                    lambda e: canvas.itemconfig(inner_id, width=e.width))
        _attach_scroll(canvas)

        for i, url in enumerate(self._urls):
            var = BooleanVar(value=True)
            self._vars.append(var)
            row = ttk.Frame(inner)
            row.pack(fill='x', padx=4, pady=1)
            ttk.Checkbutton(row, variable=var).pack(side='left')
            ttk.Label(row, text=f"{i+1:>3}.", width=4,
                      font=('Segoe UI', 9), foreground='#888').pack(side='left')
            ttk.Label(row, text=url, font=('Segoe UI', 9), anchor='w',
                      foreground='#1565C0').pack(
                          side='left', fill='x', expand=True, padx=(4, 0))

        ttk.Separator(self).pack(fill='x', pady=(4, 0))

        cfg = ttk.LabelFrame(self, text="Download-Einstellungen", padding=(12, 6))
        cfg.pack(fill='x', padx=8, pady=6)
        mode_row = ttk.Frame(cfg)
        mode_row.pack(fill='x')
        ttk.Label(mode_row, text="Modus:", width=10).pack(side='left')
        for label, key in MODES:
            ttk.Radiobutton(mode_row, text=label, variable=self._mode_var,
                            value=key, command=self._toggle_bitrate).pack(side='left', padx=6)
        self._br_frame = ttk.Frame(cfg)
        self._br_frame.pack(fill='x', pady=(4, 0))
        self._br_label = ttk.Label(self._br_frame, text="Bitrate:", width=10)
        self._br_label.pack(side='left')
        self._br_combo = ttk.Combobox(
            self._br_frame, textvariable=self._bitrate_var,
            values=["320", "256", "192", "160", "128", "96", "64"],
            width=7, state='readonly')
        self._br_combo.pack(side='left', padx=(0, 4))
        ttk.Label(self._br_frame, text="kbps",
                  font=('Segoe UI', 9), foreground='#666').pack(side='left')
        self._toggle_bitrate()
        ttk.Separator(self).pack(fill='x')

        foot = ttk.Frame(self, padding=(10, 8))
        foot.pack(fill='x')
        self._count_var = StringVar()
        self._upd_count()
        ttk.Label(foot, textvariable=self._count_var,
                  font=('Segoe UI', 9), foreground='#555').pack(side='left')
        for v in self._vars:
            v.trace_add('write', lambda *_: self._upd_count())
        ttk.Button(foot, text="✕ Abbrechen",
                   command=self._cancel).pack(side='right', padx=(6, 0))
        ttk.Button(foot, text="✔ Ausgewählte herunterladen",
                   style='Action.TButton', command=self._ok).pack(side='right')

    def _toggle_bitrate(self):
        mode = self._mode_var.get()
        if mode in ('audio_mp3', 'audio_opus'):
            self._br_combo.configure(state='readonly')
            self._br_label.configure(
                text="MP3-Bitrate:" if mode == 'audio_mp3' else "Opus-Bitrate:")
        else:
            self._br_combo.configure(state='disabled')

    def _upd_count(self):
        n = sum(v.get() for v in self._vars)
        self._count_var.set(f"{n} von {len(self._vars)} ausgewählt")

    def _all(self):    [v.set(True)  for v in self._vars]
    def _none(self):   [v.set(False) for v in self._vars]
    def _invert(self): [v.set(not v.get()) for v in self._vars]

    def _ok(self):
        sel = [self._urls[i] for i, v in enumerate(self._vars) if v.get()]
        if not sel:
            messagebox.showwarning("Hinweis",
                "Bitte mindestens eine URL auswählen.", parent=self)
            return
        self.result = {'urls': sel, 'mode': self._mode_var.get(),
                       'bitrate': self._bitrate_var.get()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ═════════════════════════════════════════════════════════════════════════════
#  Haupt-App
# ═════════════════════════════════════════════════════════════════════════════
class YouTubeDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"YouTube Downloader v{__version__}")
        self.ui_WEITE = 750
        self.root.geometry(f"{self.ui_WEITE}x600")
        self.root.minsize(680, 700)

        try:
            self.root.iconbitmap("yt_symbol_small.ico")
        except Exception:
            pass

        # Variablen
        self.audio_path_var    = StringVar()
        self.video_path_var    = StringVar()
        self.audio_to_mp3_var  = BooleanVar(value=True)
        self.video_to_mp4_var  = BooleanVar(value=True)
        self.mp3_bitrate_var   = StringVar(value="320")
        self.quick_bitrate_var = StringVar(value="320")
        self.open_folder_var   = BooleanVar(value=False)
        self.write_tags_var    = BooleanVar(value=True)

        self.clicked_stream_video = StringVar()
        self.clicked_stream_audio = StringVar()

        self._video_formats: list = []
        self._audio_formats: list = []
        self._progress_pct = DoubleVar(value=0.0)
        self._advanced_expanded      = False
        self._playlist_expanded      = False
        self._saveopts_expanded      = False
        self._quickdownload_expanded = False

        # Popup-Synchronisation (GUI-Thread ↔ Download-Thread)
        self._playlist_event:  threading.Event | None = None
        self._playlist_result: dict | None = None
        self._playlist_cancel: bool = False

        # Pause / Abbrechen
        self._pause_event:  threading.Event = threading.Event()
        self._pause_event.set()
        self._cancel_flag:  bool = False
        self._download_active: bool = False

        self._pending_playlist: dict | None = None

        parent_dir = path.dirname(path.abspath(__file__))
        self.audio_path_var.set(path.join(parent_dir, "Downloads", "audio"))
        self.video_path_var.set(path.join(parent_dir, "Downloads", "video"))

        self.setup_styles()
        self._build_scrollable_shell()
        self.create_widgets()

    # ─────────────────────────────────────────────────────────────────────────
    def _build_scrollable_shell(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._canvas = Canvas(self.root, borderwidth=0, highlightthickness=0)
        self._vbar   = ttk.Scrollbar(self.root, orient='vertical',
                                     command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vbar_set)
        self._vbar.grid(row=0, column=1, sticky='ns')
        self._canvas.grid(row=0, column=0, sticky='nsew')
        self._vbar.grid_remove()
        self._scrollbar_visible = False

        self._inner    = ttk.Frame(self._canvas)
        self._inner_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor='nw')

        self._inner.bind('<Configure>', self._on_inner_configure)
        self._canvas.bind('<Configure>',
            lambda e: self._canvas.itemconfig(self._inner_id, width=e.width))
        _attach_scroll(self._canvas)

    def _vbar_set(self, lo, hi):
        self._canvas.yview_moveto(lo)
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            if self._scrollbar_visible:
                self._vbar.grid_remove()
                self._scrollbar_visible = False
        else:
            if not self._scrollbar_visible:
                self._vbar.grid()
                self._scrollbar_visible = True
        self._vbar.set(lo, hi)

    def _on_inner_configure(self, event=None):
        self._canvas.configure(scrollregion=self._canvas.bbox('all'))
        if not getattr(self, '_initial_size_set', False):
            content_h = self._inner.winfo_reqheight()
            if content_h < 10:
                return
            screen_h = self.root.winfo_screenheight()
            usable_h = int(screen_h * 0.93)
            new_h    = min(content_h + 4, usable_h)
            cur_w    = self.root.winfo_width() or self.ui_WEITE
            self.root.geometry(f"{cur_w}x{new_h}")
            self._initial_size_set = True

    # ─────────────────────────────────────────────────────────────────────────
    def setup_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('Primary.TButton',
                    padding=10, font=('Segoe UI', 10, 'bold'), background="#2196F3")
        s.configure('Action.TButton',
                    padding=12, font=('Segoe UI', 11, 'bold'), background="#4CAF50")
        s.configure('Secondary.TButton', padding=8, font=('Segoe UI', 9))
        s.configure('Playlist.TButton',  padding=8, font=('Segoe UI', 9, 'bold'),
                    background="#2196F3")
        s.configure('Title.TLabel',
                    font=('Segoe UI', 16, 'bold'), foreground="#FF0000")
        s.configure('Subtitle.TLabel', font=('Segoe UI', 11, 'bold'))
        s.configure('Info.TLabel',    font=('Segoe UI', 9), foreground='#666666')
        s.configure('PlStatus.TLabel', font=('Segoe UI', 9, 'italic'),
                    foreground='#4527A0')
        s.configure('Bitrate.TCombobox', fieldbackground='white', background='white')
        s.map('Bitrate.TCombobox',
              fieldbackground=[('disabled', '#d9d9d9'), ('readonly', 'white')],
              foreground=[('disabled', '#999999'), ('readonly', 'black')],
              selectbackground=[('readonly', 'white')],
              selectforeground=[('readonly', 'black')])

    # ─────────────────────────────────────────────────────────────────────────
    def create_widgets(self):
        mf = ttk.Frame(self._inner, padding="18")
        mf.grid(row=0, column=0, sticky='nsew')
        self._inner.columnconfigure(0, weight=1)
        mf.columnconfigure(0, weight=1)
        self._mf = mf
        r = 0

        # ── Titel ────────────────────────────────────────────────────────────
        ttk.Label(mf, text="🎬 YouTube Downloader",
                  style='Title.TLabel').grid(row=r, column=0, pady=(0, 14), sticky='n')
        r += 1

        # ── URL-Eingabe ──────────────────────────────────────────────────────
        uf = ttk.LabelFrame(mf,
            text="URL(s)  –  ein Link pro Zeile  oder  Playlist-URL", padding="10")
        uf.grid(row=r, column=0, sticky='ew', pady=(0, 10))
        uf.columnconfigure(0, weight=1)
        r += 1

        self.url_text = Text(uf, height=4, font=('Segoe UI', 10),
                             wrap='none', relief='solid', borderwidth=1)
        self.url_text.grid(row=0, column=0, sticky='ew')
        self.url_text.bind('<KeyRelease>', self._on_url_change)
        self.url_text.bind('<<Paste>>', lambda e: self.root.after(50, self._on_url_change))

        hbar = ttk.Scrollbar(uf, orient='horizontal', command=self.url_text.xview)
        hbar.grid(row=1, column=0, sticky='ew')
        hbar.grid_remove()
        self._url_hbar = hbar

        def _url_xscroll(lo, hi):
            if float(lo) <= 0.0 and float(hi) >= 1.0:
                hbar.grid_remove()
            else:
                hbar.grid()
            hbar.set(lo, hi)

        self.url_text.configure(xscrollcommand=_url_xscroll)

        btns = ttk.Frame(uf)
        btns.grid(row=0, column=1, padx=(8, 0), sticky='n')
        ttk.Button(btns, text="📋 Einfügen",
                   command=self.paste_link).pack(fill='x', pady=2)
        ttk.Button(btns, text="🔍 Analysieren",
                   command=self.analyze_url,
                   style='Primary.TButton').pack(fill='x', pady=2)
        ttk.Button(btns, text="🗑 Löschen",
                   command=self.clear_link).pack(fill='x', pady=2)

        ttk.Label(uf,
                  text="Playlist → Playlist-Sektion nutzen  |  Mehrere URLs → Multi-URL-Dialog erscheint automatisch",
                  style='Info.TLabel', wraplength=580).grid(row=2, column=0, columnspan=2,
                                            pady=(5, 0), sticky='w')

        self.title_label = ttk.Label(mf, text="",
                                     font=('Segoe UI', 13, 'italic'),
                                     foreground='red', wraplength=710)
        self.title_label.grid(row=r, column=0, pady=(0, 6), sticky='w')
        r += 1

        # ── Status & Progress ─────────────────────────────────────────────────
        sf = ttk.Frame(mf)
        sf.grid(row=r, column=0, sticky='ew', pady=(0, 4))
        sf.columnconfigure(1, weight=1)
        r += 1

        self.status_var = StringVar(value="Bereit")
        ttk.Label(sf, text="Status:").grid(row=0, column=0, sticky='w')
        ttk.Label(sf, textvariable=self.status_var,
                  relief=SUNKEN, padding=5).grid(
            row=0, column=1, sticky='ew', padx=(8, 0))

        pgf = ttk.Frame(mf)
        pgf.grid(row=r, column=0, sticky='ew', pady=(0, 8))
        pgf.columnconfigure(0, weight=1)
        r += 1

        self.progress = ttk.Progressbar(pgf, mode='determinate',
                                        variable=self._progress_pct, maximum=100)
        self.progress.grid(row=0, column=0, sticky='ew')
        self._pct_label = ttk.Label(pgf, text="", style='Info.TLabel',
                                    width=7, anchor='e')
        self._pct_label.grid(row=0, column=1, padx=(6, 0))
        self._pause_btn  = ttk.Button(pgf, text="⏸ Pause", width=10,
                                      command=self._toggle_pause, state='disabled')
        self._pause_btn.grid(row=0, column=2, padx=(6, 0))
        self._cancel_btn = ttk.Button(pgf, text="✕ Abbrechen", width=12,
                                      command=self._request_cancel, state='disabled')
        self._cancel_btn.grid(row=0, column=3, padx=(4, 0))

        # ── Schnell-Download ──────────────────────────────────────────────────
        qd_header = ttk.Frame(mf, relief='groove', padding=(6, 4))
        qd_header.grid(row=r, column=0, sticky='ew', pady=(0, 2))
        qd_header.columnconfigure(1, weight=1)
        r += 1

        self._qd_toggle_lbl = StringVar(
            value="▶  ⚡ Schnell-Download  –  zum Aufklappen klicken")
        lbl_qd = ttk.Label(qd_header, textvariable=self._qd_toggle_lbl,
                  font=('Segoe UI', 10, 'bold'), foreground='#1565C0', cursor='hand2')
        lbl_qd.grid(row=0, column=0, sticky='w')
        qd_header.bind('<Button-1>', lambda e: self._toggle_quickdownload())
        lbl_qd.bind('<Button-1>', lambda e: self._toggle_quickdownload())

        self._qd_frame = ttk.LabelFrame(mf, text="", padding="10")
        self._qd_frame.columnconfigure(0, weight=1)
        self._qd_grid_row = r
        r += 1

        btn_row = ttk.Frame(self._qd_frame)
        btn_row.grid(row=0, column=0, sticky='n')
        for txt, cmd in [
            ("🎵 Audio (MP3)",  self.quick_audio_mp3),
            ("🎙 Audio (Opus)", self.quick_audio_opus),
            ("🎬 Video (MP4)",  self.quick_video_mp4),
            ("⭐ Video (Best)", self.quick_video_best),
        ]:
            ttk.Button(btn_row, text=txt, style='Primary.TButton',
                       command=cmd, width=16).pack(side='left', padx=4)

        ttk.Label(self._qd_frame,
                  text="MP3/Opus: Maximale verfügbare Bitrate der Quelle wird automatisch genutzt.",
                  style='Info.TLabel', wraplength=680).grid(row=1, column=0, sticky='ew', pady=(6, 2))
        ttk.Label(self._qd_frame,
                  text="Bei 1 URL oder mit playlist-INDEX: direkt herunterladen.\n"
                       "Bei Playlist-URL (ohne INDEX): alle downloadbaren Einträge direkt, kein Dialog.\n"
                       "Gelöschte/private Videos werden automatisch übersprungen.",
                  style='Info.TLabel', wraplength=680).grid(row=2, column=0, pady=(4, 0), sticky='ew')

        # ── Playlist-Sektion ──────────────────────────────────────────────────
        pl_header = ttk.Frame(mf, relief='groove', padding=(6, 4))
        pl_header.grid(row=r, column=0, sticky='ew', pady=(0, 2))
        pl_header.columnconfigure(1, weight=1)
        r += 1

        self._pl_toggle_lbl = StringVar(
            value="▶  📋 Playlist-Verwaltung  –  zum Aufklappen klicken")
        lbl_pl = ttk.Label(pl_header, textvariable=self._pl_toggle_lbl,
                  font=('Segoe UI', 10, 'bold'), foreground='#1565C0', cursor='hand2')
        lbl_pl.grid(row=0, column=0, sticky='w')
        pl_header.bind('<Button-1>', lambda e: self._toggle_playlist())
        lbl_pl.bind('<Button-1>', lambda e: self._toggle_playlist())

        self._pl_frame = ttk.LabelFrame(mf, text="", padding="10")
        self._pl_frame.columnconfigure(0, weight=1)
        self._pl_grid_row = r
        r += 1

        pl_btn_row = ttk.Frame(self._pl_frame)
        pl_btn_row.grid(row=0, column=0, sticky='n')
        ttk.Button(pl_btn_row, text="📋 Playlist bearbeiten",
                   command=self.open_playlist_editor,
                   style='Playlist.TButton', width=22).pack(side='left', padx=4)
        ttk.Button(pl_btn_row, text="▶ Playlist herunterladen",
                   command=self.download_pending_playlist,
                   style='Action.TButton', width=22).pack(side='left', padx=4)

        self._pl_status_var = StringVar(value="Keine Playlist geladen.")
        ttk.Label(self._pl_frame, textvariable=self._pl_status_var,
                  style='PlStatus.TLabel', wraplength=680).grid(
                      row=1, column=0, sticky='w', pady=(6, 0))
        ttk.Label(self._pl_frame,
                  text="Tipp: Nach der Analyse direkt 'Bearbeiten' klicken – "
                       "Playlist ist bereits geladen. Auswahl bleibt bis zum Download erhalten.",
                  style='Info.TLabel', wraplength=680).grid(
                      row=2, column=0, sticky='w', pady=(2, 0))

        # ── Erweiterte Optionen ───────────────────────────────────────────────
        adv_header = ttk.Frame(mf, relief='groove', padding=(6, 4))
        adv_header.grid(row=r, column=0, sticky='ew', pady=(0, 2))
        adv_header.columnconfigure(1, weight=1)
        r += 1

        self._adv_toggle_lbl = StringVar(
            value="▶  Erweiterte Optionen (Einzelvideo)  –  zum Aufklappen klicken")
        lbl_adv = ttk.Label(adv_header, textvariable=self._adv_toggle_lbl,
                  font=('Segoe UI', 10, 'bold'), foreground='#1565C0', cursor='hand2')
        lbl_adv.grid(row=0, column=0, sticky='w')
        adv_header.bind('<Button-1>', lambda e: self._toggle_advanced())
        lbl_adv.bind('<Button-1>', lambda e: self._toggle_advanced())

        self._adv_frame = ttk.LabelFrame(mf, text="", padding="10")
        self._adv_frame.columnconfigure(0, weight=3)
        self._adv_frame.columnconfigure(1, weight=1)
        self._adv_grid_row = r
        r += 1

        ttk.Label(self._adv_frame, text="Video Stream:",
                  style='Subtitle.TLabel').grid(row=0, column=0, sticky='w', pady=(0, 3))
        self.video_combo = ttk.Combobox(self._adv_frame,
                                        textvariable=self.clicked_stream_video,
                                        width=68, state='readonly')
        self.video_combo.grid(row=1, column=0, pady=(0, 7), sticky='ew')
        self.video_combo['values'] = [_PLACEHOLDER_ANALYSE]
        self.video_combo.current(0)
        ttk.Checkbutton(self._adv_frame, text="zu MP4 konvertieren",
                        variable=self.video_to_mp4_var).grid(
            row=1, column=1, padx=(8, 0), sticky='w')

        ttk.Label(self._adv_frame, text="Audio Stream:",
                  style='Subtitle.TLabel').grid(row=2, column=0, sticky='w', pady=(0, 3))
        self.audio_combo = ttk.Combobox(self._adv_frame,
                                        textvariable=self.clicked_stream_audio,
                                        width=68, state='readonly')
        self.audio_combo.grid(row=3, column=0, pady=(0, 7), sticky='ew')
        self.audio_combo['values'] = [_PLACEHOLDER_ANALYSE]
        self.audio_combo.current(0)

        mp3f = ttk.Frame(self._adv_frame)
        mp3f.grid(row=3, column=1, padx=(8, 0), sticky='w')
        ttk.Checkbutton(mp3f, text="zu MP3",
                        variable=self.audio_to_mp3_var,
                        command=self._toggle_bitrate_state).pack(anchor='w')
        brow = ttk.Frame(mp3f)
        brow.pack(anchor='w', pady=(3, 0))
        ttk.Label(brow, text="Bitrate:", style='Info.TLabel').pack(side='left')
        self.bitrate_combo = ttk.Combobox(
            brow, textvariable=self.mp3_bitrate_var,
            values=["320", "256", "192", "160", "128", "96", "64"],
            width=6, state='readonly', style='Bitrate.TCombobox')
        self.bitrate_combo.pack(side='left', padx=(4, 0))
        ttk.Label(brow, text="kbps", style='Info.TLabel').pack(side='left', padx=(2, 0))

        ttk.Button(self._adv_frame, text="📥 Mit Auswahl herunterladen",
                   command=self.download_custom,
                   style='Action.TButton').grid(
            row=4, column=0, columnspan=2, pady=(10, 0))

        # ── Speicherorte & Optionen ───────────────────────────────────────────
        so_header = ttk.Frame(mf, relief='groove', padding=(6, 4))
        so_header.grid(row=r, column=0, sticky='ew', pady=(0, 2))
        so_header.columnconfigure(1, weight=1)
        r += 1

        self._so_toggle_lbl = StringVar(
            value="▶  💾 Speicherorte & Optionen  –  zum Aufklappen klicken")
        lbl_so = ttk.Label(so_header, textvariable=self._so_toggle_lbl,
                  font=('Segoe UI', 10, 'bold'), foreground='#1565C0', cursor='hand2')
        lbl_so.grid(row=0, column=0, sticky='w')
        so_header.bind('<Button-1>', lambda e: self._toggle_saveopts())
        lbl_so.bind('<Button-1>', lambda e: self._toggle_saveopts())

        self._so_frame = ttk.LabelFrame(mf, text="", padding="10")
        self._so_frame.columnconfigure(1, weight=1)
        self._so_grid_row = r
        r += 1

        ttk.Label(self._so_frame, text="Audio:").grid(row=0, column=0, sticky='w', pady=3)
        ttk.Entry(self._so_frame, textvariable=self.audio_path_var,
                  width=54).grid(row=0, column=1, padx=(8, 8), sticky='ew')
        ttk.Button(self._so_frame, text="📁 Durchsuchen",
                   command=lambda: self.browse_folder('audio'),
                   style='Secondary.TButton').grid(row=0, column=2)

        ttk.Label(self._so_frame, text="Video:").grid(row=1, column=0, sticky='w', pady=3)
        ttk.Entry(self._so_frame, textvariable=self.video_path_var,
                  width=54).grid(row=1, column=1, padx=(8, 8), sticky='ew')
        ttk.Button(self._so_frame, text="📁 Durchsuchen",
                   command=lambda: self.browse_folder('video'),
                   style='Secondary.TButton').grid(row=1, column=2)

        opt_row = ttk.Frame(self._so_frame)
        opt_row.grid(row=2, column=0, columnspan=3, sticky='w', pady=(8, 2))
        ttk.Checkbutton(opt_row, text="📂 Zielordner nach Download öffnen",
                        variable=self.open_folder_var).pack(side='left', padx=(0, 20))
        ttk.Checkbutton(opt_row, text="🏷 Metadaten-Tags in Datei schreiben",
                        variable=self.write_tags_var).pack(side='left')

        self.root.after(0, lambda: self._toggle_quickdownload(force_open=True))

    # ═════════════════════════════════════════════════════════════════════════
    #  UI-Hilfsmethoden
    # ═════════════════════════════════════════════════════════════════════════

    def _get_urls(self) -> list:
        raw = self.url_text.get("1.0", END)
        return [l.strip() for l in raw.splitlines()
                if l.strip().startswith('http')]

    def set_status(self, msg, show_progress=False):
        self.status_var.set(msg)
        if show_progress:
            self._progress_pct.set(0.0)
            self._pct_label.config(text="")
        self.root.update_idletasks()

    def _reset_progress(self):
        self.root.after(0, lambda: (
            self._progress_pct.set(0.0),
            self._pct_label.config(text="")))

    def _toggle_bitrate_state(self):
        self.bitrate_combo.config(
            state='readonly' if self.audio_to_mp3_var.get() else 'disabled')

    def _set_download_active(self, active: bool):
        state = 'normal' if active else 'disabled'
        self._download_active = active
        self.root.after(0, lambda: (
            self._pause_btn.config(state=state, text="⏸ Pause"),
            self._cancel_btn.config(state=state)))
        if not active:
            self._pause_event.set()
            self._cancel_flag = False

    def _toggle_pause(self):
        if not self._download_active:
            return
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._pause_btn.config(text="▶ Weiter")
            self.status_var.set("⏸ Pausiert – ▶ Weiter zum Fortfahren")
        else:
            self._pause_event.set()
            self._pause_btn.config(text="⏸ Pause")
            self.status_var.set("▶ Download wird fortgesetzt...")

    def _request_cancel(self):
        if not self._download_active:
            return
        self._cancel_flag = True
        self._pause_event.set()
        self._cancel_btn.config(state='disabled')
        self.status_var.set("✕ Wird abgebrochen...")

    def _check_pause_cancel(self) -> bool:
        self._pause_event.wait()
        return self._cancel_flag

    def _toggle_advanced(self, force_open: bool = False):
        if force_open and self._advanced_expanded:
            return
        self._advanced_expanded = force_open or (not self._advanced_expanded)
        if self._advanced_expanded:
            self._adv_frame.grid(row=self._adv_grid_row, column=0,
                                 sticky='ew', pady=(0, 10), in_=self._mf)
            self._adv_toggle_lbl.set(
                "▼  Erweiterte Optionen (Einzelvideo)  –  zum Einklappen klicken")
        else:
            self._adv_frame.grid_remove()
            self._adv_toggle_lbl.set(
                "▶  Erweiterte Optionen (Einzelvideo)  –  zum Aufklappen klicken")

    def _toggle_playlist(self, force_open: bool = False):
        if force_open and self._playlist_expanded:
            return
        self._playlist_expanded = force_open or (not self._playlist_expanded)
        if self._playlist_expanded:
            self._pl_frame.grid(row=self._pl_grid_row, column=0,
                                sticky='ew', pady=(0, 8), in_=self._mf)
            self._pl_toggle_lbl.set(
                "▼  📋 Playlist-Verwaltung  –  zum Einklappen klicken")
        else:
            self._pl_frame.grid_remove()
            self._pl_toggle_lbl.set(
                "▶  📋 Playlist-Verwaltung  –  zum Aufklappen klicken")

    def _toggle_saveopts(self, force_open: bool = False):
        if force_open and self._saveopts_expanded:
            return
        self._saveopts_expanded = force_open or (not self._saveopts_expanded)
        if self._saveopts_expanded:
            self._so_frame.grid(row=self._so_grid_row, column=0,
                                sticky='ew', pady=(0, 10), in_=self._mf)
            self._so_toggle_lbl.set(
                "▼  💾 Speicherorte & Optionen  –  zum Einklappen klicken")
        else:
            self._so_frame.grid_remove()
            self._so_toggle_lbl.set(
                "▶  💾 Speicherorte & Optionen  –  zum Aufklappen klicken")

    def _toggle_quickdownload(self, force_open: bool = False):
        if force_open and self._quickdownload_expanded:
            return
        self._quickdownload_expanded = force_open or (not self._quickdownload_expanded)
        if self._quickdownload_expanded:
            self._qd_frame.grid(row=self._qd_grid_row, column=0,
                                sticky='ew', pady=(0, 8), in_=self._mf)
            self._qd_toggle_lbl.set(
                "▼  ⚡ Schnell-Download  –  zum Einklappen klicken")
        else:
            self._qd_frame.grid_remove()
            self._qd_toggle_lbl.set(
                "▶  ⚡ Schnell-Download  –  zum Aufklappen klicken")

    def _on_url_change(self, event=None):
        urls = self._get_urls()
        if not urls:
            return
        if len(urls) == 1:
            p = _parse_yt_url(urls[0])
            if p['is_video']:
                self._toggle_advanced(force_open=True)
                if p['is_video_in_playlist']:
                    self._toggle_playlist(force_open=True)
            elif p['is_playlist']:
                self._toggle_playlist(force_open=True)
        elif len(urls) > 1:
            self._toggle_playlist(force_open=True)

    def _reset_pending_playlist(self):
        self._pending_playlist = None
        self._pl_status_var.set("Keine Playlist geladen.")

    def _update_pl_status(self, text: str):
        self.root.after(0, lambda: self._pl_status_var.set(text))

    def browse_folder(self, kind):
        d = filedialog.askdirectory(title=f"{kind.capitalize()} – Zielordner")
        if d:
            (self.audio_path_var if kind == 'audio' else self.video_path_var).set(d)

    def paste_link(self):
        try:
            self.url_text.insert(END, self.root.clipboard_get().strip() + '\n')
            self.set_status("Link eingefügt.")
            self.root.after(50, self._on_url_change)
        except Exception as e:
            messagebox.showerror("Fehler", f"Zwischenablage leer:\n{e}")

    def clear_link(self):
        self.url_text.delete("1.0", END)
        self.title_label.config(text='')
        self._video_formats = []
        self._audio_formats = []
        for cb, ph in [(self.video_combo, _PLACEHOLDER_ANALYSE),
                       (self.audio_combo, _PLACEHOLDER_ANALYSE)]:
            cb['values'] = [ph]
            cb.current(0)
        self._reset_progress()
        self._reset_pending_playlist()
        self.set_status("Felder geleert.")

    def _open_folder_if_wanted(self, dest):
        if self.open_folder_var.get():
            Popen(f'explorer "{dest}"')

    # ═════════════════════════════════════════════════════════════════════════
    #  yt-dlp Basis-Optionen
    # ═════════════════════════════════════════════════════════════════════════

    def _base_opts(self) -> dict:
        opts = {
            'ffmpeg_location': ffmpeg.get_ffmpeg_exe(),
            'quiet':       False,
            'no_warnings': False,
        }
        if self.write_tags_var.get():
            opts['postprocessors'] = [{
                'key':          'FFmpegMetadata',
                'add_metadata': True,
                'add_chapters': False,
            }]
        return opts

    def _ensure_dir(self, d):
        if not path.exists(d):
            makedirs(d)

    # ═════════════════════════════════════════════════════════════════════════
    #  Fortschritts-Hook
    # ═════════════════════════════════════════════════════════════════════════

    def _make_hook(self, prefix="Lade...", idx=0, total=1):
        def hook(d):
            if d['status'] == 'downloading':
                tb = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                db = d.get('downloaded_bytes', 0)
                sp = d.get('speed') or 0
                sp_s = f"  •  {sp/1024/1024:.1f} MB/s" if sp else ""
                if tb > 0:
                    item_pct = db / tb * 100
                    overall  = (idx / total * 100) + (item_pct / total)
                    lbl = f"{idx+1}/{total}" if total > 1 else f"{item_pct:.0f} %"
                    self.root.after(0, lambda p=overall, l=lbl, s=sp_s: (
                        self._progress_pct.set(p),
                        self._pct_label.config(text=l),
                        self.status_var.set(f"{prefix}{s}")))
                else:
                    cur = self._progress_pct.get()
                    self.root.after(0,
                        lambda c=cur: self._progress_pct.set((c + 1) % 99))
            elif d['status'] == 'finished':
                p = (idx + 1) / total * 100
                self.root.after(0, lambda p=p: (
                    self._progress_pct.set(p),
                    self._pct_label.config(text=f"{p:.0f} %")))
        return hook

    # ═════════════════════════════════════════════════════════════════════════
    #  URL-Analyse
    # ═════════════════════════════════════════════════════════════════════════

    def analyze_url(self):
        def worker():
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning("Fehler", "Keine gültige URL eingegeben!")
                return
            url = urls[0]
            p   = _parse_yt_url(url)
            self.root.after(0, lambda: self.set_status("Analysiere...", True))
            try:
                # ── Fall 1: Video mit Playlist-Kontext ────────────────────────
                if p['is_video_in_playlist']:
                    opts_pl = self._base_opts()
                    opts_pl['extract_flat'] = True
                    opts_pl['noplaylist']   = False
                    pl_entries = []
                    pl_title   = ''
                    try:
                        playlist_url = f"https://www.youtube.com/playlist?list={p['list_id']}"
                        with yt_dlp.YoutubeDL(opts_pl) as ydl:
                            pl_info = ydl.extract_info(playlist_url, download=False)
                        if pl_info:
                            pl_entries = _deduplicate_entries(list(pl_info.get('entries', [])))
                            pl_title   = pl_info.get('title', '')
                    except Exception:
                        pass

                    target_url = _resolve_entry_from_playlist(pl_entries, p) or url

                    opts_v = self._base_opts()
                    opts_v['noplaylist'] = True
                    with yt_dlp.YoutubeDL(opts_v) as ydl:
                        full = ydl.extract_info(target_url, download=False)

                    vfmts, afmts = self._extract_formats(full)
                    self._video_formats = vfmts
                    self._audio_formats = afmts
                    video_title = full.get('title', '')
                    index_hint  = f"  (Index {p['index']})" if p['index'] else ""
                    cnt = len(pl_entries)
                    cnt_dl = sum(1 for e in pl_entries if not _is_unavailable_entry(e))

                    if pl_entries:
                        self._pending_playlist = {
                            'entries': pl_entries,
                            'title':   pl_title,
                            'list_id': p['list_id'],
                        }

                    status_txt = (
                        f"Analyse fertig – {len(vfmts)}V/{len(afmts)}A-Streams"
                        + (f"  |  Playlist: {cnt_dl}/{cnt} downloadbar" if cnt else ""))
                    pl_status  = (
                        f"📋 {pl_title}  ({cnt_dl}/{cnt} downloadbar) – Playlist geladen."
                        if cnt else "Playlist konnte nicht geladen werden.")

                    self.root.after(0, lambda: (
                        self._toggle_advanced(force_open=True),
                        self._toggle_playlist(force_open=True),
                        self.title_label.config(
                            text=f"📹 {video_title}{index_hint}"
                                 + (f"  –  Playlist: {pl_title}" if pl_title else "")),
                        self.video_combo.__setitem__('values',
                            [f['label'] for f in vfmts] + [_NO_VIDEO]),
                        self.video_combo.current(0),
                        self.audio_combo.__setitem__('values',
                            [f['label'] for f in afmts] + [_NO_AUDIO]),
                        self.audio_combo.current(0),
                        self._pl_status_var.set(pl_status),
                        self.set_status(status_txt)))
                    return

                # ── Fall 2: Reine Playlist-URL ─────────────────────────────────
                opts = self._base_opts()
                opts['extract_flat'] = True
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                if info.get('_type') == 'playlist':
                    entries = _deduplicate_entries(list(info.get('entries', [])))
                    cnt     = len(entries)
                    cnt_dl  = sum(1 for e in entries if not _is_unavailable_entry(e))
                    self._pending_playlist = {
                        'entries': entries,
                        'title':   info.get('title', ''),
                        'list_id': p['list_id'],
                    }
                    pl_title = info.get('title', '')
                    self.root.after(0, lambda: (
                        self.title_label.config(
                            text=f"📋 Playlist: {pl_title}  ({cnt_dl}/{cnt} downloadbar)"),
                        self.set_status(f"Playlist erkannt – {cnt_dl}/{cnt} downloadbar"),
                        self._toggle_playlist(force_open=True),
                        self._pl_status_var.set(
                            f"📋 {pl_title}  ({cnt_dl}/{cnt} downloadbar) – Playlist geladen."),
                        self.video_combo.__setitem__('values', [_PLACEHOLDER_PLAYLIST]),
                        self.video_combo.current(0),
                        self.audio_combo.__setitem__('values', [_PLACEHOLDER_PLAYLIST]),
                        self.audio_combo.current(0)))
                    return

                # ── Fall 3: Einzelvideo ohne Playlist ─────────────────────────
                opts2 = self._base_opts()
                opts2['noplaylist'] = True
                with yt_dlp.YoutubeDL(opts2) as ydl:
                    full = ydl.extract_info(url, download=False)

                vfmts, afmts = self._extract_formats(full)
                self._video_formats = vfmts
                self._audio_formats = afmts

                self.root.after(0, lambda: (
                    self._toggle_advanced(force_open=True),
                    self.title_label.config(text=f"📹 {full.get('title','')}"),
                    self.video_combo.__setitem__('values',
                        [f['label'] for f in vfmts] + [_NO_VIDEO]),
                    self.video_combo.current(0),
                    self.audio_combo.__setitem__('values',
                        [f['label'] for f in afmts] + [_NO_AUDIO]),
                    self.audio_combo.current(0),
                    self.set_status(
                        f"Analyse fertig – {len(vfmts)} Video / {len(afmts)} Audio-Streams")))

            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda m=err_msg: (
                    self.set_status("Fehler bei Analyse"),
                    messagebox.showerror("Fehler", f"Analyse-Fehler:\n{m}")))

        Thread(target=worker, daemon=True).start()

    def _extract_formats(self, full: dict) -> tuple[list, list]:
        """Extrahiert und sortiert Video- und Audio-Format-Listen aus yt-dlp-Info."""
        vfmts, afmts = [], []
        for f in full.get('formats', []):
            vc  = f.get('vcodec', 'none')
            ac  = f.get('acodec', 'none')
            fid = f.get('format_id', '?')
            ext = f.get('ext', '?')
            sz  = f.get('filesize') or f.get('filesize_approx') or 0
            smb = round(sz / 1048576, 1) if sz else 0
            ss  = f"  •  {smb}MB" if smb else ""
            if vc != 'none' and ac == 'none':
                res = f.get('resolution') or f"{f.get('height','?')}p"
                fps = f.get('fps') or ''
                lbl = (f"{ext}  •  {res}"
                       f"{'  •  '+str(fps)+'fps' if fps else ''}"
                       f"  •  {vc}{ss}  [id:{fid}]")
                vfmts.append({'label': lbl, 'format_id': fid, 'ext': ext,
                              'height': f.get('height', 0) or 0, 'size_mb': smb})
            elif ac != 'none' and vc == 'none':
                abr = f.get('abr') or 0
                lbl = f"{ext}  •  {abr if abr else '?'}kbps  •  {ac}{ss}  [id:{fid}]"
                afmts.append({'label': lbl, 'format_id': fid, 'ext': ext,
                              'abr': abr, 'size_mb': smb})
        vfmts.sort(key=lambda x: (-x['size_mb'] if x['size_mb'] else -x['height'], -x['height']))
        afmts.sort(key=lambda x: (-x['size_mb'] if x['size_mb'] else -x['abr'],    -x['abr']))
        return vfmts, afmts

    # ═════════════════════════════════════════════════════════════════════════
    #  Popup-Helfer (GUI-Thread ↔ Download-Thread)
    # ═════════════════════════════════════════════════════════════════════════

    def _wait_for_popup(self) -> dict | None:
        self._playlist_event.wait(timeout=900)
        if self._playlist_cancel or self._playlist_result is None:
            return None
        return self._playlist_result

    def _open_playlist_popup(self, entries, default_mode, default_bitrate, title_prefix):
        dlg = PlaylistDialog(self.root, entries,
                             default_mode=default_mode,
                             default_bitrate=default_bitrate,
                             title_prefix=title_prefix)
        self.root.wait_window(dlg)
        self._playlist_result = dlg.result
        self._playlist_cancel = (dlg.result is None)
        if self._playlist_event:
            self._playlist_event.set()

    def _request_playlist_popup(self, entries, default_mode, default_bitrate,
                                 title_prefix="Playlist") -> dict | None:
        self._playlist_event  = threading.Event()
        self._playlist_result = None
        self._playlist_cancel = False
        self.root.after(0, lambda: self._open_playlist_popup(
            entries, default_mode, default_bitrate, title_prefix))
        return self._wait_for_popup()

    def _open_multiurl_popup(self, urls, default_mode, default_bitrate):
        dlg = MultiURLDialog(self.root, urls,
                             default_mode=default_mode,
                             default_bitrate=default_bitrate)
        self.root.wait_window(dlg)
        self._playlist_result = dlg.result
        self._playlist_cancel = (dlg.result is None)
        if self._playlist_event:
            self._playlist_event.set()

    def _request_multiurl_popup(self, urls, default_mode, default_bitrate) -> dict | None:
        self._playlist_event  = threading.Event()
        self._playlist_result = None
        self._playlist_cancel = False
        self.root.after(0, lambda: self._open_multiurl_popup(
            urls, default_mode, default_bitrate))
        return self._wait_for_popup()

    # ═════════════════════════════════════════════════════════════════════════
    #  Playlist-Sektion: Laden & Bearbeiten
    # ═════════════════════════════════════════════════════════════════════════

    def open_playlist_editor(self):
        def worker():
            existing = self._pending_playlist

            if existing and existing.get('entries'):
                entries  = existing['entries']
                pl_title = existing.get('title', 'Unbekannte Playlist')
                self.root.after(0, lambda: self.set_status(
                    f"Playlist '{pl_title}' – {len(entries)} Einträge (bereits geladen)"))
            else:
                urls = self._get_urls()
                if not urls:
                    self.root.after(0, lambda: messagebox.showwarning(
                        "Kein URL", "Bitte zuerst eine Playlist-URL eingeben."))
                    return
                url = urls[0]
                p   = _parse_yt_url(url)

                fetch_url = (f"https://www.youtube.com/playlist?list={p['list_id']}"
                             if p['is_video_in_playlist'] and p['list_id'] else url)

                self.root.after(0, lambda: self.set_status("Playlist wird geladen...", True))
                self._update_pl_status("⏳ Lade Playlist-Informationen...")

                try:
                    opts = self._base_opts()
                    opts['extract_flat'] = True
                    opts['noplaylist']   = False
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(fetch_url, download=False)
                except Exception as e:
                    err = str(e)
                    self.root.after(0, lambda m=err: (
                        self.set_status("Fehler beim Laden"),
                        messagebox.showerror("Fehler", f"Playlist nicht abrufbar:\n{m}")))
                    self._update_pl_status("❌ Fehler beim Laden.")
                    return

                if info.get('_type') != 'playlist':
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Keine Playlist",
                        "Die URL verweist auf keine Playlist.\n"
                        "Bitte eine Playlist-URL eingeben."))
                    self._update_pl_status("❌ Keine Playlist erkannt.")
                    self.root.after(0, lambda: self.set_status("Keine Playlist erkannt."))
                    return

                entries  = _deduplicate_entries(list(info.get('entries', [])))
                pl_title = info.get('title', 'Unbekannte Playlist')

                if not entries:
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Leer", "Playlist scheint leer zu sein."))
                    self._update_pl_status("❌ Playlist ist leer.")
                    return

            self._update_pl_status(
                f"✅ '{pl_title}' – {len(entries)} Einträge. Bitte Auswahl treffen...")
            self.root.after(0, lambda: self.set_status(
                f"Playlist '{pl_title}' – {len(entries)} Einträge"))

            result = self._request_playlist_popup(
                entries,
                default_mode    = 'audio_mp3',
                default_bitrate = self.quick_bitrate_var.get(),
                title_prefix    = f"Playlist: {pl_title}")

            if result is None:
                self._update_pl_status(
                    f"⚠ Bearbeitung abgebrochen – {len(entries)} Einträge verfügbar")
                self.root.after(0, lambda: self.set_status("Abgebrochen."))
                return

            self._pending_playlist = {
                'url':     self._get_urls()[0] if self._get_urls() else '',
                'entries': entries,
                'title':   pl_title,
                'result':  result,
            }
            n_sel    = len(result['indices'])
            mode_lbl = MODES_DICT.get(result['mode'], result['mode'])
            self._update_pl_status(
                f"✅ '{pl_title}': {n_sel}/{len(entries)} Einträge, "
                f"Modus: {mode_lbl} → jetzt 'Playlist herunterladen' drücken")
            self.root.after(0, lambda: self.set_status(
                f"Playlist bereit: {n_sel} Einträge ausgewählt"))

        self._update_pl_status("⏳ Wird vorbereitet...")
        Thread(target=worker, daemon=True).start()

    def download_pending_playlist(self):
        def worker():
            pending = self._pending_playlist
            if not pending or not pending.get('entries'):
                self.root.after(0, lambda: messagebox.showwarning(
                    "Keine Playlist",
                    "Bitte zuerst eine Playlist-URL analysieren\n"
                    "oder 'Playlist bearbeiten' ausführen."))
                return

            entries = pending['entries']
            result  = pending.get('result')

            if result is None:
                # Playlist analysiert aber noch nicht bearbeitet:
                # Dialog jetzt zeigen damit Modus/Auswahl festgelegt werden kann
                pl_title = pending.get('title', '')
                result = self._request_playlist_popup(
                    entries,
                    default_mode='audio_mp3',
                    default_bitrate='0',
                    title_prefix=f"Playlist: {pl_title}")
                if result is None:
                    self.root.after(0, lambda: self.set_status("Abgebrochen."))
                    return

            mode    = result['mode']
            bitrate = result['bitrate']
            prefix  = MODES_DICT.get(mode, "Download")

            resolved = [_entry_url(entries[i]) for i in result['indices']]
            if not resolved:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Leer", "Keine URLs zum Herunterladen."))
                return

            self._pending_playlist = None
            self._update_pl_status("⬇ Download läuft...")
            self._run_urls(resolved, mode, bitrate, prefix)
            self._update_pl_status("Keine Playlist geladen.")

        Thread(target=worker, daemon=True).start()

    def _build_opts_for_mode(self, mode: str, bitrate: str) -> tuple[dict, str]:
        """Gibt (opts, dest) passend zum Modus zurück."""
        opts = self._base_opts()

        if mode == 'audio_mp3':
            dest = self.audio_path_var.get()
            opts.update({
                'format': 'bestaudio/best',
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })
            mp3_pp = {'key': 'FFmpegExtractAudio',
                      'preferredcodec': 'mp3', 'preferredquality': bitrate}
            pps = opts.get('postprocessors', [])
            opts['postprocessors'] = [mp3_pp] + [
                p for p in pps if p.get('key') != 'FFmpegExtractAudio']


        elif mode == 'audio_opus':
            dest = self.audio_path_var.get()
            opts.update({
                'format': ('bestaudio[ext=webm][acodec=opus]'
                           '/bestaudio[acodec=opus]'
                           '/bestaudio/best'),
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })

        elif mode == 'video_mp4':
            dest = self.video_path_var.get()
            opts.update({
                'format': ('bestvideo[ext=mp4]+bestaudio[ext=m4a]'
                           '/bestvideo[ext=mp4]+bestaudio'
                           '/bestvideo+bestaudio'
                           '/best'),
                'outtmpl':             path.join(dest, '%(title)s.%(ext)s'),
                'merge_output_format': 'mp4',
            })

        else:  # video_best
            dest = self.video_path_var.get()
            opts.update({
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })

        return opts, dest

    def _run_urls(self, urls: list, mode: str, bitrate: str, prefix: str,
                  silent_errors: bool = False):
        """Lädt eine fertig aufgelöste URL-Liste herunter."""
        total = len(urls)
        done  = []
        skipped = []

        self._cancel_flag = False
        self._pause_event.set()
        self._set_download_active(True)
        self.root.after(0, lambda: self.set_status(
            f"Starte Download: {total} Datei(en)...", True))

        # Zielordner und Basis-Opts einmalig bestimmen
        base_opts, dest = self._build_opts_for_mode(mode, bitrate)
        self._ensure_dir(dest)
        known_names = _scan_existing_stems(dest)

        for i, url in enumerate(urls):
            if self._check_pause_cancel():
                break

            item_opts = dict(base_opts)
            if 'watch?v=' in url or 'youtu.be/' in url:
                item_opts['noplaylist'] = True

            # Eindeutigen Zielpfad VOR dem Download festlegen
            item_opts = _resolve_outtmpl_unique(url, item_opts, known_names)
            item_opts, final_path_ref = _collect_final_path(item_opts)
            item_opts['progress_hooks'] = list(item_opts.get('progress_hooks') or []) + [
                self._make_hook(
                    f"{prefix} ({i+1}/{total})" if total > 1 else prefix,
                    idx=i, total=total)]

            self.root.after(0, lambda i=i, t=total: self.status_var.set(
                f"Download {i+1} von {t}..." if t > 1 else "Download läuft..."))

            try:
                with yt_dlp.YoutubeDL(item_opts) as ydl:
                    info = ydl.extract_info(url)
                    done.append(info.get('title', url))
                _rename_after_download(final_path_ref, known_names)
            except Exception as e:
                if silent_errors:
                    skipped.append(url)
                    self.root.after(0, lambda u=url, err=str(e): self.status_var.set(
                        f"Übersprungen: {u[:60]}…"))
                    continue
                keep_going = [True]
                ev = threading.Event()
                def _ask(err=str(e), u=url):
                    keep_going[0] = messagebox.askyesno(
                        "Fehler",
                        f"Fehler bei:\n{u}\n\n{err}\n\nWeiter mit restlichen URLs?")
                    ev.set()
                self.root.after(0, _ask)
                ev.wait(30)
                if not keep_going[0]:
                    break

        self._set_download_active(False)

        if done:
            n   = len(done)
            cancelled_hint = "  (abgebrochen)" if self._cancel_flag else ""
            msg = f"✅ {n} Datei(en) heruntergeladen{cancelled_hint}"
            if skipped:
                msg += f"\n⚠ {len(skipped)} übersprungen (gelöscht/privat/Fehler)"
            if n == 1:
                msg += f"\n\n{done[0]}"
            self.root.after(0, lambda: (
                self.set_status("Download abgeschlossen!" if not self._cancel_flag
                                else "Download abgebrochen."),
                self._reset_progress(),
                messagebox.showinfo("Erfolg", msg),
                self._open_folder_if_wanted(dest)))
        else:
            self.root.after(0, lambda: (
                self.set_status("Kein Download abgeschlossen."),
                self._reset_progress()))

    def _resolve_and_run(self, urls: list, mode: str, bitrate: str, prefix: str):
        """
        Wird aus den Schnell-Download-Methoden aufgerufen.
        Löst URLs auf (Playlist-Dialog wenn nötig) und startet _run_urls.
        """
        self.root.after(0, lambda: self.set_status("URLs werden geprüft...", True))
        resolved = []

        if len(urls) > 1:
            result = self._request_multiurl_popup(urls, mode, bitrate)
            if result is None:
                self.root.after(0, lambda: self.set_status("Abgebrochen."))
                self._reset_progress()
                return
            urls    = result['urls']
            mode    = result['mode']
            bitrate = result['bitrate']
            prefix  = MODES_DICT.get(mode, prefix)

        # Bereits geladene Playlist direkt nutzen – aber NUR wenn die URL
        # tatsächlich zur gespeicherten Playlist gehört (list_id muss übereinstimmen)
        # oder eine reine Playlist-URL ohne Video-ID ist.
        if (len(urls) == 1
                and self._pending_playlist
                and self._pending_playlist.get('entries')):
            pending  = self._pending_playlist
            p        = _parse_yt_url(urls[0])
            stored_list_id = pending.get('list_id')

            url_belongs_to_playlist = (
                # URL hat list= und passt zur gespeicherten Playlist
                (p['list_id'] is not None and p['list_id'] == stored_list_id)
                # oder reine Playlist-URL (kein video_id, list_id passt)
                or (p['is_playlist'] and p['list_id'] == stored_list_id)
            )

            if url_belongs_to_playlist:
                entries  = pending['entries']
                pl_title = pending.get('title', urls[0])

                if p['index'] is not None:
                    # Konkreter Index → nur dieses eine Video
                    single_url = _resolve_entry_from_playlist(entries, p) or urls[0]
                    self.root.after(0, lambda idx=p['index']: self.set_status(
                        f"Lade Video {idx} aus Playlist...", True))
                    self._run_urls([single_url], mode, bitrate, prefix, silent_errors=True)
                else:
                    # Playlist ohne Index → alle downloadbaren
                    downloadable = [e for e in entries if not _is_unavailable_entry(e)]
                    if downloadable:
                        resolved = [_entry_url(e) for e in downloadable]
                        n_total  = len(entries)
                        n_dl     = len(downloadable)
                        self.root.after(0, lambda n=n_dl, t=pl_title, tot=n_total: self.set_status(
                            f"Playlist '{t}': {n}/{tot} downloadbare Einträge werden geladen...", True))
                        self._run_urls(resolved, mode, bitrate, prefix, silent_errors=True)
                    else:
                        self.root.after(0, lambda: self.set_status("Keine downloadbaren Einträge in der Playlist."))
                return
            # URL gehört nicht zur gespeicherten Playlist → normal weiterverarbeiten

        for url in urls:
            p_url = _parse_yt_url(url)

            if p_url['is_video_in_playlist']:
                pl_entries = []
                try:
                    opts_pl = self._base_opts()
                    opts_pl['extract_flat'] = True
                    opts_pl['noplaylist']   = False
                    playlist_url = f"https://www.youtube.com/playlist?list={p_url['list_id']}"
                    with yt_dlp.YoutubeDL(opts_pl) as ydl:
                        pl_info = ydl.extract_info(playlist_url, download=False)
                    if pl_info:
                        pl_entries = _deduplicate_entries(list(pl_info.get('entries', [])))
                        if pl_entries and not self._pending_playlist:
                            self._pending_playlist = {
                                'entries': pl_entries,
                                'title':   pl_info.get('title', ''),
                                'list_id': p_url['list_id'],
                            }
                except Exception:
                    pass

                resolved.append(_resolve_entry_from_playlist(pl_entries, p_url) or url)
                continue

            opts = self._base_opts()
            opts['extract_flat'] = True
            opts['noplaylist'] = 'watch?v=' in url or 'youtu.be/' in url
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as e:
                ev = threading.Event()
                self.root.after(0, lambda e=e, u=url: (
                    messagebox.showerror("Fehler", f"URL nicht abrufbar:\n{u}\n\n{e}"),
                    ev.set()))
                ev.wait(15)
                return

            if info.get('_type') == 'playlist':
                entries  = _deduplicate_entries(list(info.get('entries', [])))
                pl_title = info.get('title', url)
                if not entries:
                    continue
                # Schnell-Download: direkt alle downloadbaren, kein Dialog
                downloadable = [e for e in entries if not _is_unavailable_entry(e)]
                self.root.after(0, lambda n=len(downloadable), t=pl_title: self.set_status(
                    f"Playlist '{t}': {n} downloadbare Einträge werden geladen...", True))
                for e in downloadable:
                    resolved.append(_entry_url(e))
            else:
                resolved.append(url)

        if not resolved:
            self.root.after(0, lambda: self.set_status("Keine URLs zum Herunterladen."))
            return

        self._run_urls(resolved, mode, bitrate, prefix, silent_errors=True)

    # ═════════════════════════════════════════════════════════════════════════
    #  Schnell-Download-Methoden
    # ═════════════════════════════════════════════════════════════════════════

    def quick_audio_mp3(self):
        def t():
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning("Fehler", "Keine URL eingegeben!")
                return
            self._resolve_and_run(urls, 'audio_mp3', '0', "🎵 Audio (MP3) lädt...")
        Thread(target=t, daemon=True).start()

    def quick_audio_opus(self):
        def t():
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning("Fehler", "Keine URL eingegeben!")
                return
            self._resolve_and_run(urls, 'audio_opus', '0', "🎙 Audio (Opus) lädt...")
        Thread(target=t, daemon=True).start()

    def quick_video_mp4(self):
        def t():
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning("Fehler", "Keine URL eingegeben!")
                return
            self._resolve_and_run(urls, 'video_mp4', '192', "🎬 Video (MP4) lädt...")
        Thread(target=t, daemon=True).start()

    def quick_video_best(self):
        def t():
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning("Fehler", "Keine URL eingegeben!")
                return
            self._resolve_and_run(urls, 'video_best', '192', "⭐ Video Max lädt...")
        Thread(target=t, daemon=True).start()

    # Kompatibilitäts-Aliase
    def download_audio(self):      self.quick_audio_mp3()
    def download_audio_opus(self): self.quick_audio_opus()
    def download_video(self):      self.quick_video_mp4()
    def download_video_best(self):  self.quick_video_best()

    # ═════════════════════════════════════════════════════════════════════════
    #  Erweiterter Custom-Download (Einzelvideo-Auswahl)
    # ═════════════════════════════════════════════════════════════════════════

    def download_custom(self):
        def t():
            urls  = self._get_urls()
            v_lbl = self.clicked_stream_video.get()
            a_lbl = self.clicked_stream_audio.get()

            if not urls:
                messagebox.showwarning("Fehler", "Keine URL eingegeben!")
                return

            no_v = v_lbl in _SKIP_LABELS
            no_a = a_lbl in _SKIP_LABELS

            if no_v and no_a:
                messagebox.showwarning("Fehler",
                    "Bitte zuerst eine Einzel-URL analysieren und Stream wählen!")
                return

            vfmt = afmt = None
            vext = 'mp4'
            if not no_v:
                for f in self._video_formats:
                    if f['label'] == v_lbl:
                        vfmt = f['format_id']; vext = f['ext']; break
            if not no_a:
                for f in self._audio_formats:
                    if f['label'] == a_lbl:
                        afmt = f['format_id']; break

            fmt_str = (f"{vfmt}+{afmt}" if vfmt and afmt
                       else vfmt if vfmt else afmt)
            dest = (self.video_path_var.get() if vfmt
                    else self.audio_path_var.get())
            self._ensure_dir(dest)

            opts = self._base_opts()
            opts.update({
                'format': fmt_str,
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })
            if vfmt:
                opts['merge_output_format'] = (
                    'mp4' if self.video_to_mp4_var.get() else vext)
            if not vfmt and self.audio_to_mp3_var.get():
                bitrate = self.mp3_bitrate_var.get()
                pps = opts.get('postprocessors', [])
                opts['postprocessors'] = [{
                    'key':              'FFmpegExtractAudio',
                    'preferredcodec':   'mp3',
                    'preferredquality': bitrate,
                }] + [p for p in pps if p.get('key') != 'FFmpegExtractAudio']

            self.root.after(0, lambda: self.set_status("Download läuft...", True))

            known_names_custom = _scan_existing_stems(dest)
            self._cancel_flag = False
            self._pause_event.set()
            self._set_download_active(True)

            total = len(urls)
            done  = []
            for i, url in enumerate(urls):
                if self._check_pause_cancel():
                    break
                item_opts = dict(opts)

                # Playlist-Index auflösen falls nötig
                p_url = _parse_yt_url(url)
                if p_url['is_video_in_playlist']:
                    pl_entries = []
                    pending = self._pending_playlist
                    if pending and pending.get('list_id') == p_url['list_id']:
                        pl_entries = pending.get('entries', [])
                    if not pl_entries:
                        try:
                            opts_pl = self._base_opts()
                            opts_pl['extract_flat'] = True
                            opts_pl['noplaylist']   = False
                            playlist_url = (f"https://www.youtube.com/playlist"
                                            f"?list={p_url['list_id']}")
                            with yt_dlp.YoutubeDL(opts_pl) as ydl:
                                pl_info = ydl.extract_info(playlist_url, download=False)
                            if pl_info:
                                pl_entries = _deduplicate_entries(
                                    list(pl_info.get('entries', [])))
                        except Exception:
                            pass
                    url = _resolve_entry_from_playlist(pl_entries, p_url) or url

                if 'watch?v=' in url or 'youtu.be/' in url:
                    item_opts['noplaylist'] = True

                item_opts = _resolve_outtmpl_unique(url, item_opts, known_names_custom)
                item_opts, final_path_ref = _collect_final_path(item_opts)
                item_opts['progress_hooks'] = list(item_opts.get('progress_hooks') or []) + [
                    self._make_hook("📥 Lädt...", i, total)]
                self.root.after(0, lambda i=i, t=total: self.status_var.set(
                    f"Download {i+1}/{t}..." if t > 1 else "Download läuft..."))
                try:
                    with yt_dlp.YoutubeDL(item_opts) as ydl:
                        info = ydl.extract_info(url)
                        done.append(info.get('title', url))
                    _rename_after_download(final_path_ref, known_names_custom)
                except Exception as e:
                    messagebox.showerror("Fehler", f"Fehler:\n{e}")
            self._set_download_active(False)

            if done:
                n   = len(done)
                msg = f"✅ {n} Datei(en) heruntergeladen"
                if n == 1:
                    msg += f"\n\n{done[0]}"
                self.root.after(0, lambda: (
                    self.set_status("Download abgeschlossen!"),
                    self._reset_progress(),
                    messagebox.showinfo("Erfolg", msg),
                    self._open_folder_if_wanted(dest)))

        Thread(target=t, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()
