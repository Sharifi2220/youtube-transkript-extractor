# YouTube Transkript Extractor

**Entwicklungsstand v0.1.6-dev (Rechtsklick-/UX-Update in Prüfung) · Windows-first · lokal · kein Abo / keine Registrierung**

Ein kleines Desktop-Programm, das vorhandene YouTube-Untertitel abruft, anzeigt, kopiert und als **TXT, SRT oder VTT** speichert. Als **separate optionale Funktion** lassen sich bereits rechtmäßig vorhandene lokale Audio-/Videodateien mit einer eigenen Whisper-Installation transkribieren. Die Verarbeitung läuft auf deinem PC – es gibt keinen Projekt-Cloudserver.

**English:** A small, local-first Windows desktop app for retrieving available YouTube captions, copying text and exporting TXT/SRT/VTT. Optional, user-selected local audio/video transcription using an existing OpenAI Whisper installation (CPU or GPU). No bundled AI model, account, subscription or cloud service.

## Windows-Bedienung (v0.1.6-dev im Entwicklungsbranch)

Im YouTube-Linkfeld öffnet ein **Rechtsklick** die Befehle **Ausschneiden**, **Kopieren**, **Einfügen** und **Alles markieren**. Im **schreibgeschützten Transkript** stehen **Kopieren**, **Alles markieren** und **Gesamten Text kopieren** bereit. Die Auswahl kann außerdem über `Strg+C/X/V/A` bedient werden; das Kontextmenü ist über `Shift+F10` erreichbar. Im Transkript sind Ausschneiden/Einfügen bewusst gesperrt. Die Schaltflächen **Gesamtes Transkript kopieren**, **Als Markdown speichern** und **TXT/SRT/VTT speichern** befinden sich oberhalb der Vorschau.

Die Markdown-Datei ist ein lokaler UTF-8-Export mit dem erkannten Transkripttext und dem Dateiformat `.md`, etwa für Obsidian. Der Export fragt vor dem Überschreiben einer bereits vorhandenen Datei. Es werden dafür keine zusätzlichen Pakete oder Netzwerkdienste benötigt.

**Hinweis:** Diese Funktion ist derzeit im Feature-Branch zur Windows-Abnahme vorbereitet. Das Release `v0.1.5-dev` bleibt bis zur abgeschlossenen Windows-Prüfung unverändert. GUI-Smoketest auf einem Windows-Desktop: `python gui_smoke_context.py`. Kein YouTube-, Medien- oder GPU-Download im Test.

## Schnellstart auf Windows

