# -*- coding: utf-8 -*-

__version__ = '5.2.0'

"""
YouTube Downloader GUI  –  cross-platform (Windows / Linux / macOS)

A user-friendly graphical interface for downloading audio and video
from YouTube links, with a modern design and streamlined workflow.

UI languages: English (default), German and Farsi/Persian, switchable
live from the main window and persisted to yt_d_config.txt.

Author:  Waldemar Koch
Co-Author: E.S.
Updated: 2026 July 22
License: MIT

System requirements
────────────────────
Windows:
  pip install mutagen static-ffmpeg yt-dlp[default]
  (static_ffmpeg downloads FFmpeg automatically)

Linux (Debian/Ubuntu):
  sudo apt install -y ffmpeg python3-tk nodejs
  pip install "yt-dlp[default]" mutagen

macOS:
  brew install ffmpeg python-tk node
  pip install "yt-dlp[default]" mutagen

Node.js is optional but required by yt-dlp for certain YouTube pages.
"""

import os
import re
import shutil
import threading
import platform
import time
import yt_dlp
from tkinter import *
from tkinter import ttk, filedialog, messagebox
from threading import Thread
from os import path, makedirs
from subprocess import Popen
from urllib.parse import urlparse, parse_qs

# ─────────────────────────────────────────────────────────────────────────────
#  Platform detection
# ─────────────────────────────────────────────────────────────────────────────
IS_WINDOWS = platform.system() == 'Windows'
IS_LINUX   = platform.system() == 'Linux'
IS_MAC     = platform.system() == 'Darwin'

# Set the window title via os.system() only on Windows;
# on Linux/macOS, Tkinter sets the window title directly.
if IS_WINDOWS:
    from os import system
    system(f'title YouTube Downloader - Version {__version__}')


# ─────────────────────────────────────────────────────────────────────────────
#  Provide FFmpeg + ffprobe
# ─────────────────────────────────────────────────────────────────────────────
def _setup_ffmpeg():
    """
    Makes sure ffmpeg and ffprobe are available.

    Windows:  static_ffmpeg downloads a static binary on first use and
              caches it locally; afterwards shutil.which('ffmpeg') and
              shutil.which('ffprobe') are reliably populated on Windows.

    Linux/macOS:  ffmpeg must be installed system-wide (apt / brew).
                  If missing, a warning is printed to the console.
    """
    if IS_WINDOWS:
        try:
            import static_ffmpeg
            static_ffmpeg.add_paths()
        except ImportError:
            print('Warning: static_ffmpeg not installed – '
                  'ffmpeg must be on PATH manually.')
    else:
        if not shutil.which('ffmpeg'):
            print('\n' + '!' * 60)
            print('FFmpeg not found! Please install it:')
            if IS_LINUX:
                print('  sudo apt update && sudo apt install ffmpeg')
            elif IS_MAC:
                print('  brew install ffmpeg')
            print('!' * 60 + '\n')
        if not shutil.which('ffprobe'):
            print('Warning: ffprobe not found – '
                  'some features may be limited.')


_setup_ffmpeg()


# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────
# NOTE: the language-dependent placeholder strings that used to live here
# (analyse placeholder, playlist placeholder, no-video/no-audio labels) are
# now provided live via T('ph_analyse') / T('ph_playlist') / T('no_video') /
# T('no_audio') and the _skip_labels() helper, so they stay correct after a
# language switch instead of being frozen at import time.

# Markers for unavailable playlist entries (defined once, language-independent
# yt-dlp titles plus the localized variants actually seen in the wild)
_UNAVAIL_TITLES = {
    '[deleted video]', '[private video]', '[unavailable]',
    '[privates video]', '[gelöschtes video]',
}

# NOTE: (label, key) pairs for the mode radio buttons are provided live via
# _modes()/_modes_dict() (see i18n section below, next to _skip_labels()),
# not as a static constant here – so they stay correct after a language
# switch instead of being frozen in whatever language was active at import.


# ═════════════════════════════════════════════════════════════════════════════
#  i18n  –  Internationalization (English / German / Farsi)
# ═════════════════════════════════════════════════════════════════════════════
#  - LANG holds the currently active UI language code (see LANGUAGES below).
#  - Translations are organized BLOCK-WISE: one dict per language (_EN, _DE,
#    _FA, ...), each mapping the same semantic keys to that language's text.
#    _build_i18n() merges these blocks into I18N (key → {lang: text}), which
#    is what T() actually reads from.
#  - TO ADD A NEW LANGUAGE:
#      1. Copy an existing block (e.g. _EN) to a new dict, e.g. _ES, and
#         translate every value.
#      2. Add it to _LANG_BLOCKS below, e.g. 'es': _ES.
#      3. Add the code to LANGUAGES (controls order in the language switcher).
#      That's it – no need to touch any of the ~170 individual keys/lines
#      above one by one. _check_i18n_completeness() will print a warning
#      at startup if the new block is missing any keys (or has stray ones),
#      so incomplete translations are caught immediately instead of only
#      showing up later as English fallback text in the running app.
#  - T(key, **kwargs) returns the text for the active language and, if
#    keyword arguments are given, formats them into the template
#    (e.g. T('n_of_total_selected', n=3, total=10)).
#  - I18nRegistry keeps a list of static widgets (labels, buttons,
#    checkboxes, frame titles, ...) so their text can be refreshed
#    instantly, without restarting the app, whenever the language changes.
#    Dialogs and status/progress messages are built fresh every time they
#    are shown, so they simply call T() at creation time and always reflect
#    whichever language is active at that moment.
# ═════════════════════════════════════════════════════════════════════════════

# Language codes, in the order they appear in the language switcher.
# Adding a language = adding its code here (see "TO ADD A NEW LANGUAGE" above).
LANGUAGES: list[str] = ['en', 'de', 'fa']

LANG = {'code': 'en'}   # active language; 'en' is also the fallback/reference language


_EN: dict[str, str] = {
    # ── Window / general ────────────────────────────────────────────────────
    'window_title': 'YouTube Downloader v{v}  🎵 + 🎬',
    'lang_label': '🌐 Language:',
    # ── URL input ────────────────────────────────────────────────────────────
    'url_frame_title': 'URL(s)  –  one link per line  or  playlist URL',
    'url_hint': 'Playlist → use the Playlist section  |  Multiple URLs → the Multi-URL dialog appears automatically',
    'btn_paste': '📋 Paste',
    'btn_analyze': '🔍 Analyze',
    'btn_clear': '🗑 Clear',
    # ── Status / progress ───────────────────────────────────────────────────
    'lbl_status': 'Status:',
    'status_ready': 'Ready',
    'pause_btn': '⏸ Pause',
    'resume_btn': '▶ Resume',
    'cancel_btn': '✕ Cancel',
    'status_link_pasted': 'Link pasted.',
    'status_fields_cleared': 'Fields cleared.',
    'status_resuming': '▶ Resuming download...',
    'status_cancelling': '✕ Cancelling...',
    'status_paused': '⏸ Paused – click ▶ Resume to continue',
    'status_analyzing': 'Analyzing...',
    'status_analysis_done_vfa': 'Analysis done – {vc} video / {ac} audio streams',
    'status_analysis_done_pl': 'Analysis done – {vc}V/{ac}A streams{pl}',
    'status_analysis_done_pl_suffix': '  |  Playlist: {done}/{total} downloadable',
    'status_analysis_error': 'Analysis failed',
    'status_playlist_detected': 'Playlist detected – {done}/{total} downloadable',
    'status_cancelled': 'Cancelled.',
    'status_download_starting': 'Starting download: {n} file(s)...',
    'status_download_n_of_t': 'Download {i} of {t}...',
    'status_download_running': 'Download running...',
    'status_download_progress': 'Download {i}/{t}...',
    'status_download_done': 'Download complete!',
    'status_download_cancelled': 'Download cancelled.',
    'status_download_none': 'No download completed.',
    'status_skipped': 'Skipped: {u}…',
    'status_urls_checking': 'Checking URLs...',
    'status_video_from_playlist': 'Loading video {idx} from playlist...',
    'status_playlist_loading_n': "Playlist '{t}': loading {n}/{tot} downloadable entries...",
    'status_playlist_loading_dl': "Playlist '{t}': loading {n} downloadable entries...",
    'status_playlist_none_downloadable': 'No downloadable entries in the playlist.',
    'status_channel_analyzing': "Analyzing channel '{n}'...",
    'status_channel_none': "Channel '{n}': no downloadable entries found.",
    'status_channel_loading': "Channel '{nm}': loading {n} videos...",
    'status_playlist_loading': 'Loading playlist...',
    'status_playlist_ready_n': 'Playlist ready: {n} entries selected',
    'status_playlist_none_detected': 'No playlist detected.',
    'status_playlist_cached': "Playlist '{t}' – {n} entries (already loaded)",
    'status_playlist_with_n': "Playlist '{t}' – {n} entries",
    'status_load_error': 'Error loading',
    # ── Playlist status label (below Playlist section) ─────────────────────
    'pl_status_none': 'No playlist loaded.',
    'pl_status_loading_info': '⏳ Loading playlist information...',
    'pl_status_error': '❌ Error loading.',
    'pl_status_none_detected': '❌ No playlist detected.',
    'pl_status_empty': '❌ Playlist is empty.',
    'pl_status_choose': "✅ '{t}' – {n} entries. Please make a selection...",
    'pl_status_edit_cancelled': '⚠ Editing cancelled – {n} entries available',
    'pl_status_ready': "✅ '{t}': {n}/{total} entries, mode: {mode} → now click 'Download Playlist'",
    'pl_status_preparing': '⏳ Preparing...',
    'pl_status_downloading': '⬇ Download running...',
    'pl_title_prefix': 'Playlist: {t}',
    'pl_title_unknown': 'Unknown playlist',
    'pl_status_loaded': '📋 {t}  ({done}/{total} downloadable) – playlist loaded.',
    'pl_status_load_failed': 'Playlist could not be loaded.',
    'pl_title_bar': '📋 Playlist: {t}  ({done}/{total} downloadable)',
    'video_title_bar': '📹 {t}',
    'video_title_index_hint': '  (Index {idx})',
    'video_title_with_playlist': '  –  Playlist: {t}',
    # ── Collapsible section headers ─────────────────────────────────────────
    'sec_toggle_line': '{arrow}  {icon}  –  click to {action}',
    'action_expand': 'expand',
    'action_collapse': 'collapse',
    'sec_qd_title': '⚡ Quick Download',
    'sec_pl_title': '📋 Playlist Management',
    'sec_adv_title': '🛠 Advanced Options (Single Video)',
    'sec_so_title': '💾 Save Locations & Options',
    # ── Quick download section ──────────────────────────────────────────────
    'qd_btn_audio_mp3': '🎵 Audio\nMP3',
    'qd_btn_audio_opus': '🎵 Audio\nOpus',
    'qd_btn_video_mp4_m4a': '🎬 Video\nMP4+M4A',
    'qd_btn_video_mp4': '🎬 Video\nMP4',
    'qd_btn_video_best': '🎬 Video\nBest',
    'qd_loading_audio_mp3': '🎵 Audio (MP3) loading...',
    'qd_loading_audio_opus': '🎵 Audio (Opus) loading...',
    'qd_loading_video_mp4_m4a': '🎬 Video (MP4+M4A) loading...',
    'qd_loading_video_mp4': '🎬 Video (MP4) loading...',
    'qd_loading_video_best': '🎬 Video Max loading...',
    'hook_loading_generic': '📥 Loading...',
    'qd_info1': 'MP3/Opus: the maximum available source bitrate is used automatically.  MP4+M4A: original streams from the server (no re-encoding, AV1-free compatibility).',
    'qd_info2': 'With 1 URL or a playlist INDEX: downloads directly.\nWith a playlist URL (no INDEX): all downloadable entries download directly, no dialog.\nDeleted/private videos are skipped automatically.',
    # ── Playlist section ────────────────────────────────────────────────────
    'btn_pl_edit': '📋 Edit Playlist',
    'btn_pl_download': '▶ Download Playlist 📥',
    'pl_hint': "Tip: after analyzing, click 'Edit' right away – the playlist is already loaded. Your selection is kept until the download.",
    # ── Advanced options ─────────────────────────────────────────────────────
    'lf_video_stream': 'Video Stream',
    'lbl_video_format': 'Video format:',
    'radio_original': 'Original',
    'radio_mp4': 'MP4',
    'radio_mkv': 'MKV',
    'chk_ignore_video': 'Ignore video',
    'lf_audio_stream': 'Audio Stream',
    'lbl_audio_format': 'Audio format:',
    'radio_opus': 'Opus',
    'radio_mp3': 'MP3',
    'lbl_bitrate_inline': '  Bitrate:',
    'lbl_kbps': 'kbps',
    'chk_ignore_audio': 'Ignore audio',
    'btn_download_custom': '▶ Download with Selection 📥',
    # ── Save locations & options ─────────────────────────────────────────────
    'lbl_audio_path': 'Audio:',
    'lbl_video_path': 'Video:',
    'btn_browse': '📁 Browse',
    'btn_open': '🗂 Open',
    'chk_open_folder': '📂 Open destination folder after download',
    'chk_write_tags': '🏷 Write metadata tags to file',
    'chk_write_thumb': '🖼 Embed thumbnail',
    'lbl_cookies': '🍪 Cookies from browser:',
    'lbl_cookies_hint': '  ← select a browser to use your YouTube login (fixes 429 errors)',
    'browse_dialog_title': '{kind} – Destination Folder',
    # ── Dialog boxes (Playlist / Multi-URL) ─────────────────────────────────
    'dlg_playlist_title': '{prefix} – Selection & Download Settings',
    'dlg_multi_title': 'Multi-URL – Selection & Download Settings',
    'dlg_cfg_frame_title': 'Download settings (applies to all selected entries)',
    'lbl_mode': 'Mode:',
    'mode_audio_mp3':     '🎵 Audio (MP3)',
    'mode_audio_opus':    '🎵 Audio (Opus)',
    'mode_video_mp4_m4a': '🎬 Video (MP4+M4A)',
    'mode_video_mp4':     '🎬 Video (MP4)',
    'mode_video_best':    '🎬 Video (Best)',
    'lbl_mp3_bitrate': 'MP3 bitrate:',
    'lbl_opus_bitrate': 'Opus bitrate:',
    'radio_fixed_bitrate': 'Fixed bitrate',
    'radio_max_bitrate': 'Max. bitrate (automatic per file)',
    'btn_remember_selection': '📋✔ Remember Selection',
    'n_of_total_selected': '{n} of {total} selected',
    'sel_all': 'All',
    'sel_none': 'None',
    'sel_invert': 'Invert',
    'sel_only_downloadable': '✅ Downloadable Only',
    'pl_header_count': '📋  {n} entries',
    'pl_header_done': '  •  ✅ {n} already downloaded',
    'entry_default_title': 'Entry {i}',
    'entry_unavailable_suffix': '  ⚠ unavailable',
    'search_label': '🔍 Search:',
    'filter_visible': '{visible}/{total} visible',
    'multi_url_header': '🔗  {n} URLs detected',
    # ── Messagebox titles ────────────────────────────────────────────────────
    'title_error': 'Error',
    'title_success': 'Success',
    'title_note': 'Note',
    'title_cannot_open': 'Cannot Open',
    'title_no_path': 'No Path',
    'title_no_url': 'No URL',
    'title_no_playlist': 'No Playlist',
    'title_empty': 'Empty',
    # ── Messagebox contents ──────────────────────────────────────────────────
    'msg_no_url_entered': 'No URL entered!',
    'msg_no_valid_url': 'No valid URL entered!',
    'msg_no_urls_to_download': 'No URLs to download.',
    'msg_select_one_entry': 'Please select at least one entry.',
    'msg_select_one_url': 'Please select at least one URL.',
    'msg_no_file_manager': 'No file manager found. Please open the folder manually.',
    'msg_no_dest_path': 'Please enter a destination folder first.',
    'msg_no_playlist_url': 'Please enter a playlist URL first.',
    'msg_not_a_playlist': 'The URL does not point to a playlist.\nPlease enter a playlist URL.',
    'msg_playlist_empty': 'Playlist appears to be empty.',
    'msg_need_single_url_stream': 'Please analyze a single URL first and choose a stream!\n(Or: disable the ignore-video/ignore-audio checkbox.)',
    'msg_need_playlist_analyze': "Please analyze a playlist URL first,\nor run 'Edit Playlist'.",
    'msg_clipboard_empty': 'Clipboard empty:\n{e}',
    'msg_error_generic': 'Error:\n{e}',
    'msg_analysis_error': 'Analysis error:\n{m}',
    'msg_playlist_unavailable': 'Playlist not available:\n{m}',
    'msg_channel_unavailable': 'Channel not available:\n{u}\n\n{e}',
    'msg_url_unavailable': 'URL not available:\n{u}\n\n{e}',
    'msg_error_at_url': 'Error at:\n{u}\n\n{err}\n\nContinue with the remaining URLs?',
    'msg_download_success': '✅ {n} file(s) downloaded{extra}',
    'msg_download_success_single': '\n\n{title}',
    'msg_download_success_folder': '\nFolder: {folder}',
    'msg_download_cancelled_hint': '  (cancelled)',
    'msg_download_skipped_hint': '\n⚠ {n} skipped (deleted/private/error)',
    # ── Placeholders / combobox values ──────────────────────────────────────
    'ph_analyse': 'Please analyze the URL first',
    'ph_playlist': '– Playlist detected (selection at download) –',
    'no_video': '-No Video-',
    'no_audio': '-No Audio-',
}


