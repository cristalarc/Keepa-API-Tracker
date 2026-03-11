"""
Delivery speed memory store.
Persists timestamped ASIN + ZIP delivery checks and pass/fail reviews.
"""

import sqlite3
from datetime import datetime


class DeliverySpeedMemoryStore:
    """
    Handles persistence and summary queries for delivery speed checks.
    """

    def __init__(self, db_path="delivery_speed_history.db"):
        self.db_path = db_path
        self._initialize_database()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize_database(self):
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS delivery_speed_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    checked_at TEXT NOT NULL,
                    asin TEXT NOT NULL,
                    zip_code TEXT NOT NULL,
                    estimated_days INTEGER,
                    status TEXT NOT NULL,
                    threshold_days INTEGER NOT NULL,
                    is_pass INTEGER NOT NULL,
                    review_reason TEXT NOT NULL,
                    delivery_text TEXT,
                    zip_verified INTEGER NOT NULL,
                    displayed_zip TEXT,
                    error TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_delivery_checks_asin_zip
                ON delivery_speed_checks (asin, zip_code)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_delivery_checks_checked_at
                ON delivery_speed_checks (checked_at)
                """
            )
            conn.commit()

    @staticmethod
    def evaluate_review(result_row, threshold_days):
        """
        Evaluate pass/fail against configured delivery-day threshold.
        """
        status = (result_row.get("status") or "").strip().lower()
        estimated_days = result_row.get("estimated_days")

        if status != "ok":
            return False, f"FAIL: status={status or 'unknown'}"
        if estimated_days is None:
            return False, "FAIL: missing estimated delivery days"
        if not isinstance(estimated_days, int):
            return False, "FAIL: estimated days not numeric"
        if estimated_days <= threshold_days:
            return True, f"PASS: {estimated_days} <= threshold {threshold_days}"
        return False, f"FAIL: {estimated_days} > threshold {threshold_days}"

    def log_check(self, result_row, threshold_days, checked_at=None):
        """
        Persist one check and return review metadata.
        """
        timestamp = checked_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_pass, review_reason = self.evaluate_review(result_row, threshold_days)

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO delivery_speed_checks (
                    checked_at,
                    asin,
                    zip_code,
                    estimated_days,
                    status,
                    threshold_days,
                    is_pass,
                    review_reason,
                    delivery_text,
                    zip_verified,
                    displayed_zip,
                    error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    result_row.get("asin", ""),
                    result_row.get("zip_code", ""),
                    result_row.get("estimated_days"),
                    result_row.get("status", "error"),
                    int(threshold_days),
                    1 if is_pass else 0,
                    review_reason,
                    result_row.get("delivery_text"),
                    1 if result_row.get("zip_verified") else 0,
                    result_row.get("displayed_zip"),
                    result_row.get("error"),
                ),
            )
            conn.commit()

        return {
            "checked_at": timestamp,
            "is_pass": is_pass,
            "review": "PASS" if is_pass else "FAIL",
            "review_reason": review_reason,
        }

    def get_pair_summary(self, asin, zip_code):
        """
        Return pass/fail counts for one ASIN + ZIP pair.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_checks,
                    COALESCE(SUM(is_pass), 0) AS pass_checks,
                    MAX(checked_at) AS last_checked_at
                FROM delivery_speed_checks
                WHERE asin = ? AND zip_code = ?
                """,
                (asin, zip_code),
            )
            row = cursor.fetchone()

        total_checks = int(row[0] or 0)
        pass_checks = int(row[1] or 0)
        fail_checks = total_checks - pass_checks
        return {
            "total_checks": total_checks,
            "pass_checks": pass_checks,
            "fail_checks": fail_checks,
            "last_checked_at": row[2],
        }

    def get_overall_summary(self):
        """
        Return overall pass/fail counts across all stored checks.
        """
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_checks,
                    COALESCE(SUM(is_pass), 0) AS pass_checks,
                    MAX(checked_at) AS last_checked_at
                FROM delivery_speed_checks
                """
            )
            row = cursor.fetchone()

        total_checks = int(row[0] or 0)
        pass_checks = int(row[1] or 0)
        fail_checks = total_checks - pass_checks
        pass_rate = (pass_checks / total_checks) * 100 if total_checks > 0 else 0.0
        return {
            "total_checks": total_checks,
            "pass_checks": pass_checks,
            "fail_checks": fail_checks,
            "pass_rate_percent": pass_rate,
            "last_checked_at": row[2],
        }