1. Unter **Code → Download ZIP** den Quellcode herunterladen und entpacken. Python **3.11+** mit `tkinter` muss installiert sein. Das Programm ist derzeit **Quellcode, keine `.exe`**.
2. `INSTALL_WINDOWS.bat` ausführen. Die Datei legt eine lokale `.venv` an und installiert `yt-dlp[default]` aus `requirements.txt` – mit Internetverbindung und nur nach deiner Entscheidung.
3. Für zuverlässigen YouTube-Abruf eine unterstützte JavaScript-Laufzeit bereitstellen, vorzugsweise **Deno** (Versionsempfehlung und aktuelle Installation siehe [yt-dlp EJS](https://github.com/yt-dlp/yt-dlp/wiki/EJS)). `deno.exe` kann neben `app.py` liegen oder Deno ist bereits auf dem Rechner verfügbar. **Deno wird nicht mitgeliefert.**
4. `START_WINDOWS.bat` doppelklicken, einen YouTube-Videolink einfügen und **„Link → Transkript kopieren“** auswählen. Für Sprache/Spurwahl gibt es den manuellen Ablauf. Über **Speichern** TXT/SRT/VTT erzeugen.

Du kannst zu `START_WINDOWS.bat` eine Desktop-Verknüpfung erstellen. Es gibt keinen automatischen Systemstart, keine Adminpflicht und kein automatisches Softwareupdate.

## Lokale Audio-/Videotranskription (optional)

Die Taste **„Lokale Audiodatei → Whisper-Transkript“** verarbeitet **eine ausdrücklich gewählte lokale Datei**. Unterstützt werden WAV, MP3, M4A, MP4, WEBM, FLAC, OGG, OPUS, AAC, WMA, MKV und MOV (Decodierung über eine kompatible `ffmpeg`-Installation).

Benötigt werden ein bereits installiertes **`openai-whisper`**-Paket, PyTorch und ein **bereits gecachtes Modell `base.pt`** in `~/.cache/whisper/base.pt`. Das Programm lädt nicht eigenständig Modelle nach und installiert weder PyTorch noch GPU-Treiber. Mit **„Whisper-Python wählen …“** kann ein separat installierter Python-Interpreter ausgewählt werden, der Whisper/PyTorch bereits besitzt; alternativ ist `YTX_ASR_PYTHON` möglich. CUDA wird verwendet, wenn es verfügbar ist, sonst CPU.

Die Ergebnisse heißen `<Dateiname>.asr.txt`, `.asr.srt`, `.asr.vtt` und `.asr.json` und werden standardmäßig im Ordner `TRANSKRIPTE_TESTAUSGABEN` gespeichert. Bestehende Dateien werden nicht überschrieben; die Quelldatei wird vor und nach dem Lauf über SHA-256 geprüft.

**Wichtig:** Bei YouTube-Videos **ohne zugängliche Untertitel** gibt es keinen automatischen Audio-Download oder YouTube-ASR-Fallback. Die lokale Mediendatei muss separat rechtmäßig vorliegen. Die Spracherkennung kann Wörter, Sprachen und Zeitmarken falsch erkennen.

## Qualität und Datenschutz

- Bevorzugt werden Originaluntertitel, soweit sie über die Metadaten eindeutig erkennbar sind. Automatische Untertitel und maschinelle Übersetzungen werden gekennzeichnet. Keine Zusage für alle Videos oder Sprachen.
- Die TXT-Ausgabe bereinigt überlappende automatisch erzeugte Untertitel konservativ; **TXT ist keine garantiert wortgetreue Abschrift**. SRT/VTT behalten die erkannten Cues und Zeitmarken.
- Der YouTube-Pfad fragt Metadaten und Untertitel ab, **kein Audio/Video**. Dabei findet zwangsläufig eine Verbindung zu YouTube statt. Es werden keine Nutzer-Cookies automatisiert ausgelesen.
- Der optionale lokale Whisper-Pfad wählt Dateien per Dialog, lädt keine Modelle selbst herunter und sendet die Medien nicht an einen eigenen Server.
- Keine Zuordnung zu YouTube oder dessen Eigentümern. Urheberrecht, Berechtigungen und [YouTube-Nutzungsbedingungen](https://www.youtube.com/t/terms) müssen eingehalten werden; die Möglichkeit des Abrufs ist keine Erlaubnis zum Weiterveröffentlichen fremder Texte.

## Entwickler und Tests

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py transcript_core.py local_asr.py tests
```

GUI-Smokes (`python gui_smoke_v014.py` und `python gui_smoke_v015.py`) brauchen eine grafische Windows-/Tk-Umgebung. Es gibt keinen automatisierten YouTube-Livezugriff in Tests oder CI. Der GitHub-Workflow führt nur Unit-Tests und Syntaxprüfungen aus.

**Prüfstand:** Das ursprüngliche Projektpaket bestand 60 Unit-Tests und 30 synthetische GUI-Smokes unter Linux. Für diesen öffentlichen Quellstand liefen unter Windows/Python 3.14 und 3.15 jeweils 59 Unit-Tests erfolgreich, ein Symlink-Test wurde mangels Berechtigung übersprungen; 21 Untertitel- und 10 ASR-GUI-Smokes bestanden. Ältere Windows-Praxisbelege betreffen den Untertitelabruf für **ein** zugängliches Video, den Start über eine Desktop-Verknüpfung und GPU-Whisper mit einer **synthetischen** WAV-Datei. Ein Genauigkeitstest mit realem gesprochenem Material und breite Videoabdeckung fehlen. Der öffentliche Quellstand startet mit leerem Linkfeld und speichert lokale ASR-Ausgaben neben der Anwendung; diese Änderungen sind nur durch die genannten Offline-Tests geprüft.

## Lizenzen

**Eigener Quellcode: MIT-Lizenz** (siehe `LICENSE`). Fremde Abhängigkeiten werden **nicht** in diesem Repository gebündelt; sie behalten ihre eigenen Lizenzen. Details in `THIRD_PARTY_NOTICES.md`. Bitte keine fremden Videos/Transkripte, Passwörter, privaten Pfade oder große Modelle in Issues/Commits hochladen.

Beiträge und Fehlermeldungen sind willkommen – siehe `CONTRIBUTING.md` und `SECURITY.md`.

## English guide

**YouTube Transcript Extractor — local-first captions, one-click copy, TXT/SRT/VTT export.** This is an early Windows source-code preview, not an installer or `.exe`. It retrieves captions when a video makes them available. A separate optional mode transcribes one user-selected local media file with an existing Whisper setup.

### Install and use on Windows

1. Download the repository source ZIP and extract it. Install Python **3.11 or newer** with `tkinter` if it is not already available.
2. Run `INSTALL_WINDOWS.bat` when you choose to install the pinned `yt-dlp[default]` dependency into this project's `.venv`. The script needs an internet connection; it does not install Deno, Whisper, Torch or FFmpeg. The pinned version is a reproducible starting point, not an automatic update policy.
3. For YouTube caption retrieval, a compatible JavaScript runtime may be necessary. Follow the current [yt-dlp EJS instructions](https://github.com/yt-dlp/yt-dlp/wiki/EJS); Deno is not bundled. Run `START_WINDOWS.bat`, paste a single YouTube video link, then choose **“Link → Transkript kopieren”**. Select a track manually if needed. Save TXT, SRT or VTT from the preview.

The URL field starts empty. Caption lookup makes network requests to YouTube and may fail because captions are absent, blocked, translated, incomplete or changed upstream. The app does not read browser cookies or download YouTube audio/video. It is not affiliated with YouTube. Respect copyright, permissions and the [YouTube Terms](https://www.youtube.com/t/terms); availability of captions does not grant redistribution rights.

### Optional local Whisper mode

Choose **“Lokale Audiodatei → Whisper-Transkript”** and select one local file you are allowed to process. Provide your own compatible `openai-whisper`, PyTorch and FFmpeg installation and an already cached `base.pt` model. Select that Python interpreter with **“Whisper-Python wählen …”** or set `YTX_ASR_PYTHON`. The app does not download a model or media for this mode. CPU is used unless CUDA is available in the selected runtime. Results go to `TRANSKRIPTE_TESTAUSGABEN` beside the application as TXT/SRT/VTT/JSON; existing ASR output files are not overwritten. Speech recognition and timestamps are estimates and may be wrong.

### Development, privacy and support

Run offline tests with:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app.py transcript_core.py local_asr.py tests
python gui_smoke_v014.py
python gui_smoke_v015.py
```

The GUI smoke tests need a graphical Tk session and use synthetic fixtures. CI runs unit tests and syntax checks on Windows; it does not fetch live YouTube captions or process real media. Caption retrieval contacts YouTube from your computer. Local Whisper mode processes the chosen file on your computer; this project operates no cloud server. Avoid posting private transcripts, media or local paths in public issues. Use the repository's GitHub Issues tab for ordinary bugs and `SECURITY.md` for sensitive reports. Contributions are described in `CONTRIBUTING.md`. Project code is MIT-licensed; third-party tools keep their own licenses (`THIRD_PARTY_NOTICES.md`).
