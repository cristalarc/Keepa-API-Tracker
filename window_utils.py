"""
Window utility functions for consistent window sizing and positioning.

Goals:
- Child windows always open on the same physical monitor as their parent.
- Window sizes always fit within that monitor.
- Fonts and pixel values scale with DPI *and* screen size, in both directions
  (1366x768 laptop should shrink, 4K should grow). Honors KEEPA_UI_SCALE
  env var as a hard override.
"""

import os
import tkinter.font as tkfont


_scale_factor = 1.0
_MIN_SCALE = 0.85
_MAX_SCALE = 2.5
# Floor for the auto-detected screen-size factor. Keeps small laptops
# (1366x768) at a readable scale instead of shrinking to ~0.78.
_AUTO_MIN_SIZE_FACTOR = 0.95
_AUTO_MAX_SIZE_FACTOR = 2.0


def _safe_get_monitors():
    """Return list of screeninfo.Monitor or [] if screeninfo is unavailable."""
    try:
        from screeninfo import get_monitors
        return list(get_monitors())
    except Exception:
        return []


def _monitor_containing(x, y, monitors):
    """Pick the monitor whose rect contains (x, y); fall back to first/None."""
    for m in monitors:
        if m.x <= x < m.x + m.width and m.y <= y < m.y + m.height:
            return m
    return monitors[0] if monitors else None


def init_dpi_scaling(root):
    """
    Detect DPI + screen size and apply a unified scale factor to Tk.
    Call once after creating the Tk root window.
    """
    global _scale_factor

    # Best-effort DPI awareness on Windows
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    root.update_idletasks()

    override = os.environ.get("KEEPA_UI_SCALE")
    saved_override = None
    if not override:
        try:
            from settings import get_ui_scale_override
            saved_override = get_ui_scale_override()
        except Exception:
            saved_override = None

    if override:
        try:
            _scale_factor = max(_MIN_SCALE, min(_MAX_SCALE, float(override)))
        except ValueError:
            _scale_factor = 1.0
    elif saved_override is not None:
        _scale_factor = max(_MIN_SCALE, min(_MAX_SCALE, float(saved_override)))
    else:
        try:
            actual_dpi = root.winfo_fpixels('1i')
        except Exception:
            actual_dpi = 96.0
        dpi_factor = actual_dpi / 96.0

        monitors = _safe_get_monitors()
        if monitors:
            primary = next((m for m in monitors if getattr(m, 'is_primary', False)), monitors[0])
            screen_w, screen_h = primary.width, primary.height
        else:
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()

        size_factor = min(screen_w / 1920.0, screen_h / 1080.0)
        size_factor = max(_AUTO_MIN_SIZE_FACTOR, min(_AUTO_MAX_SIZE_FACTOR, size_factor))

        _scale_factor = max(_MIN_SCALE, min(_MAX_SCALE, dpi_factor * size_factor))

    try:
        root.tk.call('tk', 'scaling', _scale_factor * (96.0 / 72.0))
    except Exception:
        pass

    for font_name in ('TkDefaultFont', 'TkTextFont', 'TkFixedFont',
                       'TkMenuFont', 'TkHeadingFont', 'TkCaptionFont',
                       'TkSmallCaptionFont', 'TkIconFont', 'TkTooltipFont'):
        try:
            font = tkfont.nametofont(font_name)
            original_size = font.cget('size')
            if original_size < 0:
                font.configure(size=int(original_size * _scale_factor))
            else:
                font.configure(size=max(1, int(original_size * _scale_factor)))
        except Exception:
            pass


def get_scale_factor():
    """Return the current UI scale factor."""
    return _scale_factor


def scaled(pixel_value):
    """Scale a pixel value by the current UI factor."""
    return max(1, int(pixel_value * _scale_factor))


def scaled_font(family, size, weight=""):
    """Return a font tuple with the size scaled for the current UI factor."""
    scaled_size = max(1, int(size * _scale_factor))
    if weight:
        return (family, scaled_size, weight)
    return (family, scaled_size)


def get_parent_monitor_geometry(parent):
    """
    Return (x, y, width, height) of the monitor the parent window sits on.
    If parent is None, use the mouse position. Falls back to tkinter screen
    dimensions if screeninfo is unavailable.
    """
    monitors = _safe_get_monitors()

    cx = cy = None
    if parent is not None:
        try:
            parent.update_idletasks()
            cx = parent.winfo_rootx() + parent.winfo_width() // 2
            cy = parent.winfo_rooty() + parent.winfo_height() // 2
        except Exception:
            cx = cy = None

    if cx is None:
        try:
            import pyautogui
            cx, cy = pyautogui.position()
        except Exception:
            cx = cy = None

    if monitors and cx is not None and cy is not None:
        m = _monitor_containing(cx, cy, monitors)
        if m is not None:
            return (m.x, m.y, m.width, m.height)

    if monitors:
        primary = next((m for m in monitors if getattr(m, 'is_primary', False)), monitors[0])
        return (primary.x, primary.y, primary.width, primary.height)

    if parent is not None:
        try:
            return (0, 0, parent.winfo_screenwidth(), parent.winfo_screenheight())
        except Exception:
            pass
    return (0, 0, 1920, 1080)


def size_and_center_on_parent(window, parent, desired_w, desired_h, max_frac=0.95):
    """
    Size a window to fit the parent's monitor and center it over the parent.
    Returns the actual (width, height) used so callers can clamp minsize().
    """
    mon_x, mon_y, mon_w, mon_h = get_parent_monitor_geometry(parent)

    width = min(desired_w, int(mon_w * max_frac))
    height = min(desired_h, int(mon_h * max_frac))

    window.update_idletasks()

    if parent is not None:
        try:
            parent.update_idletasks()
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_w = parent.winfo_width()
            parent_h = parent.winfo_height()
            x = parent_x + (parent_w - width) // 2
            y = parent_y + (parent_h - height) // 2
        except Exception:
            x = mon_x + (mon_w - width) // 2
            y = mon_y + (mon_h - height) // 2
    else:
        try:
            import pyautogui
            mouse_x, mouse_y = pyautogui.position()
            x = mouse_x - width // 2
            y = mouse_y - height // 2
        except Exception:
            x = mon_x + (mon_w - width) // 2
            y = mon_y + (mon_h - height) // 2

    # Clamp inside monitor bounds so the title bar stays reachable
    x = max(mon_x, min(x, mon_x + mon_w - width))
    y = max(mon_y, min(y, mon_y + mon_h - height))

    window.geometry(f'{width}x{height}+{x}+{y}')
    return (width, height)


def center_window_on_parent(window, parent, width, height):
    """
    Backward-compatible alias. Position a window over its parent or over
    the mouse cursor if no parent is provided. Delegates to
    size_and_center_on_parent so the parent's actual monitor is respected.
    """
    size_and_center_on_parent(window, parent, width, height)


def clamp_minsize(window, width, height, cap_w=1280, cap_h=680):
    """
    Set minsize so the window can shrink to fit a 1366x768 laptop.
    Caps oversized requests; passes smaller requests through unchanged.
    """
    try:
        window.minsize(min(width, cap_w), min(height, cap_h))
    except Exception:
        pass
