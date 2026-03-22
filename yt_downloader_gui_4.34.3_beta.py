# -*- coding: utf-8 -*-

__version__ = '4.34.3 beta'

"""
YouTube Downloader GUI

Eine benutzerfreundliche grafische Oberfläche zum Herunterladen von Audio und Video
aus YouTube-Links mit modernem Design und verbessertem Workflow.

License: MIT
"""
# pip install mutagen yt-dlp[default] 

# mutagen for opus files (just only write thumpnail into file)
# empfohlen: node installieren für die login cokies, um nicht als bot verdächtigt zu werden.

import os
import re
import threading
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
#  Konfigurationsdatei  (yt_d_config.txt  –  neben der .py-Datei)
# ═════════════════════════════════════════════════════════════════════════════

_CONFIG_FILE = path.join(path.dirname(path.abspath(__file__)), 'yt_d_config.txt')

# Schlüssel → (Typ, Standardwert)
# Typen: 'str' | 'bool' | 'int'
_CONFIG_SCHEMA: dict[str, tuple[str, object]] = {
    'audio_path':         ('str',  ''),
    'video_path':         ('str',  ''),
    'audio_to_mp3':       ('bool', True),
    'audio_format':       ('str',  'mp3'),
    'video_to_mp4':       ('bool', True),
    'video_format':       ('str',  'mp4'),
    'mp3_bitrate':        ('str',  '320'),
    'open_folder':        ('bool', False),
    'write_tags':         ('bool', True),
    'write_thumbnail':    ('bool', True),
    'cookies_browser':    ('str',  ''),
    'playlist_mode':      ('str',  'audio_mp3'),
    'playlist_bitrate':   ('str',  '0'),
}


