"""
PyQt6-based GUI for whisper-keyboard.

A compact, floating window with dark mode design including:
- Status indicator for recording states
- Hotkey display and configuration
- Auto-enter toggle
- Optional prompt input

Usage:
    from wkey.gui_pyqt import main
    main()
"""

import os
import sys

# Load environment variables EARLY, before other imports that may need them
def _early_load_env():
    """Load .env file early, before other modules are imported."""
    home_config = os.path.expanduser("~/.whisper-speak")
    home_env = os.path.join(home_config, ".env")

    # Check home config first (for bundled app)
    if os.path.exists(home_env):
        env_path = home_env
    else:
        # Try project root (development mode)
        project_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(project_env):
            env_path = project_env
        else:
            return  # No .env file found

    # Load the .env file
    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value:
                        os.environ[key] = value
    except Exception:
        pass

_early_load_env()

import threading
import subprocess
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTextEdit, QFrame, QCheckBox,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QEvent, QPoint
from PyQt6.QtGui import QFont, QColor, QPalette, QCursor
from PyQt6.QtWidgets import QToolTip, QSizePolicy

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
    "fr": "Fran\u00e7ais",
    "es": "Espa\u00f1ol",
    "it": "Italiano",
    "pt": "Portugu\u00eas",
    "nl": "Nederlands",
    "pl": "Polski",
    "ru": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
    "ja": "\u65e5\u672c\u8a9e",
    "zh": "\u4e2d\u6587",
    "ko": "\ud55c\uad6d\uc5b4",
    "ar": "\u0627\u0644\u0639\u0631\u0628\u064a\u0629",
    "hi": "\u0939\u093f\u0928\u094d\u0926\u0940",
    "no": "Norsk",
    "da": "Dansk",
    "fi": "Suomi",
}

# Status states
STATUS_READY = "ready"
STATUS_RECORDING = "recording"
STATUS_PROCESSING = "processing"

# Status indicator config
STATUS_CONFIG = {
    STATUS_READY: {"symbol": "\u25cf", "color": "#34C759", "text": "Ready"},
    STATUS_RECORDING: {"symbol": "\u25c9", "color": "#FF3B30", "text": "Recording"},
    STATUS_PROCESSING: {"symbol": "\u25cb", "color": "#FF9500", "text": "Processing"},
}

# Colors
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


def _get_env_file_path() -> str:
    """Get the path to the .env file."""
    # For bundled apps, use ~/.whisper-speak/.env
    # For development, use project root
    home_config = os.path.expanduser("~/.whisper-speak")
    home_env = os.path.join(home_config, ".env")

    # If home config exists or we're running as bundled app, use home directory
    if os.path.exists(home_env) or getattr(sys, 'frozen', False):
        os.makedirs(home_config, exist_ok=True)
        return home_env

    # Otherwise try project root (development mode)
    project_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(project_env):
        return project_env

    # Default to home config
    os.makedirs(home_config, exist_ok=True)
    return home_env


def _load_env_values() -> dict:
    """Load current values from the .env file."""
    env_values = {
        "OPENAI_API_KEY": "",
        "OPENAI_API_BASE": "",
        "OPENAI_MODEL": "",
        "WHISPER_MODEL": "",
    }
    env_path = _get_env_file_path()
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        if key in env_values:
                            env_values[key] = value
        except Exception:
            pass
    return env_values


def _save_env_values(values: dict):
    """Save values to the .env file and update runtime environment."""
    env_path = _get_env_file_path()
    existing_lines = []
    existing_keys = set()

    # Read existing file
    if os.path.exists(env_path):
        try:
            with open(env_path, "r") as f:
                for line in f:
                    original_line = line
                    line_stripped = line.strip()
                    if line_stripped and not line_stripped.startswith("#") and "=" in line_stripped:
                        key = line_stripped.split("=", 1)[0].strip()
                        existing_keys.add(key)
                        if key in values:
                            # Replace with new value
                            existing_lines.append(f"{key}={values[key]}\n")
                        else:
                            existing_lines.append(original_line if original_line.endswith("\n") else original_line + "\n")
                    else:
                        existing_lines.append(original_line if original_line.endswith("\n") else original_line + "\n")
        except Exception:
            pass

    # Add any new keys that weren't in the file
    for key, value in values.items():
        if key not in existing_keys and value:
            existing_lines.append(f"{key}={value}\n")

    # Write back
    try:
        with open(env_path, "w") as f:
            f.writelines(existing_lines)
    except Exception as e:
        print(f"Error saving .env file: {e}")

    # Update runtime environment variables
    # (whisper.py and utils.py will pick these up when creating their clients)
    for key, value in values.items():
        if value:
            os.environ[key] = value


