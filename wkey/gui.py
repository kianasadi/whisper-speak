"""
Minimal Apple-style GUI for whisper-keyboard.

A compact, floating window with macOS-inspired aesthetics including:
- Semi-transparent dark mode design
- Status indicator for recording states
- Hotkey display and configuration
- Auto-enter toggle
- Optional prompt input

Usage:
    from wkey.gui import main
    main()
"""

import os
import threading
import queue
import subprocess
from typing import Optional, Callable

import customtkinter as ctk
import numpy as np
from scipy.io import wavfile
import sounddevice as sd
from pynput.keyboard import Controller as KeyboardController, Key, Listener

from wkey.whisper import apply_whisper
from wkey.utils import process_transcript, apply_gpt_correction
from wkey.key_config import (
    get_config, get_hotkey, get_hotkey_label, get_auto_enter,
    set_auto_enter, toggle_auto_enter, get_language, set_language,
    get_use_llm, set_use_llm, get_auto_enter_key, get_auto_enter_key_label,
    get_autostart, set_autostart, get_send_mode, set_send_mode
)

# Supported languages (ISO-639-1 codes)
LANGUAGES = {
    "sv": "Svenska",
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "pl": "Polski",
    "ru": "Русский",
    "ja": "日本語",
    "zh": "中文",
    "ko": "한국어",
    "ar": "العربية",
    "hi": "हिन्दी",
    "no": "Norsk",
    "da": "Dansk",
    "fi": "Suomi",
}

# Configure customtkinter for dark mode with Apple-like appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Status states
STATUS_READY = "ready"
STATUS_RECORDING = "recording"
STATUS_PROCESSING = "processing"

# Status indicator symbols and colors
STATUS_CONFIG = {
    STATUS_READY: {"symbol": "\u25cf", "color": "#34C759", "text": "Ready"},  # Green circle
    STATUS_RECORDING: {"symbol": "\u25c9", "color": "#FF3B30", "text": "Recording"},  # Red target
    STATUS_PROCESSING: {"symbol": "\u25cb", "color": "#FF9500", "text": "Processing"},  # Orange hollow
}

# Apple-style colors
COLORS = {
    "bg_dark": "#1C1C1E",
    "bg_secondary": "#2C2C2E",
    "bg_tertiary": "#3A3A3C",
    "text_primary": "#FFFFFF",
    "text_secondary": "#8E8E93",
    "accent": "#007AFF",
    "success": "#34C759",
    "warning": "#FF9500",
    "error": "#FF3B30",
    "border": "#38383A",
}


