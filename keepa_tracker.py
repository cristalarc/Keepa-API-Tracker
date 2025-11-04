"""
Keepa API Tracker - Main Application
This is the main entry point for the unified Keepa API tracking application.
It provides a menu-driven interface to access different analysis tools.
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from dotenv import load_dotenv
import pyautogui
from buybox_analyzer import BuyboxAnalyzer
from sales_rank_module import SalesRankAnalyzer


# Load API key from .env
load_dotenv('.env.local')
KEEPA_API_KEY = os.getenv('Keepa_API_KEY')

# Validate that API key was loaded
if not KEEPA_API_KEY:
    print("Error: Keepa_API_KEY not found in .env.local file.")
    print("Please ensure your .env.local file contains: Keepa_API_KEY=your_api_key_here")
    exit(1)


class KeepaTrackerApp:
    """
    Main application class for the Keepa API Tracker.
    This class manages the main menu and coordinates between different analyzers.
    """
    
    def __init__(self):
        """Initialize the main application"""
        self.root = None
        self.buybox_analyzer = BuyboxAnalyzer(KEEPA_API_KEY)
        self.sales_rank_analyzer = SalesRankAnalyzer(KEEPA_API_KEY)
    
    def create_main_menu(self):
        """
        Creates and displays the main menu window.
        This is the central hub where users can select which analysis tool to use.
        """
        mouse_x, mouse_y = pyautogui.position()
        
        # Create the main window
        self.root = tk.Tk()
        self.root.title("Keepa API Tracker")
        self.root.geometry(f'500x400+{mouse_x}+{mouse_y}')
        
        # Center the window on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.root.winfo_screenheight() // 2) - (400 // 2)
        self.root.geometry(f'500x400+{x}+{y}')
        
        # Make window stay on top initially, then allow normal behavior
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after_idle(lambda: self.root.attributes('-topmost', False))
        
        # Create main frame
        main_frame = ttk.Frame(self.root, padding="30")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame, 
            text="Keepa API Tracker", 
            font=("Arial", 24, "bold")
        )
        title_label.pack(pady=(0, 30))
        
        # Subtitle
        subtitle_label = ttk.Label(
            main_frame, 
            text="Select an analysis tool:", 
            font=("Arial", 12)
        )
        subtitle_label.pack(pady=(0, 20))
        
        # Create button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)
        
        # Buybox Analyzer Button
        buybox_btn = ttk.Button(
            button_frame,
            text="Buybox Analyzer",
            command=self.run_buybox_analyzer,
            width=25,
            style="Accent.TButton"
        )
        buybox_btn.pack(pady=10)
        
        # Add tooltip/description for buybox analyzer
        buybox_desc = ttk.Label(
            button_frame,
            text="Analyze Amazon buybox ownership percentages",
            font=("Arial", 9),
            foreground="gray"
        )
        buybox_desc.pack(pady=(0, 10))
        
        # Sales Rank Analyzer Button
        sales_rank_btn = ttk.Button(
            button_frame,
            text="Sales Rank Analyzer",
            command=self.run_sales_rank_analyzer,
            width=25
        )
        sales_rank_btn.pack(pady=10)
        
        # Add tooltip/description for sales rank analyzer
        sales_rank_desc = ttk.Label(
            button_frame,
            text="Analyze product sales rank trends",
            font=("Arial", 9),
            foreground="gray"
        )
        sales_rank_desc.pack(pady=(0, 10))
        
        # Exit Button
        exit_btn = ttk.Button(
            button_frame,
            text="Exit",
            command=self.exit_application,
            width=25
        )
        exit_btn.pack(pady=(20, 0))
        
        # Add footer
        footer_label = ttk.Label(
            main_frame,
            text="All tools will return to this menu when finished",
            font=("Arial", 8),
            foreground="gray"
        )
        footer_label.pack(side=tk.BOTTOM, pady=(20, 0))
    
    def run_buybox_analyzer(self):
        """
        Runs the buybox analyzer tool.
        After completion, returns to the main menu.
        """
        try:
            # Get user input for buybox analysis
            user_input = self.buybox_analyzer.get_user_input(parent_window=self.root)
            
            if user_input is None:
                # User cancelled, return to menu
                return
            
            asins, year, months, export_csv = user_input
            
            # Process and display results
            self.buybox_analyzer.process_and_display_results(
                asins, year, months, export_csv, parent_window=self.root
            )
            
            # Return to menu after results window is closed
            messagebox.showinfo(
                "Complete", 
                "Buybox analysis complete. Returning to main menu.",
                parent=self.root
            )
            
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"An error occurred during buybox analysis:\n{str(e)}",
                parent=self.root
            )
    
    def run_sales_rank_analyzer(self):
        """
        Runs the sales rank analyzer tool.
        After completion, returns to the main menu.
        """
        try:
            # Get user input for sales rank analysis
            user_input = self.sales_rank_analyzer.get_user_input(parent_window=self.root)
            
            if user_input is None:
                # User cancelled, return to menu
                return
            
            asin, days, export_csv = user_input
            
            # Process and display results
            self.sales_rank_analyzer.process_and_display_results(
                asin, days, export_csv, parent_window=self.root
            )
            
            # Return to menu after results window is closed
            messagebox.showinfo(
                "Complete", 
                "Sales rank analysis complete. Returning to main menu.",
                parent=self.root
            )
            
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"An error occurred during sales rank analysis:\n{str(e)}",
                parent=self.root
            )
    
    def exit_application(self):
        """Exits the application"""
        if messagebox.askyesno("Exit", "Are you sure you want to exit?", parent=self.root):
            self.root.destroy()
    
    def run(self):
        """
        Starts the main application loop.
        This is the entry point that displays the menu and handles user interactions.
        """
        self.create_main_menu()
        self.root.mainloop()


def main():
    """
    Main function to start the Keepa API Tracker application.
    This is the entry point when running the script directly.
    """
    print("Keepa API Tracker")
    print("=" * 30)
    print("Starting application...")
    
    # Create and run the application
    app = KeepaTrackerApp()
    app.run()


if __name__ == "__main__":
    main()

