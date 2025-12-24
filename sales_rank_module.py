"""
Sales Rank Analyzer Module
This module provides functionality for analyzing sales rank data from Keepa API.
It follows the Single Responsibility Principle by focusing solely on sales rank analysis.
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import pyautogui


class SalesRankAnalyzer:
    """
    A class to analyze sales rank data from Keepa API.
    This follows the Single Responsibility Principle by focusing only on sales rank analysis.
    """
    
    def __init__(self, api_key, verbose=False):
        """
        Initialize the analyzer with the Keepa API key.
        
        Args:
            api_key (str): The Keepa API key for authentication
            verbose (bool): If True, print detailed debugging information
        """
        self.api_key = api_key
        self.keepa_epoch = datetime(2011, 1, 1)  # Keepa's epoch date
        self.verbose = verbose  # Enable debug output when True
        
        # Store information about the last analyzed product
        self.selected_category_id = None
        self.selected_category_name = None
    
    def _debug_print(self, message):
        """Print debug message if verbose mode is enabled."""
        if self.verbose:
            print(f"[DEBUG] {message}")
        
    def get_product_sales_rank(self, asin, domain=1):
        """
        Fetch sales rank data for a specific ASIN from Keepa API.
        
        Args:
            asin (str): The Amazon ASIN (10-character product identifier)
            domain (int): Amazon domain (1 for Amazon.com)
            
        Returns:
            dict: Product data including sales rank history, or None if not found
        """
        url = 'https://api.keepa.com/product'
        params = {
            'key': self.api_key,
            'domain': domain,
            'asin': asin,
            'history': 1,  # Include historical data
            'stats': 1     # Include statistics
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise exception for bad status codes
            data = response.json()
            
            if not data.get('products'):
                print(f'No product data found for ASIN: {asin}')
                return None
                
            return data['products'][0]
            
        except requests.exceptions.RequestException as e:
            print(f'Error fetching data for ASIN {asin}: {e}')
            return None
    
    def parse_sales_rank_history(self, product_data):
        """
        Parse sales rank history from Keepa product data.
        
        Uses the categoryTree to find the most specific (deepest) category,
        which is the last item in the category tree hierarchy.
        
        Args:
            product_data (dict): Product data from Keepa API
            
        Returns:
            pandas.DataFrame: DataFrame with datetime and sales rank columns
        """
        if not product_data:
            self._debug_print("parse_sales_rank_history: product_data is None/empty")
            return pd.DataFrame()
        
        self._debug_print(f"parse_sales_rank_history: Product title: {product_data.get('title', 'N/A')}")
            
        # Keepa provides sales rank data in the salesRanks field
        # Format: {"category_id": [timestamp1, rank1, timestamp2, rank2, ...]}
        sales_ranks_data = product_data.get('salesRanks', {})
        
        self._debug_print(f"parse_sales_rank_history: salesRanks field type: {type(sales_ranks_data)}")
        self._debug_print(f"parse_sales_rank_history: salesRanks keys: {list(sales_ranks_data.keys()) if sales_ranks_data else 'None'}")
        
        if not sales_ranks_data:
            self._debug_print("parse_sales_rank_history: salesRanks is empty - returning empty DataFrame")
            return pd.DataFrame()
        
        # Get the categoryTree to find the most specific category
        # The categoryTree is ordered from broad to specific, so the last item
        # is the most specific (deepest) category for the product
        category_tree = product_data.get('categoryTree', [])
        
        # Build a lookup dictionary for category names
        category_names = {}
        self._debug_print(f"parse_sales_rank_history: categoryTree has {len(category_tree)} levels")
        for i, cat in enumerate(category_tree):
            cat_id = cat.get('catId') if isinstance(cat, dict) else cat
            cat_name = cat.get('name', 'Unknown') if isinstance(cat, dict) else 'Unknown'
            category_names[str(cat_id)] = cat_name
            self._debug_print(f"  Level {i+1}: {cat_name} (ID: {cat_id})")
        
        # Reset selected category info
        self.selected_category_id = None
        self.selected_category_name = None
        
        # Find the target category - use the most specific (last) category from categoryTree
        target_category_id = None
        target_category_name = None
        sales_rank_data = None
        
        if category_tree:
            # Get the last (most specific) category from the tree
            last_category = category_tree[-1]
            # categoryTree entries can be dicts with 'catId' or just IDs
            if isinstance(last_category, dict):
                target_category_id = last_category.get('catId')
                target_category_name = last_category.get('name', 'Unknown')
            else:
                target_category_id = last_category
                target_category_name = 'Unknown'
            
            self._debug_print(f"parse_sales_rank_history: Target category from tree: {target_category_name} (ID: {target_category_id})")
            
            # Look for this category in salesRanks
            # Note: salesRanks keys might be strings or integers depending on JSON parsing
            target_category_str = str(target_category_id)
            
            for category_id, rank_data in sales_ranks_data.items():
                if str(category_id) == target_category_str:
                    if isinstance(rank_data, list) and len(rank_data) >= 2:
                        sales_rank_data = rank_data
                        # Store the selected category info
                        self.selected_category_id = target_category_id
                        self.selected_category_name = target_category_name
                        self._debug_print(f"parse_sales_rank_history: Found target category {target_category_name} (ID: {target_category_id}) in salesRanks!")
                        break
            
            if not sales_rank_data:
                self._debug_print(f"parse_sales_rank_history: Target category {target_category_id} not found in salesRanks keys: {list(sales_ranks_data.keys())}")
        
        # Fallback: if target category not found, use the first available category with valid data
        if not sales_rank_data:
            self._debug_print("parse_sales_rank_history: Using fallback - selecting first available category with data")
            for category_id, rank_data in sales_ranks_data.items():
                if isinstance(rank_data, list) and len(rank_data) >= 2:
                    # Check if there's at least some valid (non -1) data
                    valid_ranks = [r for r in rank_data[1::2] if r != -1]
                    if valid_ranks:
                        sales_rank_data = rank_data
                        # Store fallback category info
                        self.selected_category_id = category_id
                        # Try to get the name from our lookup, otherwise use 'Unknown'
                        self.selected_category_name = category_names.get(str(category_id), f"Category {category_id}")
                        self._debug_print(f"parse_sales_rank_history: Fallback selected category: {self.selected_category_name} (ID: {category_id}, {len(valid_ranks)} valid ranks)")
                        break
            
            if not sales_rank_data:
                self._debug_print("parse_sales_rank_history: No valid category data found - returning empty DataFrame")
                return pd.DataFrame()
        
        # Parse the sales rank data
        # Format: [timestamp1, rank1, timestamp2, rank2, ...]
        records = []
        skipped_negative_one = 0
        parse_errors = 0
        
        for i in range(0, len(sales_rank_data), 2):
            if i + 1 < len(sales_rank_data):
                try:
                    minutes = int(sales_rank_data[i])
                    rank = sales_rank_data[i + 1]
                    
                    # Convert Keepa minutes to datetime
                    dt = self.keepa_epoch + timedelta(minutes=minutes)
                    
                    # Keepa uses -1 to indicate no rank data
                    if rank != -1:
                        records.append({
                            'datetime': dt,
                            'sales_rank': rank
                        })
                    else:
                        skipped_negative_one += 1
                except (ValueError, TypeError) as e:
                    parse_errors += 1
                    continue
        
        self._debug_print(f"parse_sales_rank_history: Parsed {len(records)} records, skipped {skipped_negative_one} (-1 values), {parse_errors} parse errors")
        
        if records:
            # Show date range of parsed data
            dates = [r['datetime'] for r in records]
            self._debug_print(f"parse_sales_rank_history: Date range: {min(dates)} to {max(dates)}")
        
        return pd.DataFrame(records)
    
    def calculate_sales_rank_stats(self, df, days=30):
        """
        Calculate sales rank statistics for the last N days.
        
        Args:
            df (pandas.DataFrame): DataFrame with datetime and sales_rank columns
            days (int): Number of days to analyze (default: 30)
            
        Returns:
            dict: Dictionary containing various sales rank statistics
        """
        self._debug_print(f"calculate_sales_rank_stats: Analyzing last {days} days")
        self._debug_print(f"calculate_sales_rank_stats: Input DataFrame has {len(df)} rows")
        
        if df.empty:
            self._debug_print("calculate_sales_rank_stats: DataFrame is empty - returning zeros")
            return {
                'average_rank': None,
                'min_rank': None,
                'max_rank': None,
                'rank_changes': 0,
                'data_points': 0,
                'days_analyzed': days
            }
        
        # Filter for last N days
        cutoff_date = datetime.now() - timedelta(days=days)
        self._debug_print(f"calculate_sales_rank_stats: Cutoff date: {cutoff_date}")
        self._debug_print(f"calculate_sales_rank_stats: DataFrame date range: {df['datetime'].min()} to {df['datetime'].max()}")
        
        recent_data = df[df['datetime'] >= cutoff_date].copy()
        
        self._debug_print(f"calculate_sales_rank_stats: After filtering: {len(recent_data)} rows (from {len(df)} total)")
        
        if recent_data.empty:
            self._debug_print("calculate_sales_rank_stats: No data within period - returning zeros")
            self._debug_print(f"  HINT: Data ends at {df['datetime'].max()}, but cutoff is {cutoff_date}")
            return {
                'average_rank': None,
                'min_rank': None,
                'max_rank': None,
                'rank_changes': 0,
                'data_points': 0,
                'days_analyzed': days
            }
        
        # Calculate statistics
        stats = {
            'average_rank': recent_data['sales_rank'].mean(),
            'min_rank': recent_data['sales_rank'].min(),
            'max_rank': recent_data['sales_rank'].max(),
            'rank_changes': len(recent_data) - 1,  # Number of rank changes
            'data_points': len(recent_data),
            'days_analyzed': days
        }
        
        self._debug_print(f"calculate_sales_rank_stats: Stats calculated successfully")
        
        return stats
    
    def get_user_input(self, parent_window=None):
        """
        Creates a user input window for sales rank analysis.
        Returns tuple of (asin, days, export_csv) or None if cancelled.
        
        Args:
            parent_window: Optional parent window for modal behavior
            
        Returns:
            tuple: (asin, days, export_csv) or None if cancelled
        """
        # Create the main input window
        root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        root.title("Sales Rank Analyzer - Input")
        
        # IMPORTANT: Enable resizing so user can expand the window if needed
        root.resizable(True, True)
        
        # Set minimum size to ensure UI elements are visible
        root.minsize(400, 300)
        
        # Center the window on screen with a reasonable default size
        root.update_idletasks()
        window_width = 500
        window_height = 400
        x = (root.winfo_screenwidth() // 2) - (window_width // 2)
        y = (root.winfo_screenheight() // 2) - (window_height // 2)
        root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        # Show window on top initially
        root.lift()
        root.attributes('-topmost', True)
        root.after_idle(lambda: root.attributes('-topmost', False))
        
        # Variables to store input values
        asin_var = tk.StringVar()
        days_var = tk.StringVar(value="30")  # Default to 30 days
        export_var = tk.BooleanVar()
        
        # Variable to store the result
        result_var = [None]
        
        def validate_inputs():
            """Validates all inputs and returns (asin, days, export_csv) or None if invalid"""
            asin = asin_var.get().strip()
            days_str = days_var.get().strip()
            
            # Validate ASIN
            if not asin or len(asin) != 10:
                messagebox.showerror('Validation Error', 'ASIN must be exactly 10 characters.', parent=root)
                return None
            
            # Validate Days
            if not days_str or not days_str.isdigit():
                messagebox.showerror('Validation Error', 'Days must be a valid number.', parent=root)
                return None
            
            days = int(days_str)
            if days < 1 or days > 365:
                messagebox.showerror('Validation Error', 'Days must be between 1 and 365.', parent=root)
                return None
            
            return asin, days, export_var.get()
        
        def submit_inputs():
            """Handles form submission and validation"""
            result = validate_inputs()
            if result:
                result_var[0] = result
                root.destroy()
        
        def cancel_inputs():
            """Handles cancellation"""
            root.destroy()
        
        # Create the form layout
        main_frame = ttk.Frame(root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Sales Rank Analyzer", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # ASIN Input
        ttk.Label(main_frame, text="ASIN (10 characters):", font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        asin_entry = ttk.Entry(main_frame, textvariable=asin_var, width=30)
        asin_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Days Input
        ttk.Label(main_frame, text="Days to analyze:", font=("Arial", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        days_entry = ttk.Entry(main_frame, textvariable=days_var, width=30)
        days_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Help text
        help_text = "Enter number of days to analyze (1-365)"
        help_label = ttk.Label(main_frame, text=help_text, font=("Arial", 8), foreground="gray")
        help_label.grid(row=3, column=0, columnspan=2, pady=(5, 10))
        
        # Export checkbox
        export_checkbox = ttk.Checkbutton(main_frame, text="Export results to CSV file", variable=export_var)
        export_checkbox.grid(row=4, column=0, columnspan=2, pady=(5, 20))
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=(10, 0))
        
        # Submit and Cancel buttons
        submit_btn = ttk.Button(button_frame, text="Submit", command=submit_inputs, style="Accent.TButton")
        submit_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel_inputs)
        cancel_btn.pack(side=tk.LEFT)
        
        # Set focus to first entry and bind Enter key
        asin_entry.focus()
        root.bind('<Return>', lambda e: submit_inputs())
        root.bind('<Escape>', lambda e: cancel_inputs())
        
        # Start the GUI event loop (only if not a child window)
        if not parent_window:
            root.mainloop()
        else:
            root.wait_window()
        
        # Return the stored result
        return result_var[0]
    
    def process_and_display_results(self, asin, days, export_csv, parent_window=None, verbose=False):
        """
        Process ASIN and display sales rank analysis results in a GUI window.
        
        Args:
            asin (str): The analyzed ASIN
            days (int): Number of days to analyze
            export_csv (bool): Whether to offer CSV export
            parent_window: Optional parent window for modal behavior
            verbose (bool): If True, enable debug output for this analysis
        """
        # Temporarily enable verbose mode if requested
        original_verbose = self.verbose
        if verbose:
            self.verbose = True
        
        self._debug_print(f"=" * 60)
        self._debug_print(f"Starting sales rank analysis for ASIN: {asin}")
        self._debug_print(f"Days to analyze: {days}")
        self._debug_print(f"=" * 60)
        
        # Fetch product data
        print(f"Fetching sales rank data for ASIN: {asin}")
        product_data = self.get_product_sales_rank(asin)
        
        if not product_data:
            self._debug_print("process_and_display_results: API returned no product data")
            self.verbose = original_verbose  # Restore original verbose setting
            if parent_window:
                messagebox.showerror("Error", "Failed to fetch product data.", parent=parent_window)
            else:
                print("Failed to fetch product data. Exiting.")
            return
        
        self._debug_print(f"process_and_display_results: Product data received, parsing sales rank history...")
        
        # Parse sales rank history
        sales_rank_df = self.parse_sales_rank_history(product_data)
        
        if sales_rank_df.empty:
            self._debug_print("process_and_display_results: parse_sales_rank_history returned empty DataFrame")
            self.verbose = original_verbose  # Restore original verbose setting
            if parent_window:
                messagebox.showwarning("Warning", "No sales rank history found for this product.", parent=parent_window)
            else:
                print("No sales rank history found for this product.")
            return
        
        self._debug_print(f"process_and_display_results: DataFrame has {len(sales_rank_df)} records, calculating stats...")
        
        # Calculate statistics
        stats = self.calculate_sales_rank_stats(sales_rank_df, days)
        
        self._debug_print(f"process_and_display_results: Stats calculated - data_points={stats['data_points']}")
        self._debug_print(f"=" * 60)
        
        # Restore original verbose setting
        self.verbose = original_verbose
        
        # Display results
        result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        result_root.title(f'Sales Rank Analysis - {asin}')
        
        # IMPORTANT: Enable resizing so user can expand the window
        result_root.resizable(True, True)
        
        # Set minimum size
        result_root.minsize(700, 500)
        
        # Center the window on screen with a larger default size
        result_root.update_idletasks()
        screen_width = result_root.winfo_screenwidth()
        screen_height = result_root.winfo_screenheight()
        # Use 70% of screen dimensions
        window_width = min(int(screen_width * 0.70), 1200)
        window_height = min(int(screen_height * 0.70), 900)
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        result_root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        # Show window on top initially
        result_root.lift()
        result_root.attributes('-topmost', True)
        result_root.after_idle(lambda: result_root.attributes('-topmost', False))
        
        # Create scrolled text widget
        text = scrolledtext.ScrolledText(result_root, wrap=tk.WORD, width=60, height=25)
        text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Format output
        output_lines = [f'Sales Rank Analysis for ASIN: {asin}\n']
        output_lines.append('=' * 50)
        
        # Show the selected category
        if self.selected_category_name:
            output_lines.append(f'Category: {self.selected_category_name}')
            if self.selected_category_id:
                output_lines.append(f'Category ID: {self.selected_category_id}')
            output_lines.append('')
        
        if stats['data_points'] == 0:
            output_lines.append('No sales rank data available for the specified time period.')
        else:
            output_lines.append(f'Analysis Period: Last {stats["days_analyzed"]} days')
            output_lines.append(f'Data Points: {stats["data_points"]}')
            output_lines.append(f'Rank Changes: {stats["rank_changes"]}')
            output_lines.append('')
            output_lines.append('Statistics:')
            output_lines.append(f'  Average Rank: {stats["average_rank"]:.0f}' if stats["average_rank"] else '  Average Rank: N/A')
            output_lines.append(f'  Best Rank: {stats["min_rank"]}' if stats["min_rank"] else '  Best Rank: N/A')
            output_lines.append(f'  Worst Rank: {stats["max_rank"]}' if stats["max_rank"] else '  Worst Rank: N/A')
            
            if not sales_rank_df.empty:
                output_lines.append('')
                output_lines.append('Recent Rank History (last 10 entries):')
                recent_data = sales_rank_df.tail(10)
                for _, row in recent_data.iterrows():
                    output_lines.append(f'  {row["datetime"].strftime("%Y-%m-%d %H:%M")}: Rank #{row["sales_rank"]}')
        
        output_lines.append('=' * 50)
        text.insert(tk.END, '\n'.join(output_lines))
        text.config(state=tk.DISABLED)
        
        # Handle CSV export if requested
        if export_csv and not sales_rank_df.empty:
            save_path = filedialog.asksaveasfilename(
                title='Save sales rank history as CSV',
                defaultextension='.csv',
                filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
                parent=result_root
            )
            if save_path:
                sales_rank_df.to_csv(save_path, index=False)
                messagebox.showinfo('Export', f'Sales rank history saved to {save_path}', parent=result_root)
            else:
                messagebox.showinfo('Export', 'No file selected. Data not saved.', parent=result_root)
        
        # If parent_window exists, wait for window to close; otherwise run mainloop
        if parent_window:
            result_root.wait_window()
        else:
            result_root.mainloop()

