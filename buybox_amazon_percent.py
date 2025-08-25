import os
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import json
import re

# Load API key from .env
load_dotenv('.env.local')
KEEPA_API_KEY = os.getenv('Keepa_API_KEY')

# Validate that API key was loaded
if not KEEPA_API_KEY:
    print("Error: Keepa_API_KEY not found in .env.local file.")
    print("Please ensure your .env.local file contains: Keepa_API_KEY=your_api_key_here")
    exit(1)

AMAZON_SELLER_ID = 'ATVPDKIKX0DER'

# ASIN Management Functions
ASIN_FILE = 'saved_asins.json'

def load_saved_asins():
    """Load saved ASINs from JSON file"""
    try:
        if os.path.exists(ASIN_FILE):
            with open(ASIN_FILE, 'r') as f:
                data = json.load(f)
                return data.get('asins', [])
        return []
    except (json.JSONDecodeError, FileNotFoundError):
        return []

def save_asins_to_file(asins):
    """Save ASINs to JSON file"""
    try:
        with open(ASIN_FILE, 'w') as f:
            json.dump({'asins': asins}, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving ASINs: {e}")
        return False

def validate_asin(asin):
    """Validate if a string is a valid ASIN format"""
    if not asin:
        return False
    # ASINs are 10 characters long and contain only letters and numbers
    asin = asin.strip().upper()
    return len(asin) == 10 and re.match(r'^[A-Z0-9]{10}$', asin)

def validate_asin_list(asin_text):
    """Validate and parse a list of ASINs from text input"""
    if not asin_text.strip():
        return [], "No ASINs provided"
    
    # Split by common delimiters (comma, newline, space)
    asin_candidates = re.split(r'[,\n\s]+', asin_text.strip())
    
    valid_asins = []
    invalid_asins = []
    
    for candidate in asin_candidates:
        candidate = candidate.strip()
        if candidate:  # Skip empty strings
            if validate_asin(candidate):
                valid_asins.append(candidate.upper())
            else:
                invalid_asins.append(candidate)
    
    if invalid_asins:
        error_msg = f"Invalid ASINs found: {', '.join(invalid_asins[:5])}"
        if len(invalid_asins) > 5:
            error_msg += f" and {len(invalid_asins) - 5} more"
        return valid_asins, error_msg
    
    return valid_asins, None

def add_asins_to_saved_list(new_asins):
    """Add new ASINs to the saved list, avoiding duplicates"""
    current_asins = load_saved_asins()
    
    # Convert to uppercase and remove duplicates
    new_asins_upper = [asin.upper() for asin in new_asins]
    all_asins = list(set(current_asins + new_asins_upper))
    
    # Save updated list
    if save_asins_to_file(all_asins):
        return len(all_asins), len(new_asins)
    return len(current_asins), 0

# --- Get user input via consolidated popup ---
import tkinter as tk
import pyautogui
from screeninfo import get_monitors
from tkinter import simpledialog, messagebox, filedialog, ttk

def get_user_input():
    """
    Creates a single consolidated input window for ASIN, year, and months.
    Returns tuple of (asin, year, months, export_preference) with all validation intact.
    """
    mouse_x, mouse_y = pyautogui.position()
    
    # Create the main input window
    root = tk.Tk()
    root.title("Keepa API Tracker - Input")
    root.geometry(f'500x500+{mouse_x}+{mouse_y}')
    root.lift()
    root.attributes('-topmost', True)
    root.resizable(False, False)
    
    # Center the window on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (500 // 2)
    y = (root.winfo_screenheight() // 2) - (500 // 2)
    root.geometry(f'500x500+{x}+{y}')
    
    # Variables to store input values
    asin_var = tk.StringVar()
    year_var = tk.StringVar()
    months_var = tk.StringVar()
    export_var = tk.BooleanVar()  # Checkbox for export preference
    asin_input_mode = tk.StringVar(value="manual")  # "manual" or "select"
    
    # Variable to store the result
    result_var = [None]  # Using list to store result (mutable)
    
    # ASIN Management Functions
    def open_asin_manager():
        """Open ASIN management window"""
        manager_window = tk.Toplevel(root)
        manager_window.title("ASIN Manager")
        manager_window.geometry("600x400")
        manager_window.transient(root)
        manager_window.grab_set()
        
        # Load current ASINs
        saved_asins = load_saved_asins()
        
        # Create main frame
        main_frame = ttk.Frame(manager_window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="ASIN Manager", font=("Arial", 16, "bold")).pack(pady=(0, 20))
        
        # Add ASINs section
        add_frame = ttk.LabelFrame(main_frame, text="Add New ASINs", padding="10")
        add_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(add_frame, text="Paste ASINs (comma, space, or newline separated):").pack(anchor=tk.W)
        
        asin_text = tk.Text(add_frame, height=4, width=50)
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
            
            total_asins, new_asins = add_asins_to_saved_list(valid_asins)
            messagebox.showinfo("Success", f"Added {new_asins} new ASINs. Total saved: {total_asins}", parent=manager_window)
            
            # Refresh the list
            refresh_asin_list()
            asin_text.delete("1.0", tk.END)
        
        ttk.Button(add_frame, text="Add ASINs", command=add_asins).pack(pady=(0, 10))
        
        # Current ASINs section
        list_frame = ttk.LabelFrame(main_frame, text="Saved ASINs", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # ASIN listbox with scrollbar
        listbox_frame = ttk.Frame(list_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True)
        
        asin_listbox = tk.Listbox(listbox_frame, selectmode=tk.SINGLE)
        scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=asin_listbox.yview)
        asin_listbox.configure(yscrollcommand=scrollbar.set)
        
        asin_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def refresh_asin_list():
            """Refresh the ASIN listbox"""
            asin_listbox.delete(0, tk.END)
            current_asins = load_saved_asins()
            for asin in sorted(current_asins):
                asin_listbox.insert(tk.END, asin)
        
        def remove_selected_asin():
            """Remove selected ASIN from list"""
            selection = asin_listbox.curselection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select an ASIN to remove.", parent=manager_window)
                return
            
            selected_asin = asin_listbox.get(selection[0])
            current_asins = load_saved_asins()
            current_asins.remove(selected_asin)
            
            if save_asins_to_file(current_asins):
                messagebox.showinfo("Success", f"Removed ASIN: {selected_asin}", parent=manager_window)
                refresh_asin_list()
            else:
                messagebox.showerror("Error", "Failed to remove ASIN.", parent=manager_window)
        
        def clear_all_asins():
            """Clear all saved ASINs"""
            if messagebox.askyesno("Confirm", "Are you sure you want to remove all saved ASINs?", parent=manager_window):
                if save_asins_to_file([]):
                    messagebox.showinfo("Success", "All ASINs removed.", parent=manager_window)
                    refresh_asin_list()
                else:
                    messagebox.showerror("Error", "Failed to clear ASINs.", parent=manager_window)
        
        # Buttons for ASIN management
        button_frame = ttk.Frame(list_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Remove Selected", command=remove_selected_asin).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Clear All", command=clear_all_asins).pack(side=tk.LEFT)
        
        # Initial load
        refresh_asin_list()
        
        # Close button
        ttk.Button(main_frame, text="Close", command=manager_window.destroy).pack(pady=(20, 0))
    
    def update_asin_selection():
        """Update ASIN input based on selection mode"""
        if asin_input_mode.get() == "select":
            # Enable combobox, disable manual entry
            asin_combobox.config(state="readonly")
            asin_entry.config(state="disabled")
        else:
            # Enable manual entry, disable combobox
            asin_combobox.config(state="disabled")
            asin_entry.config(state="normal")
    
    # Validation function
    def validate_inputs():
        """Validates all inputs and returns (asin, year, months, export_preference) or None if invalid"""
        # Get ASIN based on input mode
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
            
            return asin, year, months, export_var.get()
            
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
    title_label = ttk.Label(main_frame, text="Keepa API Tracker", font=("Arial", 16, "bold"))
    title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
    
    # ASIN Input Mode Selection
    ttk.Label(main_frame, text="ASIN Input Mode:", font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
    
    manual_radio = ttk.Radiobutton(main_frame, text="Manual Input", variable=asin_input_mode, value="manual", command=update_asin_selection)
    manual_radio.grid(row=1, column=1, sticky=tk.W, pady=5)
    
    select_radio = ttk.Radiobutton(main_frame, text="Select from List", variable=asin_input_mode, value="select", command=update_asin_selection)
    select_radio.grid(row=1, column=2, sticky=tk.W, pady=5)
    
    # ASIN Input
    ttk.Label(main_frame, text="ASIN:", font=("Arial", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
    
    # Manual entry
    asin_entry = ttk.Entry(main_frame, textvariable=asin_var, width=30)
    asin_entry.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
    
    # Combobox for selection
    saved_asins = load_saved_asins()
    asin_combobox = ttk.Combobox(main_frame, textvariable=asin_var, values=saved_asins, state="disabled", width=30)
    asin_combobox.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
    
    # ASIN Manager Button
    ttk.Button(main_frame, text="Manage ASIN List", command=open_asin_manager).grid(row=3, column=0, columnspan=3, pady=(5, 10))
    
    # Year Input
    ttk.Label(main_frame, text="Year:", font=("Arial", 10)).grid(row=4, column=0, sticky=tk.W, pady=5)
    year_entry = ttk.Entry(main_frame, textvariable=year_var, width=30)
    year_entry.grid(row=4, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
    
    # Months Input
    ttk.Label(main_frame, text="Months (comma-separated):", font=("Arial", 10)).grid(row=5, column=0, sticky=tk.W, pady=5)
    months_entry = ttk.Entry(main_frame, textvariable=months_var, width=30)
    months_entry.grid(row=5, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
    
    # Help text
    help_text = "Example: 1,2,3 for January, February, March"
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
    
    # Initialize ASIN input mode
    update_asin_selection()
    
    # Set focus to first entry and bind Enter key
    asin_entry.focus()
    root.bind('<Return>', lambda e: submit_inputs())
    root.bind('<Escape>', lambda e: cancel_inputs())
    
    # Start the GUI event loop
    root.mainloop()
    
    # Return the stored result
    return result_var[0]

# Get user input with the new consolidated interface
user_input = get_user_input()
if user_input is None:
    print("Input cancelled or invalid. Exiting.")
    exit(1)

ASIN, YEAR, MONTHS, EXPORT_CSV = user_input

# Fetch product data from Keepa
url = 'https://api.keepa.com/product'
params = {
    'key': KEEPA_API_KEY,
    'domain': 1,  # Amazon.com
    'asin': ASIN,
    'buybox': 1
}
response = requests.get(url, params=params)
data = response.json()

if not data.get('products'):
    print('No product data found.')
    exit(1)

product = data['products'][0]
buybox_history = product.get('buyBoxSellerIdHistory')

if not buybox_history:
    print('No buybox history available for this ASIN.')
    exit(1)

# buyBoxSellerIdHistory: [timestamp1, sellerId1, timestamp2, sellerId2, ...]
# Timestamps are in Keepa minutes since Jan 1, 2011
keepa_epoch = datetime(2011, 1, 1)

records = []
for i in range(0, len(buybox_history), 2):
    minutes = int(buybox_history[i])
    seller_id = buybox_history[i+1]
    dt = keepa_epoch + pd.Timedelta(minutes=minutes)
    records.append({'datetime': dt, 'seller_id': seller_id})

df = pd.DataFrame(records)
df['year'] = df['datetime'].dt.year
df['month'] = df['datetime'].dt.month

# Filter for selected month/year

results = []
for month in MONTHS:
    month_df = df[(df['year'] == YEAR) & (df['month'] == month)].sort_values('datetime').reset_index(drop=True)
    if month_df.empty or len(month_df) < 2:
        results.append({
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
        'month': month,
        'amazon_percent_count': percent_count,
        'amazon_percent_time': percent_time,
        'total_count': total_count,
        'amazon_count': amazon_count,
        'amazon_time_minutes': amazon_time,
        'total_time_minutes': total_time
    })

# Show results in a dedicated tkinter window
mouse_x, mouse_y = pyautogui.position()
result_root = tk.Tk()
result_root.geometry(f'1000x1000+{mouse_x}+{mouse_y}')
result_root.title('Buybox Analysis Results')
result_root.lift()
result_root.attributes('-topmost', True)

from tkinter import scrolledtext
text = scrolledtext.ScrolledText(result_root, wrap=tk.WORD, width=50, height=20)
text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

output_lines = [f'ASIN: {ASIN} | Year: {YEAR}\n']
for r in results:
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
text.insert(tk.END, '\n'.join(output_lines))
text.config(state=tk.DISABLED)

# Handle CSV export if requested
if EXPORT_CSV:
    save_path = filedialog.asksaveasfilename(
        title='Save buybox summary as CSV',
        defaultextension='.csv',
        filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
        parent=result_root
    )
    if save_path:
        pd.DataFrame(results).to_csv(save_path, index=False)
        messagebox.showinfo('Export', f'Summary DataFrame saved to {save_path}', parent=result_root)
    else:
        messagebox.showinfo('Export', 'No file selected. DataFrame not saved.', parent=result_root)
result_root.mainloop()