def _mask_api_key(key: str) -> str:
    """Mask API key for display, showing only last 4 characters."""
    if not key or len(key) <= 4:
        return key
    return "*" * (len(key) - 4) + key[-4:]


class InstructionsDialog(QDialog):
    """Dialog for editing LLM instructions/prompt."""

    def __init__(self, current_prompt: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Instructions")
        self.setFixedSize(500, 350)
        self.setModal(True)
        self._current_prompt = current_prompt
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        """Create dialog UI elements."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel("LLM Instructions")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        # Description
        desc = QLabel("Enter instructions for how the LLM should process your transcribed text:")
        desc.setObjectName("dialogDesc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Prompt text area
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setObjectName("promptEditDialog")
        self.prompt_edit.setPlaceholderText("Example: Fix grammar and spelling errors. Keep the tone casual.")
        if self._current_prompt:
            self.prompt_edit.setPlainText(self._current_prompt)
        layout.addWidget(self.prompt_edit)

        # Button box
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("clearButton")
        self.clear_button.clicked.connect(self._clear_prompt)
        button_layout.addWidget(self.clear_button)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("saveButton")
        self.save_button.clicked.connect(self.accept)
        button_layout.addWidget(self.save_button)

        layout.addLayout(button_layout)

    def _apply_styles(self):
        """Apply dark mode styles to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS["bg_dark"]};
            }}
            QLabel {{
                color: {COLORS["text_primary"]};
                font-size: 13px;
            }}
            QLabel#dialogTitle {{
                font-size: 18px;
                font-weight: bold;
                color: {COLORS["text_primary"]};
            }}
            QLabel#dialogDesc {{
                color: {COLORS["text_secondary"]};
                font-size: 12px;
            }}
            QTextEdit {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_primary"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
            }}
            QTextEdit:focus {{
                border: 1px solid {COLORS["accent"]};
            }}
            QPushButton {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_primary"]};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {COLORS["border"]};
            }}
            QPushButton#saveButton {{
                background-color: {COLORS["accent"]};
                color: {COLORS["text_primary"]};
            }}
            QPushButton#saveButton:hover {{
                background-color: #0066DD;
            }}
        """)

    def _clear_prompt(self):
        """Clear the prompt text."""
        self.prompt_edit.clear()

    def get_prompt(self) -> str:
        """Get the current prompt text."""
        return self.prompt_edit.toPlainText().strip()


class APIKeysDialog(QDialog):
    """Dialog for configuring API keys and settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API Keys Configuration")
        self.setFixedSize(550, 320)
        self.setModal(True)

        # Store original values to detect changes
        self._original_values = _load_env_values()
        self._api_key_changed = False

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self):
        """Create dialog UI elements."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title
        title = QLabel("API Configuration")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        # Form layout for fields
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # API Key field
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setObjectName("apiKeyEdit")
        self.api_key_edit.setPlaceholderText("Enter API key...")
        masked_key = _mask_api_key(self._original_values.get("OPENAI_API_KEY", ""))
        self.api_key_edit.setText(masked_key)
        self.api_key_edit.textChanged.connect(self._on_api_key_changed)
        form_layout.addRow("API Key:", self.api_key_edit)

        # API Base URL field
        self.api_base_edit = QLineEdit()
        self.api_base_edit.setObjectName("apiBaseEdit")
        self.api_base_edit.setPlaceholderText("https://api.openai.com/v1")
        self.api_base_edit.setText(self._original_values.get("OPENAI_API_BASE", ""))
        form_layout.addRow("API Base URL:", self.api_base_edit)

        # LLM Model field
        self.llm_model_edit = QLineEdit()
        self.llm_model_edit.setObjectName("llmModelEdit")
        self.llm_model_edit.setPlaceholderText("gpt-3.5-turbo")
        self.llm_model_edit.setText(self._original_values.get("OPENAI_MODEL", ""))
        form_layout.addRow("LLM Model:", self.llm_model_edit)

        # Whisper Model field
        self.whisper_model_edit = QLineEdit()
        self.whisper_model_edit.setObjectName("whisperModelEdit")
        self.whisper_model_edit.setPlaceholderText("whisper-1")
        self.whisper_model_edit.setText(self._original_values.get("WHISPER_MODEL", ""))
        form_layout.addRow("Whisper Model:", self.whisper_model_edit)

        layout.addLayout(form_layout)
        layout.addStretch()

        # Button box
        button_box = QDialogButtonBox()
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("saveButton")
        self.save_button.clicked.connect(self._save_and_close)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.reject)

        button_box.addButton(self.save_button, QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(button_box)

    def _on_api_key_changed(self, text):
        """Track if user has modified the API key field."""
        # If the text no longer matches the masked version, user is editing
        masked = _mask_api_key(self._original_values.get("OPENAI_API_KEY", ""))
        if text != masked:
            self._api_key_changed = True

    def _apply_styles(self):
        """Apply dark mode styles to the dialog."""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS["bg_dark"]};
            }}
            QLabel {{
                color: {COLORS["text_primary"]};
                font-size: 13px;
            }}
            QLabel#dialogTitle {{
                font-size: 18px;
                font-weight: bold;
                color: {COLORS["text_primary"]};
            }}
            QLineEdit {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_primary"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 6px;
                padding: 8px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {COLORS["accent"]};
            }}
            QPushButton {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_primary"]};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                background-color: {COLORS["border"]};
            }}
            QPushButton#saveButton {{
                background-color: {COLORS["accent"]};
                color: {COLORS["text_primary"]};
            }}
            QPushButton#saveButton:hover {{
                background-color: #0066DD;
            }}
        """)

    def _save_and_close(self):
        """Save the configuration and close the dialog."""
        values = {}

        # Only save API key if it was actually changed (not the masked version)
        if self._api_key_changed:
            new_key = self.api_key_edit.text().strip()
            # Don't save if it's still the masked version or contains asterisks
            if new_key and "*" not in new_key:
                values["OPENAI_API_KEY"] = new_key
            else:
                # Keep original key
                values["OPENAI_API_KEY"] = self._original_values.get("OPENAI_API_KEY", "")
        else:
            values["OPENAI_API_KEY"] = self._original_values.get("OPENAI_API_KEY", "")

        values["OPENAI_API_BASE"] = self.api_base_edit.text().strip()
        values["OPENAI_MODEL"] = self.llm_model_edit.text().strip()
        values["WHISPER_MODEL"] = self.whisper_model_edit.text().strip()

        _save_env_values(values)
        self.accept()


