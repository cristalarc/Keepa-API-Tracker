# Keepa API Desktop Tracker

This project is a comprehensive Python `tkinter` desktop GUI application for Amazon product analytics via the Keepa API. It allows users to track and analyze Buybox ownership percentages, Sales Rank changes, Price histories, and Delivery Speeds.

## Features

- **Unified GUI Dashboard**: Launch the tracking suite through `keepa_tracker.py`, giving you tabbed access to all available tools.
- **Buybox Tracker**: Fetch historical buybox data and calculate the percentage of time Amazon holds the buybox for a given ASIN.
- **Sales Rank Analyzer**: Analyze sales rank history, including average, median, and extreme drops over a specified period.
- **Delivery Speed Tracker**: Monitor historic competitor fulfillment and delivery speeds on specific items.
- **Price Tracking**: Keep tabs on long-term price fluctuations for competing offers.
- **CSV Exports**: Export the underlying historical data to local CSV files for further analysis.

## Prerequisites & Installation

The tracker requires Python 3.7+ and relies on system-level GUI libraries (Tkinter).

### 1. System Dependencies

**Linux / Ubuntu / Debian:**
You must install the system python-tk package for the GUI to render.
```bash
sudo apt-get update
sudo apt-get install python3-tk
```
*(If running on a headless server or VM without a display, you must run it inside an `Xvfb` session, e.g., `DISPLAY=:1 python3 keepa_tracker.py`).*

**Windows / macOS:**
Tkinter is generally included with standard Python installations.

### 2. Python Packages

Install all necessary Python dependencies via `pip`:
```bash
pip install -r requirements.txt
```
*(Packages include: `requests`, `python-dotenv`, `pandas`, `pyautogui`, `screeninfo`, `pytz`)*

## Configuration

You must have an active Keepa API Key to fetch data. The application expects this in a `.env.local` file at the root of the project.

Create a file named `.env.local` and add your API key:
```env
Keepa_API_KEY=YOUR_KEEPA_API_KEY_HERE
```
> **Note:** If this file or key is missing, the application will exit immediately upon launch.

## Usage

Simply run the main unified tracker script. All interactions are handled through the launched graphical user interface.

```bash
python3 keepa_tracker.py
```

### Legacy standalone scripts
While the main entry point is recommended, there are individual legacy scripts if you prefer running separate GUIs:
- `buybox_amazon_percent.py` (Main Buybox module)
- `sales_rank_analyzer.py` (Sales rank analytics)

## Privacy & Security

The `.gitignore` has been updated to prevent tracking of local SQLite databases (`*.db`), configuration state (`*.json`), and environment variables (`.env`). Your search history and API keys remain safe and local to your machine. 

## License

MIT 

## Author

Cristalarc / Talavera
