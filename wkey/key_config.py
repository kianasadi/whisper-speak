"""
Dynamic hotkey configuration module for whisper-keyboard.

This module provides functionality to:
- Store and retrieve the current voice input hotkey
- Allow runtime hotkey changes via Ctrl+Shift+K
- Persist hotkey configuration to a file

Usage:
    from wkey.key_config import KeyConfig

    config = KeyConfig()
    current_key = config.get_hotkey()  # Returns pynput Key object
    key_label = config.get_hotkey_label()  # Returns string like "ctrl_l"
"""

import os
import sys
import json
import threading
import plistlib
from pynput.keyboard import Key, Listener, KeyCode


# Configuration file path (in user's home directory)
CONFIG_FILE = os.path.expanduser("~/.wkey_config")

# LaunchAgent plist path for autostart (macOS)
LAUNCH_AGENT_DIR = os.path.expanduser("~/Library/LaunchAgents")
LAUNCH_AGENT_PLIST = os.path.join(LAUNCH_AGENT_DIR, "com.wkey.autostart.plist")
LAUNCH_AGENT_LABEL = "com.wkey.autostart"

# Key combination to enter key change mode: Ctrl+Shift+K
CHANGE_MODE_MODIFIERS = {Key.ctrl, Key.ctrl_l, Key.ctrl_r}
CHANGE_MODE_SHIFT = {Key.shift, Key.shift_l, Key.shift_r}
CHANGE_MODE_TRIGGER = KeyCode.from_char('k')

# Key combination to toggle auto-enter: Ctrl+Shift+E
AUTO_ENTER_TOGGLE_TRIGGER = KeyCode.from_char('e')


