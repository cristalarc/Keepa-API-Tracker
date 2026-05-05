"""
Walmart IP Price Tracker Module
Tracks current prices and sellers for Walmart IP numbers, stores snapshots in SQLite,
and visualizes price history. Mirrors the CompetitorPriceTracker pattern.
"""

import queue
import random
import sqlite3
import threading
import time
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, ttk, messagebox

import pandas as pd

from walmart_ip_manager import load_all_ip_lists
from window_utils import (
    scaled_font, scaled,
    size_and_center_on_parent, clamp_minsize,
)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class WalmartPriceStore:
    """Handles persistent storage for tracked Walmart IP prices using SQLite."""

    def __init__(self, db_path="walmart_price_tracking.db"):
        self.db_path = db_path
        self._initialize_database()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize_database(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS walmart_price_logs (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_name  TEXT NOT NULL,
                    ip_number  TEXT NOT NULL,
                    title      TEXT NOT NULL,
                    seller     TEXT NOT NULL DEFAULT '',
                    price      REAL NOT NULL,
                    currency   TEXT NOT NULL DEFAULT 'USD',
                    tracked_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_walmart_ip_list "
                "ON walmart_price_logs(ip_number, list_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_walmart_tracked_at "
                "ON walmart_price_logs(tracked_at)"
            )
            conn.commit()

    def log_price(self, list_name, ip_number, title, seller, price, currency="USD", tracked_at=None):
        tracked_at = tracked_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO walmart_price_logs
                    (list_name, ip_number, title, seller, price, currency, tracked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (list_name, ip_number, title, seller, price, currency, tracked_at),
            )
            conn.commit()

    def get_latest_price_record(self, ip_number, list_name):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ip_number, title, seller, price, currency, tracked_at
                FROM walmart_price_logs
                WHERE ip_number = ? AND list_name = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ip_number, list_name),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"ip_number": row[0], "title": row[1], "seller": row[2],
                "price": row[3], "currency": row[4], "tracked_at": row[5]}

    def get_previous_price_record(self, ip_number, list_name):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ip_number, title, seller, price, currency, tracked_at
                FROM walmart_price_logs
                WHERE ip_number = ? AND list_name = ?
                ORDER BY id DESC
                LIMIT 1 OFFSET 1
                """,
                (ip_number, list_name),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"ip_number": row[0], "title": row[1], "seller": row[2],
                "price": row[3], "currency": row[4], "tracked_at": row[5]}

    def get_price_history(self, ip_number, list_name, limit=300):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tracked_at, price, seller, title, currency
                FROM walmart_price_logs
                WHERE ip_number = ? AND list_name = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (ip_number, list_name, limit),
            )
            rows = cursor.fetchall()
        rows.reverse()
        return [
            {"tracked_at": r[0], "price": r[1], "seller": r[2],
             "title": r[3], "currency": r[4]}
            for r in rows
        ]

    def get_price_history_rows(self, list_name=None, ip_number=None):
        """Return rows for CSV export."""
        query = (
            "SELECT id, list_name, ip_number, title, seller, price, currency, tracked_at "
            "FROM walmart_price_logs"
        )
        clauses, params = [], []
        if list_name:
            clauses.append("list_name = ?")
            params.append(list_name)
        if ip_number:
            clauses.append("ip_number = ?")
            params.append(ip_number)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY tracked_at ASC, id ASC"

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        export_rows = []
        for row in rows:
            tracked_at = row[7]
            tracked_date = tracked_hour = ""
            try:
                dt = datetime.strptime(tracked_at, "%Y-%m-%d %H:%M:%S")
                tracked_date = dt.strftime("%Y-%m-%d")
                tracked_hour = dt.strftime("%H:00")
            except (TypeError, ValueError):
                pass
            export_rows.append({
                "record_id": row[0], "list_name": row[1], "ip_number": row[2],
                "title": row[3], "seller": row[4],
                "price": float(row[5]) if row[5] is not None else None,
                "currency": row[6], "tracked_at": tracked_at,
                "tracked_date": tracked_date, "tracked_hour": tracked_hour,
            })
        return export_rows


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class WalmartScraper:
    """
    Scrapes current price and seller from Walmart product pages using Playwright.
    Must be called from a background thread — never from the tkinter main thread.
    """

    BASE_URL = "https://www.walmart.com/ip/{ip_number}"
    SCRAPE_DELAY_SECONDS = (2, 4)

    def _make_result(self, ip_number, title=None, price=None, seller=None,
                     error=None, error_code=None):
        return {
            "ip_number": ip_number,
            "title": title or f"IP {ip_number}",
            "price": price,
            "seller": seller or "",
            "error": error,
            "error_code": error_code,
        }

    def _scrape_ip(self, page, ip_number, stop_flag):
        if stop_flag[0]:
            return self._make_result(ip_number, error="Stopped by user", error_code="STOPPED")

        url = self.BASE_URL.format(ip_number=ip_number)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            return self._make_result(ip_number, error=str(exc), error_code="TIMEOUT")

        # Detect bot-block / CAPTCHA
        try:
            page_content = page.content()
            if any(k in page_content for k in ("captcha", "px-captcha", "Access Denied", "Robot Check")):
                return self._make_result(ip_number, error="Bot detection triggered", error_code="BLOCKED")
        except Exception:
            pass

        # Wait for price to appear
        try:
            page.wait_for_selector("[itemprop='price'], [data-testid='price-wrap']", timeout=15000)
        except Exception:
            # Check for 404 / unavailable
            try:
                body = page.inner_text("body")
                if any(k in body for k in ("Item not available", "We couldn't find", "404")):
                    return self._make_result(ip_number, error="Item not found", error_code="NOT_FOUND")
            except Exception:
                pass
            return self._make_result(ip_number, error="Price element not found", error_code="PARSE_ERROR")

        # Extract title
        title = f"IP {ip_number}"
        for sel in (
            "[itemprop='name']",
            "[data-testid='product-title']",
            "h1",
        ):
            try:
                el = page.query_selector(sel)
                if el:
                    text = (el.inner_text() or "").strip()
                    if text:
                        title = text
                        break
            except Exception:
                continue

        # Fallback title from <title> tag
        if title == f"IP {ip_number}":
            try:
                page_title = page.title()
                if page_title:
                    title = page_title.replace(" - Walmart.com", "").strip()
            except Exception:
                pass

        # Extract price — try selectors in priority order, then JSON-LD
        price = None
        price_selectors = [
            "[itemprop='price']",
            "[data-testid='price-wrap'] span",
            "span[class*='price-characteristic']",
        ]
        for sel in price_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    # Prefer the 'content' attribute (schema.org), then inner text
                    raw = el.get_attribute("content") or el.inner_text()
                    raw = raw.replace("$", "").replace(",", "").strip()
                    price = float(raw)
                    break
            except Exception:
                continue

        # JSON-LD fallback
        if price is None:
            try:
                import json as _json
                scripts = page.query_selector_all("script[type='application/ld+json']")
                for script in scripts:
                    try:
                        data = _json.loads(script.inner_text())
                        if isinstance(data, dict) and "offers" in data:
                            offers = data["offers"]
                            if isinstance(offers, list):
                                offers = offers[0]
                            raw = str(offers.get("price", "")).replace("$", "").replace(",", "")
                            if raw:
                                price = float(raw)
                                break
                        elif isinstance(data, dict) and "price" in data:
                            raw = str(data["price"]).replace("$", "").replace(",", "")
                            if raw:
                                price = float(raw)
                                break
                    except Exception:
                        continue
            except Exception:
                pass

        if price is None:
            return self._make_result(ip_number, title=title, error="Price not found on page", error_code="PARSE_ERROR")

        # Extract seller
        seller = "Walmart.com"
        seller_selectors = [
            "[data-testid='seller-info'] a",
            "[data-testid='seller-name']",
            "span[class*='seller']",
        ]
        for sel in seller_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    text = (el.inner_text() or "").strip()
                    if text:
                        seller = text
                        break
            except Exception:
                continue

        # "Sold by" text search fallback
        if seller == "Walmart.com":
            try:
                sold_by_el = page.get_by_text("Sold by", exact=False).first
                if sold_by_el:
                    parent_text = sold_by_el.inner_text().strip()
                    if "Sold by" in parent_text:
                        seller_part = parent_text.split("Sold by", 1)[-1].strip()
                        if seller_part:
                            seller = seller_part
            except Exception:
                pass

        return self._make_result(ip_number, title=title, price=price, seller=seller)

    def run_batch(self, ip_entries, progress_callback, stop_flag):
        """
        Scrape a list of (list_name, ip_number) tuples.

        Args:
            ip_entries: list of (list_name, ip_number) tuples
            progress_callback: callable(current_idx, total, list_name, ip_number)
            stop_flag: list with one bool element; set [0]=True to abort

        Returns:
            list of result dicts with 'list_name' added
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright is not installed.\n"
                "Run: pip install playwright playwright-stealth && playwright install chromium"
            )

        results = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = context.new_page()

            # Apply stealth patch if available
            try:
                from playwright_stealth import Stealth
                Stealth().apply_stealth_sync(page)
            except (ImportError, Exception):
                pass

            total = len(ip_entries)
            for idx, (list_name, ip_number) in enumerate(ip_entries, start=1):
                if stop_flag[0]:
                    break
                progress_callback(idx, total, list_name, ip_number)
                try:
                    result = self._scrape_ip(page, ip_number, stop_flag)
                except Exception as exc:
                    result = self._make_result(
                        ip_number, error=str(exc), error_code="EXCEPTION"
                    )

                # Abort the whole batch on hard bot-block
                if result.get("error_code") == "BLOCKED":
                    result["list_name"] = list_name
                    results.append(result)
                    break

                result["list_name"] = list_name
                results.append(result)

                if idx < total and not stop_flag[0]:
                    delay = random.uniform(*self.SCRAPE_DELAY_SECONDS)
                    time.sleep(delay)

            try:
                context.close()
                browser.close()
            except Exception:
                pass

        return results


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class WalmartPriceTracker:
    """
    Tkinter UI for tracking and visualizing Walmart IP prices.
    Mirrors CompetitorPriceTracker.
    """

    ALL_LISTS = "All Lists"

    def __init__(self):
        self.store = WalmartPriceStore()
        self.scraper = WalmartScraper()

        self.window = None
        self.list_var = None
        self.list_combo = None
        self.batch_listbox = None
        self.status_var = None
        self.results_tree = None
        self.history_tree = None
        self.chart_canvas = None

        self.selected_ip = None
        self.selected_title = None
        self.selected_row_list = None

        self._tracking_thread = None
        self._queue = queue.Queue()
        self._stop_flag = [False]

    def open_window(self, parent=None):
        # Verify Playwright is importable before opening the window
        try:
            import playwright  # noqa: F401
        except ImportError:
            messagebox.showerror(
                "Playwright Not Installed",
                "Playwright is required for Walmart price scraping.\n\n"
                "Install it with:\n"
                "  pip install playwright playwright-stealth\n"
                "  playwright install chromium",
                parent=parent,
            )
            return

        self.window = tk.Toplevel(parent) if parent else tk.Tk()
        self.window.title("Walmart IP Price Tracker")
        self.window.resizable(True, True)
        size_and_center_on_parent(self.window, parent, 1500, 980, max_frac=0.95)
        clamp_minsize(self.window, 1200, 820)
        self.window.lift()
        self.window.attributes("-topmost", True)
        self.window.after_idle(lambda: self.window.attributes("-topmost", False))
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_list_choices()
        self._refresh_latest_for_selected_list()

        if parent:
            self.window.wait_window()
        else:
            self.window.mainloop()

    def _on_close(self):
        self._stop_flag[0] = True
        self.window.destroy()

    def _build_ui(self):
        container = ttk.Frame(self.window, padding="16")
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            container,
            text="Walmart IP Price Tracker",
            font=scaled_font("Arial", 18, "bold"),
        ).pack(anchor=tk.W, pady=(0, 10))

        # --- Controls bar ---
        controls = ttk.Frame(container)
        controls.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(controls, text="View List:").pack(side=tk.LEFT)
        self.list_var = tk.StringVar()
        self.list_combo = ttk.Combobox(
            controls, textvariable=self.list_var, state="readonly", width=35
        )
        self.list_combo.pack(side=tk.LEFT, padx=(8, 8))
        self.list_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._refresh_latest_for_selected_list(),
        )

        ttk.Button(
            controls, text="Refresh Lists", command=self._refresh_list_choices
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            controls,
            text="Export All Price History",
            command=self._export_all_price_history,
        ).pack(side=tk.RIGHT)

        ttk.Button(
            controls,
            text="Export Selected IP History",
            command=self._export_selected_ip_history,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        # --- Batch tracking ---
        batch_frame = ttk.LabelFrame(container, text="Batch Tracking", padding="8")
        batch_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            batch_frame,
            text="Select one or more lists to track (Ctrl/Cmd-click for multiple):",
        ).pack(anchor=tk.W)

        batch_listbox_frame = ttk.Frame(batch_frame)
        batch_listbox_frame.pack(fill=tk.X, pady=(4, 6))

        self.batch_listbox = tk.Listbox(
            batch_listbox_frame, selectmode=tk.EXTENDED, height=6, exportselection=False
        )
        batch_scroll = ttk.Scrollbar(
            batch_listbox_frame, orient=tk.VERTICAL, command=self.batch_listbox.yview
        )
        self.batch_listbox.configure(yscrollcommand=batch_scroll.set)
        self.batch_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        batch_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        batch_buttons = ttk.Frame(batch_frame)
        batch_buttons.pack(fill=tk.X)

        ttk.Button(
            batch_buttons, text="Select All", command=self._select_all_batch_lists
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            batch_buttons, text="Clear", command=self._clear_batch_selection
        ).pack(side=tk.LEFT, padx=(0, 10))

        self._track_btn = ttk.Button(
            batch_buttons,
            text="Track Selected Lists",
            command=self._track_prices_for_selected_lists,
            style="Accent.TButton",
        )
        self._track_btn.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            batch_buttons,
            text="Stop",
            command=self._stop_tracking,
        ).pack(side=tk.LEFT)

        # --- Status label ---
        self.status_var = tk.StringVar(
            value="Select lists in Batch Tracking and click Track. Use View List to inspect history."
        )
        ttk.Label(container, textvariable=self.status_var, foreground="gray").pack(
            anchor=tk.W, pady=(0, 10)
        )

        # --- Results table ---
        results_frame = ttk.LabelFrame(
            container,
            text="Latest Tracked Prices (drops are highlighted)",
            padding="8",
        )
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = (
            "list_name", "ip_number", "title", "seller",
            "current_price", "previous_price", "change", "tracked_at",
        )
        self.results_tree = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=12
        )
        self.results_tree.heading("list_name", text="List")
        self.results_tree.heading("ip_number", text="IP Number")
        self.results_tree.heading("title", text="Product Title")
        self.results_tree.heading("seller", text="Seller")
        self.results_tree.heading("current_price", text="Current Price")
        self.results_tree.heading("previous_price", text="Previous Price")
        self.results_tree.heading("change", text="Change")
        self.results_tree.heading("tracked_at", text="Last Tracked")

        self.results_tree.column("list_name", width=scaled(150), anchor=tk.W)
        self.results_tree.column("ip_number", width=scaled(140), anchor=tk.W)
        self.results_tree.column("title", width=scaled(300), anchor=tk.W)
        self.results_tree.column("seller", width=scaled(200), anchor=tk.W)
        self.results_tree.column("current_price", width=scaled(100), anchor=tk.E)
        self.results_tree.column("previous_price", width=scaled(100), anchor=tk.E)
        self.results_tree.column("change", width=scaled(90), anchor=tk.E)
        self.results_tree.column("tracked_at", width=scaled(160), anchor=tk.W)

        results_scroll = ttk.Scrollbar(
            results_frame, orient=tk.VERTICAL, command=self.results_tree.yview
        )
        self.results_tree.configure(yscrollcommand=results_scroll.set)
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.results_tree.tag_configure("drop", background="#E5F7E6")
        self.results_tree.tag_configure("increase", background="#FFF2E5")
        self.results_tree.tag_configure("no_data", background="#F5F5F5")
        self.results_tree.bind("<<TreeviewSelect>>", self._on_ip_selected)

        # Open in browser toolbar button
        results_toolbar = ttk.Frame(results_frame)
        results_toolbar.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        ttk.Button(
            results_toolbar,
            text="Open in Browser",
            command=self._open_selected_in_browser,
        ).pack(side=tk.LEFT)

        # --- History detail ---
        details_frame = ttk.LabelFrame(
            container, text="Selected IP Price History", padding="8"
        )
        details_frame.pack(fill=tk.BOTH, expand=True)

        self.chart_canvas = tk.Canvas(
            details_frame, bg="white", height=260,
            highlightthickness=1, highlightbackground="#D9D9D9",
        )
        self.chart_canvas.pack(fill=tk.X, expand=False, pady=(0, 8))
        self.chart_canvas.bind(
            "<Configure>", lambda _e: self._redraw_chart_for_selection()
        )

        history_columns = ("tracked_at", "price", "seller", "title")
        self.history_tree = ttk.Treeview(
            details_frame, columns=history_columns, show="headings", height=8
        )
        self.history_tree.heading("tracked_at", text="Tracked At")
        self.history_tree.heading("price", text="Price")
        self.history_tree.heading("seller", text="Seller")
        self.history_tree.heading("title", text="Product Title")
        self.history_tree.column("tracked_at", width=scaled(180), anchor=tk.W)
        self.history_tree.column("price", width=scaled(100), anchor=tk.E)
        self.history_tree.column("seller", width=scaled(200), anchor=tk.W)
        self.history_tree.column("title", width=scaled(600), anchor=tk.W)

        history_scroll = ttk.Scrollbar(
            details_frame, orient=tk.VERTICAL, command=self.history_tree.yview
        )
        self.history_tree.configure(yscrollcommand=history_scroll.set)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # ------------------------------------------------------------------
    # List management helpers
    # ------------------------------------------------------------------

    def _refresh_list_choices(self):
        lists_data = load_all_ip_lists()
        list_names = sorted(lists_data.keys())
        view_options = [self.ALL_LISTS] + list_names
        current_selection = self.list_var.get()
        self.list_combo["values"] = view_options
        self._populate_batch_listbox(list_names)

        if not list_names:
            self.list_var.set("")
            self.status_var.set(
                "No IP lists found. Add lists using the Walmart IP Manager "
                "(coming soon) or create walmart_ips.json manually."
            )
            self._clear_results_table()
            self._clear_history_details()
            return

        if current_selection in view_options:
            self.list_var.set(current_selection)
        elif self.list_var.get() not in view_options:
            self.list_var.set(list_names[0])
        self._refresh_latest_for_selected_list()

    def _populate_batch_listbox(self, list_names):
        if self.batch_listbox is None:
            return
        selected_names = set(self._get_selected_batch_lists())
        self.batch_listbox.delete(0, tk.END)
        for name in list_names:
            self.batch_listbox.insert(tk.END, name)
        if selected_names:
            for idx, name in enumerate(list_names):
                if name in selected_names:
                    self.batch_listbox.selection_set(idx)
        elif self.list_var and self.list_var.get() in list_names:
            self.batch_listbox.selection_set(list_names.index(self.list_var.get()))

    def _get_selected_batch_lists(self):
        if self.batch_listbox is None:
            return []
        return [self.batch_listbox.get(i) for i in self.batch_listbox.curselection()]

    def _select_all_batch_lists(self):
        if self.batch_listbox and self.batch_listbox.size() > 0:
            self.batch_listbox.selection_set(0, tk.END)

    def _clear_batch_selection(self):
        if self.batch_listbox:
            self.batch_listbox.selection_clear(0, tk.END)

    def _clear_results_table(self):
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

    def _clear_history_details(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        self.chart_canvas.delete("all")
        self.chart_canvas.create_text(
            20, 20,
            text="Select an IP row to view chart and history.",
            anchor=tk.NW, fill="#555555",
        )

    # ------------------------------------------------------------------
    # Results table
    # ------------------------------------------------------------------

    def _refresh_latest_for_selected_list(self):
        selected_view = self.list_var.get().strip() if self.list_var else ""
        lists_data = load_all_ip_lists()

        self._clear_results_table()
        self._clear_history_details()
        self.selected_ip = None
        self.selected_title = None
        self.selected_row_list = None

        if not selected_view:
            self.status_var.set("Select a list.")
            return

        if selected_view == self.ALL_LISTS:
            total = 0
            non_empty = 0
            for list_name in sorted(lists_data.keys()):
                ips = lists_data.get(list_name, {}).get("ips", [])
                if ips:
                    non_empty += 1
                for ip in sorted(ips):
                    latest = self.store.get_latest_price_record(ip, list_name)
                    previous = self.store.get_previous_price_record(ip, list_name)
                    self._insert_result_row(list_name, ip, latest, previous)
                    total += 1
            if total == 0:
                self.status_var.set("All lists are empty.")
                return
            self.status_var.set(
                f"Loaded {total} IP rows across {non_empty} list(s). "
                "Select a row to view history."
            )
            return

        ips = lists_data.get(selected_view, {}).get("ips", [])
        if not ips:
            self.status_var.set(f"List '{selected_view}' has no IPs.")
            return

        for ip in sorted(ips):
            latest = self.store.get_latest_price_record(ip, selected_view)
            previous = self.store.get_previous_price_record(ip, selected_view)
            self._insert_result_row(selected_view, ip, latest, previous)

        self.status_var.set(
            f"Loaded {len(ips)} IPs from list '{selected_view}'. "
            "Select a row to view history."
        )

    def _insert_result_row(self, list_name, ip_number, latest, previous):
        if not latest:
            self.results_tree.insert(
                "", tk.END,
                values=(list_name, ip_number, "Not tracked yet", "-", "-", "-", "-", "-"),
                tags=("no_data",),
            )
            return

        current_price = float(latest["price"])
        previous_price = (
            float(previous["price"]) if previous and previous["price"] is not None else None
        )
        change = (current_price - previous_price) if previous_price is not None else None
        change_text = f"{change:+.2f}" if change is not None else "-"
        change_tag = (
            "drop" if change is not None and change < 0
            else "increase" if change is not None and change > 0
            else ""
        )

        self.results_tree.insert(
            "", tk.END,
            values=(
                list_name,
                ip_number,
                latest["title"],
                latest.get("seller", ""),
                f"${current_price:.2f}",
                f"${previous_price:.2f}" if previous_price is not None else "-",
                f"${change_text}" if change is not None else "-",
                latest["tracked_at"],
            ),
            tags=(change_tag,) if change_tag else (),
        )

    # ------------------------------------------------------------------
    # Tracking
    # ------------------------------------------------------------------

    def _track_prices_for_selected_lists(self):
        if self._tracking_thread and self._tracking_thread.is_alive():
            messagebox.showwarning(
                "Already Tracking",
                "A tracking session is already running. Click Stop to abort it first.",
                parent=self.window,
            )
            return

        selected_lists = self._get_selected_batch_lists()
        if not selected_lists:
            messagebox.showwarning(
                "No Lists Selected",
                "Select one or more lists in Batch Tracking first.",
                parent=self.window,
            )
            return

        lists_data = load_all_ip_lists()
        ip_entries = []
        empty_lists = []
        for list_name in selected_lists:
            ips = lists_data.get(list_name, {}).get("ips", [])
            if ips:
                for ip in ips:
                    ip_entries.append((list_name, ip))
            else:
                empty_lists.append(list_name)

        if not ip_entries:
            messagebox.showwarning(
                "No IPs Found",
                "None of the selected lists contain IP numbers.",
                parent=self.window,
            )
            return

        self._stop_flag[0] = False
        self._track_btn.configure(state="disabled")
        self.status_var.set(f"Starting tracking of {len(ip_entries)} IP(s)…")
        self.window.update_idletasks()

        def worker():
            def progress_cb(current, total, list_name, ip_number):
                self._queue.put({
                    "type": "progress",
                    "current": current, "total": total,
                    "list_name": list_name, "ip": ip_number,
                })

            try:
                results = self.scraper.run_batch(ip_entries, progress_cb, self._stop_flag)
                self._queue.put({"type": "done", "results": results, "empty_lists": empty_lists})
            except Exception as exc:
                self._queue.put({"type": "error", "code": "FATAL", "message": str(exc)})

        self._tracking_thread = threading.Thread(target=worker, daemon=True)
        self._tracking_thread.start()
        self.window.after(200, self._poll_queue)

    def _stop_tracking(self):
        self._stop_flag[0] = True
        self.status_var.set("Stopping… waiting for current page to finish.")

    def _poll_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                msg_type = msg.get("type")

                if msg_type == "progress":
                    self.status_var.set(
                        f"Tracking {msg['current']}/{msg['total']} | "
                        f"List '{msg['list_name']}' | IP {msg['ip']}"
                    )
                    self.window.update_idletasks()

                elif msg_type == "done":
                    self._on_tracking_done(msg["results"], msg.get("empty_lists", []))
                    return

                elif msg_type == "error":
                    self._track_btn.configure(state="normal")
                    messagebox.showerror(
                        "Tracking Error",
                        f"Fatal error during tracking:\n\n{msg['message']}",
                        parent=self.window,
                    )
                    self.status_var.set("Tracking failed. See error dialog.")
                    return

        except queue.Empty:
            pass

        if self._tracking_thread and self._tracking_thread.is_alive():
            self.window.after(200, self._poll_queue)

    def _on_tracking_done(self, results, empty_lists):
        self._track_btn.configure(state="normal")

        tracked_count = 0
        errors = []
        blocked = False

        for result in results:
            list_name = result.get("list_name", "")
            ip_number = result.get("ip_number", "")
            error_code = result.get("error_code")

            if error_code == "BLOCKED":
                blocked = True
                errors.append(f"[{list_name}] {ip_number}: Bot detection triggered — batch aborted.")
                break
            elif result.get("error"):
                errors.append(f"[{list_name}] {ip_number}: {result['error']}")
            else:
                self.store.log_price(
                    list_name, ip_number,
                    result["title"], result["seller"], result["price"],
                )
                tracked_count += 1

        self._refresh_latest_for_selected_list()

        summary_lines = [f"Tracked {tracked_count} IP(s)."]

        if empty_lists:
            preview = ", ".join(empty_lists[:5])
            extra = f" (+{len(empty_lists) - 5} more)" if len(empty_lists) > 5 else ""
            summary_lines.append(f"Skipped empty list(s): {preview}{extra}")

        if blocked:
            messagebox.showerror(
                "Bot Detection",
                "Walmart detected the scraper (CAPTCHA or 403).\n\n"
                "Wait a few minutes before trying again. "
                "Consider using a different network or reducing batch size.\n\n"
                + "\n".join(summary_lines),
                parent=self.window,
            )
        elif errors:
            preview = "\n".join(errors[:5])
            extra = f"\n…and {len(errors) - 5} more." if len(errors) > 5 else ""
            messagebox.showwarning(
                "Tracking Completed with Warnings",
                "\n".join(summary_lines) + f"\n\nErrors:\n{preview}{extra}",
                parent=self.window,
            )
        else:
            messagebox.showinfo(
                "Tracking Complete",
                "\n".join(summary_lines),
                parent=self.window,
            )

        self.status_var.set(
            f"Tracking finished. {tracked_count} IP(s) logged. "
            "Price drops are highlighted in green."
        )

    # ------------------------------------------------------------------
    # History detail
    # ------------------------------------------------------------------

    def _on_ip_selected(self, _event):
        selection = self.results_tree.selection()
        if not selection:
            return
        row = self.results_tree.item(selection[0], "values")
        self.selected_row_list = row[0]
        self.selected_ip = row[1]
        self.selected_title = row[2]
        self._load_history_for_ip(self.selected_row_list, self.selected_ip)

    def _load_history_for_ip(self, list_name, ip_number):
        history = self.store.get_price_history(ip_number, list_name)

        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        for record in history:
            self.history_tree.insert(
                "", tk.END,
                values=(
                    record["tracked_at"],
                    f"${float(record['price']):.2f}",
                    record.get("seller", ""),
                    record["title"],
                ),
            )

        self._draw_chart(history)

    def _redraw_chart_for_selection(self):
        if not self.selected_ip or not self.selected_row_list:
            return
        history = self.store.get_price_history(self.selected_ip, self.selected_row_list)
        self._draw_chart(history)

    def _draw_chart(self, history):
        self.chart_canvas.delete("all")
        width = max(self.chart_canvas.winfo_width(), 700)
        height = max(self.chart_canvas.winfo_height(), 260)

        if not history:
            self.chart_canvas.create_text(
                20, 20,
                text="No tracked history yet for this IP.",
                anchor=tk.NW, fill="#555555",
            )
            return

        title_text = self.selected_title or history[-1]["title"]
        ip_label = self.selected_ip or ""
        header = f"{ip_label} | {title_text[:90]}"
        self.chart_canvas.create_text(
            14, 10, text=header, anchor=tk.NW,
            fill="#222222", font=scaled_font("Arial", 10, "bold"),
        )

        left_margin = 70
        right_margin = 20
        top_margin = 35
        bottom_margin = 65
        plot_width = width - left_margin - right_margin
        plot_height = height - top_margin - bottom_margin

        prices = [float(r["price"]) for r in history]
        time_points = [
            datetime.strptime(r["tracked_at"], "%Y-%m-%d %H:%M:%S").timestamp()
            for r in history
        ]

        min_price = min(prices)
        max_price = max(prices)
        if min_price == max_price:
            min_price -= 1
            max_price += 1

        min_time = min(time_points)
        max_time = max(time_points)
        if min_time == max_time:
            max_time += 1

        def map_x(ts):
            return left_margin + ((ts - min_time) / (max_time - min_time)) * plot_width

        def map_y(p):
            return top_margin + ((1 - (p - min_price) / (max_price - min_price)) * plot_height)

        self.chart_canvas.create_line(
            left_margin, top_margin, left_margin, top_margin + plot_height, fill="#666666"
        )
        self.chart_canvas.create_line(
            left_margin, top_margin + plot_height,
            left_margin + plot_width, top_margin + plot_height, fill="#666666",
        )

        for i in range(5):
            ratio = i / 4
            price_tick = max_price - ratio * (max_price - min_price)
            y = top_margin + ratio * plot_height
            self.chart_canvas.create_line(left_margin - 5, y, left_margin, y, fill="#666666")
            self.chart_canvas.create_text(
                left_margin - 8, y, text=f"${price_tick:.2f}",
                anchor=tk.E, fill="#444444", font=scaled_font("Arial", 8),
            )

        x_tick_indices = sorted({0, len(history) // 2, len(history) - 1})
        for idx in x_tick_indices:
            x = map_x(time_points[idx])
            label = datetime.strptime(history[idx]["tracked_at"], "%Y-%m-%d %H:%M:%S").strftime("%m-%d %H:%M")
            self.chart_canvas.create_line(
                x, top_margin + plot_height, x, top_margin + plot_height + 5, fill="#666666"
            )
            self.chart_canvas.create_text(
                x, top_margin + plot_height + 18, text=label,
                anchor=tk.N, fill="#444444", font=scaled_font("Arial", 8),
            )

        points = []
        for ts, p in zip(time_points, prices):
            points.extend([map_x(ts), map_y(p)])

        if len(points) >= 4:
            self.chart_canvas.create_line(*points, fill="#1F77B4", width=2, smooth=True)
        for i in range(0, len(points), 2):
            x_c, y_c = points[i], points[i + 1]
            self.chart_canvas.create_oval(
                x_c - 2.5, y_c - 2.5, x_c + 2.5, y_c + 2.5,
                fill="#1F77B4", outline="#1F77B4",
            )

    # ------------------------------------------------------------------
    # Browser integration
    # ------------------------------------------------------------------

    def _open_selected_in_browser(self):
        selection = self.results_tree.selection()
        if not selection:
            messagebox.showwarning(
                "No Row Selected",
                "Select an IP row first.",
                parent=self.window,
            )
            return
        row = self.results_tree.item(selection[0], "values")
        ip_number = row[1]
        webbrowser.open(f"https://www.walmart.com/ip/{ip_number}")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_history_rows(self, rows, default_filename):
        if not rows:
            messagebox.showinfo(
                "No Data", "No historical rows found for export.", parent=self.window
            )
            return
        save_path = filedialog.asksaveasfilename(
            title="Export price history",
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            parent=self.window,
        )
        if not save_path:
            return
        pd.DataFrame(rows).to_csv(save_path, index=False)
        messagebox.showinfo(
            "Export Complete",
            f"Saved {len(rows)} rows to:\n{save_path}",
            parent=self.window,
        )

    def _export_all_price_history(self):
        rows = self.store.get_price_history_rows()
        self._export_history_rows(rows, "walmart_price_history_all.csv")

    def _export_selected_ip_history(self):
        if not self.selected_ip or not self.selected_row_list:
            messagebox.showwarning(
                "No IP Selected",
                "Select an IP row first, then export.",
                parent=self.window,
            )
            return
        rows = self.store.get_price_history_rows(
            list_name=self.selected_row_list, ip_number=self.selected_ip
        )
        filename = (
            f"walmart_history_{self.selected_row_list}_{self.selected_ip}.csv"
            .replace(" ", "_")
        )
        self._export_history_rows(rows, filename)
