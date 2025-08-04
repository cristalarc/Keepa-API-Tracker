# Keepa API Buybox Tracker

This project provides Python scripts to analyze Amazon product data using the Keepa API. It includes two main tools:

1. **Buybox Tracker** (`buybox_amazon_percent.py`): Analyzes historical buybox ownership
2. **Sales Rank Analyzer** (`sales_rank_analyzer.py`): Analyzes sales rank trends and statistics

## Features

### Buybox Tracker
- Fetch buybox history for a given ASIN from Keepa
- Calculate the percentage of buybox held by Amazon for one or multiple months in a selected year
- Optionally export the full buybox history data to a CSV file
- Use a graphical interface (popups) to enter ASIN, year, and months, and to select export options

### Sales Rank Analyzer
- Fetch and analyze sales rank history for any ASIN
- Calculate statistics for the last N days (default: 30 days)
- Provides average, minimum, and maximum sales rank
- Tracks number of rank changes and data points
- Shows recent rank history
- Optional CSV export of full sales rank history

## Requirements
- Python 3.7+
- requests
- python-dotenv
- pandas
- tkinter (included with standard Python)

Install dependencies:
```
pip install -r requirements.txt
```

## Usage

### Buybox Analysis
1. Add your Keepa API key to a `.env.local` file:
   ```
   Keepa_API_KEY=YOUR_KEEPA_API_KEY
   ```
2. Run the buybox tracker:
   ```
   python buybox_amazon_percent.py
   ```
3. Enter the ASIN, year, and months when prompted.
4. View results in the terminal. Optionally export the data to CSV.

### Sales Rank Analysis
1. Ensure your Keepa API key is in the `.env.local` file
2. Run the sales rank analyzer:
   ```
   python sales_rank_analyzer.py
   ```
3. Enter the ASIN and number of days to analyze when prompted.
4. View detailed sales rank statistics and history.

## Files
- `buybox_amazon_percent.py`: Main script for buybox analysis
- `sales_rank_analyzer.py`: Script for sales rank analysis
- `requirements.txt`: Python dependencies
- `.env.local`: Your Keepa API key

## Keepa API Limitations

**Important Note**: The Keepa API provides individual product sales rank data but does NOT provide:
- Average sales rank for entire categories or subcategories
- Aggregated category data
- Average sales rank for the last 30 days across multiple products

The sales rank analyzer focuses on individual product analysis, which is what the Keepa API supports.

## License
MIT

## Author
Cristal Arc / Talavera

## Changelog
See `CHANGELOG.md` for details.
