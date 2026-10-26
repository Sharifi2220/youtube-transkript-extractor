"""Synthetic v0.1.5 GUI verification; no actual model, GPU, YouTube or internet."""
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import filedialog, messagebox
import app

checks=[]
def check(label,yes):
    checks.append(bool(yes));print(('PASS ' if yes else 'FAIL ')+label)

messagebox.showerror=lambda *a,**k: None
messagebox.showwarning=lambda *a,**k: None
root=tk.Tk();ui=app.ExtractorApp(root);root.update()
check('GUI v0.1.5 vorhanden','v0.1.5' in root.title())
check('ASR-Schaltfläche vorhanden',str(ui.audio_button.cget('state'))=='normal')
check('Whisper-Python-Wahl vorhanden',str(ui.python_button.cget('state'))=='normal')
with tempfile.TemporaryDirectory() as tmp:
    source=Path(tmp)/'test_audio.wav';source.write_bytes(b'offline-fake-media')
    fake={"source_name":source.name,"sha256":"a"*64,"language":"de","model":"base","device":"cuda","seconds":1.42,
          "cues":[{"start_ms":0,"end_ms":1300,"text":"Lokaler Test"},{"start_ms":60500,"end_ms":62000,"text":"سلام"}],
          "outputs":{"txt":str(Path(tmp)/'test_audio.asr.txt'),"srt":str(Path(tmp)/'test_audio.asr.srt'),
                     "vtt":str(Path(tmp)/'test_audio.asr.vtt'),"json":str(Path(tmp)/'test_audio.asr.json')}}
    with patch.object(filedialog,'askopenfilename',return_value=str(source)), patch.object(app.ExtractorApp,'_run_asr',return_value=fake) as mock:
        ui.open_audio()
        for i in range(150):
            root.update();time.sleep(.01)
            if ui.cues:break
    check('genau ein lokaler ASR-Aufruf',mock.call_count==1)
    check('ASR-Transkript wurde angezeigt','Lokaler Test' in ui.text and 'سلام' in ui.text)
    check('Provenienz als ASR statt YouTube', 'LOKALE WHISPER' in ui.text and 'youtube.com/watch' not in ui.text)
    check('ASR-Originalsprache und Modell notiert','Sprache (automatisch erkannt): de' in ui.text and 'Whisper base' in ui.text)
    check('Vorschau schreibgeschützt',str(ui.preview.cget('state'))=='disabled')
    check('Whisper kopieren möglich',str(ui.copy_button.cget('state'))=='normal')
    check('Status gesetzt', bool(ui.status.get().strip()))
root.destroy()
print(f'{sum(checks)}/{len(checks)} ASR-GUI-Smoke-Checks')
sys.exit(0 if all(checks) else 1)