_DE: dict[str, str] = {
    # ── Window / general ────────────────────────────────────────────────────
    'window_title': 'YouTube Downloader v{v}  🎵 + 🎬',
    'lang_label': '🌐 Sprache:',
    # ── URL input ────────────────────────────────────────────────────────────
    'url_frame_title': 'URL(s)  –  ein Link pro Zeile  oder  Playlist-URL',
    'url_hint': 'Playlist → Playlist-Sektion nutzen  |  Mehrere URLs → Multi-URL-Dialog erscheint automatisch',
    'btn_paste': '📋 Einfügen',
    'btn_analyze': '🔍 Analysieren',
    'btn_clear': '🗑 Löschen',
    # ── Status / progress ───────────────────────────────────────────────────
    'lbl_status': 'Status:',
    'status_ready': 'Bereit',
    'pause_btn': '⏸ Pause',
    'resume_btn': '▶ Weiter',
    'cancel_btn': '✕ Abbrechen',
    'status_link_pasted': 'Link eingefügt.',
    'status_fields_cleared': 'Felder geleert.',
    'status_resuming': '▶ Download wird fortgesetzt...',
    'status_cancelling': '✕ Wird abgebrochen...',
    'status_paused': '⏸ Pausiert – ▶ Weiter zum Fortfahren',
    'status_analyzing': 'Analysiere...',
    'status_analysis_done_vfa': 'Analyse fertig – {vc} Video / {ac} Audio-Streams',
    'status_analysis_done_pl': 'Analyse fertig – {vc}V/{ac}A-Streams{pl}',
    'status_analysis_done_pl_suffix': '  |  Playlist: {done}/{total} downloadbar',
    'status_analysis_error': 'Fehler bei Analyse',
    'status_playlist_detected': 'Playlist erkannt – {done}/{total} downloadbar',
    'status_cancelled': 'Abgebrochen.',
    'status_download_starting': 'Starte Download: {n} Datei(en)...',
    'status_download_n_of_t': 'Download {i} von {t}...',
    'status_download_running': 'Download läuft...',
    'status_download_progress': 'Download {i}/{t}...',
    'status_download_done': 'Download abgeschlossen!',
    'status_download_cancelled': 'Download abgebrochen.',
    'status_download_none': 'Kein Download abgeschlossen.',
    'status_skipped': 'Übersprungen: {u}…',
    'status_urls_checking': 'URLs werden geprüft...',
    'status_video_from_playlist': 'Lade Video {idx} aus Playlist...',
    'status_playlist_loading_n': "Playlist '{t}': {n}/{tot} downloadbare Einträge werden geladen...",
    'status_playlist_loading_dl': "Playlist '{t}': {n} downloadbare Einträge werden geladen...",
    'status_playlist_none_downloadable': 'Keine downloadbaren Einträge in der Playlist.',
    'status_channel_analyzing': "Kanal '{n}' wird analysiert...",
    'status_channel_none': "Kanal '{n}': Keine downloadbaren Einträge gefunden.",
    'status_channel_loading': "Kanal '{nm}': {n} Videos werden geladen...",
    'status_playlist_loading': 'Playlist wird geladen...',
    'status_playlist_ready_n': 'Playlist bereit: {n} Einträge ausgewählt',
    'status_playlist_none_detected': 'Keine Playlist erkannt.',
    'status_playlist_cached': "Playlist '{t}' – {n} Einträge (bereits geladen)",
    'status_playlist_with_n': "Playlist '{t}' – {n} Einträge",
    'status_load_error': 'Fehler beim Laden',
    # ── Playlist status label (below Playlist section) ─────────────────────
    'pl_status_none': 'Keine Playlist geladen.',
    'pl_status_loading_info': '⏳ Lade Playlist-Informationen...',
    'pl_status_error': '❌ Fehler beim Laden.',
    'pl_status_none_detected': '❌ Keine Playlist erkannt.',
    'pl_status_empty': '❌ Playlist ist leer.',
    'pl_status_choose': "✅ '{t}' – {n} Einträge. Bitte Auswahl treffen...",
    'pl_status_edit_cancelled': '⚠ Bearbeitung abgebrochen – {n} Einträge verfügbar',
    'pl_status_ready': "✅ '{t}': {n}/{total} Einträge, Modus: {mode} → jetzt 'Playlist herunterladen' drücken",
    'pl_status_preparing': '⏳ Wird vorbereitet...',
    'pl_status_downloading': '⬇ Download läuft...',
    'pl_title_prefix': 'Playlist: {t}',
    'pl_title_unknown': 'Unbekannte Playlist',
    'pl_status_loaded': '📋 {t}  ({done}/{total} downloadbar) – Playlist geladen.',
    'pl_status_load_failed': 'Playlist konnte nicht geladen werden.',
    'pl_title_bar': '📋 Playlist: {t}  ({done}/{total} downloadbar)',
    'video_title_bar': '📹 {t}',
    'video_title_index_hint': '  (Index {idx})',
    'video_title_with_playlist': '  –  Playlist: {t}',
    # ── Collapsible section headers ─────────────────────────────────────────
    'sec_toggle_line': '{arrow}  {icon}  –  zum {action} klicken',
    'action_expand': 'Aufklappen',
    'action_collapse': 'Einklappen',
    'sec_qd_title': '⚡ Schnell-Download',
    'sec_pl_title': '📋 Playlist-Verwaltung',
    'sec_adv_title': '🛠 Erweiterte Optionen (Einzelvideo)',
    'sec_so_title': '💾 Speicherorte & Optionen',
    # ── Quick download section ──────────────────────────────────────────────
    'qd_btn_audio_mp3': '🎵 Audio\nMP3',
    'qd_btn_audio_opus': '🎵 Audio\nOpus',
    'qd_btn_video_mp4_m4a': '🎬 Video\nMP4+M4A',
    'qd_btn_video_mp4': '🎬 Video\nMP4',
    'qd_btn_video_best': '🎬 Video\nBest',
    'qd_loading_audio_mp3': '🎵 Audio (MP3) lädt...',
    'qd_loading_audio_opus': '🎵 Audio (Opus) lädt...',
    'qd_loading_video_mp4_m4a': '🎬 Video (MP4+M4A) lädt...',
    'qd_loading_video_mp4': '🎬 Video (MP4) lädt...',
    'qd_loading_video_best': '🎬 Video Max lädt...',
    'hook_loading_generic': '📥 Lädt...',
    'qd_info1': 'MP3/Opus: Maximale verfügbare Bitrate der Quelle wird automatisch genutzt.  MP4+M4A: Original-Streams vom Server (kein Re-Encoding, AV1-freie Kompatibilität).',
    'qd_info2': 'Bei 1 URL oder mit playlist-INDEX: direkt herunterladen.\nBei Playlist-URL (ohne INDEX): alle downloadbaren Einträge direkt, kein Dialog.\nGelöschte/private Videos werden automatisch übersprungen.',
    # ── Playlist section ────────────────────────────────────────────────────
    'btn_pl_edit': '📋 Playlist bearbeiten',
    'btn_pl_download': '▶ Playlist herunterladen 📥',
    'pl_hint': "Tipp: Nach der Analyse direkt 'Bearbeiten' klicken – Playlist ist bereits geladen. Auswahl bleibt bis zum Download erhalten.",
    # ── Advanced options ─────────────────────────────────────────────────────
    'lf_video_stream': 'Video Stream',
    'lbl_video_format': 'Video-Format:',
    'radio_original': 'Original',
    'radio_mp4': 'MP4',
    'radio_mkv': 'MKV',
    'chk_ignore_video': 'Video ignorieren',
    'lf_audio_stream': 'Audio Stream',
    'lbl_audio_format': 'Audio-Format:',
    'radio_opus': 'Opus',
    'radio_mp3': 'MP3',
    'lbl_bitrate_inline': '  Bitrate:',
    'lbl_kbps': 'kbps',
    'chk_ignore_audio': 'Audio ignorieren',
    'btn_download_custom': '▶ Mit Auswahl herunterladen 📥',
    # ── Save locations & options ─────────────────────────────────────────────
    'lbl_audio_path': 'Audio:',
    'lbl_video_path': 'Video:',
    'btn_browse': '📁 Durchsuchen',
    'btn_open': '🗂 Öffnen',
    'chk_open_folder': '📂 Zielordner nach Download öffnen',
    'chk_write_tags': '🏷 Metadaten-Tags in Datei schreiben',
    'chk_write_thumb': '🖼 Thumbnail einbetten',
    'lbl_cookies': '🍪 Cookies aus Browser:',
    'lbl_cookies_hint': '  ← Browser wählen um YouTube-Anmeldung zu nutzen (löst 429-Fehler)',
    'browse_dialog_title': '{kind} – Zielordner',
    # ── Dialog boxes (Playlist / Multi-URL) ─────────────────────────────────
    'dlg_playlist_title': '{prefix} – Auswahl & Download-Einstellungen',
    'dlg_multi_title': 'Multi-URL – Auswahl & Download-Einstellungen',
    'dlg_cfg_frame_title': 'Download-Einstellungen (gilt für alle ausgewählten Einträge)',
    'lbl_mode': 'Modus:',
    'mode_audio_mp3':     '🎵 Audio (MP3)',
    'mode_audio_opus':    '🎵 Audio (Opus)',
    'mode_video_mp4_m4a': '🎬 Video (MP4+M4A)',
    'mode_video_mp4':     '🎬 Video (MP4)',
    'mode_video_best':    '🎬 Video (Best)',
    'lbl_mp3_bitrate': 'MP3-Bitrate:',
    'lbl_opus_bitrate': 'Opus-Bitrate:',
    'radio_fixed_bitrate': 'Feste Bitrate',
    'radio_max_bitrate': 'Max. Bitrate (automatisch je Datei)',
    'btn_remember_selection': '📋✔ Auswahl merken',
    'n_of_total_selected': '{n} von {total} ausgewählt',
    'sel_all': 'Alle',
    'sel_none': 'Keine',
    'sel_invert': 'Umkehren',
    'sel_only_downloadable': '✅ Nur Downloadbare',
    'pl_header_count': '📋  {n} Einträge',
    'pl_header_done': '  •  ✅ {n} bereits vorhanden',
    'entry_default_title': 'Eintrag {i}',
    'entry_unavailable_suffix': '  ⚠ nicht verfügbar',
    'search_label': '🔍 Suche:',
    'filter_visible': '{visible}/{total} sichtbar',
    'multi_url_header': '🔗  {n} URLs erkannt',
    # ── Messagebox titles ────────────────────────────────────────────────────
    'title_error': 'Fehler',
    'title_success': 'Erfolg',
    'title_note': 'Hinweis',
    'title_cannot_open': 'Öffnen nicht möglich',
    'title_no_path': 'Kein Pfad',
    'title_no_url': 'Kein URL',
    'title_no_playlist': 'Keine Playlist',
    'title_empty': 'Leer',
    # ── Messagebox contents ──────────────────────────────────────────────────
    'msg_no_url_entered': 'Keine URL eingegeben!',
    'msg_no_valid_url': 'Keine gültige URL eingegeben!',
    'msg_no_urls_to_download': 'Keine URLs zum Herunterladen.',
    'msg_select_one_entry': 'Bitte mindestens einen Eintrag auswählen.',
    'msg_select_one_url': 'Bitte mindestens eine URL auswählen.',
    'msg_no_file_manager': 'Kein Dateimanager gefunden. Bitte Ordner manuell öffnen.',
    'msg_no_dest_path': 'Bitte zuerst einen Zielordner eingeben.',
    'msg_no_playlist_url': 'Bitte zuerst eine Playlist-URL eingeben.',
    'msg_not_a_playlist': 'Die URL verweist auf keine Playlist.\nBitte eine Playlist-URL eingeben.',
    'msg_playlist_empty': 'Playlist scheint leer zu sein.',
    'msg_need_single_url_stream': 'Bitte zuerst eine Einzel-URL analysieren und Stream wählen!\n(Oder: Video/Audio-ignorieren-Checkbox deaktivieren.)',
    'msg_need_playlist_analyze': "Bitte zuerst eine Playlist-URL analysieren\noder 'Playlist bearbeiten' ausführen.",
    'msg_clipboard_empty': 'Zwischenablage leer:\n{e}',
    'msg_error_generic': 'Fehler:\n{e}',
    'msg_analysis_error': 'Analyse-Fehler:\n{m}',
    'msg_playlist_unavailable': 'Playlist nicht abrufbar:\n{m}',
    'msg_channel_unavailable': 'Kanal nicht abrufbar:\n{u}\n\n{e}',
    'msg_url_unavailable': 'URL nicht abrufbar:\n{u}\n\n{e}',
    'msg_error_at_url': 'Fehler bei:\n{u}\n\n{err}\n\nWeiter mit restlichen URLs?',
    'msg_download_success': '✅ {n} Datei(en) heruntergeladen{extra}',
    'msg_download_success_single': '\n\n{title}',
    'msg_download_success_folder': '\nOrdner: {folder}',
    'msg_download_cancelled_hint': '  (abgebrochen)',
    'msg_download_skipped_hint': '\n⚠ {n} übersprungen (gelöscht/privat/Fehler)',
    # ── Placeholders / combobox values ──────────────────────────────────────
    'ph_analyse': 'Bitte zuerst URL analysieren',
    'ph_playlist': '– Playlist erkannt (Auswahl beim Download) –',
    'no_video': '-Kein Video-',
    'no_audio': '-Kein Audio-',
}


