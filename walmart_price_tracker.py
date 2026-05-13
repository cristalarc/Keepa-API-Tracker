"""
Walmart IP Price Tracker Module
Tracks current prices and sellers for Walmart IP numbers, stores snapshots in SQLite,
and visualizes price history. Mirrors the CompetitorPriceTracker pattern.
"""

import queue
import random
import json
import re
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

try:
    import seleniumbase
    from seleniumbase import SB
    HAS_SELENIUMBASE = True
except ImportError:
    SB = None
    HAS_SELENIUMBASE = False

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
    Scrapes current price and seller from Walmart product pages using SeleniumBase.
    Must be called from a background thread — never from the tkinter main thread.
    """

    BASE_URL = "https://www.walmart.com/ip/{ip_number}"
    SCRAPE_DELAY_SECONDS = (8, 15)

    def _make_result(self, ip_number, title=None, price=None, seller=None,
                     error=None, error_code=None, debug=None):
        return {
            "ip_number": ip_number,
            "title": title or f"IP {ip_number}",
            "price": price,
            "seller": seller or "",
            "error": error,
            "error_code": error_code,
            "debug": debug or "",
        }

    def _safe_get_text(self, sb, selector):
        try:
            if sb.is_element_present(selector):
                return sb.get_text(selector).strip()
        except Exception:
            return ""
        return ""

    def _extract_price_from_text(self, raw_text):
        if raw_text is None:
            return None
        raw = str(raw_text).replace(",", " ")
        for token in re.findall(r"\d+(?:\.\d{1,2})?", raw):
            try:
                value = float(token)
            except ValueError:
                continue
            if value > 0:
                return value
        return None

    def _extract_price_from_json_node(self, node):
        if isinstance(node, list):
            for item in node:
                value = self._extract_price_from_json_node(item)
                if value is not None:
                    return value
            return None

        if isinstance(node, dict):
            for key in ("price", "lowPrice", "highPrice"):
                if key in node:
                    value = self._extract_price_from_text(node.get(key))
                    if value is not None:
                        return value
            for key in ("offers", "@graph", "mainEntity", "itemOffered"):
                if key in node:
                    value = self._extract_price_from_json_node(node.get(key))
                    if value is not None:
                        return value
            for value in node.values():
                nested = self._extract_price_from_json_node(value)
                if nested is not None:
                    return nested
        return None

    def _extract_price_from_json_ld(self, sb):
        try:
            if not sb.is_element_present("script[type='application/ld+json']"):
                return None
            scripts = sb.find_elements("script[type='application/ld+json']")
        except Exception:
            return None

        for script in scripts:
            try:
                payload = script.get_attribute("innerHTML")
                if not payload:
                    continue
                data = json.loads(payload)
            except Exception:
                continue
            value = self._extract_price_from_json_node(data)
            if value is not None:
                return value
        return None

    def _extract_title(self, sb, ip_number):
        title = f"IP {ip_number}"
        for sel in (
            "[itemprop='name']",
            "[data-testid='product-title']",
            "h1",
            "[data-automation-id='product-title']",
        ):
            text = self._safe_get_text(sb, sel)
            if text:
                return text
        try:
            page_title = sb.get_title()
        except Exception:
            page_title = ""
        if page_title:
            return page_title.replace(" - Walmart.com", "").strip()
        return title

    def _extract_price_from_next_data(self, sb):
        """
        Walmart embeds product data in <script id="__NEXT_DATA__">.
        Pull the canonical current price from there.

        Preferred path: props.pageProps.initialData.data.product.priceInfo.currentPrice.price
        Fallback path:  props.pageProps.initialData.data.product.conditionOffers[0].price.price
        Last resort:    recursive scan of the parsed JSON for price-shaped values.
        """
        try:
            if not sb.is_element_present("script#__NEXT_DATA__"):
                return None
            raw = sb.execute_script(
                "var el=document.getElementById('__NEXT_DATA__');"
                "return el ? el.textContent : null;"
            )
            if not raw:
                return None
            data = json.loads(raw)
        except Exception:
            return None

        try:
            product = data["props"]["pageProps"]["initialData"]["data"]["product"]
        except (KeyError, TypeError):
            product = None

        if isinstance(product, dict):
            price_info = product.get("priceInfo") or {}
            current_price = price_info.get("currentPrice") or {}
            value = current_price.get("price")
            if isinstance(value, (int, float)) and value > 0:
                return float(value)

            offers = product.get("conditionOffers") or []
            if isinstance(offers, list) and offers:
                first_offer = offers[0] or {}
                offer_price = first_offer.get("price") or {}
                value = offer_price.get("price") if isinstance(offer_price, dict) else None
                if isinstance(value, (int, float)) and value > 0:
                    return float(value)

        return self._extract_price_from_json_node(data)

    def _extract_price(self, sb):
        # 1) Canonical source — Walmart's embedded Next.js state.
        price = self._extract_price_from_next_data(sb)
        if price is not None:
            return price, "next-data"

        # 2) DOM fallback — current Walmart PDP price-bearing containers.
        price_selectors = [
            "[itemprop='price']",
            "span[itemprop='price']",
            "[data-fs-element='price']",
            "[data-automation-id='product-price']",
            "[data-testid='price-wrap'] [itemprop='price']",
            "[data-testid='price-wrap'] [data-automation-id='product-price']",
            "[data-testid='price-wrap']",
            "[data-testid='hero-price-container']",
            "[data-testid='product-price']",
            "[data-testid='min-max-price']",
            "[data-testid='price-current']",
            "span[class*='price-characteristic']",
        ]

        for sel in price_selectors:
            try:
                if not sb.is_element_present(sel):
                    continue
            except Exception:
                continue

            raw = None
            # `get_attribute` raises in seleniumbase when the attribute is absent.
            # Isolate it so we always fall through to `get_text`.
            try:
                raw = sb.get_attribute(sel, "content")
            except Exception:
                raw = None
            if not raw:
                try:
                    raw = sb.get_text(sel)
                except Exception:
                    raw = None

            price = self._extract_price_from_text(raw)
            if price is not None:
                return price, f"selector:{sel}"

        # 3) Legacy JSON-LD fallback (Walmart no longer emits product price here,
        #    but keep it as a safety net for older variants).
        price = self._extract_price_from_json_ld(sb)
        if price is not None:
            return price, "json-ld"
        return None, "none"

    def _has_product_markers(self, sb):
        """
        Strong PDP markers only. Bare h1 and [itemprop='name'] also appear on
        Walmart's 404 page, so they cannot be trusted as PDP evidence.
        """
        product_selectors = (
            "[data-testid='product-title']",
            "[data-automation-id='product-title']",
            "[itemprop='price']",
            "[data-testid='price-wrap']",
            "[data-automation-id='product-price']",
            "[data-fs-element='price']",
            "[data-automation-id='add-to-cart-button']",
            "button[aria-label*='Add to cart']",
        )
        for sel in product_selectors:
            try:
                if sb.is_element_present(sel):
                    return True
            except Exception:
                continue
        return False

    def _detect_challenge(self, sb):
        signals = []
        source = ""
        body = ""
        title = ""
        current_url = ""

        try:
            source = sb.get_page_source() or ""
        except Exception:
            source = ""
        try:
            body = sb.get_text("body") or ""
        except Exception:
            body = ""
        try:
            title = sb.get_title() or ""
        except Exception:
            title = ""
        try:
            current_url = sb.get_current_url() or ""
        except Exception:
            current_url = ""

        combined = " ".join((source.lower(), body.lower(), title.lower()))
        strict_phrases = (
            "verify you are human",
            "robot check",
            "unusual traffic",
            "px-captcha",
            "press and hold",
            "access denied",
        )
        for phrase in strict_phrases:
            if phrase in combined:
                signals.append(phrase)

        for sel in (
            "iframe[src*='captcha']",
            "[id*='px-captcha']",
            "[class*='px-captcha']",
            "form[action*='captcha']",
        ):
            try:
                if sb.is_element_present(sel):
                    signals.append(f"selector:{sel}")
            except Exception:
                continue

        if "captcha" in current_url.lower():
            signals.append("url:captcha")

        unique_signals = sorted(set(signals))
        high_confidence = len(unique_signals) >= 2
        return {
            "high_confidence": high_confidence,
            "suspicious": bool(unique_signals),
            "signal_count": len(unique_signals),
            "signals": unique_signals,
        }

    def _wait_for_product_ready(self, sb):
        readiness_selectors = (
            "[data-testid='product-title']",
            "h1",
            "[itemprop='name']",
            "[itemprop='price']",
            "[data-testid='price-wrap']",
            "[data-testid='buy-box-container']",
        )
        for _ in range(4):
            for sel in readiness_selectors:
                try:
                    if sb.is_element_present(sel):
                        return True
                except Exception:
                    continue
            try:
                sb.wait_for_element_present(
                    "[data-testid='product-title'], h1, [itemprop='price'], [data-testid='price-wrap']",
                    timeout=4,
                )
                return True
            except Exception:
                continue
        return self._has_product_markers(sb)

    def _extract_seller(self, sb):
        seller = "Walmart.com"
        seller_selectors = [
            "[data-testid='seller-info'] a",
            "[data-testid='seller-name']",
            "span[class*='seller']",
            "[data-testid='product-seller-info'] a",
        ]
        for sel in seller_selectors:
            text = self._safe_get_text(sb, sel)
            if text:
                return text

        try:
            if sb.is_text_visible("Sold by", "body"):
                elements = sb.find_elements("//*[contains(text(), 'Sold by')]")
                for el in elements:
                    parent_text = el.text.strip()
                    if "Sold by" not in parent_text:
                        continue
                    seller_part = parent_text.split("Sold by", 1)[-1].strip()
                    if seller_part:
                        return seller_part
        except Exception:
            pass
        return seller

    def _scrape_ip(self, sb, ip_number, stop_flag):
        if stop_flag[0]:
            return self._make_result(ip_number, error="Stopped by user", error_code="STOPPED")

        url = self.BASE_URL.format(ip_number=ip_number)
        try:
            sb.uc_open_with_reconnect(url, 4)
        except Exception as exc:
            return self._make_result(ip_number, error=str(exc), error_code="TIMEOUT")

        challenge_before = self._detect_challenge(sb)
        if challenge_before["suspicious"] and not self._has_product_markers(sb):
            try:
                print("Challenge detected. Solve it in the browser window if prompted...")
                sb.sleep(30)
            except Exception:
                pass
            challenge_after = self._detect_challenge(sb)
            if challenge_after["high_confidence"] and not self._has_product_markers(sb):
                return self._make_result(
                    ip_number,
                    error="Bot detection triggered",
                    error_code="BLOCKED",
                    debug="challenge=" + ",".join(challenge_after["signals"]),
                )

        page_ready = self._wait_for_product_ready(sb)
        title = self._extract_title(sb, ip_number)
        not_found_title_phrases = (
            "we couldn't find this page",
            "we couldn\u2019t find this page",
            "page not found",
            "item not available",
        )
        title_lower = (title or "").lower().strip()
        if not self._has_product_markers(sb) and any(
            phrase in title_lower for phrase in not_found_title_phrases
        ):
            return self._make_result(
                ip_number, title=title, error="Item not found", error_code="NOT_FOUND"
            )

        if not page_ready:
            return self._make_result(
                ip_number,
                title=title,
                error="Product page loaded but key content did not render in time",
                error_code="PARSE_TIMEOUT",
            )

        price, price_strategy = self._extract_price(sb)
        if price is None:
            debug_bits = [f"price_strategy={price_strategy}"]
            challenge_now = self._detect_challenge(sb)
            if challenge_now["suspicious"]:
                debug_bits.append("challenge=" + ",".join(challenge_now["signals"]))
            return self._make_result(
                ip_number,
                title=title,
                error="Product page loaded but no parseable price was found",
                error_code="PRICE_NOT_FOUND",
                debug=" | ".join(debug_bits),
            )

        seller = self._extract_seller(sb)
        return self._make_result(
            ip_number,
            title=title,
            price=price,
            seller=seller,
            debug=f"price_strategy={price_strategy}",
        )

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
        if not HAS_SELENIUMBASE:
            raise RuntimeError(
                "SeleniumBase is not installed.\n"
                "Run: pip install seleniumbase"
            )

        results = []

        try:
            with SB(uc=True, headless=False) as sb:
                total = len(ip_entries)
                for idx, (list_name, ip_number) in enumerate(ip_entries, start=1):
                    if stop_flag[0]:
                        break
                    progress_callback(idx, total, list_name, ip_number)
                    try:
                        result = self._scrape_ip(sb, ip_number, stop_flag)
                    except Exception as exc:
                        result = self._make_result(
                            ip_number, error=str(exc), error_code="EXCEPTION"
                        )

                    # Abort only when challenge signals remain high confidence.
                    if result.get("error_code") == "BLOCKED":
                        result["list_name"] = list_name
                        results.append(result)
                        break

                    result["list_name"] = list_name
                    results.append(result)

                    if idx < total and not stop_flag[0]:
                        delay = random.uniform(*self.SCRAPE_DELAY_SECONDS)
                        time.sleep(delay)
        except Exception as e:
            return [{"ip_number": "", "list_name": "", "error": f"Failed to launch browser: {str(e)}", "error_code": "EXCEPTION"}]

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
        # Verify SeleniumBase is importable before opening the window
        if not HAS_SELENIUMBASE:
            messagebox.showerror(
                "SeleniumBase Not Installed",
                "SeleniumBase is required for Walmart price scraping.\n\n"
                "Install it with:\n"
                "  pip install seleniumbase undetected-chromedriver",
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
