#!/usr/bin/env python3
"""
Keepa API Tracker - Unified Menu
Main entry point for all tracking tools
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import pyautogui
from dotenv import load_dotenv

# Load API key from .env
load_dotenv('.env.local')
KEEPA_API_KEY = os.getenv('Keepa_API_KEY')

# Validate that API key was loaded
if not KEEPA_API_KEY:
    print("Error: Keepa_API_KEY not found in .env.local file.")
    print("Please ensure your .env.local file contains: Keepa_API_KEY=your_api_key_here")
    sys.exit(1)


class KeepaTrackerMenu:
    """Main menu for Keepa API tracking tools"""

    def __init__(self):
        """Initialize the menu window"""
        self.root = tk.Tk()
        self.root.title("Keepa API Tracker - Main Menu")
        self.root.resizable(False, False)

        # Center the window on screen
        window_width = 600
        window_height = 400
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        self.root.geometry(f'{window_width}x{window_height}+{x}+{y}')

        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface"""
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="40")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # Title
        title_label = ttk.Label(
            main_frame,
            text="Keepa API Tracker",
            font=("Arial", 20, "bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 10))

        # Subtitle
        subtitle_label = ttk.Label(
            main_frame,
            text="Select a tracking tool to begin",
            font=("Arial", 11)
        )
        subtitle_label.grid(row=1, column=0, pady=(0, 30))

        # Separator
        separator = ttk.Separator(main_frame, orient='horizontal')
        separator.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 30))

        # Tool buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.grid(row=3, column=0, pady=(0, 20))

        # Buybox Tracker button
        buybox_frame = self.create_tool_button(
            buttons_frame,
            "Buybox Tracker",
            "Analyze Amazon buybox history and ownership percentages",
            self.launch_buybox_tracker
        )
        buybox_frame.pack(pady=10, fill=tk.X)

        # Sales Rank Analyzer button
        sales_rank_frame = self.create_tool_button(
            buttons_frame,
            "Sales Rank Analyzer",
            "Track and analyze product sales rank trends",
            self.launch_sales_rank_analyzer
        )
        sales_rank_frame.pack(pady=10, fill=tk.X)

        # Separator
        separator2 = ttk.Separator(main_frame, orient='horizontal')
        separator2.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(20, 20))

        # Exit button
        exit_btn = ttk.Button(
            main_frame,
            text="Exit",
            command=self.exit_application,
            width=20
        )
        exit_btn.grid(row=5, column=0)

        # Bind Escape key to exit
        self.root.bind('<Escape>', lambda e: self.exit_application())

    def create_tool_button(self, parent, title, description, command):
        """
        Create a styled button for a tracking tool

        Args:
            parent: Parent widget
            title: Tool title
            description: Tool description
            command: Function to call when clicked

        Returns:
            Frame containing the button
        """
        # Container frame
        container = ttk.Frame(parent, relief="raised", borderwidth=1)

        # Create a frame for button content
        button_frame = ttk.Frame(container)
        button_frame.pack(padx=20, pady=15, fill=tk.X)

        # Title
        title_label = ttk.Label(
            button_frame,
            text=title,
            font=("Arial", 14, "bold")
        )
        title_label.pack(anchor=tk.W)

        # Description
        desc_label = ttk.Label(
            button_frame,
            text=description,
            font=("Arial", 9),
            foreground="gray"
        )
        desc_label.pack(anchor=tk.W, pady=(5, 10))

        # Launch button
        launch_btn = ttk.Button(
            button_frame,
            text=f"Launch {title}",
            command=command,
            width=25
        )
        launch_btn.pack(anchor=tk.W)

        # Make the whole frame clickable
        for widget in [container, button_frame, title_label, desc_label]:
            widget.bind('<Button-1>', lambda e: command())
            widget.bind('<Enter>', lambda e: container.configure(relief="sunken"))
            widget.bind('<Leave>', lambda e: container.configure(relief="raised"))

        return container

    def launch_buybox_tracker(self):
        """Launch the buybox tracker tool"""
        self.root.destroy()
        try:
            # Import and run the buybox tracker
            import buybox_amazon_percent
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Failed to launch Buybox Tracker:\n{str(e)}"
            )
            sys.exit(1)

    def launch_sales_rank_analyzer(self):
        """Launch the sales rank analyzer tool"""
        self.root.destroy()
        try:
            # Import and run the sales rank analyzer
            import sales_rank_analyzer
            sales_rank_analyzer.main()
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Failed to launch Sales Rank Analyzer:\n{str(e)}"
            )
            sys.exit(1)

    def exit_application(self):
        """Exit the application"""
        self.root.destroy()
        sys.exit(0)

    def run(self):
        """Start the menu application"""
        self.root.mainloop()


def main():
    """Main entry point"""
    print("=" * 50)
    print("Keepa API Tracker - Unified Menu")
    print("=" * 50)
    print("\nLaunching menu...")

    app = KeepaTrackerMenu()
    app.run()


if __name__ == "__main__":
    main()
