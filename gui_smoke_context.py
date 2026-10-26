"""Tkinter GUI smoke: right-click clipboard, shortcuts, readonly view and Markdown.
Run: python gui_smoke_context.py  (Windows desktop or Linux xvfb-run -a)
No live YouTube fetch, audio download or Whisper/model invocation.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import tkinter as tk

import app
from transcript_core import Cue

root = tk.Tk()
ui = app.ExtractorApp(root)
root.update()
results = []


def check(label, success):
    success = bool(success)
    results.append(success)
    print(("PASS " if success else "FAIL ") + label)


try:
    check("v0.1.6 app", "v0.1.6" in root.title())
    entry_menu = ui.url_context.menu
    check("editable menu labels", [entry_menu.entrycget(i, "label") for i in (0, 1, 2, 4)] ==
          ["Ausschneiden", "Kopieren", "Einfügen", "Alles markieren"])
    view_menu = ui.preview_context.menu
    check("readonly menu labels", [view_menu.entrycget(i, "label") for i in (0, 2, 3)] ==
          ["Kopieren", "Alles markieren", "Gesamten Text kopieren"])
    ui.url.set("alpha beta")
    ui.url_entry.selection_range(0, 5)
    ui.url_context.copy()
    check("selected URL copy", root.clipboard_get() == "alpha")
    ui.url_context.cut()
    check("selected URL cut", ui.url.get() == " beta")
    ui.url_entry.icursor(0)
    ui.url_context.paste()
    check("URL paste", ui.url.get() == "alpha beta")
    ui.url_context.select_all()
    check("URL select all", ui.url_context._selected() == "alpha beta")
    ui.url_context._update_menu()
    check("menu enables edit actions", all(entry_menu.entrycget(i, "state") == "normal" for i in (0, 1, 2)))
    ui.url_entry.selection_clear()
    ui.url_context._update_menu()
    check("menu disables unselected cut/copy", entry_menu.entrycget(0, "state") == "disabled"
          and entry_menu.entrycget(1, "state") == "disabled")
    root.clipboard_clear()
    ui.url_context.paste()
    check("missing clipboard harmless", ui.url.get() == "alpha beta")
    check("keyboard paste bound", bool(ui.url_entry.bind("<Control-v>")))
    check("keyboard menu bound", bool(ui.url_entry.bind("<Shift-F10>")))
    ui.cues = [Cue(0, 1200, "Grüße سلام")]
    ui.text = "Grüße سلام\nnext line"
    ui._show_preview(ui.text)
    ui._set_busy(False)
    root.update()
    check("readonly preview", str(ui.preview.cget("state")) == "disabled")
    ui.preview_context.select_all()
    check("readonly selection", bool(ui.preview.tag_ranges("sel")))
    ui.preview_context.copy()
    check("readonly copy selection", root.clipboard_get() == ui.text)
    ui.preview.tag_remove("sel", "1.0", "end")
    ui.preview_context._update_menu()
    check("no selection disables copy", view_menu.entrycget("Kopieren", "state") == "disabled")
    ui.preview_context.copy_all()
    check("readonly copy all", root.clipboard_get() == ui.text)
    ui.preview_context.cut()
    ui.preview_context.paste()
    check("readonly stays untouched", ui.preview.get("1.0", "end-1c") == ui.text)
    check("copy button enabled", str(ui.copy_button.cget("state")) == "normal")
    check("Markdown button enabled", str(ui.markdown_button.cget("state")) == "normal")
    with TemporaryDirectory() as temp:
        target = Path(temp) / "notes.md"
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(target)):
            ui.save_markdown()
        check("Unicode Markdown", target.read_text(encoding="utf-8") ==
              "# Transkript\n\nGrüße سلام\nnext line\n")
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(target)), \
             patch.object(app.messagebox, "askyesno", return_value=False):
            ui.save_markdown()
        check("no overwrite on rejection", target.read_text(encoding="utf-8").startswith("# Transkript"))
finally:
    root.destroy()

print(f"{sum(results)}/{len(results)} context-menu GUI checks")
sys.exit(0 if all(results) else 1)