class KeyConfig:
    """
    Manages the voice input hotkey configuration.

    Provides methods to get/set the hotkey and handles persistence
    to a configuration file.
    """

    def __init__(self):
        self._hotkey_label = None
        self._hotkey = None
        self._auto_enter = False
        self._auto_enter_key_label = None  # Separate key for auto-enter trigger
        self._auto_enter_key = None
        self._language = "sv"  # Default to Swedish
        self._use_llm = False  # LLM prompt disabled by default for speed
        self._autostart = False  # Autostart on login disabled by default
        self._send_mode = "cmd+enter"  # "enter" or "cmd+enter"
        self._in_change_mode = False
        self._in_auto_enter_key_change_mode = False  # Track auto-enter key change mode
        self._pressed_modifiers = set()
        self._change_callback = None
        self._auto_enter_callback = None
        self._auto_enter_key_callback = None  # Callback for auto-enter key changes
        self._load_config()

    def _load_config(self):
        """Load hotkey configuration from file or environment."""
        # First try to load from config file
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    self._hotkey_label = config.get('hotkey', None)
                    self._auto_enter = config.get('auto_enter', False)
                    self._auto_enter_key_label = config.get('auto_enter_key', None)
                    self._language = config.get('language', 'sv')
                    self._use_llm = config.get('use_llm', False)
                    self._autostart = config.get('autostart', False)
                    self._send_mode = config.get('send_mode', 'cmd+enter')
            except (json.JSONDecodeError, IOError):
                pass  # Silent failure, will use defaults

        # Sync autostart state with actual plist file existence
        self._autostart = os.path.exists(LAUNCH_AGENT_PLIST)

        # Fall back to environment variable if no config file
        if self._hotkey_label is None:
            self._hotkey_label = os.environ.get("WKEY", "ctrl_l")

        # Convert label to Key object
        self._hotkey = self._label_to_key(self._hotkey_label)

        # Convert auto-enter key label to Key object (if set)
        if self._auto_enter_key_label:
            self._auto_enter_key = self._label_to_key(self._auto_enter_key_label)

    def _save_config(self):
        """Save current hotkey configuration to file."""
        try:
            config = {
                'hotkey': self._hotkey_label,
                'auto_enter': self._auto_enter,
                'auto_enter_key': self._auto_enter_key_label,
                'language': self._language,
                'use_llm': self._use_llm,
                'autostart': self._autostart,
                'send_mode': self._send_mode
            }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)
            return True
        except IOError:
            return False

    def _label_to_key(self, label):
        """Convert a string label to a pynput Key object."""
        # Try to get as a special key first
        key = getattr(Key, label, None)
        if key is not None:
            return key

        # If it's a single character, create a KeyCode
        if len(label) == 1:
            return KeyCode.from_char(label)

        # Try to interpret as a virtual key code (for special cases)
        if label.startswith('vk_'):
            try:
                vk = int(label[3:])
                return KeyCode.from_vk(vk)
            except ValueError:
                pass

        # Default fallback
        return Key.ctrl_l

    def _key_to_label(self, key):
        """Convert a pynput Key object to a string label."""
        # Check if it's a special Key
        if isinstance(key, Key):
            return key.name

        # It's a KeyCode
        if isinstance(key, KeyCode):
            if key.char is not None:
                return key.char
            elif key.vk is not None:
                return f"vk_{key.vk}"

        return str(key)

    def get_hotkey(self):
        """Get the current hotkey as a pynput Key/KeyCode object."""
        return self._hotkey

    def get_hotkey_label(self):
        """Get the current hotkey as a string label."""
        return self._hotkey_label

    def set_hotkey(self, key):
        """
        Set a new hotkey.

        Args:
            key: Either a pynput Key/KeyCode object or a string label

        Returns:
            bool: True if successful, False otherwise
        """
        if isinstance(key, str):
            self._hotkey_label = key
            self._hotkey = self._label_to_key(key)
        else:
            self._hotkey_label = self._key_to_label(key)
            self._hotkey = key

        return self._save_config()

    def get_auto_enter(self):
        """Get the current auto-enter setting."""
        return self._auto_enter

    def set_auto_enter(self, enabled):
        """
        Set the auto-enter setting.

        Args:
            enabled: Boolean indicating whether auto-enter should be enabled

        Returns:
            bool: True if successful, False otherwise
        """
        self._auto_enter = bool(enabled)
        return self._save_config()

    def toggle_auto_enter(self):
        """
        Toggle the auto-enter setting.

        Returns:
            bool: The new auto-enter state
        """
        self._auto_enter = not self._auto_enter
        self._save_config()
        return self._auto_enter

    def get_auto_enter_key(self):
        """Get the auto-enter trigger key as a pynput Key/KeyCode object."""
        return self._auto_enter_key

    def get_auto_enter_key_label(self):
        """Get the auto-enter trigger key as a string label."""
        return self._auto_enter_key_label

    def set_auto_enter_key(self, key):
        """
        Set a new auto-enter trigger key.

        Args:
            key: Either a pynput Key/KeyCode object or a string label

        Returns:
            bool: True if successful, False otherwise
        """
        old_key = self._auto_enter_key
        if isinstance(key, str):
            self._auto_enter_key_label = key
            self._auto_enter_key = self._label_to_key(key)
        else:
            self._auto_enter_key_label = self._key_to_label(key)
            self._auto_enter_key = key

        # Also enable auto-enter when a key is set
        self._auto_enter = True

        success = self._save_config()

        # Call the change callback if set
        if success and self._auto_enter_key_callback:
            self._auto_enter_key_callback(old_key, self._auto_enter_key)

        return success

    def clear_auto_enter_key(self):
        """
        Clear the auto-enter trigger key (disable auto-enter).

        Returns:
            bool: True if successful, False otherwise
        """
        old_key = self._auto_enter_key
        self._auto_enter_key_label = None
        self._auto_enter_key = None
        self._auto_enter = False
        success = self._save_config()

        if success and self._auto_enter_key_callback:
            self._auto_enter_key_callback(old_key, None)

        return success

    def set_auto_enter_key_callback(self, callback):
        """
        Set a callback function to be called when the auto-enter key changes.

        Args:
            callback: Function that takes (old_key, new_key) as arguments
        """
        self._auto_enter_key_callback = callback

    def is_in_auto_enter_key_change_mode(self):
        """Check if currently in auto-enter key change mode."""
        return self._in_auto_enter_key_change_mode

    def _enter_auto_enter_key_change_mode(self):
        """Enter auto-enter key change mode."""
        self._in_auto_enter_key_change_mode = True
        print("○ Press new auto-enter key (Enter/Tab/Space/letter) - esc to cancel, backspace to disable")

    def _exit_auto_enter_key_change_mode(self, cancelled=False):
        """Exit auto-enter key change mode."""
        self._in_auto_enter_key_change_mode = False
        self._pressed_modifiers.clear()
        if cancelled:
            print("○ Cancelled")

    def _keys_are_equal(self, key1, key2):
        """
        Compare two keys for equality, handling both Key and KeyCode types.

        Args:
            key1: First key to compare
            key2: Second key to compare

        Returns:
            bool: True if keys are equal, False otherwise
        """
        if key1 is None or key2 is None:
            return False

        # Direct equality check
        if key1 == key2:
            return True

        # Compare by label for consistent comparison across different key representations
        label1 = self._key_to_label(key1)
        label2 = self._key_to_label(key2)
        return label1 == label2

    def _capture_new_auto_enter_key(self, key):
        """
        Capture a key to set as the new auto-enter key.
        Allows ALL keys including modifiers.

        Args:
            key: The key that was pressed

        Returns:
            bool: True (always consumes the key in change mode)
        """
        try:
            # Escape cancels
            if key == Key.esc:
                self._exit_auto_enter_key_change_mode(cancelled=True)
                return True

            # Backspace clears/disables auto-enter
            if key == Key.backspace:
                self.clear_auto_enter_key()
                self._exit_auto_enter_key_change_mode()
                print("Auto-enter disabled")
                return True

            # Check if this key is already used as the transcription hotkey
            if self._keys_are_equal(key, self._hotkey):
                print(f"Key already used as transcription hotkey - choose a different key")
                self._exit_auto_enter_key_change_mode(cancelled=True)
                return True

            # Set the new auto-enter key (allow ANY key including modifiers)
            if self.set_auto_enter_key(key):
                print(f"Auto-enter key set to: {self._auto_enter_key_label}")

            self._exit_auto_enter_key_change_mode()
            return True
        except Exception as e:
            # Never crash on key capture - just cancel and log
            print(f"Warning: Error capturing auto-enter key: {e}")
            self._exit_auto_enter_key_change_mode(cancelled=True)
            return True

    def get_language(self):
        """Get the current language setting (ISO-639-1 code)."""
        return self._language

    def set_language(self, language):
        """
        Set the language for transcription.

        Args:
            language: ISO-639-1 language code (e.g., 'sv', 'en', 'de')

        Returns:
            bool: True if successful, False otherwise
        """
        self._language = language
        return self._save_config()

    def get_use_llm(self):
        """Get whether LLM processing is enabled."""
        return self._use_llm

    def set_use_llm(self, enabled):
        """
        Enable or disable LLM processing.

        Args:
            enabled: Boolean indicating whether to use LLM processing

        Returns:
            bool: True if successful, False otherwise
        """
        self._use_llm = bool(enabled)
        return self._save_config()

    def get_send_mode(self):
        """Get the send mode ('enter' or 'cmd+enter')."""
        return self._send_mode

    def set_send_mode(self, mode):
        """
        Set the send mode for auto-enter.

        Args:
            mode: 'enter' or 'cmd+enter'

        Returns:
            bool: True if successful, False otherwise
        """
        if mode in ('enter', 'cmd+enter'):
            self._send_mode = mode
            return self._save_config()
        return False

    def get_autostart(self):
        """Get whether autostart on login is enabled."""
        # Always check actual plist file to ensure sync
        return os.path.exists(LAUNCH_AGENT_PLIST)

    def set_autostart(self, enabled):
        """
        Enable or disable autostart on login (macOS only).

        Creates or removes a LaunchAgent plist file to control
        whether wkey starts automatically at login.

        Args:
            enabled: Boolean indicating whether to autostart

        Returns:
            bool: True if successful, False otherwise
        """
        self._autostart = bool(enabled)

        if enabled:
            success = self._create_launch_agent()
        else:
            success = self._remove_launch_agent()

        if success:
            self._save_config()
        return success

    def _get_wkey_command(self):
        """Get the command to run wkey, finding the correct Python/wkey path."""
        # Try to find the wkey executable
        import shutil

        # First, try to find wkey in PATH
        wkey_path = shutil.which('wkey')
        if wkey_path:
            return [wkey_path]

        # Otherwise, use the Python interpreter with -m wkey.gui_pyqt
        python_path = sys.executable
        return [python_path, '-m', 'wkey.gui_pyqt']

    def _create_launch_agent(self):
        """Create the LaunchAgent plist file for autostart."""
        try:
            # Ensure LaunchAgents directory exists
            os.makedirs(LAUNCH_AGENT_DIR, exist_ok=True)

            # Get the command to run
            program_args = self._get_wkey_command()

            # Create plist content
            plist_content = {
                'Label': LAUNCH_AGENT_LABEL,
                'ProgramArguments': program_args,
                'RunAtLoad': True,
                'KeepAlive': {
                    'SuccessfulExit': False  # Restart if crashes, not if exits normally
                },
                'StandardErrorPath': os.path.expanduser('~/Library/Logs/wkey.err.log'),
                'StandardOutPath': os.path.expanduser('~/Library/Logs/wkey.out.log'),
                'EnvironmentVariables': {
                    'PATH': '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                    'HOME': os.path.expanduser('~')
                }
            }

            # Write the plist file
            with open(LAUNCH_AGENT_PLIST, 'wb') as f:
                plistlib.dump(plist_content, f)

            print(f"Autostart enabled: {LAUNCH_AGENT_PLIST}")
            return True
        except Exception as e:
            print(f"Failed to create LaunchAgent: {e}")
            return False

    def _remove_launch_agent(self):
        """Remove the LaunchAgent plist file to disable autostart."""
        try:
            if os.path.exists(LAUNCH_AGENT_PLIST):
                os.remove(LAUNCH_AGENT_PLIST)
                print(f"Autostart disabled: removed {LAUNCH_AGENT_PLIST}")
            return True
        except Exception as e:
            print(f"Failed to remove LaunchAgent: {e}")
            return False

    def set_change_callback(self, callback):
        """
        Set a callback function to be called when the hotkey changes.

        Args:
            callback: Function that takes (old_key, new_key) as arguments
        """
        self._change_callback = callback

    def set_auto_enter_callback(self, callback):
        """
        Set a callback function to be called when auto-enter is toggled.

        Args:
            callback: Function that takes (new_state) as argument
        """
        self._auto_enter_callback = callback

    def is_in_change_mode(self):
        """Check if currently in any key change mode."""
        return self._in_change_mode or self._in_auto_enter_key_change_mode

    def handle_key_press(self, key):
        """
        Handle a key press event for hotkey configuration.

        This method should be called from the main keyboard listener.
        Returns True if the key was consumed by the config handler.

        Args:
            key: The key that was pressed

        Returns:
            bool: True if the key was handled, False otherwise
        """
        # Track modifier keys
        if key in CHANGE_MODE_MODIFIERS or key in CHANGE_MODE_SHIFT:
            self._pressed_modifiers.add(key)

        # Check for change mode activation (Ctrl+Shift+K) or auto-enter toggle (Ctrl+Shift+E)
        if not self._in_change_mode:
            has_ctrl = any(k in self._pressed_modifiers for k in CHANGE_MODE_MODIFIERS)
            has_shift = any(k in self._pressed_modifiers for k in CHANGE_MODE_SHIFT)

            if has_ctrl and has_shift and key == CHANGE_MODE_TRIGGER:
                self._enter_change_mode()
                return True

            # Check for auto-enter toggle (Ctrl+Shift+E)
            if has_ctrl and has_shift and key == AUTO_ENTER_TOGGLE_TRIGGER:
                new_state = self.toggle_auto_enter()
                status = "on" if new_state else "off"
                print(f"✓ Auto-enter {status}")
                if self._auto_enter_callback:
                    self._auto_enter_callback(new_state)
                return True
        else:
            # In change mode - capture the next key
            return self._capture_new_hotkey(key)

        return False

    def handle_key_release(self, key):
        """
        Handle a key release event for hotkey configuration.

        Args:
            key: The key that was released
        """
        # Remove from tracked modifiers
        self._pressed_modifiers.discard(key)

    def _enter_change_mode(self):
        """Enter key change mode."""
        self._in_change_mode = True
        print("○ Press new hotkey (esc to cancel)")

    def _exit_change_mode(self, cancelled=False):
        """Exit key change mode."""
        self._in_change_mode = False
        self._pressed_modifiers.clear()
        if cancelled:
            print("○ Cancelled")

    def _capture_new_hotkey(self, key):
        """
        Capture a key to set as the new hotkey.
        Allows ALL keys except Escape (which cancels).

        Args:
            key: The key that was pressed

        Returns:
            bool: True (always consumes the key in change mode)
        """
        try:
            # Escape cancels
            if key == Key.esc:
                self._exit_change_mode(cancelled=True)
                return True

            # Check if this key is already used as the auto-enter key
            if self._keys_are_equal(key, self._auto_enter_key):
                print(f"Key already used as auto-enter hotkey - choose a different key")
                self._exit_change_mode(cancelled=True)
                return True

            # Set the new hotkey (allow ANY key including modifiers)
            old_key = self._hotkey

            if self.set_hotkey(key):
                # Call the change callback if set
                if self._change_callback:
                    self._change_callback(old_key, self._hotkey)

            self._exit_change_mode()
            return True
        except Exception as e:
            # Never crash on key capture - just cancel and log
            print(f"Warning: Error capturing hotkey: {e}")
            self._exit_change_mode(cancelled=True)
            return True


