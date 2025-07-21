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
    month = simpledialog.askinteger('Input', 'Enter Month (1-12):', parent=root)
    if not asin or not year or not month:
        messagebox.showerror('Error', 'All fields are required.')
        root.destroy()
        exit(1)
    root.destroy()
    return asin, year, month

ASIN, YEAR, MONTH = get_user_input()

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
month_df = df[(df['year'] == YEAR) & (df['month'] == MONTH)]
if month_df.empty:
    print(f'No buybox data for {YEAR}-{MONTH:02d}.')
    exit(1)

# Debug: Show unique seller IDs and sample data
print('Sample seller IDs in selected month:', month_df['seller_id'].head(10).tolist())
print('Unique seller IDs in selected month:', month_df['seller_id'].unique())

# Calculate % held by Amazon
amazon_count = (month_df['seller_id'] == AMAZON_SELLER_ID).sum()
total_count = len(month_df)
percent = (amazon_count / total_count) * 100

print(f'Amazon match count: {amazon_count} / {total_count}')

print(f'ASIN: {ASIN}\nMonth: {YEAR}-{MONTH:02d}')
print(f'Amazon held the buybox {percent:.2f}% of the time.')
