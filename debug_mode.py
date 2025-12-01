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
from datetime import datetime
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
        Allows user to select ASIN and which data to view (raw, processed, or both).
        
        Args:
            parent_window: Optional parent window for modal behavior
            
        Returns:
            tuple: (asin, show_raw, show_processed, export_raw, export_processed) or None if cancelled
        """
        mouse_x, mouse_y = pyautogui.position()
        
        # Create the main input window
        root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        root.title("Debug Mode - Buybox Analyzer")
        root.geometry(f'600x550+{mouse_x}+{mouse_y}')
        root.lift()
        root.attributes('-topmost', True)
        root.resizable(False, False)
        
        # Center the window on screen
        root.update_idletasks()
        x = (root.winfo_screenwidth() // 2) - (600 // 2)
        y = (root.winfo_screenheight() // 2) - (550 // 2)
        root.geometry(f'600x550+{x}+{y}')
        
        # Variables to store input values
        asin_var = tk.StringVar()
        asin_input_mode = tk.StringVar(value="manual")  # "manual" or "select"
        
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
            
            return (
                asin,
                show_raw_var.get(),
                show_processed_var.get(),
                export_raw_var.get(),
                export_processed_var.get()
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
        
        # ASIN Input Mode Selection
        ttk.Label(main_frame, text="ASIN Input Mode:", font=("Arial", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        
        mode_frame = ttk.Frame(main_frame)
        mode_frame.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        manual_radio = ttk.Radiobutton(mode_frame, text="Manual Input", variable=asin_input_mode, value="manual", command=update_asin_selection)
        manual_radio.pack(side=tk.LEFT, padx=(0, 10))
        
        select_radio = ttk.Radiobutton(mode_frame, text="Select from List", variable=asin_input_mode, value="select", command=update_asin_selection)
        select_radio.pack(side=tk.LEFT)
        
        # ASIN Input
        ttk.Label(main_frame, text="ASIN:", font=("Arial", 10)).grid(row=3, column=0, sticky=tk.W, pady=5)
        
        # Create a frame to hold the ASIN input widgets
        asin_input_frame = ttk.Frame(main_frame)
        asin_input_frame.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # Manual entry
        asin_entry = ttk.Entry(asin_input_frame, textvariable=asin_var, width=30)
        asin_entry.pack(fill=tk.X, expand=True)
        
        # Combobox for selection from saved ASINs
        saved_asins = load_saved_asins()
        asin_combobox = ttk.Combobox(asin_input_frame, textvariable=asin_var, values=list(saved_asins), state="disabled", width=30)
        asin_combobox.pack(fill=tk.X, expand=True)
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)
        
        # Data View Options Frame
        view_options_frame = ttk.LabelFrame(main_frame, text="Data to View", padding="10")
        view_options_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
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
        ttk.Separator(main_frame, orient='horizontal').grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=15)
        
        # Export Options Frame
        export_options_frame = ttk.LabelFrame(main_frame, text="Export Options", padding="10")
        export_options_frame.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
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
        button_frame.grid(row=8, column=0, columnspan=2, pady=(20, 0))
        
        # Submit and Cancel buttons
        submit_btn = ttk.Button(button_frame, text="Run Debug Analysis", command=submit_inputs, style="Accent.TButton")
        submit_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel_inputs)
        cancel_btn.pack(side=tk.LEFT)
        
        # Initialize UI modes
        update_asin_selection()
        
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
        mouse_x, mouse_y = pyautogui.position()
        
        # Create the results window
        result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        result_root.geometry(f'1050x750+{mouse_x}+{mouse_y}')
        result_root.title(f'Debug View - ASIN: {asin}')
        result_root.lift()
        result_root.attributes('-topmost', True)
        
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
    
    def run_debug_analysis(self, parent_window=None):
        """
        Main method to run the debug analysis flow.
        Gets user input, fetches data, and displays results.
        
        Args:
            parent_window: Optional parent window for modal behavior
            
        Returns:
            bool: True if analysis completed, False if cancelled or error
        """
        # Get user input (ASIN and display options)
        user_input = self.get_user_input(parent_window=parent_window)
        
        if user_input is None:
            # User cancelled
            return False
        
        asin, show_raw, show_processed, export_raw, export_processed = user_input
        
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
            
            ttk.Label(loading_window, text=f"Fetching data for ASIN: {asin}...", font=("Arial", 10)).pack(expand=True)
            loading_window.update()
        
        # Fetch the buybox data
        raw_data, processed_data, error = self.fetch_buybox_data(asin)
        
        # Close loading window
        if loading_window:
            loading_window.destroy()
        
        # Check for errors
        if error:
            messagebox.showerror("Debug Mode Error", f"Failed to fetch data:\n\n{error}", parent=parent_window)
            return False
        
        # Display the results
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