_FA: dict[str, str] = {
    # ── Window / general ────────────────────────────────────────────────────
    'window_title': 'دانلودکننده یوتیوب نسخه {v}  🎵 + 🎬',
    'lang_label': '🌐 زبان:',
    # ── URL input ────────────────────────────────────────────────────────────
    'url_frame_title': 'آدرس(ها)  –  هر لینک در یک خط  یا  آدرس پلی\u200cلیست',
    'url_hint': 'پلی\u200cلیست → از بخش پلی\u200cلیست استفاده کنید  |  چند آدرس → پنجره چند-آدرسی به\u200cصورت خودکار باز می\u200cشود',
    'btn_paste': '📋 چسباندن',
    'btn_analyze': '🔍 تحلیل',
    'btn_clear': '🗑 پاک کردن',
    # ── Status / progress ───────────────────────────────────────────────────
    'lbl_status': 'وضعیت:',
    'status_ready': 'آماده',
    'pause_btn': '⏸ توقف',
    'resume_btn': '▶ ادامه',
    'cancel_btn': '✕ لغو',
    'status_link_pasted': 'لینک چسبانده شد.',
    'status_fields_cleared': 'فیلدها پاک شدند.',
    'status_resuming': '▶ ازسرگیری دانلود...',
    'status_cancelling': '✕ در حال لغو...',
    'status_paused': '⏸ متوقف\u200cشده – برای ادامه روی ▶ ادامه کلیک کنید',
    'status_analyzing': 'در حال تحلیل...',
    'status_analysis_done_vfa': 'تحلیل انجام شد – {vc} ویدیو / {ac} جریان صوتی',
    'status_analysis_done_pl': 'تحلیل انجام شد – {vc}ویدیو/{ac}صدا{pl}',
    'status_analysis_done_pl_suffix': '  |  پلی\u200cلیست: {done}/{total} قابل دانلود',
    'status_analysis_error': 'تحلیل ناموفق بود',
    'status_playlist_detected': 'پلی\u200cلیست شناسایی شد – {done}/{total} قابل دانلود',
    'status_cancelled': 'لغو شد.',
    'status_download_starting': 'شروع دانلود: {n} فایل...',
    'status_download_n_of_t': 'دانلود {i} از {t}...',
    'status_download_running': 'دانلود در حال اجراست...',
    'status_download_progress': 'دانلود {i}/{t}...',
    'status_download_done': 'دانلود کامل شد!',
    'status_download_cancelled': 'دانلود لغو شد.',
    'status_download_none': 'هیچ دانلودی کامل نشد.',
    'status_skipped': 'رد شد: {u}…',
    'status_urls_checking': 'در حال بررسی آدرس\u200cها...',
    'status_video_from_playlist': 'در حال بارگذاری ویدیو {idx} از پلی\u200cلیست...',
    'status_playlist_loading_n': "پلی\u200cلیست '{t}': در حال بارگذاری {n}/{tot} مورد قابل دانلود...",
    'status_playlist_loading_dl': "پلی\u200cلیست '{t}': در حال بارگذاری {n} مورد قابل دانلود...",
    'status_playlist_none_downloadable': 'هیچ مورد قابل دانلودی در پلی\u200cلیست نیست.',
    'status_channel_analyzing': "در حال تحلیل کانال '{n}'...",
    'status_channel_none': "کانال '{n}': هیچ مورد قابل دانلودی پیدا نشد.",
    'status_channel_loading': "کانال '{nm}': در حال بارگذاری {n} ویدیو...",
    'status_playlist_loading': 'در حال بارگذاری پلی\u200cلیست...',
    'status_playlist_ready_n': 'پلی\u200cلیست آماده است: {n} مورد انتخاب شد',
    'status_playlist_none_detected': 'پلی\u200cلیستی شناسایی نشد.',
    'status_playlist_cached': "پلی\u200cلیست '{t}' – {n} مورد (قبلاً بارگذاری شده)",
    'status_playlist_with_n': "پلی\u200cلیست '{t}' – {n} مورد",
    'status_load_error': 'خطا در بارگذاری',
    # ── Playlist status label (below Playlist section) ─────────────────────
    'pl_status_none': 'پلی\u200cلیستی بارگذاری نشده است.',
    'pl_status_loading_info': '⏳ در حال بارگذاری اطلاعات پلی\u200cلیست...',
    'pl_status_error': '❌ خطا در بارگذاری.',
    'pl_status_none_detected': '❌ پلی\u200cلیستی شناسایی نشد.',
    'pl_status_empty': '❌ پلی\u200cلیست خالی است.',
    'pl_status_choose': "✅ '{t}' – {n} مورد. لطفاً یک انتخاب انجام دهید...",
    'pl_status_edit_cancelled': '⚠ ویرایش لغو شد – {n} مورد در دسترس',
    'pl_status_ready': "✅ '{t}': {n}/{total} مورد، حالت: {mode} → اکنون روی «دانلود پلی\u200cلیست» کلیک کنید",
    'pl_status_preparing': '⏳ در حال آماده\u200cسازی...',
    'pl_status_downloading': '⬇ دانلود در حال اجراست...',
    'pl_title_prefix': 'پلی\u200cلیست: {t}',
    'pl_title_unknown': 'پلی\u200cلیست ناشناخته',
    'pl_status_loaded': '📋 {t}  ({done}/{total} قابل دانلود) – پلی\u200cلیست بارگذاری شد.',
    'pl_status_load_failed': 'پلی\u200cلیست بارگذاری نشد.',
    'pl_title_bar': '📋 پلی\u200cلیست: {t}  ({done}/{total} قابل دانلود)',
    'video_title_bar': '📹 {t}',
    'video_title_index_hint': '  (اندیس {idx})',
    'video_title_with_playlist': '  –  پلی\u200cلیست: {t}',
    # ── Collapsible section headers ─────────────────────────────────────────
    'sec_toggle_line': '{arrow}  {icon}  –  برای {action} کلیک کنید',
    'action_expand': 'باز کردن',
    'action_collapse': 'بستن',
    'sec_qd_title': '⚡ دانلود سریع',
    'sec_pl_title': '📋 مدیریت پلی\u200cلیست',
    'sec_adv_title': '🛠 گزینه\u200cهای پیشرفته (تک ویدیو)',
    'sec_so_title': '💾 محل ذخیره\u200cسازی و گزینه\u200cها',
    # ── Quick download section ──────────────────────────────────────────────
    'qd_btn_audio_mp3': '🎵 صدا\nMP3',
    'qd_btn_audio_opus': '🎵 صدا\nOpus',
    'qd_btn_video_mp4_m4a': '🎬 ویدیو\nMP4+M4A',
    'qd_btn_video_mp4': '🎬 ویدیو\nMP4',
    'qd_btn_video_best': '🎬 ویدیو\nبهترین',
    'qd_loading_audio_mp3': '🎵 صدا (MP3) در حال بارگذاری...',
    'qd_loading_audio_opus': '🎵 صدا (Opus) در حال بارگذاری...',
    'qd_loading_video_mp4_m4a': '🎬 ویدیو (MP4+M4A) در حال بارگذاری...',
    'qd_loading_video_mp4': '🎬 ویدیو (MP4) در حال بارگذاری...',
    'qd_loading_video_best': '🎬 ویدیو با بهترین کیفیت در حال بارگذاری...',
    'hook_loading_generic': '📥 در حال بارگذاری...',
    'qd_info1': 'MP3/Opus: بالاترین بیت\u200cریت موجود منبع به\u200cطور خودکار استفاده می\u200cشود.  MP4+M4A: جریان\u200cهای اصلی از سرور (بدون تبدیل مجدد، سازگاری بدون AV1).',
    'qd_info2': 'با ۱ آدرس یا اندیس پلی\u200cلیست: دانلود مستقیم.\nبا آدرس پلی\u200cلیست (بدون اندیس): همه موارد قابل دانلود مستقیماً دانلود می\u200cشوند، بدون پنجره تأیید.\nویدیوهای حذف\u200cشده/خصوصی به\u200cطور خودکار رد می\u200cشوند.',
    # ── Playlist section ────────────────────────────────────────────────────
    'btn_pl_edit': '📋 ویرایش پلی\u200cلیست',
    'btn_pl_download': '▶ دانلود پلی\u200cلیست 📥',
    'pl_hint': 'نکته: پس از تحلیل، بلافاصله روی «ویرایش» کلیک کنید – پلی\u200cلیست از قبل بارگذاری شده است. انتخاب شما تا زمان دانلود حفظ می\u200cشود.',
    # ── Advanced options ─────────────────────────────────────────────────────
    'lf_video_stream': 'جریان ویدیو',
    'lbl_video_format': 'قالب ویدیو:',
    'radio_original': 'اصلی',
    'radio_mp4': 'MP4',
    'radio_mkv': 'MKV',
    'chk_ignore_video': 'نادیده گرفتن ویدیو',
    'lf_audio_stream': 'جریان صوتی',
    'lbl_audio_format': 'قالب صدا:',
    'radio_opus': 'Opus',
    'radio_mp3': 'MP3',
    'lbl_bitrate_inline': '  بیت\u200cریت:',
    'lbl_kbps': 'کیلوبیت بر ثانیه',
    'chk_ignore_audio': 'نادیده گرفتن صدا',
    'btn_download_custom': '▶ دانلود با انتخاب 📥',
    # ── Save locations & options ─────────────────────────────────────────────
    'lbl_audio_path': 'صدا:',
    'lbl_video_path': 'ویدیو:',
    'btn_browse': '📁 انتخاب پوشه',
    'btn_open': '🗂 باز کردن',
    'chk_open_folder': '📂 باز کردن پوشه مقصد پس از دانلود',
    'chk_write_tags': '🏷 نوشتن برچسب\u200cهای متادیتا در فایل',
    'chk_write_thumb': '🖼 جاسازی تصویر بندانگشتی',
    'lbl_cookies': '🍪 کوکی\u200cها از مرورگر:',
    'lbl_cookies_hint': '  ← برای استفاده از ورود یوتیوب خود یک مرورگر انتخاب کنید (رفع خطای 429)',
    'browse_dialog_title': '{kind} – پوشه مقصد',
    # ── Dialog boxes (Playlist / Multi-URL) ─────────────────────────────────
    'dlg_playlist_title': '{prefix} – انتخاب و تنظیمات دانلود',
    'dlg_multi_title': 'چند-آدرسی – انتخاب و تنظیمات دانلود',
    'dlg_cfg_frame_title': 'تنظیمات دانلود (برای همه موارد انتخاب\u200cشده اعمال می\u200cشود)',
    'lbl_mode': 'حالت:',
    'mode_audio_mp3':     '🎵 صوت (MP3)',
    'mode_audio_opus':    '🎵 صوت (Opus)',
    'mode_video_mp4_m4a': '🎬 ویدیو (MP4+M4A)',
    'mode_video_mp4':     '🎬 ویدیو (MP4)',
    'mode_video_best':    '🎬 ویدیو (بهترین کیفیت)',
    'lbl_mp3_bitrate': 'بیت\u200cریت MP3:',
    'lbl_opus_bitrate': 'بیت\u200cریت Opus:',
    'radio_fixed_bitrate': 'بیت\u200cریت ثابت',
    'radio_max_bitrate': 'حداکثر بیت\u200cریت (خودکار برای هر فایل)',
    'btn_remember_selection': '📋✔ به\u200cخاطر سپردن انتخاب',
    'n_of_total_selected': '{n} از {total} انتخاب شد',
    'sel_all': 'همه',
    'sel_none': 'هیچ\u200cکدام',
    'sel_invert': 'معکوس کردن',
    'sel_only_downloadable': '✅ فقط قابل دانلود',
    'pl_header_count': '📋  {n} مورد',
    'pl_header_done': '  •  ✅ {n} مورد قبلاً دانلود شده',
    'entry_default_title': 'مورد {i}',
    'entry_unavailable_suffix': '  ⚠ در دسترس نیست',
    'search_label': '🔍 جستجو:',
    'filter_visible': '{visible}/{total} نمایان',
    'multi_url_header': '🔗  {n} آدرس شناسایی شد',
    # ── Messagebox titles ────────────────────────────────────────────────────
    'title_error': 'خطا',
    'title_success': 'موفقیت',
    'title_note': 'یادداشت',
    'title_cannot_open': 'قابل باز کردن نیست',
    'title_no_path': 'بدون مسیر',
    'title_no_url': 'بدون آدرس',
    'title_no_playlist': 'بدون پلی\u200cلیست',
    'title_empty': 'خالی',
    # ── Messagebox contents ──────────────────────────────────────────────────
    'msg_no_url_entered': 'هیچ آدرسی وارد نشد!',
    'msg_no_valid_url': 'هیچ آدرس معتبری وارد نشد!',
    'msg_no_urls_to_download': 'آدرسی برای دانلود وجود ندارد.',
    'msg_select_one_entry': 'لطفاً حداقل یک مورد را انتخاب کنید.',
    'msg_select_one_url': 'لطفاً حداقل یک آدرس را انتخاب کنید.',
    'msg_no_file_manager': 'مدیر فایلی پیدا نشد. لطفاً پوشه را به\u200cصورت دستی باز کنید.',
    'msg_no_dest_path': 'لطفاً ابتدا یک پوشه مقصد وارد کنید.',
    'msg_no_playlist_url': 'لطفاً ابتدا یک آدرس پلی\u200cلیست وارد کنید.',
    'msg_not_a_playlist': 'این آدرس به یک پلی\u200cلیست اشاره نمی\u200cکند.\nلطفاً یک آدرس پلی\u200cلیست وارد کنید.',
    'msg_playlist_empty': 'به\u200cنظر می\u200cرسد پلی\u200cلیست خالی است.',
    'msg_need_single_url_stream': 'لطفاً ابتدا یک آدرس تکی را تحلیل کرده و یک جریان انتخاب کنید!\n(یا: گزینه نادیده\u200cگرفتن ویدیو/صدا را غیرفعال کنید.)',
    'msg_need_playlist_analyze': 'لطفاً ابتدا یک آدرس پلی\u200cلیست را تحلیل کنید،\nیا «ویرایش پلی\u200cلیست» را اجرا کنید.',
    'msg_clipboard_empty': 'کلیپ\u200cبورد خالی است:\n{e}',
    'msg_error_generic': 'خطا:\n{e}',
    'msg_analysis_error': 'خطای تحلیل:\n{m}',
    'msg_playlist_unavailable': 'پلی\u200cلیست در دسترس نیست:\n{m}',
    'msg_channel_unavailable': 'کانال در دسترس نیست:\n{u}\n\n{e}',
    'msg_url_unavailable': 'آدرس در دسترس نیست:\n{u}\n\n{e}',
    'msg_error_at_url': 'خطا در:\n{u}\n\n{err}\n\nآیا با آدرس\u200cهای باقی\u200cمانده ادامه یابد؟',
    'msg_download_success': '✅ {n} فایل دانلود شد{extra}',
    'msg_download_success_single': '\n\n{title}',
    'msg_download_success_folder': '\nپوشه: {folder}',
    'msg_download_cancelled_hint': '  (لغو شد)',
    'msg_download_skipped_hint': '\n⚠ {n} مورد رد شد (حذف\u200cشده/خصوصی/خطا)',
    # ── Placeholders / combobox values ──────────────────────────────────────
    'ph_analyse': 'لطفاً ابتدا آدرس را تحلیل کنید',
    'ph_playlist': '– پلی\u200cلیست شناسایی شد (انتخاب هنگام دانلود) –',
    'no_video': '-بدون ویدیو-',
    'no_audio': '-بدون صدا-',
}

# Reference language: every other block is checked against this one's keys.
_REFERENCE_LANG = 'en'

_LANG_BLOCKS: dict[str, dict[str, str]] = {
    'en': _EN,
    'de': _DE,
    'fa': _FA,
}


def _build_i18n() -> dict:
    """Merges the per-language blocks above into the key -> {lang: text}
    structure T() reads from. Keys are taken from the reference language
    (_REFERENCE_LANG) so every key is guaranteed present at least in English."""
    merged: dict[str, dict[str, str]] = {}
    for key in _LANG_BLOCKS[_REFERENCE_LANG]:
        merged[key] = {
            lang: block[key]
            for lang, block in _LANG_BLOCKS.items()
            if key in block
        }
    return merged


def _check_i18n_completeness() -> None:
    """Startup sanity check: warns (does not crash) if a language block is
    missing keys the reference language has, or carries stray keys the
    reference language doesn't. Makes incomplete translations visible right
    away instead of silently falling back to English at runtime."""
    ref_keys = set(_LANG_BLOCKS[_REFERENCE_LANG])
    for lang, block in _LANG_BLOCKS.items():
        if lang == _REFERENCE_LANG:
            continue
        missing = sorted(ref_keys - set(block))
        extra = sorted(set(block) - ref_keys)
        if missing:
            print(f"[i18n] WARNING: language '{lang}' is missing {len(missing)} "
                  f"key(s): {missing}")
        if extra:
            print(f"[i18n] WARNING: language '{lang}' has {len(extra)} unknown "
                  f"key(s) not present in '{_REFERENCE_LANG}': {extra}")
    unknown_langs = set(LANGUAGES) - set(_LANG_BLOCKS)
    if unknown_langs:
        print(f"[i18n] WARNING: LANGUAGES lists {sorted(unknown_langs)} but "
              f"no matching block exists in _LANG_BLOCKS.")


_check_i18n_completeness()
I18N: dict[str, dict[str, str]] = _build_i18n()



# Maps a rendered string -> (key, kwargs) that produced it, so dynamic
# labels/status text still on screen (e.g. "Playlist geladen: X (5/10)")
# can be re-rendered in a newly chosen language later, values and all –
# see MainWindow._retranslate_var()/_retranslate_combo().
_T_ORIGIN: dict = {}


def T(key: str, **kwargs) -> str:
    """Return the UI text for *key* in the currently active language.

    Falls back to English (then to the key itself) if a translation is
    missing, and formats any keyword arguments into the template.
    """
    entry = I18N.get(key)
    if entry is None:
        return key
    text = entry.get(LANG['code']) or entry.get('en') or key
    result = text
    if kwargs:
        try:
            result = text.format(**kwargs)
        except Exception:
            result = text
    if len(_T_ORIGIN) > 1000:   # simple safety cap against unbounded growth
        _T_ORIGIN.clear()
    _T_ORIGIN[result] = (key, kwargs)
    return result


def _skip_labels() -> set:
    """Combobox placeholder labels that must never be treated as a real
    stream selection – recomputed so it always matches the active language."""
    return {T('ph_analyse'), T('ph_playlist'), T('no_video'), T('no_audio')}


def _modes() -> list:
    """(label, key) pairs for the mode radio buttons (Playlist/Multi-URL
    dialogs) – recomputed so the labels always match the active language,
    same idea as _skip_labels()."""
    return [
        (T('mode_audio_mp3'),     'audio_mp3'),
        (T('mode_audio_opus'),    'audio_opus'),
        (T('mode_video_mp4_m4a'), 'video_mp4_m4a'),
        (T('mode_video_mp4'),     'video_mp4'),
        (T('mode_video_best'),    'video_best'),
    ]


def _modes_dict() -> dict:
    return dict(_modes())


class I18nRegistry:
    """Keeps track of static widgets so their displayed text can be
    refreshed instantly when the UI language is switched at runtime."""

    def __init__(self):
        self._items: list = []

    def reg(self, widget, key: str, attr: str = 'text', **kwargs):
        """Register *widget* to show T(key, **kwargs) in *attr*, and apply it now."""
        self._items.append((widget, attr, key, kwargs))
        try:
            widget.configure(**{attr: T(key, **kwargs)})
        except Exception:
            pass
        return widget

    def refresh(self):
        """Re-applies T(key, **kwargs) to every registered widget."""
        for widget, attr, key, kwargs in self._items:
            try:
                widget.configure(**{attr: T(key, **kwargs)})
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════════
#  Configuration file  (yt_d_config.txt  –  next to the .py file)
# ═════════════════════════════════════════════════════════════════════════════

_CONFIG_FILE = path.join(path.dirname(path.abspath(__file__)), 'yt_d_config.txt')

# Key → (type, default value)
# Types: 'str' | 'bool' | 'int'
_CONFIG_SCHEMA: dict[str, tuple[str, object]] = {
    'audio_path':         ('str',  ''),
    'video_path':         ('str',  ''),
    'audio_to_mp3':       ('bool', True),
    'audio_format':       ('str',  'original'),
    'video_to_mp4':       ('bool', True),
    'video_format':       ('str',  'original'),
    'mp3_bitrate':        ('str',  '320'),
    'open_folder':        ('bool', False),
    'write_tags':         ('bool', True),
    'write_thumbnail':    ('bool', True),
    'cookies_browser':    ('str',  ''),
    'playlist_mode':      ('str',  'audio_mp3'),
    'playlist_bitrate':   ('str',  '0'),
    'language':           ('str',  'en'),   # one of LANGUAGES, see i18n section above ('en' default)
}


