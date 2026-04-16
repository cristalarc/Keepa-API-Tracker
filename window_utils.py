"""
Window utility functions for consistent window sizing and positioning.
Ensures child windows open on the same screen/monitor as their parent window.
"""


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
