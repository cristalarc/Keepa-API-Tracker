# Keepa API Buybox Tracker

This project provides a Python script to analyze historical buybox ownership for Amazon products using the Keepa API. It allows users to:

- Fetch buybox history for a given ASIN from Keepa.
- Calculate the percentage of buybox held by Amazon for one or multiple months in a selected year.
- Optionally export the full buybox history data to a CSV file.
- Use a graphical interface (popups) to enter ASIN, year, and months, and to select export options.

## Features
- Single API call for multiple months (efficient usage of Keepa API tokens).
- Interactive user input via popup windows (tkinter).
- Results displayed for each selected month.
- Optional CSV export of all buybox history data.

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
1. Add your Keepa API key to a `.env` file:
   ```
   Keepa_API_KEY=YOUR_KEEPA_API_KEY
   ```
2. Run the script:
   ```
   python buybox_amazon_percent.py
   ```
3. Enter the ASIN, year, and months when prompted.
4. View results in the terminal. Optionally export the data to CSV.

## Files
- `buybox_amazon_percent.py`: Main script for buybox analysis.
- `requirements.txt`: Python dependencies.
- `.env`: Your Keepa API key.

## License
MIT

## Author
Cristal Arc / Talavera

## Changelog
See `CHANGELOG.md` for details.
