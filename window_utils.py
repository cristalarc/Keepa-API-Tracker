"""
Window utility functions for consistent window sizing and positioning.
Ensures child windows open on the same screen/monitor as their parent window.
Provides DPI-aware scaling for fonts and pixel values on high-resolution displays.
"""

import tkinter.font as tkfont


_scale_factor = 1.0
_BASE_TK_SCALING = 96.0 / 72.0
_font_base_sizes = {}


def _get_monitor_metrics(window):
    """
    Return monitor metrics for the display containing the window center.
    Falls back to None values when monitor info is unavailable.
    """
    try:
        from screeninfo import get_monitors
    except Exception:
        return None, None, None

    try:
        monitors = get_monitors()
    except Exception:
        return None, None, None

    if not monitors:
        return None, None, None

    window.update_idletasks()
    center_x = window.winfo_rootx() + (window.winfo_width() // 2)
    center_y = window.winfo_rooty() + (window.winfo_height() // 2)

    selected = None
    for monitor in monitors:
        if (
            monitor.x <= center_x < (monitor.x + monitor.width)
            and monitor.y <= center_y < (monitor.y + monitor.height)
        ):
            selected = monitor
            break

    # If the center is outside known monitor rectangles, choose closest monitor.
    if selected is None:
        def distance_sq(monitor):
            mid_x = monitor.x + (monitor.width / 2)
            mid_y = monitor.y + (monitor.height / 2)
            return ((center_x - mid_x) ** 2) + ((center_y - mid_y) ** 2)

        selected = min(monitors, key=distance_sq)

    dpi = None
    try:
        if selected.width_mm and selected.height_mm:
            dpi_x = selected.width / (selected.width_mm / 25.4)
            dpi_y = selected.height / (selected.height_mm / 25.4)
            dpi = (dpi_x + dpi_y) / 2.0
    except Exception:
        dpi = None

    return dpi, int(selected.width), int(selected.height)


def _resolution_scale_for_monitor(width, height):
    """
    Return a practical UI scale multiplier based on monitor resolution.
    Uses conservative buckets to avoid oversized windows on smaller displays.
    """
    if not width or not height:
        return 1.0

    monitor_ratio = min(width / 1920.0, height / 1080.0)
    if monitor_ratio >= 1.9:
        return 1.5
    if monitor_ratio >= 1.6:
        return 1.35
    if monitor_ratio >= 1.3:
        return 1.2
    if monitor_ratio >= 1.1:
        return 1.1
    return 1.0


def _compute_target_tk_scaling(window):
    """
    Compute desired Tk scaling from monitor DPI/resolution.
    This adapts better when moving windows between monitors.
    """
    monitor_dpi, monitor_width, monitor_height = _get_monitor_metrics(window)
    monitor_info_available = bool(monitor_width and monitor_height)

    # Resolution-based fallback works well even when physical DPI data is missing.
    resolution_multiplier = _resolution_scale_for_monitor(monitor_width, monitor_height)
    resolution_tk_scaling = _BASE_TK_SCALING * resolution_multiplier

    dpi_tk_scaling = _BASE_TK_SCALING
    if monitor_dpi:
        dpi_tk_scaling = _BASE_TK_SCALING * (monitor_dpi / 96.0)

    if monitor_info_available:
        target_tk_scaling = max(_BASE_TK_SCALING, dpi_tk_scaling, resolution_tk_scaling)
    else:
        # Last-resort fallback to Tk-reported DPI if monitor metadata is unavailable.
        try:
            tk_dpi = float(window.winfo_fpixels("1i"))
            tk_tk_scaling = tk_dpi / 72.0
        except Exception:
            tk_tk_scaling = _BASE_TK_SCALING
        target_tk_scaling = max(_BASE_TK_SCALING, tk_tk_scaling)

    return min(target_tk_scaling, 3.0)


def _apply_font_scaling(scale_multiplier):
    """Apply font scaling from stable baseline sizes (no cumulative drift)."""
    for font_name in (
        "TkDefaultFont",
        "TkTextFont",
        "TkFixedFont",
        "TkMenuFont",
        "TkHeadingFont",
        "TkCaptionFont",
        "TkSmallCaptionFont",
        "TkIconFont",
        "TkTooltipFont",
    ):
        try:
            font = tkfont.nametofont(font_name)
            if font_name not in _font_base_sizes:
                _font_base_sizes[font_name] = int(font.cget("size"))

            base_size = _font_base_sizes[font_name]
            if base_size < 0:
                scaled_size = int(base_size * scale_multiplier)
            else:
                scaled_size = max(1, int(base_size * scale_multiplier))
            font.configure(size=scaled_size)
        except Exception:
            pass


def _apply_dynamic_scaling(root):
    """Recompute and apply scaling for the monitor where a window currently sits."""
    global _scale_factor

    target_tk_scaling = _compute_target_tk_scaling(root)
    current_scaling = float(root.tk.call("tk", "scaling"))
    if abs(current_scaling - target_tk_scaling) > 0.03:
        root.tk.call("tk", "scaling", target_tk_scaling)

    _scale_factor = max(1.0, target_tk_scaling / _BASE_TK_SCALING)
    _apply_font_scaling(_scale_factor)


def _start_scaling_poll(root):
    """Continuously refresh scaling so monitor moves update UI size automatically."""
    def poll():
        if not root.winfo_exists():
            return
        _apply_dynamic_scaling(root)
        root._scaling_poll_after_id = root.after(900, poll)

    existing_after = getattr(root, "_scaling_poll_after_id", None)
    if existing_after:
        try:
            root.after_cancel(existing_after)
        except Exception:
            pass
    root._scaling_poll_after_id = root.after(900, poll)


def ensure_window_scaling(window):
    """
    Apply monitor-aware scaling for a window and keep watching for monitor changes.
    This can be used on Tk roots and Toplevels.
    """
    window.update_idletasks()
    _apply_dynamic_scaling(window)
    _start_scaling_poll(window)


def init_dpi_scaling(root):
    """
    Detect system DPI and apply scaling to Tkinter.
    Call once after creating the Tk root window.
    """
    root.update_idletasks()
    _apply_dynamic_scaling(root)
    _start_scaling_poll(root)


def get_scale_factor():
    """Return the current DPI scale factor."""
    return _scale_factor


def scaled(pixel_value):
    """Scale a pixel value by the current DPI factor."""
    return max(1, int(pixel_value * _scale_factor))


def scaled_font(family, size, weight=""):
    """Return a font tuple with the size scaled for the current DPI."""
    scaled_size = max(1, int(size * _scale_factor))
    if weight:
        return (family, scaled_size, weight)
    return (family, scaled_size)


def _get_max_window_bounds(window):
    """
    Compute safe max window bounds for reliable first-open visibility.
    Caps prevent oversized windows from pushing action buttons below the viewport.
    """
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    max_width = max(320, min(int(screen_width * 0.94), scaled(1280)))
    max_height = max(240, min(int(screen_height * 0.88), scaled(760)))
    return max_width, max_height


def _normalize_window_size(window, width, height):
    """
    Normalize a requested window size so it:
    - respects DPI scaling
    - honors explicit minimum size constraints
    - stays inside the visible screen bounds
    """
    requested_width = max(1, int(width))
    requested_height = max(1, int(height))

    # Scale hard-coded pixel sizes for high-DPI displays.
    scaled_width = scaled(requested_width)
    scaled_height = scaled(requested_height)

    max_width, max_height = _get_max_window_bounds(window)

    min_width, min_height = window.minsize()
    min_width = max(1, int(min_width))
    min_height = max(1, int(min_height))

    # Protect against oversized hard-coded mins that can hide bottom controls.
    safe_min_width = min(min_width, max_width)
    safe_min_height = min(min_height, max_height)
    if safe_min_width != min_width or safe_min_height != min_height:
        window.minsize(safe_min_width, safe_min_height)

    normalized_width = max(scaled_width, safe_min_width)
    normalized_height = max(scaled_height, safe_min_height)
    normalized_width = min(normalized_width, max_width)
    normalized_height = min(normalized_height, max_height)

    return normalized_width, normalized_height


def _expand_window_to_fit_content(window):
    """
    Grow the initial geometry if widget content needs extra space.
    This prevents action buttons from being clipped on first open.
    """
    if not window.winfo_exists():
        return

    window.update_idletasks()

    content_padding = scaled(40)
    required_width = window.winfo_reqwidth() + content_padding
    required_height = window.winfo_reqheight() + content_padding

    current_width = window.winfo_width()
    current_height = window.winfo_height()
    target_width = max(current_width, required_width)
    target_height = max(current_height, required_height)

    min_width, min_height = window.minsize()
    target_width = max(target_width, int(min_width))
    target_height = max(target_height, int(min_height))

    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    max_width, max_height = _get_max_window_bounds(window)

    target_width = min(target_width, max_width)
    target_height = min(target_height, max_height)

    if target_width == current_width and target_height == current_height:
        return

    x = window.winfo_x()
    y = window.winfo_y()
    x = max(0, min(x, screen_width - target_width))
    y = max(0, min(y, screen_height - target_height))
    window.geometry(f"{target_width}x{target_height}+{x}+{y}")


def center_window_on_parent(window, parent, width, height):
    """
    Position a window centered over its parent window.
    This ensures the window opens on the same monitor as the parent.
    If no parent is provided, centers on the screen.

    Args:
        window: The tkinter window to position
        parent: The parent tkinter window (or None)
        width: Desired window width
        height: Desired window height
    """
    # Use the parent's monitor for initial scaling when available.
    if parent and parent.winfo_exists():
        _apply_dynamic_scaling(parent)
    else:
        _apply_dynamic_scaling(window)

    window.update_idletasks()
    width, height = _normalize_window_size(window, width, height)

    if parent:
        parent.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()

        x = parent_x + (parent_w - width) // 2
        y = parent_y + (parent_h - height) // 2
    else:
        # Top-biased centering for root windows keeps bottom action buttons
        # visible on first open in shorter desktop viewports.
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = (screen_w - width) // 2
        if height >= scaled(500):
            y = min((screen_h - height) // 2, scaled(24))
        else:
            y = (screen_h - height) // 2

    # Keep the full window within visible screen bounds.
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    x = max(0, min(x, screen_w - width))
    y = max(0, min(y, screen_h - height))

    window.geometry(f'{width}x{height}+{x}+{y}')

    # Re-check scaling once positioned, then keep monitoring this window for monitor moves.
    previous_scale = _scale_factor
    _apply_dynamic_scaling(window)
    if abs(_scale_factor - previous_scale) > 0.02:
        width, height = _normalize_window_size(window, width, height)
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = max(0, min(x, screen_w - width))
        y = max(0, min(y, screen_h - height))
        window.geometry(f"{width}x{height}+{x}+{y}")

    _start_scaling_poll(window)
