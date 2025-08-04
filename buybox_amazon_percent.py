import os
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Load API key from .env
load_dotenv('.env.local')
KEEPA_API_KEY = os.getenv('Keepa_API_KEY')

# Validate that API key was loaded
if not KEEPA_API_KEY:
    print("Error: Keepa_API_KEY not found in .env.local file.")
    print("Please ensure your .env.local file contains: Keepa_API_KEY=your_api_key_here")
    exit(1)

AMAZON_SELLER_ID = 'ATVPDKIKX0DER'

# --- Get user input via consolidated popup ---
import tkinter as tk
import pyautogui
from screeninfo import get_monitors
from tkinter import simpledialog, messagebox, filedialog, ttk

def get_user_input():
    """
    Creates a single consolidated input window for ASIN, year, and months.
    Returns tuple of (asin, year, months) with all validation intact.
    """
    mouse_x, mouse_y = pyautogui.position()
    
    # Create the main input window
    root = tk.Tk()
    root.title("Keepa API Tracker - Input")
    root.geometry(f'400x350+{mouse_x}+{mouse_y}')
    root.lift()
    root.attributes('-topmost', True)
    root.resizable(False, False)
    
    # Center the window on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (400 // 2)
    y = (root.winfo_screenheight() // 2) - (350 // 2)
    root.geometry(f'400x350+{x}+{y}')
    
    # Variables to store input values
    asin_var = tk.StringVar()
    year_var = tk.StringVar()
    months_var = tk.StringVar()
    export_var = tk.BooleanVar()  # Checkbox for export preference
    
    # Variable to store the result
    result_var = [None]  # Using list to store result (mutable)
    
    # Validation function
    def validate_inputs():
        """Validates all inputs and returns (asin, year, months) or None if invalid"""
        asin = asin_var.get().strip()
        year_str = year_var.get().strip()
        months_str = months_var.get().strip()
        
        # Validate ASIN
        if not asin or len(asin) != 10:
            messagebox.showerror('Validation Error', 'ASIN must be exactly 10 characters.', parent=root)
            return None
        
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
    
    # Title
    title_label = ttk.Label(main_frame, text="Keepa API Tracker", font=("Arial", 16, "bold"))
    title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
    
    # ASIN Input
    ttk.Label(main_frame, text="ASIN (10 characters):", font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
    asin_entry = ttk.Entry(main_frame, textvariable=asin_var, width=30)
    asin_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
    
    # Year Input
    ttk.Label(main_frame, text="Year:", font=("Arial", 10)).grid(row=2, column=0, sticky=tk.W, pady=5)
    year_entry = ttk.Entry(main_frame, textvariable=year_var, width=30)
    year_entry.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
    
    # Months Input
    ttk.Label(main_frame, text="Months (comma-separated):", font=("Arial", 10)).grid(row=3, column=0, sticky=tk.W, pady=5)
    months_entry = ttk.Entry(main_frame, textvariable=months_var, width=30)
    months_entry.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5, padx=(10, 0))
    
    # Help text
    help_text = "Example: 1,2,3 for January, February, March"
    help_label = ttk.Label(main_frame, text=help_text, font=("Arial", 8), foreground="gray")
    help_label.grid(row=4, column=0, columnspan=2, pady=(5, 10))
    
    # Export checkbox
    export_checkbox = ttk.Checkbutton(main_frame, text="Export results to CSV file", variable=export_var)
    export_checkbox.grid(row=5, column=0, columnspan=2, pady=(5, 20))
    
    # Buttons frame
    button_frame = ttk.Frame(main_frame)
    button_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0))
    
    # Submit and Cancel buttons
    submit_btn = ttk.Button(button_frame, text="Submit", command=submit_inputs, style="Accent.TButton")
    submit_btn.pack(side=tk.LEFT, padx=(0, 10))
    
    cancel_btn = ttk.Button(button_frame, text="Cancel", command=cancel_inputs)
    cancel_btn.pack(side=tk.LEFT)
    
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