class ToggleSwitch(QPushButton):
    """Custom toggle switch widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(44, 24)
        self._update_style()
        self.clicked.connect(self._update_style)

    def _update_style(self):
        """Update the switch appearance based on state."""
        if self.isChecked():
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS["accent"]};
                    border-radius: 12px;
                    border: none;
                }}
                QPushButton::after {{
                    content: "";
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS["bg_tertiary"]};
                    border-radius: 12px;
                    border: none;
                }}
            """)

    def paintEvent(self, event):
        """Custom paint to draw the switch knob."""
        super().paintEvent(event)
        from PyQt6.QtGui import QPainter, QBrush, QColor as QC
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw the knob
        knob_diameter = 18
        knob_margin = 3
        if self.isChecked():
            knob_x = self.width() - knob_diameter - knob_margin
        else:
            knob_x = knob_margin
        knob_y = (self.height() - knob_diameter) // 2

        painter.setBrush(QBrush(QC("#FFFFFF")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(knob_x, knob_y, knob_diameter, knob_diameter)
        painter.end()


class InstantTooltipFilter(QObject):
    """Event filter to show tooltips instantly on hover."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter:
            tooltip = obj.toolTip()
            if tooltip:
                # Show tooltip immediately at cursor position
                QToolTip.showText(QCursor.pos(), tooltip, obj)
        elif event.type() == QEvent.Type.Leave:
            QToolTip.hideText()
        return super().eventFilter(obj, event)


class SignalEmitter(QObject):
    """Thread-safe signal emitter for GUI updates."""
    status_changed = pyqtSignal(str)
    hotkey_changed = pyqtSignal()
    auto_enter_key_changed = pyqtSignal()


class WKeyGUI(QMainWindow):
    """PyQt6-based GUI for whisper-keyboard."""

    def __init__(self):
        super().__init__()

        # Signal emitter for thread-safe updates
        self._signals = SignalEmitter()
        self._signals.status_changed.connect(self._update_status_display)
        self._signals.hotkey_changed.connect(self._update_hotkey_display)
        self._signals.auto_enter_key_changed.connect(self._update_auto_enter_key_display)

        # State variables
        self._status = STATUS_READY
        self._recording = False
        self._audio_data = []
        self._sample_rate = 16000
        self._keyboard_controller = KeyboardController()
        self._key_config = get_config()
        self._current_prompt = self._load_prompt()
        self._gui_hotkey_change_mode = False
        self._gui_auto_enter_key_change_mode = False
        self._recording_with_auto_enter = False

        # Setup UI
        self._setup_window()
        self._create_widgets()
        self._apply_styles()

        # Set up callbacks for key config changes
        self._key_config.set_change_callback(self._on_hotkey_change)
        self._key_config.set_auto_enter_callback(self._on_auto_enter_change)
        self._key_config.set_auto_enter_key_callback(self._on_auto_enter_key_change)

        # Start background threads
        self._start_audio_stream()
        self._start_keyboard_listener()

    def _setup_window(self):
        """Configure the main window."""
        self.setWindowTitle("Viska")
        self.setFixedSize(320, 340)
        # Position window at top-right of screen
        self.move(100, 100)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Window
        )
        # Set window opacity
        self.setWindowOpacity(0.95)

    def _create_widgets(self):
        """Create all GUI widgets."""
        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # --- Status Section ---
        self.status_frame = QFrame()
        self.status_frame.setObjectName("statusFrame")
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(16, 14, 16, 14)

        self.status_indicator = QLabel(STATUS_CONFIG[STATUS_READY]["symbol"])
        self.status_indicator.setObjectName("statusIndicator")
        self.status_indicator.setStyleSheet(f"color: {STATUS_CONFIG[STATUS_READY]['color']}; font-size: 24px;")
        status_layout.addWidget(self.status_indicator)

        self.status_text = QLabel(STATUS_CONFIG[STATUS_READY]["text"])
        self.status_text.setObjectName("statusText")
        status_layout.addWidget(self.status_text)
        status_layout.addStretch()

        # Help toggle button
        self.help_button = QPushButton("?")
        self.help_button.setObjectName("helpButton")
        self.help_button.setCheckable(True)
        self.help_button.setFixedSize(28, 28)
        self.help_button.clicked.connect(self._toggle_help_mode)
        status_layout.addWidget(self.help_button)

        main_layout.addWidget(self.status_frame)

        # --- Controls Section ---
        controls_frame = QFrame()
        controls_frame.setObjectName("controlsFrame")
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(16, 16, 16, 16)
        controls_layout.setSpacing(18)

        # 1. Transcription row
        self.trans_row_frame = QFrame()
        self.trans_row_frame.setObjectName("transRowFrame")
        self.trans_row_frame.setFixedHeight(28)
        trans_row = QHBoxLayout(self.trans_row_frame)
        trans_row.setContentsMargins(0, 0, 0, 0)
        trans_label = QLabel("Transcription")
        trans_row.addWidget(trans_label)
        trans_row.addStretch()

        self.hotkey_button = QPushButton(self._format_hotkey(get_hotkey_label()))
        self.hotkey_button.setObjectName("hotkeyButton")
        self.hotkey_button.setFixedSize(60, 28)
        self.hotkey_button.clicked.connect(self._enter_gui_hotkey_change_mode)
        trans_row.addWidget(self.hotkey_button)
        controls_layout.addWidget(self.trans_row_frame)

        # 2. Auto-enter mode row
        self.auto_row_frame = QFrame()
        self.auto_row_frame.setObjectName("autoRowFrame")
        self.auto_row_frame.setFixedHeight(28)
        auto_row = QHBoxLayout(self.auto_row_frame)
        auto_row.setContentsMargins(0, 0, 0, 0)
        auto_label = QLabel("Auto-enter mode")
        auto_row.addWidget(auto_label)
        auto_row.addStretch()

        # Send mode toggle button
        current_send_mode = get_send_mode()
        send_text = "\u2318\u23ce" if current_send_mode == "cmd+enter" else "\u23ce"
        self.send_mode_button = QPushButton(send_text)
        self.send_mode_button.setObjectName("sendModeButton")
        self.send_mode_button.setFixedSize(45, 28)
        self.send_mode_button.clicked.connect(self._toggle_send_mode)
        auto_row.addWidget(self.send_mode_button)

        # Auto-enter key button
        auto_enter_key_label = get_auto_enter_key_label()
        auto_enter_display = self._format_hotkey(auto_enter_key_label) if auto_enter_key_label else "Off"
        self.auto_enter_button = QPushButton(auto_enter_display)
        self.auto_enter_button.setObjectName("autoEnterButton" if auto_enter_key_label else "autoEnterButtonOff")
        self.auto_enter_button.setFixedSize(60, 28)
        self.auto_enter_button.clicked.connect(self._enter_gui_auto_enter_key_change_mode)
        auto_row.addWidget(self.auto_enter_button)
        controls_layout.addWidget(self.auto_row_frame)

        # 3. LLM processing section
        self.llm_section_frame = QFrame()
        self.llm_section_frame.setObjectName("llmSectionFrame")
        self.llm_section_frame.setFixedHeight(28)
        llm_row = QHBoxLayout(self.llm_section_frame)
        llm_row.setContentsMargins(0, 0, 0, 0)
        llm_label = QLabel("LLM processing")
        llm_row.addWidget(llm_label)
        llm_row.addStretch()

        self.llm_switch = ToggleSwitch()
        self.llm_switch.setChecked(get_use_llm())
        self.llm_switch.clicked.connect(self._toggle_llm)
        llm_row.addWidget(self.llm_switch)

        # Instructions button
        self.instructions_button = QPushButton("Instructions")
        self.instructions_button.setObjectName("instructionsButton")
        self.instructions_button.setFixedHeight(28)
        self.instructions_button.clicked.connect(self._open_instructions_dialog)
        llm_row.addWidget(self.instructions_button)
        controls_layout.addWidget(self.llm_section_frame)

        # 4. Language row
        self.lang_row_frame = QFrame()
        self.lang_row_frame.setObjectName("langRowFrame")
        self.lang_row_frame.setFixedHeight(28)
        lang_row = QHBoxLayout(self.lang_row_frame)
        lang_row.setContentsMargins(0, 0, 0, 0)
        lang_label = QLabel("Language")
        lang_row.addWidget(lang_label)
        lang_row.addStretch()

        self.language_combo = QComboBox()
        self.language_combo.setObjectName("languageCombo")
        self.language_combo.setFixedWidth(120)
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        current_lang = get_language()
        index = self.language_combo.findData(current_lang)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        self.language_combo.currentIndexChanged.connect(self._on_language_change)
        lang_row.addWidget(self.language_combo)
        controls_layout.addWidget(self.lang_row_frame)

        # 5. Autostart row
        self.autostart_row_frame = QFrame()
        self.autostart_row_frame.setObjectName("autostartRowFrame")
        self.autostart_row_frame.setFixedHeight(28)
        autostart_row = QHBoxLayout(self.autostart_row_frame)
        autostart_row.setContentsMargins(0, 0, 0, 0)
        autostart_label = QLabel("Start with computer")
        autostart_row.addWidget(autostart_label)
        autostart_row.addStretch()

        self.autostart_switch = ToggleSwitch()
        self.autostart_switch.setChecked(get_autostart())
        self.autostart_switch.clicked.connect(self._toggle_autostart)
        autostart_row.addWidget(self.autostart_switch)
        controls_layout.addWidget(self.autostart_row_frame)

        main_layout.addWidget(controls_frame)
        main_layout.addStretch()

        # --- API Keys Button ---
        self.api_keys_button = QPushButton("API Keys")
        self.api_keys_button.setObjectName("apiKeysButton")
        self.api_keys_button.setFixedHeight(32)
        self.api_keys_button.clicked.connect(self._open_api_keys_dialog)
        main_layout.addWidget(self.api_keys_button)

    def _apply_styles(self):
        """Apply dark mode stylesheet."""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS["bg_dark"]};
            }}
            QFrame#statusFrame, QFrame#controlsFrame {{
                background-color: {COLORS["bg_secondary"]};
                border-radius: 12px;
            }}
            QLabel {{
                color: {COLORS["text_primary"]};
                font-size: 14px;
            }}
            QLabel#statusText {{
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_secondary"]};
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-family: monospace;
            }}
            QPushButton:hover {{
                background-color: {COLORS["border"]};
            }}
            QPushButton:checked {{
                background-color: {COLORS["accent"]};
                color: {COLORS["text_primary"]};
            }}
            QPushButton#autoEnterButton {{
                background-color: {COLORS["accent"]};
                color: {COLORS["text_primary"]};
            }}
            QPushButton#autoEnterButtonOff {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_secondary"]};
            }}
            QPushButton#hotkeyButton:disabled {{
                background-color: {COLORS["accent"]};
                color: {COLORS["text_primary"]};
            }}
            QCheckBox {{
                color: {COLORS["text_secondary"]};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                background-color: {COLORS["bg_tertiary"]};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLORS["accent"]};
            }}
            QComboBox {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_primary"]};
                border: none;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLORS["bg_secondary"]};
                color: {COLORS["text_primary"]};
                selection-background-color: {COLORS["bg_tertiary"]};
            }}
            QPushButton#helpButton {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_secondary"]};
                border-radius: 14px;
                font-weight: bold;
            }}
            QPushButton#helpButton:checked {{
                background-color: {COLORS["accent"]};
                color: {COLORS["text_primary"]};
            }}
            QPushButton#sendModeButton {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_primary"]};
                font-size: 14px;
            }}
            QPushButton#instructionsButton {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_secondary"]};
                font-size: 11px;
                padding: 4px 10px;
            }}
            QPushButton#instructionsButton:hover {{
                background-color: {COLORS["border"]};
                color: {COLORS["text_primary"]};
            }}
            QPushButton#apiKeysButton {{
                background-color: {COLORS["bg_secondary"]};
                color: {COLORS["text_secondary"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 8px;
                font-size: 12px;
            }}
            QPushButton#apiKeysButton:hover {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_primary"]};
            }}
            QToolTip {{
                background-color: {COLORS["bg_tertiary"]};
                color: {COLORS["text_primary"]};
                border: 1px solid {COLORS["border"]};
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
            }}
        """)

    def _format_hotkey(self, label: str) -> str:
        """Format a key label for display."""
        if not label:
            return "Off"
        key_symbols = {
            'ctrl_l': '\u2303L', 'ctrl_r': '\u2303R', 'ctrl': '\u2303',
            'shift_l': '\u21e7L', 'shift_r': '\u21e7R', 'shift': '\u21e7',
            'alt_l': '\u2325L', 'alt_r': '\u2325R', 'alt': '\u2325',
            'cmd_l': '\u2318L', 'cmd_r': '\u2318R', 'cmd': '\u2318',
        }
        return key_symbols.get(label, label.upper())

    def _set_status(self, status: str):
        """Update status (thread-safe)."""
        self._status = status
        self._signals.status_changed.emit(status)

    def _update_status_display(self, status: str):
        """Update the status display (main thread)."""
        config = STATUS_CONFIG[status]
        self.status_indicator.setText(config["symbol"])
        self.status_indicator.setStyleSheet(f"color: {config['color']}; font-size: 24px;")
        self.status_text.setText(config["text"])

    def _update_hotkey_display(self):
        """Update hotkey button display."""
        label = get_hotkey_label()
        self.hotkey_button.setText(self._format_hotkey(label))
        self.hotkey_button.setEnabled(True)
        self.hotkey_button.setStyleSheet("")

    def _update_auto_enter_key_display(self):
        """Update auto-enter key button display."""
        label = get_auto_enter_key_label()
        display = self._format_hotkey(label) if label else "Off"
        self.auto_enter_button.setText(display)
        self.auto_enter_button.setEnabled(True)
        if label:
            self.auto_enter_button.setObjectName("autoEnterButton")
        else:
            self.auto_enter_button.setObjectName("autoEnterButtonOff")
        # Force style refresh
        self.auto_enter_button.style().unpolish(self.auto_enter_button)
        self.auto_enter_button.style().polish(self.auto_enter_button)

    # --- Event Handlers ---

    def _toggle_help_mode(self):
        """Toggle help mode - show/hide tooltips on sections."""
        help_enabled = self.help_button.isChecked()

        # Define tooltips for each section
        section_tooltips = {
            self.status_frame: "Shows current app status: Ready, Recording, or Processing",
            self.trans_row_frame: "Hold the hotkey to record voice, release to transcribe and type text",
            self.auto_row_frame: "Like transcription, but automatically sends the text with Enter or Cmd+Enter after typing",
            self.llm_section_frame: "Enable AI text correction. Write instructions in the prompt box below",
            self.lang_row_frame: "Select the language for Whisper transcription",
            self.autostart_row_frame: "Automatically start the app when your computer starts",
        }

        if help_enabled:
            # Create tooltip filter if not exists
            if not hasattr(self, '_tooltip_filter'):
                self._tooltip_filter = InstantTooltipFilter(self)
            # Set tooltips and install event filter on sections
            for widget, tooltip in section_tooltips.items():
                widget.setToolTip(tooltip)
                widget.installEventFilter(self._tooltip_filter)
        else:
            # Clear all tooltips and remove event filters
            for widget in section_tooltips.keys():
                widget.setToolTip("")
                if hasattr(self, '_tooltip_filter'):
                    widget.removeEventFilter(self._tooltip_filter)
            QToolTip.hideText()

    def _toggle_send_mode(self):
        """Toggle between Enter and Cmd+Enter."""
        current = get_send_mode()
        if current == "cmd+enter":
            set_send_mode("enter")
            self.send_mode_button.setText("\u23ce")
        else:
            set_send_mode("cmd+enter")
            self.send_mode_button.setText("\u2318\u23ce")

    def _enter_gui_hotkey_change_mode(self):
        """Enter hotkey change mode."""
        if self._gui_hotkey_change_mode:
            self._exit_gui_hotkey_change_mode(cancelled=True)
            return

        self._gui_hotkey_change_mode = True
        self.hotkey_button.setText("...")
        self.hotkey_button.setEnabled(False)
        self._key_config._enter_change_mode()

    def _exit_gui_hotkey_change_mode(self, cancelled=False):
        """Exit hotkey change mode."""
        self._gui_hotkey_change_mode = False
        self._signals.hotkey_changed.emit()
        if cancelled:
            self._key_config._exit_change_mode(cancelled=True)

    def _enter_gui_auto_enter_key_change_mode(self):
        """Enter auto-enter key change mode."""
        if self._gui_auto_enter_key_change_mode:
            self._exit_gui_auto_enter_key_change_mode(cancelled=True)
            return

        self._gui_auto_enter_key_change_mode = True
        self.auto_enter_button.setText("...")
        self.auto_enter_button.setEnabled(False)
        self._key_config._enter_auto_enter_key_change_mode()

    def _exit_gui_auto_enter_key_change_mode(self, cancelled=False):
        """Exit auto-enter key change mode."""
        self._gui_auto_enter_key_change_mode = False
        self._signals.auto_enter_key_changed.emit()
        if cancelled:
            self._key_config._exit_auto_enter_key_change_mode(cancelled=True)

    def _on_hotkey_change(self, old_key, new_key):
        """Callback when hotkey is changed."""
        if self._gui_hotkey_change_mode:
            self._gui_hotkey_change_mode = False
        self._signals.hotkey_changed.emit()

    def _on_auto_enter_change(self, new_state: bool):
        """Callback when auto-enter is toggled."""
        self._signals.auto_enter_key_changed.emit()

    def _on_auto_enter_key_change(self, old_key, new_key):
        """Callback when auto-enter key is changed."""
        if self._gui_auto_enter_key_change_mode:
            self._gui_auto_enter_key_change_mode = False
        self._signals.auto_enter_key_changed.emit()

    def _toggle_llm(self):
        """Handle LLM toggle."""
        set_use_llm(self.llm_switch.isChecked())

    def _open_instructions_dialog(self):
        """Open the instructions dialog for LLM prompt."""
        dialog = InstructionsDialog(self._current_prompt or "", self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            prompt = dialog.get_prompt()
            if prompt:
                self._current_prompt = prompt
                self._save_prompt(prompt)
            else:
                self._current_prompt = None
                self._delete_prompt_file()

    def _on_language_change(self, index):
        """Handle language change."""
        code = self.language_combo.itemData(index)
        if code:
            set_language(code)

    def _toggle_autostart(self):
        """Handle autostart toggle."""
        success = set_autostart(self.autostart_switch.isChecked())
        if not success:
            # Revert on failure
            self.autostart_switch.setChecked(get_autostart())
            self.autostart_switch._update_style()

    def _open_api_keys_dialog(self):
        """Open the API Keys configuration dialog."""
        dialog = APIKeysDialog(self)
        dialog.exec()

    # --- Prompt File Management ---

    def _get_prompt_file_path(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_prompt")

    def _save_prompt(self, prompt: str):
        try:
            with open(self._get_prompt_file_path(), "w") as f:
                f.write(prompt)
        except Exception:
            pass

    def _load_prompt(self) -> Optional[str]:
        try:
            path = self._get_prompt_file_path()
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read().strip()
        except Exception:
            pass
        return None

    def _delete_prompt_file(self):
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
        """Audio stream callback."""
        if self._recording:
            self._audio_data.append(indata.copy())

    # --- Keyboard Listener ---

    def _start_keyboard_listener(self):
        """Start the keyboard listener."""
        self._listener = Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self._listener.start()

    def _on_key_press(self, key):
        """Handle key press events."""
        try:
            if self._gui_hotkey_change_mode:
                try:
                    if self._key_config._capture_new_hotkey(key):
                        return
                except Exception as e:
                    print(f"Warning: Error in hotkey capture: {e}")
                    self._exit_gui_hotkey_change_mode(cancelled=True)
                    return

            if self._gui_auto_enter_key_change_mode:
                try:
                    if self._key_config._capture_new_auto_enter_key(key):
                        return
                except Exception as e:
                    print(f"Warning: Error in auto-enter key capture: {e}")
                    self._exit_gui_auto_enter_key_change_mode(cancelled=True)
                    return

            try:
                if self._key_config.handle_key_press(key):
                    return
            except Exception as e:
                print(f"Warning: Error handling key press in config: {e}")

            if self._key_config.is_in_change_mode():
                return

            try:
                if key == get_hotkey():
                    self._recording = True
                    self._recording_with_auto_enter = False
                    self._audio_data = []
                    self._set_status(STATUS_RECORDING)
                elif key == get_auto_enter_key():
                    self._recording = True
                    self._recording_with_auto_enter = True
                    self._audio_data = []
                    self._set_status(STATUS_RECORDING)
            except Exception:
                pass
        except Exception as e:
            print(f"Warning: Unexpected error in _on_key_press: {e}")

    def _on_key_release(self, key):
        """Handle key release events."""
        try:
            try:
                self._key_config.handle_key_release(key)
            except Exception as e:
                print(f"Warning: Error handling key release in config: {e}")

            if self._key_config.is_in_change_mode() or self._gui_hotkey_change_mode or self._gui_auto_enter_key_change_mode:
                return

            try:
                is_hotkey = key == get_hotkey()
                is_auto_enter_key = key == get_auto_enter_key()

                if (is_hotkey or is_auto_enter_key) and self._recording:
                    self._recording = False
                    self._set_status(STATUS_PROCESSING)

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
            print(f"Warning: Unexpected error in _on_key_release: {e}")

    def _process_audio(self, audio_data: list, use_auto_enter: bool = False):
        """Process recorded audio and transcribe."""
        MIN_AUDIO_DURATION_SECONDS = 0.5
        MIN_RMS_THRESHOLD = 0.005
        MIN_TRANSCRIPT_LENGTH = 2

        HALLUCINATION_PHRASES = [
            "tack alla som tittat", "thanks for watching", "thank you for watching",
            "subscribe", "like and subscribe", "see you next time", "bye bye",
            "goodbye", "music", "applause", "[music]", "[applause]", "you",
            "...", "the end", "subtitles by", "captions by",
        ]

        try:
            if not audio_data:
                self._set_status(STATUS_READY)
                return

            audio_data_np = np.concatenate(audio_data, axis=0)

            audio_duration = len(audio_data_np) / self._sample_rate
            if audio_duration < MIN_AUDIO_DURATION_SECONDS:
                self._set_status(STATUS_READY)
                return

            rms = np.sqrt(np.mean(audio_data_np ** 2))
            if rms < MIN_RMS_THRESHOLD:
                self._set_status(STATUS_READY)
                return

            audio_data_int16 = (audio_data_np * np.iinfo(np.int16).max).astype(np.int16)

            # Use absolute paths in /tmp for bundled app compatibility
            import tempfile
            temp_dir = tempfile.gettempdir()
            wav_path = os.path.join(temp_dir, 'viska_recording.wav')
            m4a_path = os.path.join(temp_dir, 'viska_recording.m4a')

            wavfile.write(wav_path, self._sample_rate, audio_data_int16)

            file_to_transcribe = wav_path
            try:
                subprocess.run(
                    ['ffmpeg', '-i', wav_path, '-c:a', 'aac', '-b:a', '32k', m4a_path, '-y'],
                    check=True, capture_output=True
                )
                file_to_transcribe = m4a_path
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass

            transcript = None
            try:
                language = get_language()
                transcript = apply_whisper(file_to_transcribe, 'transcribe', language=language)
            except Exception as e:
                # Handle API errors (e.g., invalid request, audio too short)
                if "Invalid" in str(e) or "audio" in str(e).lower():
                    self._set_status(STATUS_READY)
                    return
                raise

            if not transcript or len(transcript.strip()) < MIN_TRANSCRIPT_LENGTH:
                print("Transcript too short, skipping")
                self._set_status(STATUS_READY)
                return

            transcript_lower = transcript.strip().lower()
            for phrase in HALLUCINATION_PHRASES:
                if transcript_lower == phrase or transcript_lower.startswith(phrase):
                    print(f"Detected hallucination: '{transcript}', skipping")
                    self._set_status(STATUS_READY)
                    return

            if transcript:
                if get_use_llm() and self._current_prompt:
                    transcript = apply_gpt_correction(transcript, self._current_prompt)

                processed_transcript = process_transcript(transcript)
                self._keyboard_controller.type(processed_transcript)

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
                        print(f"Auto-enter: sending {send_mode}")
                        if send_mode == "cmd+enter":
                            self._keyboard_controller.press(Key.cmd)
                            self._keyboard_controller.press(Key.enter)
                            self._keyboard_controller.release(Key.enter)
                            self._keyboard_controller.release(Key.cmd)
                        else:
                            self._keyboard_controller.press(Key.enter)
                            self._keyboard_controller.release(Key.enter)
                        print("Auto-enter: key sent successfully")
                    except Exception as e:
                        print(f"Warning: Could not press send key: {e}")

        except ValueError:
            pass
        except Exception as e:
            print(f"Error processing audio: {str(e)}")
        finally:
            self._set_status(STATUS_READY)

    def closeEvent(self, event):
        """Handle window close."""
        try:
            if hasattr(self, '_stream'):
                self._stream.stop()
                self._stream.close()
            if hasattr(self, '_listener'):
                self._listener.stop()
        except Exception:
            pass
        event.accept()


def main():
    """Main entry point."""
    try:
        # Load environment variables from .env file
        # (whisper.py and utils.py will pick these up when creating their clients)
        env_path = _get_env_file_path()
        if os.path.exists(env_path):
            env_values = _load_env_values()
            for key, value in env_values.items():
                if value:
                    os.environ[key] = value

        app = QApplication(sys.argv)
        app.setApplicationName("Viska")
        window = WKeyGUI()
        window.show()
        window.raise_()
        window.activateWindow()
        sys.exit(app.exec())
    except Exception as e:
        import traceback
        # Write error to log file in home directory
        log_path = os.path.expanduser("~/whisper-speak-error.log")
        with open(log_path, "w") as f:
            f.write(f"Error: {e}\n\n")
            f.write(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
