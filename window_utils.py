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

    if parent:
        parent.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()

        x = parent_x + (parent_w - width) // 2
        y = parent_y + (parent_h - height) // 2
    else:
        # No parent - try to center at mouse position so the window
        # appears on whichever monitor the user is currently using.
        try:
            import pyautogui
            mouse_x, mouse_y = pyautogui.position()
            x = mouse_x - (width // 2)
            y = mouse_y - (height // 2)
        except Exception:
            # Fallback to screen center
            screen_w = window.winfo_screenwidth()
            screen_h = window.winfo_screenheight()
            x = (screen_w - width) // 2
            y = (screen_h - height) // 2

    # Ensure window is not positioned off the top-left edge
    x = max(0, x)
    y = max(0, y)

    window.geometry(f'{width}x{height}+{x}+{y}')
