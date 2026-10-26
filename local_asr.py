"""Standalone, opt-in local Whisper ASR for the YouTube-Transkript-Extractor.

Standalone local Whisper adapter with no external project integrations,
background tasks, database, media discovery or system changes.
Never fetch media, models or network URLs. Expects an explicitly chosen local media file.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

from transcript_core import Cue, make_srt, make_vtt, render_ai_txt

ALLOWED_EXT = frozenset({".wav", ".mp3", ".m4a", ".mp4", ".webm", ".flac", ".ogg", ".opus", ".aac", ".wma", ".mkv", ".mov"})
ASR_MARKER = "YTX_ASR_RESULT_JSON="
MODEL = "base"  # Only an already cached model; never auto-download another model.
MAX_BYTES = 3 * 1024 * 1024 * 1024  # protect interactive UI from accidental gigantic files


class AsrError(Exception):
    """Actionable local ASR error."""


@dataclass(frozen=True)
class AsrTranscript:
    source_name: str
    sha256: str
    language: str
    model: str
    device: str
    seconds: float
    cues: tuple[Cue, ...]


def verify_source(source: str | Path) -> Path:
    path = Path(source).expanduser()
    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in ALLOWED_EXT:
        raise AsrError("Nur eine explizit ausgewählte lokale Audio-/Videodatei in unterstütztem Format ist erlaubt.")
    size = path.stat().st_size
    if size <= 0 or size > MAX_BYTES:
        raise AsrError("Datei ist leer oder größer als 3 GiB; bitte einzelne kleinere lokale Datei wählen.")
    return path.resolve(strict=True)


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _cues_from_segments(segments: Any) -> tuple[Cue, ...]:
    if not isinstance(segments, (list, tuple)):
        raise AsrError("Whisper lieferte keine lesbare Segmentliste.")
    cues = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise AsrError("Ungültiges Whisper-Segment.")
        piece = " ".join(str(segment.get("text") or "").split())
        if not piece:
            continue
        try:
            begin, end = float(segment["start"]), float(segment["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AsrError("Fehlende Zeitmarken im Whisper-Ergebnis.") from exc
        if not (math.isfinite(begin) and math.isfinite(end) and 0 <= begin <= end <= 86400 * 7):
            raise AsrError("Ungültige oder rückwärts laufende Whisper-Zeitmarke.")
        start_ms, end_ms = round(begin * 1000), round(end * 1000)
        cues.append(Cue(start_ms, max(start_ms + 1, end_ms), piece))
    if not cues:
        raise AsrError("NO_SPEECH_DETECTED: keine erkennbaren Wörter mit Zeitmarken.")
    return tuple(cues)


def transcribe_one(source: str | Path, *, requested_device: str = "auto", model_loader=None) -> AsrTranscript:
    path = verify_source(source)
    if requested_device not in {"auto", "cuda", "cpu"}:
        raise AsrError("Gerät muss auto, cuda oder cpu sein.")
    cache = Path.home() / ".cache" / "whisper" / f"{MODEL}.pt"
    if model_loader is None:
        if not cache.is_file():
            raise AsrError(f"Whisper-Modell nicht lokal vorhanden: {cache}. Kein automatischer Modelldownload.")
        try:
            torch = importlib.import_module("torch")
            whisper = importlib.import_module("whisper")
        except ImportError as exc:
            raise AsrError("Whisper/PyTorch fehlen in der gewählten Python-Umgebung. Bestehenden GPU-Python-Interpreter auswählen.") from exc
        if requested_device == "cuda" and not torch.cuda.is_available():
            raise AsrError("CUDA ist in der ausgewählten Python-Umgebung nicht verfügbar.")
        device = "cuda" if (requested_device == "cuda" or requested_device == "auto" and torch.cuda.is_available()) else "cpu"
        # A checkpoint PATH (not model name) prevents Whisper from attempting a silent download
        # when the cached checksum is damaged; the official loader supports local .pt.
        model_loader = lambda: whisper.load_model(str(cache), device=device)
    else:
        # Explicit dependency injection for offline unit tests only; never used in production CLI.
        device = "cpu" if requested_device == "auto" else requested_device
    before = hash_file(path)
    started = time.perf_counter()
    try:
        model = model_loader()
        result = model.transcribe(str(path), language=None, fp16=(device == "cuda"), verbose=False)
    except Exception as exc:
        raise AsrError(f"Lokale Whisper-Verarbeitung fehlgeschlagen: {type(exc).__name__}: {str(exc)[:230]}") from exc
    if not isinstance(result, dict):
        raise AsrError("Whisper gab kein Ergebnisobjekt zurück.")
    cues = _cues_from_segments(result.get("segments"))
    after = hash_file(path)
    if before != after:
        raise AsrError("INPUT_CHANGED_DURING_TRANSCRIPTION: Quelle hat sich verändert; Ergebnis wird verworfen.")
    return AsrTranscript(path.name, before, str(result.get("language") or "unbestimmt"), MODEL, device,
                         round(time.perf_counter() - started, 3), cues)


def ai_text(result: AsrTranscript) -> str:
    # Reuse this project's existing minute anchors and paragraphs.
    body = render_ai_txt(list(result.cues)).split("\n\n", 1)[-1]
    return ("TRANSKRIPT – LOKALE WHISPER-SPRACHERKENNUNG\n"
            f"Lokale Mediendatei: {result.source_name}\n"
            f"Sprache (automatisch erkannt): {result.language}\n"
            f"ASR-Modell: Whisper {result.model}; Gerät: {result.device}\n"
            f"Quell-SHA256: {result.sha256}\n"
            "Hinweis: automatisch erkannter Text, nicht wortgetreu geprüft. Zeitmarken sind Näherungen.\n\n" + body)


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    if stem.endswith(".speech"):
        stem = stem[:-7]
    stem = re.sub(r'[^\w.\-]+', '_', stem, flags=re.UNICODE).strip("._")[:100]
    if not stem:
        raise AsrError("Ungültiger Quelldateiname.")
    return stem


def save_asr(result: AsrTranscript, directory: str | Path) -> dict[str, str]:
    root = Path(directory).expanduser()
    if root.is_symlink():
        raise AsrError("Symlink als Ausgabeordner nicht erlaubt.")
    root.mkdir(parents=True, exist_ok=True)
    suffix = _safe_stem(result.source_name) + ".asr"
    meta = {"source_file": result.source_name, "source_sha256": result.sha256,
            "method": "local-openai-whisper", "model": result.model,
            "device": result.device, "language": result.language,
            "cues": len(result.cues), "runtime_seconds": result.seconds,
            "source_type": "user-selected-local-file", "no_network_media_download": True}
    contents = {"txt": ai_text(result), "srt": make_srt(list(result.cues)),
                "vtt": make_vtt(list(result.cues)), "json": json.dumps(meta, indent=2, ensure_ascii=False) + "\n"}
    paths = {kind: root / f"{suffix}.{kind}" for kind in contents}
    if any(p.exists() or p.is_symlink() for p in paths.values()):
        raise AsrError("Mindestens eine ASR-Zieldatei existiert schon; nichts überschrieben. Bitte anderen Ausgabeordner wählen.")
    created: list[Path] = []
    try:
        for kind, p in paths.items():
            # Exclusive creation, unlike replace/rename; refuse all preexisting files.
            with p.open("x", encoding="utf-8-sig" if kind == "txt" else "utf-8", newline="\n") as stream:
                created.append(p)
                stream.write(contents[kind])
                stream.flush()
                os.fsync(stream.fileno())
    except OSError as exc:
        for p in created:
            p.unlink(missing_ok=True)
        raise AsrError(f"Ausgabe konnte nicht vollständig geschrieben werden: {exc}") from exc
    return {kind: str(p) for kind, p in paths.items()}


def result_payload(result: AsrTranscript, outputs: dict[str, str]) -> dict:
    return {"source_name": result.source_name, "sha256": result.sha256,
            "language": result.language, "model": result.model, "device": result.device,
            "seconds": result.seconds, "cues": [{"start_ms": x.start_ms, "end_ms": x.end_ms, "text": x.text} for x in result.cues],
            "outputs": outputs}


def output_folder(project_dir: Path | None = None) -> Path:
    """Keep ASR exports beside this standalone application."""
    root = (project_dir or Path(__file__).resolve().parent).resolve()
    return root / "TRANSKRIPTE_TESTAUSGABEN"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="YouTube-Transkript-Extractor: lokal gewählte Datei mit Whisper transkribieren")
    parser.add_argument("--input", required=True, help="Explizite lokale Mediendatei (keine YouTube-URL)")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    args = parser.parse_args(argv)
    try:
        result = transcribe_one(args.input, requested_device=args.device)
        outputs = save_asr(result, args.output_dir or output_folder())
    except (AsrError, OSError) as exc:
        print(f"YTX_ASR_ERROR: {exc}", file=sys.stderr)
        return 2
    print(ASR_MARKER + json.dumps(result_payload(result, outputs), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
