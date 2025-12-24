"""
Buybox Analyzer Module
This module provides functionality for analyzing Amazon buybox ownership data from Keepa API.
It follows the Single Responsibility Principle by focusing solely on buybox analysis.
"""

import requests
import pandas as pd
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext, simpledialog
import pyautogui
from asin_manager import (
    load_saved_asins, load_all_asin_lists, validate_asin, validate_asin_list,
    add_asins_to_saved_list, save_asin_lists
)


# Amazon's seller ID constant
AMAZON_SELLER_ID = 'ATVPDKIKX0DER'


class BuyboxAnalyzer:
    """
    A class to analyze buybox ownership data from Keepa API.
    This follows the Single Responsibility Principle by focusing only on buybox analysis.
    """
    
    def __init__(self, api_key):
        """
        Initialize the analyzer with the Keepa API key.
        
        Args:
            api_key (str): The Keepa API key for authentication
        """
        self.api_key = api_key
        self.keepa_epoch = datetime(2011, 1, 1)  # Keepa's epoch date
    
    def get_current_buybox_owner(self, asin):
        """
        Get the current buybox owner for a single ASIN.

        Args:
            asin (str): The Amazon ASIN to analyze

        Returns:
            tuple: (result_dict, error) where result_dict contains current owner info or None if error
        """
        url = 'https://api.keepa.com/product'
        params = {
            'key': self.api_key,
            'domain': 1,  # Amazon.com
            'asin': asin,
            'buybox': 1
        }

        try:
            response = requests.get(url, params=params)
            data = response.json()

            if not data.get('products'):
                return None, f"No product data found for ASIN {asin}"

            product = data['products'][0]
            buybox_history = product.get('buyBoxSellerIdHistory')

            if not buybox_history or len(buybox_history) < 2:
                return None, f"No buybox history available for ASIN {asin}"

            # Get the most recent buybox owner (last entry in the history)
            # buyBoxSellerIdHistory: [timestamp1, sellerId1, timestamp2, sellerId2, ...]
            last_timestamp_minutes = int(buybox_history[-2])
            last_seller_id = buybox_history[-1]

            # Convert Keepa timestamp to datetime
            last_updated = self.keepa_epoch + pd.Timedelta(minutes=last_timestamp_minutes)

            # Determine if owner is Amazon
            is_amazon = last_seller_id == AMAZON_SELLER_ID
            owner_type = "Amazon" if is_amazon else "3rd Party"

            # Get product title if available
            product_title = product.get('title', 'N/A')

            result = {
                'asin': asin,
                'current_owner_id': last_seller_id,
                'owner_type': owner_type,
                'last_updated': last_updated.strftime('%Y-%m-%d %H:%M:%S'),
                'product_title': product_title
            }

            return result, None

        except Exception as e:
            return None, f"Error fetching ASIN {asin}: {str(e)}"

    def process_single_asin(self, asin, year, months):
        """
        Process a single ASIN and return buybox analysis results.

        Args:
            asin (str): The Amazon ASIN to analyze
            year (int): The year to analyze
            months (list): List of month numbers (1-12) to analyze

        Returns:
            tuple: (results, error) where results is a list of dicts or None if error
        """
        # Fetch product data from Keepa
        url = 'https://api.keepa.com/product'
        params = {
            'key': self.api_key,
            'domain': 1,  # Amazon.com
            'asin': asin,
            'buybox': 1
        }
        
        try:
            response = requests.get(url, params=params)
            data = response.json()
            
            if not data.get('products'):
                return None, f"No product data found for ASIN {asin}"
            
            product = data['products'][0]
            buybox_history = product.get('buyBoxSellerIdHistory')
            
            if not buybox_history:
                return None, f"No buybox history available for ASIN {asin}"
            
            # buyBoxSellerIdHistory: [timestamp1, sellerId1, timestamp2, sellerId2, ...]
            # Timestamps are in Keepa minutes since Jan 1, 2011
            records = []
            for i in range(0, len(buybox_history), 2):
                minutes = int(buybox_history[i])
                seller_id = buybox_history[i+1]
                dt = self.keepa_epoch + pd.Timedelta(minutes=minutes)
                records.append({'datetime': dt, 'seller_id': seller_id})
            
            df = pd.DataFrame(records)
            df['year'] = df['datetime'].dt.year
            df['month'] = df['datetime'].dt.month
            
            # Filter for selected month/year
            results = []
            for month in months:
                month_df = df[(df['year'] == year) & (df['month'] == month)].sort_values('datetime').reset_index(drop=True)
                if month_df.empty or len(month_df) < 2:
                    results.append({
                        'asin': asin,
                        'month': month,
                        'amazon_percent_count': None,
                        'amazon_percent_time': None,
                        'total_count': 0,
                        'amazon_count': 0,
                        'amazon_time_minutes': None,
                        'total_time_minutes': None
                    })
                    continue
                
                # Count-based calculation
                amazon_count = (month_df['seller_id'] == AMAZON_SELLER_ID).sum()
                total_count = len(month_df)
                percent_count = (amazon_count / total_count) * 100
                
                # Time-based calculation
                amazon_time = 0
                total_time = 0
                for i in range(len(month_df) - 1):
                    t1 = month_df.loc[i, 'datetime']
                    t2 = month_df.loc[i + 1, 'datetime']
                    delta = (t2 - t1).total_seconds() / 60  # minutes
                    total_time += delta
                    if month_df.loc[i, 'seller_id'] == AMAZON_SELLER_ID:
                        amazon_time += delta
                
                percent_time = (amazon_time / total_time) * 100 if total_time > 0 else None
                results.append({
                    'asin': asin,
                    'month': month,
                    'amazon_percent_count': percent_count,
                    'amazon_percent_time': percent_time,
                    'total_count': total_count,
                    'amazon_count': amazon_count,
                    'amazon_time_minutes': amazon_time,
                    'total_time_minutes': total_time
                })
            
            return results, None
            
        except Exception as e:
            return None, f"Error processing ASIN {asin}: {str(e)}"
    
    def get_user_input(self, parent_window=None):
        """
        Creates a single consolidated input window for ASIN, year, and months.
        Returns tuple of (asins, year, months, export_preference) with all validation intact.
        
        Args:
            parent_window: Optional parent window for modal behavior
            
        Returns:
            tuple: (asins, year, months, export_preference) or None if cancelled
        """
        mouse_x, mouse_y = pyautogui.position()
        
        # Create the main input window
        root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        root.title("Buybox Analyzer - Input")
        root.geometry(f'500x500+{mouse_x}+{mouse_y}')
        root.lift()
        root.attributes('-topmost', True)
        root.resizable(False, False)
        
        # Center the window on screen
        root.update_idletasks()
        x = (root.winfo_screenwidth() // 2) - (600 // 2)
        y = (root.winfo_screenheight() // 2) - (600 // 2)
        root.geometry(f'600x600+{x}+{y}')
        
        # Variables to store input values
        asin_var = tk.StringVar()
        year_var = tk.StringVar()
        months_var = tk.StringVar()
        export_var = tk.BooleanVar()  # Checkbox for export preference
        asin_input_mode = tk.StringVar(value="manual")  # "manual" or "select"
        batch_mode_var = tk.BooleanVar()  # Checkbox for batch processing mode
        
        # Variable to store the result
        result_var = [None]  # Using list to store result (mutable)
        
        # ASIN Management Functions
        def open_asin_manager():
            """Open ASIN management window"""
            manager_window = tk.Toplevel(root)
            manager_window.title("ASIN Manager")
            manager_window.geometry("800x600")
            manager_window.transient(root)
            manager_window.grab_set()
            
            # Load current ASIN lists
            lists_data = load_all_asin_lists()
            
            # Create main frame
            main_frame = ttk.Frame(manager_window, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Title
            ttk.Label(main_frame, text="ASIN Manager", font=("Arial", 16, "bold")).pack(pady=(0, 20))
            
            # Create notebook for tabs
            notebook = ttk.Notebook(main_frame)
            notebook.pack(fill=tk.BOTH, expand=True)
            
            # Add ASINs tab
            add_frame = ttk.Frame(notebook, padding="10")
            notebook.add(add_frame, text="Add ASINs")
            
            # List selection for adding ASINs
            list_selection_frame = ttk.Frame(add_frame)
            list_selection_frame.pack(fill=tk.X, pady=(0, 10))
            
            ttk.Label(list_selection_frame, text="Add to list:").pack(side=tk.LEFT)
            list_names = list(lists_data.keys()) if lists_data else ["Default List"]
            selected_list_var = tk.StringVar(value=list_names[0] if list_names else "Default List")
            list_combobox = ttk.Combobox(list_selection_frame, textvariable=selected_list_var, values=list_names, state="readonly", width=20)
            list_combobox.pack(side=tk.LEFT, padx=(10, 0))
            
            def create_new_list():
                """Create a new ASIN list"""
                new_name = simpledialog.askstring("New List", "Enter name for new list:", parent=manager_window)
                if new_name and new_name.strip():
                    new_name = new_name.strip()
                    if new_name in lists_data:
                        messagebox.showerror("Error", "List name already exists.", parent=manager_window)
                        return
                    
                    lists_data[new_name] = {'asins': [], 'description': ''}
                    if add_asins_to_saved_list([], new_name):
                        # Update combobox
                        list_names = list(load_all_asin_lists().keys())
                        list_combobox['values'] = list_names
                        selected_list_var.set(new_name)
                        messagebox.showinfo("Success", f"Created new list: {new_name}", parent=manager_window)
                        refresh_all_lists()
                    else:
                        messagebox.showerror("Error", "Failed to create new list.", parent=manager_window)
            
            ttk.Button(list_selection_frame, text="New List", command=create_new_list).pack(side=tk.LEFT, padx=(10, 0))
            
            # Add ASINs section
            add_asins_frame = ttk.LabelFrame(add_frame, text="Add New ASINs", padding="10")
            add_asins_frame.pack(fill=tk.X, pady=(10, 0))
            
            ttk.Label(add_asins_frame, text="Paste ASINs (comma, space, or newline separated):").pack(anchor=tk.W)
            
            asin_text = tk.Text(add_asins_frame, height=6, width=70)
            asin_text.pack(fill=tk.X, pady=(5, 10))
            
            def add_asins():
                """Add ASINs from text input"""
                text_content = asin_text.get("1.0", tk.END).strip()
                valid_asins, error_msg = validate_asin_list(text_content)
                
                if error_msg:
                    messagebox.showerror("Validation Error", error_msg, parent=manager_window)
                    return
                
                if not valid_asins:
                    messagebox.showwarning("No ASINs", "No valid ASINs found in input.", parent=manager_window)
                    return
                
                selected_list = selected_list_var.get()
                total_asins, new_asins = add_asins_to_saved_list(valid_asins, selected_list)
                messagebox.showinfo("Success", f"Added {new_asins} new ASINs to '{selected_list}'. Total in list: {total_asins}", parent=manager_window)
                
                # Refresh all lists and update combobox
                refresh_all_lists()
                asin_text.delete("1.0", tk.END)
            
            ttk.Button(add_asins_frame, text="Add ASINs", command=add_asins).pack(pady=(0, 10))
            
            # Manage Lists tab
            manage_frame = ttk.Frame(notebook, padding="10")
            notebook.add(manage_frame, text="Manage Lists")
            
            # Lists overview
            lists_frame = ttk.LabelFrame(manage_frame, text="ASIN Lists", padding="10")
            lists_frame.pack(fill=tk.BOTH, expand=True)
            
            # Create treeview for lists
            columns = ('List Name', 'ASIN Count', 'Description')
            lists_tree = ttk.Treeview(lists_frame, columns=columns, show='headings', height=15)
            
            for col in columns:
                lists_tree.heading(col, text=col)
                lists_tree.column(col, width=150)
            
            lists_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Scrollbar for treeview
            tree_scrollbar = ttk.Scrollbar(lists_frame, orient=tk.VERTICAL, command=lists_tree.yview)
            lists_tree.configure(yscrollcommand=tree_scrollbar.set)
            tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            def refresh_lists_tree():
                """Refresh the lists treeview"""
                for item in lists_tree.get_children():
                    lists_tree.delete(item)
                
                lists_data = load_all_asin_lists()
                for list_name, list_data in lists_data.items():
                    asin_count = len(list_data.get('asins', []))
                    description = list_data.get('description', '')
                    lists_tree.insert('', tk.END, values=(list_name, asin_count, description))
            
            def remove_selected_list():
                """Remove selected list"""
                selection = lists_tree.selection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a list to remove.", parent=manager_window)
                    return
                
                selected_item = lists_tree.item(selection[0])
                list_name = selected_item['values'][0]
                
                if messagebox.askyesno("Confirm", f"Are you sure you want to remove the list '{list_name}'?", parent=manager_window):
                    lists_data = load_all_asin_lists()
                    if list_name in lists_data:
                        del lists_data[list_name]
                        if save_asin_lists(lists_data):
                            messagebox.showinfo("Success", f"Removed list: {list_name}", parent=manager_window)
                            refresh_lists_tree()
                            refresh_all_lists()
                        else:
                            messagebox.showerror("Error", "Failed to remove list.", parent=manager_window)
            
            def clear_selected_list():
                """Clear ASINs from selected list"""
                selection = lists_tree.selection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a list to clear.", parent=manager_window)
                    return
                
                selected_item = lists_tree.item(selection[0])
                list_name = selected_item['values'][0]
                
                if messagebox.askyesno("Confirm", f"Are you sure you want to clear all ASINs from '{list_name}'?", parent=manager_window):
                    lists_data = load_all_asin_lists()
                    if list_name in lists_data:
                        lists_data[list_name]['asins'] = []
                        if save_asin_lists(lists_data):
                            messagebox.showinfo("Success", f"Cleared list: {list_name}", parent=manager_window)
                            refresh_lists_tree()
                            refresh_all_lists()
                        else:
                            messagebox.showerror("Error", "Failed to clear list.", parent=manager_window)
            
            # Buttons for list management
            list_buttons_frame = ttk.Frame(manage_frame)
            list_buttons_frame.pack(fill=tk.X, pady=(10, 0))
            
            ttk.Button(list_buttons_frame, text="Remove Selected List", command=remove_selected_list).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(list_buttons_frame, text="Clear Selected List", command=clear_selected_list).pack(side=tk.LEFT)
            
            # All ASINs tab
            all_asins_frame = ttk.Frame(notebook, padding="10")
            notebook.add(all_asins_frame, text="All ASINs")
            
            # ASIN listbox with scrollbar
            asin_listbox_frame = ttk.Frame(all_asins_frame)
            asin_listbox_frame.pack(fill=tk.BOTH, expand=True)
            
            asin_listbox = tk.Listbox(asin_listbox_frame, selectmode=tk.SINGLE, height=20)
            asin_scrollbar = ttk.Scrollbar(asin_listbox_frame, orient=tk.VERTICAL, command=asin_listbox.yview)
            asin_listbox.configure(yscrollcommand=asin_scrollbar.set)
            
            asin_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            asin_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            def refresh_asin_list():
                """Refresh the ASIN listbox"""
                asin_listbox.delete(0, tk.END)
                current_asins = load_saved_asins()
                for asin in sorted(current_asins):
                    asin_listbox.insert(tk.END, asin)
            
            def remove_selected_asin():
                """Remove selected ASIN from all lists"""
                selection = asin_listbox.curselection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select an ASIN to remove.", parent=manager_window)
                    return
                
                selected_asin = asin_listbox.get(selection[0])
                lists_data = load_all_asin_lists()
                
                # Remove ASIN from all lists
                removed_from = []
                for list_name, list_data in lists_data.items():
                    if selected_asin in list_data.get('asins', []):
                        list_data['asins'].remove(selected_asin)
                        removed_from.append(list_name)
                
                if removed_from:
                    if save_asin_lists(lists_data):
                        messagebox.showinfo("Success", f"Removed ASIN {selected_asin} from: {', '.join(removed_from)}", parent=manager_window)
                        refresh_asin_list()
                        refresh_lists_tree()
                    else:
                        messagebox.showerror("Error", "Failed to remove ASIN.", parent=manager_window)
            
            def clear_all_asins():
                """Clear all saved ASINs"""
                if messagebox.askyesno("Confirm", "Are you sure you want to remove all saved ASINs?", parent=manager_window):
                    if save_asin_lists({}):
                        messagebox.showinfo("Success", "All ASINs removed.", parent=manager_window)
                        refresh_asin_list()
                        refresh_lists_tree()
                    else:
                        messagebox.showerror("Error", "Failed to clear ASINs.", parent=manager_window)
            
            # Buttons for ASIN management
            asin_buttons_frame = ttk.Frame(all_asins_frame)
            asin_buttons_frame.pack(fill=tk.X, pady=(10, 0))
            
            ttk.Button(asin_buttons_frame, text="Remove Selected ASIN", command=remove_selected_asin).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(asin_buttons_frame, text="Clear All ASINs", command=clear_all_asins).pack(side=tk.LEFT)
            
            def refresh_all_lists():
                """Refresh all list displays"""
                refresh_lists_tree()
                refresh_asin_list()
                # Update combobox values
                lists_data = load_all_asin_lists()
                list_names = list(lists_data.keys()) if lists_data else ["Default List"]
                list_combobox['values'] = list_names
                if selected_list_var.get() not in list_names:
                    selected_list_var.set(list_names[0] if list_names else "Default List")
                # Update main window combobox
                update_main_combobox()
            
            def update_main_combobox():
                """Update the main window combobox with current ASINs"""
                all_asins = load_saved_asins()
                asin_combobox['values'] = sorted(all_asins)
            
            # Initial load
            refresh_all_lists()
            
            # Close button
            ttk.Button(main_frame, text="Close", command=manager_window.destroy).pack(pady=(20, 0))
        
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
                batch_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 10), padx=(0, 0))
                asin_label.grid_remove()
                asin_input_frame.grid_remove()
                asin_manager_button.grid_remove()
                # Increase window height for batch mode
                root.geometry(f'600x700+{x}+{y}')
            else:
                # Single mode: hide batch input, show single ASIN input
                batch_frame.grid_remove()
                asin_label.grid()
                asin_input_frame.grid()
                asin_manager_button.grid()
                # Reset window height for single mode
                root.geometry(f'600x600+{x}+{y}')
        
        # Validation function
        def validate_inputs():
            """Validates all inputs and returns (asins, year, months, export_preference) or None if invalid"""
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
            
            year_str = year_var.get().strip()
            months_str = months_var.get().strip()
            
            # Validate Year
            if not year_str or not year_str.isdigit():
                messagebox.showerror('Validation Error', 'Year must be a valid number.', parent=root)
                return None
            
            year = int(year_str)
            if year < 2011 or year > 2030:  # Reasonable range for Keepa data
                messagebox.showerror('Validation Error', 'Year must be between 2011 and 2030.', parent=root)
                return None
            
            # Validate Months
            if not months_str:
                messagebox.showerror('Validation Error', 'Please enter at least one month.', parent=root)
                return None
            
            try:
                months = [int(m.strip()) for m in months_str.split(',') if m.strip().isdigit()]
                if not months:
                    messagebox.showerror('Validation Error', 'Please enter valid month numbers.', parent=root)
                    return None
                
                # Check if all months are valid (1-12)
                invalid_months = [m for m in months if m < 1 or m > 12]
                if invalid_months:
                    messagebox.showerror('Validation Error', f'Invalid months: {invalid_months}. Months must be 1-12.', parent=root)
                    return None
                
                return asins, year, months, export_var.get()
                
            except ValueError:
                messagebox.showerror('Validation Error', 'Invalid month format. Use comma-separated numbers (e.g., 1,2,3).', parent=root)
                return None
        
        # Submit function
        def submit_inputs():
            """Handles form submission and validation"""
            result = validate_inputs()
            if result:
                result_var[0] = result  # Store the result
                root.destroy()
        
        # Cancel function
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
        title_label = ttk.Label(main_frame, text="Buybox Analyzer", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Processing Mode Selection
        ttk.Label(main_frame, text="Processing Mode:", font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        
        single_mode_radio = ttk.Radiobutton(main_frame, text="Single ASIN", variable=batch_mode_var, value=False, command=update_batch_mode)
        single_mode_radio.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        batch_mode_radio = ttk.Radiobutton(main_frame, text="Batch Processing", variable=batch_mode_var, value=True, command=update_batch_mode)
        batch_mode_radio.grid(row=1, column=2, sticky=tk.W, pady=5)
        
        # ASIN Input Mode Selection (for single mode)
        ttk.Label(main_frame, text="ASIN Input Mode:", font=("Arial", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
        
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
        asin_combobox = ttk.Combobox(asin_input_frame, textvariable=asin_var, values=saved_asins, state="disabled", width=30)
        asin_combobox.pack(fill=tk.X, expand=True)
        
        # ASIN Manager Button
        asin_manager_button = ttk.Button(main_frame, text="Manage ASIN List", command=open_asin_manager)
        asin_manager_button.grid(row=4, column=0, columnspan=3, pady=(5, 10))
        
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
            list_window.geometry("300x200")
            list_window.transient(root)
            list_window.grab_set()
            
            # Center the list selection window
            list_window.update_idletasks()
            list_x = (list_window.winfo_screenwidth() // 2) - (300 // 2)
            list_y = (list_window.winfo_screenheight() // 2) - (200 // 2)
            list_window.geometry(f'300x200+{list_x}+{list_y}')
            
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
        
        # Year Input
        ttk.Label(main_frame, text="Year:", font=("Arial", 10)).grid(row=5, column=0, sticky=tk.W, pady=5)
        year_entry = ttk.Entry(main_frame, textvariable=year_var, width=30)
        year_entry.grid(row=5, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Months Input
        ttk.Label(main_frame, text="Months (comma-separated):", font=("Arial", 10)).grid(row=6, column=0, sticky=tk.W, pady=5)
        months_entry = ttk.Entry(main_frame, textvariable=months_var, width=30)
        months_entry.grid(row=6, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
        
        # Help text
        help_text = "Example: 1,2,3 for January, February, March"
        help_label = ttk.Label(main_frame, text=help_text, font=("Arial", 8), foreground="gray")
        help_label.grid(row=7, column=0, columnspan=3, pady=(5, 10))
        
        # Export checkbox
        export_checkbox = ttk.Checkbutton(main_frame, text="Export results to CSV file", variable=export_var)
        export_checkbox.grid(row=8, column=0, columnspan=3, pady=(5, 20))
        
        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=9, column=0, columnspan=3, pady=(10, 0))
        
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
    
    def process_and_display_results(self, asins, year, months, export_csv, parent_window=None):
        """
        Process ASINs and display results in a GUI window.
        
        Args:
            asins (list): List of ASINs to process
            year (int): Year to analyze
            months (list): List of months to analyze
            export_csv (bool): Whether to export to CSV
            parent_window: Optional parent window for modal behavior
        """
        all_results = []
        errors = []
        
        if len(asins) == 1:
            # Single ASIN processing
            results, error = self.process_single_asin(asins[0], year, months)
            if error:
                if parent_window:
                    messagebox.showerror("Error", error, parent=parent_window)
                else:
                    print(error)
                return
            all_results = results
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
                results, error = self.process_single_asin(asin, year, months)
                if error:
                    errors.append(error)
                else:
                    all_results.extend(results)
            
            progress_window.destroy()
            
            # Show summary
            if errors:
                print(f"Completed with {len(errors)} errors:")
                for error in errors:
                    print(f"  - {error}")
            else:
                print("All ASINs processed successfully!")
        
        # Show results in a dedicated tkinter window
        result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        result_root.title('Buybox Analysis Results')

        # CRITICAL: Set resizable BEFORE any geometry settings
        result_root.resizable(True, True)

        # Remove transient to allow independent window controls
        if parent_window:
            result_root.transient()  # Clear transient relationship

        # Make window very large - almost full screen
        result_root.update_idletasks()
        screen_width = result_root.winfo_screenwidth()
        screen_height = result_root.winfo_screenheight()
        # Use 95% of screen dimensions with much larger minimums
        window_width = int(screen_width * 0.95)
        window_height = int(screen_height * 0.90)
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        result_root.geometry(f'{window_width}x{window_height}+{x}+{y}')

        # Set minimum size AFTER geometry
        result_root.minsize(1200, 800)

        # Show window on top initially, then allow normal behavior
        result_root.lift()
        result_root.attributes('-topmost', True)
        result_root.after_idle(lambda: result_root.attributes('-topmost', False))

        # Force update to apply all settings
        result_root.update()
        
        text = scrolledtext.ScrolledText(result_root, wrap=tk.WORD, width=80, height=30)
        text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        # Generate output
        if len(asins) == 1:
            # Single ASIN output (original format)
            output_lines = [f'ASIN: {asins[0]} | Year: {year}\n']
            for r in all_results:
                output_lines.append('-' * 40)
                output_lines.append(f'Month: {r["month"]:02d}')
                if r['amazon_percent_time'] is None:
                    output_lines.append('No buybox data for this month.')
                else:
                    output_lines.append(f'Amazon match count: {r["amazon_count"]} / {r["total_count"]}')
                    output_lines.append(f'Amazon held the buybox (by count): {r["amazon_percent_count"]:.2f}%')
                    output_lines.append(f'Amazon held the buybox (by time): {r["amazon_percent_time"]:.2f}%')
                    output_lines.append(f'Amazon time held (min): {r["amazon_time_minutes"]:.2f} / {r["total_time_minutes"]:.2f}')
            output_lines.append('-' * 40)
        else:
            # Batch processing output
            output_lines = [f'Batch Analysis Results | Year: {year} | ASINs Processed: {len(asins)}\n']
            if errors:
                output_lines.append(f'Errors: {len(errors)} ASINs failed to process\n')
            
            # Group results by ASIN
            asin_results = {}
            for r in all_results:
                asin = r['asin']
                if asin not in asin_results:
                    asin_results[asin] = []
                asin_results[asin].append(r)
            
            for asin in sorted(asin_results.keys()):
                output_lines.append('=' * 60)
                output_lines.append(f'ASIN: {asin}')
                output_lines.append('=' * 60)
                
                for r in asin_results[asin]:
                    output_lines.append(f'Month: {r["month"]:02d}')
                    if r['amazon_percent_time'] is None:
                        output_lines.append('  No buybox data for this month.')
                    else:
                        output_lines.append(f'  Amazon held the buybox (by count): {r["amazon_percent_count"]:.2f}%')
                        output_lines.append(f'  Amazon held the buybox (by time): {r["amazon_percent_time"]:.2f}%')
                    output_lines.append('')
            
            if errors:
                output_lines.append('=' * 60)
                output_lines.append('ERRORS:')
                output_lines.append('=' * 60)
                for error in errors:
                    output_lines.append(f'  {error}')
        
        text.insert(tk.END, '\n'.join(output_lines))
        text.config(state=tk.DISABLED)
        
        # Handle CSV export if requested
        if export_csv:
            save_path = filedialog.asksaveasfilename(
                title='Save buybox summary as CSV',
                defaultextension='.csv',
                filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
                parent=result_root
            )
            if save_path:
                # Create DataFrame with all results
                df_results = pd.DataFrame(all_results)
                df_results.to_csv(save_path, index=False)
                
                # Show summary message
                if len(asins) == 1:
                    messagebox.showinfo('Export', f'Summary DataFrame saved to {save_path}', parent=result_root)
                else:
                    messagebox.showinfo('Export', f'Batch results saved to {save_path}\nProcessed {len(asins)} ASINs with {len(errors)} errors', parent=result_root)
            else:
                messagebox.showinfo('Export', 'No file selected. DataFrame not saved.', parent=result_root)
        
        # If parent_window exists, wait for window to close; otherwise run mainloop
        if parent_window:
            result_root.wait_window()
        else:
            result_root.mainloop()

    def get_current_owners_input(self, parent_window=None):
        """
        Creates a simplified input window for fetching current buybox owners.
        Only requires ASIN input (no year/months needed).

        Args:
            parent_window: Optional parent window for modal behavior

        Returns:
            tuple: (asins, export_preference) or None if cancelled
        """
        # Create the main input window
        root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        root.title("Current Buybox Owners - Input")
        
        # IMPORTANT: Enable resizing so user can expand the window if needed
        root.resizable(True, True)
        
        # Set minimum size to ensure UI elements are visible
        root.minsize(700, 650)
        
        # Center the window on screen with a larger default size
        root.update_idletasks()
        window_width = 750
        window_height = 700
        x = (root.winfo_screenwidth() // 2) - (window_width // 2)
        y = (root.winfo_screenheight() // 2) - (window_height // 2)
        root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        # Show window on top initially
        root.lift()
        root.attributes('-topmost', True)
        root.after_idle(lambda: root.attributes('-topmost', False))

        # Variables to store input values
        asin_var = tk.StringVar()
        export_var = tk.BooleanVar()
        asin_input_mode = tk.StringVar(value="manual")
        batch_mode_var = tk.BooleanVar()

        # Variable to store the result
        result_var = [None]

        # ASIN Management Functions
        def open_asin_manager():
            """Open ASIN management window"""
            manager_window = tk.Toplevel(root)
            manager_window.title("ASIN Manager")
            manager_window.geometry("800x600")
            manager_window.transient(root)
            manager_window.grab_set()

            lists_data = load_all_asin_lists()

            main_frame = ttk.Frame(manager_window, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)

            ttk.Label(main_frame, text="ASIN Manager", font=("Arial", 16, "bold")).pack(pady=(0, 20))

            notebook = ttk.Notebook(main_frame)
            notebook.pack(fill=tk.BOTH, expand=True)

            # Add ASINs tab
            add_frame = ttk.Frame(notebook, padding="10")
            notebook.add(add_frame, text="Add ASINs")

            list_selection_frame = ttk.Frame(add_frame)
            list_selection_frame.pack(fill=tk.X, pady=(0, 10))

            ttk.Label(list_selection_frame, text="Add to list:").pack(side=tk.LEFT)
            list_names = list(lists_data.keys()) if lists_data else ["Default List"]
            selected_list_var = tk.StringVar(value=list_names[0] if list_names else "Default List")
            list_combobox = ttk.Combobox(list_selection_frame, textvariable=selected_list_var, values=list_names, state="readonly", width=20)
            list_combobox.pack(side=tk.LEFT, padx=(10, 0))

            def create_new_list():
                new_name = simpledialog.askstring("New List", "Enter name for new list:", parent=manager_window)
                if new_name and new_name.strip():
                    new_name = new_name.strip()
                    if new_name in lists_data:
                        messagebox.showerror("Error", "List name already exists.", parent=manager_window)
                        return

                    lists_data[new_name] = {'asins': [], 'description': ''}
                    if add_asins_to_saved_list([], new_name):
                        list_names = list(load_all_asin_lists().keys())
                        list_combobox['values'] = list_names
                        selected_list_var.set(new_name)
                        messagebox.showinfo("Success", f"Created new list: {new_name}", parent=manager_window)
                        refresh_all_lists()
                    else:
                        messagebox.showerror("Error", "Failed to create new list.", parent=manager_window)

            ttk.Button(list_selection_frame, text="New List", command=create_new_list).pack(side=tk.LEFT, padx=(10, 0))

            add_asins_frame = ttk.LabelFrame(add_frame, text="Add New ASINs", padding="10")
            add_asins_frame.pack(fill=tk.X, pady=(10, 0))

            ttk.Label(add_asins_frame, text="Paste ASINs (comma, space, or newline separated):").pack(anchor=tk.W)

            asin_text = tk.Text(add_asins_frame, height=6, width=70)
            asin_text.pack(fill=tk.X, pady=(5, 10))

            def add_asins():
                text_content = asin_text.get("1.0", tk.END).strip()
                valid_asins, error_msg = validate_asin_list(text_content)

                if error_msg:
                    messagebox.showerror("Validation Error", error_msg, parent=manager_window)
                    return

                if not valid_asins:
                    messagebox.showwarning("No ASINs", "No valid ASINs found in input.", parent=manager_window)
                    return

                selected_list = selected_list_var.get()
                total_asins, new_asins = add_asins_to_saved_list(valid_asins, selected_list)
                messagebox.showinfo("Success", f"Added {new_asins} new ASINs to '{selected_list}'. Total in list: {total_asins}", parent=manager_window)

                refresh_all_lists()
                asin_text.delete("1.0", tk.END)

            ttk.Button(add_asins_frame, text="Add ASINs", command=add_asins).pack(pady=(0, 10))

            # Manage Lists tab
            manage_frame = ttk.Frame(notebook, padding="10")
            notebook.add(manage_frame, text="Manage Lists")

            lists_frame = ttk.LabelFrame(manage_frame, text="ASIN Lists", padding="10")
            lists_frame.pack(fill=tk.BOTH, expand=True)

            columns = ('List Name', 'ASIN Count', 'Description')
            lists_tree = ttk.Treeview(lists_frame, columns=columns, show='headings', height=15)

            for col in columns:
                lists_tree.heading(col, text=col)
                lists_tree.column(col, width=150)

            lists_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            tree_scrollbar = ttk.Scrollbar(lists_frame, orient=tk.VERTICAL, command=lists_tree.yview)
            lists_tree.configure(yscrollcommand=tree_scrollbar.set)
            tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            def refresh_lists_tree():
                for item in lists_tree.get_children():
                    lists_tree.delete(item)

                lists_data = load_all_asin_lists()
                for list_name, list_data in lists_data.items():
                    asin_count = len(list_data.get('asins', []))
                    description = list_data.get('description', '')
                    lists_tree.insert('', tk.END, values=(list_name, asin_count, description))

            def remove_selected_list():
                selection = lists_tree.selection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a list to remove.", parent=manager_window)
                    return

                selected_item = lists_tree.item(selection[0])
                list_name = selected_item['values'][0]

                if messagebox.askyesno("Confirm", f"Are you sure you want to remove the list '{list_name}'?", parent=manager_window):
                    lists_data = load_all_asin_lists()
                    if list_name in lists_data:
                        del lists_data[list_name]
                        if save_asin_lists(lists_data):
                            messagebox.showinfo("Success", f"Removed list: {list_name}", parent=manager_window)
                            refresh_lists_tree()
                            refresh_all_lists()
                        else:
                            messagebox.showerror("Error", "Failed to remove list.", parent=manager_window)

            def clear_selected_list():
                selection = lists_tree.selection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select a list to clear.", parent=manager_window)
                    return

                selected_item = lists_tree.item(selection[0])
                list_name = selected_item['values'][0]

                if messagebox.askyesno("Confirm", f"Are you sure you want to clear all ASINs from '{list_name}'?", parent=manager_window):
                    lists_data = load_all_asin_lists()
                    if list_name in lists_data:
                        lists_data[list_name]['asins'] = []
                        if save_asin_lists(lists_data):
                            messagebox.showinfo("Success", f"Cleared list: {list_name}", parent=manager_window)
                            refresh_lists_tree()
                            refresh_all_lists()
                        else:
                            messagebox.showerror("Error", "Failed to clear list.", parent=manager_window)

            list_buttons_frame = ttk.Frame(manage_frame)
            list_buttons_frame.pack(fill=tk.X, pady=(10, 0))

            ttk.Button(list_buttons_frame, text="Remove Selected List", command=remove_selected_list).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(list_buttons_frame, text="Clear Selected List", command=clear_selected_list).pack(side=tk.LEFT)

            # All ASINs tab
            all_asins_frame = ttk.Frame(notebook, padding="10")
            notebook.add(all_asins_frame, text="All ASINs")

            asin_listbox_frame = ttk.Frame(all_asins_frame)
            asin_listbox_frame.pack(fill=tk.BOTH, expand=True)

            asin_listbox = tk.Listbox(asin_listbox_frame, selectmode=tk.SINGLE, height=20)
            asin_scrollbar = ttk.Scrollbar(asin_listbox_frame, orient=tk.VERTICAL, command=asin_listbox.yview)
            asin_listbox.configure(yscrollcommand=asin_scrollbar.set)

            asin_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            asin_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            def refresh_asin_list():
                asin_listbox.delete(0, tk.END)
                current_asins = load_saved_asins()
                for asin in sorted(current_asins):
                    asin_listbox.insert(tk.END, asin)

            def remove_selected_asin():
                selection = asin_listbox.curselection()
                if not selection:
                    messagebox.showwarning("No Selection", "Please select an ASIN to remove.", parent=manager_window)
                    return

                selected_asin = asin_listbox.get(selection[0])
                lists_data = load_all_asin_lists()

                removed_from = []
                for list_name, list_data in lists_data.items():
                    if selected_asin in list_data.get('asins', []):
                        list_data['asins'].remove(selected_asin)
                        removed_from.append(list_name)

                if removed_from:
                    if save_asin_lists(lists_data):
                        messagebox.showinfo("Success", f"Removed ASIN {selected_asin} from: {', '.join(removed_from)}", parent=manager_window)
                        refresh_asin_list()
                        refresh_lists_tree()
                    else:
                        messagebox.showerror("Error", "Failed to remove ASIN.", parent=manager_window)

            def clear_all_asins():
                if messagebox.askyesno("Confirm", "Are you sure you want to remove all saved ASINs?", parent=manager_window):
                    if save_asin_lists({}):
                        messagebox.showinfo("Success", "All ASINs removed.", parent=manager_window)
                        refresh_asin_list()
                        refresh_lists_tree()
                    else:
                        messagebox.showerror("Error", "Failed to clear ASINs.", parent=manager_window)

            asin_buttons_frame = ttk.Frame(all_asins_frame)
            asin_buttons_frame.pack(fill=tk.X, pady=(10, 0))

            ttk.Button(asin_buttons_frame, text="Remove Selected ASIN", command=remove_selected_asin).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(asin_buttons_frame, text="Clear All ASINs", command=clear_all_asins).pack(side=tk.LEFT)

            def refresh_all_lists():
                refresh_lists_tree()
                refresh_asin_list()
                lists_data = load_all_asin_lists()
                list_names = list(lists_data.keys()) if lists_data else ["Default List"]
                list_combobox['values'] = list_names
                if selected_list_var.get() not in list_names:
                    selected_list_var.set(list_names[0] if list_names else "Default List")
                update_main_combobox()

            def update_main_combobox():
                all_asins = load_saved_asins()
                asin_combobox['values'] = sorted(all_asins)

            refresh_all_lists()

            ttk.Button(main_frame, text="Close", command=manager_window.destroy).pack(pady=(20, 0))

        def update_asin_selection():
            if asin_input_mode.get() == "select":
                asin_combobox.pack(fill=tk.X, expand=True)
                asin_entry.pack_forget()
                asin_combobox.config(state="readonly")
            else:
                asin_entry.pack(fill=tk.X, expand=True)
                asin_combobox.pack_forget()
                asin_entry.config(state="normal")

        def update_batch_mode():
            if batch_mode_var.get():
                # Use all sticky directions (N, S, E, W) so it expands when window is resized
                batch_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 10), padx=(0, 0))
                asin_label.grid_remove()
                asin_input_frame.grid_remove()
                asin_manager_button.grid_remove()
            else:
                batch_frame.grid_remove()
                asin_label.grid()
                asin_input_frame.grid()
                asin_manager_button.grid()

        def validate_inputs():
            if batch_mode_var.get():
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
                if asin_input_mode.get() == "select":
                    asin = asin_var.get().strip()
                    if not asin:
                        messagebox.showerror('Validation Error', 'Please select an ASIN from the list.', parent=root)
                        return None
                else:
                    asin = asin_var.get().strip()
                    if not validate_asin(asin):
                        messagebox.showerror('Validation Error', 'ASIN must be exactly 10 characters (letters and numbers only).', parent=root)
                        return None
                asins = [asin]

            return asins, export_var.get()

        def submit_inputs():
            result = validate_inputs()
            if result:
                result_var[0] = result
                root.destroy()

        def cancel_inputs():
            root.destroy()

        # Create the form layout
        main_frame = ttk.Frame(root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights for proper resizing
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=1)
        # Allow row 3 (where batch_frame is placed) to expand vertically when resizing
        main_frame.rowconfigure(3, weight=1)

        # Title
        title_label = ttk.Label(main_frame, text="Current Buybox Owners", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))

        # Processing Mode Selection
        ttk.Label(main_frame, text="Processing Mode:", font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)

        single_mode_radio = ttk.Radiobutton(main_frame, text="Single ASIN", variable=batch_mode_var, value=False, command=update_batch_mode)
        single_mode_radio.grid(row=1, column=1, sticky=tk.W, pady=5)

        batch_mode_radio = ttk.Radiobutton(main_frame, text="Batch Processing", variable=batch_mode_var, value=True, command=update_batch_mode)
        batch_mode_radio.grid(row=1, column=2, sticky=tk.W, pady=5)

        # ASIN Input Mode Selection
        ttk.Label(main_frame, text="ASIN Input Mode:", font=("Arial", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)

        manual_radio = ttk.Radiobutton(main_frame, text="Manual Input", variable=asin_input_mode, value="manual", command=update_asin_selection)
        manual_radio.grid(row=2, column=1, sticky=tk.W, pady=5)

        select_radio = ttk.Radiobutton(main_frame, text="Select from List", variable=asin_input_mode, value="select", command=update_asin_selection)
        select_radio.grid(row=2, column=2, sticky=tk.W, pady=5)

        # ASIN Input
        asin_label = ttk.Label(main_frame, text="ASIN:", font=("Arial", 10))
        asin_label.grid(row=3, column=0, sticky=tk.W, pady=5)

        asin_input_frame = ttk.Frame(main_frame)
        asin_input_frame.grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))

        asin_entry = ttk.Entry(asin_input_frame, textvariable=asin_var, width=30)
        asin_entry.pack(fill=tk.X, expand=True)

        saved_asins = load_saved_asins()
        asin_combobox = ttk.Combobox(asin_input_frame, textvariable=asin_var, values=saved_asins, state="disabled", width=30)
        asin_combobox.pack(fill=tk.X, expand=True)

        # ASIN Manager Button
        asin_manager_button = ttk.Button(main_frame, text="Manage ASIN List", command=open_asin_manager)
        asin_manager_button.grid(row=4, column=0, columnspan=3, pady=(5, 10))

        # Batch Processing Input
        batch_frame = ttk.LabelFrame(main_frame, text="Batch ASIN Processing", padding="10")

        ttk.Label(batch_frame, text="Enter ASINs (comma, space, or newline separated):").pack(anchor=tk.W)

        # Create a frame for the text widget and scrollbar
        batch_text_frame = ttk.Frame(batch_frame)
        batch_text_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        # Create scrollbar for the text widget
        batch_scrollbar = ttk.Scrollbar(batch_text_frame, orient=tk.VERTICAL)
        batch_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Larger text area (height=12 instead of 6) with scrollbar
        batch_text_widget = tk.Text(batch_text_frame, height=12, width=50, yscrollcommand=batch_scrollbar.set)
        batch_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        batch_scrollbar.config(command=batch_text_widget.yview)

        # Quick load buttons
        batch_buttons_frame = ttk.Frame(batch_frame)
        batch_buttons_frame.pack(fill=tk.X)

        def load_all_saved_asins():
            all_asins = load_saved_asins()
            if all_asins:
                batch_text_widget.delete("1.0", tk.END)
                batch_text_widget.insert("1.0", "\n".join(all_asins))
            else:
                messagebox.showinfo("Info", "No saved ASINs found.", parent=root)

        def load_selected_list():
            lists_data = load_all_asin_lists()
            if not lists_data:
                messagebox.showinfo("Info", "No ASIN lists found.", parent=root)
                return

            list_window = tk.Toplevel(root)
            list_window.title("Select List")
            list_window.geometry("300x200")
            list_window.transient(root)
            list_window.grab_set()

            list_window.update_idletasks()
            list_x = (list_window.winfo_screenwidth() // 2) - (300 // 2)
            list_y = (list_window.winfo_screenheight() // 2) - (200 // 2)
            list_window.geometry(f'300x200+{list_x}+{list_y}')

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

        # Submit button for batch frame
        batch_submit_frame = ttk.Frame(batch_frame)
        batch_submit_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(batch_submit_frame, text="Submit", command=submit_inputs, style="Accent.TButton").pack()

        # Export checkbox
        export_checkbox = ttk.Checkbutton(main_frame, text="Export results to CSV file", variable=export_var)
        export_checkbox.grid(row=5, column=0, columnspan=3, pady=(5, 20))

        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=(10, 0))

        submit_btn = ttk.Button(button_frame, text="Submit", command=submit_inputs, style="Accent.TButton")
        submit_btn.pack(side=tk.LEFT, padx=(0, 10))

        cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel_inputs)
        cancel_btn.pack(side=tk.LEFT)

        # Initialize UI modes
        update_asin_selection()
        update_batch_mode()

        asin_entry.focus()
        root.bind('<Return>', lambda e: submit_inputs())
        root.bind('<Escape>', lambda e: cancel_inputs())

        if not parent_window:
            root.mainloop()
        else:
            root.wait_window()

        return result_var[0]

    def process_and_display_current_owners(self, asins, export_csv, parent_window=None):
        """
        Process ASINs to get current buybox owners and display results.

        Args:
            asins (list): List of ASINs to process
            export_csv (bool): Whether to export to CSV
            parent_window: Optional parent window for modal behavior
        """
        all_results = []
        errors = []

        if len(asins) == 1:
            # Single ASIN processing
            result, error = self.get_current_buybox_owner(asins[0])
            if error:
                if parent_window:
                    messagebox.showerror("Error", error, parent=parent_window)
                else:
                    print(error)
                return
            all_results = [result]
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

            progress_label = ttk.Label(progress_window, text="Fetching current buybox owners...", font=("Arial", 12))
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
                result, error = self.get_current_buybox_owner(asin)
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

        # Show results in a dedicated tkinter window
        result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        result_root.title('Current Buybox Owners')

        # CRITICAL: Set resizable BEFORE any geometry settings
        result_root.resizable(True, True)

        # Remove transient to allow independent window controls
        if parent_window:
            result_root.transient()  # Clear transient relationship

        # Make window very large - almost full screen
        result_root.update_idletasks()
        screen_width = result_root.winfo_screenwidth()
        screen_height = result_root.winfo_screenheight()
        # Use 95% of screen dimensions with much larger minimums
        window_width = int(screen_width * 0.95)
        window_height = int(screen_height * 0.90)
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        result_root.geometry(f'{window_width}x{window_height}+{x}+{y}')

        # Set minimum size AFTER geometry
        result_root.minsize(1200, 800)

        # Show window on top initially, then allow normal behavior
        result_root.lift()
        result_root.attributes('-topmost', True)
        result_root.after_idle(lambda: result_root.attributes('-topmost', False))

        # Force update to apply all settings
        result_root.update()

        text = scrolledtext.ScrolledText(result_root, wrap=tk.WORD, width=80, height=30)
        text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # Generate output
        output_lines = [f'Current Buybox Owners | Total ASINs: {len(asins)}\n']
        if errors:
            output_lines.append(f'Errors: {len(errors)} ASINs failed to process\n')

        output_lines.append('=' * 120)
        output_lines.append(f'{"ASIN":<15} {"Owner Type":<15} {"Current Owner ID":<25} {"Last Updated":<25} {"Product Title"}')
        output_lines.append('=' * 120)

        for result in all_results:
            asin = result['asin']
            owner_type = result['owner_type']
            owner_id = result['current_owner_id']
            last_updated = result['last_updated']
            title = result['product_title'][:50] + '...' if len(result['product_title']) > 50 else result['product_title']

            output_lines.append(f'{asin:<15} {owner_type:<15} {owner_id:<25} {last_updated:<25} {title}')

        if errors:
            output_lines.append('')
            output_lines.append('=' * 120)
            output_lines.append('ERRORS:')
            output_lines.append('=' * 120)
            for error in errors:
                output_lines.append(f'  {error}')

        text.insert(tk.END, '\n'.join(output_lines))
        text.config(state=tk.DISABLED)

        # Handle CSV export if requested
        if export_csv:
            save_path = filedialog.asksaveasfilename(
                title='Save current buybox owners as CSV',
                defaultextension='.csv',
                filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
                parent=result_root
            )
            if save_path:
                df_results = pd.DataFrame(all_results)
                df_results.to_csv(save_path, index=False)

                if len(asins) == 1:
                    messagebox.showinfo('Export', f'Results saved to {save_path}', parent=result_root)
                else:
                    messagebox.showinfo('Export', f'Batch results saved to {save_path}\nProcessed {len(asins)} ASINs with {len(errors)} errors', parent=result_root)
            else:
                messagebox.showinfo('Export', 'No file selected. Results not saved.', parent=result_root)

        # If parent_window exists, wait for window to close; otherwise run mainloop
        if parent_window:
            result_root.wait_window()
        else:
            result_root.mainloop()

