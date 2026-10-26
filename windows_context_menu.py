"""Windows-style clipboard context menus for editable Tk Entry and readonly Text.

No shell integration or global keyboard hooks. All actions stay inside the app.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ContextMenu:
    def __init__(self, widget: tk.Widget, *, readonly: bool = False):
        if not isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
            raise TypeError("Unsupported context-menu widget")
        self.widget = widget
        self.readonly = readonly
        self.menu = tk.Menu(widget, tearoff=False)
        if not readonly:
            self.menu.add_command(label="Ausschneiden", command=self.cut)
        self.menu.add_command(label="Kopieren", command=self.copy)
        if not readonly:
            self.menu.add_command(label="Einfügen", command=self.paste)
        self.menu.add_separator()
        self.menu.add_command(label="Alles markieren", command=self.select_all)
        if readonly:
            self.menu.add_command(label="Gesamten Text kopieren", command=self.copy_all)
        widget.bind("<Button-3>", self.popup, add="+")
        widget.bind("<Shift-F10>", self.keyboard_popup, add="+")
        widget.bind("<Menu>", self.keyboard_popup, add="+")
        for chord, handler in (
            ("a", self.select_all), ("c", self.copy),
            ("x", self.cut), ("v", self.paste),
        ):
            if readonly and chord in ("x", "v"):
                continue
            for key in (chord.lower(), chord.upper()):
                widget.bind("<Control-" + key + ">", self._shortcut(handler), add="+")

    @staticmethod
    def _shortcut(handler):
        def callback(event):
            handler()
            return "break"
        return callback

    def _text(self):
        return isinstance(self.widget, tk.Text)

    def _selected(self) -> str:
        try:
            if self._text():
                return self.widget.get("sel.first", "sel.last")
            if self.widget.selection_present():
                # exportselection=False disables PRIMARY on some Tk builds:
                # querying selection_get() here would wrongly lose the selection.
                text = self.widget.get()
                return text[self.widget.index("sel.first"):self.widget.index("sel.last")]
        except tk.TclError:
            pass
        return ""

    def _writable(self) -> bool:
        return not self.readonly and str(self.widget.cget("state")) == "normal"

    def _set_clipboard(self, value: str) -> None:
        self.widget.clipboard_clear()
        self.widget.clipboard_append(value)
        self.widget.update_idletasks()

    def copy(self) -> None:
        selected = self._selected()
        if selected:
            self._set_clipboard(selected)

    def copy_all(self) -> None:
        value = self.widget.get("1.0", "end-1c") if self._text() else self.widget.get()
        if value:
            self._set_clipboard(value)

    def cut(self) -> None:
        if not self._writable():
            return
        selected = self._selected()
        if selected:
            self._set_clipboard(selected)
            self.widget.delete("sel.first", "sel.last")

    def paste(self) -> None:
        if not self._writable():
            return
        try:
            value = self.widget.clipboard_get()
        except tk.TclError:
            return
        if self._text():
            if self._selected():
                self.widget.delete("sel.first", "sel.last")
            self.widget.insert("insert", value)
        else:
            if self.widget.selection_present():
                self.widget.delete("sel.first", "sel.last")
            self.widget.insert("insert", value)

    def select_all(self) -> None:
        if self._text():
            self.widget.tag_add("sel", "1.0", "end-1c")
            self.widget.mark_set("insert", "1.0")
        else:
            self.widget.selection_range(0, "end")
            self.widget.icursor("end")
        self.widget.focus_set()

    def _update_menu(self) -> None:
        selected = bool(self._selected())
        try:
            can_paste = bool(self.widget.clipboard_get())
        except tk.TclError:
            can_paste = False
        self.menu.entryconfigure("Kopieren", state="normal" if selected else "disabled")
        if not self.readonly:
            editable = self._writable()
            self.menu.entryconfigure("Ausschneiden", state="normal" if editable and selected else "disabled")
            self.menu.entryconfigure("Einfügen", state="normal" if editable and can_paste else "disabled")
        else:
            value = self.widget.get("1.0", "end-1c")
            self.menu.entryconfigure("Gesamten Text kopieren", state="normal" if value else "disabled")

    def popup(self, event: tk.Event) -> str:
        self.widget.focus_set()
        self._update_menu()
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()
        return "break"

    def keyboard_popup(self, event: tk.Event) -> str:
        self.widget.focus_set()
        self._update_menu()
        try:
            self.menu.tk_popup(self.widget.winfo_rootx() + 18, self.widget.winfo_rooty() + 18)
        finally:
            self.menu.grab_release()
        return "break"
