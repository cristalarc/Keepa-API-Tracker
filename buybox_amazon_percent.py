import os
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()
KEEPA_API_KEY = os.getenv('Keepa_API_KEY')

AMAZON_SELLER_ID = 'ATVPDKIKX0DER'

# --- Get user input via popup ---
import tkinter as tk
import pyautogui
from screeninfo import get_monitors
from tkinter import simpledialog, messagebox, filedialog

def get_user_input():
    mouse_x, mouse_y = pyautogui.position()
    root = tk.Tk()
    # Make the window tiny and position it at the mouse
    root.geometry(f'1x1+{mouse_x}+{mouse_y}')
    root.lift()
    root.attributes('-topmost', True)
    root.update()
    asin = simpledialog.askstring('Input', 'Enter ASIN:', parent=root)
    if not asin or len(asin) != 10:
        messagebox.showerror('Error', 'ASIN must be exactly 10 characters.', parent=root)
        root.destroy()
        exit(1)
    year = simpledialog.askinteger('Input', 'Enter Year (e.g. 2025):', parent=root)
    months_str = simpledialog.askstring('Input', 'Enter months as comma-separated numbers (e.g. 1,2,3):', parent=root)
    if not year or not months_str:
        messagebox.showerror('Error', 'All fields are required.', parent=root)
        root.destroy()
        exit(1)
    months = [int(m.strip()) for m in months_str.split(',') if m.strip().isdigit() and 1 <= int(m.strip()) <= 12]
    if not months:
        messagebox.showerror('Error', 'Invalid months input.', parent=root)
        root.destroy()
        exit(1)
    root.destroy()
    return asin, year, months

ASIN, YEAR, MONTHS = get_user_input()

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

# Ask user if they want to export the DataFrame
def ask_export():
    export = messagebox.askyesno('Export Data', 'Do you want to export the summary DataFrame to a CSV file?', parent=result_root)
    if export:
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
    else:
        messagebox.showinfo('Export', 'DataFrame export skipped.', parent=result_root)

result_root.after(100, ask_export)
result_root.mainloop()
