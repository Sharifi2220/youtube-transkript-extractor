"""Run in a Tk-enabled graphical session or under xvfb-run (Linux). Synthetic data only."""
import sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
import tkinter as tk
from tkinter import filedialog, messagebox
import app
import transcript_core as t

passes = []
def check(msg, value):
    print(('PASS ' if value else 'FAIL ') + msg)
    passes.append(bool(value))

msgs=[]
messagebox.showerror=lambda *a,**k: msgs.append(('error',a))
messagebox.showwarning=lambda *a,**k: msgs.append(('warning',a))
messagebox.askyesno=lambda *a,**k: True
root=tk.Tk()
a=app.ExtractorApp(root);root.update()
check('Fenster-Version v0.1.6', 'v0.1.6' in root.title())
check('Linkeingabe startet leer', a.url.get() == '')
with tempfile.TemporaryDirectory() as d:
    p=Path(d)
    f=Path(__file__).with_name('beispiel_OFFLINE_SYNTHETISCH.vtt')
    filedialog.askopenfilename=lambda **k: str(f)
    a.open_local();root.update()
    check('lokale Testdatei geladen',len(a.cues)>0)
    check('Unicode Persisch/Umlaute', 'سلام' in a.text and 'Grüße' in a.text)
    check('Vorschau schreibgeschützt',str(a.preview.cget('state'))=='disabled')
    check('Text in Vorschau',a.text.strip() in a.preview.get('1.0','end'))
    a.copy();root.update()
    check('Kopieren aller Zeichen', root.clipboard_get()==a.text)
    for ext in ('txt','srt','vtt'):
        target=p/f'export.{ext}'
        filedialog.asksaveasfilename=lambda **k, :str(target)
        a.save()
        check(f'{ext.upper()} exportiert',target.exists())
        if ext != 'txt': check(f'{ext.upper()} zurücklesbar',t.load_subtitle_file(target)==a.cues)
        else: check('TXT hat UTF-8 BOM',target.read_bytes().startswith(b'\xef\xbb\xbf'))
    cp=p/'alt.srt';cp.write_bytes('1\n00:00:00,000 --> 00:00:01,000\nGrüße\n'.encode('cp1252'))
    filedialog.askopenfilename=lambda **k:str(cp)
    a.open_local();root.update()
    check('Windows-1252-Fallback kenntlich', 'Windows-1252' in a.status.get())
    broken=p/'broken.vtt'; broken.write_text('Nichts',encoding='utf-8')
    filedialog.askopenfilename=lambda **k:str(broken)
    n=len(msgs);a.open_local()
    check('Fehlerdialog bei defekter Datei',len(msgs)==n+1 and msgs[-1][0]=='error')
    opts=(t.CaptionOption('en-orig','auto'),t.CaptionOption('de','auto',True))
    info=t.VideoInfo('e_4YEmG9KyU','SYNTHETISCH',opts)
    cues=[t.Cue(500,1200,'Hello سلام'),t.Cue(62000,63500,'World Grüße')]
    def fake_retrieve(u):return info,opts[0],cues
    with patch.object(app,'retrieve_best',side_effect=fake_retrieve) as call:
        a.quick()
        for i in range(60):
            root.update();time.sleep(.02)
            if a.info:break
    check('Ein-Klick-Funktion 1 Aufruf',call.call_count==1)
    check('Originalspur vorübersetzt',a.option==opts[0])
    check('TXT wurde automatisch kopiert',root.clipboard_get()==a.text)
    check('AI-TXT mit 2 Zeitmarken','[00:00:00]' in a.text and '[00:01:00]' in a.text)
    check('Daten mit Quelle und Spur', 'Quelle:' in a.text and 'en-orig' in a.text)
    # Search records URL ID; manual fetch cannot act on changed video.
    with patch.object(app,'get_video_info',return_value=info):
        a.search()
        for i in range(60):
            root.update();time.sleep(.02)
            if a.info:break
    a.url.set('https://youtu.be/AAAAAAAAAAA')
    n=len(msgs);a.fetch()
    check('Linkänderung geblockt',len(msgs)==n+1 and msgs[-1][0]=='warning')
root.destroy()
print(f'{sum(passes)}/{len(passes)} GUI-Smoke-Checks bestanden')
sys.exit(0 if all(passes) else 1)
