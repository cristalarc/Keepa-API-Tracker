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
from tkinter import filedialog, simpledialog, ttk, messagebox

import pandas as pd

from walmart_ip_manager import load_all_ip_lists
from walmart_zip_switcher import WalmartZipSwitcher
from window_utils import (
    scaled_font, scaled,
    size_and_center_on_parent, clamp_minsize,
)
from zip_list_manager import (
    load_all_zip_lists,
    parse_zip_list,
    save_zip_list,
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
                    zip_code   TEXT NOT NULL DEFAULT '',
                    tracked_at TEXT NOT NULL
                )
                """
            )

            # Idempotent migration: older databases predate the zip_code column.
            # Detect via PRAGMA and ADD COLUMN with a safe default so existing
            # rows become legacy (zip_code='') entries.
            cursor.execute("PRAGMA table_info(walmart_price_logs)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            if "zip_code" not in existing_columns:
                cursor.execute(
                    "ALTER TABLE walmart_price_logs "
                    "ADD COLUMN zip_code TEXT NOT NULL DEFAULT ''"
                )

            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_walmart_ip_list "
                "ON walmart_price_logs(ip_number, list_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_walmart_ip_list_zip "
                "ON walmart_price_logs(ip_number, list_name, zip_code)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_walmart_tracked_at "
                "ON walmart_price_logs(tracked_at)"
            )
            conn.commit()

    def log_price(self, list_name, ip_number, title, seller, price,
                  currency="USD", zip_code="", tracked_at=None):
        tracked_at = tracked_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        zip_code = (zip_code or "").strip()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO walmart_price_logs
                    (list_name, ip_number, title, seller, price,
                     currency, zip_code, tracked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (list_name, ip_number, title, seller, price,
                 currency, zip_code, tracked_at),
            )
            conn.commit()

    def get_latest_price_record(self, ip_number, list_name, zip_code=""):
        zip_code = (zip_code or "").strip()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ip_number, title, seller, price, currency, zip_code, tracked_at
                FROM walmart_price_logs
                WHERE ip_number = ? AND list_name = ? AND zip_code = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ip_number, list_name, zip_code),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"ip_number": row[0], "title": row[1], "seller": row[2],
                "price": row[3], "currency": row[4],
                "zip_code": row[5], "tracked_at": row[6]}

    def get_previous_price_record(self, ip_number, list_name, zip_code=""):
        zip_code = (zip_code or "").strip()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ip_number, title, seller, price, currency, zip_code, tracked_at
                FROM walmart_price_logs
                WHERE ip_number = ? AND list_name = ? AND zip_code = ?
                ORDER BY id DESC
                LIMIT 1 OFFSET 1
                """,
                (ip_number, list_name, zip_code),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"ip_number": row[0], "title": row[1], "seller": row[2],
                "price": row[3], "currency": row[4],
                "zip_code": row[5], "tracked_at": row[6]}

    def get_price_history(self, ip_number, list_name, zip_code="", limit=300):
        zip_code = (zip_code or "").strip()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tracked_at, price, seller, title, currency, zip_code
                FROM walmart_price_logs
                WHERE ip_number = ? AND list_name = ? AND zip_code = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (ip_number, list_name, zip_code, limit),
            )
            rows = cursor.fetchall()
        rows.reverse()
        return [
            {"tracked_at": r[0], "price": r[1], "seller": r[2],
             "title": r[3], "currency": r[4], "zip_code": r[5]}
            for r in rows
        ]

    def get_distinct_zips(self, list_name=None):
        """
        Return sorted list of ZIPs that have data, optionally filtered by list.

        Args:
            list_name (str | None): Optional list filter.

        Returns:
            list[str]: Distinct ZIP codes (may include '' for legacy rows).
        """
        query = "SELECT DISTINCT zip_code FROM walmart_price_logs"
        params = []
        if list_name:
            query += " WHERE list_name = ?"
            params.append(list_name)
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
        zips = sorted({(row[0] or "") for row in rows})
        return zips

    def get_distinct_ip_zip_pairs(self, list_name):
        """
        Return (ip_number, zip_code) pairs with at least one record for a list.

        Args:
            list_name (str): List filter.

        Returns:
            list[tuple[str, str]]: Sorted (ip, zip) pairs.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT ip_number, zip_code
                FROM walmart_price_logs
                WHERE list_name = ?
                ORDER BY ip_number, zip_code
                """,
                (list_name,),
            )
            rows = cursor.fetchall()
        return [(row[0], row[1] or "") for row in rows]

    def get_price_history_rows(self, list_name=None, ip_number=None, zip_code=None):
        """Return rows for CSV export. ZIP filter accepts '' for legacy rows."""
        query = (
            "SELECT id, list_name, ip_number, title, seller, "
            "price, currency, zip_code, tracked_at "
            "FROM walmart_price_logs"
        )
        clauses, params = [], []
        if list_name:
            clauses.append("list_name = ?")
            params.append(list_name)
        if ip_number:
            clauses.append("ip_number = ?")
            params.append(ip_number)
        if zip_code is not None:
            clauses.append("zip_code = ?")
            params.append(zip_code)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY tracked_at ASC, id ASC"

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        export_rows = []
        for row in rows:
            tracked_at = row[8]
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
                "currency": row[6], "zip_code": row[7] or "",
                "tracked_at": tracked_at,
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

    Composition: a WalmartZipSwitcher handles changing Walmart's delivery ZIP
    so this scraper stays focused on parsing PDP content.
    """

    BASE_URL = "https://www.walmart.com/ip/{ip_number}"
    SCRAPE_DELAY_SECONDS = (8, 15)

    def __init__(self, zip_switcher=None):
        # Dependency-inject the switcher so it can be replaced in tests.
        self.zip_switcher = zip_switcher or WalmartZipSwitcher()

    def _make_result(self, ip_number, title=None, price=None, seller=None,
                     error=None, error_code=None, debug=None, zip_code=""):
        return {
            "ip_number": ip_number,
            "title": title or f"IP {ip_number}",
            "price": price,
            "seller": seller or "",
            "zip_code": zip_code or "",
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

    def _scrape_ip(self, sb, ip_number, stop_flag, zip_code=""):
        if stop_flag[0]:
            return self._make_result(
                ip_number, error="Stopped by user", error_code="STOPPED",
                zip_code=zip_code,
            )

        url = self.BASE_URL.format(ip_number=ip_number)
        try:
            sb.uc_open_with_reconnect(url, 4)
        except Exception as exc:
            return self._make_result(
                ip_number, error=str(exc), error_code="TIMEOUT", zip_code=zip_code,
            )

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
                    zip_code=zip_code,
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
                ip_number, title=title, error="Item not found",
                error_code="NOT_FOUND", zip_code=zip_code,
            )

        if not page_ready:
            return self._make_result(
                ip_number,
                title=title,
                error="Product page loaded but key content did not render in time",
                error_code="PARSE_TIMEOUT",
                zip_code=zip_code,
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
                zip_code=zip_code,
            )

        seller = self._extract_seller(sb)
        return self._make_result(
            ip_number,
            title=title,
            price=price,
            seller=seller,
            debug=f"price_strategy={price_strategy}",
            zip_code=zip_code,
        )

    def run_batch(self, ip_entries, zip_codes, progress_callback, stop_flag):
        """
        Scrape (list_name, ip_number) entries across one or more ZIPs.

        Iteration strategy: outer-ZIP, inner-IP. Walmart caches the location
        in cookies for the session, so we set the ZIP once per ZIP and then
        scrape every IP under that ZIP before moving on. This minimises the
        number of "open sidebar / type ZIP / Save" UI steps.

        Args:
            ip_entries: list of (list_name, ip_number) tuples.
            zip_codes:  list[str] of 5-digit ZIPs, or None/[] for the
                        existing zip-agnostic flow (zip_code='' in results).
            progress_callback: callable
                (zip_idx, zip_total, ip_idx, ip_total,
                 current_zip, list_name, ip_number)
            stop_flag: list with one bool element; set [0]=True to abort.

        Returns:
            list of result dicts. Each result includes 'list_name' and
            'zip_code' keys ('' when no ZIP loop is in effect).
        """
        if not HAS_SELENIUMBASE:
            raise RuntimeError(
                "SeleniumBase is not installed.\n"
                "Run: pip install seleniumbase"
            )

        # Empty/None ZIPs => one zip-agnostic pass with empty-string ZIP.
        zip_list = [str(z).strip()[:5] for z in (zip_codes or []) if str(z).strip()]
        if not zip_list:
            zip_list = [""]

        results = []
        ip_total = len(ip_entries)
        zip_total = len(zip_list)

        try:
            with SB(uc=True, headless=False) as sb:
                for zip_idx, current_zip in enumerate(zip_list, start=1):
                    if stop_flag[0]:
                        break

                    # When ZIP is requested, ensure cookies are set BEFORE the
                    # per-IP scrape loop. The location pill only appears once
                    # we've loaded a real Walmart page, so we open the first
                    # IP's PDP just to drive the sidebar.
                    if current_zip:
                        try:
                            first_url = self.BASE_URL.format(ip_number=ip_entries[0][1])
                            sb.uc_open_with_reconnect(first_url, 4)
                        except Exception as exc:
                            err_msg = f"Failed to open Walmart for ZIP switch: {exc}"
                            for list_name, ip_number in ip_entries:
                                err_result = self._make_result(
                                    ip_number, error=err_msg,
                                    error_code="ZIP_SET_FAILED",
                                    zip_code=current_zip,
                                )
                                err_result["list_name"] = list_name
                                results.append(err_result)
                            continue

                        ok, err = self.zip_switcher.set_zip(sb, current_zip)
                        if not ok:
                            for list_name, ip_number in ip_entries:
                                err_result = self._make_result(
                                    ip_number,
                                    error=err or "ZIP switch failed",
                                    error_code="ZIP_SET_FAILED",
                                    zip_code=current_zip,
                                )
                                err_result["list_name"] = list_name
                                results.append(err_result)
                            continue

                    blocked = False
                    for ip_idx, (list_name, ip_number) in enumerate(ip_entries, start=1):
                        if stop_flag[0]:
                            break
                        progress_callback(zip_idx, zip_total, ip_idx, ip_total,
                                          current_zip, list_name, ip_number)
                        try:
                            result = self._scrape_ip(
                                sb, ip_number, stop_flag, zip_code=current_zip
                            )
                        except Exception as exc:
                            result = self._make_result(
                                ip_number, error=str(exc),
                                error_code="EXCEPTION", zip_code=current_zip,
                            )

                        result["list_name"] = list_name
                        results.append(result)

                        # Bot detection still aborts the entire batch.
                        if result.get("error_code") == "BLOCKED":
                            blocked = True
                            break

                        if ip_idx < ip_total and not stop_flag[0]:
                            delay = random.uniform(*self.SCRAPE_DELAY_SECONDS)
                            time.sleep(delay)

                    if blocked:
                        break
        except Exception as e:
            return [{
                "ip_number": "", "list_name": "", "zip_code": "",
                "error": f"Failed to launch browser: {str(e)}",
                "error_code": "EXCEPTION",
            }]

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
    NO_ZIP_FILTER_LABEL = "(No ZIP filter)"
    ALL_ZIPS_LABEL = "All ZIPs"
    NO_ZIP_VIEW_LABEL = "(No ZIP)"

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

        # ZIP picker widgets / state
        self.zip_list_var = None
        self.zip_list_combo = None
        self.zip_preview_var = None
        self.zip_view_var = None
        self.zip_view_combo = None

        # Selected row state (note: zip_code is the third column now)
        self.selected_ip = None
        self.selected_title = None
        self.selected_row_list = None
        self.selected_zip = ""

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

        # --- ZIP picker (optional) ---
        # Saved ZIP lists come from zip_list_manager.py, shared with the
        # Delivery Speed Tracker. Picking "(No ZIP filter)" keeps the original
        # zip-agnostic flow, where rows are stored with zip_code=''.
        zip_picker_frame = ttk.Frame(batch_frame)
        zip_picker_frame.pack(fill=tk.X, pady=(4, 6))

        ttk.Label(zip_picker_frame, text="ZIP List:").pack(side=tk.LEFT)
        self.zip_list_var = tk.StringVar(value=self.NO_ZIP_FILTER_LABEL)
        self.zip_list_combo = ttk.Combobox(
            zip_picker_frame,
            textvariable=self.zip_list_var,
            state="readonly",
            width=32,
        )
        self.zip_list_combo.pack(side=tk.LEFT, padx=(8, 8))
        self.zip_list_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._on_zip_list_selected()
        )

        ttk.Button(
            zip_picker_frame, text="Refresh ZIPs", command=self._refresh_zip_choices
        ).pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(
            zip_picker_frame, text="Manage ZIP Lists...",
            command=self._open_zip_list_manager,
        ).pack(side=tk.LEFT)

        self.zip_preview_var = tk.StringVar(value="No ZIP filter (single default-ZIP pass)")
        ttk.Label(
            batch_frame,
            textvariable=self.zip_preview_var,
            foreground="gray",
        ).pack(anchor=tk.W, pady=(0, 4))

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

        # View ZIPs filter — narrows the results table to a specific ZIP.
        view_zip_bar = ttk.Frame(results_frame)
        view_zip_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
        ttk.Label(view_zip_bar, text="View ZIPs:").pack(side=tk.LEFT)
        self.zip_view_var = tk.StringVar(value=self.ALL_ZIPS_LABEL)
        self.zip_view_combo = ttk.Combobox(
            view_zip_bar,
            textvariable=self.zip_view_var,
            state="readonly",
            width=18,
        )
        self.zip_view_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.zip_view_combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._refresh_latest_for_selected_list(),
        )

        columns = (
            "list_name", "ip_number", "zip_code", "title", "seller",
            "current_price", "previous_price", "change", "tracked_at",
        )
        self.results_tree = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=12
        )
        self.results_tree.heading("list_name", text="List")
        self.results_tree.heading("ip_number", text="IP Number")
        self.results_tree.heading("zip_code", text="ZIP")
        self.results_tree.heading("title", text="Product Title")
        self.results_tree.heading("seller", text="Seller")
        self.results_tree.heading("current_price", text="Current Price")
        self.results_tree.heading("previous_price", text="Previous Price")
        self.results_tree.heading("change", text="Change")
        self.results_tree.heading("tracked_at", text="Last Tracked")

        self.results_tree.column("list_name", width=scaled(150), anchor=tk.W)
        self.results_tree.column("ip_number", width=scaled(140), anchor=tk.W)
        self.results_tree.column("zip_code", width=scaled(70), anchor=tk.W)
        self.results_tree.column("title", width=scaled(280), anchor=tk.W)
        self.results_tree.column("seller", width=scaled(180), anchor=tk.W)
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

        history_columns = ("tracked_at", "zip_code", "price", "seller", "title")
        self.history_tree = ttk.Treeview(
            details_frame, columns=history_columns, show="headings", height=8
        )
        self.history_tree.heading("tracked_at", text="Tracked At")
        self.history_tree.heading("zip_code", text="ZIP")
        self.history_tree.heading("price", text="Price")
        self.history_tree.heading("seller", text="Seller")
        self.history_tree.heading("title", text="Product Title")
        self.history_tree.column("tracked_at", width=scaled(180), anchor=tk.W)
        self.history_tree.column("zip_code", width=scaled(70), anchor=tk.W)
        self.history_tree.column("price", width=scaled(100), anchor=tk.E)
        self.history_tree.column("seller", width=scaled(180), anchor=tk.W)
        self.history_tree.column("title", width=scaled(540), anchor=tk.W)

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

        # Keep ZIP picker + View ZIPs combobox in sync with the lists view.
        self._refresh_zip_choices()

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

    # ------------------------------------------------------------------
    # ZIP picker helpers
    # ------------------------------------------------------------------

    def _refresh_zip_choices(self):
        """Reload saved ZIP lists + rebuild the View ZIPs filter values."""
        if self.zip_list_combo is None:
            return

        zip_lists = load_all_zip_lists()
        names = sorted(zip_lists.keys())
        values = [self.NO_ZIP_FILTER_LABEL] + names
        self.zip_list_combo["values"] = values
        if self.zip_list_var.get() not in values:
            self.zip_list_var.set(self.NO_ZIP_FILTER_LABEL)
        self._update_zip_preview()

        if self.zip_view_combo is not None:
            current = self.zip_view_var.get() if self.zip_view_var else self.ALL_ZIPS_LABEL
            view_list_name = self.list_var.get().strip() if self.list_var else ""
            list_name_filter = (
                None if view_list_name in ("", self.ALL_LISTS) else view_list_name
            )
            distinct_zips = self.store.get_distinct_zips(list_name=list_name_filter)
            options = [self.ALL_ZIPS_LABEL]
            if "" in distinct_zips:
                options.append(self.NO_ZIP_VIEW_LABEL)
            for zip_code in distinct_zips:
                if zip_code:
                    options.append(zip_code)
            self.zip_view_combo["values"] = options
            if current not in options:
                self.zip_view_var.set(self.ALL_ZIPS_LABEL)

    def _on_zip_list_selected(self):
        """Combobox handler — refresh the preview label only."""
        self._update_zip_preview()

    def _update_zip_preview(self):
        """Render a short preview of the currently chosen ZIP list."""
        if self.zip_preview_var is None:
            return
        zips = self._get_selected_zip_codes()
        if not zips:
            self.zip_preview_var.set(
                "No ZIP filter (single default-ZIP pass; zip_code stored as empty)."
            )
            return
        preview = ", ".join(zips[:6])
        if len(zips) > 6:
            preview += f" (+{len(zips) - 6} more)"
        self.zip_preview_var.set(f"{len(zips)} ZIP(s): {preview}")

    def _get_selected_zip_codes(self):
        """Resolve the ZIP picker selection to a list of 5-digit ZIPs (or [])."""
        if self.zip_list_var is None:
            return []
        name = self.zip_list_var.get().strip()
        if not name or name == self.NO_ZIP_FILTER_LABEL:
            return []
        zip_lists = load_all_zip_lists()
        return list(zip_lists.get(name, {}).get("zips", []))

    def _open_zip_list_manager(self):
        """Open a small editor for saved ZIP lists (mirrors delivery_speed_tracker)."""
        manager = tk.Toplevel(self.window)
        manager.title("Manage ZIP Lists")
        manager.transient(self.window)
        manager.grab_set()
        manager.resizable(True, True)
        size_and_center_on_parent(manager, self.window, 520, 480)
        clamp_minsize(manager, 460, 420)

        outer = ttk.Frame(manager, padding="10")
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="Saved ZIP list:").pack(anchor=tk.W)
        select_row = ttk.Frame(outer)
        select_row.pack(fill=tk.X, pady=(4, 8))

        current_name_var = tk.StringVar()
        zips_text = tk.Text(outer, height=14, wrap=tk.WORD)

        def load_list_into_text(name):
            data = load_all_zip_lists().get(name, {})
            zips = data.get("zips", [])
            zips_text.delete("1.0", tk.END)
            zips_text.insert("1.0", "\n".join(zips))

        list_names = sorted(load_all_zip_lists().keys())
        combo = ttk.Combobox(
            select_row, textvariable=current_name_var,
            values=list_names, state="readonly", width=30,
        )
        combo.pack(side=tk.LEFT)
        if list_names:
            combo.current(0)
            load_list_into_text(list_names[0])

        combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: load_list_into_text(current_name_var.get()),
        )

        ttk.Label(
            outer,
            text="ZIP codes (one per line, or comma / space separated):",
        ).pack(anchor=tk.W)
        zips_text.pack(fill=tk.BOTH, expand=True, pady=(4, 8))

        # Validate input and persist via zip_list_manager.save_zip_list.
        def do_save(as_new):
            raw = zips_text.get("1.0", tk.END)
            valid, invalid = parse_zip_list(raw)
            if invalid:
                preview = ", ".join(invalid[:6])
                if len(invalid) > 6:
                    preview += f" (+{len(invalid) - 6} more)"
                messagebox.showerror(
                    "Invalid ZIPs",
                    f"These tokens are not 5-digit ZIPs: {preview}",
                    parent=manager,
                )
                return
            if not valid:
                messagebox.showerror(
                    "Empty",
                    "Enter at least one valid 5-digit ZIP code.",
                    parent=manager,
                )
                return

            if as_new or not current_name_var.get().strip():
                target_name = simpledialog.askstring(
                    "Save ZIP List",
                    "Name for this ZIP list:",
                    initialvalue=current_name_var.get().strip(),
                    parent=manager,
                )
                if not target_name or not target_name.strip():
                    return
                target_name = target_name.strip()
                if target_name in load_all_zip_lists() and not messagebox.askyesno(
                    "Overwrite",
                    f"A list named '{target_name}' already exists. Overwrite?",
                    parent=manager,
                ):
                    return
            else:
                target_name = current_name_var.get().strip()

            saved, error = save_zip_list(target_name, valid)
            if not saved:
                messagebox.showerror(
                    "Save Failed", error or "Unknown error", parent=manager
                )
                return

            messagebox.showinfo(
                "Saved",
                f"Saved {len(valid)} ZIP(s) to '{target_name}'.",
                parent=manager,
            )
            new_names = sorted(load_all_zip_lists().keys())
            combo["values"] = new_names
            current_name_var.set(target_name)
            self._refresh_zip_choices()

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Save",
                   command=lambda: do_save(False)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text="Save As New...",
                   command=lambda: do_save(True)).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text="Close",
                   command=manager.destroy).pack(side=tk.RIGHT)

        manager.wait_window()

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
        self.selected_zip = ""

        if not selected_view:
            self.status_var.set("Select a list.")
            return

        # Determine the ZIP filter from the "View ZIPs" combobox.
        # - "All ZIPs"     -> show one row per (IP, ZIP-with-data), plus a
        #                     "Not tracked yet" row for IPs without any data.
        # - "(No ZIP)"     -> only legacy / zip-agnostic rows (zip_code='').
        # - "<5-digit ZIP>" -> only rows for that ZIP.
        view_zip_label = (
            self.zip_view_var.get().strip() if self.zip_view_var else self.ALL_ZIPS_LABEL
        )

        if selected_view == self.ALL_LISTS:
            total_rows = 0
            non_empty = 0
            for list_name in sorted(lists_data.keys()):
                ips = lists_data.get(list_name, {}).get("ips", [])
                if ips:
                    non_empty += 1
                inserted_for_list = self._insert_rows_for_list(
                    list_name, ips, view_zip_label
                )
                total_rows += inserted_for_list
            if total_rows == 0:
                self.status_var.set("All lists are empty (or no rows match the ZIP filter).")
                return
            self.status_var.set(
                f"Loaded {total_rows} row(s) across {non_empty} list(s) "
                f"(ZIP filter: {view_zip_label}). Select a row to view history."
            )
            return

        ips = lists_data.get(selected_view, {}).get("ips", [])
        if not ips:
            self.status_var.set(f"List '{selected_view}' has no IPs.")
            return

        inserted = self._insert_rows_for_list(selected_view, ips, view_zip_label)
        self.status_var.set(
            f"Loaded {inserted} row(s) from list '{selected_view}' "
            f"(ZIP filter: {view_zip_label}). Select a row to view history."
        )

    def _insert_rows_for_list(self, list_name, ips, view_zip_label):
        """
        Insert one Treeview row per (IP, ZIP) pair matching the ZIP filter.

        Returns the number of rows inserted (excluding pure placeholders).
        """
        # Build (ip, zip) work items based on the active ZIP filter.
        ip_set = set(ips)
        if view_zip_label == self.ALL_ZIPS_LABEL:
            # Every (ip, zip) with data, PLUS one placeholder for any IP with no data at all.
            pairs = [
                (ip, zip_code)
                for ip, zip_code in self.store.get_distinct_ip_zip_pairs(list_name)
                if ip in ip_set
            ]
            ips_with_data = {ip for ip, _ in pairs}
            for ip in sorted(ips):
                if ip not in ips_with_data:
                    pairs.append((ip, ""))
        elif view_zip_label == self.NO_ZIP_VIEW_LABEL:
            pairs = [(ip, "") for ip in sorted(ips)]
        else:
            # Specific 5-digit ZIP selected.
            pairs = [(ip, view_zip_label) for ip in sorted(ips)]

        # Sort for stable display: by IP, then ZIP (legacy '' first).
        pairs.sort(key=lambda p: (p[0], p[1]))

        inserted = 0
        for ip, zip_code in pairs:
            latest = self.store.get_latest_price_record(ip, list_name, zip_code)
            previous = self.store.get_previous_price_record(ip, list_name, zip_code)
            self._insert_result_row(list_name, ip, zip_code, latest, previous)
            inserted += 1
        return inserted

    def _insert_result_row(self, list_name, ip_number, zip_code, latest, previous):
        zip_display = zip_code if zip_code else "-"
        if not latest:
            self.results_tree.insert(
                "", tk.END,
                values=(
                    list_name, ip_number, zip_display,
                    "Not tracked yet", "-", "-", "-", "-", "-",
                ),
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
                zip_display,
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

        zip_codes = self._get_selected_zip_codes()
        zip_summary = (
            f" across {len(zip_codes)} ZIP(s)" if zip_codes else " (no ZIP filter)"
        )

        self._stop_flag[0] = False
        self._track_btn.configure(state="disabled")
        self.status_var.set(
            f"Starting tracking of {len(ip_entries)} IP(s){zip_summary}\u2026"
        )
        self.window.update_idletasks()

        def worker():
            def progress_cb(zip_idx, zip_total, ip_idx, ip_total,
                            current_zip, list_name, ip_number):
                self._queue.put({
                    "type": "progress",
                    "zip_idx": zip_idx, "zip_total": zip_total,
                    "ip_idx": ip_idx, "ip_total": ip_total,
                    "zip_code": current_zip,
                    "list_name": list_name, "ip": ip_number,
                })

            try:
                results = self.scraper.run_batch(
                    ip_entries, zip_codes, progress_cb, self._stop_flag,
                )
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
                    zip_total = msg.get("zip_total", 1)
                    zip_idx = msg.get("zip_idx", 1)
                    zip_label = msg.get("zip_code") or "no ZIP"
                    zip_part = (
                        f"ZIP {zip_idx}/{zip_total} ({zip_label}) | "
                        if zip_total > 1 or msg.get("zip_code")
                        else ""
                    )
                    self.status_var.set(
                        f"Tracking {zip_part}IP {msg['ip_idx']}/{msg['ip_total']} | "
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
        # zip_code -> {"ips": [...], "messages": {error_text -> count}}
        # We keep the actual error message strings so the dialog can surface
        # which step of the ZIP switch failed (pill click / sidebar / save / verify).
        zip_set_failures = {}

        for result in results:
            list_name = result.get("list_name", "")
            ip_number = result.get("ip_number", "")
            zip_code = result.get("zip_code", "") or ""
            error_code = result.get("error_code")
            err_message = result.get("error") or ""
            zip_label = f" @ZIP {zip_code}" if zip_code else ""

            if error_code == "BLOCKED":
                blocked = True
                errors.append(
                    f"[{list_name}] {ip_number}{zip_label}: "
                    "Bot detection triggered \u2014 batch aborted."
                )
                break
            elif error_code == "ZIP_SET_FAILED":
                # Group by ZIP so the dialog stays readable when many IPs failed
                # under the same ZIP. Also track distinct underlying error
                # messages so the user can see *why* the switch failed.
                bucket = zip_set_failures.setdefault(
                    zip_code or "(unknown)", {"ips": [], "messages": {}}
                )
                bucket["ips"].append(f"[{list_name}] {ip_number}")
                key = err_message or "Unknown ZIP switch error"
                bucket["messages"][key] = bucket["messages"].get(key, 0) + 1
            elif result.get("error"):
                errors.append(
                    f"[{list_name}] {ip_number}{zip_label}: {result['error']}"
                )
            else:
                self.store.log_price(
                    list_name, ip_number,
                    result["title"], result["seller"], result["price"],
                    zip_code=zip_code,
                )
                tracked_count += 1

        # Re-render results table + View ZIPs combobox (new ZIPs may have been added).
        self._refresh_zip_choices()
        self._refresh_latest_for_selected_list()

        summary_lines = [f"Tracked {tracked_count} record(s)."]

        if empty_lists:
            preview = ", ".join(empty_lists[:5])
            extra = f" (+{len(empty_lists) - 5} more)" if len(empty_lists) > 5 else ""
            summary_lines.append(f"Skipped empty list(s): {preview}{extra}")

        if zip_set_failures:
            failed_zip_total = sum(len(v["ips"]) for v in zip_set_failures.values())
            zip_preview = ", ".join(sorted(zip_set_failures.keys())[:5])
            summary_lines.append(
                f"ZIP switch failed for {failed_zip_total} IP-attempt(s) "
                f"across ZIPs: {zip_preview}. "
                "Those IPs were skipped under their failed ZIP."
            )

        if blocked:
            messagebox.showerror(
                "Bot Detection",
                "Walmart detected the scraper (CAPTCHA or 403).\n\n"
                "Wait a few minutes before trying again. "
                "Consider using a different network or reducing batch size.\n\n"
                + "\n".join(summary_lines),
                parent=self.window,
            )
        elif errors or zip_set_failures:
            details = []
            if zip_set_failures:
                details.append("ZIP_SET_FAILED:")
                for zip_code, bucket in sorted(zip_set_failures.items()):
                    ip_preview = ", ".join(bucket["ips"][:3])
                    extra = (
                        f" (+{len(bucket['ips']) - 3} more)"
                        if len(bucket["ips"]) > 3 else ""
                    )
                    details.append(f"  ZIP {zip_code}: {ip_preview}{extra}")
                    # Show distinct underlying error messages with their counts.
                    for msg, count in bucket["messages"].items():
                        details.append(f"    -> ({count}x) {msg}")
            if errors:
                details.append("Errors:")
                details.extend(f"  {e}" for e in errors[:5])
                if len(errors) > 5:
                    details.append(f"  \u2026and {len(errors) - 5} more.")
            messagebox.showwarning(
                "Tracking Completed with Warnings",
                "\n".join(summary_lines) + "\n\n" + "\n".join(details),
                parent=self.window,
            )
        else:
            messagebox.showinfo(
                "Tracking Complete",
                "\n".join(summary_lines),
                parent=self.window,
            )

        self.status_var.set(
            f"Tracking finished. {tracked_count} record(s) logged. "
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
        # Column 2 is the ZIP cell: '-' for the placeholder "no data" case.
        zip_display = row[2] if len(row) > 2 else "-"
        self.selected_zip = "" if zip_display in ("", "-") else zip_display
        # Title is now at index 3 (after list, ip, zip).
        self.selected_title = row[3] if len(row) > 3 else ""
        self._load_history_for_ip(
            self.selected_row_list, self.selected_ip, self.selected_zip
        )

    def _load_history_for_ip(self, list_name, ip_number, zip_code=""):
        history = self.store.get_price_history(ip_number, list_name, zip_code=zip_code)

        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        for record in history:
            zip_value = record.get("zip_code") or ""
            self.history_tree.insert(
                "", tk.END,
                values=(
                    record["tracked_at"],
                    zip_value or "-",
                    f"${float(record['price']):.2f}",
                    record.get("seller", ""),
                    record["title"],
                ),
            )

        self._draw_chart(history)

    def _redraw_chart_for_selection(self):
        if not self.selected_ip or not self.selected_row_list:
            return
        history = self.store.get_price_history(
            self.selected_ip, self.selected_row_list, zip_code=self.selected_zip
        )
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
        zip_label = self.selected_zip or "no ZIP"
        header = f"{ip_label} | ZIP {zip_label} | {title_text[:80]}"
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
        # Filter by the same ZIP the detail view is showing so the export
        # matches what the user is looking at on screen.
        rows = self.store.get_price_history_rows(
            list_name=self.selected_row_list,
            ip_number=self.selected_ip,
            zip_code=self.selected_zip,
        )
        zip_suffix = f"_{self.selected_zip}" if self.selected_zip else ""
        filename = (
            f"walmart_history_{self.selected_row_list}_{self.selected_ip}"
            f"{zip_suffix}.csv".replace(" ", "_")
        )
        self._export_history_rows(rows, filename)