def _config_load() -> dict:
    """
    Reads yt_d_config.txt and returns a dict with all settings.
    Missing keys are filled in with the default value from _CONFIG_SCHEMA.
    Lines starting with '#' are ignored.
    Format per line:  key = value
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
    Writes all settings from *cfg* to yt_d_config.txt.
    Unknown keys are ignored.
    """
    lines = [
        '# YouTube Downloader – configuration file',
        '# Automatically generated. Manual edits are allowed.',
        '# Format:  key = value',
        '# Boolean values: true / false',
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
#  Helper functions
# ═════════════════════════════════════════════════════════════════════════════

def _unique_path(filepath: str, known_names: set | None = None) -> str:
    """
    Returns a unique file path.
    Checks both against files that actually exist on disk and against
    *known_names* (a set of filenames without extension, populated once
    from the destination folder when the download starts).
    This also catches collisions when several files are downloaded in one
    session before the first of them has actually landed on disk.
    Example: 'Song.mp3' → 'Song (1).mp3' → 'Song (2).mp3' …
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
        candidate = f'{base} ({i}){ext}'
        cand_stem = f'{stem} ({i})'
        if not _is_taken(candidate):
            if known_names is not None:
                known_names.add(cand_stem)
            return candidate
        i += 1


def _scan_existing_stems(folder: str) -> set:
    """
    Returns a set of all filenames (without extension) found in *folder*.
    Called once when the download starts.
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
    Attaches both a postprocessor_hook AND a progress_hook that write the
    final file path into a 1-element list once all postprocessors are done.
    Returns (new_opts, result_list) – result[0] is populated after the download.

    Note: yt-dlp does not reliably set 'filepath' in info_dict at every PP
    step (e.g. it's missing after FFmpegMetadata). The last known path is
    therefore kept (never overwritten with an empty value) and additionally
    determined from the download status via progress_hook as a fallback.
    """
    result: list = [None]

    def _pp_hook(d):
        if d.get('status') != 'finished':
            return
        fp = (d.get('info_dict') or {}).get('filepath', '')
        if fp:
            result[0] = fp

    def _prog_hook(d):
        # On completion of the download, save the path from the filename,
        # before postprocessors possibly rename it (extension change).
        # Serves as the initial baseline; _pp_hook overwrites it with the real final path.
        if d.get('status') == 'finished':
            fp = d.get('filename') or d.get('tmpfilename') or ''
            if fp and not result[0]:
                result[0] = fp

    new_opts = dict(opts)
    pph = list(new_opts.get('postprocessor_hooks') or [])
    pph.append(_pp_hook)
    new_opts['postprocessor_hooks'] = pph
    # Attach progress_hook as a fallback (fires BEFORE the PP hooks)
    prh = list(new_opts.get('progress_hooks') or [])
    prh.insert(0, _prog_hook)
    new_opts['progress_hooks'] = prh
    new_opts['no_overwrites'] = False
    return new_opts, result


def _resolve_outtmpl_unique(url: str, base_opts: dict, known_names: set) -> dict:
    """
    Fetches the video title beforehand (download=False), computes a
    unique destination filename from it, and sets it as a fixed outtmpl.
    """
    info_opts = dict(base_opts)
    info_opts['extract_flat'] = False
    info_opts['skip_download'] = True
    info_opts['quiet'] = True
    info_opts['no_warnings'] = True
    info_opts.pop('postprocessors', None)
    info_opts.pop('postprocessor_hooks', None)
    info_opts.pop('progress_hooks', None)

    title       = None
    ext         = None
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

    # Final extension: FFmpegExtractAudio codec takes precedence
    final_ext = ext
    has_extract_audio = False
    for pp in (base_opts.get('postprocessors') or []):
        if pp.get('key') == 'FFmpegExtractAudio':
            codec = pp.get('preferredcodec', '')
            if codec:
                final_ext = codec
            has_extract_audio = True
            break

    candidate   = os.path.join(dest_dir, f'{safe_title}.{final_ext}')
    unique_path = _unique_path(candidate, known_names)

    new_opts  = dict(base_opts)
    stem_path = os.path.splitext(unique_path)[0]
    new_opts['outtmpl'] = stem_path + '.%(ext)s'

    # For MP3 conversion: inject webpage_url into postprocessor_args in advance.
    # FFmpegExtractAudio truncates the URL at '&' when writing the comment tag.
    # By passing postprocessor_args we hand -metadata comment=<url> directly to FFmpeg,
    # which prevents it from being truncated.
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
    Records the finished filename in known_names.
    If the extension changed (e.g. webm→mp3), searches for the actual file.
    """
    fp = final_path_ref[0]
    if not fp:
        return
    stem = os.path.splitext(os.path.basename(fp))[0]
    if os.path.exists(fp):
        known_names.add(stem)
        return
    # Extension changed (e.g. after re-encoding) → search the folder
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
    Finds the thumbnail file belonging to media_fp (.webp/.jpg/.png),
    converts it to a small JPEG (500px, q:v 4 ≈ 30–50 KB) and embeds it:
      • .opus      → OggOpus  (metadata_block_picture / FLAC Picture) via mutagen
      • .mp3       → ID3 APIC tag via mutagen
      • .mp4/.mkv  → FFmpeg remux with embedded cover (no mutagen needed)
    The temporary thumbnail file is deleted afterwards.
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
            # FFmpeg remux: original + cover → temp file → replace original
            tmp_out = stem + '_covtmp' + ext_lower
            try:
                if ext_lower == '.mkv':
                    # MKV/Matroska has no 'attached_pic' – embed the cover as a
                    # file attachment instead (recognized by VLC, mpv, Kodi).
                    cmd = [ffmpeg_exe, '-y',
                           '-i', media_fp,
                           '-c', 'copy',
                           '-attach', th_jpg,
                           '-metadata:s:t', 'mimetype=image/jpeg',
                           '-metadata:s:t', 'filename=cover.jpg',
                           tmp_out]
                else:
                    # MP4 / WebM: embed the cover as a video stream with attached_pic
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
    """Removes duplicates from a yt-dlp entry list (key: video ID)."""
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
    """Normalizes a YouTube URL or ID down to the plain video ID."""
    if 'watch?v=' in s:
        return s.split('watch?v=')[1].split('&')[0]
    if 'youtu.be/' in s:
        return s.split('youtu.be/')[1].split('?')[0].split('&')[0]
    return s


def _entry_url(e: dict) -> str:
    """Returns the best retrievable URL for a playlist entry."""
    url = e.get('webpage_url') or e.get('url') or ''
    if url.startswith('http'):
        return url
    vid_id = e.get('id', '')
    if vid_id:
        return f'https://www.youtube.com/watch?v={vid_id}'
    return url


def _parse_yt_url(url: str) -> dict:
    """
    Analyzes a YouTube URL and returns a dict:
      {
        'video_id':    str | None,
        'list_id':     str | None,
        'index':       int | None,   # 1-based
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
    Returns True if the URL points to a YouTube channel
    (/@handle, /channel/ID, /c/Name, /user/Name) – but NOT a video or playlist URL.
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
    Extracts the channel handle/name from a channel URL as a safe folder name.
    Examples:
      https://www.youtube.com/@Germaninexile  →  'Germaninexile'
      https://www.youtube.com/channel/UCxxxx  →  'UCxxxx'
      https://www.youtube.com/c/MyChannel     →  'MyChannel'
    """
    for marker in ('/@', '/channel/', '/c/', '/user/'):
        if marker in url:
            part = url.split(marker, 1)[1]
            # Fragment/Query abschneiden
            part = part.split('?')[0].split('#')[0].split('/')[0].strip()
            # Remove characters that are invalid in folder names
            safe = re.sub(r'[\\/*?:"<>|]', '_', part).strip()
            return safe or 'channel'
    return 'channel'


def _flatten_channel_entries(info: dict) -> list:
    """
    Recursively collects all video entries from a channel info structure.
    For /@handle, yt-dlp returns a nested structure:
      Channel → [tab playlist, ...] → [sub playlist, ...] → [video, ...]
    This function returns a flat list of all leaf entries (videos).
    """
    entries = list(info.get('entries') or [])
    if not entries:
        return []

    # Check whether entries are themselves playlists
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
    Resolves the concrete video URL from a playlist entry list.
    Priority 1: index parameter (1-based)
    Priority 2: video ID from the v= parameter
    Returns None if nothing is found.
    """
    if not pl_entries:
        return None
    # Priority 1: index
    if p_url['index'] is not None:
        idx_0 = p_url['index'] - 1
        if 0 <= idx_0 < len(pl_entries):
            return _entry_url(pl_entries[idx_0])
    # Priority 2: video ID
    if p_url['video_id']:
        for e in pl_entries:
            eid = _extract_video_id(
                (e.get('id') or e.get('url') or '').strip())
            if eid == p_url['video_id']:
                return _entry_url(e)
    return None


def _is_unavailable_entry(entry: dict) -> bool:
    """Returns True if a playlist entry is not downloadable."""
    title = (entry.get('title') or '').lower().strip()
    return (
        title in _UNAVAIL_TITLES
        or title.startswith('[deleted')
        or title.startswith('[private')
        or title.startswith('[unavailable')
        or not entry.get('id')
    )


def _attach_scroll(canvas: 'Canvas'):
    """Binds the mouse wheel locally to a canvas (no bind_all)."""
    def _on_mw(event):
        canvas.yview_scroll(-1 * (event.delta // 120), 'units')
    canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _on_mw))
    canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))


def _open_folder(folder: str):
    """
    Opens a folder in the native file manager – cross-platform.
      Windows → Explorer
      macOS   → Finder (open)
      Linux   → xdg-open, falling back to common file managers
    """
    norm = os.path.normpath(folder)
    if IS_WINDOWS:
        Popen(f'explorer "{norm}"')
    elif IS_MAC:
        Popen(['open', norm])
    else:
        for opener in ['xdg-open', 'gvfs-open', 'exo-open',
                       'nautilus', 'dolphin', 'thunar']:
            if shutil.which(opener):
                Popen([opener, norm])
                return
        messagebox.showwarning(
            T('title_cannot_open'), T('msg_no_file_manager'))


# ═════════════════════════════════════════════════════════════════════════════
#  _BaseSelectionDialog  –  shared base for the Playlist and Multi-URL dialogs
# ═════════════════════════════════════════════════════════════════════════════
class _BaseSelectionDialog(Toplevel):
    """
    Abstract base: scrollable selection list + download settings + footer.
    Subclasses implement _build_header() and _populate_rows(inner).
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
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')
        self.minsize(min_w, min_h)

        self._vars: list[BooleanVar] = []
        self._mode_var         = StringVar(value=default_mode)
        self._bitrate_var      = StringVar(value=default_bitrate)
        self._use_max_bitrate  = BooleanVar(value=use_max_bitrate)
        self._search_var       = StringVar()      # given a trace in _build()
        self._filter_count_var = StringVar()      # set as label source in _build()
        self._list_canvas      = None             # set in _build()
        self._row_frames: list = []
        self._row_visible: list[bool] = []
        self._filter_after_id = None
        self._build()

    # ── Subclasses override these two methods ──────────────────────────────

    def _build_header(self, head: ttk.Frame):
        """Fill the header row with a title and selection buttons."""
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
        ttk.Label(sf, text=T('search_label'), font=('Segoe UI', 9)).pack(side='left')
        search_entry = ttk.Entry(sf, textvariable=self._search_var,
                                 font=('Segoe UI', 9), width=40)
        search_entry.pack(side='left', padx=(4, 6), fill='x', expand=True)
        ttk.Button(sf, text='✕', width=3,
                   command=lambda: self._search_var.set('')).pack(side='left')
        ttk.Label(sf, textvariable=self._filter_count_var,
                  font=('Segoe UI', 9), foreground='#555').pack(side='left', padx=(8, 0))
        self._search_var.trace_add('write', lambda *_: self._queue_filter_rows())
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
            text=T('dlg_cfg_frame_title'),
            padding=(12, 6))
        cfg.pack(fill='x', padx=8, pady=6)
        mode_row = ttk.Frame(cfg)
        mode_row.pack(fill='x')
        ttk.Label(mode_row, text=T('lbl_mode'), width=10).pack(side='left')
        for label, key in _modes():
            ttk.Radiobutton(mode_row, text=label, variable=self._mode_var,
                            value=key,
                            command=self._toggle_bitrate).pack(side='left', padx=6)
        br_row = ttk.Frame(cfg)
        br_row.pack(fill='x', pady=(4, 0))
        self._br_label = ttk.Label(br_row, text=T('lbl_mp3_bitrate'), width=10)
        self._br_label.pack(side='left')
        self._br_combo = ttk.Combobox(
            br_row, textvariable=self._bitrate_var,
            values=['320', '256', '192', '160', '128', '96', '64'],
            width=7, state='readonly', style='Bitrate.TCombobox')
        self._br_combo.pack(side='left', padx=(0, 2))
        ttk.Label(br_row, text=T('lbl_kbps'),
                  font=('Segoe UI', 9), foreground='#666').pack(side='left')
        ttk.Radiobutton(br_row, text=T('radio_fixed_bitrate'),
                        variable=self._use_max_bitrate, value=False,
                        command=self._toggle_bitrate).pack(side='left', padx=(14, 2))
        ttk.Radiobutton(br_row, text=T('radio_max_bitrate'),
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
        ttk.Button(foot, text=T('cancel_btn'),
                   command=self._cancel).pack(side='right', padx=(6, 0))
        ttk.Button(foot, text=T('btn_remember_selection'),
                   style='Playlist.TButton', command=self._ok).pack(side='right')

    # ── Shared-Logik ──────────────────────────────────────────────────────────

    def _get_row_texts(self) -> list[str]:
        """
        Returns a list of search terms (one string per row).
        Subclasses may override this; default: an empty string for every row.
        """
        return ['' for _ in self._row_frames]

    def _filter_rows(self):
        """Shows/hides rows based on the search text; updates the counter label."""
        term = self._search_var.get().lower().strip()
        texts = self._get_row_texts()
        visible = 0
        total   = len(self._row_frames)
        if len(self._row_visible) != total:
            self._row_visible = [True] * total
        for idx, (row, text) in enumerate(zip(self._row_frames, texts)):
            show = (not term) or (term in text.lower())
            if show == self._row_visible[idx]:
                visible += 1 if show else 0
                continue
            if show:
                row.pack(fill='x', padx=4, pady=1)
                visible += 1
            else:
                row.pack_forget()
            self._row_visible[idx] = show
        if term:
            self._filter_count_var.set(T('filter_visible', visible=visible, total=total))
        else:
            self._filter_count_var.set('')
        try:
            self._list_canvas.after_idle(
                lambda: self._list_canvas.configure(
                    scrollregion=self._list_canvas.bbox('all')))
        except Exception:
            pass

    def _queue_filter_rows(self):
        if self._filter_after_id is not None:
            try:
                self.after_cancel(self._filter_after_id)
            except Exception:
                pass
        self._filter_after_id = self.after(120, self._run_queued_filter_rows)

    def _run_queued_filter_rows(self):
        self._filter_after_id = None
        self._filter_rows()

    def _toggle_bitrate(self):
        mode = self._mode_var.get()
        if mode in ('audio_mp3', 'audio_opus'):
            use_max = self._use_max_bitrate.get()
            self._br_combo.configure(state='disabled' if use_max else 'readonly')
            self._br_label.configure(
                text=T('lbl_mp3_bitrate') if mode == 'audio_mp3' else T('lbl_opus_bitrate'))
        else:
            self._br_combo.configure(state='disabled')

    def _upd_count(self):
        n = sum(v.get() for v in self._vars)
        self._count_var.set(T('n_of_total_selected', n=n, total=len(self._vars)))

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
    Shows all (already deduplicated) entries of a playlist.
    Result: dict {'indices': [...], 'mode': str, 'bitrate': str} or None.

    checked_indices   – Set[int]: which entries were checked the last time it
                        was opened. None means: default behavior (all
                        downloadable entries checked).
    downloaded_stems  – dict[str, str]: stem → 'audio'|'video', files already
                        present in the destination folder. Matching entries
                        are marked white and get an icon.
    """

    # Background colors
    _BG_NORMAL     = ''          # empty = theme default
    _BG_DOWNLOADED = 'white'     # already downloaded
    _BG_UNAVAIL    = ''          # stays default, text red

    def __init__(self, parent, entries: list,
                 default_mode: str = 'audio_mp3',
                 default_bitrate: str = '320',
                 title_prefix: str = 'Playlist',
                 checked_indices: set | None = None,
                 downloaded_stems: set | None = None):
        self._entries          = entries
        self._checked_indices  = checked_indices   # None = first call
        self._downloaded_stems: dict = downloaded_stems or {}  # stem → 'audio'|'video'
        self.last_checked: set = set()             # filled on close
        self._row_frames: list = []                # for background updates
        super().__init__(
            parent,
            default_mode=default_mode,
            default_bitrate=default_bitrate,
            title=T('dlg_playlist_title', prefix=title_prefix),
            geometry=(980, 720),
            minsize=(700, 380),
            use_max_bitrate=True,
        )

    def _build_header(self, head: ttk.Frame):
        n_done = sum(
            1 for e in self._entries
            if self._is_downloaded(e) and not _is_unavailable_entry(e)
        )

        # Base text
        base_text = T('pl_header_count', n=len(self._entries))
        ttk.Label(
            head,
            text=base_text,
            font=('Segoe UI', 11, 'bold')
        ).pack(side='left')

        if n_done:
            ttk.Label(
                head,
                text=T('pl_header_done', n=n_done),
                foreground='blue',
                font=('Segoe UI', 11, 'bold')
            ).pack(side='left')

        # Buttons on the right
        sel_frame = ttk.Frame(head)
        sel_frame.pack(side='right')

        for lbl2, cmd, w in [
            (T('sel_all'),                self._all,                  8),
            (T('sel_none'),               self._none,                 8),
            (T('sel_invert'),             self._invert,               9),
            (T('sel_only_downloadable'),  self._select_downloadable, 18),
        ]:
            ttk.Button(
                sel_frame,
                text=lbl2,
                width=w,
                command=cmd
            ).pack(side='left', padx=2)

    def _is_downloaded(self, entry: dict) -> set:
        """
        Returns a set: {'audio'}, {'video'}, {'audio','video'} or set().
        Checks whether matching files exist in the audio AND/OR video folder.
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
            title  = entry.get('title') or T('entry_default_title', i=i+1)
            is_bad = _is_unavailable_entry(entry)
            is_done = self._is_downloaded(entry) if not is_bad else set()

            # Initial checkbox state:
            # – first call (checked_indices is None):
            #     unavailable → off; already downloaded → off; otherwise → on
            # – subsequent call: restore the saved state exactly
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

            Label(row, text=f'{i+1:>3}.',
                  width=4, font=('Segoe UI', 9),
                  foreground='#888', background=bg,
                  anchor='e').pack(side='left')

            dur   = entry.get('duration') or 0
            dur_s = f'  [{int(dur//60)}:{int(dur%60):02d}]' if dur else ''

            if is_bad:
                text_color = 'red'
                icon   = ''
                suffix = T('entry_unavailable_suffix')
            elif is_done:
                text_color = 'blue'
                # Both, audio only, video only
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
                text=f'{title}{dur_s}{icon}{suffix}',
                font=('Segoe UI', 9), anchor='w',
                foreground=text_color, background=bg,
            ).pack(side='left', fill='x', expand=True, padx=(4, 0))

    def _select_downloadable(self):
        for var, entry in zip(self._vars, self._entries):
            var.set(not _is_unavailable_entry(entry))

    def _get_row_texts(self) -> list[str]:
        """Returns the titles of all entries – for the search filter."""
        return [e.get('title') or T('entry_default_title', i=i+1)
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
            messagebox.showwarning(T('title_note'),
                T('msg_select_one_entry'), parent=self)
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
    Shows all entered URLs in a preview list.
    Result: dict {'urls': [...], 'mode': str, 'bitrate': str} or None.
    """

    def __init__(self, parent, urls: list,
                 default_mode: str = 'audio_mp3',
                 default_bitrate: str = '320'):
        self._urls = urls
        super().__init__(
            parent,
            default_mode=default_mode,
            default_bitrate=default_bitrate,
            title=T('dlg_multi_title'),
            geometry=(860, 640),
            minsize=(560, 360),
            use_max_bitrate=False,
        )

    def _build_header(self, head: ttk.Frame):
        ttk.Label(head, text=T('multi_url_header', n=len(self._urls)),
                  font=('Segoe UI', 11, 'bold')).pack(side='left')
        sel_frame = ttk.Frame(head)
        sel_frame.pack(side='right')
        for lbl, cmd in [(T('sel_all'), self._all), (T('sel_none'), self._none),
                         (T('sel_invert'), self._invert)]:
            ttk.Button(sel_frame, text=lbl, width=8,
                       command=cmd).pack(side='left', padx=2)

    def _populate_rows(self, inner: ttk.Frame):
        for i, url in enumerate(self._urls):
            var = BooleanVar(value=True)
            self._vars.append(var)
            row = ttk.Frame(inner)
            row.pack(fill='x', padx=4, pady=1)
            ttk.Checkbutton(row, variable=var).pack(side='left')
            ttk.Label(row, text=f'{i+1:>3}.', width=4,
                      font=('Segoe UI', 9), foreground='#888').pack(side='left')
            ttk.Label(row, text=url, font=('Segoe UI', 9), anchor='w',
                      foreground='#1565C0').pack(
                          side='left', fill='x', expand=True, padx=(4, 0))

    def _ok(self):
        sel = [self._urls[i] for i, v in enumerate(self._vars) if v.get()]
        if not sel:
            messagebox.showwarning(T('title_note'),
                T('msg_select_one_url'), parent=self)
            return
        self.result = {'urls': sel, 'mode': self._mode_var.get(),
                       'bitrate': self._bitrate_var.get()}
        self.destroy()

    def _get_row_texts(self) -> list[str]:
        """Returns URLs – for the search filter in the Multi-URL dialog."""
        return list(self._urls)


# ═════════════════════════════════════════════════════════════════════════════
#  Main app
# ═════════════════════════════════════════════════════════════════════════════
class ConfigMixin:
    """
    Configuration & filesystem-path handling.

    Contract – expects the following attributes to already exist on self
    (all set up in YouTubeDownloaderApp.__init__ before this mixin's
    methods are used):
        self._cfg                 dict, loaded via _config_load()
        self.audio_path_var       StringVar
        self.video_path_var       StringVar
        self.audio_to_mp3_var     BooleanVar
        self.audio_format_var     StringVar
        self.video_to_mp4_var     BooleanVar
        self.video_format_var     StringVar
        self.mp3_bitrate_var      StringVar
        self.open_folder_var      BooleanVar
        self.write_tags_var       BooleanVar
        self.write_thumbnail_var  BooleanVar
        self.cookies_browser_var  StringVar
    Also relies on module-level LANG / _config_load / _config_save / T /
    _open_folder and on messagebox/filedialog/path/makedirs imports.
    """

    def _apply_config(self, cfg: dict):
        """Applies loaded configuration values to the Tkinter variables."""
        parent_dir = path.dirname(path.abspath(__file__))
        default_audio = path.join(parent_dir, 'Downloads', 'audio')
        default_video = path.join(parent_dir, 'Downloads', 'video')

        self.audio_path_var.set(cfg.get('audio_path') or default_audio)
        self.video_path_var.set(cfg.get('video_path') or default_video)
        self.audio_to_mp3_var.set(cfg.get('audio_to_mp3', True))
        # Migration: old values 'm4a' and 'webm' → 'original'
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
        """Reads all current settings from the Tkinter variables."""
        return {
            'language':        LANG['code'],
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
        """Saves all current settings to yt_d_config.txt immediately."""
        _config_save(self._collect_config())

    def browse_folder(self, kind):
        d = filedialog.askdirectory(title=T('browse_dialog_title', kind=kind.capitalize()))
        if d:
            (self.audio_path_var if kind == 'audio' else self.video_path_var).set(d)

    def _open_folder_if_wanted(self, dest):
        """Automatically opens the destination folder after the download (if the option is active)."""
        if self.open_folder_var.get():
            _open_folder(dest)

    def _open_folder_direct(self, folder: str):
        """Opens the given folder immediately in the file manager (creates it if needed)."""
        if not folder:
            messagebox.showwarning(T('title_no_path'), T('msg_no_dest_path'))
            return
        self._ensure_dir(folder)
        _open_folder(folder)

    def _ensure_dir(self, d):
        if not path.exists(d):
            makedirs(d)


class I18nMixin:
    """
    Live UI-language switching (no restart needed).

    Contract – expects on self:
        self.root                 Tk root window
        self.i18n                 I18nRegistry (built in __init__)
        self.language_var         StringVar
        self.status_var           StringVar          (built by UIBuildMixin.create_widgets)
        self._pl_status_var       StringVar          (built by UIBuildMixin.create_widgets)
        self.video_combo          ttk.Combobox       (built by UIBuildMixin.create_widgets)
        self.audio_combo          ttk.Combobox       (built by UIBuildMixin.create_widgets)
        self.title_label          ttk.Label          (built by UIBuildMixin.create_widgets)
        self._sec_qd/_sec_pl/_sec_adv/_sec_so   dicts (built by UIBuildMixin.create_widgets)
        self._cfg                 dict               (ConfigMixin)
    Also relies on module-level LANG / LANGUAGES / T / _T_ORIGIN / _config_save.
    """

    def _update_window_title(self):
        self.root.title(T('window_title', v=__version__))

    @staticmethod
    def _retranslate_var(var: StringVar):
        """If *var* currently shows text that was produced by T() (which is
        true for both idle placeholders AND dynamic status text like
        'Playlist geladen: X (5/10)'), re-render it in the now-active
        language, keeping the same dynamic values. Text that was set
        directly rather than via T() is left untouched."""
        origin = _T_ORIGIN.get(var.get())
        if origin:
            key, kwargs = origin
            var.set(T(key, **kwargs))

    @staticmethod
    def _retranslate_combo(combo: ttk.Combobox):
        """Same idea as _retranslate_var, but for a Combobox whose displayed
        value is a single-item placeholder (e.g. 'Please analyze the URL
        first') rather than a real list of stream choices."""
        origin = _T_ORIGIN.get(combo.get())
        if origin:
            key, kwargs = origin
            combo['values'] = [T(key, **kwargs)]
            combo.current(0)

    @staticmethod
    def _retranslate_label(label: ttk.Label):
        """Same idea as _retranslate_var, but for a plain Label whose text
        was set directly via .config(text=...) instead of a StringVar
        (e.g. the video/playlist title bar)."""
        origin = _T_ORIGIN.get(label.cget('text'))
        if origin:
            key, kwargs = origin
            label.config(text=T(key, **kwargs))

    def set_language(self, code: str):
        """Switches the UI language live (no restart) and persists the choice."""
        if code not in LANGUAGES or code == LANG['code']:
            return
        LANG['code'] = code
        self.language_var.set(code)
        self._update_window_title()
        self.i18n.refresh()
        self._refresh_section_toggles()
        # Registered widgets (labels/buttons/checkboxes) are handled by
        # i18n.refresh() above. The lines below catch dynamic content that
        # was set once via T(...) at creation/last-update time and would
        # otherwise stay frozen in the old language until the next status
        # change or analysis run.
        self._retranslate_var(self.status_var)
        self._retranslate_var(self._pl_status_var)
        self._retranslate_combo(self.video_combo)
        self._retranslate_combo(self.audio_combo)
        self._retranslate_label(self.title_label)
        self._cfg['language'] = code
        _config_save(self._cfg)

    def _refresh_section_toggles(self):
        """Re-renders the arrow/title/action line of every collapsible
        section (Quick Download, Playlist, Advanced, Save Locations) in the
        newly active language, preserving each section's expanded state."""
        for sec in (self._sec_qd, self._sec_pl, self._sec_adv, self._sec_so):
            arrow  = '▼' if sec['expanded'] else '▶'
            action = T('action_collapse') if sec['expanded'] else T('action_expand')
            sec['lbl_var'].set(T('sec_toggle_line', arrow=arrow,
                                  icon=T(sec['icon_key']), action=action))


class UIBuildMixin:
    """
    Widget construction and generic widget-level interaction (scrolling,
    collapsible sections, URL textbox handling).

    Contract – expects on self:
        self.root, self._inner, self._canvas    (._inner/._canvas built here)
        self.i18n                  I18nRegistry
        self.ui_WEITE               int
        all the *_var Tkinter variables created in __init__ (audio_path_var,
            video_path_var, language_var, mp3_bitrate_var, ignore_video_var,
            ignore_audio_var, clicked_stream_video/audio, etc.)
        self._progress_pct          DoubleVar
        Methods provided by other mixins that create_widgets() wires up as
        callbacks: self.paste_link/self.analyze_url/self.clear_link
        (UIBuildMixin), self.open_playlist_editor/self.download_pending_playlist
        (PlaylistMixin), self.download_custom/self.quick_audio_mp3/... (DownloadMixin),
        self.set_language (I18nMixin), self.browse_folder (ConfigMixin),
        self._toggle_pause/self._request_cancel (DownloadMixin),
        self._save_config (ConfigMixin).
    Produces (consumed by other mixins): self._mf, self.url_text, self._url_hbar,
        self.title_label, self.status_var, self.progress, self._pct_label,
        self._pause_btn, self._cancel_btn, self._qd_frame/_pl_frame/_adv_frame/
        _so_frame plus the matching self._sec_* dicts, self.video_combo,
        self.audio_combo, self._bitrate_frame, self.bitrate_combo,
        self.lang_combo.
    """

    def setup_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('Primary.TButton',
                    padding=8, font=('Segoe UI', 10, 'bold'), background='#2196F3')  # blue
        s.configure('Action.TButton',
                    padding=8, font=('Segoe UI', 10, 'bold'), background='#4CAF50')  # green
        s.configure('Secondary.TButton', padding=8, font=('Segoe UI', 9))
        s.configure('Playlist.TButton',  padding=8, font=('Segoe UI', 10, 'bold'), background='#2196F3')
        s.configure('Title.TLabel',
                    font=('Segoe UI', 16, 'bold'), foreground='#FF0000')
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
            self.root.geometry(f'{cur_w}x{new_h}')
            self._initial_size_set = True

    def create_widgets(self):
        mf = ttk.Frame(self._inner, padding='4')
        mf.grid(row=0, column=0, sticky='nsew')
        self._inner.columnconfigure(0, weight=1)
        mf.columnconfigure(0, weight=1)
        self._mf = mf
        r = 0

        # ── Language switcher ───────────────────────────────────────────────
        # Placed top-right, above the URL box: the first thing anyone looks
        # for and out of the way of the main workflow.
        lang_bar = ttk.Frame(mf)
        lang_bar.grid(row=r, column=0, sticky='ew', pady=(0, 4))
        lang_bar.columnconfigure(0, weight=1)
        r += 1

        lang_frame = ttk.Frame(lang_bar)
        lang_frame.grid(row=0, column=1, sticky='e')
        lang_lbl = ttk.Label(lang_frame, style='Info.TLabel')
        self.i18n.reg(lang_lbl, 'lang_label')
        lang_lbl.pack(side='left', padx=(0, 4))
        self.lang_combo = ttk.Combobox(
            lang_frame, textvariable=self.language_var,
            values=LANGUAGES, width=5, state='readonly')
        self.lang_combo.pack(side='left')
        self.lang_combo.bind('<<ComboboxSelected>>',
                              lambda e: self.set_language(self.language_var.get()))
        # A readonly ttk.Combobox by default cycles through its values on
        # mouse-wheel scroll while the cursor hovers over it – easy to
        # trigger by accident while scrolling the page. Swallow wheel
        # events here so the language can only be changed deliberately,
        # via the dropdown itself.
        for wheel_event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.lang_combo.bind(wheel_event, lambda e: 'break')

        # ── URL input ────────────────────────────────────────────────────────
        uf = ttk.LabelFrame(mf, padding='10')
        self.i18n.reg(uf, 'url_frame_title')
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
        btn_paste = ttk.Button(btns, command=self.paste_link)
        self.i18n.reg(btn_paste, 'btn_paste')
        btn_paste.pack(fill='x', pady=2)
        btn_analyze = ttk.Button(btns, command=self.analyze_url, style='Primary.TButton')
        self.i18n.reg(btn_analyze, 'btn_analyze')
        btn_analyze.pack(fill='x', pady=2)
        btn_clear = ttk.Button(btns, command=self.clear_link)
        self.i18n.reg(btn_clear, 'btn_clear')
        btn_clear.pack(fill='x', pady=2)

        url_hint = ttk.Label(uf, style='Info.TLabel', wraplength=580)
        self.i18n.reg(url_hint, 'url_hint')
        url_hint.grid(row=2, column=0, columnspan=2, pady=(5, 0), sticky='w')

        self.title_label = ttk.Label(mf, text='',
                                     font=('Segoe UI', 13, 'italic'),
                                     foreground='red', wraplength=710)
        self.title_label.grid(row=r, column=0, pady=(0, 6), sticky='w')
        r += 1

        # ── Status & Progress ─────────────────────────────────────────────────
        sf = ttk.Frame(mf)
        sf.grid(row=r, column=0, sticky='ew', pady=(0, 4))
        sf.columnconfigure(1, weight=1)
        r += 1

        self.status_var = StringVar(value=T('status_ready'))
        status_lbl = ttk.Label(sf)
        self.i18n.reg(status_lbl, 'lbl_status')
        status_lbl.grid(row=0, column=0, sticky='w')
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
        self._pct_label = ttk.Label(pgf, text='', style='Info.TLabel',
                                    width=7, anchor='e')
        self._pct_label.grid(row=0, column=1, padx=(6, 0))
        self._pause_btn  = ttk.Button(pgf, width=10,
                                      command=self._toggle_pause, state='disabled')
        self.i18n.reg(self._pause_btn, 'pause_btn')
        self._pause_btn.grid(row=0, column=2, padx=(6, 0))
        self._cancel_btn = ttk.Button(pgf, width=12,
                                      command=self._request_cancel, state='disabled')
        self.i18n.reg(self._cancel_btn, 'cancel_btn')
        self._cancel_btn.grid(row=0, column=3, padx=(4, 0))

        # ── Schnell-Download ──────────────────────────────────────────────────
        qd_header = ttk.Frame(mf, relief='groove', padding=(6, 4))
        qd_header.grid(row=r, column=0, sticky='ew', pady=(0, 2))
        qd_header.columnconfigure(1, weight=1)
        r += 1

        self._qd_toggle_lbl = StringVar(value=T('sec_toggle_line', arrow='▶', icon=T('sec_qd_title'), action=T('action_expand')))
        lbl_qd = ttk.Label(qd_header, textvariable=self._qd_toggle_lbl,
                  font=('Segoe UI', 10, 'bold'), foreground='#1565C0', cursor='hand2')
        lbl_qd.grid(row=0, column=0, sticky='w')
        qd_header.bind('<Button-1>', lambda e: self._toggle_quickdownload())
        lbl_qd.bind('<Button-1>', lambda e: self._toggle_quickdownload())

        self._qd_frame = ttk.LabelFrame(mf, text='', padding='10')
        self._qd_frame.columnconfigure(0, weight=1)
        self._sec_qd = {
            'expanded': False, 'frame': self._qd_frame,
            'grid_row': r, 'lbl_var': self._qd_toggle_lbl,
            'icon_key': 'sec_qd_title', 'pady': (0, 8),
        }
        r += 1

        btn_row = ttk.Frame(self._qd_frame)
        btn_row.grid(row=0, column=0, sticky='n')
        for key, cmd in [
            ('qd_btn_audio_mp3',     self.quick_audio_mp3),
            ('qd_btn_audio_opus',    self.quick_audio_opus),
            ('qd_btn_video_mp4_m4a', self.quick_video_mp4_m4a),
            ('qd_btn_video_mp4',     self.quick_video_mp4),
            ('qd_btn_video_best',    self.quick_video_best),
        ]:
            btn = self.i18n.reg(
                ttk.Button(btn_row, style='Action.TButton', command=cmd, width=16),
                key)
            btn.pack(side='left', padx=4)

        self.i18n.reg(
            ttk.Label(self._qd_frame, style='Info.TLabel', wraplength=680),
            'qd_info1').grid(row=1, column=0, sticky='ew', pady=(6, 2))
        self.i18n.reg(
            ttk.Label(self._qd_frame, style='Info.TLabel', wraplength=680),
            'qd_info2').grid(row=2, column=0, pady=(4, 0), sticky='ew')

        # ── Playlist section ────────────────────────────────────────────────────
        pl_header = ttk.Frame(mf, relief='groove', padding=(6, 4))
        pl_header.grid(row=r, column=0, sticky='ew', pady=(0, 2))
        pl_header.columnconfigure(1, weight=1)
        r += 1

        self._pl_toggle_lbl = StringVar(value=T('sec_toggle_line', arrow='▶', icon=T('sec_pl_title'), action=T('action_expand')))
        lbl_pl = ttk.Label(pl_header, textvariable=self._pl_toggle_lbl,
                  font=('Segoe UI', 10, 'bold'), foreground='#1565C0', cursor='hand2')
        lbl_pl.grid(row=0, column=0, sticky='w')
        pl_header.bind('<Button-1>', lambda e: self._toggle_playlist())
        lbl_pl.bind('<Button-1>', lambda e: self._toggle_playlist())

        self._pl_frame = ttk.LabelFrame(mf, text='', padding='10')
        self._pl_frame.columnconfigure(0, weight=1)
        self._sec_pl = {
            'expanded': False, 'frame': self._pl_frame,
            'grid_row': r, 'lbl_var': self._pl_toggle_lbl,
            'icon_key': 'sec_pl_title', 'pady': (0, 8),
        }
        r += 1

        pl_btn_row = ttk.Frame(self._pl_frame)
        pl_btn_row.grid(row=0, column=0, sticky='n')
        self.i18n.reg(
            ttk.Button(pl_btn_row, command=self.open_playlist_editor,
                       style='Playlist.TButton', width=22),
            'btn_pl_edit').pack(side='left', padx=4)
        self.i18n.reg(
            ttk.Button(pl_btn_row, command=self.download_pending_playlist,
                       style='Action.TButton', width=22),
            'btn_pl_download').pack(side='left', padx=4)

        self._pl_status_var = StringVar(value=T('pl_status_none'))
        ttk.Label(self._pl_frame, textvariable=self._pl_status_var,
                  style='PlStatus.TLabel', wraplength=680).grid(
                      row=1, column=0, sticky='w', pady=(6, 0))
        self.i18n.reg(
            ttk.Label(self._pl_frame, style='Info.TLabel', wraplength=680),
            'pl_hint').grid(row=2, column=0, sticky='w', pady=(2, 0))

        # ── Erweiterte Optionen ───────────────────────────────────────────────
        adv_header = ttk.Frame(mf, relief='groove', padding=(6, 4))
        adv_header.grid(row=r, column=0, sticky='ew', pady=(0, 2))
        adv_header.columnconfigure(1, weight=1)
        r += 1

        self._adv_toggle_lbl = StringVar(value=T('sec_toggle_line', arrow='▶', icon=T('sec_adv_title'), action=T('action_expand')))
        lbl_adv = ttk.Label(adv_header, textvariable=self._adv_toggle_lbl,
                  font=('Segoe UI', 10, 'bold'), foreground='#1565C0', cursor='hand2')
        lbl_adv.grid(row=0, column=0, sticky='w')
        adv_header.bind('<Button-1>', lambda e: self._toggle_advanced())
        lbl_adv.bind('<Button-1>', lambda e: self._toggle_advanced())

        self._adv_frame = ttk.LabelFrame(mf, text='', padding='10')
        self._adv_frame.columnconfigure(0, weight=3)
        self._adv_frame.columnconfigure(1, weight=1)
        self._sec_adv = {
            'expanded': False, 'frame': self._adv_frame,
            'grid_row': r, 'lbl_var': self._adv_toggle_lbl,
            'icon_key': 'sec_adv_title', 'pady': (0, 10),
        }
        r += 1

        # ── Section: Video Stream ─────────────────────────────────────────────
        video_lf = self.i18n.reg(
            ttk.LabelFrame(self._adv_frame, padding=(8, 4)), 'lf_video_stream')
        video_lf.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        video_lf.columnconfigure(0, weight=1)

        video_top = ttk.Frame(video_lf)
        video_top.grid(row=0, column=0, sticky='ew')
        video_top.columnconfigure(0, weight=1)

        self.video_combo = ttk.Combobox(video_top,
                                        textvariable=self.clicked_stream_video,
                                        width=68, state='readonly')
        self.video_combo.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        self.video_combo['values'] = [T('ph_analyse')]
        self.video_combo.current(0)

        video_opts = ttk.Frame(video_lf)
        video_opts.grid(row=1, column=0, sticky='w', pady=(4, 0))
        self.i18n.reg(ttk.Label(video_opts, style='Info.TLabel'),
                       'lbl_video_format').pack(side='left', padx=(0, 6))
        for key, val in [('radio_original', 'original'), ('radio_mp4', 'mp4'), ('radio_mkv', 'mkv')]:
            self.i18n.reg(
                ttk.Radiobutton(video_opts, variable=self.video_format_var, value=val),
                key).pack(side='left', padx=(0, 4))
        ttk.Separator(video_lf, orient='horizontal').grid(row=2, column=0, sticky='ew', pady=(6, 4))
        ignore_video_row = ttk.Frame(video_lf)
        ignore_video_row.grid(row=3, column=0, sticky='w')
        self.i18n.reg(
            ttk.Checkbutton(ignore_video_row, variable=self.ignore_video_var),
            'chk_ignore_video').pack(side='left')

        # ── Section: Audio Stream ─────────────────────────────────────────────
        audio_lf = self.i18n.reg(
            ttk.LabelFrame(self._adv_frame, padding=(8, 4)), 'lf_audio_stream')
        audio_lf.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        audio_lf.columnconfigure(0, weight=1)

        self.audio_combo = ttk.Combobox(audio_lf,
                                        textvariable=self.clicked_stream_audio,
                                        width=68, state='readonly')
        self.audio_combo.grid(row=0, column=0, sticky='ew', pady=(0, 4))
        self.audio_combo['values'] = [T('ph_analyse')]
        self.audio_combo.current(0)

        audio_opts = ttk.Frame(audio_lf)
        audio_opts.grid(row=1, column=0, sticky='w')

        self.i18n.reg(ttk.Label(audio_opts, style='Info.TLabel'),
                       'lbl_audio_format').pack(side='left', padx=(0, 6))
        for key, val in [('radio_original', 'original'), ('radio_opus', 'opus'), ('radio_mp3', 'mp3')]:
            self.i18n.reg(
                ttk.Radiobutton(audio_opts, variable=self.audio_format_var,
                                value=val, command=self._toggle_bitrate_state),
                key).pack(side='left', padx=(0, 4))

        # Bitrate frame – only visible when MP3 is active, appears inline on the right
        self._bitrate_frame = ttk.Frame(audio_opts)
        brow = self._bitrate_frame
        self.i18n.reg(ttk.Label(brow, style='Info.TLabel'),
                       'lbl_bitrate_inline').pack(side='left')
        self.bitrate_combo = ttk.Combobox(
            brow, textvariable=self.mp3_bitrate_var,
            values=['320', '256', '192', '160', '128', '96', '64'],
            width=6, state='readonly', style='Bitrate.TCombobox')
        self.bitrate_combo.pack(side='left', padx=(4, 0))
        self.i18n.reg(ttk.Label(brow, style='Info.TLabel'),
                       'lbl_kbps').pack(side='left', padx=(2, 0))

        ttk.Separator(audio_lf, orient='horizontal').grid(row=2, column=0, sticky='ew', pady=(6, 4))
        ignore_audio_row = ttk.Frame(audio_lf)
        ignore_audio_row.grid(row=3, column=0, sticky='w')
        self.i18n.reg(
            ttk.Checkbutton(ignore_audio_row, variable=self.ignore_audio_var),
            'chk_ignore_audio').pack(side='left')

        self.i18n.reg(
            ttk.Button(self._adv_frame, command=self.download_custom, style='Action.TButton'),
            'btn_download_custom').grid(row=2, column=0, columnspan=2, pady=(4, 0))

        # ── Speicherorte & Optionen ───────────────────────────────────────────
        so_header = ttk.Frame(mf, relief='groove', padding=(6, 4))
        so_header.grid(row=r, column=0, sticky='ew', pady=(0, 2))
        so_header.columnconfigure(1, weight=1)
        r += 1

        self._so_toggle_lbl = StringVar(value=T('sec_toggle_line', arrow='▶', icon=T('sec_so_title'), action=T('action_expand')))
        lbl_so = ttk.Label(so_header, textvariable=self._so_toggle_lbl,
                  font=('Segoe UI', 10, 'bold'), foreground='#1565C0', cursor='hand2')
        lbl_so.grid(row=0, column=0, sticky='w')
        so_header.bind('<Button-1>', lambda e: self._toggle_saveopts())
        lbl_so.bind('<Button-1>', lambda e: self._toggle_saveopts())

        self._so_frame = ttk.LabelFrame(mf, text='', padding='10')
        self._so_frame.columnconfigure(1, weight=1)
        self._sec_so = {
            'expanded': False, 'frame': self._so_frame,
            'grid_row': r, 'lbl_var': self._so_toggle_lbl,
            'icon_key': 'sec_so_title', 'pady': (0, 10),
        }
        r += 1

        def _path_row(grid_row: int, label_key: str, path_var: StringVar, kind: str):
            self.i18n.reg(ttk.Label(self._so_frame), label_key).grid(
                row=grid_row, column=0, sticky='w', pady=3)
            ttk.Entry(self._so_frame, textvariable=path_var,
                      width=50).grid(row=grid_row, column=1, padx=(8, 4), sticky='ew')
            btn_frame = ttk.Frame(self._so_frame)
            btn_frame.grid(row=grid_row, column=2, sticky='w')
            self.i18n.reg(
                ttk.Button(btn_frame, command=lambda k=kind: self.browse_folder(k),
                           style='Secondary.TButton'),
                'btn_browse').pack(side='left')
            self.i18n.reg(
                ttk.Button(btn_frame, command=lambda v=path_var: self._open_folder_direct(v.get()),
                           style='Secondary.TButton'),
                'btn_open').pack(side='left', padx=(4, 0))

        _path_row(0, 'lbl_audio_path', self.audio_path_var, 'audio')
        _path_row(1, 'lbl_video_path', self.video_path_var, 'video')

        opt_row = ttk.Frame(self._so_frame)
        opt_row.grid(row=2, column=0, columnspan=3, sticky='w', pady=(8, 2))
        self.i18n.reg(
            ttk.Checkbutton(opt_row, variable=self.open_folder_var),
            'chk_open_folder').pack(side='left', padx=(0, 20))
        self.i18n.reg(
            ttk.Checkbutton(opt_row, variable=self.write_tags_var),
            'chk_write_tags').pack(side='left', padx=(0, 20))
        self.i18n.reg(
            ttk.Checkbutton(opt_row, variable=self.write_thumbnail_var),
            'chk_write_thumb').pack(side='left')

        # ── Cookies row ────────────────────────────────────────────────────────
        ck_row = ttk.Frame(self._so_frame)
        ck_row.grid(row=4, column=0, columnspan=3, sticky='w', pady=(6, 2))
        self.i18n.reg(ttk.Label(ck_row, style='Info.TLabel'),
                       'lbl_cookies').pack(side='left', padx=(0, 6))
        _BROWSERS = ['', 'chrome', 'firefox', 'edge', 'brave', 'opera', 'safari']
        ck_combo = ttk.Combobox(ck_row, textvariable=self.cookies_browser_var,
                                values=_BROWSERS, width=10, state='readonly')
        ck_combo.pack(side='left')
        self.i18n.reg(ttk.Label(ck_row, style='Info.TLabel'),
                       'lbl_cookies_hint').pack(side='left')

        self.root.after(0, lambda: self._toggle_quickdownload(force_open=True))
        self.root.after(0, self._toggle_bitrate_state)

        # ── Automatically save settings ───────────────────────────────
        for var in (
            self.audio_path_var, self.video_path_var,
            self.audio_to_mp3_var, self.audio_format_var,
            self.video_to_mp4_var, self.video_format_var, self.mp3_bitrate_var,
            self.open_folder_var, self.write_tags_var,
            self.write_thumbnail_var, self.cookies_browser_var,
        ):
            var.trace_add('write', self._save_config)

    def _get_urls(self) -> list:
        raw = self.url_text.get('1.0', END)
        return [l.strip() for l in raw.splitlines()
                if l.strip().startswith('http')]

    def _toggle_bitrate_state(self):
        if self.audio_format_var.get() == 'mp3':
            self._bitrate_frame.pack(side='left', padx=(4, 0))
        else:
            self._bitrate_frame.pack_forget()

    def _toggle_section(self, sec: dict, force_open: bool = False):
        if force_open and sec['expanded']:
            return
        sec['expanded'] = force_open or (not sec['expanded'])
        arrow  = '▼' if sec['expanded'] else '▶'
        action = T('action_collapse') if sec['expanded'] else T('action_expand')
        sec['lbl_var'].set(T('sec_toggle_line', arrow=arrow,
                              icon=T(sec['icon_key']), action=action))
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

    def paste_link(self):
        try:
            self.url_text.insert(END, self.root.clipboard_get().strip() + '\n')
            self.set_status(T('status_link_pasted'))
            self.root.after(50, self._on_url_change)
        except Exception as e:
            messagebox.showerror(T('title_error'), T('msg_clipboard_empty', e=e))

    def clear_link(self):
        self.url_text.delete('1.0', END)
        self.title_label.config(text='')
        self._video_formats = []
        self._audio_formats = []
        for cb in (self.video_combo, self.audio_combo):
            cb['values'] = [T('ph_analyse')]
            cb.current(0)
        self._reset_progress()
        self._reset_pending_playlist()
        self.set_status(T('status_fields_cleared'))


class AnalysisMixin:
    """
    URL analysis: builds yt-dlp option dicts and inspects a URL/playlist
    without downloading anything.

    Contract – expects on self:
        self.cookies_browser_var   StringVar   (ConfigMixin's config surface)
        self._video_formats        list        (set in __init__, filled here)
        self._audio_formats        list        (set in __init__, filled here)
        self.write_tags_var        BooleanVar
        self.write_thumbnail_var   BooleanVar
        self.root                  Tk root
        self.title_label, self.video_combo, self.audio_combo   (UIBuildMixin)
        self._pl_status_var                                    (UIBuildMixin)
        self._pending_playlist     dict | None (set in __init__, may be filled here)
        self._toggle_advanced/_toggle_playlist                 (UIBuildMixin)
        self._status_async/self.set_status                     (DownloadMixin)
        self._fetch_playlist_flat                               (PlaylistMixin)
    """

    def _base_opts(self) -> dict:
        """
        Minimal yt-dlp options – only the ffmpeg path and cookies.
        Used for both analysis AND download.
        No writethumbnail, no postprocessors – so that analysis never
        writes image files to disk.
        """
        opts = {
            'ffmpeg_location': shutil.which('ffmpeg') or '',
            'quiet':       False,
            'no_warnings': False,
        }
        # Register Node.js as a JS runtime (yt-dlp otherwise only looks for Deno).
        # The internal format is a dict: {'runtime_name': {optional 'path': ...}}
        # Supported keys: 'deno', 'node', 'bun', 'quickjs'
        node_path = shutil.which('node')
        if not node_path and os.path.exists('/usr/bin/node'):
            # Fallback for Linux systems where node isn't in PATH
            node_path = '/usr/bin/node'
        if node_path:
            opts['js_runtimes'] = {'node': {'path': node_path}}
        browser = self.cookies_browser_var.get().strip()
        if browser:
            # cookiesfrombrowser expects a tuple: (browser, profile, keyring, container)
            # Fill missing fields with None so yt-dlp doesn't crash
            opts['cookiesfrombrowser'] = (browser, None, None, None)
        return opts

    def _download_opts(self, mode: str = '') -> dict:
        """
        Extended yt-dlp options for real downloads:
        _base_opts() + metadata tags + embed thumbnail (if enabled).
        writethumbnail is only ever set here – never during analysis.

        mode: 'audio_mp3' | 'audio_opus' | 'video_mp4' | 'video_best' | ''
              For video modes, EmbedThumbnail is left out.

        Opus: yt-dlp would convert the thumbnail to PNG (→ 800 KB!),
              because it expects PNG in the OGG tags.
              A postprocessor_hook instead converts the downloaded
              .webp/.jpg to JPEG – EmbedThumbnail then embeds the JPEG.
        """
        opts = self._base_opts()

        # static_ffmpeg provides both ffmpeg AND ffprobe → resolve directly via which
        ffprobe_exe = shutil.which('ffprobe')
        if ffprobe_exe:
            opts['ffprobe_location'] = ffprobe_exe

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
                    # ── MP3: do NOT delegate EmbedThumbnail to yt-dlp ──────
                    # yt-dlp konvertiert .webp → .png (unkomprimiert, ~500-800 KB!)
                    # and embeds that huge PNG as an ID3 APIC tag.
                    # Instead, _embed_thumbnail_as_jpeg handles the job:
                    # .webp/.jpg → JPEG 500px (≈ 30–50 KB) → ID3 via mutagen.
                    opts['convert_thumbnails'] = False
                    opts['_mp3_embed_ffmpeg']  = opts.get('ffmpeg_location') or 'ffmpeg'
                    # EmbedThumbnail is deliberately NOT added to pps

                elif mode == 'audio_opus':
                    # ── Opus: do NOT use EmbedThumbnail ─────────────────────
                    # The thumbnail is embedded directly AFTER the download
                    # (via _embed_thumbnail_as_jpeg), not via a hook.
                    # otherwise yt-dlp would embed it as an uncompressed PNG (~800KB).
                    opts['convert_thumbnails'] = False
                    opts['_opus_embed_ffmpeg'] = opts.get('ffmpeg_location') or 'ffmpeg'
                    # EmbedThumbnail is deliberately NOT added to pps

                else:
                    # Andere Audio-Formate: Standard yt-dlp EmbedThumbnail
                    pps.append({'key': 'EmbedThumbnail'})

            else:
                # ── Video: gleiche Logik wie Audio ──────────────────────────
                # _embed_thumbnail_as_jpeg takes care of the job after the download:
                # .webp/.jpg → JPEG 500px → FFmpeg remux (no yt-dlp EmbedThumbnail).
                opts['convert_thumbnails'] = False
                opts['_video_embed_ffmpeg'] = opts.get('ffmpeg_location') or 'ffmpeg'
                # EmbedThumbnail is deliberately NOT added to pps
        if pps:
            opts['postprocessors'] = pps
        return opts

    def analyze_url(self):
        def worker():
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning(T('title_error'), T('msg_no_valid_url'))
                return
            url = urls[0]
            p   = _parse_yt_url(url)
            self._status_async(T('status_analyzing'), True)
            try:
                # ── Case 1: video with playlist context ───────────────────────
                if p['is_video_in_playlist']:
                    pl_entries, pl_title = self._fetch_playlist_flat(p['list_id'])

                    target_url = _resolve_entry_from_playlist(pl_entries, p) or url

                    opts_v = self._base_opts()
                    opts_v['noplaylist'] = True
                    with yt_dlp.YoutubeDL(opts_v) as ydl:
                        full = ydl.extract_info(target_url, download=False)

                    vfmts, afmts = self._extract_formats(full)
                    self._video_formats = vfmts
                    self._audio_formats = afmts
                    video_title = full.get('title', '')
                    index_hint  = T('video_title_index_hint', idx=p['index']) if p['index'] else ''
                    cnt = len(pl_entries)
                    cnt_dl = sum(1 for e in pl_entries if not _is_unavailable_entry(e))

                    if pl_entries:
                        self._pending_playlist = {
                            'entries': pl_entries,
                            'title':   pl_title,
                            'list_id': p['list_id'],
                        }

                    status_txt = T('status_analysis_done_pl',
                                    vc=len(vfmts), ac=len(afmts),
                                    pl=(T('status_analysis_done_pl_suffix', done=cnt_dl, total=cnt)
                                        if cnt else ''))
                    pl_status  = (
                        T('pl_status_loaded', t=pl_title, done=cnt_dl, total=cnt)
                        if cnt else T('pl_status_load_failed'))

                    self.root.after(0, lambda: (
                        self._toggle_advanced(force_open=True),
                        self._toggle_playlist(force_open=True),
                        self.title_label.config(
                            text=T('video_title_bar', t=video_title) + index_hint
                                 + (T('video_title_with_playlist', t=pl_title) if pl_title else '')),
                        self.video_combo.__setitem__('values',
                            [f['label'] for f in vfmts] + [T('no_video')]),
                        self.video_combo.current(0),
                        self.audio_combo.__setitem__('values',
                            [f['label'] for f in afmts] + [T('no_audio')]),
                        self.audio_combo.current(0),
                        self._pl_status_var.set(pl_status),
                        self.set_status(status_txt)))
                    return

                # ── Case 2: pure playlist URL ──────────────────────────────────
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
                            text=T('pl_title_bar', t=pl_title, done=cnt_dl, total=cnt)),
                        self.set_status(T('status_playlist_detected', done=cnt_dl, total=cnt)),
                        self._toggle_playlist(force_open=True),
                        self._pl_status_var.set(
                            T('pl_status_loaded', t=pl_title, done=cnt_dl, total=cnt)),
                        self.video_combo.__setitem__('values', [T('ph_playlist')]),
                        self.video_combo.current(0),
                        self.audio_combo.__setitem__('values', [T('ph_playlist')]),
                        self.audio_combo.current(0)))
                    return

                # ── Case 3: single video without playlist ──────────────────────
                opts2 = self._base_opts()
                opts2['noplaylist'] = True
                with yt_dlp.YoutubeDL(opts2) as ydl:
                    full = ydl.extract_info(url, download=False)

                vfmts, afmts = self._extract_formats(full)
                self._video_formats = vfmts
                self._audio_formats = afmts

                self.root.after(0, lambda: (
                    self._toggle_advanced(force_open=True),
                    self.title_label.config(text=T('video_title_bar', t=full.get('title', ''))),
                    self.video_combo.__setitem__('values',
                        [f['label'] for f in vfmts] + [T('no_video')]),
                    self.video_combo.current(0),
                    self.audio_combo.__setitem__('values',
                        [f['label'] for f in afmts] + [T('no_audio')]),
                    self.audio_combo.current(0),
                    self.set_status(
                        T('status_analysis_done_vfa', vc=len(vfmts), ac=len(afmts)))))

            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda m=err_msg: (
                    self.set_status(T('status_analysis_error')),
                    messagebox.showerror(T('title_error'), T('msg_analysis_error', m=m))))

        Thread(target=worker, daemon=True).start()

    def _extract_formats(self, full: dict) -> tuple[list, list]:
        """Extracts and sorts the video and audio format lists from yt-dlp info."""
        vfmts, afmts = [], []
        for f in full.get('formats', []):
            vc  = f.get('vcodec', 'none')
            ac  = f.get('acodec', 'none')
            fid = f.get('format_id', '?')
            ext = f.get('ext', '?')
            sz  = f.get('filesize') or f.get('filesize_approx') or 0
            smb = round(sz / 1048576, 1) if sz else 0
            ss  = f'  •  {smb}MB' if smb else ''
            if vc != 'none' and ac == 'none':
                res = f.get('resolution') or f"{f.get('height','?')}p"
                fps = f.get('fps') or ''
                lbl = (f'{ext}  •  {res}'
                       f"{'  •  '+str(fps)+'fps' if fps else ''}"
                       f'  •  {vc}{ss}  [id:{fid}]')
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


