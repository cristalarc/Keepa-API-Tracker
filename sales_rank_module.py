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

from asin_manager import (
    load_saved_asins,
    load_all_asin_lists,
    validate_asin,
    validate_asin_list,
    add_asins_to_saved_list
)


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
        Supports both single ASIN and batch processing modes.
        Returns tuple of (asins, days, export_csv) or None if cancelled.

        Args:
            parent_window: Optional parent window for modal behavior

        Returns:
            tuple: (asins, days, export_csv) or None if cancelled
                   asins is a list (single element for single mode, multiple for batch)
        """
        # Create the main input window
        root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        root.title("Sales Rank Analyzer - Input")

        # IMPORTANT: Enable resizing so user can expand the window if needed
        root.resizable(True, True)

        # Set minimum size to ensure UI elements are visible
        root.minsize(600, 500)

        # Center the window on screen with a reasonable default size
        root.update_idletasks()
        window_width = 700
        window_height = 600
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
        asin_input_mode = tk.StringVar(value="manual")  # "manual" or "select"
        batch_mode_var = tk.BooleanVar()  # Checkbox for batch processing mode

        # Variable to store the result
        result_var = [None]

        def update_asin_selection():
            """Update ASIN input based on selection mode"""
            if asin_input_mode.get() == "select":
                # Show combobox, hide manual entry
                asin_combobox.pack(fill=tk.X, expand=True)
                asin_entry.pack_forget()
                asin_combobox.config(state="readonly")
            else:
                # Show manual entry, hide combobox
                asin_entry.pack(fill=tk.X, expand=True)
                asin_combobox.pack_forget()
                asin_entry.config(state="normal")

        def update_batch_mode():
            """Update UI based on batch mode selection"""
            if batch_mode_var.get():
                # Batch mode: show batch input, hide single ASIN input
                batch_frame.grid(row=4, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 10), padx=(0, 0))
                asin_label.grid_remove()
                asin_input_frame.grid_remove()
                input_mode_label.grid_remove()
                manual_radio.grid_remove()
                select_radio.grid_remove()
                # Increase window height for batch mode
                root.geometry(f'{window_width}x700+{x}+{y}')
            else:
                # Single mode: hide batch input, show single ASIN input
                batch_frame.grid_remove()
                asin_label.grid()
                asin_input_frame.grid()
                input_mode_label.grid()
                manual_radio.grid()
                select_radio.grid()
                # Reset window height for single mode
                root.geometry(f'{window_width}x{window_height}+{x}+{y}')

        def validate_inputs():
            """Validates all inputs and returns (asins, days, export_csv) or None if invalid"""
            # Get ASIN(s) based on input mode
            if batch_mode_var.get():
                # Batch mode: validate multiple ASINs
                batch_text = batch_text_widget.get("1.0", tk.END).strip()
                if not batch_text:
                    messagebox.showerror('Validation Error', 'Please enter ASINs for batch processing.', parent=root)
                    return None

                valid_asins, error_msg = validate_asin_list(batch_text)
                if error_msg:
                    messagebox.showerror('Validation Error', error_msg, parent=root)
                    return None

                if not valid_asins:
                    messagebox.showerror('Validation Error', 'No valid ASINs found in batch input.', parent=root)
                    return None

                asins = valid_asins
            else:
                # Single mode: validate single ASIN
                if asin_input_mode.get() == "select":
                    asin = asin_var.get().strip()
                    if not asin:
                        messagebox.showerror('Validation Error', 'Please select an ASIN from the list.', parent=root)
                        return None
                else:
                    asin = asin_var.get().strip()
                    # Validate ASIN format
                    if not validate_asin(asin):
                        messagebox.showerror('Validation Error', 'ASIN must be exactly 10 characters (letters and numbers only).', parent=root)
                        return None
                asins = [asin]

            days_str = days_var.get().strip()

            # Validate Days
            if not days_str or not days_str.isdigit():
                messagebox.showerror('Validation Error', 'Days must be a valid number.', parent=root)
                return None

            days = int(days_str)
            if days < 1 or days > 365:
                messagebox.showerror('Validation Error', 'Days must be between 1 and 365.', parent=root)
                return None

            return asins, days, export_var.get()

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
        main_frame.columnconfigure(2, weight=1)

        # Title
        title_label = ttk.Label(main_frame, text="Sales Rank Analyzer", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # Processing Mode Selection
        ttk.Label(main_frame, text="Processing Mode:", font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)

        single_mode_radio = ttk.Radiobutton(main_frame, text="Single ASIN", variable=batch_mode_var, value=False, command=update_batch_mode)
        single_mode_radio.grid(row=1, column=1, sticky=tk.W, pady=5)

        batch_mode_radio = ttk.Radiobutton(main_frame, text="Batch Processing", variable=batch_mode_var, value=True, command=update_batch_mode)
        batch_mode_radio.grid(row=1, column=2, sticky=tk.W, pady=5)

        # ASIN Input Mode Selection (for single mode)
        input_mode_label = ttk.Label(main_frame, text="ASIN Input Mode:", font=("Arial", 10))
        input_mode_label.grid(row=2, column=0, sticky=tk.W, pady=5)

        manual_radio = ttk.Radiobutton(main_frame, text="Manual Input", variable=asin_input_mode, value="manual", command=update_asin_selection)
        manual_radio.grid(row=2, column=1, sticky=tk.W, pady=5)

        select_radio = ttk.Radiobutton(main_frame, text="Select from List", variable=asin_input_mode, value="select", command=update_asin_selection)
        select_radio.grid(row=2, column=2, sticky=tk.W, pady=5)

        # ASIN Input
        asin_label = ttk.Label(main_frame, text="ASIN:", font=("Arial", 10))
        asin_label.grid(row=3, column=0, sticky=tk.W, pady=5)

        # Create a frame to hold the ASIN input widgets
        asin_input_frame = ttk.Frame(main_frame)
        asin_input_frame.grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))

        # Manual entry
        asin_entry = ttk.Entry(asin_input_frame, textvariable=asin_var, width=30)
        asin_entry.pack(fill=tk.X, expand=True)

        # Combobox for selection
        saved_asins = load_saved_asins()
        asin_combobox = ttk.Combobox(asin_input_frame, textvariable=asin_var, values=sorted(saved_asins), state="disabled", width=30)
        asin_combobox.pack(fill=tk.X, expand=True)

        # Batch Processing Input
        batch_frame = ttk.LabelFrame(main_frame, text="Batch ASIN Processing", padding="10")

        ttk.Label(batch_frame, text="Enter ASINs (comma, space, or newline separated):").pack(anchor=tk.W)

        batch_text_widget = tk.Text(batch_frame, height=6, width=50)
        batch_text_widget.pack(fill=tk.X, pady=(5, 10))

        # Quick load buttons for batch processing
        batch_buttons_frame = ttk.Frame(batch_frame)
        batch_buttons_frame.pack(fill=tk.X)

        def load_all_saved_asins():
            """Load all saved ASINs into batch input"""
            all_asins = load_saved_asins()
            if all_asins:
                batch_text_widget.delete("1.0", tk.END)
                batch_text_widget.insert("1.0", "\n".join(all_asins))
            else:
                messagebox.showinfo("Info", "No saved ASINs found.", parent=root)

        def load_selected_list():
            """Load ASINs from a selected list into batch input"""
            lists_data = load_all_asin_lists()
            if not lists_data:
                messagebox.showinfo("Info", "No ASIN lists found.", parent=root)
                return

            # Create a simple dialog to select list
            list_window = tk.Toplevel(root)
            list_window.title("Select List")
            list_window.transient(root)
            list_window.grab_set()

            # Enable resizing and set minimum size
            list_window.resizable(True, True)
            list_window.minsize(300, 180)

            # Center the list selection window with a reasonable default size
            list_window.update_idletasks()
            lw_width = 400
            lw_height = 250
            list_x = (list_window.winfo_screenwidth() // 2) - (lw_width // 2)
            list_y = (list_window.winfo_screenheight() // 2) - (lw_height // 2)
            list_window.geometry(f'{lw_width}x{lw_height}+{list_x}+{list_y}')

            ttk.Label(list_window, text="Select a list to load:").pack(pady=10)

            list_var = tk.StringVar(value=list(lists_data.keys())[0])
            list_combobox = ttk.Combobox(list_window, textvariable=list_var, values=list(lists_data.keys()), state="readonly")
            list_combobox.pack(pady=10)

            def load_list():
                selected_list = list_var.get()
                asins = lists_data[selected_list].get('asins', [])
                if asins:
                    batch_text_widget.delete("1.0", tk.END)
                    batch_text_widget.insert("1.0", "\n".join(asins))
                list_window.destroy()

            ttk.Button(list_window, text="Load", command=load_list).pack(pady=10)

        ttk.Button(batch_buttons_frame, text="Load All Saved ASINs", command=load_all_saved_asins).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(batch_buttons_frame, text="Load from List", command=load_selected_list).pack(side=tk.LEFT)

        # Days Input
        ttk.Label(main_frame, text="Days to analyze:", font=("Arial", 10)).grid(row=5, column=0, sticky=tk.W, pady=5)
        days_entry = ttk.Entry(main_frame, textvariable=days_var, width=30)
        days_entry.grid(row=5, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))

        # Help text
        help_text = "Enter number of days to analyze (1-365)"
        help_label = ttk.Label(main_frame, text=help_text, font=("Arial", 8), foreground="gray")
        help_label.grid(row=6, column=0, columnspan=3, pady=(5, 10))

        # Export checkbox
        export_checkbox = ttk.Checkbutton(main_frame, text="Export results to CSV file", variable=export_var)
        export_checkbox.grid(row=7, column=0, columnspan=3, pady=(5, 20))

        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=8, column=0, columnspan=3, pady=(10, 0))

        # Submit and Cancel buttons
        submit_btn = ttk.Button(button_frame, text="Submit", command=submit_inputs, style="Accent.TButton")
        submit_btn.pack(side=tk.LEFT, padx=(0, 10))

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel_inputs)
        cancel_btn.pack(side=tk.LEFT)

        # Initialize UI modes
        update_asin_selection()
        update_batch_mode()

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
    
    def process_single_asin(self, asin, days):
        """
        Process a single ASIN and return results.

        Args:
            asin (str): The ASIN to analyze
            days (int): Number of days to analyze

        Returns:
            tuple: (result_dict, error_string) where result_dict contains all analysis data
                   or (None, error_string) if failed
        """
        self._debug_print(f"Processing ASIN: {asin}")

        # Fetch product data
        product_data = self.get_product_sales_rank(asin)

        if not product_data:
            return None, f"Failed to fetch product data for ASIN: {asin}"

        # Get product title
        product_title = product_data.get('title', 'Unknown')

        # Parse sales rank history
        sales_rank_df = self.parse_sales_rank_history(product_data)

        if sales_rank_df.empty:
            return None, f"No sales rank history found for ASIN: {asin}"

        # Calculate statistics
        stats = self.calculate_sales_rank_stats(sales_rank_df, days)

        # Build result dictionary
        result = {
            'asin': asin,
            'title': product_title,
            'category_name': self.selected_category_name,
            'category_id': self.selected_category_id,
            'days_analyzed': stats['days_analyzed'],
            'data_points': stats['data_points'],
            'rank_changes': stats['rank_changes'],
            'average_rank': stats['average_rank'],
            'min_rank': stats['min_rank'],
            'max_rank': stats['max_rank'],
            'sales_rank_df': sales_rank_df  # Include raw data for potential export
        }

        return result, None

    def process_and_display_results(self, asins, days, export_csv, parent_window=None, verbose=False):
        """
        Process ASIN(s) and display sales rank analysis results in a GUI window.
        Supports both single ASIN and batch processing.

        Args:
            asins (list): List of ASINs to analyze (single element for single mode)
            days (int): Number of days to analyze
            export_csv (bool): Whether to offer CSV export
            parent_window: Optional parent window for modal behavior
            verbose (bool): If True, enable debug output for this analysis
        """
        # Temporarily enable verbose mode if requested
        original_verbose = self.verbose
        if verbose:
            self.verbose = True

        all_results = []
        errors = []

        if len(asins) == 1:
            # Single ASIN processing
            self._debug_print(f"=" * 60)
            self._debug_print(f"Starting sales rank analysis for ASIN: {asins[0]}")
            self._debug_print(f"Days to analyze: {days}")
            self._debug_print(f"=" * 60)

            print(f"Fetching sales rank data for ASIN: {asins[0]}")
            result, error = self.process_single_asin(asins[0], days)

            if error:
                self._debug_print(f"process_and_display_results: {error}")
                self.verbose = original_verbose
                if parent_window:
                    messagebox.showerror("Error", error, parent=parent_window)
                else:
                    print(error)
                return

            all_results.append(result)
            self._debug_print(f"process_and_display_results: Stats calculated - data_points={result['data_points']}")
            self._debug_print(f"=" * 60)
        else:
            # Batch processing with progress tracking
            print(f"Processing {len(asins)} ASINs...")

            # Create progress window
            progress_window = tk.Toplevel(parent_window) if parent_window else tk.Tk()
            progress_window.title("Processing ASINs")
            progress_window.geometry("600x200")
            progress_window.lift()
            progress_window.attributes('-topmost', True)

            # Center the progress window
            progress_window.update_idletasks()
            progress_x = (progress_window.winfo_screenwidth() // 2) - (600 // 2)
            progress_y = (progress_window.winfo_screenheight() // 2) - (200 // 2)
            progress_window.geometry(f'600x200+{progress_x}+{progress_y}')

            progress_label = ttk.Label(progress_window, text="Processing ASINs...", font=("Arial", 12))
            progress_label.pack(pady=20)

            progress_bar = ttk.Progressbar(progress_window, length=300, mode='determinate')
            progress_bar.pack(pady=10)

            status_label = ttk.Label(progress_window, text="", font=("Arial", 10))
            status_label.pack(pady=10)

            progress_bar['maximum'] = len(asins)

            for i, asin in enumerate(asins):
                # Update progress
                progress_bar['value'] = i + 1
                status_label.config(text=f"Processing ASIN {i+1}/{len(asins)}: {asin}")
                progress_window.update()

                # Process ASIN
                result, error = self.process_single_asin(asin, days)
                if error:
                    errors.append(error)
                else:
                    all_results.append(result)

            progress_window.destroy()

            # Show summary
            if errors:
                print(f"Completed with {len(errors)} errors:")
                for error in errors:
                    print(f"  - {error}")
            else:
                print("All ASINs processed successfully!")

        # Restore original verbose setting
        self.verbose = original_verbose

        # Check if we have any results to display
        if not all_results:
            if parent_window:
                messagebox.showerror("Error", "No results to display. All ASINs failed to process.", parent=parent_window)
            else:
                print("No results to display. All ASINs failed to process.")
            return

        # Display results
        if len(asins) == 1:
            result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
            result_root.title(f'Sales Rank Analysis - {asins[0]}')
        else:
            result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
            result_root.title(f'Sales Rank Analysis - Batch Results ({len(all_results)} ASINs)')

        # CRITICAL: Set resizable BEFORE any geometry settings
        result_root.resizable(True, True)

        # Remove transient to allow independent window controls
        if parent_window:
            result_root.transient()  # Clear transient relationship

        # Make window very large - almost full screen for batch, smaller for single
        result_root.update_idletasks()
        screen_width = result_root.winfo_screenwidth()
        screen_height = result_root.winfo_screenheight()

        if len(asins) == 1:
            # Single ASIN: Use 70% of screen dimensions
            window_width = min(int(screen_width * 0.70), 1200)
            window_height = min(int(screen_height * 0.70), 900)
            result_root.minsize(700, 500)
        else:
            # Batch: Use 95% of screen dimensions
            window_width = int(screen_width * 0.95)
            window_height = int(screen_height * 0.90)
            result_root.minsize(1200, 800)

        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        result_root.geometry(f'{window_width}x{window_height}+{x}+{y}')

        # Show window on top initially
        result_root.lift()
        result_root.attributes('-topmost', True)
        result_root.after_idle(lambda: result_root.attributes('-topmost', False))

        # Force update to apply all settings
        result_root.update()

        # Create scrolled text widget
        text = scrolledtext.ScrolledText(result_root, wrap=tk.WORD, width=80, height=30)
        text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Generate output
        if len(asins) == 1:
            # Single ASIN output (original format)
            result = all_results[0]
            output_lines = [f'Sales Rank Analysis for ASIN: {result["asin"]}\n']
            output_lines.append('=' * 50)

            # Show the selected category
            if result['category_name']:
                output_lines.append(f'Category: {result["category_name"]}')
                if result['category_id']:
                    output_lines.append(f'Category ID: {result["category_id"]}')
                output_lines.append('')

            if result['data_points'] == 0:
                output_lines.append('No sales rank data available for the specified time period.')
            else:
                output_lines.append(f'Analysis Period: Last {result["days_analyzed"]} days')
                output_lines.append(f'Data Points: {result["data_points"]}')
                output_lines.append(f'Rank Changes: {result["rank_changes"]}')
                output_lines.append('')
                output_lines.append('Statistics:')
                output_lines.append(f'  Average Rank: {result["average_rank"]:.0f}' if result["average_rank"] else '  Average Rank: N/A')
                output_lines.append(f'  Best Rank: {result["min_rank"]}' if result["min_rank"] else '  Best Rank: N/A')
                output_lines.append(f'  Worst Rank: {result["max_rank"]}' if result["max_rank"] else '  Worst Rank: N/A')

                sales_rank_df = result['sales_rank_df']
                if not sales_rank_df.empty:
                    output_lines.append('')
                    output_lines.append('Recent Rank History (last 10 entries):')
                    recent_data = sales_rank_df.tail(10)
                    for _, row in recent_data.iterrows():
                        output_lines.append(f'  {row["datetime"].strftime("%Y-%m-%d %H:%M")}: Rank #{row["sales_rank"]}')

            output_lines.append('=' * 50)
        else:
            # Batch processing output
            output_lines = [f'Batch Sales Rank Analysis Results | Days Analyzed: {days} | ASINs Processed: {len(all_results)}/{len(asins)}\n']
            if errors:
                output_lines.append(f'Errors: {len(errors)} ASINs failed to process\n')

            for result in all_results:
                output_lines.append('=' * 70)
                output_lines.append(f'ASIN: {result["asin"]}')
                output_lines.append(f'Title: {result["title"][:80]}...' if len(result["title"]) > 80 else f'Title: {result["title"]}')
                if result['category_name']:
                    output_lines.append(f'Category: {result["category_name"]}')
                output_lines.append('=' * 70)

                if result['data_points'] == 0:
                    output_lines.append('  No sales rank data available for the specified time period.')
                else:
                    output_lines.append(f'  Analysis Period: Last {result["days_analyzed"]} days')
                    output_lines.append(f'  Data Points: {result["data_points"]}')
                    output_lines.append(f'  Average Rank: {result["average_rank"]:.0f}' if result["average_rank"] else '  Average Rank: N/A')
                    output_lines.append(f'  Best Rank: {result["min_rank"]}' if result["min_rank"] else '  Best Rank: N/A')
                    output_lines.append(f'  Worst Rank: {result["max_rank"]}' if result["max_rank"] else '  Worst Rank: N/A')
                output_lines.append('')

            if errors:
                output_lines.append('=' * 70)
                output_lines.append('ERRORS:')
                output_lines.append('=' * 70)
                for error in errors:
                    output_lines.append(f'  {error}')

        text.insert(tk.END, '\n'.join(output_lines))
        text.config(state=tk.DISABLED)

        # Handle CSV export if requested
        if export_csv and all_results:
            save_path = filedialog.asksaveasfilename(
                title='Save sales rank analysis as CSV',
                defaultextension='.csv',
                filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
                parent=result_root
            )
            if save_path:
                # Create DataFrame with summary results (without the raw DataFrames)
                export_data = []
                for r in all_results:
                    export_data.append({
                        'asin': r['asin'],
                        'title': r['title'],
                        'category_name': r['category_name'],
                        'category_id': r['category_id'],
                        'days_analyzed': r['days_analyzed'],
                        'data_points': r['data_points'],
                        'rank_changes': r['rank_changes'],
                        'average_rank': r['average_rank'],
                        'min_rank': r['min_rank'],
                        'max_rank': r['max_rank']
                    })
                df_results = pd.DataFrame(export_data)
                df_results.to_csv(save_path, index=False)

                # Show summary message
                if len(asins) == 1:
                    messagebox.showinfo('Export', f'Sales rank analysis saved to {save_path}', parent=result_root)
                else:
                    messagebox.showinfo('Export', f'Batch results saved to {save_path}\nProcessed {len(all_results)} ASINs with {len(errors)} errors', parent=result_root)
            else:
                messagebox.showinfo('Export', 'No file selected. Data not saved.', parent=result_root)

        # If parent_window exists, wait for window to close; otherwise run mainloop
        if parent_window:
            result_root.wait_window()
        else:
            result_root.mainloop()

