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
from tkinter import simpledialog, messagebox

def get_user_input():
    root = tk.Tk()
    root.withdraw()  # Hide main window
    asin = simpledialog.askstring('Input', 'Enter ASIN:', parent=root)
    year = simpledialog.askinteger('Input', 'Enter Year (e.g. 2025):', parent=root)
    months_str = simpledialog.askstring('Input', 'Enter months as comma-separated numbers (e.g. 1,2,3):', parent=root)
    if not asin or not year or not months_str:
        messagebox.showerror('Error', 'All fields are required.')
        root.destroy()
        exit(1)
    months = [int(m.strip()) for m in months_str.split(',') if m.strip().isdigit() and 1 <= int(m.strip()) <= 12]
    if not months:
        messagebox.showerror('Error', 'Invalid months input.')
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

# Ask user where to save the DataFrame as CSV
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
save_path = filedialog.asksaveasfilename(
    title='Save buybox history as CSV',
    defaultextension='.csv',
    filetypes=[('CSV files', '*.csv'), ('All files', '*.*')]
)
root.destroy()
if save_path:
    df.to_csv(save_path, index=False)
    print(f'DataFrame saved to {save_path}')
else:
    print('No file selected. DataFrame not saved.')

# Filter for selected month/year

results = []
for month in MONTHS:
    month_df = df[(df['year'] == YEAR) & (df['month'] == month)]
    if month_df.empty:
        print(f'No buybox data for {YEAR}-{month:02d}.')
        results.append({'month': month, 'amazon_percent': None, 'total_count': 0, 'amazon_count': 0})
        continue
    amazon_count = (month_df['seller_id'] == AMAZON_SELLER_ID).sum()
    total_count = len(month_df)
    percent = (amazon_count / total_count) * 100
    print(f'ASIN: {ASIN}\nMonth: {YEAR}-{month:02d}')
    print(f'Amazon match count: {amazon_count} / {total_count}')
    print(f'Amazon held the buybox {percent:.2f}% of the time.')
    results.append({'month': month, 'amazon_percent': percent, 'total_count': total_count, 'amazon_count': amazon_count})

# Ask user if they want to export the DataFrame
root = tk.Tk()
root.withdraw()
export = messagebox.askyesno('Export Data', 'Do you want to export the full DataFrame to a CSV file?')
if export:
    from tkinter import filedialog
    save_path = filedialog.asksaveasfilename(
        title='Save buybox history as CSV',
        defaultextension='.csv',
        filetypes=[('CSV files', '*.csv'), ('All files', '*.*')]
    )
    root.destroy()
    if save_path:
        df.to_csv(save_path, index=False)
        print(f'DataFrame saved to {save_path}')
    else:
        print('No file selected. DataFrame not saved.')
else:
    root.destroy()
    print('DataFrame export skipped.')