# Global singleton instance
_config_instance = None


def get_config():
    """Get the global KeyConfig singleton instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = KeyConfig()
    return _config_instance


def get_hotkey():
    """Convenience function to get the current hotkey."""
    return get_config().get_hotkey()


def get_hotkey_label():
    """Convenience function to get the current hotkey label."""
    return get_config().get_hotkey_label()


def set_hotkey(key):
    """Convenience function to set a new hotkey."""
    return get_config().set_hotkey(key)


def get_auto_enter():
    """Convenience function to get the current auto-enter setting."""
    return get_config().get_auto_enter()


def set_auto_enter(enabled):
    """Convenience function to set the auto-enter setting."""
    return get_config().set_auto_enter(enabled)


def toggle_auto_enter():
    """Convenience function to toggle the auto-enter setting."""
    return get_config().toggle_auto_enter()


def get_auto_enter_key():
    """Convenience function to get the auto-enter key."""
    return get_config().get_auto_enter_key()


def get_auto_enter_key_label():
    """Convenience function to get the auto-enter key label."""
    return get_config().get_auto_enter_key_label()


def set_auto_enter_key(key):
    """Convenience function to set the auto-enter key."""
    return get_config().set_auto_enter_key(key)


def clear_auto_enter_key():
    """Convenience function to clear/disable the auto-enter key."""
    return get_config().clear_auto_enter_key()


def get_language():
    """Convenience function to get the current language setting."""
    return get_config().get_language()


def set_language(language):
    """Convenience function to set the language setting."""
    return get_config().set_language(language)


def get_use_llm():
    """Convenience function to get whether LLM processing is enabled."""
    return get_config().get_use_llm()


def set_use_llm(enabled):
    """Convenience function to enable/disable LLM processing."""
    return get_config().set_use_llm(enabled)


def get_autostart():
    """Convenience function to get whether autostart is enabled."""
    return get_config().get_autostart()


def set_autostart(enabled):
    """Convenience function to enable/disable autostart."""
    return get_config().set_autostart(enabled)


def get_send_mode():
    """Convenience function to get the send mode."""
    return get_config().get_send_mode()


def set_send_mode(mode):
    """Convenience function to set the send mode."""
    return get_config().set_send_mode(mode)


# Standalone test/demo mode
if __name__ == "__main__":
    print(f"● Key config test — hotkey: {get_hotkey_label()} | ⌃⇧K change")

    config = get_config()

    def on_press(key):
        if config.handle_key_press(key):
            return
        if not config.is_in_change_mode():
            label = config._key_to_label(key)
            marker = " *" if key == config.get_hotkey() else ""
            print(f"  {label}{marker}")

    def on_release(key):
        config.handle_key_release(key)

    try:
        with Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
    except KeyboardInterrupt:
        print("\n○ Stopped")
