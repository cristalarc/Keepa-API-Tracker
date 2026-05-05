"""
Persistent settings for the Keepa API Tracker.

Currently stores the user's UI scale override (None = auto-detect, else a float).
File lives next to the app at keepa_settings.json so packaging stays simple.
"""

import json
import os

_SETTINGS_FILENAME = "keepa_settings.json"
_DEFAULTS = {
    "ui_scale_override": None,  # None | float in [0.5, 3.0]
}


def _settings_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _SETTINGS_FILENAME)


def load_settings():
    """Return a dict merged with defaults. Never raises."""
    data = dict(_DEFAULTS)
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if k in _DEFAULTS})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return data


def save_settings(updates):
    """Merge updates into the stored settings. Returns True on success."""
    current = load_settings()
    current.update(updates)
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True
    except OSError:
        return False


def get_ui_scale_override():
    """Return the saved UI scale override (float) or None for auto."""
    val = load_settings().get("ui_scale_override")
    if val is None:
        return None
    try:
        f = float(val)
        if 0.5 <= f <= 3.0:
            return f
    except (TypeError, ValueError):
        pass
    return None


def set_ui_scale_override(value):
    """Persist a UI scale override. Pass None to clear (auto-detect)."""
    if value is None:
        return save_settings({"ui_scale_override": None})
    try:
        f = float(value)
    except (TypeError, ValueError):
        return False
    f = max(0.5, min(3.0, f))
    return save_settings({"ui_scale_override": f})
