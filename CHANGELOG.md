# Changelog

## 2025-08-04
- **NEW FEATURE**: Created `sales_rank_analyzer.py` - A comprehensive sales rank analysis tool
  - Added `SalesRankAnalyzer` class following Single Responsibility Principle
  - Implemented sales rank history fetching from Keepa API using correct `salesRanks` field
  - Added intelligent category selection algorithm to choose the most relevant sales rank data
  - Created GUI interface for user input (ASIN, days to analyze, export options)
  - Added comprehensive statistics calculation (average, min, max, rank changes)
  - Implemented CSV export functionality for sales rank history
  - Added robust error handling and input validation
- **BUG FIX**: Corrected sales rank data parsing
  - Fixed incorrect use of `csv` field (price data) instead of `salesRanks` field
  - Implemented proper category selection algorithm to identify best sales rank category
  - Added scoring system to prefer categories with lower average ranks and more data points
  - Resolved data structure parsing issues with Keepa API response format
- **DOCUMENTATION**: Updated README.md with sales rank analyzer documentation
  - Added explanation of Keepa API limitations for category-level data
  - Documented individual product sales rank analysis capabilities
  - Updated usage instructions for both buybox tracker and sales rank analyzer
- **CODE QUALITY**: Improved project structure and maintainability
  - Separated concerns between buybox analysis and sales rank analysis
  - Added comprehensive comments and documentation
  - Implemented consistent error handling patterns
  - Added temporary debug capabilities (commented out for production use)

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