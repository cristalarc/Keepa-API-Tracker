# AGENTS.md

## Cursor Cloud specific instructions

### Overview
This is a Python tkinter desktop GUI application (Keepa API Tracker) for Amazon product analytics via the Keepa API. There is no web server, no database, and no Docker. The entire app is GUI-based.

### Running the application
```
DISPLAY=:1 python3 keepa_tracker.py
```
The app requires a valid `Keepa_API_KEY` in `.env.local` (loaded via `python-dotenv`). If the key is missing, the app exits immediately. In Cloud Agent VMs, the key is injected as an environment variable; create `.env.local` from it:
```
echo "Keepa_API_KEY=$Keepa_API_KEY" > .env.local
```

### Key caveats
- **`requirements.txt` is incomplete**: It only lists `requests`, `python-dotenv`, `pandas`. The code also requires `pyautogui`, `screeninfo`, and `pytz`. Install all with: `pip install -r requirements.txt pyautogui screeninfo pytz`.
- **System dependency**: `python3-tk` must be installed via apt for tkinter GUI.
- **Display required**: All interactions are GUI-based (tkinter). Xvfb is pre-configured at `DISPLAY=:1` on Cloud Agent VMs.
- **No tests or linter**: The project has no automated test suite, no linter config, and no build system. Use `python3 -m py_compile <file>` for basic syntax validation.
- **Standalone scripts**: `buybox_amazon_percent.py` and `sales_rank_analyzer.py` are legacy standalone scripts with their own GUIs. The unified entry point is `keepa_tracker.py`.
