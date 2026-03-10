"""
Competitor Price Tracker Module
Tracks current prices for ASIN lists, stores snapshots in SQLite, and visualizes price history.
"""

import sqlite3
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import requests

from asin_manager import load_all_asin_lists


class PriceHistoryStore:
    """
    Handles persistent storage for tracked ASIN prices using SQLite.
    """

    def __init__(self, db_path="price_tracking.db"):
        self.db_path = db_path
        self._initialize_database()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize_database(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS price_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_name TEXT NOT NULL,
                    asin TEXT NOT NULL,
                    title TEXT NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    tracked_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_logs_asin_list ON price_logs(asin, list_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_price_logs_tracked_at ON price_logs(tracked_at)"
            )
            conn.commit()

    def log_price(self, list_name, asin, title, price, currency="USD", tracked_at=None):
        tracked_at = tracked_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO price_logs (list_name, asin, title, price, currency, tracked_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (list_name, asin, title, price, currency, tracked_at),
            )
            conn.commit()

    def get_latest_price_record(self, asin, list_name):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT asin, title, price, currency, tracked_at
                FROM price_logs
                WHERE asin = ? AND list_name = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (asin, list_name),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "asin": row[0],
                "title": row[1],
                "price": row[2],
                "currency": row[3],
                "tracked_at": row[4],
            }

    def get_previous_price_record(self, asin, list_name):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT asin, title, price, currency, tracked_at
                FROM price_logs
                WHERE asin = ? AND list_name = ?
                ORDER BY id DESC
                LIMIT 1 OFFSET 1
                """,
                (asin, list_name),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "asin": row[0],
                "title": row[1],
                "price": row[2],
                "currency": row[3],
                "tracked_at": row[4],
            }

    def get_price_history(self, asin, list_name, limit=300):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT tracked_at, price, title, currency
                FROM price_logs
                WHERE asin = ? AND list_name = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (asin, list_name, limit),
            )
            rows = cursor.fetchall()

        rows.reverse()
        return [
            {
                "tracked_at": row[0],
                "price": row[1],
                "title": row[2],
                "currency": row[3],
            }
            for row in rows
        ]


class KeepaPriceClient:
    """
    Fetches current product title and price from Keepa API.
    """

    def __init__(self, api_key):
        self.api_key = api_key
        self.endpoint = "https://api.keepa.com/product"

    def fetch_current_price(self, asin):
        params = {
            "key": self.api_key,
            "domain": 1,
            "asin": asin,
            "stats": 1,
            "buybox": 1,
            "history": 0,
        }
        try:
            response = requests.get(self.endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as exc:
            return None, None, f"API request failed: {exc}"

        products = data.get("products") or []
        if not products:
            return None, None, "No product data returned by Keepa."

        product = products[0]
        title = (product.get("title") or f"ASIN {asin}").strip()
        price_cents = self._extract_price_cents(product)
        if price_cents is None:
            return None, title, "No current price available from Keepa for this ASIN."

        return round(price_cents / 100.0, 2), title, None

    def _extract_price_cents(self, product):
        candidates = []

        direct_buybox = product.get("buyBoxPrice")
        if isinstance(direct_buybox, (int, float)):
            candidates.append(direct_buybox)

        stats = product.get("stats", {})
        current = stats.get("current") if isinstance(stats, dict) else None
        if isinstance(current, list):
            for idx in (18, 1, 0):
                if len(current) > idx and isinstance(current[idx], (int, float)):
                    candidates.append(current[idx])

        csv_data = product.get("csv")
        if isinstance(csv_data, list):
            for idx in (18, 1, 0):
                if len(csv_data) > idx and isinstance(csv_data[idx], list) and csv_data[idx]:
                    latest_value = csv_data[idx][-1]
                    if isinstance(latest_value, (int, float)):
                        candidates.append(latest_value)

        for value in candidates:
            if value is not None and value > 0:
                return int(value)
        return None


class CompetitorPriceTracker:
    """
    Tkinter UI for tracking and visualizing competitor ASIN prices.
    """

    def __init__(self, api_key):
        self.store = PriceHistoryStore()
        self.keepa_client = KeepaPriceClient(api_key)

        self.window = None
        self.list_var = None
        self.status_var = None
        self.results_tree = None
        self.history_tree = None
        self.chart_canvas = None
        self.selected_asin = None
        self.selected_title = None

    def open_tracker_window(self, parent_window=None):
        self.window = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        self.window.title("Competitor ASIN Price Tracker")
        self.window.resizable(True, True)
        self.window.minsize(1200, 820)

        self.window.update_idletasks()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        width = min(int(screen_width * 0.95), 1500)
        height = min(int(screen_height * 0.92), 980)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")

        self.window.lift()
        self.window.attributes("-topmost", True)
        self.window.after_idle(lambda: self.window.attributes("-topmost", False))

        self._build_ui()
        self._refresh_list_choices()
        self._refresh_latest_for_selected_list()

        if parent_window:
            self.window.wait_window()
        else:
            self.window.mainloop()

    def _build_ui(self):
        container = ttk.Frame(self.window, padding="16")
        container.pack(fill=tk.BOTH, expand=True)

        header_label = ttk.Label(
            container,
            text="Competitor ASIN Price Tracker",
            font=("Arial", 18, "bold"),
        )
        header_label.pack(anchor=tk.W, pady=(0, 10))

        controls = ttk.Frame(container)
        controls.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(controls, text="ASIN List:").pack(side=tk.LEFT)
        self.list_var = tk.StringVar()
        self.list_combo = ttk.Combobox(
            controls,
            textvariable=self.list_var,
            state="readonly",
            width=35,
        )
        self.list_combo.pack(side=tk.LEFT, padx=(8, 8))
        self.list_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_latest_for_selected_list())

        ttk.Button(
            controls,
            text="Refresh Lists",
            command=self._refresh_list_choices,
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            controls,
            text="Track Prices Now",
            command=self._track_prices_for_selected_list,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)

        self.status_var = tk.StringVar(value="Select an ASIN list, then click 'Track Prices Now'.")
        ttk.Label(container, textvariable=self.status_var, foreground="gray").pack(anchor=tk.W, pady=(0, 10))

        results_frame = ttk.LabelFrame(
            container,
            text="Latest Tracked Prices (drops are highlighted)",
            padding="8",
        )
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("asin", "title", "current_price", "previous_price", "change", "tracked_at")
        self.results_tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=12)
        self.results_tree.heading("asin", text="ASIN")
        self.results_tree.heading("title", text="Product Title")
        self.results_tree.heading("current_price", text="Current Price")
        self.results_tree.heading("previous_price", text="Previous Price")
        self.results_tree.heading("change", text="Change")
        self.results_tree.heading("tracked_at", text="Last Tracked")

        self.results_tree.column("asin", width=120, anchor=tk.W)
        self.results_tree.column("title", width=420, anchor=tk.W)
        self.results_tree.column("current_price", width=110, anchor=tk.E)
        self.results_tree.column("previous_price", width=110, anchor=tk.E)
        self.results_tree.column("change", width=100, anchor=tk.E)
        self.results_tree.column("tracked_at", width=160, anchor=tk.W)

        results_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=results_scrollbar.set)
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.results_tree.tag_configure("drop", background="#E5F7E6")
        self.results_tree.tag_configure("increase", background="#FFF2E5")
        self.results_tree.tag_configure("no_data", background="#F5F5F5")
        self.results_tree.bind("<<TreeviewSelect>>", self._on_asin_selected)

        details_frame = ttk.LabelFrame(
            container,
            text="Selected ASIN Price History",
            padding="8",
        )
        details_frame.pack(fill=tk.BOTH, expand=True)

        self.chart_canvas = tk.Canvas(details_frame, bg="white", height=260, highlightthickness=1, highlightbackground="#D9D9D9")
        self.chart_canvas.pack(fill=tk.X, expand=False, pady=(0, 8))
        self.chart_canvas.bind("<Configure>", lambda _event: self._redraw_chart_for_selection())

        history_columns = ("tracked_at", "price", "title")
        self.history_tree = ttk.Treeview(details_frame, columns=history_columns, show="headings", height=8)
        self.history_tree.heading("tracked_at", text="Tracked At")
        self.history_tree.heading("price", text="Price")
        self.history_tree.heading("title", text="Product Title")
        self.history_tree.column("tracked_at", width=180, anchor=tk.W)
        self.history_tree.column("price", width=120, anchor=tk.E)
        self.history_tree.column("title", width=760, anchor=tk.W)

        history_scrollbar = ttk.Scrollbar(details_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_scrollbar.set)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _refresh_list_choices(self):
        lists_data = load_all_asin_lists()
        list_names = sorted(lists_data.keys())
        self.list_combo["values"] = list_names

        if not list_names:
            self.list_var.set("")
            self.status_var.set("No ASIN lists found. Use ASIN Manager to create or populate a list.")
            self._clear_results_table()
            self._clear_history_details()
            return

        if self.list_var.get() not in list_names:
            self.list_var.set(list_names[0])
        self._refresh_latest_for_selected_list()

    def _clear_results_table(self):
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

    def _clear_history_details(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        self.chart_canvas.delete("all")
        self.chart_canvas.create_text(20, 20, text="Select an ASIN to view chart and dated history.", anchor=tk.NW, fill="#555555")

    def _refresh_latest_for_selected_list(self):
        selected_list = self.list_var.get().strip()
        lists_data = load_all_asin_lists()
        asins = lists_data.get(selected_list, {}).get("asins", []) if selected_list else []

        self._clear_results_table()
        self._clear_history_details()
        self.selected_asin = None
        self.selected_title = None

        if not selected_list:
            self.status_var.set("Select an ASIN list.")
            return

        if not asins:
            self.status_var.set(f"List '{selected_list}' has no ASINs.")
            return

        for asin in sorted(asins):
            latest = self.store.get_latest_price_record(asin, selected_list)
            previous = self.store.get_previous_price_record(asin, selected_list)

            if not latest:
                self.results_tree.insert(
                    "",
                    tk.END,
                    values=(asin, "Not tracked yet", "-", "-", "-", "-"),
                    tags=("no_data",),
                )
                continue

            current_price = float(latest["price"])
            previous_price = float(previous["price"]) if previous and previous["price"] is not None else None
            change = (current_price - previous_price) if previous_price is not None else None
            change_text = f"{change:+.2f}" if change is not None else "-"
            change_tag = "drop" if change is not None and change < 0 else "increase" if change is not None and change > 0 else ""

            self.results_tree.insert(
                "",
                tk.END,
                values=(
                    asin,
                    latest["title"],
                    f"${current_price:.2f}",
                    f"${previous_price:.2f}" if previous_price is not None else "-",
                    f"${change_text}" if change is not None else "-",
                    latest["tracked_at"],
                ),
                tags=(change_tag,) if change_tag else (),
            )

        self.status_var.set(
            f"Loaded {len(asins)} ASINs from list '{selected_list}'. Select a row to view history chart."
        )

    def _track_prices_for_selected_list(self):
        selected_list = self.list_var.get().strip()
        if not selected_list:
            messagebox.showwarning("No List Selected", "Please select an ASIN list first.", parent=self.window)
            return

        lists_data = load_all_asin_lists()
        asins = lists_data.get(selected_list, {}).get("asins", [])
        if not asins:
            messagebox.showwarning(
                "Empty List",
                f"List '{selected_list}' has no ASINs. Add ASINs in ASIN Manager first.",
                parent=self.window,
            )
            return

        tracked_count = 0
        errors = []
        total = len(asins)

        for index, asin in enumerate(asins, start=1):
            self.status_var.set(f"Tracking {index}/{total}: {asin}")
            self.window.update_idletasks()

            price, title, error = self.keepa_client.fetch_current_price(asin)
            if error:
                errors.append(f"{asin}: {error}")
                continue

            self.store.log_price(selected_list, asin, title, price)
            tracked_count += 1

        self._refresh_latest_for_selected_list()

        if errors:
            preview = "\n".join(errors[:5])
            extra = f"\n...and {len(errors) - 5} more." if len(errors) > 5 else ""
            messagebox.showwarning(
                "Tracking Completed with Warnings",
                f"Tracked {tracked_count} ASIN(s) successfully.\n\nErrors:\n{preview}{extra}",
                parent=self.window,
            )
        else:
            messagebox.showinfo(
                "Tracking Complete",
                f"Tracked {tracked_count} ASIN(s) successfully.",
                parent=self.window,
            )

        self.status_var.set(
            f"Tracking finished for list '{selected_list}'. Rows with price drops are highlighted in green."
        )

    def _on_asin_selected(self, _event):
        selection = self.results_tree.selection()
        if not selection:
            return

        row_values = self.results_tree.item(selection[0], "values")
        asin = row_values[0]
        title = row_values[1]
        self.selected_asin = asin
        self.selected_title = title
        self._load_history_for_asin(asin)

    def _load_history_for_asin(self, asin):
        selected_list = self.list_var.get().strip()
        history = self.store.get_price_history(asin, selected_list)

        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        for record in history:
            self.history_tree.insert(
                "",
                tk.END,
                values=(
                    record["tracked_at"],
                    f"${float(record['price']):.2f}",
                    record["title"],
                ),
            )

        self._draw_chart(history)

    def _redraw_chart_for_selection(self):
        if not self.selected_asin:
            return
        selected_list = self.list_var.get().strip()
        history = self.store.get_price_history(self.selected_asin, selected_list)
        self._draw_chart(history)

    def _draw_chart(self, history):
        self.chart_canvas.delete("all")
        width = max(self.chart_canvas.winfo_width(), 700)
        height = max(self.chart_canvas.winfo_height(), 260)

        if not history:
            self.chart_canvas.create_text(
                20,
                20,
                text="No tracked history yet for this ASIN.",
                anchor=tk.NW,
                fill="#555555",
            )
            return

        title_text = self.selected_title or history[-1]["title"]
        header = f"{self.selected_asin} | {title_text[:90]}"
        self.chart_canvas.create_text(14, 10, text=header, anchor=tk.NW, fill="#222222", font=("Arial", 10, "bold"))

        left_margin = 70
        right_margin = 20
        top_margin = 35
        bottom_margin = 65
        plot_width = width - left_margin - right_margin
        plot_height = height - top_margin - bottom_margin

        prices = [float(row["price"]) for row in history]
        time_points = [
            datetime.strptime(row["tracked_at"], "%Y-%m-%d %H:%M:%S").timestamp()
            for row in history
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

        def map_x(timestamp_value):
            ratio = (timestamp_value - min_time) / (max_time - min_time)
            return left_margin + (ratio * plot_width)

        def map_y(price_value):
            ratio = (price_value - min_price) / (max_price - min_price)
            return top_margin + ((1 - ratio) * plot_height)

        self.chart_canvas.create_line(left_margin, top_margin, left_margin, top_margin + plot_height, fill="#666666")
        self.chart_canvas.create_line(
            left_margin,
            top_margin + plot_height,
            left_margin + plot_width,
            top_margin + plot_height,
            fill="#666666",
        )

        y_tick_count = 4
        for i in range(y_tick_count + 1):
            ratio = i / y_tick_count
            price_tick = max_price - (ratio * (max_price - min_price))
            y = top_margin + (ratio * plot_height)
            self.chart_canvas.create_line(left_margin - 5, y, left_margin, y, fill="#666666")
            self.chart_canvas.create_text(
                left_margin - 8,
                y,
                text=f"${price_tick:.2f}",
                anchor=tk.E,
                fill="#444444",
                font=("Arial", 8),
            )

        x_tick_indices = sorted(set([0, len(history) // 2, len(history) - 1]))
        for idx in x_tick_indices:
            timestamp_value = time_points[idx]
            x = map_x(timestamp_value)
            label = datetime.strptime(history[idx]["tracked_at"], "%Y-%m-%d %H:%M:%S").strftime("%m-%d %H:%M")
            self.chart_canvas.create_line(x, top_margin + plot_height, x, top_margin + plot_height + 5, fill="#666666")
            self.chart_canvas.create_text(
                x,
                top_margin + plot_height + 18,
                text=label,
                anchor=tk.N,
                fill="#444444",
                font=("Arial", 8),
            )

        points = []
        for timestamp_value, price_value in zip(time_points, prices):
            x = map_x(timestamp_value)
            y = map_y(price_value)
            points.extend([x, y])

        if len(points) >= 4:
            self.chart_canvas.create_line(*points, fill="#1F77B4", width=2, smooth=True)
        for i in range(0, len(points), 2):
            x_coord = points[i]
            y_coord = points[i + 1]
            self.chart_canvas.create_oval(
                x_coord - 2.5,
                y_coord - 2.5,
                x_coord + 2.5,
                y_coord + 2.5,
                fill="#1F77B4",
                outline="#1F77B4",
            )
