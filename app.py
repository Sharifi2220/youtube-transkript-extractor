"""Local Tk GUI: single-click YouTube transcript copy or offline SRT/VTT import."""
from __future__ import annotations

from pathlib import Path
from queue import Queue, Empty
import threading
import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from windows_context_menu import ContextMenu
from local_asr import ASR_MARKER, ai_text, AsrTranscript, output_folder, verify_source
from transcript_core import (CaptionOption, Cue, VideoInfo, TranscriptError,
    fetch_subtitles, get_video_info, load_subtitle_file_with_encoding,
    make_srt, make_vtt, normalize_youtube_url, render_ai_txt, retrieve_best)

class ExtractorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("YouTube-Transkript-Extractor v0.1.6-dev")
        root.geometry("900x680")
        root.minsize(710, 520)
        self.events: Queue = Queue()
        self.info: VideoInfo | None = None
        self.cues: list[Cue] = []
        self.option: CaptionOption | None = None
        self.text = ""
        self.local_name = ""
        self.current_url = ""
        self.asr_python = os.environ.get("YTX_ASR_PYTHON", sys.executable)
        self.url = tk.StringVar(value="")
        self.selection = tk.StringVar()
        self.status = tk.StringVar(value="Link einfügen und den großen Knopf anklicken. Oder SRT/VTT lokal öffnen.")
        self._busy = False
        self._construct()
        self.root.after(100, self._poll)

    def _construct(self):
        pane = ttk.Frame(self.root, padding=15); pane.pack(fill="both", expand=True)
        ttk.Label(pane, text="YouTube-Transkript-Extractor", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(pane, text="Untertitel zuerst · optional lokale Whisper-Audiotranskription · kein YouTube-Audiodownload").pack(anchor="w")
        top = ttk.Frame(pane); top.pack(fill="x", pady=(14, 8))
        ttk.Label(top, text="Video:").pack(side="left")
        self.url_entry = ttk.Entry(top, textvariable=self.url)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=8)
        self.url_entry.configure(exportselection=False)
        self.url_context = ContextMenu(self.url_entry)
        one = ttk.Frame(pane); one.pack(fill="x", pady=(0, 9))
        self.quick_button = ttk.Button(one, text="Link → Transkript kopieren", command=self.quick)
        self.quick_button.pack(side="left")
        self.open_button = ttk.Button(one, text="Lokale SRT/VTT öffnen", command=self.open_local)
        self.open_button.pack(side="left", padx=(10, 0))
        audio = ttk.Frame(pane); audio.pack(fill="x", pady=(0, 9))
        self.audio_button = ttk.Button(audio, text="Lokale Audiodatei → Whisper-Transkript", command=self.open_audio)
        self.audio_button.pack(side="left")
        self.python_button = ttk.Button(audio, text="Whisper-Python wählen …", command=self.choose_asr_python)
        self.python_button.pack(side="left", padx=(10, 0))
        second = ttk.LabelFrame(pane, text="Optional: Untertitelspur gezielt wählen", padding=(8, 7))
        second.pack(fill="x", pady=(0, 8))
        self.search_button = ttk.Button(second, text="Spuren suchen", command=self.search)
        self.search_button.pack(side="left")
        self.tracks = ttk.Combobox(second, state="readonly", textvariable=self.selection, width=38)
        self.tracks.pack(side="left", padx=8)
        self.fetch_button = ttk.Button(second, text="Gewählte Spur laden", command=self.fetch, state="disabled")
        self.fetch_button.pack(side="left")
        # These actions remain visible above the scrolling transcript pane.
        btns = ttk.Frame(pane); btns.pack(fill="x", pady=(0, 8))
        self.copy_button = ttk.Button(btns, text="Gesamtes Transkript kopieren", command=self.copy, state="disabled")
        self.copy_button.pack(side="left")
        self.markdown_button = ttk.Button(btns, text="Als Markdown speichern", command=self.save_markdown, state="disabled")
        self.markdown_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(btns, text="Speichern (TXT / SRT / VTT)", command=self.save, state="disabled")
        self.save_button.pack(side="left")
        body = ttk.Frame(pane); body.pack(fill="both", expand=True)
        self.preview = tk.Text(body, wrap="word", font=("Segoe UI", 10), undo=False)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=sb.set, state="disabled", exportselection=False)
        self.preview_context = ContextMenu(self.preview, readonly=True)
        self.preview.pack(side="left", fill="both", expand=True); sb.pack(side="left", fill="y")
        ttk.Label(pane, textvariable=self.status, wraplength=850, foreground="#355681").pack(fill="x", anchor="w")

    def _show_preview(self, content: str):
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", content)
        self.preview.config(state="disabled")

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.quick_button.config(state="disabled" if busy else "normal")
        self.search_button.config(state="disabled" if busy else "normal")
        self.open_button.config(state="disabled" if busy else "normal")
        self.audio_button.config(state="disabled" if busy else "normal")
        self.python_button.config(state="disabled" if busy else "normal")
        self.fetch_button.config(state="normal" if not busy and self.info and self.info.captions else "disabled")
        self.tracks.config(state="disabled" if busy else "readonly")
        self.copy_button.config(state="normal" if not busy and self.cues else "disabled")
        self.save_button.config(state="normal" if not busy and self.cues else "disabled")
        self.markdown_button.config(state="normal" if not busy and self.cues else "disabled")

    def _worker(self, action: str, fn, *args):
        def run():
            try: self.events.put((action, fn(*args), None))
            except Exception as exc: self.events.put((action, None, exc))
        self._set_busy(True)
        threading.Thread(target=run, daemon=True).start()

    def _reset(self):
        self.info = None; self.cues = []; self.option = None; self.text = ""; self.local_name = ""; self.current_url = ""
        self.tracks["values"] = []; self.selection.set(""); self._show_preview(""); self._set_busy(False)

    def open_local(self):
        if self._busy: return
        path = filedialog.askopenfilename(title="Lokale Untertiteldatei öffnen",
            filetypes=[("Untertitel", "*.srt *.vtt"), ("SRT", "*.srt"), ("WebVTT", "*.vtt")])
        if not path: return
        try: cues, encoding = load_subtitle_file_with_encoding(path)
        except TranscriptError as exc:
            messagebox.showerror("Datei öffnen", str(exc)); return
        self._reset()
        self.cues = cues; self.local_name = Path(path).name
        self.text = render_ai_txt(cues, local_name=self.local_name)
        self._show_preview(self.text)
        self.status.set(f"Datei geladen ({encoding}): {self.local_name} – {len(cues)} Untertitelabschnitte.")
        self._set_busy(False)

    def choose_asr_python(self):
        if self._busy: return
        python = filedialog.askopenfilename(title="Python.exe der vorhandenen Whisper-/GPU-Umgebung wählen",
            filetypes=[("Python", "python.exe"), ("Programme", "*.exe"), ("Alle Dateien", "*.*")])
        if python:
            if not Path(python).is_file():
                messagebox.showerror("ASR-Python", "Der gewählte Python-Interpreter existiert nicht.")
                return
            self.asr_python = python
            self.status.set(f"ASR-Python gewählt: {Path(python).name}. Kein Eingriff in andere Anwendungen.")

    @staticmethod
    def _run_asr(python_exe: str, media: str, folder: str) -> dict:
        argv = [python_exe, str(Path(__file__).resolve().with_name("local_asr.py")),
                "--input", media, "--output-dir", folder]
        try:
            completed = subprocess.run(argv, shell=False, capture_output=True, text=True,
                                      timeout=3 * 60 * 60, encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TranscriptError(f"Whisper-Python konnte nicht ausgeführt werden: {exc}") from exc
        payload = next((line[len(ASR_MARKER):] for line in reversed(completed.stdout.splitlines())
                        if line.startswith(ASR_MARKER)), None)
        if completed.returncode != 0 or payload is None:
            message = next((line for line in reversed(completed.stderr.splitlines()) if "YTX_ASR_ERROR:" in line), "")
            raise TranscriptError((message or completed.stderr.strip() or "Whisper ohne lesbares Ergebnis")[:400]
                                  + " | Falls Whisper fehlt: 'Whisper-Python wählen …' verwenden.")
        try: return json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise TranscriptError("Whisper-Ergebnis konnte nicht gelesen werden.") from exc

    def open_audio(self):
        if self._busy: return
        media = filedialog.askopenfilename(title="Bereits vorhandene, zulässig nutzbare lokale Mediendatei wählen",
            filetypes=[("Mediendateien", "*.wav *.mp3 *.m4a *.mp4 *.webm *.flac *.ogg *.opus *.aac *.wma *.mkv *.mov"),
                       ("Alle Dateien", "*.*")])
        if not media: return
        try: verify_source(media)
        except Exception as exc:
            messagebox.showerror("Audiodatei", str(exc)); return
        folder = output_folder()
        self._reset()
        self.status.set("Whisper arbeitet offline an EINER ausgewählten Datei. Es werden keine YouTube-Medien geladen …")
        self._worker("audio", self._run_asr, self.asr_python, media, str(folder))

    def _loaded_audio(self, data: dict):
        try:
            cues = [Cue(int(c["start_ms"]), int(c["end_ms"]), str(c["text"])) for c in data["cues"]]
            if not cues: raise ValueError("no cues")
            result = AsrTranscript(str(data["source_name"]), str(data["sha256"]), str(data["language"]),
                                   str(data["model"]), str(data["device"]), float(data["seconds"]), tuple(cues))
            paths = dict(data["outputs"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TranscriptError("Ungültiger Datensatz vom Whisper-Prozess.") from exc
        self.info = None; self.option = None; self.cues = cues
        self.local_name = result.source_name
        self.text = ai_text(result)
        self._show_preview(self.text)
        self.status.set(f"Lokale Whisper-Transkription: {len(cues)} Segmente · {result.language} · {result.device} · TXT/SRT/VTT im Ordner {Path(paths['txt']).parent}")

    def quick(self):
        if self._busy: return
        url = self.url.get()
        self._reset()
        self.status.set("Untertitel suchen und beste Originalspur laden …")
        self._worker("quick", retrieve_best, url)

    def search(self):
        if self._busy: return
        url = self.url.get()
        self._reset()
        self.status.set("Untertitelspuren werden abgefragt …")
        self._worker("search", get_video_info, url)

    def fetch(self):
        if self._busy or not self.info: return
        try: current = normalize_youtube_url(self.url.get())
        except TranscriptError:
            messagebox.showwarning("Link geändert", "Bitte für den neuen Link zuerst erneut Spuren suchen."); return
        if current != self.current_url:
            messagebox.showwarning("Link geändert", "Videolink wurde geändert. Bitte erneut Spuren suchen."); return
        opt = next((x for x in self.info.captions if x.label == self.selection.get()), None)
        if opt is None:
            messagebox.showwarning("Spurauswahl", "Bitte eine Untertitelspur wählen."); return
        self.option = opt; self.cues = []; self.text = ""; self._show_preview("")
        self.status.set("Gewählte Untertitel werden geladen …")
        self._worker("fetch", fetch_subtitles, self.info, opt)

    def _loaded(self, cues):
        self.cues = cues
        self.text = render_ai_txt(cues, info=self.info, option=self.option, local_name=self.local_name)
        self._show_preview(self.text)
        self.status.set(f"{len(cues)} Untertitelabschnitte geladen · {'maschinelle Übersetzung! ' if self.option and self.option.translated else ''}TXT ist Standard · kopieren oder speichern.")

    def _poll(self):
        try:
            while True:
                action, value, error = self.events.get_nowait()
                self._set_busy(False)
                if error is not None:
                    msg = str(error)[:450] if isinstance(error, TranscriptError) else f"Unerwarteter Fehler: {str(error)[:300]}"
                    self.status.set(msg); messagebox.showerror("Abruf fehlgeschlagen", msg); continue
                if action == "search":
                    self.info = value
                    self.current_url = "https://www.youtube.com/watch?v=" + value.video_id
                    options = [c.label for c in value.captions]
                    self.tracks["values"] = options; self.selection.set(options[0] if options else "")
                    translations = sum(o.translated for o in value.captions)
                    extra = (f" · {translations} maschinelle Übersetzungen" if translations else "")
                    extra += (" · Deno prüfen!" if value.warning else "")
                    self.status.set((f"{value.title} · {len(options)} Spuren{extra}" if options else "Keine zugänglichen VTT/SRT-Untertitel gefunden.") )
                elif action == "quick":
                    self.info, self.option, cues = value
                    self.current_url = "https://www.youtube.com/watch?v=" + self.info.video_id
                    options = [c.label for c in self.info.captions]
                    self.tracks["values"] = options; self.selection.set(self.option.label)
                    self._loaded(cues)
                    self.copy()
                    self.status.set(f"Transkript kopiert · {len(cues)} Abschnitte · {self.option.label}" + (" · Deno prüfen" if self.info.warning else ""))
                elif action == "fetch": self._loaded(value)
                elif action == "audio":
                    try: self._loaded_audio(value)
                    except TranscriptError as exc:
                        self.status.set(str(exc)); messagebox.showerror("ASR-Ausgabe", str(exc))
                self._set_busy(False)
        except Empty: pass
        self.root.after(100, self._poll)

    def copy(self):
        if not self.cues: return
        self.root.clipboard_clear(); self.root.clipboard_append(self.text)
        self.status.set("Gesamtes KI-taugliches Transkript in Zwischenablage kopiert.")

    def save_markdown(self):
        if not self.cues:
            return
        path = filedialog.asksaveasfilename(title="Transkript als Markdown speichern",
            defaultextension=".md", filetypes=[("Markdown", "*.md")],
            initialfile=f"transkript_{self.info.video_id if self.info else 'lokal'}.md")
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".md":
            messagebox.showerror("Format", "Bitte eine Markdown-Datei (.md) auswählen.")
            return
        if target.exists() and not messagebox.askyesno("Überschreiben?", f"Datei {target.name} existiert. Überschreiben?"):
            return
        try:
            target.write_text("# Transkript\\n\\n" + self.text.strip() + "\\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Speichern fehlgeschlagen", str(exc))
            return
        self.status.set(f"Markdown gespeichert: {target}")

    def save(self):
        if not self.cues: return
        path = filedialog.asksaveasfilename(title="Transkript speichern", defaultextension=".txt",
            filetypes=[("Textdatei (KI-tauglich)", "*.txt"), ("SRT", "*.srt"), ("WebVTT", "*.vtt")],
            initialfile=f"transkript_{self.info.video_id if self.info else 'lokal'}.txt")
        if not path: return
        target = Path(path); ext = target.suffix.lower()
        if ext not in {".txt", ".srt", ".vtt"}:
            messagebox.showerror("Format", "Bitte .txt, .srt oder .vtt wählen."); return
        if target.exists() and not messagebox.askyesno("Überschreiben?", f"Datei {target.name} existiert. Überschreiben?"):
            return
        content = self.text if ext == ".txt" else (make_srt(self.cues) if ext == ".srt" else make_vtt(self.cues))
        try: target.write_text(content, encoding="utf-8-sig" if ext == ".txt" else "utf-8")
        except OSError as exc:
            messagebox.showerror("Speichern fehlgeschlagen", str(exc)); return
        self.status.set(f"Gespeichert: {target}")


def main():
    root = tk.Tk(); ExtractorApp(root); root.mainloop()

if __name__ == "__main__": main()
