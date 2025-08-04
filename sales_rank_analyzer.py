import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import pyautogui

# Load API key from .env
load_dotenv('.env.local')
KEEPA_API_KEY = os.getenv('Keepa_API_KEY')

# Validate that API key was loaded
if not KEEPA_API_KEY:
    print("Error: Keepa_API_KEY not found in .env.local file.")
    print("Please ensure your .env.local file contains: Keepa_API_KEY=your_api_key_here")
    exit(1)

class SalesRankAnalyzer:
    """
    A class to analyze sales rank data from Keepa API.
    This follows the Single Responsibility Principle by focusing only on sales rank analysis.
    """
    
    def __init__(self, api_key):
        """
        Initialize the analyzer with the Keepa API key.
        
        Args:
            api_key (str): The Keepa API key for authentication
        """
        self.api_key = api_key
        self.keepa_epoch = datetime(2011, 1, 1)  # Keepa's epoch date
        
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
            
            # DEBUG: Uncomment the following lines if you need to export raw data for debugging
            # import json
            # debug_filename = f'keepa_debug_{asin}.json'
            # with open(debug_filename, 'w') as f:
            #     json.dump(data, f, indent=2, default=str)
            # print(f"DEBUG: Raw Keepa data exported to {debug_filename}")
                
            return data['products'][0]
            
        except requests.exceptions.RequestException as e:
            print(f'Error fetching data for ASIN {asin}: {e}')
            return None
    
    def parse_sales_rank_history(self, product_data):
        """
        Parse sales rank history from Keepa product data.
        
        Args:
            product_data (dict): Product data from Keepa API
            
        Returns:
            pandas.DataFrame: DataFrame with datetime and sales rank columns
        """
        if not product_data:
            return pd.DataFrame()
            
        # Keepa provides sales rank data in the salesRanks field
        # Format: {"category_id": [timestamp1, rank1, timestamp2, rank2, ...]}
        sales_ranks_data = product_data.get('salesRanks', {})
        
        if not sales_ranks_data:
            return pd.DataFrame()
        
        # Find the category with the most reasonable sales rank values
        # Sales ranks should typically be between 1 and 100,000
        best_category_id = None
        best_category_data = None
        best_score = 0
        
        for category_id, rank_data in sales_ranks_data.items():
            if isinstance(rank_data, list) and len(rank_data) >= 2:
                valid_ranks = [rank for rank in rank_data[1::2] if rank != -1]
                if valid_ranks:
                    # Calculate a score based on how reasonable the ranks are
                    # Lower ranks (better sales) should be more common
                    avg_rank = sum(valid_ranks) / len(valid_ranks)
                    min_rank = min(valid_ranks)
                    max_rank = max(valid_ranks)
                    
                    # Prefer categories with lower average ranks and reasonable ranges
                    score = len(valid_ranks) * (100000 / avg_rank) if avg_rank > 0 else 0
                    
                    if score > best_score:
                        best_score = score
                        best_category_id = category_id
                        best_category_data = rank_data
        
        if best_category_data:
            sales_rank_data = best_category_data
        else:
            # Fallback to first category with data
            for category_id, rank_data in sales_ranks_data.items():
                if isinstance(rank_data, list) and len(rank_data) >= 2:
                    sales_rank_data = rank_data
                    break
            else:
                return pd.DataFrame()
        
        # Parse the sales rank data
        # Format: [timestamp1, rank1, timestamp2, rank2, ...]
        records = []
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
                except (ValueError, TypeError) as e:
                    # Skip invalid data points
                    continue
        
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
        if df.empty:
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
        recent_data = df[df['datetime'] >= cutoff_date].copy()
        
        if recent_data.empty:
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
        
        return stats

def get_user_input():
    """
    Creates a user input window for sales rank analysis.
    Returns tuple of (asin, days, export_csv) or None if cancelled.
    """
    mouse_x, mouse_y = pyautogui.position()
    
    # Create the main input window
    root = tk.Tk()
    root.title("Sales Rank Analyzer - Input")
    root.geometry(f'400x300+{mouse_x}+{mouse_y}')
    root.lift()
    root.attributes('-topmost', True)
    root.resizable(False, False)
    
    # Center the window on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (400 // 2)
    y = (root.winfo_screenheight() // 2) - (300 // 2)
    root.geometry(f'400x300+{x}+{y}')
    
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
    
    # Start the GUI event loop
    root.mainloop()
    
    # Return the stored result
    return result_var[0]

def display_results(asin, stats, sales_rank_df, export_csv=False):
    """
    Display sales rank analysis results in a GUI window.
    
    Args:
        asin (str): The analyzed ASIN
        stats (dict): Sales rank statistics
        sales_rank_df (pandas.DataFrame): Full sales rank history
        export_csv (bool): Whether to offer CSV export
    """
    mouse_x, mouse_y = pyautogui.position()
    result_root = tk.Tk()
    result_root.geometry(f'800x600+{mouse_x}+{mouse_y}')
    result_root.title(f'Sales Rank Analysis - {asin}')
    result_root.lift()
    result_root.attributes('-topmost', True)
    
    # Create scrolled text widget
    text = scrolledtext.ScrolledText(result_root, wrap=tk.WORD, width=60, height=25)
    text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
    
    # Format output
    output_lines = [f'Sales Rank Analysis for ASIN: {asin}\n']
    output_lines.append('=' * 50)
    
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
    
    result_root.mainloop()

def main():
    """
    Main function to run the sales rank analyzer.
    """
    print("Sales Rank Analyzer")
    print("=" * 30)
    
    # Get user input
    user_input = get_user_input()
    if user_input is None:
        print("Input cancelled or invalid. Exiting.")
        return
    
    asin, days, export_csv = user_input
    
    # Initialize analyzer
    analyzer = SalesRankAnalyzer(KEEPA_API_KEY)
    
    # Fetch product data
    print(f"Fetching sales rank data for ASIN: {asin}")
    product_data = analyzer.get_product_sales_rank(asin)
    
    if not product_data:
        print("Failed to fetch product data. Exiting.")
        return
    
    # Parse sales rank history
    sales_rank_df = analyzer.parse_sales_rank_history(product_data)
    
    if sales_rank_df.empty:
        print("No sales rank history found for this product.")
        return
    
    # Calculate statistics
    stats = analyzer.calculate_sales_rank_stats(sales_rank_df, days)
    
    # Display results
    display_results(asin, stats, sales_rank_df, export_csv)

if __name__ == "__main__":
    main() 