def _config_load() -> dict:
    """
    Liest yt_d_config.txt und gibt ein Dict mit allen Einstellungen zurück.
    Fehlende Schlüssel werden mit dem Standardwert aus _CONFIG_SCHEMA aufgefüllt.
    Zeilen mit '#' am Anfang werden ignoriert.
    Format pro Zeile:  schlüssel = wert
    """
    result = {k: v for k, (_, v) in _CONFIG_SCHEMA.items()}
    if not path.exists(_CONFIG_FILE):
        return result
    try:
        with open(_CONFIG_FILE, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, raw = line.partition('=')
                key = key.strip()
                raw = raw.strip()
                if key not in _CONFIG_SCHEMA:
                    continue
                typ, _ = _CONFIG_SCHEMA[key]
                if typ == 'bool':
                    result[key] = raw.lower() in ('1', 'true', 'yes', 'ja')
                elif typ == 'int':
                    try:
                        result[key] = int(raw)
                    except ValueError:
                        pass
                else:
                    result[key] = raw
    except OSError:
        pass
    return result


def _config_save(cfg: dict):
    """
    Schreibt alle Einstellungen aus *cfg* in yt_d_config.txt.
    Unbekannte Schlüssel werden ignoriert.
    """
    lines = [
        '# YouTube Downloader – Konfigurationsdatei',
        '# Automatisch generiert. Manuelle Änderungen sind erlaubt.',
        '# Format:  schlüssel = wert',
        '# Bool-Werte: true / false',
        '',
    ]
    for key, (typ, default) in _CONFIG_SCHEMA.items():
        val = cfg.get(key, default)
        if typ == 'bool':
            val = 'true' if val else 'false'
        lines.append(f'{key} = {val}')
    try:
        with open(_CONFIG_FILE, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
    except OSError:
        pass


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
    Hängt einen postprocessor_hook UND einen progress_hook ein, die den
    finalen Dateipfad nach Abschluss aller Postprozessoren in eine
    1-Element-Liste schreiben.
    Gibt (neue_opts, result_liste) zurück – result[0] ist nach dem Download befüllt.

    Hinweis: yt-dlp setzt 'filepath' im info_dict nicht bei jedem PP-Schritt
    zuverlässig (z.B. fehlt er nach FFmpegMetadata). Daher wird der zuletzt
    bekannte Pfad beibehalten (niemals mit leerem Wert überschrieben) und
    zusätzlich per progress_hook aus dem Download-Status ermittelt.
    """
    result: list = [None]

    def _pp_hook(d):
        if d.get('status') != 'finished':
            return
        fp = (d.get('info_dict') or {}).get('filepath', '')
        if fp:
            result[0] = fp

    def _prog_hook(d):
        # Beim Abschluss des Downloads den Pfad aus dem Dateinamen sichern,
        # bevor Postprozessoren ihn ggf. umbenennen (Extension-Wechsel).
        # Dient als initiale Basis; _pp_hook überschreibt mit dem echten Endpfad.
        if d.get('status') == 'finished':
            fp = d.get('filename') or d.get('tmpfilename') or ''
            if fp and not result[0]:
                result[0] = fp

    new_opts = dict(opts)
    pph = list(new_opts.get('postprocessor_hooks') or [])
    pph.append(_pp_hook)
    new_opts['postprocessor_hooks'] = pph
    # progress_hook als Fallback einhängen (wird VOR den PP-Hooks ausgelöst)
    prh = list(new_opts.get('progress_hooks') or [])
    prh.insert(0, _prog_hook)
    new_opts['progress_hooks'] = prh
    new_opts['no_overwrites'] = False
    return new_opts, result


def _resolve_outtmpl_unique(url: str, base_opts: dict, known_names: set) -> dict:
    """
    Holt den Videotitel vorab (download=False), berechnet daraus einen
    eindeutigen Ziel-Dateinamen und setzt diesen als fixen outtmpl.
    """
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





def _embed_thumbnail_as_jpeg(media_fp: str, ffmpeg_exe: str):
    """
    Sucht die zum media_fp gehörende Thumbnail-Datei (.webp/.jpg/.png),
    konvertiert sie zu einem kleinen JPEG (500px, q:v 4 ≈ 30–50 KB)
    und bettet sie ein:
      • .opus      → OggOpus  (metadata_block_picture / FLAC Picture) via mutagen
      • .mp3       → ID3 APIC-Tag via mutagen
      • .mp4/.mkv  → FFmpeg remux mit eingebettetem Cover (kein mutagen nötig)
    Thumbnail-Temp-Datei wird danach gelöscht.
    """
    import subprocess as _sp
    if not media_fp or not os.path.isfile(media_fp):
        return
    ext_lower = os.path.splitext(media_fp)[1].lower()
    stem = os.path.splitext(media_fp)[0]
    th_src = ''
    for ext2 in ('.webp', '.jpg', '.jpeg', '.png'):
        cand = stem + ext2
        if os.path.isfile(cand):
            th_src = cand
            break
    if not th_src:
        return
    th_jpg = stem + '_cover.jpg'
    try:
        _sp.run(
            [ffmpeg_exe, '-y', '-i', th_src,
             '-vf', 'scale=500:-1', '-q:v', '4', th_jpg],
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, check=True)
    except Exception:
        return
    try:
        with open(th_jpg, 'rb') as fh:
            jpg_data = fh.read()

        if ext_lower == '.opus':
            from mutagen.oggopus import OggOpus
            from mutagen.flac import Picture
            import base64
            pic = Picture()
            pic.type = 3
            pic.mime = 'image/jpeg'
            pic.desc = 'Cover'
            pic.data = jpg_data
            audio = OggOpus(media_fp)
            audio['metadata_block_picture'] = [
                base64.b64encode(pic.write()).decode('ascii')
            ]
            audio.save()

        elif ext_lower == '.mp3':
            from mutagen.id3 import ID3, APIC, error as ID3Error
            try:
                tags = ID3(media_fp)
            except ID3Error:
                tags = ID3()
            tags.delall('APIC')
            tags.add(APIC(
                encoding=3,        # UTF-8
                mime='image/jpeg',
                type=3,            # Cover (front)
                desc='Cover',
                data=jpg_data,
            ))
            tags.save(media_fp, v2_version=3)

        elif ext_lower in ('.mp4', '.mkv', '.webm'):
            # FFmpeg remux: Original + Cover → Temp-Datei → Original ersetzen
            tmp_out = stem + '_covtmp' + ext_lower
            try:
                if ext_lower == '.mkv':
                    # MKV/Matroska kennt kein 'attached_pic' – Cover als
                    # Datei-Attachment einbetten (wird von VLC, mpv, Kodi erkannt).
                    cmd = [ffmpeg_exe, '-y',
                           '-i', media_fp,
                           '-c', 'copy',
                           '-attach', th_jpg,
                           '-metadata:s:t', 'mimetype=image/jpeg',
                           '-metadata:s:t', 'filename=cover.jpg',
                           tmp_out]
                else:
                    # MP4 / WebM: Cover als Videostream mit attached_pic einbetten
                    cmd = [ffmpeg_exe, '-y',
                           '-i', media_fp, '-i', th_jpg,
                           '-map', '0', '-map', '1',
                           '-c', 'copy',
                           '-disposition:v:1', 'attached_pic',
                           tmp_out]
                _sp.run(cmd, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, check=True)
                os.replace(tmp_out, media_fp)
            except Exception:
                if os.path.isfile(tmp_out):
                    try:
                        os.remove(tmp_out)
                    except OSError:
                        pass

    except Exception:
        pass
    finally:
        for tmp in (th_jpg, th_src):
            if tmp and os.path.isfile(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

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
    raw_id   = _extract_video_id(url)
    video_id = raw_id if ('watch?v=' in url or 'youtu.be/' in url) else None
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


def _is_channel_url(url: str) -> bool:
    """
    Gibt True zurück wenn die URL auf einen YouTube-Kanal zeigt
    (/@handle, /channel/ID, /c/Name, /user/Name) – aber KEINE Video- oder Playlist-URL.
    """
    p = _parse_yt_url(url)
    if p['video_id'] or p['list_id']:
        return False
    low = url.lower()
    return (
        '/@' in low
        or '/channel/' in low
        or '/c/' in low
        or '/user/' in low
    )


def _channel_name_from_url(url: str) -> str:
    """
    Extrahiert den Kanal-Handle/-Namen aus einer Channel-URL als sicheren Ordnernamen.
    Beispiele:
      https://www.youtube.com/@Germaninexile  →  'Germaninexile'
      https://www.youtube.com/channel/UCxxxx  →  'UCxxxx'
      https://www.youtube.com/c/MyChannel     →  'MyChannel'
    """
    for marker in ('/@', '/channel/', '/c/', '/user/'):
        if marker in url:
            part = url.split(marker, 1)[1]
            # Fragment/Query abschneiden
            part = part.split('?')[0].split('#')[0].split('/')[0].strip()
            # Ungültige Zeichen für Ordnernamen entfernen
            safe = re.sub(r'[\\/*?:"<>|]', '_', part).strip()
            return safe or 'channel'
    return 'channel'


def _flatten_channel_entries(info: dict) -> list:
    """
    Sammelt rekursiv alle Video-Einträge aus einer Channel-Info-Struktur.
    yt-dlp liefert bei /@handle eine verschachtelte Struktur:
      Channel → [Tab-Playlist, ...] → [Sub-Playlist, ...] → [Video, ...]
    Diese Funktion gibt eine flache Liste aller Blatt-Einträge (Videos) zurück.
    """
    entries = list(info.get('entries') or [])
    if not entries:
        return []

    # Prüfe ob Einträge selbst wieder Playlists sind
    result = []
    for e in entries:
        if e is None:
            continue
        sub = e.get('entries')
        if sub is not None:
            # Rekursiv einsteigen
            result.extend(_flatten_channel_entries(e))
        else:
            # Blatt-Eintrag (Video)
            result.append(e)
    return result


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
#  _BaseSelectionDialog  –  gemeinsame Basis für Playlist- und MultiURL-Dialog
# ═════════════════════════════════════════════════════════════════════════════
class _BaseSelectionDialog(Toplevel):
    """
    Abstrakte Basis: scrollbare Auswahlliste + Download-Einstellungen + Footer.
    Subklassen implementieren _build_header() und _populate_rows(inner).
    """

    def __init__(self, parent, default_mode: str, default_bitrate: str,
                 title: str, geometry: tuple, minsize: tuple,
                 use_max_bitrate: bool = False):
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)
        self.grab_set()
        self.result      = None
        self.last_checked: set = set()

        sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
        w, h, min_w, min_h = *geometry, *minsize
        w = min(w, sw - 60)
        h = min(h, sh - 80)
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.minsize(min_w, min_h)

        self._vars: list[BooleanVar] = []
        self._mode_var        = StringVar(value=default_mode)
        self._bitrate_var     = StringVar(value=default_bitrate)
        self._use_max_bitrate = BooleanVar(value=use_max_bitrate)
        self._search_var      = StringVar()      # wird in _build() mit trace versehen
        self._filter_count_var = StringVar()     # wird in _build() als Label-Quelle gesetzt
        self._list_canvas     = None   # wird in _build() gesetzt
        self._row_frames: list = []
        self._build()

    # ── Subklassen überschreiben diese zwei Methoden ──────────────────────────

    def _build_header(self, head: ttk.Frame):
        """Kopfzeile mit Titel und Auswahl-Buttons befüllen."""
        raise NotImplementedError

    def _populate_rows(self, inner: ttk.Frame):
        """Eintragszeilen in den scrollbaren Innenbereich schreiben."""
        raise NotImplementedError

    # ── Gemeinsamer Aufbau ────────────────────────────────────────────────────

    def _build(self):
        _bg = ttk.Style().lookup('TFrame', 'background') or '#d9d9d9'
        self.configure(background=_bg)

        # Header
        head = ttk.Frame(self, padding=(12, 8))
        head.pack(fill='x')
        self._build_header(head)
        ttk.Separator(self).pack(fill='x')

        # ── Suchfilter ────────────────────────────────────────────────────────
        sf = ttk.Frame(self, padding=(8, 4))
        sf.pack(fill='x')
        ttk.Label(sf, text="🔍 Suche:", font=('Segoe UI', 9)).pack(side='left')
        search_entry = ttk.Entry(sf, textvariable=self._search_var,
                                 font=('Segoe UI', 9), width=40)
        search_entry.pack(side='left', padx=(4, 6), fill='x', expand=True)
        ttk.Button(sf, text="✕", width=3,
                   command=lambda: self._search_var.set('')).pack(side='left')
        ttk.Label(sf, textvariable=self._filter_count_var,
                  font=('Segoe UI', 9), foreground='#555').pack(side='left', padx=(8, 0))
        self._search_var.trace_add('write', lambda *_: self._filter_rows())
        ttk.Separator(self).pack(fill='x')

        # Scrollbare Liste
        lf = ttk.Frame(self)
        lf.pack(fill='both', expand=True, padx=8, pady=4)
        self._list_canvas = Canvas(lf, borderwidth=0, highlightthickness=0, background=_bg)
        canvas = self._list_canvas
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
        self._populate_rows(inner)

        ttk.Separator(self).pack(fill='x', pady=(4, 0))

        # Download-Einstellungen
        cfg = ttk.LabelFrame(
            self,
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
        br_row = ttk.Frame(cfg)
        br_row.pack(fill='x', pady=(4, 0))
        self._br_label = ttk.Label(br_row, text="MP3-Bitrate:", width=10)
        self._br_label.pack(side='left')
        self._br_combo = ttk.Combobox(
            br_row, textvariable=self._bitrate_var,
            values=["320", "256", "192", "160", "128", "96", "64"],
            width=7, state='readonly', style='Bitrate.TCombobox')
        self._br_combo.pack(side='left', padx=(0, 2))
        ttk.Label(br_row, text="kbps",
                  font=('Segoe UI', 9), foreground='#666').pack(side='left')
        ttk.Radiobutton(br_row, text="Feste Bitrate",
                        variable=self._use_max_bitrate, value=False,
                        command=self._toggle_bitrate).pack(side='left', padx=(14, 2))
        ttk.Radiobutton(br_row, text="Max. Bitrate (automatisch je Datei)",
                        variable=self._use_max_bitrate, value=True,
                        command=self._toggle_bitrate).pack(side='left', padx=(2, 0))
        self._toggle_bitrate()

        ttk.Separator(self).pack(fill='x')

        # Footer
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

    # ── Shared-Logik ──────────────────────────────────────────────────────────

    def _get_row_texts(self) -> list[str]:
        """
        Gibt eine Liste von Suchbegriffen (je Zeile einen String) zurück.
        Subklassen können dies überschreiben; Standard: leerer String für jede Zeile.
        """
        return ['' for _ in self._row_frames]

    def _filter_rows(self):
        """Blendet Zeilen ein/aus anhand des Suchtexts; aktualisiert Zähler-Label."""
        term = self._search_var.get().lower().strip()
        texts = self._get_row_texts()
        visible = 0
        total   = len(self._row_frames)
        for row, text in zip(self._row_frames, texts):
            show = (not term) or (term in text.lower())
            if show:
                row.pack(fill='x', padx=4, pady=1)
                visible += 1
            else:
                row.pack_forget()
        if term:
            self._filter_count_var.set(f"{visible}/{total} sichtbar")
        else:
            self._filter_count_var.set('')
        # Scrollregion aktualisieren
        try:
            self._list_canvas.update_idletasks()
            self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox('all'))
        except Exception:
            pass

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

    def _cancel(self):
        self.result = None
        self.destroy()

    def _ok(self):
        raise NotImplementedError


# ═════════════════════════════════════════════════════════════════════════════
#  PlaylistDialog
# ═════════════════════════════════════════════════════════════════════════════
class PlaylistDialog(_BaseSelectionDialog):
    """
    Zeigt alle (bereits deduplizierten) Einträge einer Playlist.
    Ergebnis: dict {'indices': [...], 'mode': str, 'bitrate': str} oder None.

    checked_indices   – Set[int]: welche Einträge beim letzten Öffnen angehakt waren.
                        None bedeutet: Standardverhalten (alle downloadbaren an).
    downloaded_stems  – dict[str, str]: stem → 'audio'|'video', Dateien im Zielordner.
                        Passende Einträge werden hellgrün markiert + Symbol angezeigt.
    """

    # Hintergrundfarben
    _BG_NORMAL     = ''          # leer = Theme-Standard
    _BG_DOWNLOADED = 'white'     #'#c8f0c8'   # hellgrün
    _BG_UNAVAIL    = ''          # bleibt Standard, Schrift rot

    def __init__(self, parent, entries: list,
                 default_mode: str = "audio_mp3",
                 default_bitrate: str = "320",
                 title_prefix: str = "Playlist",
                 checked_indices: set | None = None,
                 downloaded_stems: set | None = None):
        self._entries          = entries
        self._checked_indices  = checked_indices   # None = erster Aufruf
        self._downloaded_stems: dict = downloaded_stems or {}  # stem → 'audio'|'video'
        self.last_checked: set = set()             # wird beim Schließen gefüllt
        self._row_frames: list = []                # für Hintergrund-Updates
        super().__init__(
            parent,
            default_mode=default_mode,
            default_bitrate=default_bitrate,
            title=f"{title_prefix} – Auswahl & Download-Einstellungen",
            geometry=(980, 720),
            minsize=(700, 380),
            use_max_bitrate=True,
        )

    def _build_header(self, head: ttk.Frame):
        n_dl = sum(1 for e in self._entries if not _is_unavailable_entry(e))
        n_done = sum(
            1 for e in self._entries
            if self._is_downloaded(e) and not _is_unavailable_entry(e)
        )

        # Basis-Text
        base_text = f"📋  {len(self._entries)} Einträge"
        ttk.Label(
            head,
            text=base_text,
            font=('Segoe UI', 11, 'bold')
        ).pack(side='left')

        if n_done:
            ttk.Label(
                head,
                text=f"  •  ✅ {n_done} bereits vorhanden",
                foreground="blue",
                font=('Segoe UI', 11, 'bold')
            ).pack(side='left')

        # Buttons rechts
        sel_frame = ttk.Frame(head)
        sel_frame.pack(side='right')

        for lbl2, cmd, w in [
            ("Alle",                self._all,                  8),
            ("Keine",               self._none,                 8),
            ("Umkehren",            self._invert,               9),
            ("✅ Nur Downloadbare", self._select_downloadable, 18),
        ]:
            ttk.Button(
                sel_frame,
                text=lbl2,
                width=w,
                command=cmd
            ).pack(side='left', padx=2)

    def _is_downloaded(self, entry: dict) -> set:
        """
        Gibt ein Set zurück: {'audio'}, {'video'}, {'audio','video'} oder set().
        Prüft ob passende Dateien in Audio- UND/ODER Video-Ordner existieren.
        """
        if not self._downloaded_stems:
            return set()
        title = (entry.get('title') or '').strip()
        if not title:
            return set()
        safe = re.sub(r'[\\/*?:"<>|]', '_', title).strip()
        found: set = set()
        for stem, kinds in self._downloaded_stems.items():
            if stem == safe or stem.startswith(safe + ' ('):
                found |= kinds
        return found

    def _populate_rows(self, inner: ttk.Frame):
        _bg_dialog = ttk.Style().lookup('TFrame', 'background') or '#d9d9d9'
        self._row_frames.clear()

        for i, entry in enumerate(self._entries):
            title  = entry.get('title') or f'Eintrag {i+1}'
            is_bad = _is_unavailable_entry(entry)
            is_done = self._is_downloaded(entry) if not is_bad else set()

            # Startzustand der Checkbox:
            # – erster Aufruf (checked_indices is None):
            #     nicht verfügbar → aus; bereits heruntergeladen → aus; sonst → an
            # – Folgeaufruf: gespeicherten Zustand exakt wiederherstellen
            if self._checked_indices is None:
                initial = (not is_bad) and (not is_done)
            else:
                initial = (i in self._checked_indices)

            var = BooleanVar(value=initial)
            self._vars.append(var)

            # Zeilenhintergrund
            bg = self._BG_DOWNLOADED if is_done else _bg_dialog

            row = Frame(inner, background=bg)
            row.pack(fill='x', padx=4, pady=1)
            self._row_frames.append(row)

            cb = ttk.Checkbutton(row, variable=var)
            cb.pack(side='left')

            Label(row, text=f"{i+1:>3}.",
                  width=4, font=('Segoe UI', 9),
                  foreground='#888', background=bg,
                  anchor='e').pack(side='left')

            dur   = entry.get('duration') or 0
            dur_s = f"  [{int(dur//60)}:{int(dur%60):02d}]" if dur else ""

            if is_bad:
                text_color = 'red' # '#CC0000'
                icon   = ''
                suffix = '  ⚠ nicht verfügbar'
            elif is_done:
                text_color = 'blue' # '#1a6b1a'
                # Beide, nur Audio, nur Video
                if 'audio' in is_done and 'video' in is_done:
                    icon = '  🎵🎬'
                elif 'audio' in is_done:
                    icon = '  🎵'
                else:
                    icon = '  🎬'
                suffix = ''
            else:
                text_color = 'black'
                icon   = ''
                suffix = ''

            Label(
                row,
                text=f"{title}{dur_s}{icon}{suffix}",
                font=('Segoe UI', 9), anchor='w',
                foreground=text_color, background=bg,
            ).pack(side='left', fill='x', expand=True, padx=(4, 0))

    def _select_downloadable(self):
        for var, entry in zip(self._vars, self._entries):
            var.set(not _is_unavailable_entry(entry))

    def _get_row_texts(self) -> list[str]:
        """Gibt Titel aller Einträge zurück – für den Suchfilter."""
        return [e.get('title') or f'Eintrag {i+1}'
                for i, e in enumerate(self._entries)]

    def _collect_checked(self) -> set:
        return {i for i, v in enumerate(self._vars) if v.get()}

    def _cancel(self):
        self.last_checked = self._collect_checked()
        self.result = None
        self.destroy()

    def _ok(self):
        sel = [i for i, v in enumerate(self._vars) if v.get()]
        self.last_checked = set(sel)
        if not sel:
            messagebox.showwarning("Hinweis",
                "Bitte mindestens einen Eintrag auswählen.", parent=self)
            return
        bitrate = '0' if self._use_max_bitrate.get() else self._bitrate_var.get()
        self.result = {'indices': sel, 'mode': self._mode_var.get(),
                       'bitrate': bitrate}
        self.destroy()


# ═════════════════════════════════════════════════════════════════════════════
#  MultiURLDialog
# ═════════════════════════════════════════════════════════════════════════════
class MultiURLDialog(_BaseSelectionDialog):
    """
    Zeigt alle eingegebenen URLs in einer Vorschau-Liste.
    Ergebnis: dict {'urls': [...], 'mode': str, 'bitrate': str} oder None.
    """

    def __init__(self, parent, urls: list,
                 default_mode: str = "audio_mp3",
                 default_bitrate: str = "320"):
        self._urls = urls
        super().__init__(
            parent,
            default_mode=default_mode,
            default_bitrate=default_bitrate,
            title="Multi-URL – Auswahl & Download-Einstellungen",
            geometry=(860, 640),
            minsize=(560, 360),
            use_max_bitrate=False,
        )

    def _build_header(self, head: ttk.Frame):
        ttk.Label(head, text=f"🔗  {len(self._urls)} URLs erkannt",
                  font=('Segoe UI', 11, 'bold')).pack(side='left')
        sel_frame = ttk.Frame(head)
        sel_frame.pack(side='right')
        for lbl, cmd in [("Alle", self._all), ("Keine", self._none),
                         ("Umkehren", self._invert)]:
            ttk.Button(sel_frame, text=lbl, width=8,
                       command=cmd).pack(side='left', padx=2)

    def _populate_rows(self, inner: ttk.Frame):
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

    def _ok(self):
        sel = [self._urls[i] for i, v in enumerate(self._vars) if v.get()]
        if not sel:
            messagebox.showwarning("Hinweis",
                "Bitte mindestens eine URL auswählen.", parent=self)
            return
        self.result = {'urls': sel, 'mode': self._mode_var.get(),
                       'bitrate': self._bitrate_var.get()}
        self.destroy()

    def _get_row_texts(self) -> list[str]:
        """Gibt URLs zurück – für den Suchfilter im MultiURL-Dialog."""
        return list(self._urls)


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
        self.audio_format_var  = StringVar(value="mp3")   # "original" | "opus" | "mp3"
        self.video_to_mp4_var  = BooleanVar(value=True)
        self.video_format_var  = StringVar(value="mp4")   # "original" | "mp4" | "mkv"
        self.mp3_bitrate_var   = StringVar(value="320")
        self.quick_bitrate_var = StringVar(value="320")
        self.open_folder_var      = BooleanVar(value=False)
        self.write_tags_var       = BooleanVar(value=True)
        self.write_thumbnail_var  = BooleanVar(value=True)
        self.cookies_browser_var  = StringVar(value="")   # leer = keine Cookies

        self.clicked_stream_video = StringVar()
        self.clicked_stream_audio = StringVar()
        self.ignore_video_var = BooleanVar(value=False)
        self.ignore_audio_var = BooleanVar(value=False)

        self._video_formats: list = []
        self._audio_formats: list = []
        self._progress_pct = DoubleVar(value=0.0)

        # Popup-Synchronisation (GUI-Thread ↔ Download-Thread)
        self._pending_playlist: dict | None = None
        self._playlist_event:  threading.Event | None = None
        self._playlist_result: dict | None = None
        self._playlist_cancel: bool = False

        # Pause / Abbrechen
        self._pause_event:  threading.Event = threading.Event()
        self._pause_event.set()
        self._cancel_flag:  bool = False
        self._download_active: bool = False

        parent_dir = path.dirname(path.abspath(__file__))
        self.audio_path_var.set(path.join(parent_dir, "Downloads", "audio"))
        self.video_path_var.set(path.join(parent_dir, "Downloads", "video"))

        # ── Konfiguration laden ───────────────────────────────────────────────
        self._cfg = _config_load()
        self._apply_config(self._cfg)

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
    def _apply_config(self, cfg: dict):
        """Überträgt geladene Konfigurationswerte auf die Tkinter-Variablen."""
        parent_dir = path.dirname(path.abspath(__file__))
        default_audio = path.join(parent_dir, "Downloads", "audio")
        default_video = path.join(parent_dir, "Downloads", "video")

        self.audio_path_var.set(cfg.get('audio_path') or default_audio)
        self.video_path_var.set(cfg.get('video_path') or default_video)
        self.audio_to_mp3_var.set(cfg.get('audio_to_mp3', True))
        # Migration: alte Werte 'm4a' und 'webm' → 'original'
        raw_afmt = cfg.get('audio_format', 'mp3')
        if raw_afmt in ('m4a', 'webm'):
            raw_afmt = 'original'
        self.audio_format_var.set(raw_afmt)
        self.video_to_mp4_var.set(cfg.get('video_to_mp4', True))
        self.video_format_var.set(cfg.get('video_format', 'mp4'))
        self.mp3_bitrate_var.set(cfg.get('mp3_bitrate', '320'))
        self.open_folder_var.set(cfg.get('open_folder', False))
        self.write_tags_var.set(cfg.get('write_tags', True))
        self.write_thumbnail_var.set(cfg.get('write_thumbnail', True))
        self.cookies_browser_var.set(cfg.get('cookies_browser', ''))

    def _collect_config(self) -> dict:
        """Liest alle aktuellen Einstellungen aus den Tkinter-Variablen."""
        return {
            'audio_path':      self.audio_path_var.get(),
            'video_path':      self.video_path_var.get(),
            'audio_to_mp3':    self.audio_to_mp3_var.get(),
            'audio_format':    self.audio_format_var.get(),
            'video_to_mp4':    self.video_to_mp4_var.get(),
            'video_format':    self.video_format_var.get(),
            'mp3_bitrate':     self.mp3_bitrate_var.get(),
            'open_folder':     self.open_folder_var.get(),
            'write_tags':      self.write_tags_var.get(),
            'write_thumbnail': self.write_thumbnail_var.get(),
            'cookies_browser': self.cookies_browser_var.get(),
        }

    def _save_config(self, *_):
        """Speichert alle aktuellen Einstellungen sofort in yt_d_config.txt."""
        _config_save(self._collect_config())

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
        self._sec_qd = {
            'expanded': False, 'frame': self._qd_frame,
            'grid_row': r, 'lbl_var': self._qd_toggle_lbl,
            'icon_text': "⚡ Schnell-Download", 'pady': (0, 8),
        }
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
        self._sec_pl = {
            'expanded': False, 'frame': self._pl_frame,
            'grid_row': r, 'lbl_var': self._pl_toggle_lbl,
            'icon_text': "📋 Playlist-Verwaltung", 'pady': (0, 8),
        }
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
        self._sec_adv = {
            'expanded': False, 'frame': self._adv_frame,
            'grid_row': r, 'lbl_var': self._adv_toggle_lbl,
            'icon_text': "Erweiterte Optionen (Einzelvideo)", 'pady': (0, 10),
        }
        r += 1

        # ── Bereich: Video Stream ─────────────────────────────────────────────
        video_lf = ttk.LabelFrame(self._adv_frame, text="Video Stream", padding=(8, 4))
        video_lf.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        video_lf.columnconfigure(0, weight=1)

        video_top = ttk.Frame(video_lf)
        video_top.grid(row=0, column=0, sticky='ew')
        video_top.columnconfigure(0, weight=1)

        self.video_combo = ttk.Combobox(video_top,
                                        textvariable=self.clicked_stream_video,
                                        width=68, state='readonly')
        self.video_combo.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.video_combo['values'] = [_PLACEHOLDER_ANALYSE]
        self.video_combo.current(0)

        video_opts = ttk.Frame(video_lf)
        video_opts.grid(row=1, column=0, sticky='w', pady=(4, 0))
        ttk.Label(video_opts, text="Video-Format:", style='Info.TLabel').pack(side='left', padx=(0, 6))
        for lbl, val in [("Original", "original"), ("MP4", "mp4"), ("MKV", "mkv")]:
            ttk.Radiobutton(video_opts, text=lbl, variable=self.video_format_var,
                            value=val).pack(side='left', padx=(0, 4))
        ttk.Checkbutton(video_opts, text="Video ignorieren",
                        variable=self.ignore_video_var).pack(side='left', padx=(16, 0))

        # ── Bereich: Audio Stream ─────────────────────────────────────────────
        audio_lf = ttk.LabelFrame(self._adv_frame, text="Audio Stream", padding=(8, 4))
        audio_lf.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        audio_lf.columnconfigure(0, weight=1)

        self.audio_combo = ttk.Combobox(audio_lf,
                                        textvariable=self.clicked_stream_audio,
                                        width=68, state='readonly')
        self.audio_combo.grid(row=0, column=0, sticky='ew', pady=(0, 4))
        self.audio_combo['values'] = [_PLACEHOLDER_ANALYSE]
        self.audio_combo.current(0)

        audio_opts = ttk.Frame(audio_lf)
        audio_opts.grid(row=1, column=0, sticky='w')

        ttk.Label(audio_opts, text="Audio-Format:", style='Info.TLabel').pack(side='left', padx=(0, 6))
        for lbl, val in [("Original", "original"), ("Opus", "opus"), ("MP3", "mp3")]:
            ttk.Radiobutton(audio_opts, text=lbl, variable=self.audio_format_var,
                            value=val, command=self._toggle_bitrate_state).pack(side='left', padx=(0, 4))

        # Bitrate-Frame – nur sichtbar wenn MP3 aktiv, erscheint inline rechts
        self._bitrate_frame = ttk.Frame(audio_opts)
        brow = self._bitrate_frame
        ttk.Label(brow, text="  Bitrate:", style='Info.TLabel').pack(side='left')
        self.bitrate_combo = ttk.Combobox(
            brow, textvariable=self.mp3_bitrate_var,
            values=["320", "256", "192", "160", "128", "96", "64"],
            width=6, state='readonly', style='Bitrate.TCombobox')
        self.bitrate_combo.pack(side='left', padx=(4, 0))
        ttk.Label(brow, text="kbps", style='Info.TLabel').pack(side='left', padx=(2, 0))

        ttk.Separator(audio_lf, orient='horizontal').grid(row=2, column=0, sticky='ew', pady=(6, 4))
        ignore_audio_row = ttk.Frame(audio_lf)
        ignore_audio_row.grid(row=3, column=0, sticky='w')
        ttk.Checkbutton(ignore_audio_row, text="Audio ignorieren",
                        variable=self.ignore_audio_var).pack(side='left')

        ttk.Button(self._adv_frame, text="📥 Mit Auswahl herunterladen",
                   command=self.download_custom,
                   style='Action.TButton').grid(
            row=2, column=0, columnspan=2, pady=(4, 0))

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
        self._sec_so = {
            'expanded': False, 'frame': self._so_frame,
            'grid_row': r, 'lbl_var': self._so_toggle_lbl,
            'icon_text': "💾 Speicherorte & Optionen", 'pady': (0, 10),
        }
        r += 1

        def _path_row(grid_row: int, label: str, path_var: StringVar, kind: str):
            ttk.Label(self._so_frame, text=label).grid(
                row=grid_row, column=0, sticky='w', pady=3)
            ttk.Entry(self._so_frame, textvariable=path_var,
                      width=50).grid(row=grid_row, column=1, padx=(8, 4), sticky='ew')
            btn_frame = ttk.Frame(self._so_frame)
            btn_frame.grid(row=grid_row, column=2, sticky='w')
            ttk.Button(btn_frame, text="📁 Durchsuchen",
                       command=lambda k=kind: self.browse_folder(k),
                       style='Secondary.TButton').pack(side='left')
            ttk.Button(btn_frame, text="🗂 Öffnen",
                       command=lambda v=path_var: self._open_folder_direct(v.get()),
                       style='Secondary.TButton').pack(side='left', padx=(4, 0))

        _path_row(0, "Audio:", self.audio_path_var, 'audio')
        _path_row(1, "Video:", self.video_path_var, 'video')

        opt_row = ttk.Frame(self._so_frame)
        opt_row.grid(row=2, column=0, columnspan=3, sticky='w', pady=(8, 2))
        ttk.Checkbutton(opt_row, text="📂 Zielordner nach Download öffnen",
                        variable=self.open_folder_var).pack(side='left', padx=(0, 20))
        ttk.Checkbutton(opt_row, text="🏷 Metadaten-Tags in Datei schreiben",
                        variable=self.write_tags_var).pack(side='left', padx=(0, 20))
        ttk.Checkbutton(opt_row, text="🖼 Thumbnail einbetten",
                        variable=self.write_thumbnail_var).pack(side='left')

        # ── Cookies-Zeile ─────────────────────────────────────────────────────
        ck_row = ttk.Frame(self._so_frame)
        ck_row.grid(row=4, column=0, columnspan=3, sticky='w', pady=(6, 2))
        ttk.Label(ck_row, text="🍪 Cookies aus Browser:",
                  style='Info.TLabel').pack(side='left', padx=(0, 6))
        _BROWSERS = ["", "chrome", "firefox", "edge", "brave", "opera", "safari"]
        ck_combo = ttk.Combobox(ck_row, textvariable=self.cookies_browser_var,
                                values=_BROWSERS, width=10, state='readonly')
        ck_combo.pack(side='left')
        ttk.Label(ck_row,
                  text="  ← Browser wählen um YouTube-Anmeldung zu nutzen (löst 429-Fehler)",
                  style='Info.TLabel').pack(side='left')

        self.root.after(0, lambda: self._toggle_quickdownload(force_open=True))
        self.root.after(0, self._toggle_bitrate_state)

        # ── Einstellungen automatisch speichern ───────────────────────────────
        for var in (
            self.audio_path_var, self.video_path_var,
            self.audio_to_mp3_var, self.audio_format_var,
            self.video_to_mp4_var, self.video_format_var, self.mp3_bitrate_var,
            self.open_folder_var, self.write_tags_var,
            self.write_thumbnail_var, self.cookies_browser_var,
        ):
            var.trace_add('write', self._save_config)

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
        if self.audio_format_var.get() == 'mp3':
            self._bitrate_frame.pack(side='left', padx=(4, 0))
        else:
            self._bitrate_frame.pack_forget()

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

    # ── Generischer Klapp-Mechanismus ─────────────────────────────────────────
    # Jede Sektion ist ein Dict:
    #   {'expanded': bool, 'frame': widget, 'grid_row': int,
    #    'lbl_var': StringVar, 'icon_text': str, 'pady': tuple}
    # Die vier _toggle_*-Wrapper bleiben als schmale Aliase erhalten,
    # damit bestehende call-sites unverändert funktionieren.

    def _toggle_section(self, sec: dict, force_open: bool = False):
        if force_open and sec['expanded']:
            return
        sec['expanded'] = force_open or (not sec['expanded'])
        arrow = "▼" if sec['expanded'] else "▶"
        action = "zum Einklappen" if sec['expanded'] else "zum Aufklappen"
        sec['lbl_var'].set(f"{arrow}  {sec['icon_text']}  –  {action} klicken")
        if sec['expanded']:
            sec['frame'].grid(row=sec['grid_row'], column=0,
                              sticky='ew', pady=sec['pady'], in_=self._mf)
        else:
            sec['frame'].grid_remove()

    def _toggle_advanced(self, force_open: bool = False):
        self._toggle_section(self._sec_adv, force_open)

    def _toggle_playlist(self, force_open: bool = False):
        self._toggle_section(self._sec_pl, force_open)

    def _toggle_saveopts(self, force_open: bool = False):
        self._toggle_section(self._sec_so, force_open)

    def _toggle_quickdownload(self, force_open: bool = False):
        self._toggle_section(self._sec_qd, force_open)

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

    def _open_folder_direct(self, folder: str):
        """Öffnet den angegebenen Ordner sofort im Explorer (erstellt ihn wenn nötig)."""
        if not folder:
            messagebox.showwarning("Kein Pfad", "Bitte zuerst einen Zielordner eingeben.")
            return
        self._ensure_dir(folder)
        Popen(f'explorer "{os.path.normpath(folder)}"')

    # ═════════════════════════════════════════════════════════════════════════
    #  yt-dlp Basis-Optionen
    # ═════════════════════════════════════════════════════════════════════════

    def _base_opts(self) -> dict:
        """
        Minimale yt-dlp-Optionen – nur ffmpeg-Pfad und Cookies.
        Wird bei Analyse UND Download verwendet.
        Kein writethumbnail, keine Postprocessoren – damit die Analyse
        keine Bilddateien auf die Platte schreibt.
        """
        import shutil
        # ffmpeg-Pfad über yt-dlp ermitteln (kein imageio_ffmpeg nötig).
        # FFmpegPostProcessor kennt alle yt-dlp-eigenen Such-Pfade (inkl. Bundle).
        try:
            from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
            _tmp_ydl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True})
            _ffpp = FFmpegPostProcessor(_tmp_ydl)
            _ffmpeg_exe = _ffpp.executable or shutil.which('ffmpeg') or 'ffmpeg'
        except Exception:
            _ffmpeg_exe = shutil.which('ffmpeg') or 'ffmpeg'
        opts = {
            'ffmpeg_location': _ffmpeg_exe,
            'quiet':       False,
            'no_warnings': False,
        }
        # Node.js als JS-Runtime registrieren (yt-dlp sucht sonst nur nach Deno).
        # Das interne Format ist ein Dict: {'runtime_name': {optionaler 'path': ...}}
        # Unterstützte Keys: 'deno', 'node', 'bun', 'quickjs'
        node_path = shutil.which('node')
        if node_path:
            opts['js_runtimes'] = {'node': {'path': node_path}}
        browser = self.cookies_browser_var.get().strip()
        if browser:
            # cookiesfrombrowser erwartet ein Tuple: (browser, profile, keyring, container)
            # Fehlende Felder mit None auffüllen damit yt-dlp nicht abstürzt
            opts['cookiesfrombrowser'] = (browser, None, None, None)
        return opts

    def _download_opts(self, mode: str = '') -> dict:
        """
        Erweiterte yt-dlp-Optionen für echte Downloads:
        _base_opts() + Metadaten-Tags + Thumbnail einbetten (falls aktiviert).
        Nur hier wird writethumbnail gesetzt – niemals bei der Analyse.

        mode: 'audio_mp3' | 'audio_opus' | 'video_mp4' | 'video_best' | ''
              Bei Video-Modi wird EmbedThumbnail weggelassen.

        Opus: yt-dlp würde das Thumbnail zu PNG konvertieren (→ 800 KB!),
              weil es PNG in den OGG-Tags erwartet.
              Ein postprocessor_hook konvertiert stattdessen das heruntergeladene
              .webp/.jpg zu JPEG – EmbedThumbnail bettet dann JPEG ein.
        """
        opts = self._base_opts()

        # ffprobe neben ffmpeg suchen
        ffmpeg_exe = opts.get('ffmpeg_location', '')
        if ffmpeg_exe:
            ffprobe_candidate = os.path.join(
                os.path.dirname(ffmpeg_exe),
                'ffprobe' + ('.exe' if os.name == 'nt' else ''))
            if os.path.isfile(ffprobe_candidate):
                opts['ffprobe_location'] = ffprobe_candidate

        is_video = mode.startswith('video')
        pps = []
        if self.write_tags_var.get():
            pps.append({
                'key':          'FFmpegMetadata',
                'add_metadata': True,
                'add_chapters': False,
            })
        if self.write_thumbnail_var.get():
            opts['writethumbnail'] = True
            if not is_video:
                if mode == 'audio_mp3':
                    # ── MP3: EmbedThumbnail NICHT an yt-dlp delegieren ──────
                    # yt-dlp konvertiert .webp → .png (unkomprimiert, ~500-800 KB!)
                    # und bettet dieses riesige PNG als ID3-APIC-Tag ein.
                    # Stattdessen übernimmt _embed_thumbnail_as_jpeg den Job:
                    # .webp/.jpg → JPEG 500px (≈ 30–50 KB) → ID3 via mutagen.
                    opts['convert_thumbnails'] = False
                    opts['_mp3_embed_ffmpeg']  = opts.get('ffmpeg_location') or 'ffmpeg'
                    # EmbedThumbnail bewusst NICHT in pps einfügen

                elif mode == 'audio_opus':
                    # ── Opus: EmbedThumbnail NICHT verwenden ────────────────
                    # Das Thumbnail wird NACH dem Download direkt eingebettet
                    # (via _embed_thumbnail_as_jpeg), nicht per Hook.
                    # yt-dlp würde es sonst als unkomprimiertes PNG einbetten (~800KB).
                    opts['convert_thumbnails'] = False
                    opts['_opus_embed_ffmpeg'] = opts.get('ffmpeg_location') or 'ffmpeg'
                    # EmbedThumbnail bewusst NICHT in pps einfügen

                else:
                    # Andere Audio-Formate: Standard yt-dlp EmbedThumbnail
                    pps.append({'key': 'EmbedThumbnail'})

            else:
                # ── Video: gleiche Logik wie Audio ──────────────────────────
                # _embed_thumbnail_as_jpeg übernimmt den Job nach dem Download:
                # .webp/.jpg → JPEG 500px → FFmpeg remux (kein yt-dlp EmbedThumbnail).
                opts['convert_thumbnails'] = False
                opts['_video_embed_ffmpeg'] = opts.get('ffmpeg_location') or 'ffmpeg'
                # EmbedThumbnail bewusst NICHT in pps einfügen
        if pps:
            opts['postprocessors'] = pps
        return opts

    def _ensure_dir(self, d):
        if not path.exists(d):
            makedirs(d)

    # ═════════════════════════════════════════════════════════════════════════
    #  Fortschritts-Hook
    # ═════════════════════════════════════════════════════════════════════════

    def _make_hook(self, prefix="Lade...", idx=0, total=1):
        def hook(d):
            # ── Abbrechen: sofort Exception werfen → yt-dlp bricht ab ──────────
            if self._cancel_flag:
                raise Exception("Download abgebrochen.")

            # ── Pause: blockieren bis Weiter gedrückt wird ──────────────────────
            if not self._pause_event.is_set():
                self._pause_event.wait()
                # Nach dem Warten erneut auf Cancel prüfen
                if self._cancel_flag:
                    raise Exception("Download abgebrochen.")

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
        pending = self._pending_playlist or {}
        dlg = PlaylistDialog(self.root, entries,
                             default_mode=default_mode,
                             default_bitrate=default_bitrate,
                             title_prefix=title_prefix,
                             checked_indices=pending.get('checked'),
                             downloaded_stems=pending.get('downloaded_stems'))
        self.root.wait_window(dlg)
        self._playlist_result = dlg.result
        self._playlist_cancel = (dlg.result is None)
        # Checkbox-Zustand merken (auch bei Abbrechen)
        if self._pending_playlist is not None:
            self._pending_playlist['checked'] = dlg.last_checked
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

            # Bereits heruntergeladene Dateien ermitteln (Audio + Video-Ordner scannen)
            # dl_stems: {stem: set('audio'|'video')} – ein Stem kann in beiden Ordnern liegen
            dl_stems: dict = {}
            for stem in _scan_existing_stems(self.audio_path_var.get()):
                dl_stems.setdefault(stem, set()).add('audio')
            for stem in _scan_existing_stems(self.video_path_var.get()):
                dl_stems.setdefault(stem, set()).add('video')
            if self._pending_playlist is None:
                self._pending_playlist = {'entries': entries, 'title': pl_title}
            self._pending_playlist['downloaded_stems'] = dl_stems

            result = self._request_playlist_popup(
                entries,
                default_mode    = self._cfg.get('playlist_mode', 'audio_mp3'),
                default_bitrate = self._cfg.get('playlist_bitrate', self.quick_bitrate_var.get()),
                title_prefix    = f"Playlist: {pl_title}")

            if result is None:
                self._update_pl_status(
                    f"⚠ Bearbeitung abgebrochen – {len(entries)} Einträge verfügbar")
                self.root.after(0, lambda: self.set_status("Abgebrochen."))
                return

            # Modus & Bitrate für nächste Öffnung merken
            self._cfg['playlist_mode']    = result['mode']
            self._cfg['playlist_bitrate'] = result['bitrate']
            _config_save(self._cfg)

            self._pending_playlist = {
                'url':              self._get_urls()[0] if self._get_urls() else '',
                'entries':          entries,
                'title':            pl_title,
                'result':           result,
                'checked':          self._pending_playlist.get('checked') if self._pending_playlist else None,
                'downloaded_stems': self._pending_playlist.get('downloaded_stems', {}) if self._pending_playlist else {},
                'list_id':          self._pending_playlist.get('list_id') if self._pending_playlist else None,
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
                    default_mode    = self._cfg.get('playlist_mode', 'audio_mp3'),
                    default_bitrate = self._cfg.get('playlist_bitrate', '0'),
                    title_prefix    = f"Playlist: {pl_title}")
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
        opts = self._download_opts(mode)

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
            pps = opts.get('postprocessors', [])
            # Immer zu .opus re-encodieren (OGG-Container, verlustfrei mit quality 0)
            # → saubere Extension, Metadaten & Thumbnails werden unterstützt
            opus_pp = {'key': 'FFmpegExtractAudio',
                       'preferredcodec': 'opus', 'preferredquality': '0'}
            # EmbedThumbnail ebenfalls entfernen – unser Hook übernimmt das
            opts['postprocessors'] = [opus_pp] + [
                p for p in pps
                if p.get('key') not in ('FFmpegExtractAudio', 'EmbedThumbnail')]
            opts['convert_thumbnails'] = False

        elif mode == 'video_mp4':
            dest = self.video_path_var.get()
            opts.update({
                'format': ('bestvideo[ext=mp4]+bestaudio[ext=m4a]'
                           '/bestvideo[ext=mp4]+bestaudio'
                           '/bestvideo+bestaudio'
                           '/best'),
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })
            vfmt = self.video_format_var.get()
            if vfmt == 'original':
                # Kein merge_output_format – yt-dlp wählt Extension selbst
                pass
            elif vfmt == 'mkv':
                opts['merge_output_format'] = 'mkv'
            else:  # 'mp4' (Standard)
                opts['merge_output_format'] = 'mp4'

        else:  # video_best
            dest = self.video_path_var.get()
            opts.update({
                'format': 'bestvideo+bestaudio/best',
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
                # Stets MKV: unterstützt alle Codecs (auch webm/vp9/av1/opus)
                # und erlaubt Metadaten + Thumbnail-Embedding
                'merge_output_format': 'mkv',
            })

        return opts, dest

    def _maybe_embed_thumbnail(self, opts: dict, fp: str):
        """
        Bettet das Thumbnail als JPEG ein – einheitliche Hilfsmethode,
        die in _run_urls, dem Channel-Loop und download_custom genutzt wird.
        """
        if not fp:
            return
        low = fp.lower()
        if low.endswith('.opus'):
            _ff = opts.get('_opus_embed_ffmpeg', '')
        elif low.endswith('.mp3'):
            _ff = opts.get('_mp3_embed_ffmpeg', '')
        else:
            _ff = opts.get('_video_embed_ffmpeg', '')
        if _ff:
            _embed_thumbnail_as_jpeg(fp, _ff)

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
                self._maybe_embed_thumbnail(base_opts, final_path_ref[0])
            except Exception as e:
                if self._cancel_flag:
                    break
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

            url_belongs_to_playlist = (p['list_id'] == stored_list_id)

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

            # ── Channel-URL (/@handle, /channel/, /c/, /user/) ────────────────
            # yt-dlp liefert hier eine verschachtelte Playlist-Struktur
            # (Channel → Tabs → Sub-Playlists → Videos).  Würden wir die URL
            # direkt an yt-dlp übergeben, lädt es alle Videos in einem
            # einzigen ydl.extract_info()-Aufruf – unsere Hooks für
            # Thumbnail-Embedding greifen dann NICHT.
            # Lösung: Einträge vorab flach auflösen, jeden Video-URL einzeln
            # durch _run_urls schicken (wo Hooks zuverlässig feuern).
            # Außerdem wird ein Unterordner <Kanalname> angelegt.
            if _is_channel_url(url):
                ch_name = _channel_name_from_url(url)
                self.root.after(0, lambda n=ch_name: self.set_status(
                    f"Kanal '{n}' wird analysiert...", True))
                try:
                    opts_ch = self._base_opts()
                    opts_ch['extract_flat'] = True
                    opts_ch['noplaylist']   = False
                    with yt_dlp.YoutubeDL(opts_ch) as ydl:
                        ch_info = ydl.extract_info(url, download=False)
                except Exception as e:
                    ev = threading.Event()
                    self.root.after(0, lambda e=e, u=url: (
                        messagebox.showerror("Fehler", f"Kanal nicht abrufbar:\n{u}\n\n{e}"),
                        ev.set()))
                    ev.wait(15)
                    return

                flat = _deduplicate_entries(_flatten_channel_entries(ch_info))
                downloadable = [e for e in flat if not _is_unavailable_entry(e)]
                if not downloadable:
                    self.root.after(0, lambda n=ch_name: self.set_status(
                        f"Kanal '{n}': Keine downloadbaren Einträge gefunden."))
                    continue

                ch_urls = [_entry_url(e) for e in downloadable]
                n_dl = len(ch_urls)
                self.root.after(0, lambda n=n_dl, nm=ch_name: self.set_status(
                    f"Kanal '{nm}': {n} Videos werden geladen...", True))

                # Unterordner anlegen: <Basispfad>/<Kanalname>
                base_opts_ch, base_dest = self._build_opts_for_mode(mode, bitrate)
                ch_dest = os.path.join(base_dest, ch_name)
                self._ensure_dir(ch_dest)

                # outtmpl auf Unterordner umbiegen
                old_outtmpl = base_opts_ch.get('outtmpl', '')
                if old_outtmpl:
                    base_opts_ch['outtmpl'] = os.path.join(
                        ch_dest, os.path.basename(old_outtmpl))
                else:
                    base_opts_ch['outtmpl'] = os.path.join(ch_dest, '%(title)s.%(ext)s')

                # Direkt herunterladen (nicht nochmal _run_urls mit mode-Erkennung,
                # sondern den bereits angepassten opts-Block verwenden)
                self._cancel_flag = False
                self._pause_event.set()
                self._set_download_active(True)
                known = _scan_existing_stems(ch_dest)
                done_ch = []
                total_ch = len(ch_urls)
                for i, v_url in enumerate(ch_urls):
                    if self._check_pause_cancel():
                        break
                    item_opts = dict(base_opts_ch)
                    item_opts['noplaylist'] = True
                    item_opts = _resolve_outtmpl_unique(v_url, item_opts, known)
                    item_opts, fp_ref = _collect_final_path(item_opts)
                    item_opts['progress_hooks'] = list(item_opts.get('progress_hooks') or []) + [
                        self._make_hook(f"{prefix} ({i+1}/{total_ch})", idx=i, total=total_ch)]
                    self.root.after(0, lambda i=i, t=total_ch: self.status_var.set(
                        f"Download {i+1}/{t}..."))
                    try:
                        with yt_dlp.YoutubeDL(item_opts) as ydl:
                            info_dl = ydl.extract_info(v_url)
                            done_ch.append(info_dl.get('title', v_url))
                        _rename_after_download(fp_ref, known)
                        self._maybe_embed_thumbnail(base_opts_ch, fp_ref[0])
                    except Exception as e:
                        if self._cancel_flag:
                            break
                        self.root.after(0, lambda u=v_url, err=str(e): self.status_var.set(
                            f"Übersprungen: {u[:50]}…"))
                        continue
                self._set_download_active(False)
                n = len(done_ch)
                if n:
                    msg = f"✅ {n} Datei(en) heruntergeladen\nOrdner: {ch_dest}"
                    self.root.after(0, lambda: (
                        self.set_status("Download abgeschlossen!"),
                        self._reset_progress(),
                        messagebox.showinfo("Erfolg", msg),
                        self._open_folder_if_wanted(ch_dest)))
                else:
                    self.root.after(0, lambda: (
                        self.set_status("Kein Download abgeschlossen."),
                        self._reset_progress()))
                return

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

    def _quick_download(self, mode: str, bitrate: str, label: str):
        """Gemeinsamer Thread-Starter für alle Schnell-Download-Schaltflächen."""
        def t():
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning("Fehler", "Keine URL eingegeben!")
                return
            self._resolve_and_run(urls, mode, bitrate, label)
        Thread(target=t, daemon=True).start()

    def quick_audio_mp3(self):   self._quick_download('audio_mp3',  '0',   "🎵 Audio (MP3) lädt...")
    def quick_audio_opus(self):  self._quick_download('audio_opus', '0',   "🎙 Audio (Opus) lädt...")
    def quick_video_mp4(self):   self._quick_download('video_mp4',  '192', "🎬 Video (MP4) lädt...")
    def quick_video_best(self):  self._quick_download('video_best', '192', "⭐ Video Max lädt...")

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

            no_v = v_lbl in _SKIP_LABELS or self.ignore_video_var.get()
            no_a = a_lbl in _SKIP_LABELS or self.ignore_audio_var.get()

            if no_v and no_a:
                messagebox.showwarning("Fehler",
                    "Bitte zuerst eine Einzel-URL analysieren und Stream wählen!\n"
                    "(Oder: Video/Audio-ignorieren-Checkbox deaktivieren.)")
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

            # Modus für _download_opts bestimmen (Video oder Audio)
            _custom_mode = 'video_mp4' if vfmt else 'audio_mp3'
            opts = self._download_opts(_custom_mode)
            opts.update({
                'format': fmt_str,
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })
            if vfmt:
                # Video-Format-Auswahl: Original | MP4 | MKV
                vid_fmt_sel = self.video_format_var.get()
                if vid_fmt_sel == 'mkv':
                    opts['merge_output_format'] = 'mkv'
                elif vid_fmt_sel == 'mp4':
                    opts['merge_output_format'] = 'mp4'
                # 'original' → kein merge_output_format setzen
            if not vfmt:
                audio_fmt = self.audio_format_var.get()
                bitrate   = self.mp3_bitrate_var.get()
                pps = opts.get('postprocessors', [])
                if audio_fmt == 'mp3':
                    opts['postprocessors'] = [{
                        'key':              'FFmpegExtractAudio',
                        'preferredcodec':   'mp3',
                        'preferredquality': bitrate,
                    }] + [p for p in pps if p.get('key') != 'FFmpegExtractAudio']
                elif audio_fmt == 'opus':
                    opts['postprocessors'] = [{
                        'key':              'FFmpegExtractAudio',
                        'preferredcodec':   'opus',
                        'preferredquality': '0',
                    }] + [p for p in pps
                          if p.get('key') not in ('FFmpegExtractAudio', 'EmbedThumbnail')]
                    opts['convert_thumbnails'] = False
                    opts['_opus_embed_ffmpeg'] = opts.get('ffmpeg_location') or 'ffmpeg'
                else:
                    # 'original' → rohe Originaldatei, kein Konvertierungs-Postprozessor.
                    # EmbedThumbnail entfernen (unbekanntes Format – sicherheitshalber).
                    opts['postprocessors'] = [
                        p for p in pps
                        if p.get('key') not in ('FFmpegExtractAudio', 'EmbedThumbnail')
                    ]
                    opts.pop('writethumbnail', None)
                    opts.pop('_mp3_embed_ffmpeg', None)
                    opts.pop('_opus_embed_ffmpeg', None)

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
                    self._maybe_embed_thumbnail(item_opts, final_path_ref[0])
                except Exception as e:
                    if self._cancel_flag:
                        break
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
