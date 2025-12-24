"""
Debug Mode Module
This module provides debugging functionality for the Keepa API Tracker application.
It allows users to view raw API responses and processed data to verify accuracy.

The DebugViewer class follows the Single Responsibility Principle by focusing
solely on capturing, displaying, and exporting debug information.
"""

import os
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from datetime import datetime, timedelta
import pyautogui
import requests
import pandas as pd
from asin_manager import (
    load_saved_asins, load_all_asin_lists, validate_asin, validate_asin_list
)


# Amazon's seller ID constant (used for identifying Amazon as buybox owner)
AMAZON_SELLER_ID = 'ATVPDKIKX0DER'


class DebugViewer:
    """
    A class to handle debug mode functionality for the Keepa API Tracker.
    
    This class captures raw API responses and processed data, then displays
    them in a user-friendly interface for verification and debugging.
    
    Attributes:
        api_key (str): The Keepa API key for authentication
        keepa_epoch (datetime): Keepa's epoch date for timestamp conversion
        raw_api_data (dict): Stores the raw API response
        processed_data (dict): Stores the processed/transformed data
    """
    
    def __init__(self, api_key):
        """
        Initialize the DebugViewer with the Keepa API key.
        
        Args:
            api_key (str): The Keepa API key for authentication
        """
        self.api_key = api_key
        self.keepa_epoch = datetime(2011, 1, 1)  # Keepa's epoch date
        self.raw_api_data = None  # Will store the raw API response
        self.processed_data = None  # Will store the processed data
    
    def fetch_sales_rank_data(self, asin, days=60):
        """
        Fetch sales rank data from Keepa API for a single ASIN.
        Stores both raw and processed data for debugging.
        
        This method is specifically designed to help troubleshoot issues
        where sales rank analysis returns "no results available".
        
        Args:
            asin (str): The Amazon ASIN to fetch data for
            days (int): Number of days to analyze (for filtering)
            
        Returns:
            tuple: (raw_data, processed_data, error_message)
                   Returns (None, None, error_string) if an error occurs
        """
        # Build the API request URL and parameters
        url = 'https://api.keepa.com/product'
        params = {
            'key': self.api_key,
            'domain': 1,  # Amazon.com
            'asin': asin,
            'history': 1,  # Request historical data including sales rank
            'stats': 1     # Request statistics
        }
        
        try:
            # Make the API request
            response = requests.get(url, params=params)
            
            # Store the raw API response
            self.raw_api_data = {
                'request_url': url,
                'request_params': {k: v for k, v in params.items() if k != 'key'},
                'response_status_code': response.status_code,
                'response_data': response.json(),
                'timestamp': datetime.now().isoformat()
            }
            
            data = response.json()
            
            # Check if we got valid product data
            if not data.get('products'):
                return self.raw_api_data, None, f"No product data found for ASIN {asin}"
            
            product = data['products'][0]
            
            # Get sales rank data from different possible sources
            # 1. salesRanks field (contains category-specific ranks)
            sales_ranks_field = product.get('salesRanks', {})
            
            # 2. csv field index 3 (main sales rank history)
            # Keepa CSV format: [timestamp1, value1, timestamp2, value2, ...]
            csv_data = product.get('csv', [])
            csv_sales_rank = csv_data[3] if len(csv_data) > 3 else None
            
            # Process the sales rank data from both sources
            processed_records = {
                'salesRanks_categories': {},
                'csv_sales_rank': [],
                'category_info': {},
                'date_range_analysis': {}
            }
            
            # Get category info if available
            category_tree = product.get('categoryTree', [])
            if category_tree:
                processed_records['category_info'] = {
                    'main_category': category_tree[0] if category_tree else 'Unknown',
                    'full_tree': category_tree
                }
            
            # Process salesRanks field (multiple categories)
            cutoff_date = datetime.now() - timedelta(days=days)
            
            for category_id, rank_data in sales_ranks_field.items():
                if isinstance(rank_data, list) and len(rank_data) >= 2:
                    category_records = []
                    records_in_period = 0
                    records_total = 0
                    min_date = None
                    max_date = None
                    
                    for i in range(0, len(rank_data), 2):
                        if i + 1 < len(rank_data):
                            try:
                                minutes = int(rank_data[i])
                                rank = rank_data[i + 1]
                                dt = self.keepa_epoch + timedelta(minutes=minutes)
                                
                                # Track date range
                                if min_date is None or dt < min_date:
                                    min_date = dt
                                if max_date is None or dt > max_date:
                                    max_date = dt
                                
                                if rank != -1:  # -1 means no data
                                    records_total += 1
                                    if dt >= cutoff_date:
                                        records_in_period += 1
                                        category_records.append({
                                            'datetime': dt.isoformat(),
                                            'sales_rank': rank
                                        })
                            except (ValueError, TypeError):
                                continue
                    
                    processed_records['salesRanks_categories'][category_id] = {
                        'total_records': records_total,
                        'records_in_period': records_in_period,
                        'date_range': {
                            'earliest': min_date.isoformat() if min_date else None,
                            'latest': max_date.isoformat() if max_date else None
                        },
                        'sample_records': category_records[:10],  # First 10 for display
                        'recent_records': category_records[-10:]  # Last 10 for display
                    }
            
            # Process csv sales rank (index 3)
            if csv_sales_rank and isinstance(csv_sales_rank, list):
                csv_records = []
                csv_in_period = 0
                csv_total = 0
                csv_min_date = None
                csv_max_date = None
                
                for i in range(0, len(csv_sales_rank), 2):
                    if i + 1 < len(csv_sales_rank):
                        try:
                            minutes = int(csv_sales_rank[i])
                            rank = csv_sales_rank[i + 1]
                            dt = self.keepa_epoch + timedelta(minutes=minutes)
                            
                            if csv_min_date is None or dt < csv_min_date:
                                csv_min_date = dt
                            if csv_max_date is None or dt > csv_max_date:
                                csv_max_date = dt
                            
                            if rank != -1:
                                csv_total += 1
                                if dt >= cutoff_date:
                                    csv_in_period += 1
                                    csv_records.append({
                                        'datetime': dt.isoformat(),
                                        'sales_rank': rank
                                    })
                        except (ValueError, TypeError):
                            continue
                
                processed_records['csv_sales_rank'] = {
                    'total_records': csv_total,
                    'records_in_period': csv_in_period,
                    'date_range': {
                        'earliest': csv_min_date.isoformat() if csv_min_date else None,
                        'latest': csv_max_date.isoformat() if csv_max_date else None
                    },
                    'sample_records': csv_records[:10],
                    'recent_records': csv_records[-10:]
                }
            
            # Add date range analysis summary
            processed_records['date_range_analysis'] = {
                'requested_days': days,
                'cutoff_date': cutoff_date.isoformat(),
                'current_date': datetime.now().isoformat()
            }
            
            # Store the processed data
            self.processed_data = {
                'asin': asin,
                'product_title': product.get('title', 'N/A'),
                'sales_rank_data': processed_records,
                'processing_timestamp': datetime.now().isoformat()
            }
            
            return self.raw_api_data, self.processed_data, None
            
        except requests.exceptions.RequestException as e:
            return None, None, f"API request failed: {str(e)}"
        except json.JSONDecodeError as e:
            return None, None, f"Failed to parse API response: {str(e)}"
        except Exception as e:
            return None, None, f"Unexpected error: {str(e)}"
    
    def fetch_buybox_data(self, asin):
        """
        Fetch buybox data from Keepa API for a single ASIN.
        Stores both raw and processed data for debugging.
        
        Args:
            asin (str): The Amazon ASIN to fetch data for
            
        Returns:
            tuple: (raw_data, processed_data, error_message)
                   Returns (None, None, error_string) if an error occurs
        """
        # Build the API request URL and parameters
        url = 'https://api.keepa.com/product'
        params = {
            'key': self.api_key,
            'domain': 1,  # Amazon.com
            'asin': asin,
            'buybox': 1  # Request buybox history
        }
        
        try:
            # Make the API request
            response = requests.get(url, params=params)
            
            # Store the raw API response
            self.raw_api_data = {
                'request_url': url,
                'request_params': {k: v for k, v in params.items() if k != 'key'},  # Don't store API key
                'response_status_code': response.status_code,
                'response_data': response.json(),
                'timestamp': datetime.now().isoformat()
            }
            
            data = response.json()
            
            # Check if we got valid product data
            if not data.get('products'):
                return self.raw_api_data, None, f"No product data found for ASIN {asin}"
            
            product = data['products'][0]
            buybox_history = product.get('buyBoxSellerIdHistory')
            
            if not buybox_history:
                return self.raw_api_data, None, f"No buybox history available for ASIN {asin}"
            
            # Process the buybox history into a more readable format
            # buyBoxSellerIdHistory: [timestamp1, sellerId1, timestamp2, sellerId2, ...]
            processed_records = []
            for i in range(0, len(buybox_history), 2):
                if i + 1 < len(buybox_history):
                    # Convert Keepa minutes to datetime
                    minutes = int(buybox_history[i])
                    seller_id = buybox_history[i + 1]
                    dt = self.keepa_epoch + pd.Timedelta(minutes=minutes)
                    
                    # Determine if this is Amazon or a third party seller
                    is_amazon = seller_id == AMAZON_SELLER_ID
                    owner_type = "Amazon" if is_amazon else "3rd Party"
                    
                    processed_records.append({
                        'timestamp_keepa_minutes': minutes,
                        'datetime': dt.isoformat(),
                        'seller_id': seller_id,
                        'owner_type': owner_type
                    })
            
            # Store the processed data
            self.processed_data = {
                'asin': asin,
                'product_title': product.get('title', 'N/A'),
                'total_records': len(processed_records),
                'buybox_history': processed_records,
                'processing_timestamp': datetime.now().isoformat()
            }
            
            return self.raw_api_data, self.processed_data, None
            
        except requests.exceptions.RequestException as e:
            return None, None, f"API request failed: {str(e)}"
        except json.JSONDecodeError as e:
            return None, None, f"Failed to parse API response: {str(e)}"
        except Exception as e:
            return None, None, f"Unexpected error: {str(e)}"
    
    def get_user_input(self, parent_window=None):
        """
        Creates an input window for debug mode settings.
        Allows user to select ASIN, debug type (Buybox or Sales Rank),
        and which data to view (raw, processed, or both).
        
        Args:
            parent_window: Optional parent window for modal behavior
            
        Returns:
            tuple: (asin, debug_type, show_raw, show_processed, export_raw, export_processed, days)
                   or None if cancelled
                   debug_type: "buybox" or "sales_rank"
                   days: only used for sales_rank (number of days to analyze)
        """
        # Create the main input window
        root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        root.title("Debug Mode")
        
        # IMPORTANT: Enable resizing so user can expand the window if needed
        root.resizable(True, True)
        
        # Set minimum size to ensure UI elements are visible
        root.minsize(600, 650)
        
        # Center the window on screen with a larger default size
        root.update_idletasks()
        window_width = 700
        window_height = 750
        x = (root.winfo_screenwidth() // 2) - (window_width // 2)
        y = (root.winfo_screenheight() // 2) - (window_height // 2)
        root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        # Show window on top initially
        root.lift()
        root.attributes('-topmost', True)
        root.after_idle(lambda: root.attributes('-topmost', False))
        
        # Variables to store input values
        asin_var = tk.StringVar()
        asin_input_mode = tk.StringVar(value="manual")  # "manual" or "select"
        debug_type_var = tk.StringVar(value="buybox")  # "buybox" or "sales_rank"
        days_var = tk.StringVar(value="60")  # Days for sales rank analysis
        
        # Debug output options (checkboxes)
        show_raw_var = tk.BooleanVar(value=True)
        show_processed_var = tk.BooleanVar(value=True)
        export_raw_var = tk.BooleanVar(value=False)
        export_processed_var = tk.BooleanVar(value=False)
        
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
        
        def update_debug_type_options():
            """Show/hide days input based on debug type selection"""
            if debug_type_var.get() == "sales_rank":
                days_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
            else:
                days_frame.grid_remove()
        
        def validate_inputs():
            """Validates all inputs and returns settings tuple or None if invalid"""
            # Get ASIN based on input mode
            if asin_input_mode.get() == "select":
                asin = asin_var.get().strip()
                if not asin:
                    messagebox.showerror('Validation Error', 'Please select an ASIN from the list.', parent=root)
                    return None
            else:
                asin = asin_var.get().strip().upper()
                if not validate_asin(asin):
                    messagebox.showerror('Validation Error', 'ASIN must be exactly 10 alphanumeric characters.', parent=root)
                    return None
            
            # Check that at least one view option is selected
            if not show_raw_var.get() and not show_processed_var.get():
                messagebox.showerror('Validation Error', 'Please select at least one data view option (Raw API or Processed Data).', parent=root)
                return None
            
            # Validate days if sales rank is selected
            days = 60  # Default
            if debug_type_var.get() == "sales_rank":
                try:
                    days = int(days_var.get().strip())
                    if days < 1 or days > 365:
                        messagebox.showerror('Validation Error', 'Days must be between 1 and 365.', parent=root)
                        return None
                except ValueError:
                    messagebox.showerror('Validation Error', 'Days must be a valid number.', parent=root)
                    return None
            
            return (
                asin,
                debug_type_var.get(),  # "buybox" or "sales_rank"
                show_raw_var.get(),
                show_processed_var.get(),
                export_raw_var.get(),
                export_processed_var.get(),
                days
            )
        
        def submit_inputs():
            """Handles form submission and validation"""
            result = validate_inputs()
            if result:
                result_var[0] = result
                root.destroy()
        
        def cancel_inputs():
            """Handles cancellation"""
            root.destroy()
        
        # Create the form layout with generous padding for readability
        main_frame = ttk.Frame(root, padding="30")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Debug Mode", font=("Arial", 18, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 5))
        
        # Subtitle explaining what debug mode does
        subtitle_label = ttk.Label(
            main_frame, 
            text="View raw API data and processed results for verification",
            font=("Arial", 9),
            foreground="gray"
        )
        subtitle_label.grid(row=1, column=0, columnspan=2, pady=(0, 20))
        
        # ===== Debug Type Selection =====
        debug_type_frame = ttk.LabelFrame(main_frame, text="Debug Type", padding="10")
        debug_type_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        buybox_radio = ttk.Radiobutton(
            debug_type_frame, 
            text="Buybox Analyzer - Debug buybox ownership data", 
            variable=debug_type_var, 
            value="buybox",
            command=update_debug_type_options
        )
        buybox_radio.pack(anchor=tk.W, pady=2)
        
        sales_rank_radio = ttk.Radiobutton(
            debug_type_frame, 
            text="Sales Rank Analyzer - Debug sales rank history data", 
            variable=debug_type_var, 
            value="sales_rank",
            command=update_debug_type_options
        )
        sales_rank_radio.pack(anchor=tk.W, pady=2)
        
        # ===== ASIN Input Mode Selection =====
        ttk.Label(main_frame, text="ASIN Input Mode:", font=("Arial", 10)).grid(row=3, column=0, sticky=tk.W, pady=5)
        
        mode_frame = ttk.Frame(main_frame)
        mode_frame.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        manual_radio = ttk.Radiobutton(mode_frame, text="Manual Input", variable=asin_input_mode, value="manual", command=update_asin_selection)
        manual_radio.pack(side=tk.LEFT, padx=(0, 10))
        
        select_radio = ttk.Radiobutton(mode_frame, text="Select from List", variable=asin_input_mode, value="select", command=update_asin_selection)
        select_radio.pack(side=tk.LEFT)
        
        # ASIN Input
        ttk.Label(main_frame, text="ASIN:", font=("Arial", 10)).grid(row=4, column=0, sticky=tk.W, pady=5)
        
        # Create a frame to hold the ASIN input widgets
        asin_input_frame = ttk.Frame(main_frame)
        asin_input_frame.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Manual entry
        asin_entry = ttk.Entry(asin_input_frame, textvariable=asin_var, width=30)
        asin_entry.pack(fill=tk.X, expand=True)
        
        # Combobox for selection from saved ASINs
        saved_asins = load_saved_asins()
        asin_combobox = ttk.Combobox(asin_input_frame, textvariable=asin_var, values=list(saved_asins), state="disabled", width=30)
        asin_combobox.pack(fill=tk.X, expand=True)
        
        # ===== Days Input (for Sales Rank only) =====
        days_frame = ttk.Frame(main_frame)
        days_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(days_frame, text="Days to analyze:", font=("Arial", 10)).pack(side=tk.LEFT)
        days_entry = ttk.Entry(days_frame, textvariable=days_var, width=10)
        days_entry.pack(side=tk.LEFT, padx=(10, 5))
        ttk.Label(days_frame, text="(1-365)", font=("Arial", 9), foreground="gray").pack(side=tk.LEFT)
        
        # Initially hide days frame (only shown for sales rank)
        days_frame.grid_remove()
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)
        
        # Data View Options Frame
        view_options_frame = ttk.LabelFrame(main_frame, text="Data to View", padding="10")
        view_options_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Checkboxes for what data to display
        raw_checkbox = ttk.Checkbutton(
            view_options_frame, 
            text="Show Raw API Response (data received from Keepa)", 
            variable=show_raw_var
        )
        raw_checkbox.pack(anchor=tk.W, pady=2)
        
        processed_checkbox = ttk.Checkbutton(
            view_options_frame, 
            text="Show Processed Data (data used for calculations)", 
            variable=show_processed_var
        )
        processed_checkbox.pack(anchor=tk.W, pady=2)
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=8, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)
        
        # Export Options Frame
        export_options_frame = ttk.LabelFrame(main_frame, text="Export Options", padding="10")
        export_options_frame.grid(row=9, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        # Checkboxes for export options
        export_raw_checkbox = ttk.Checkbutton(
            export_options_frame, 
            text="Export Raw API Response to JSON file", 
            variable=export_raw_var
        )
        export_raw_checkbox.pack(anchor=tk.W, pady=2)
        
        export_processed_checkbox = ttk.Checkbutton(
            export_options_frame, 
            text="Export Processed Data to JSON file", 
            variable=export_processed_var
        )
        export_processed_checkbox.pack(anchor=tk.W, pady=2)
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=10, column=0, columnspan=2, pady=(20, 0))
        
        # Submit and Cancel buttons
        submit_btn = ttk.Button(button_frame, text="Run Debug Analysis", command=submit_inputs, style="Accent.TButton")
        submit_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel_inputs)
        cancel_btn.pack(side=tk.LEFT)
        
        # Initialize UI modes
        update_asin_selection()
        update_debug_type_options()
        
        # Set focus to first entry and bind Enter key
        asin_entry.focus()
        root.bind('<Return>', lambda e: submit_inputs())
        root.bind('<Escape>', lambda e: cancel_inputs())
        
        # Start the GUI event loop
        if not parent_window:
            root.mainloop()
        else:
            root.wait_window()
        
        # Return the stored result
        return result_var[0]
    
    def display_debug_results(self, asin, raw_data, processed_data, show_raw, show_processed, export_raw, export_processed, parent_window=None):
        """
        Display debug results in a GUI window with tabs for raw and processed data.
        
        Args:
            asin (str): The ASIN that was analyzed
            raw_data (dict): The raw API response data
            processed_data (dict): The processed/transformed data
            show_raw (bool): Whether to show the raw API data tab
            show_processed (bool): Whether to show the processed data tab
            export_raw (bool): Whether to export raw data to file
            export_processed (bool): Whether to export processed data to file
            parent_window: Optional parent window for modal behavior
        """
        # Create the results window
        result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        result_root.title(f'Debug View - ASIN: {asin}')
        
        # IMPORTANT: Enable resizing so user can expand the window
        result_root.resizable(True, True)
        
        # Set minimum size
        result_root.minsize(900, 700)
        
        # Center the window on screen with a large default size
        result_root.update_idletasks()
        screen_width = result_root.winfo_screenwidth()
        screen_height = result_root.winfo_screenheight()
        # Use 85% of screen dimensions with max limits
        window_width = min(int(screen_width * 0.85), 1600)
        window_height = min(int(screen_height * 0.85), 1000)
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        result_root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        # Show window on top initially
        result_root.lift()
        result_root.attributes('-topmost', True)
        result_root.after_idle(lambda: result_root.attributes('-topmost', False))
        
        # Create main frame with generous padding
        main_frame = ttk.Frame(result_root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text=f"Debug Analysis for ASIN: {asin}", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Create notebook (tabbed interface)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Tab 1: Raw API Data (if selected)
        if show_raw and raw_data:
            raw_frame = ttk.Frame(notebook, padding="15")
            notebook.add(raw_frame, text="Raw API Response")
            
            # Explanation label
            raw_info = ttk.Label(
                raw_frame, 
                text="This is the exact data received from the Keepa API. Use this to verify the API is returning expected data.",
                font=("Arial", 9),
                foreground="gray",
                wraplength=900
            )
            raw_info.pack(anchor=tk.W, pady=(0, 10))
            
            # Create scrolled text widget for raw data
            raw_text = scrolledtext.ScrolledText(raw_frame, wrap=tk.WORD, width=100, height=30, font=("Consolas", 9))
            raw_text.pack(fill=tk.BOTH, expand=True)
            
            # Format and display raw data as pretty JSON
            try:
                raw_json_str = json.dumps(raw_data, indent=2, default=str)
                raw_text.insert(tk.END, raw_json_str)
            except Exception as e:
                raw_text.insert(tk.END, f"Error formatting raw data: {str(e)}\n\n{str(raw_data)}")
            
            raw_text.config(state=tk.DISABLED)
        
        # Tab 2: Processed Data (if selected)
        if show_processed and processed_data:
            processed_frame = ttk.Frame(notebook, padding="15")
            notebook.add(processed_frame, text="Processed Data")
            
            # Explanation label
            processed_info = ttk.Label(
                processed_frame, 
                text="This is the transformed data used for buybox calculations. Timestamps are converted from Keepa format to readable dates.",
                font=("Arial", 9),
                foreground="gray",
                wraplength=900
            )
            processed_info.pack(anchor=tk.W, pady=(0, 10))
            
            # Create scrolled text widget for processed data
            processed_text = scrolledtext.ScrolledText(processed_frame, wrap=tk.WORD, width=100, height=30, font=("Consolas", 9))
            processed_text.pack(fill=tk.BOTH, expand=True)
            
            # Format and display processed data
            try:
                processed_json_str = json.dumps(processed_data, indent=2, default=str)
                processed_text.insert(tk.END, processed_json_str)
            except Exception as e:
                processed_text.insert(tk.END, f"Error formatting processed data: {str(e)}\n\n{str(processed_data)}")
            
            processed_text.config(state=tk.DISABLED)
        
        # Tab 3: Summary View (always shown)
        summary_frame = ttk.Frame(notebook, padding="15")
        notebook.add(summary_frame, text="Summary")
        
        summary_text = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, width=100, height=30, font=("Consolas", 10))
        summary_text.pack(fill=tk.BOTH, expand=True)
        
        # Generate summary
        summary_lines = []
        summary_lines.append("=" * 80)
        summary_lines.append(f"DEBUG SUMMARY FOR ASIN: {asin}")
        summary_lines.append("=" * 80)
        summary_lines.append("")
        
        if raw_data:
            summary_lines.append("RAW API DATA STATUS:")
            summary_lines.append(f"  - API Request Status Code: {raw_data.get('response_status_code', 'N/A')}")
            summary_lines.append(f"  - Timestamp: {raw_data.get('timestamp', 'N/A')}")
            
            response_data = raw_data.get('response_data', {})
            if response_data.get('products'):
                product = response_data['products'][0]
                summary_lines.append(f"  - Product Title: {product.get('title', 'N/A')}")
                buybox_history = product.get('buyBoxSellerIdHistory', [])
                summary_lines.append(f"  - Buybox History Entries (raw): {len(buybox_history)} values ({len(buybox_history) // 2} records)")
            summary_lines.append("")
        
        if processed_data:
            summary_lines.append("PROCESSED DATA STATUS:")
            summary_lines.append(f"  - Product Title: {processed_data.get('product_title', 'N/A')}")
            summary_lines.append(f"  - Total Processed Records: {processed_data.get('total_records', 0)}")
            summary_lines.append(f"  - Processing Timestamp: {processed_data.get('processing_timestamp', 'N/A')}")
            summary_lines.append("")
            
            # Count Amazon vs 3rd Party
            buybox_history = processed_data.get('buybox_history', [])
            amazon_count = sum(1 for record in buybox_history if record.get('owner_type') == 'Amazon')
            third_party_count = len(buybox_history) - amazon_count
            
            summary_lines.append("BUYBOX OWNERSHIP BREAKDOWN:")
            summary_lines.append(f"  - Amazon Records: {amazon_count}")
            summary_lines.append(f"  - 3rd Party Records: {third_party_count}")
            if buybox_history:
                amazon_percent = (amazon_count / len(buybox_history)) * 100
                summary_lines.append(f"  - Amazon Ownership (by count): {amazon_percent:.2f}%")
            summary_lines.append("")
            
            # Show first and last few records
            if buybox_history:
                summary_lines.append("FIRST 5 RECORDS (oldest):")
                for record in buybox_history[:5]:
                    summary_lines.append(f"  - {record['datetime']}: {record['owner_type']} ({record['seller_id']})")
                
                summary_lines.append("")
                summary_lines.append("LAST 5 RECORDS (most recent):")
                for record in buybox_history[-5:]:
                    summary_lines.append(f"  - {record['datetime']}: {record['owner_type']} ({record['seller_id']})")
        
        summary_lines.append("")
        summary_lines.append("=" * 80)
        
        summary_text.insert(tk.END, '\n'.join(summary_lines))
        summary_text.config(state=tk.DISABLED)
        
        # Handle exports
        if export_raw and raw_data:
            save_path = filedialog.asksaveasfilename(
                title='Save Raw API Response',
                defaultextension='.json',
                filetypes=[('JSON files', '*.json'), ('All files', '*.*')],
                initialfile=f'debug_raw_{asin}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                parent=result_root
            )
            if save_path:
                try:
                    with open(save_path, 'w') as f:
                        json.dump(raw_data, f, indent=2, default=str)
                    messagebox.showinfo('Export Success', f'Raw API data saved to:\n{save_path}', parent=result_root)
                except Exception as e:
                    messagebox.showerror('Export Error', f'Failed to save raw data: {str(e)}', parent=result_root)
        
        if export_processed and processed_data:
            save_path = filedialog.asksaveasfilename(
                title='Save Processed Data',
                defaultextension='.json',
                filetypes=[('JSON files', '*.json'), ('All files', '*.*')],
                initialfile=f'debug_processed_{asin}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                parent=result_root
            )
            if save_path:
                try:
                    with open(save_path, 'w') as f:
                        json.dump(processed_data, f, indent=2, default=str)
                    messagebox.showinfo('Export Success', f'Processed data saved to:\n{save_path}', parent=result_root)
                except Exception as e:
                    messagebox.showerror('Export Error', f'Failed to save processed data: {str(e)}', parent=result_root)
        
        # Close button at the bottom
        close_btn = ttk.Button(main_frame, text="Close", command=result_root.destroy)
        close_btn.pack(pady=(10, 0))
        
        # Wait for window to close
        if parent_window:
            result_root.wait_window()
        else:
            result_root.mainloop()
    
    def display_sales_rank_debug_results(self, asin, days, raw_data, processed_data, show_raw, show_processed, export_raw, export_processed, parent_window=None):
        """
        Display sales rank debug results in a GUI window with tabs for raw and processed data.
        
        This method shows detailed information about sales rank data to help troubleshoot
        issues where the sales rank analyzer returns "no results available".
        
        Args:
            asin (str): The ASIN that was analyzed
            days (int): Number of days that were analyzed
            raw_data (dict): The raw API response data
            processed_data (dict): The processed/transformed data
            show_raw (bool): Whether to show the raw API data tab
            show_processed (bool): Whether to show the processed data tab
            export_raw (bool): Whether to export raw data to file
            export_processed (bool): Whether to export processed data to file
            parent_window: Optional parent window for modal behavior
        """
        # Create the results window
        result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        result_root.title(f'Sales Rank Debug View - ASIN: {asin}')
        
        # IMPORTANT: Enable resizing so user can expand the window
        result_root.resizable(True, True)
        
        # Set minimum size
        result_root.minsize(900, 700)
        
        # Center the window on screen with a large default size
        result_root.update_idletasks()
        screen_width = result_root.winfo_screenwidth()
        screen_height = result_root.winfo_screenheight()
        # Use 85% of screen dimensions with max limits
        window_width = min(int(screen_width * 0.85), 1600)
        window_height = min(int(screen_height * 0.85), 1000)
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        result_root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        # Show window on top initially
        result_root.lift()
        result_root.attributes('-topmost', True)
        result_root.after_idle(lambda: result_root.attributes('-topmost', False))
        
        # Create main frame with generous padding
        main_frame = ttk.Frame(result_root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text=f"Sales Rank Debug Analysis for ASIN: {asin}", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Create notebook (tabbed interface)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Tab 1: Diagnostic Summary (always shown first for troubleshooting)
        diag_frame = ttk.Frame(notebook, padding="15")
        notebook.add(diag_frame, text="🔍 Diagnostic Summary")
        
        diag_text = scrolledtext.ScrolledText(diag_frame, wrap=tk.WORD, width=100, height=30, font=("Consolas", 10))
        diag_text.pack(fill=tk.BOTH, expand=True)
        
        # Generate diagnostic summary
        diag_lines = []
        diag_lines.append("=" * 90)
        diag_lines.append(f"SALES RANK DIAGNOSTIC SUMMARY FOR ASIN: {asin}")
        diag_lines.append(f"Requested Period: Last {days} days")
        diag_lines.append("=" * 90)
        diag_lines.append("")
        
        if processed_data:
            sr_data = processed_data.get('sales_rank_data', {})
            
            # Show date range analysis
            date_analysis = sr_data.get('date_range_analysis', {})
            diag_lines.append("📅 DATE RANGE ANALYSIS:")
            diag_lines.append(f"   Current Date: {date_analysis.get('current_date', 'N/A')}")
            diag_lines.append(f"   Cutoff Date (for {days} days): {date_analysis.get('cutoff_date', 'N/A')}")
            diag_lines.append("")
            
            # Check salesRanks field
            categories = sr_data.get('salesRanks_categories', {})
            diag_lines.append("📊 SALES RANK CATEGORIES (from salesRanks field):")
            if categories:
                for cat_id, cat_data in categories.items():
                    diag_lines.append(f"   Category ID: {cat_id}")
                    diag_lines.append(f"      Total Records (all time): {cat_data.get('total_records', 0)}")
                    diag_lines.append(f"      Records in Period ({days} days): {cat_data.get('records_in_period', 0)}")
                    date_range = cat_data.get('date_range', {})
                    diag_lines.append(f"      Data Range: {date_range.get('earliest', 'N/A')} to {date_range.get('latest', 'N/A')}")
                    
                    # Highlight the problem if no records in period
                    if cat_data.get('records_in_period', 0) == 0 and cat_data.get('total_records', 0) > 0:
                        diag_lines.append(f"      ⚠️  WARNING: Data exists but NONE within the last {days} days!")
                        diag_lines.append(f"      💡 TIP: Try increasing the 'Days to analyze' value")
                    diag_lines.append("")
            else:
                diag_lines.append("   ❌ No categories found in salesRanks field!")
                diag_lines.append("   This product may not have category-specific sales rank data.")
                diag_lines.append("")
            
            # Check csv sales rank (index 3)
            csv_sr = sr_data.get('csv_sales_rank', {})
            diag_lines.append("📈 MAIN SALES RANK (from csv[3] field):")
            if csv_sr:
                diag_lines.append(f"   Total Records (all time): {csv_sr.get('total_records', 0)}")
                diag_lines.append(f"   Records in Period ({days} days): {csv_sr.get('records_in_period', 0)}")
                date_range = csv_sr.get('date_range', {})
                diag_lines.append(f"   Data Range: {date_range.get('earliest', 'N/A')} to {date_range.get('latest', 'N/A')}")
                
                # Highlight the problem if no records in period
                if csv_sr.get('records_in_period', 0) == 0 and csv_sr.get('total_records', 0) > 0:
                    diag_lines.append(f"   ⚠️  WARNING: Data exists but NONE within the last {days} days!")
                    diag_lines.append(f"   💡 TIP: Try increasing the 'Days to analyze' value")
            else:
                diag_lines.append("   ❌ No main sales rank data found in csv field!")
            diag_lines.append("")
            
            # Category info
            cat_info = sr_data.get('category_info', {})
            if cat_info:
                diag_lines.append("📁 PRODUCT CATEGORY INFORMATION:")
                diag_lines.append(f"   Main Category: {cat_info.get('main_category', 'N/A')}")
                full_tree = cat_info.get('full_tree', [])
                if full_tree:
                    diag_lines.append(f"   Full Path: {' > '.join(str(c) for c in full_tree)}")
            diag_lines.append("")
            
            # Overall diagnosis
            diag_lines.append("=" * 90)
            diag_lines.append("🩺 DIAGNOSIS:")
            
            total_in_period = sum(c.get('records_in_period', 0) for c in categories.values())
            if csv_sr:
                total_in_period += csv_sr.get('records_in_period', 0)
            
            total_all_time = sum(c.get('total_records', 0) for c in categories.values())
            if csv_sr:
                total_all_time += csv_sr.get('total_records', 0)
            
            if total_in_period == 0 and total_all_time == 0:
                diag_lines.append("   ❌ NO SALES RANK DATA AVAILABLE")
                diag_lines.append("   This product has no sales rank history in the Keepa database.")
                diag_lines.append("   Possible reasons:")
                diag_lines.append("      - Product is too new")
                diag_lines.append("      - Product is not tracked by Keepa")
                diag_lines.append("      - Product is in a category without sales rank tracking")
            elif total_in_period == 0:
                diag_lines.append("   ⚠️  NO DATA WITHIN REQUESTED PERIOD")
                diag_lines.append(f"   Data exists ({total_all_time} records total) but none in the last {days} days.")
                diag_lines.append("")
                diag_lines.append("   🔧 SOLUTIONS:")
                diag_lines.append("      1. Increase the 'Days to analyze' value (try 90, 180, or 365)")
                diag_lines.append("      2. Check the data range above to see when data is available")
            else:
                diag_lines.append(f"   ✅ DATA AVAILABLE: {total_in_period} records in the last {days} days")
                diag_lines.append("   If you're still seeing 'no results', there may be a processing bug.")
            
            diag_lines.append("=" * 90)
        else:
            diag_lines.append("❌ NO PROCESSED DATA AVAILABLE")
            diag_lines.append("Failed to process the API response. Check the Raw API Response tab for details.")
        
        diag_text.insert(tk.END, '\n'.join(diag_lines))
        diag_text.config(state=tk.DISABLED)
        
        # Tab 2: Raw API Data (if selected)
        if show_raw and raw_data:
            raw_frame = ttk.Frame(notebook, padding="15")
            notebook.add(raw_frame, text="Raw API Response")
            
            # Explanation label
            raw_info = ttk.Label(
                raw_frame, 
                text="This is the exact data received from the Keepa API. Look for 'salesRanks' and 'csv' fields.",
                font=("Arial", 9),
                foreground="gray",
                wraplength=900
            )
            raw_info.pack(anchor=tk.W, pady=(0, 10))
            
            # Create scrolled text widget for raw data
            raw_text = scrolledtext.ScrolledText(raw_frame, wrap=tk.WORD, width=100, height=30, font=("Consolas", 9))
            raw_text.pack(fill=tk.BOTH, expand=True)
            
            # Format and display raw data as pretty JSON
            try:
                raw_json_str = json.dumps(raw_data, indent=2, default=str)
                raw_text.insert(tk.END, raw_json_str)
            except Exception as e:
                raw_text.insert(tk.END, f"Error formatting raw data: {str(e)}\n\n{str(raw_data)}")
            
            raw_text.config(state=tk.DISABLED)
        
        # Tab 3: Processed Data (if selected)
        if show_processed and processed_data:
            processed_frame = ttk.Frame(notebook, padding="15")
            notebook.add(processed_frame, text="Processed Data")
            
            # Explanation label
            processed_info = ttk.Label(
                processed_frame, 
                text="This shows how the raw data is transformed for analysis. Check records counts and date ranges.",
                font=("Arial", 9),
                foreground="gray",
                wraplength=900
            )
            processed_info.pack(anchor=tk.W, pady=(0, 10))
            
            # Create scrolled text widget for processed data
            processed_text = scrolledtext.ScrolledText(processed_frame, wrap=tk.WORD, width=100, height=30, font=("Consolas", 9))
            processed_text.pack(fill=tk.BOTH, expand=True)
            
            # Format and display processed data
            try:
                processed_json_str = json.dumps(processed_data, indent=2, default=str)
                processed_text.insert(tk.END, processed_json_str)
            except Exception as e:
                processed_text.insert(tk.END, f"Error formatting processed data: {str(e)}\n\n{str(processed_data)}")
            
            processed_text.config(state=tk.DISABLED)
        
        # Tab 4: Sample Data (shows actual rank values)
        if processed_data:
            sample_frame = ttk.Frame(notebook, padding="15")
            notebook.add(sample_frame, text="📋 Sample Data")
            
            sample_text = scrolledtext.ScrolledText(sample_frame, wrap=tk.WORD, width=100, height=30, font=("Consolas", 10))
            sample_text.pack(fill=tk.BOTH, expand=True)
            
            sample_lines = []
            sample_lines.append("SAMPLE SALES RANK DATA")
            sample_lines.append("=" * 70)
            sample_lines.append("")
            
            sr_data = processed_data.get('sales_rank_data', {})
            
            # Show sample from each category
            categories = sr_data.get('salesRanks_categories', {})
            for cat_id, cat_data in categories.items():
                sample_lines.append(f"Category {cat_id}:")
                sample_lines.append("-" * 50)
                
                recent = cat_data.get('recent_records', [])
                if recent:
                    sample_lines.append("Most Recent Records:")
                    for rec in recent:
                        sample_lines.append(f"   {rec['datetime']}: Rank #{rec['sales_rank']}")
                else:
                    sample_lines.append("   No records available in period")
                sample_lines.append("")
            
            # Show csv sales rank samples
            csv_sr = sr_data.get('csv_sales_rank', {})
            if csv_sr:
                sample_lines.append("Main Sales Rank (csv[3]):")
                sample_lines.append("-" * 50)
                
                recent = csv_sr.get('recent_records', [])
                if recent:
                    sample_lines.append("Most Recent Records:")
                    for rec in recent:
                        sample_lines.append(f"   {rec['datetime']}: Rank #{rec['sales_rank']}")
                else:
                    sample_lines.append("   No records available in period")
            
            sample_text.insert(tk.END, '\n'.join(sample_lines))
            sample_text.config(state=tk.DISABLED)
        
        # Handle exports
        if export_raw and raw_data:
            save_path = filedialog.asksaveasfilename(
                title='Save Raw API Response',
                defaultextension='.json',
                filetypes=[('JSON files', '*.json'), ('All files', '*.*')],
                initialfile=f'debug_salesrank_raw_{asin}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                parent=result_root
            )
            if save_path:
                try:
                    with open(save_path, 'w') as f:
                        json.dump(raw_data, f, indent=2, default=str)
                    messagebox.showinfo('Export Success', f'Raw API data saved to:\n{save_path}', parent=result_root)
                except Exception as e:
                    messagebox.showerror('Export Error', f'Failed to save raw data: {str(e)}', parent=result_root)
        
        if export_processed and processed_data:
            save_path = filedialog.asksaveasfilename(
                title='Save Processed Data',
                defaultextension='.json',
                filetypes=[('JSON files', '*.json'), ('All files', '*.*')],
                initialfile=f'debug_salesrank_processed_{asin}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json',
                parent=result_root
            )
            if save_path:
                try:
                    with open(save_path, 'w') as f:
                        json.dump(processed_data, f, indent=2, default=str)
                    messagebox.showinfo('Export Success', f'Processed data saved to:\n{save_path}', parent=result_root)
                except Exception as e:
                    messagebox.showerror('Export Error', f'Failed to save processed data: {str(e)}', parent=result_root)
        
        # Close button at the bottom
        close_btn = ttk.Button(main_frame, text="Close", command=result_root.destroy)
        close_btn.pack(pady=(10, 0))
        
        # Wait for window to close
        if parent_window:
            result_root.wait_window()
        else:
            result_root.mainloop()
    
    def run_debug_analysis(self, parent_window=None):
        """
        Main method to run the debug analysis flow.
        Gets user input, fetches data, and displays results.
        
        Supports both Buybox and Sales Rank debugging.
        
        Args:
            parent_window: Optional parent window for modal behavior
            
        Returns:
            bool: True if analysis completed, False if cancelled or error
        """
        # Get user input (ASIN, debug type, and display options)
        user_input = self.get_user_input(parent_window=parent_window)
        
        if user_input is None:
            # User cancelled
            return False
        
        # Unpack the user input
        # Format: (asin, debug_type, show_raw, show_processed, export_raw, export_processed, days)
        asin, debug_type, show_raw, show_processed, export_raw, export_processed, days = user_input
        
        # Show a "loading" message while fetching data
        loading_window = None
        if parent_window:
            loading_window = tk.Toplevel(parent_window)
            loading_window.title("Fetching Data...")
            loading_window.geometry("300x100")
            loading_window.transient(parent_window)
            
            # Center the loading window
            loading_window.update_idletasks()
            lx = (loading_window.winfo_screenwidth() // 2) - 150
            ly = (loading_window.winfo_screenheight() // 2) - 50
            loading_window.geometry(f'300x100+{lx}+{ly}')
            
            # Show appropriate loading message based on debug type
            data_type = "sales rank" if debug_type == "sales_rank" else "buybox"
            ttk.Label(loading_window, text=f"Fetching {data_type} data for ASIN: {asin}...", font=("Arial", 10)).pack(expand=True)
            loading_window.update()
        
        # Fetch data based on debug type
        if debug_type == "sales_rank":
            # Fetch sales rank data for debugging
            raw_data, processed_data, error = self.fetch_sales_rank_data(asin, days)
        else:
            # Fetch buybox data for debugging
            raw_data, processed_data, error = self.fetch_buybox_data(asin)
        
        # Close loading window
        if loading_window:
            loading_window.destroy()
        
        # Check for errors
        if error:
            messagebox.showerror("Debug Mode Error", f"Failed to fetch data:\n\n{error}", parent=parent_window)
            return False
        
        # Display the results based on debug type
        if debug_type == "sales_rank":
            # Display sales rank debug results
            self.display_sales_rank_debug_results(
                asin=asin,
                days=days,
                raw_data=raw_data,
                processed_data=processed_data,
                show_raw=show_raw,
                show_processed=show_processed,
                export_raw=export_raw,
                export_processed=export_processed,
                parent_window=parent_window
            )
        else:
            # Display buybox debug results
            self.display_debug_results(
                asin=asin,
                raw_data=raw_data,
                processed_data=processed_data,
                show_raw=show_raw,
                show_processed=show_processed,
                export_raw=export_raw,
                export_processed=export_processed,
                parent_window=parent_window
            )
        
        return True


def main():
    """
    Main function to run the debug mode standalone.
    This allows testing the debug functionality independently.
    """
    # Load API key from environment
    import os
    from dotenv import load_dotenv
    
    load_dotenv('.env.local')
    api_key = os.getenv('Keepa_API_KEY')
    
    if not api_key:
        print("Error: Keepa_API_KEY not found in .env.local file.")
        return
    
    print("Debug Mode - Buybox Analyzer")
    print("=" * 30)
    
    # Create and run debug viewer
    viewer = DebugViewer(api_key)
    viewer.run_debug_analysis()


if __name__ == "__main__":
    main()