class WKeyGUI(ctk.CTk):
    """
    Minimal Apple-style floating window for whisper-keyboard.
    """

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("wkey")
        self.geometry("320x445")
        self.minsize(280, 405)
        self.configure(fg_color=COLORS["bg_dark"])

        # Make window float on top and give it a minimal appearance
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.95)  # Slight transparency

        # macOS specific: remove title bar chrome for cleaner look
        # Note: This may not work on all systems
        try:
            self.overrideredirect(False)  # Keep title bar for dragging
        except Exception:
            pass

        # State variables
        self._status = STATUS_READY
        self._recording = False
        self._audio_data = []
        self._sample_rate = 16000
        self._keyboard_controller = KeyboardController()
        self._key_config = get_config()
        self._current_prompt = self._load_prompt()
        self._gui_hotkey_change_mode = False  # Track GUI-initiated hotkey change mode
        self._gui_auto_enter_key_change_mode = False  # Track GUI-initiated auto-enter key change mode
        self._ignore_next_click = False  # Ignore click right after entering change mode
        self._recording_with_auto_enter = False  # Track if recording was started with auto-enter key
        self._help_mode = False  # Track if help tooltips are enabled
        self._tooltip = None  # Current tooltip window
        self._tooltip_descriptions = {}  # Widget -> description mapping

        # Queue for thread-safe GUI updates
        self._update_queue = queue.Queue()

        # Build UI
        self._create_widgets()

        # Set up callbacks for key config changes
        self._key_config.set_change_callback(self._on_hotkey_change)
        self._key_config.set_auto_enter_callback(self._on_auto_enter_change)
        self._key_config.set_auto_enter_key_callback(self._on_auto_enter_key_change)

        # Start background threads
        self._start_audio_stream()
        self._start_keyboard_listener()

        # Start queue processor
        self._process_queue()

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Force UI update after initialization
        self.after(100, self._finalize_init)

    def _finalize_init(self):
        """Finalize initialization after window is fully loaded."""
        self.update_idletasks()

    def _create_widgets(self):
        """Create all GUI widgets with Apple-style design."""
        # Main container with padding
        self.main_frame = ctk.CTkFrame(
            self,
            fg_color="transparent",
            corner_radius=0
        )
        self.main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        # --- Status Section (Ready indicator alone) ---
        self.status_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS["bg_secondary"],
            corner_radius=12
        )
        self.status_frame.pack(fill="x", pady=(0, 12))

        self.status_inner = ctk.CTkFrame(
            self.status_frame,
            fg_color="transparent"
        )
        self.status_inner.pack(fill="x", padx=16, pady=12)

        self.status_indicator = ctk.CTkLabel(
            self.status_inner,
            text=STATUS_CONFIG[STATUS_READY]["symbol"],
            font=ctk.CTkFont(size=24),
            text_color=STATUS_CONFIG[STATUS_READY]["color"]
        )
        self.status_indicator.pack(side="left")

        self.status_text = ctk.CTkLabel(
            self.status_inner,
            text=STATUS_CONFIG[STATUS_READY]["text"],
            font=ctk.CTkFont(family="SF Pro Display", size=16, weight="bold"),
            text_color=COLORS["text_primary"]
        )
        self.status_text.pack(side="left", padx=(8, 0))

        # Help switch (top right, in status box)
        self.help_label = ctk.CTkLabel(
            self.status_inner,
            text="?",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text_secondary"],
            width=20
        )
        self.help_label.pack(side="right", padx=(0, 4))

        self.help_switch = ctk.CTkSwitch(
            self.status_inner,
            text="",
            width=36,
            height=18,
            switch_width=32,
            switch_height=16,
            command=self._toggle_help_mode,
            progress_color=COLORS["accent"],
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["text_primary"]
        )
        self.help_switch.pack(side="right")

        # --- Controls Section ---
        self.controls_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color=COLORS["bg_secondary"],
            corner_radius=12
        )
        self.controls_frame.pack(fill="x", pady=(0, 12))

        # 1. Transcription - Listener (hotkey button)
        self.transcription_frame = ctk.CTkFrame(
            self.controls_frame,
            fg_color="transparent"
        )
        self.transcription_frame.pack(fill="x", padx=16, pady=12)

        self.transcription_label = ctk.CTkLabel(
            self.transcription_frame,
            text="Transcription",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_primary"]
        )
        self.transcription_label.pack(side="left")

        self.hotkey_button = ctk.CTkButton(
            self.transcription_frame,
            text=self._format_hotkey(get_hotkey_label()),
            font=ctk.CTkFont(family="SF Mono", size=12),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["border"],
            corner_radius=6,
            width=50,
            height=28,
            command=self._enter_gui_hotkey_change_mode
        )
        self.hotkey_button.pack(side="right")

        # Separator
        self.separator1 = ctk.CTkFrame(
            self.controls_frame,
            height=1,
            fg_color=COLORS["border"]
        )
        self.separator1.pack(fill="x", padx=16)

        # 2. Auto-enter mode - listener + enter toggle
        self.auto_enter_frame = ctk.CTkFrame(
            self.controls_frame,
            fg_color="transparent"
        )
        self.auto_enter_frame.pack(fill="x", padx=16, pady=12)

        self.auto_enter_label = ctk.CTkLabel(
            self.auto_enter_frame,
            text="Auto-enter mode",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_primary"]
        )
        self.auto_enter_label.pack(side="left")

        # Get current auto-enter key label or show "Off"
        auto_enter_key_label = get_auto_enter_key_label()
        auto_enter_display = self._format_hotkey(auto_enter_key_label) if auto_enter_key_label else "Off"

        # Auto-enter key button
        self.auto_enter_button = ctk.CTkButton(
            self.auto_enter_frame,
            text=auto_enter_display,
            font=ctk.CTkFont(family="SF Mono", size=12),
            text_color=COLORS["text_secondary"],
            fg_color=COLORS["bg_tertiary"] if not auto_enter_key_label else COLORS["accent"],
            hover_color=COLORS["border"],
            corner_radius=6,
            width=50,
            height=28,
            command=self._enter_gui_auto_enter_key_change_mode
        )
        self.auto_enter_button.pack(side="right", padx=(6, 0))

        # Send mode segmented button (Enter or Cmd+Enter)
        current_send_mode = get_send_mode()

        self.send_mode_segmented = ctk.CTkSegmentedButton(
            self.auto_enter_frame,
            values=["⏎", "⌘⏎"],
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_tertiary"],
            selected_color=COLORS["accent"],
            selected_hover_color=COLORS["accent"],
            unselected_color=COLORS["bg_tertiary"],
            unselected_hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            corner_radius=6,
            height=28,
            command=self._on_send_mode_change
        )
        self.send_mode_segmented.set("⌘⏎" if current_send_mode == "cmd+enter" else "⏎")
        self.send_mode_segmented.pack(side="right")

        # Separator
        self.separator2 = ctk.CTkFrame(
            self.controls_frame,
            height=1,
            fg_color=COLORS["border"]
        )
        self.separator2.pack(fill="x", padx=16)

        # 3. LLM processing toggle + Prompt
        self.llm_frame = ctk.CTkFrame(
            self.controls_frame,
            fg_color="transparent"
        )
        self.llm_frame.pack(fill="x", padx=16, pady=(12, 6))

        self.llm_label = ctk.CTkLabel(
            self.llm_frame,
            text="LLM processing",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_primary"]
        )
        self.llm_label.pack(side="left")

        self.llm_switch = ctk.CTkSwitch(
            self.llm_frame,
            text="",
            width=44,
            height=24,
            switch_width=40,
            switch_height=20,
            command=self._toggle_llm,
            progress_color=COLORS["accent"],
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["text_primary"]
        )
        self.llm_switch.pack(side="right")
        if get_use_llm():
            self.llm_switch.select()

        # Prompt text box (always visible, below LLM toggle)
        self.prompt_entry = ctk.CTkTextbox(
            self.controls_frame,
            font=ctk.CTkFont(size=13),
            height=80,
            fg_color=COLORS["bg_tertiary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=8,
            text_color=COLORS["text_primary"]
        )
        self.prompt_entry.pack(fill="x", padx=16, pady=(0, 12))
        if self._current_prompt:
            self.prompt_entry.insert("1.0", self._current_prompt)
        self.prompt_entry.bind("<FocusOut>", self._on_prompt_change)

        # Separator
        self.separator3 = ctk.CTkFrame(
            self.controls_frame,
            height=1,
            fg_color=COLORS["border"]
        )
        self.separator3.pack(fill="x", padx=16)

        # 4. Language dropdown
        self.language_frame = ctk.CTkFrame(
            self.controls_frame,
            fg_color="transparent"
        )
        self.language_frame.pack(fill="x", padx=16, pady=12)

        self.language_label = ctk.CTkLabel(
            self.language_frame,
            text="Language",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_primary"]
        )
        self.language_label.pack(side="left")

        current_lang = get_language()
        lang_values = list(LANGUAGES.values())
        current_display = LANGUAGES.get(current_lang, "Svenska")

        self.language_dropdown = ctk.CTkOptionMenu(
            self.language_frame,
            values=lang_values,
            command=self._on_language_change,
            width=120,
            height=28,
            font=ctk.CTkFont(size=12),
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["bg_tertiary"],
            button_hover_color=COLORS["border"],
            dropdown_fg_color=COLORS["bg_secondary"],
            dropdown_hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_primary"]
        )
        self.language_dropdown.set(current_display)
        self.language_dropdown.pack(side="right")

        # Separator
        self.separator4 = ctk.CTkFrame(
            self.controls_frame,
            height=1,
            fg_color=COLORS["border"]
        )
        self.separator4.pack(fill="x", padx=16)

        # 5. Start with computer toggle
        self.autostart_frame = ctk.CTkFrame(
            self.controls_frame,
            fg_color="transparent"
        )
        self.autostart_frame.pack(fill="x", padx=16, pady=12)

        self.autostart_label = ctk.CTkLabel(
            self.autostart_frame,
            text="Start with computer",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["text_primary"]
        )
        self.autostart_label.pack(side="left")

        self.autostart_switch = ctk.CTkSwitch(
            self.autostart_frame,
            text="",
            width=44,
            height=24,
            switch_width=40,
            switch_height=20,
            command=self._toggle_autostart,
            progress_color=COLORS["accent"],
            fg_color=COLORS["bg_tertiary"],
            button_color=COLORS["text_primary"]
        )
        self.autostart_switch.pack(side="right")
        if get_autostart():
            self.autostart_switch.select()

        # Setup tooltip descriptions
        self._setup_tooltips()

    def _setup_tooltips(self):
        """Setup tooltip descriptions for all interactive elements."""
        self._tooltip_descriptions = {
            # Status section
            self.status_indicator: "Visar appens status:\n● Grön = Redo\n● Röd = Spelar in\n● Orange = Bearbetar",
            self.status_text: "Visar appens status:\n● Ready = Redo att spela in\n● Recording = Spelar in\n● Processing = Transkriberar",
            # Transcription
            self.transcription_label: "Vanlig transkription.\nHåll tangenten → spela in → släpp → text skrivs.",
            self.hotkey_button: "Klicka för att välja inspelningstangent.\nHåll tangenten för att spela in,\nsläpp för att transkribera.",
            # Auto-enter mode
            self.auto_enter_label: "Transkription + automatisk sändning.\nHåll tangenten → spela in → släpp → text skrivs + skickas.",
            self.auto_enter_button: "Klicka för att välja auto-enter tangent.\nHåll tangenten för att spela in,\nsläpp för att transkribera + skicka.",
            # LLM processing
            self.llm_label: "AI-korrigering av transkription.\nRättar stavfel, grammatik, etc.",
            self.llm_switch: "Aktivera AI-textkorrigering.\nAnvänd prompten nedan för instruktioner.",
            self.prompt_entry: "Skriv instruktioner för AI-korrigering.\nT.ex. 'Skriv formellt' eller 'Översätt till engelska'",
            # Language
            self.language_label: "Språk för Whisper-transkription.",
            self.language_dropdown: "Välj språk för transkription.\nWhisper stödjer 18 språk.",
            # Autostart
            self.autostart_label: "Starta appen vid datorstart.",
            self.autostart_switch: "Starta appen automatiskt\nnär datorn startar."
        }

    def _toggle_help_mode(self):
        """Toggle help mode on/off."""
        print(f">>> _toggle_help_mode called! Current state: {self._help_mode}")
        self._help_mode = not self._help_mode

        if self._help_mode:
            # Enable help mode - bind hover events
            self._bind_tooltips()
        else:
            # Disable help mode
            self._unbind_tooltips()
            self._hide_tooltip()
        print(f">>> _toggle_help_mode done. New state: {self._help_mode}")

    def _bind_tooltips(self):
        """Bind hover events to show tooltips."""
        for widget in self._tooltip_descriptions:
            widget.bind("<Enter>", self._show_tooltip, add="+")
            widget.bind("<Leave>", self._hide_tooltip, add="+")

    def _unbind_tooltips(self):
        """Unbind hover events."""
        for widget in self._tooltip_descriptions:
            widget.unbind("<Enter>")
            widget.unbind("<Leave>")

    def _show_tooltip(self, event):
        """Show tooltip for the hovered widget."""
        if not self._help_mode:
            return

        widget = event.widget

        # Find the widget in our descriptions (might be a child widget)
        description = None
        for w, desc in self._tooltip_descriptions.items():
            if widget == w or self._is_child_of(widget, w):
                description = desc
                break

        if not description:
            return

        # Hide existing tooltip
        self._hide_tooltip()

        # Create tooltip window
        self._tooltip = ctk.CTkToplevel(self)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.attributes("-topmost", True)

        # Position tooltip near the widget
        x = event.x_root + 10
        y = event.y_root + 10

        # Create tooltip content
        label = ctk.CTkLabel(
            self._tooltip,
            text=description,
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_primary"],
            fg_color=COLORS["bg_secondary"],
            corner_radius=8,
            padx=12,
            pady=8
        )
        label.pack()

        self._tooltip.wm_geometry(f"+{x}+{y}")

    def _hide_tooltip(self, event=None):
        """Hide the current tooltip."""
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    def _is_child_of(self, widget, parent):
        """Check if widget is a child of parent."""
        while widget:
            if widget == parent:
                return True
            try:
                widget = widget.master
            except AttributeError:
                break
        return False

    def _on_focus_out(self, event):
        """Cancel key selection modes when window loses focus."""
        # Cancel any active key change modes when focus is lost
        if self._gui_hotkey_change_mode:
            self._exit_gui_hotkey_change_mode(cancelled=True)
        if self._gui_auto_enter_key_change_mode:
            self._exit_gui_auto_enter_key_change_mode(cancelled=True)

    def _format_hotkey(self, label: str) -> str:
        """Format a key label for display using Apple-style symbols."""
        key_symbols = {
            'ctrl_l': '\u2303L', 'ctrl_r': '\u2303R', 'ctrl': '\u2303',
            'shift_l': '\u21e7L', 'shift_r': '\u21e7R', 'shift': '\u21e7',
            'alt_l': '\u2325L', 'alt_r': '\u2325R', 'alt': '\u2325',
            'cmd_l': '\u2318L', 'cmd_r': '\u2318R', 'cmd': '\u2318',
        }
        return key_symbols.get(label, label.upper())

    def _set_status(self, status: str):
        """Update the status indicator."""
        self._status = status
        config = STATUS_CONFIG[status]
        self._queue_update(lambda: self._update_status_display(config))

    def _update_status_display(self, config: dict):
        """Actually update the status display (must be called from main thread)."""
        self.status_indicator.configure(
            text=config["symbol"],
            text_color=config["color"]
        )
        self.status_text.configure(text=config["text"])

    def _queue_update(self, func: Callable):
        """Queue a function to be executed in the main thread."""
        self._update_queue.put(func)

    def _process_queue(self):
        """Process queued GUI updates."""
        try:
            while True:
                func = self._update_queue.get_nowait()
                func()
        except queue.Empty:
            pass
        finally:
            self.after(50, self._process_queue)

    def _enter_gui_auto_enter_key_change_mode(self):
        """
        Enter auto-enter key change mode when the GUI button is clicked.
        This activates a listener that reads the next keypress to set as the auto-enter key.
        """
        if self._gui_auto_enter_key_change_mode:
            # Already in change mode, cancel it
            self._exit_gui_auto_enter_key_change_mode(cancelled=True)
            return

        self._gui_auto_enter_key_change_mode = True
        self._ignore_next_click = True  # Ignore the click that activated this mode
        # Update button to indicate listening state and disable it to prevent re-triggering
        self.auto_enter_button.configure(
            text="...",
            fg_color=COLORS["warning"],
            state="disabled"
        )
        # Remove focus from button so Enter key doesn't re-trigger it
        self.focus_set()
        # Put the key_config into change mode so it captures the next key
        self._key_config._enter_auto_enter_key_change_mode()

    def _exit_gui_auto_enter_key_change_mode(self, cancelled=False):
        """Exit auto-enter key change mode."""
        self._gui_auto_enter_key_change_mode = False
        label = get_auto_enter_key_label()
        display = self._format_hotkey(label) if label else "Off"
        self.auto_enter_button.configure(
            text=display,
            fg_color=COLORS["accent"] if label else COLORS["bg_tertiary"],
            state="normal"
        )
        if cancelled:
            self._key_config._exit_auto_enter_key_change_mode(cancelled=True)

    def _on_auto_enter_key_change(self, old_key, new_key):
        """Callback when auto-enter key is changed."""
        label = get_auto_enter_key_label()
        display = self._format_hotkey(label) if label else "Off"
        # Exit GUI auto-enter key change mode if we were in it
        if self._gui_auto_enter_key_change_mode:
            self._gui_auto_enter_key_change_mode = False
        self._queue_update(
            lambda: self.auto_enter_button.configure(
                text=display,
                fg_color=COLORS["accent"] if label else COLORS["bg_tertiary"],
                state="normal"
            )
        )

    def _toggle_autostart(self):
        """Handle autostart toggle."""
        current = get_autostart()
        new_state = not current
        success = set_autostart(new_state)
        if not success:
            # Revert the switch if it failed
            if current:
                self.autostart_switch.select()
            else:
                self.autostart_switch.deselect()

    def _on_language_change(self, selected_name: str):
        """Handle language dropdown change."""
        # Find the code for the selected language name
        for code, name in LANGUAGES.items():
            if name == selected_name:
                set_language(code)
                break

    def _on_send_mode_change(self, selected_value):
        """Handle send mode segmented button change."""
        if selected_value == "⌘⏎":
            set_send_mode("cmd+enter")
        else:
            set_send_mode("enter")

    def _toggle_llm(self):
        """Handle LLM processing toggle."""
        current = get_use_llm()
        new_state = not current
        set_use_llm(new_state)

    def _on_prompt_change(self, event=None):
        """Handle prompt entry changes."""
        new_prompt = self.prompt_entry.get("1.0", "end-1c").strip()
        if new_prompt.lower() == "no prompt":
            self._current_prompt = None
            self.prompt_entry.delete("1.0", "end")
            self._delete_prompt_file()
        elif new_prompt:
            self._current_prompt = new_prompt
            self._save_prompt(new_prompt)
        else:
            self._current_prompt = None
            self._delete_prompt_file()

    def _enter_gui_hotkey_change_mode(self):
        """
        Enter hotkey change mode when the GUI button is clicked.
        This activates a listener that reads the next keypress to set as the new hotkey.
        """
        if self._gui_hotkey_change_mode:
            # Already in change mode, cancel it
            self._exit_gui_hotkey_change_mode(cancelled=True)
            return

        self._gui_hotkey_change_mode = True
        self._ignore_next_click = True  # Ignore the click that activated this mode
        # Update button to indicate listening state and disable it to prevent re-triggering
        self.hotkey_button.configure(
            text="...",
            fg_color=COLORS["accent"],
            state="disabled"
        )
        # Remove focus from button so Enter key doesn't re-trigger it
        self.focus_set()
        # Put the key_config into change mode so it captures the next key
        self._key_config._enter_change_mode()

    def _exit_gui_hotkey_change_mode(self, cancelled=False):
        """Exit hotkey change mode."""
        self._gui_hotkey_change_mode = False
        label = get_hotkey_label()
        self.hotkey_button.configure(
            text=self._format_hotkey(label),
            fg_color=COLORS["bg_tertiary"],
            state="normal"
        )
        if cancelled:
            self._key_config._exit_change_mode(cancelled=True)

    def _on_hotkey_change(self, old_key, new_key):
        """Callback when hotkey is changed."""
        label = get_hotkey_label()
        # Exit GUI hotkey change mode if we were in it
        if self._gui_hotkey_change_mode:
            self._gui_hotkey_change_mode = False
        self._queue_update(
            lambda: self.hotkey_button.configure(
                text=self._format_hotkey(label),
                fg_color=COLORS["bg_tertiary"],
                state="normal"
            )
        )

    def _on_auto_enter_change(self, new_state: bool):
        """Callback when auto-enter is toggled via keyboard shortcut."""
        label = get_auto_enter_key_label()
        display = self._format_hotkey(label) if label else "Off"
        self._queue_update(
            lambda: self.auto_enter_button.configure(
                text=display,
                fg_color=COLORS["accent"] if new_state and label else COLORS["bg_tertiary"]
            )
        )

    # --- Prompt File Management ---

    def _get_prompt_file_path(self) -> str:
        """Get the path to the prompt file."""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_prompt")

    def _save_prompt(self, prompt: str):
        """Save prompt to file."""
        try:
            with open(self._get_prompt_file_path(), "w") as f:
                f.write(prompt)
        except Exception:
            pass

    def _load_prompt(self) -> Optional[str]:
        """Load prompt from file."""
        try:
            path = self._get_prompt_file_path()
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
        return None

    def _delete_prompt_file(self):
        """Delete the prompt file."""
        try:
            path = self._get_prompt_file_path()
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    # --- Audio Recording ---

    def _start_audio_stream(self):
        """Start the audio input stream."""
        self._stream = sd.InputStream(
            callback=self._audio_callback,
            channels=1,
            samplerate=self._sample_rate
        )
        self._stream.start()

    def _audio_callback(self, indata, frames, time, status):
        """Audio stream callback - collects audio data when recording."""
        if self._recording:
            self._audio_data.append(indata.copy())

    # --- Keyboard Listener ---

    def _start_keyboard_listener(self):
        """Start the keyboard listener in a background thread."""
        self._listener = Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self._listener.start()

    def _on_key_press(self, key):
        """Handle key press events with robust error handling."""
        try:
            # Check if we're in GUI-initiated hotkey change mode
            if self._gui_hotkey_change_mode:
                # Let key_config capture the key
                try:
                    if self._key_config._capture_new_hotkey(key):
                        return
                except Exception as e:
                    print(f"Warning: Error in hotkey capture: {e}")
                    self._exit_gui_hotkey_change_mode(cancelled=True)
                    return

            # Check if we're in GUI-initiated auto-enter key change mode
            if self._gui_auto_enter_key_change_mode:
                # Let key_config capture the key
                try:
                    if self._key_config._capture_new_auto_enter_key(key):
                        return
                except Exception as e:
                    print(f"Warning: Error in auto-enter key capture: {e}")
                    self._exit_gui_auto_enter_key_change_mode(cancelled=True)
                    return

            # Let key_config handle hotkey change mode (Ctrl+Shift+K)
            try:
                if self._key_config.handle_key_press(key):
                    return
            except Exception as e:
                print(f"Warning: Error handling key press in config: {e}")

            # Skip if in key change mode
            if self._key_config.is_in_change_mode():
                return

            # Check if this is the hotkey for recording
            try:
                if key == get_hotkey():
                    self._recording = True
                    self._recording_with_auto_enter = False
                    self._audio_data = []
                    self._set_status(STATUS_RECORDING)
                # Check if this is the auto-enter hotkey for recording (second hotkey)
                elif key == get_auto_enter_key():
                    self._recording = True
                    self._recording_with_auto_enter = True  # Flag to press Enter after
                    self._audio_data = []
                    self._set_status(STATUS_RECORDING)
            except Exception as e:
                print(f"Warning: Error comparing hotkey: {e}")
        except Exception as e:
            # Catch-all to prevent any crash from key press handling
            print(f"Warning: Unexpected error in _on_key_press: {e}")

    def _on_key_release(self, key):
        """Handle key release events with robust error handling."""
        try:
            # Let key_config track modifier releases
            try:
                self._key_config.handle_key_release(key)
            except Exception as e:
                print(f"Warning: Error handling key release in config: {e}")

            # Skip if in key change mode (either GUI or keyboard initiated)
            if self._key_config.is_in_change_mode() or self._gui_hotkey_change_mode or self._gui_auto_enter_key_change_mode:
                return

            # Check if this is the hotkey or auto-enter key being released to stop recording
            try:
                is_hotkey = key == get_hotkey()
                is_auto_enter_key = key == get_auto_enter_key()

                if (is_hotkey or is_auto_enter_key) and self._recording:
                    self._recording = False
                    self._set_status(STATUS_PROCESSING)

                    # Process audio in background thread
                    audio_data = self._audio_data.copy()
                    use_auto_enter = self._recording_with_auto_enter
                    threading.Thread(
                        target=self._process_audio,
                        args=(audio_data, use_auto_enter),
                        daemon=True
                    ).start()
            except Exception as e:
                print(f"Warning: Error comparing hotkey on release: {e}")
                self._recording = False
                self._set_status(STATUS_READY)
        except Exception as e:
            # Catch-all to prevent any crash from key release handling
            print(f"Warning: Unexpected error in _on_key_release: {e}")

    def _process_audio(self, audio_data: list, use_auto_enter: bool = False):
        """Process recorded audio and transcribe."""
        # Thresholds for silence/hallucination detection
        MIN_AUDIO_DURATION_SECONDS = 0.5
        MIN_RMS_THRESHOLD = 0.005  # Minimum RMS energy to consider as non-silence
        MIN_TRANSCRIPT_LENGTH = 2  # Minimum characters for valid transcript

        # Common Whisper hallucination phrases (often appear with silence)
        HALLUCINATION_PHRASES = [
            "tack alla som tittat",
            "thanks for watching",
            "thank you for watching",
            "subscribe",
            "like and subscribe",
            "see you next time",
            "bye bye",
            "goodbye",
            "music",
            "applause",
            "[music]",
            "[applause]",
            "you",
            "...",
            "the end",
            "subtitles by",
            "captions by",
        ]

        try:
            if not audio_data:
                self._set_status(STATUS_READY)
                return

            audio_data_np = np.concatenate(audio_data, axis=0)

            # Check 1: Audio duration
            audio_duration = len(audio_data_np) / self._sample_rate
            if audio_duration < MIN_AUDIO_DURATION_SECONDS:
                print(f"Audio too short ({audio_duration:.2f}s < {MIN_AUDIO_DURATION_SECONDS}s), skipping transcription")
                self._set_status(STATUS_READY)
                return

            # Check 2: Audio energy (RMS)
            rms = np.sqrt(np.mean(audio_data_np ** 2))
            if rms < MIN_RMS_THRESHOLD:
                print(f"Audio too quiet (RMS={rms:.6f} < {MIN_RMS_THRESHOLD}), likely silence, skipping transcription")
                self._set_status(STATUS_READY)
                return

            audio_data_int16 = (audio_data_np * np.iinfo(np.int16).max).astype(np.int16)

            wavfile.write('recording.wav', self._sample_rate, audio_data_int16)

            # Convert to m4a for faster upload
            file_to_transcribe = 'recording.wav'
            try:
                subprocess.run(
                    ['ffmpeg', '-i', 'recording.wav', '-c:a', 'aac', '-b:a', '32k', 'recording.m4a', '-y'],
                    check=True,
                    capture_output=True
                )
                file_to_transcribe = 'recording.m4a'
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

            # Transcribe with language setting
            transcript = None
            try:
                language = get_language()
                transcript = apply_whisper(file_to_transcribe, 'transcribe', language=language)
            except Exception as e:
                # Handle API errors (e.g., invalid request, audio too short)
                if "Invalid" in str(e) or "audio" in str(e).lower():
                    print(f"Transcription error: {e}")
                    self._set_status(STATUS_READY)
                    return
                raise

            # Check 3: Filter empty/short transcripts
            if not transcript or len(transcript.strip()) < MIN_TRANSCRIPT_LENGTH:
                print(f"Transcript too short or empty, skipping")
                self._set_status(STATUS_READY)
                return

            # Check 4: Filter common hallucination phrases
            transcript_lower = transcript.strip().lower()
            for phrase in HALLUCINATION_PHRASES:
                if transcript_lower == phrase or transcript_lower.startswith(phrase):
                    print(f"Detected hallucination phrase: '{transcript}', skipping")
                    self._set_status(STATUS_READY)
                    return

            if transcript:
                # Apply LLM correction only if enabled and prompt is set
                if get_use_llm() and self._current_prompt:
                    transcript = apply_gpt_correction(transcript, self._current_prompt)

                processed_transcript = process_transcript(transcript)

                # Type the text
                self._keyboard_controller.type(processed_transcript)

                # Press Enter or Cmd+Enter based on send mode setting
                if use_auto_enter:
                    try:
                        import time
                        time.sleep(0.3)  # Delay to let the app process the typed text

                        # Release all modifier keys to ensure clean Enter press
                        for mod_key in [Key.shift, Key.shift_l, Key.shift_r,
                                        Key.ctrl, Key.ctrl_l, Key.ctrl_r,
                                        Key.alt, Key.alt_l, Key.alt_r,
                                        Key.cmd, Key.cmd_l, Key.cmd_r]:
                            try:
                                self._keyboard_controller.release(mod_key)
                            except:
                                pass

                        time.sleep(0.05)  # Small delay after releasing modifiers

                        send_mode = get_send_mode()
                        if send_mode == "cmd+enter":
                            self._keyboard_controller.press(Key.cmd)
                            self._keyboard_controller.press(Key.enter)
                            self._keyboard_controller.release(Key.enter)
                            self._keyboard_controller.release(Key.cmd)
                        else:
                            self._keyboard_controller.press(Key.enter)
                            self._keyboard_controller.release(Key.enter)
                    except Exception as e:
                        print(f"Warning: Could not press send key: {e}")

        except ValueError:
            pass  # Empty audio data
        except Exception as e:
            print(f"Error processing audio: {str(e)}")
        finally:
            self._set_status(STATUS_READY)

    def _on_close(self):
        """Handle window close."""
        try:
            if hasattr(self, '_stream'):
                self._stream.stop()
                self._stream.close()
            if hasattr(self, '_listener'):
                self._listener.stop()
        except Exception:
            pass
        self.destroy()


def main():
    """Main entry point for the GUI application."""
    app = WKeyGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
