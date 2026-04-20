"""
Window utility functions for consistent window sizing and positioning.
Ensures child windows open on the same screen/monitor as their parent window.
Provides DPI-aware scaling for fonts and pixel values on high-resolution displays.
"""

import tkinter.font as tkfont


_scale_factor = 1.0


def init_dpi_scaling(root):
    """
    Detect system DPI and apply scaling to Tkinter.
    Call once after creating the Tk root window.
    """
    global _scale_factor

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    root.update_idletasks()
    current_scaling = root.tk.call('tk', 'scaling')
    actual_dpi = root.winfo_fpixels('1i')
    target_scaling = actual_dpi / 72.0

    if target_scaling > current_scaling * 1.1:
        _scale_factor = target_scaling / current_scaling
        root.tk.call('tk', 'scaling', target_scaling)
    else:
        _scale_factor = 1.0

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