class PlaylistMixin:
    """
    Playlist loading, the playlist/multi-URL selection dialogs, and the
    thread-safe popup handshake between the download worker thread and
    the Tk GUI thread.

    Contract – expects on self:
        self.root                  Tk root
        self._pending_playlist     dict | None   (set in __init__)
        self._playlist_event       threading.Event | None (set in __init__)
        self._playlist_result      dict | None   (set in __init__)
        self._playlist_cancel      bool          (set in __init__)
        self._cfg                  dict          (ConfigMixin)
        self.quick_bitrate_var     StringVar
        self.audio_path_var/self.video_path_var  StringVar (ConfigMixin)
        self._status_async/self.set_status                      (DownloadMixin)
        self._run_urls                                           (DownloadMixin)
        self._get_urls                                           (UIBuildMixin)
    """

    def _fetch_playlist_flat(self, list_id: str) -> tuple[list, str]:
        """
        Flat-extracts a playlist's entries (metadata only, no per-video
        info) by list_id. Returns ([], '') on any failure – callers then
        fall back to treating the URL as a single video.
        """
        try:
            opts = self._base_opts()
            opts['extract_flat'] = True
            opts['noplaylist']   = False
            playlist_url = f'https://www.youtube.com/playlist?list={list_id}'
            with yt_dlp.YoutubeDL(opts) as ydl:
                pl_info = ydl.extract_info(playlist_url, download=False)
            if pl_info:
                entries = _deduplicate_entries(list(pl_info.get('entries', [])))
                return entries, pl_info.get('title', '')
        except Exception:
            pass
        return [], ''

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
        # Remember the checkbox state (even on cancel)
        if self._pending_playlist is not None:
            self._pending_playlist['checked'] = dlg.last_checked
        if self._playlist_event:
            self._playlist_event.set()

    def _request_playlist_popup(self, entries, default_mode, default_bitrate,
                                 title_prefix='Playlist') -> dict | None:
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

    def open_playlist_editor(self):
        def worker():
            existing = self._pending_playlist

            if existing and existing.get('entries'):
                entries  = existing['entries']
                pl_title = existing.get('title') or T('pl_title_unknown')
                self._status_async(T('status_playlist_cached', t=pl_title, n=len(entries)))
            else:
                urls = self._get_urls()
                if not urls:
                    self.root.after(0, lambda: messagebox.showwarning(
                        T('title_no_url'), T('msg_no_playlist_url')))
                    return
                url = urls[0]
                p   = _parse_yt_url(url)

                fetch_url = (f"https://www.youtube.com/playlist?list={p['list_id']}"
                             if p['is_video_in_playlist'] and p['list_id'] else url)

                self._status_async(T('status_playlist_loading'), True)
                self._update_pl_status(T('pl_status_loading_info'))

                try:
                    opts = self._base_opts()
                    opts['extract_flat'] = True
                    opts['noplaylist']   = False
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(fetch_url, download=False)
                except Exception as e:
                    err = str(e)
                    self.root.after(0, lambda m=err: (
                        self.set_status(T('status_load_error')),
                        messagebox.showerror(T('title_error'), T('msg_playlist_unavailable', m=m))))
                    self._update_pl_status(T('pl_status_error'))
                    return

                if info.get('_type') != 'playlist':
                    self.root.after(0, lambda: messagebox.showinfo(
                        T('title_no_playlist'), T('msg_not_a_playlist')))
                    self._update_pl_status(T('pl_status_none_detected'))
                    self._status_async(T('status_playlist_none_detected'))
                    return

                entries  = _deduplicate_entries(list(info.get('entries', [])))
                pl_title = info.get('title', 'Unbekannte Playlist')

                if not entries:
                    self.root.after(0, lambda: messagebox.showinfo(
                        T('title_empty'), T('msg_playlist_empty')))
                    self._update_pl_status(T('pl_status_empty'))
                    return

            self._update_pl_status(
                T('pl_status_choose', t=pl_title, n=len(entries)))
            self._status_async(T('status_playlist_with_n', t=pl_title, n=len(entries)))

            # Determine already-downloaded files (scan audio + video folders)
            # dl_stems: {stem: set('audio'|'video')} – a stem may exist in both folders
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
                title_prefix    = T('pl_title_prefix', t=pl_title))

            if result is None:
                self._update_pl_status(
                    T('pl_status_edit_cancelled', n=len(entries)))
                self._status_async(T('status_cancelled'))
                return

            # Remember mode & bitrate for the next time it's opened
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
            mode_lbl = _modes_dict().get(result['mode'], result['mode'])
            self._update_pl_status(
                T('pl_status_ready', t=pl_title, n=n_sel, total=len(entries), mode=mode_lbl))
            self._status_async(T('status_playlist_ready_n', n=n_sel))

        self._update_pl_status(T('pl_status_preparing'))
        Thread(target=worker, daemon=True).start()

    def download_pending_playlist(self):
        def worker():
            pending = self._pending_playlist
            if not pending or not pending.get('entries'):
                self.root.after(0, lambda: messagebox.showwarning(
                    T('title_no_playlist'), T('msg_need_playlist_analyze')))
                return

            entries = pending['entries']
            result  = pending.get('result')

            if result is None:
                # Playlist analyzed but not yet edited:
                # Show the dialog now so mode/selection can be set
                pl_title = pending.get('title', '')
                result = self._request_playlist_popup(
                    entries,
                    default_mode    = self._cfg.get('playlist_mode', 'audio_mp3'),
                    default_bitrate = self._cfg.get('playlist_bitrate', '0'),
                    title_prefix    = T('pl_title_prefix', t=pl_title))
                if result is None:
                    self._status_async(T('status_cancelled'))
                    return

            mode    = result['mode']
            bitrate = result['bitrate']
            prefix  = _modes_dict().get(mode, 'Download')

            resolved = [_entry_url(entries[i]) for i in result['indices']]
            if not resolved:
                self.root.after(0, lambda: messagebox.showwarning(
                    T('title_empty'), T('msg_no_urls_to_download')))
                return

            self._pending_playlist = None
            self._update_pl_status(T('pl_status_downloading'))
            self._run_urls(resolved, mode, bitrate, prefix)
            self._update_pl_status(T('pl_status_none'))

        Thread(target=worker, daemon=True).start()

    def _reset_pending_playlist(self):
        self._pending_playlist = None
        self._pl_status_var.set(T('pl_status_none'))

    def _update_pl_status(self, text: str):
        self.root.after(0, lambda: self._pl_status_var.set(text))


