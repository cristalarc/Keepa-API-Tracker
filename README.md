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

### Quick Start (Unified Menu)
1. Add your Keepa API key to a `.env.local` file:
   ```
   Keepa_API_KEY=YOUR_KEEPA_API_KEY
   ```
2. Run the unified menu:
   ```
   python main.py
   ```
3. Select the tracking tool you want to use from the menu:
   - **Buybox Tracker**: Analyze Amazon buybox history
   - **Sales Rank Analyzer**: Track sales rank trends

### Individual Tool Usage

#### Buybox Analysis
Run directly:
```
python buybox_amazon_percent.py
```
- Enter the ASIN, year, and months when prompted
- View results in the GUI window
- Optionally export the data to CSV
- Supports batch processing of multiple ASINs

#### Sales Rank Analysis
Run directly:
```
python sales_rank_analyzer.py
```
- Enter the ASIN and number of days to analyze when prompted
- View detailed sales rank statistics and history
- Optionally export full history to CSV

## Files
- `main.py`: Unified menu for accessing all tracking tools
- `buybox_amazon_percent.py`: Main script for buybox analysis
- `sales_rank_analyzer.py`: Script for sales rank analysis
- `requirements.txt`: Python dependencies
- `.env.local`: Your Keepa API key (not included in repository)

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
