# Changelog

## 2025-07-21
- Project created: Keepa API Buybox Tracker.
- Added `.env` file for Keepa API key management.
- Created `requirements.txt` with dependencies: requests, python-dotenv, pandas.
- Developed initial Python script to fetch buybox history and calculate Amazon's buybox percentage for a selected month and ASIN.
- Fixed bug: Convert buybox history timestamps to integer for correct datetime conversion.
- Corrected Amazon seller ID to `ATVPDKIKX0DER`.
- Added debug output to inspect DataFrame and seller IDs.
- Added tkinter popup for user input (ASIN, year, month).
- Added option to save DataFrame to CSV via file dialog.
- Made file export optional (user chooses via popup).
- Enhanced script to allow calculation of buybox % for multiple months in one API call (user enters months as comma-separated values).
- Improved user experience with popups for all major inputs and options.
- Created `README.md` and `CHANGELOG.md` files documenting project purpose and changes.