class DownloadMixin:
    """
    Building download-time yt-dlp options, running downloads (single URLs,
    playlists, channels, custom stream selections, quick-download presets),
    and progress/pause/cancel state shared by all of the above.

    Contract – expects on self:
        self.root                  Tk root
        self._cancel_flag           bool               (set in __init__)
        self._pause_event           threading.Event    (set in __init__)
        self._download_active       bool               (set in __init__)
        self._pause_btn/self._cancel_btn                (UIBuildMixin)
        self.status_var             StringVar           (UIBuildMixin)
        self._progress_pct          DoubleVar           (set in __init__)
        self._pct_label                                  (UIBuildMixin)
        self._last_status_msg / self._last_progress_update /
            self._progress_update_interval / self._indeterminate_progress_value
            (set in __init__)
        self.video_path_var/self.audio_path_var          (ConfigMixin)
        self.video_format_var/self.audio_format_var/self.mp3_bitrate_var
        self.write_tags_var/self.write_thumbnail_var      (ConfigMixin)
        self.clicked_stream_video/self.clicked_stream_audio
        self.ignore_video_var/self.ignore_audio_var
        self._video_formats/self._audio_formats           (AnalysisMixin)
        self._pending_playlist                             (PlaylistMixin)
        self._cfg                                          (ConfigMixin)
        self._base_opts/self._download_opts                (AnalysisMixin)
        self._fetch_playlist_flat/self._request_playlist_popup/
            self._request_multiurl_popup                   (PlaylistMixin)
        self._get_urls/self._ensure_dir                    (UIBuildMixin/ConfigMixin)
    """

    def _make_hook(self, prefix='Lade...', idx=0, total=1):
        def check_cancel():
            if self._cancel_flag:
                raise Exception('Download abgebrochen.')

        def hook(d):
            # ── Abbrechen: sofort Exception werfen → yt-dlp bricht ab ──────────
            check_cancel()

            # ── Pause: block until Resume is pressed ────────────────────────────
            if not self._pause_event.is_set():
                self._pause_event.wait()
                # Check for cancel again after waiting
                check_cancel()

            if d['status'] == 'downloading':
                tb = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                db = d.get('downloaded_bytes', 0)
                sp = d.get('speed') or 0
                sp_s = f'  •  {sp/1024/1024:.1f} MB/s' if sp else ''
                if tb > 0:
                    item_pct = db / tb * 100
                    overall  = (idx / total * 100) + (item_pct / total)
                    lbl = f'{idx+1}/{total}' if total > 1 else f'{item_pct:.0f} %'
                    self._queue_progress_update(
                        progress=overall,
                        pct_label=lbl,
                        status_msg=f'{prefix}{sp_s}')
                else:
                    self._indeterminate_progress_value = (
                        self._indeterminate_progress_value + 1) % 99
                    self._queue_progress_update(
                        progress=self._indeterminate_progress_value)
            elif d['status'] == 'finished':
                p = (idx + 1) / total * 100
                self._queue_progress_update(
                    progress=p,
                    pct_label=f'{p:.0f} %',
                    force=True)
        return hook

    def _show_error_blocking(self, msg_key: str, **kwargs):
        """
        Shows an error messagebox from a worker thread and blocks (max 15s)
        until it has been scheduled on the GUI thread, so the worker doesn't
        race ahead (e.g. into further status updates) before the user has
        actually seen the error.
        """
        ev = threading.Event()
        self.root.after(0, lambda: (
            messagebox.showerror(T('title_error'), T(msg_key, **kwargs)),
            ev.set()))
        ev.wait(15)

    def _apply_audio_extract(self, opts: dict, codec: str, quality: str) -> dict:
        """
        Prepends an FFmpegExtractAudio postprocessor (codec/quality) to opts,
        replacing any previous one. Shared by the quick-download and the
        custom-download path so both build MP3/Opus options identically.

        For 'opus' this also disables yt-dlp's own thumbnail handling and
        drops a queued EmbedThumbnail entry, because yt-dlp would otherwise
        embed an uncompressed PNG (~800 KB) – see _download_opts docstring.
        _embed_thumbnail_as_jpeg takes care of the thumbnail afterwards.
        """
        pps  = opts.get('postprocessors', [])
        drop = {'FFmpegExtractAudio'} | ({'EmbedThumbnail'} if codec == 'opus' else set())
        opts['postprocessors'] = [{
            'key':              'FFmpegExtractAudio',
            'preferredcodec':   codec,
            'preferredquality': quality,
        }] + [p for p in pps if p.get('key') not in drop]
        if codec == 'opus':
            opts['convert_thumbnails'] = False
            opts['_opus_embed_ffmpeg'] = opts.get('ffmpeg_location') or 'ffmpeg'
        return opts

    def _build_opts_for_mode(self, mode: str, bitrate: str) -> tuple[dict, str]:
        """Returns (opts, dest) matching the given mode."""
        opts = self._download_opts(mode)

        if mode == 'audio_mp3':
            dest = self.audio_path_var.get()
            opts.update({
                'format': 'bestaudio/best',
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })
            self._apply_audio_extract(opts, 'mp3', bitrate)

        elif mode == 'audio_opus':
            dest = self.audio_path_var.get()
            opts.update({
                'format': ('bestaudio[ext=webm][acodec=opus]'
                           '/bestaudio[acodec=opus]'
                           '/bestaudio/best'),
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })
            # Always re-encode to .opus (OGG container, lossless with quality 0)
            # → clean extension, metadata & thumbnails are supported
            self._apply_audio_extract(opts, 'opus', '0')

        elif mode == 'video_mp4_m4a':
            # MP4 video + M4A audio: both streams exist natively on YouTube's servers
            # → no re-encoding needed, fast merging, maximum compatibility
            # (no AV1 codec, also works in players without AV1 support)
            dest = self.video_path_var.get()
            opts.update({
                'format': ('bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]'
                           '/bestvideo[ext=mp4]+bestaudio[ext=m4a]'
                           '/bestvideo[ext=mp4]+bestaudio'
                           '/best'),
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
                'merge_output_format': 'mp4',
            })

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
                # No merge_output_format – yt-dlp chooses the extension itself
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
                # Always MKV: supports all codecs (including webm/vp9/av1/opus)
                # and allows metadata + thumbnail embedding
                'merge_output_format': 'mkv',
            })

        return opts, dest

    def _maybe_embed_thumbnail(self, opts: dict, fp: str):
        """
        Embeds the thumbnail as a JPEG – a shared helper method used by
        _run_urls, the channel loop, and download_custom.
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
        """Downloads an already-resolved list of URLs."""
        total = len(urls)
        done  = []
        skipped = []

        self._cancel_flag = False
        self._pause_event.set()
        self._set_download_active(True)
        self._status_async(T('status_download_starting', n=total), True)

        # Determine destination folder and base opts once
        base_opts, dest = self._build_opts_for_mode(mode, bitrate)
        self._ensure_dir(dest)
        known_names = _scan_existing_stems(dest)

        for i, url in enumerate(urls):
            if self._check_pause_cancel():
                break

            item_opts = dict(base_opts)
            if 'watch?v=' in url or 'youtu.be/' in url:
                item_opts['noplaylist'] = True

            # Determine unique destination path BEFORE the download
            item_opts = _resolve_outtmpl_unique(url, item_opts, known_names)
            item_opts, final_path_ref = _collect_final_path(item_opts)
            item_opts['progress_hooks'] = list(item_opts.get('progress_hooks') or []) + [
                self._make_hook(
                    f'{prefix} ({i+1}/{total})' if total > 1 else prefix,
                    idx=i, total=total)]

            self.root.after(0, lambda i=i, t=total: self.status_var.set(
                T('status_download_n_of_t', i=i+1, t=t) if t > 1
                else T('status_download_running')))

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
                        T('status_skipped', u=u[:60])))
                    continue
                keep_going = [True]
                ev = threading.Event()
                def _ask(err=str(e), u=url):
                    keep_going[0] = messagebox.askyesno(
                        T('title_error'),
                        T('msg_error_at_url', u=u, err=err))
                    ev.set()
                self.root.after(0, _ask)
                ev.wait(30)
                if not keep_going[0]:
                    break

        self._set_download_active(False)

        if done:
            n   = len(done)
            cancelled_hint = T('msg_download_cancelled_hint') if self._cancel_flag else ''
            msg = T('msg_download_success', n=n, extra=cancelled_hint)
            if skipped:
                msg += T('msg_download_skipped_hint', n=len(skipped))
            if n == 1:
                msg += T('msg_download_success_single', title=done[0])
            self.root.after(0, lambda: (
                self.set_status(T('status_download_done') if not self._cancel_flag
                                else T('status_download_cancelled')),
                self._reset_progress(),
                messagebox.showinfo(T('title_success'), msg),
                self._open_folder_if_wanted(dest)))
        else:
            self.root.after(0, lambda: (
                self.set_status(T('status_download_none')),
                self._reset_progress()))

    def _resolve_and_run(self, urls: list, mode: str, bitrate: str, prefix: str):
        """
        Called from the quick-download methods.
        Resolves URLs (showing the playlist dialog if needed) and starts _run_urls.
        """
        self._status_async(T('status_urls_checking'), True)
        resolved = []

        if len(urls) > 1:
            result = self._request_multiurl_popup(urls, mode, bitrate)
            if result is None:
                self._status_async(T('status_cancelled'))
                self._reset_progress()
                return
            urls    = result['urls']
            mode    = result['mode']
            bitrate = result['bitrate']
            prefix  = _modes_dict().get(mode, prefix)

        # Use an already-loaded playlist directly – but ONLY if the URL
        # actually belongs to the stored playlist (list_id must match)
        # or is a plain playlist URL without a video ID.
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
                    # Specific index → only this one video
                    single_url = _resolve_entry_from_playlist(entries, p) or urls[0]
                    self._status_async(T('status_video_from_playlist', idx=p['index']), True)
                    self._run_urls([single_url], mode, bitrate, prefix, silent_errors=True)
                else:
                    # Playlist without index → all downloadable entries
                    downloadable = [e for e in entries if not _is_unavailable_entry(e)]
                    if downloadable:
                        resolved = [_entry_url(e) for e in downloadable]
                        n_total  = len(entries)
                        n_dl     = len(downloadable)
                        self._status_async(
                            T('status_playlist_loading_n', t=pl_title, n=n_dl, tot=n_total), True)
                        self._run_urls(resolved, mode, bitrate, prefix, silent_errors=True)
                    else:
                        self._status_async(T('status_playlist_none_downloadable'))
                return
            # URL doesn't belong to the stored playlist → process normally

        for url in urls:
            p_url = _parse_yt_url(url)

            if p_url['is_video_in_playlist']:
                pl_entries, pl_title = self._fetch_playlist_flat(p_url['list_id'])
                if pl_entries and not self._pending_playlist:
                    self._pending_playlist = {
                        'entries': pl_entries,
                        'title':   pl_title,
                        'list_id': p_url['list_id'],
                    }

                resolved.append(_resolve_entry_from_playlist(pl_entries, p_url) or url)
                continue

            # ── Channel-URL (/@handle, /channel/, /c/, /user/) ────────────────
            # yt-dlp returns a nested playlist structure here
            # (Channel → tabs → sub-playlists → videos).  If we passed the URL
            # directly to yt-dlp, it would load all videos in a single
            # ydl.extract_info() call – and our hooks for
            # thumbnail embedding would then NOT fire.
            # Solution: flatten the entries beforehand, send each video URL
            # through _run_urls individually (where hooks fire reliably).
            # A subfolder <channel name> is also created.
            if _is_channel_url(url):
                ch_name = _channel_name_from_url(url)
                self._status_async(T('status_channel_analyzing', n=ch_name), True)
                try:
                    opts_ch = self._base_opts()
                    opts_ch['extract_flat'] = True
                    opts_ch['noplaylist']   = False
                    with yt_dlp.YoutubeDL(opts_ch) as ydl:
                        ch_info = ydl.extract_info(url, download=False)
                except Exception as e:
                    self._show_error_blocking('msg_channel_unavailable', u=url, e=e)
                    return

                flat = _deduplicate_entries(_flatten_channel_entries(ch_info))
                downloadable = [e for e in flat if not _is_unavailable_entry(e)]
                if not downloadable:
                    self._status_async(T('status_channel_none', n=ch_name))
                    continue

                ch_urls = [_entry_url(e) for e in downloadable]
                n_dl = len(ch_urls)
                self._status_async(T('status_channel_loading', nm=ch_name, n=n_dl), True)

                # Unterordner anlegen: <Basispfad>/<Kanalname>
                base_opts_ch, base_dest = self._build_opts_for_mode(mode, bitrate)
                ch_dest = os.path.join(base_dest, ch_name)
                self._ensure_dir(ch_dest)

                # Redirect outtmpl to the subfolder
                old_outtmpl = base_opts_ch.get('outtmpl', '')
                if old_outtmpl:
                    base_opts_ch['outtmpl'] = os.path.join(
                        ch_dest, os.path.basename(old_outtmpl))
                else:
                    base_opts_ch['outtmpl'] = os.path.join(ch_dest, '%(title)s.%(ext)s')

                # Download directly (not via _run_urls with mode detection again,
                # but using the already-adjusted opts block)
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
                        self._make_hook(f'{prefix} ({i+1}/{total_ch})', idx=i, total=total_ch)]
                    self.root.after(0, lambda i=i, t=total_ch: self.status_var.set(
                        T('status_download_progress', i=i+1, t=t)))
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
                            T('status_skipped', u=u[:50])))
                        continue
                self._set_download_active(False)
                n = len(done_ch)
                if n:
                    msg = T('msg_download_success', n=n, extra='') + T('msg_download_success_folder', folder=ch_dest)
                    self.root.after(0, lambda: (
                        self.set_status(T('status_download_done')),
                        self._reset_progress(),
                        messagebox.showinfo(T('title_success'), msg),
                        self._open_folder_if_wanted(ch_dest)))
                else:
                    self.root.after(0, lambda: (
                        self.set_status(T('status_download_none')),
                        self._reset_progress()))
                return

            opts = self._base_opts()
            opts['extract_flat'] = True
            opts['noplaylist'] = 'watch?v=' in url or 'youtu.be/' in url
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as e:
                self._show_error_blocking('msg_url_unavailable', u=url, e=e)
                return

            if info.get('_type') == 'playlist':
                entries  = _deduplicate_entries(list(info.get('entries', [])))
                pl_title = info.get('title', url)
                if not entries:
                    continue
                # Quick download: all downloadable entries directly, no dialog
                downloadable = [e for e in entries if not _is_unavailable_entry(e)]
                self._status_async(
                    T('status_playlist_loading_dl', t=pl_title, n=len(downloadable)), True)
                for e in downloadable:
                    resolved.append(_entry_url(e))
            else:
                resolved.append(url)

        if not resolved:
            self._status_async(T('msg_no_urls_to_download'))
            return

        self._run_urls(resolved, mode, bitrate, prefix, silent_errors=True)

    def _quick_download(self, mode: str, bitrate: str, label: str):
        """Shared thread starter for all quick-download buttons."""
        def t():
            urls = self._get_urls()
            if not urls:
                messagebox.showwarning(T('title_error'), T('msg_no_url_entered'))
                return
            self._resolve_and_run(urls, mode, bitrate, label)
        Thread(target=t, daemon=True).start()

    def quick_audio_mp3(self):       self._quick_download('audio_mp3',    '0', T('qd_loading_audio_mp3'))

    def quick_audio_opus(self):      self._quick_download('audio_opus',   '0', T('qd_loading_audio_opus'))

    def quick_video_mp4_m4a(self):   self._quick_download('video_mp4_m4a','0', T('qd_loading_video_mp4_m4a'))

    def quick_video_mp4(self):       self._quick_download('video_mp4',    '0', T('qd_loading_video_mp4'))

    def quick_video_best(self):      self._quick_download('video_best',   '0', T('qd_loading_video_best'))

    def download_custom(self):
        def t():
            urls  = self._get_urls()
            v_lbl = self.clicked_stream_video.get()
            a_lbl = self.clicked_stream_audio.get()

            if not urls:
                messagebox.showwarning(T('title_error'), T('msg_no_url_entered'))
                return

            skip_labels = _skip_labels()
            no_v = v_lbl in skip_labels or self.ignore_video_var.get()
            no_a = a_lbl in skip_labels or self.ignore_audio_var.get()

            if no_v and no_a:
                messagebox.showwarning(T('title_error'), T('msg_need_single_url_stream'))
                return

            vfmt = afmt = None
            if not no_v:
                for f in self._video_formats:
                    if f['label'] == v_lbl:
                        vfmt = f['format_id']; break
            if not no_a:
                for f in self._audio_formats:
                    if f['label'] == a_lbl:
                        afmt = f['format_id']; break

            fmt_str = (f'{vfmt}+{afmt}' if vfmt and afmt
                       else vfmt if vfmt else afmt)
            dest = (self.video_path_var.get() if vfmt
                    else self.audio_path_var.get())
            self._ensure_dir(dest)

            # Determine mode for _download_opts (video or audio)
            _custom_mode = 'video_mp4' if vfmt else 'audio_mp3'
            opts = self._download_opts(_custom_mode)
            opts.update({
                'format': fmt_str,
                'outtmpl': path.join(dest, '%(title)s.%(ext)s'),
            })
            if vfmt:
                # Video format selection: Original | MP4 | MKV
                vid_fmt_sel = self.video_format_var.get()
                if vid_fmt_sel == 'mkv':
                    opts['merge_output_format'] = 'mkv'
                elif vid_fmt_sel == 'mp4':
                    opts['merge_output_format'] = 'mp4'
                # 'original' → don't set merge_output_format
            if not vfmt:
                audio_fmt = self.audio_format_var.get()
                bitrate   = self.mp3_bitrate_var.get()
                if audio_fmt == 'mp3':
                    self._apply_audio_extract(opts, 'mp3', bitrate)
                elif audio_fmt == 'opus':
                    self._apply_audio_extract(opts, 'opus', '0')
                else:
                    # 'original' → raw original file, no conversion postprocessor.
                    # Remove EmbedThumbnail (unknown format – just to be safe).
                    pps = opts.get('postprocessors', [])
                    opts['postprocessors'] = [
                        p for p in pps
                        if p.get('key') not in ('FFmpegExtractAudio', 'EmbedThumbnail')
                    ]
                    opts.pop('writethumbnail', None)
                    opts.pop('_mp3_embed_ffmpeg', None)
                    opts.pop('_opus_embed_ffmpeg', None)

            self._status_async(T('status_download_running'), True)

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

                # Resolve playlist index if needed
                p_url = _parse_yt_url(url)
                if p_url['is_video_in_playlist']:
                    pl_entries = []
                    pending = self._pending_playlist
                    if pending and pending.get('list_id') == p_url['list_id']:
                        pl_entries = pending.get('entries', [])
                    if not pl_entries:
                        pl_entries, _ = self._fetch_playlist_flat(p_url['list_id'])
                    url = _resolve_entry_from_playlist(pl_entries, p_url) or url

                if 'watch?v=' in url or 'youtu.be/' in url:
                    item_opts['noplaylist'] = True

                item_opts = _resolve_outtmpl_unique(url, item_opts, known_names_custom)
                item_opts, final_path_ref = _collect_final_path(item_opts)
                item_opts['progress_hooks'] = list(item_opts.get('progress_hooks') or []) + [
                    self._make_hook(T('hook_loading_generic'), i, total)]
                self.root.after(0, lambda i=i, t=total: self.status_var.set(
                    T('status_download_progress', i=i+1, t=t) if t > 1
                    else T('status_download_running')))
                try:
                    with yt_dlp.YoutubeDL(item_opts) as ydl:
                        info = ydl.extract_info(url)
                        done.append(info.get('title', url))
                    _rename_after_download(final_path_ref, known_names_custom)
                    self._maybe_embed_thumbnail(item_opts, final_path_ref[0])
                except Exception as e:
                    if self._cancel_flag:
                        break
                    messagebox.showerror(T('title_error'), T('msg_error_generic', e=e))
            self._set_download_active(False)

            if done:
                n   = len(done)
                extra = T('msg_download_success_single', title=done[0]) if n == 1 else ''
                msg = T('msg_download_success', n=n, extra=extra)
                self.root.after(0, lambda: (
                    self.set_status(T('status_download_done')),
                    self._reset_progress(),
                    messagebox.showinfo(T('title_success'), msg),
                    self._open_folder_if_wanted(dest)))

        Thread(target=t, daemon=True).start()

    def set_status(self, msg, show_progress=False):
        if msg != self._last_status_msg:
            self.status_var.set(msg)
            self._last_status_msg = msg
        if show_progress:
            self._last_progress_update = 0.0
            self._indeterminate_progress_value = 0.0
            self._progress_pct.set(0.0)
            self._pct_label.config(text='')

    def _status_async(self, msg, show_progress=False):
        """Schedules set_status() onto the GUI thread. Use this from worker
        threads instead of self.root.after(0, lambda: self.set_status(...))
        directly – same effect, less boilerplate at the call site."""
        self.root.after(0, lambda: self.set_status(msg, show_progress))

    def _reset_progress(self):
        self.root.after(0, lambda: (
            self._progress_pct.set(0.0),
            self._pct_label.config(text='')))

    def _queue_progress_update(self, progress=None, pct_label=None,
                               status_msg=None, force=False):
        now = time.monotonic()
        if not force and now - self._last_progress_update < self._progress_update_interval:
            return
        self._last_progress_update = now

        def _apply():
            if progress is not None:
                self._progress_pct.set(progress)
            if pct_label is not None:
                self._pct_label.config(text=pct_label)
            if status_msg and status_msg != self._last_status_msg:
                self.status_var.set(status_msg)
                self._last_status_msg = status_msg

        self.root.after(0, _apply)

    def _set_download_active(self, active: bool):
        state = 'normal' if active else 'disabled'
        self._download_active = active
        self.root.after(0, lambda: (
            self._pause_btn.config(state=state, text=T('pause_btn')),
            self._cancel_btn.config(state=state)))
        if not active:
            self._pause_event.set()
            self._cancel_flag = False

    def _toggle_pause(self):
        if not self._download_active:
            return
        if self._pause_event.is_set():
            self._pause_event.clear()
            self._pause_btn.config(text=T('resume_btn'))
            self.status_var.set(T('status_paused'))
        else:
            self._pause_event.set()
            self._pause_btn.config(text=T('pause_btn'))
            self.status_var.set(T('status_resuming'))

    def _request_cancel(self):
        if not self._download_active:
            return
        self._cancel_flag = True
        self._pause_event.set()
        self._cancel_btn.config(state='disabled')
        self.status_var.set(T('status_cancelling'))

    def _check_pause_cancel(self) -> bool:
        self._pause_event.wait()
        return self._cancel_flag


class YouTubeDownloaderApp(
    UIBuildMixin, I18nMixin, ConfigMixin,
    AnalysisMixin, PlaylistMixin, DownloadMixin,
):
    """
    Main application class, assembled from the mixins above by
    responsibility area:
        UIBuildMixin  – widget construction & generic widget interaction
        I18nMixin     – live language switching
        ConfigMixin   – config persistence & filesystem paths
        AnalysisMixin – URL/playlist analysis (no downloading)
        PlaylistMixin – playlist loading & selection dialogs
        DownloadMixin – actual downloads, progress, pause/cancel

    __init__ remains here because it is what wires all the mixins'
    attribute contracts together in the first place.
    """

    def __init__(self, root):
        self.root = root
        self.i18n = I18nRegistry()   # live text refresh for static widgets
        self.ui_WEITE = 750
        self.root.geometry(f'{self.ui_WEITE}x600')
        self.root.minsize(self.ui_WEITE, 600)

        try:
            self.root.iconbitmap('yt_symbol_small.ico')
        except Exception:
            pass

        # Variables
        self.language_var      = StringVar(value=LANG['code'])
        self.audio_path_var    = StringVar()
        self.video_path_var    = StringVar()
        self.audio_to_mp3_var  = BooleanVar(value=True)
        self.audio_format_var  = StringVar(value='original')   # 'original' | 'opus' | 'mp3'
        self.video_to_mp4_var  = BooleanVar(value=True)
        self.video_format_var  = StringVar(value='original')   # 'original' | 'mp4' | 'mkv'
        self.mp3_bitrate_var   = StringVar(value='320')
        self.quick_bitrate_var = StringVar(value='320')
        self.open_folder_var      = BooleanVar(value=False)
        self.write_tags_var       = BooleanVar(value=True)
        self.write_thumbnail_var  = BooleanVar(value=True)
        self.cookies_browser_var  = StringVar(value='')   # empty = no cookies

        self.clicked_stream_video = StringVar()
        self.clicked_stream_audio = StringVar()
        self.ignore_video_var = BooleanVar(value=False)
        self.ignore_audio_var = BooleanVar(value=False)

        self._video_formats: list = []
        self._audio_formats: list = []
        self._progress_pct = DoubleVar(value=0.0)
        self._last_status_msg: str | None = None
        self._progress_update_interval = 0.2
        self._last_progress_update = 0.0
        self._indeterminate_progress_value = 0.0

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
        self.audio_path_var.set(path.join(parent_dir, 'Downloads', 'audio'))
        self.video_path_var.set(path.join(parent_dir, 'Downloads', 'video'))

        # ── Load configuration ──────────────────────────────────────────────
        self._cfg = _config_load()
        LANG['code'] = self._cfg.get('language') or 'en'
        self.language_var.set(LANG['code'])
        self._apply_config(self._cfg)

        self._update_window_title()
        self.setup_styles()
        self._build_scrollable_shell()
        self.create_widgets()

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    root = Tk()
    app = YouTubeDownloaderApp(root)
    root.mainloop()
