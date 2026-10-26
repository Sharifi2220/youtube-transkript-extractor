"""Offline subtitle parsing and conservative yt-dlp subtitle-only adapter.

Only an explicit user click may trigger network access. Never downloads audio/video.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape, escape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
TIME = r"(?:\d{1,}:)?\d{2}:\d{2}[.,]\d{3}"
CUE_TIME = re.compile(rf"^\s*({TIME})\s+-->\s+({TIME})(?:\s+.*)?$")
INLINE_TIME = re.compile(r"<(?:\d{1,}:)?\d{2}:\d{2}\.\d{3}>")
# Strip VTT/SRT formatting tags, but do not destroy literal terms like <C>.
CAPTION_TAG = re.compile(r"</?(?:c(?:\.[^>]*)?|v(?:\s[^>]*)?|lang(?:\s[^>]*)?|ruby|rt|b|i|u|font(?:\s[^>]*)?)>")
SPACE = re.compile(r"\s+")


class TranscriptError(Exception):
    """An actionable error presented to the user."""


@dataclass(frozen=True)
class CaptionOption:
    language: str
    kind: str  # 'manual' or 'auto'
    translated: bool = False

    @property
    def label(self) -> str:
        base = f"{self.language} – {'Manuell' if self.kind == 'manual' else 'Automatisch'}"
        if self.translated:
            return base + " (maschinell übersetzt)"
        if self.language.lower().endswith("-orig"):
            return base + " (Original)"
        return base


@dataclass(frozen=True)
class VideoInfo:
    video_id: str
    title: str
    captions: tuple[CaptionOption, ...]
    warning: str = ""


@dataclass(frozen=True)
class Cue:
    start_ms: int
    end_ms: int
    text: str


def normalize_youtube_url(source: str) -> str:
    raw = source.strip()
    if not raw or len(raw) > 2048 or any(c in raw for c in "\r\n\t\\"):
        raise TranscriptError("Bitte einen gültigen YouTube-Videolink einfügen.")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    try:
        parsed = urlsplit(raw)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
            raise ValueError()
    except (ValueError, TypeError):
        raise TranscriptError("Ungültiger YouTube-Link.") from None
    if hostname not in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com"}:
        raise TranscriptError("Nur direkte YouTube-Videolinks sind erlaubt.")
    path = parsed.path.rstrip("/")
    if hostname in {"youtu.be", "www.youtu.be"}:
        parts = path.split("/")
        vid = parts[1] if len(parts) == 2 and parts[0] == "" else ""
    elif path == "/watch":
        vids = parse_qs(parsed.query).get("v", [])
        vid = vids[0] if len(vids) == 1 else ""
    else:
        parts = path.split("/")
        vid = parts[2] if len(parts) == 3 and parts[1] in {"shorts", "live", "embed"} else ""
    if not VIDEO_ID.fullmatch(vid):
        raise TranscriptError("Der Link muss ein einzelnes YouTube-Video enthalten.")
    return f"https://www.youtube.com/watch?v={vid}"


def _supported(formats: list) -> bool:
    return any(isinstance(f, dict) and f.get("ext") in {"vtt", "srt"} for f in formats)


def _is_translation(language: str, formats: list, kind: str) -> bool:
    if kind != "auto" or language.lower().endswith("-orig"):
        return False
    # yt-dlp advertises translated YouTube auto captions with tlang= in their URL.
    return any(isinstance(f, dict) and "tlang=" in str(f.get("url", "")).lower() for f in formats)


def list_caption_options(metadata: dict) -> tuple[CaptionOption, ...]:
    found: list[CaptionOption] = []
    for key, kind in (("subtitles", "manual"), ("automatic_captions", "auto")):
        for language, formats in (metadata.get(key) or {}).items():
            if not isinstance(language, str) or not language or "live_chat" in language or not isinstance(formats, list):
                continue
            if _supported(formats):
                found.append(CaptionOption(language, kind, _is_translation(language, formats, kind)))

    def priority(c: CaptionOption):
        language = c.language.lower()
        original = language.endswith("-orig")
        # Original is preferred, before human/manual native tracks and unverified auto.
        group = 0 if original else (2 if c.translated else 1)
        preference = 0 if language in ("de", "de-orig") else (1 if language.startswith("de-") else (2 if language in ("en", "en-orig") else (3 if language.startswith("en-") else 4)))
        return group, preference, 0 if c.kind == "manual" else 1, language
    return tuple(sorted(found, key=priority))


def _ydl_params() -> dict:
    params = {"skip_download": True, "noplaylist": True, "quiet": True, "no_warnings": True,
              "cachedir": False, "ignoreerrors": False, "ignore_no_formats_error": True,
              "remote_components": []}
    # Keep a portable Deno binary next to app.py without changing system PATH.
    deno = Path(__file__).resolve().parent / ("deno.exe" if __import__("os").name == "nt" else "deno")
    if deno.is_file():
        params["js_runtimes"] = {"deno": {"path": str(deno)}}
    return params


class _Warnings:
    def __init__(self): self.values: list[str] = []
    def debug(self, msg): pass
    def warning(self, msg): self.values.append(str(msg))
    def error(self, msg): self.values.append(str(msg))


def get_video_info(url: str) -> VideoInfo:
    normalized = normalize_youtube_url(url)
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise TranscriptError('yt-dlp fehlt. Bitte "INSTALL_WINDOWS.bat" ausführen.') from exc
    logger = _Warnings()
    try:
        with YoutubeDL({**_ydl_params(), "logger": logger}) as ydl:
            info = ydl.extract_info(normalized, download=False)
    except Exception as exc:
        raise TranscriptError(f"YouTube-Metadaten konnten nicht abgerufen werden: {str(exc)[:220]}") from exc
    if not isinstance(info, dict) or not VIDEO_ID.fullmatch(str(info.get("id", ""))):
        raise TranscriptError("Keine gültigen Video-Metadaten erhalten.")
    if str(info["id"]) != parse_qs(urlsplit(normalized).query)["v"][0]:
        raise TranscriptError("YouTube leitete auf ein anderes Video um; Abruf abgebrochen.")
    warning = "Deno/JavaScript-Laufzeit prüfen." if any("javascript" in s.lower() or "runtime" in s.lower() for s in logger.values) else ""
    return VideoInfo(str(info["id"]), str(info.get("title") or "Unbenanntes Video"), list_caption_options(info), warning)


def _milliseconds(value: str) -> int:
    parts = value.replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
        elif len(parts) == 2:
            hours, minutes, seconds = "0", *parts
        else:
            raise ValueError()
        sec, milli = seconds.split(".")
        if int(minutes) > 59 or int(sec) > 59:
            raise ValueError()
        return (int(hours) * 3600 + int(minutes) * 60 + int(sec)) * 1000 + int(milli)
    except ValueError:
        raise TranscriptError("Ungültiger Zeitstempel in den Untertiteln.") from None


def parse_subtitles(raw: str) -> list[Cue]:
    lines = raw.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[Cue] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() in {"STYLE", "REGION"} or re.match(r"^NOTE(?:\s|$)", lines[i].strip()):
            i += 1
            while i < len(lines) and lines[i].strip(): i += 1
            continue
        matched = CUE_TIME.match(lines[i])
        if not matched:
            i += 1
            continue
        start, end = _milliseconds(matched.group(1)), _milliseconds(matched.group(2))
        i += 1
        content: list[str] = []
        while i < len(lines) and not CUE_TIME.match(lines[i]):
            # Some YouTube auto-VTT cues include an empty first payload line.
            if not lines[i].strip():
                if not content and i + 1 < len(lines) and lines[i + 1].strip() and not CUE_TIME.match(lines[i + 1]):
                    i += 1
                    continue
                break
            # SRT permits missing blank separators. Do not append the next cue index.
            if lines[i].strip().isdigit() and i + 1 < len(lines) and CUE_TIME.match(lines[i + 1]):
                break
            line = INLINE_TIME.sub("", lines[i])
            line = CAPTION_TAG.sub("", line)
            line = SPACE.sub(" ", unescape(line)).strip()
            if line: content.append(line)
            i += 1
        text = "\n".join(content).strip()
        if text:
            if end < start:
                raise TranscriptError("Untertiteldatei enthält einen rückwärts laufenden Zeitcode.")
            # A zero-duration cue contains words. Retain it with a minimal 1 ms range.
            cues.append(Cue(start, max(start + 1, end), text))
    if not cues:
        raise TranscriptError("Keine auswertbaren Zeitstempel in der Untertiteldatei gefunden (VTT/SRT benötigt).")
    return cues


def _spoken_pieces(cues: list[Cue]) -> list[tuple[int, str]]:
    """Return segments after only strong evidence of rolling auto-caption overlap."""
    segments: list[tuple[int, str]] = []
    emitted: list[str] = []
    previous: Cue | None = None
    for cue in cues:
        words = cue.text.split()
        if not words: continue
        if previous is not None:
            gap = cue.start_ms - previous.end_ms
            if -1500 <= gap <= 250:
                maximum = min(len(emitted), len(words), 100)
                overlap = 0
                for n in range(maximum, 1, -1):
                    if emitted[-n:] == words[:n]:
                        overlap = n
                        break
                if overlap and overlap < len(words):
                    words = words[overlap:]
                elif overlap == len(words) and (gap < 0 or cue.end_ms - cue.start_ms <= 150):
                    words = []
        if words:
            segments.append((cue.start_ms, " ".join(words)))
            emitted.extend(words)
        previous = cue
    return segments


def plain_text(cues: list[Cue]) -> str:
    return " ".join(t for _, t in _spoken_pieces(cues)) + "\n" if cues else ""


def _read_subtitle(path: Path) -> tuple[str, str]:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise TranscriptError("Untertiteldatei zu groß (maximal 8 MB).")
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try: return data.decode("utf-16"), "UTF-16"
        except UnicodeError as exc: raise TranscriptError("Ungültige UTF-16-Untertiteldatei.") from exc
    try: return data.decode("utf-8-sig"), "UTF-8"
    except UnicodeError:
        # Only for explicit user-selected local files; never silently reinterpret online bytes.
        return data.decode("cp1252"), "Windows-1252 (Fallback; bitte prüfen)"


def load_subtitle_file_with_encoding(path: str | Path) -> tuple[list[Cue], str]:
    target = Path(path)
    if target.suffix.lower() not in {".srt", ".vtt"}:
        raise TranscriptError("Bitte eine SRT- oder VTT-Datei wählen.")
    try:
        raw, encoding = _read_subtitle(target)
    except OSError as exc:
        raise TranscriptError(f"Datei kann nicht gelesen werden: {exc}") from exc
    return parse_subtitles(raw), encoding


def load_subtitle_file(path: str | Path) -> list[Cue]:
    return load_subtitle_file_with_encoding(path)[0]


def _time(ms: int, comma: bool = False) -> str:
    hh, rem = divmod(ms, 3600000)
    mm, rem = divmod(rem, 60000)
    ss, msec = divmod(rem, 1000)
    return f"{hh:02}:{mm:02}:{ss:02}{',' if comma else '.'}{msec:03}"


def make_srt(cues: list[Cue]) -> str:
    return "\n".join(f"{i}\n{_time(c.start_ms, True)} --> {_time(c.end_ms, True)}\n{escape(c.text, quote=False)}\n"
                     for i, c in enumerate(cues, 1))


def make_vtt(cues: list[Cue]) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{_time(c.start_ms)} --> {_time(c.end_ms)}\n{escape(c.text, quote=False)}\n" for c in cues)


def render_ai_txt(cues: list[Cue], info: VideoInfo | None = None,
                  option: CaptionOption | None = None, local_name: str = "") -> str:
    """Readable transcript with provenance and minute anchors, not a verbatim speech guarantee."""
    header = ["TRANSKRIPT"]
    if info:
        header += ["Titel: " + SPACE.sub(" ", info.title),
                   "Quelle: https://www.youtube.com/watch?v=" + info.video_id]
    elif local_name:
        header += ["Lokale Untertiteldatei: " + local_name]
    if option:
        header += ["Sprache: " + option.language,
                   "Spurtyp: " + ("automatische Untertitel" if option.kind == "auto" else "manuelle Untertitel") +
                   ("; maschinelle Übersetzung" if option.translated else "")]
    header += ["Hinweis: Untertitel können unvollständig oder fehlerhaft sein; Zeitmarken sind ungefähre Cue-Anfänge."]
    pieces = _spoken_pieces(cues)
    blocks: list[str] = []
    current: list[str] = []
    last_bucket: int | None = None
    length = 0
    for start, fragment in pieces:
        bucket = start // 60000
        if bucket != last_bucket:
            if current:
                blocks.append(" ".join(current)); current = []; length = 0
            hh, mm, ss = int(start // 3600000), int((start % 3600000) // 60000), 0
            blocks.append(f"[{hh:02}:{mm:02}:{ss:02}]")
            last_bucket = bucket
        if length + len(fragment) > 700 and current:
            blocks.append(" ".join(current)); current = []; length = 0
        current.append(fragment)
        length += len(fragment) + 1
    if current: blocks.append(" ".join(current))
    return "\n".join(header) + "\n\n" + "\n\n".join(blocks) + "\n"


def fetch_subtitles(video: VideoInfo, option: CaptionOption) -> list[Cue]:
    if option not in video.captions:
        raise TranscriptError("Untertitelspur ist nicht in der geprüften Videoauswahl.")
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise TranscriptError('yt-dlp fehlt. Bitte "INSTALL_WINDOWS.bat" ausführen.') from exc
    with TemporaryDirectory(prefix="transkript_yt_") as directory:
        output = Path(directory)
        params = {**_ydl_params(), "overwrites": True,
                  "writesubtitles": option.kind == "manual", "writeautomaticsub": option.kind == "auto",
                  "subtitleslangs": [option.language], "subtitlesformat": "vtt/srt",
                  "outtmpl": str(output / "untertitel.%(ext)s")}
        try:
            with YoutubeDL(params) as ydl:
                rc = ydl.download([f"https://www.youtube.com/watch?v={video.video_id}"])
            if rc not in (None, 0):
                raise TranscriptError("Der Untertitelabruf wurde von YouTube abgewiesen.")
        except TranscriptError:
            raise
        except Exception as exc:
            raise TranscriptError(f"Untertitel konnten nicht geladen werden: {str(exc)[:220]}") from exc
        matches = sorted(p for p in output.iterdir() if p.is_file() and p.suffix.lower() in {".srt", ".vtt"})
        if not matches:
            raise TranscriptError("Keine Untertiteldatei erhalten. Sprache möglicherweise nicht verfügbar oder Zugriff blockiert.")
        selected = next((p for p in matches if f".{option.language}." in p.name), None)
        if selected is None:
            raise TranscriptError("Die gewählte Untertitelsprache wurde nicht als SRT/VTT gespeichert.")
        if selected.stat().st_size > 8 * 1024 * 1024:
            raise TranscriptError("Die Untertiteldatei ist zu groß (maximal 8 MB).")
        try:
            raw = selected.read_text(encoding="utf-8-sig")
        except UnicodeError as exc:
            raise TranscriptError("Ungültige UTF-8-Zeichen in der Online-Untertiteldatei.") from exc
        return parse_subtitles(raw)


def retrieve_best(url: str) -> tuple[VideoInfo, CaptionOption, list[Cue]]:
    info = get_video_info(url)
    if not info.captions:
        raise TranscriptError("Keine zugänglichen SRT/VTT-Untertitel für dieses Video gefunden.")
    # No silent switching to other languages on failed download.
    choice = info.captions[0]
    return info, choice, fetch_subtitles(info, choice)
