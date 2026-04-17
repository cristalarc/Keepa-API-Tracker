"""
Delivery Speed Tracker Module
Fetches Amazon buybox delivery messaging for ASIN + ZIP combinations.
"""

import random
import re
import time
from datetime import datetime, timedelta
from html import unescape
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

import pandas as pd
import requests

from asin_manager import load_all_asin_lists, load_saved_asins, validate_asin_list
from window_utils import center_window_on_parent, scaled_font, scaled
from delivery_speed_memory import DeliverySpeedMemoryStore
from zip_list_manager import load_all_zip_lists, parse_zip_list, save_zip_list


class AmazonDeliveryClient:
    """
    Handles HTTP calls to Amazon with conservative request pacing.
    """

    PRODUCT_URL_TEMPLATE = "https://www.amazon.com/dp/{asin}"
    ADDRESS_CHANGE_URL = "https://www.amazon.com/gp/delivery/ajax/address-change.html"

    def __init__(
        self,
        min_delay_sec=2.0,
        max_delay_sec=5.0,
        max_retries=3,
        timeout_sec=30,
        proxy_url=None,
    ):
        self.min_delay_sec = min_delay_sec
        self.max_delay_sec = max_delay_sec
        self.max_retries = max_retries
        self.timeout_sec = timeout_sec
        self.proxy_url = proxy_url.strip() if isinstance(proxy_url, str) else ""

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Upgrade-Insecure-Requests": "1",
                "DNT": "1",
            }
        )

        if self.proxy_url:
            self.session.proxies = {"http": self.proxy_url, "https": self.proxy_url}

    def _throttle(self):
        """Sleep with jitter between requests to reduce bursty traffic."""
        sleep_seconds = random.uniform(self.min_delay_sec, self.max_delay_sec)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    def _request_get(self, url, params=None):
        """
        GET wrapper with retries + exponential backoff.
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                self._throttle()
                response = self.session.get(url, params=params, timeout=self.timeout_sec)

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = (
                        f"Amazon returned HTTP {response.status_code} "
                        f"(attempt {attempt + 1}/{self.max_retries + 1})."
                    )
                else:
                    return response, None
            except requests.exceptions.RequestException as exc:
                last_error = f"Request error: {exc}"

            if attempt < self.max_retries:
                backoff = min(2 ** attempt, 20) + random.uniform(0.2, 1.5)
                time.sleep(backoff)

        return None, last_error

    def _request_post(self, url, data, headers=None):
        """
        POST wrapper with retries + exponential backoff.
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                self._throttle()
                response = self.session.post(
                    url,
                    data=data,
                    headers=headers,
                    timeout=self.timeout_sec,
                )

                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = (
                        f"Amazon returned HTTP {response.status_code} "
                        f"(attempt {attempt + 1}/{self.max_retries + 1})."
                    )
                else:
                    return response, None
            except requests.exceptions.RequestException as exc:
                last_error = f"Request error: {exc}"

            if attempt < self.max_retries:
                backoff = min(2 ** attempt, 20) + random.uniform(0.2, 1.5)
                time.sleep(backoff)

        return None, last_error

    @staticmethod
    def _is_captcha_page(html_text):
        if not html_text:
            return False
        lowered = html_text.lower()
        return (
            "sorry, we just need to make sure you're not a robot" in lowered
            or "/errors/validatecaptcha" in lowered
            or "enter the characters you see below" in lowered
        )

    @staticmethod
    def _extract_anti_csrf_token(html_text):
        """
        Extract anti-csrftoken-a2z token when available.
        """
        token_patterns = [
            r'"anti-csrftoken-a2z"\s*:\s*"([^"]+)"',
            r'name="anti-csrftoken-a2z"\s+value="([^"]+)"',
            r'anti-csrftoken-a2z=([A-Za-z0-9%._\-]+)',
        ]
        for pattern in token_patterns:
            match = re.search(pattern, html_text, flags=re.IGNORECASE)
            if match:
                return unescape(match.group(1))
        return None

    def _set_zip_code(self, asin, zip_code):
        """
        Best-effort ZIP switch via Amazon's address-change endpoint.
        """
        product_url = self.PRODUCT_URL_TEMPLATE.format(asin=asin)
        first_page, first_error = self._request_get(product_url)
        if first_error:
            return False, first_error

        first_html = first_page.text if first_page is not None else ""
        if self._is_captcha_page(first_html):
            return False, "Captcha encountered before ZIP update."

        csrf_token = self._extract_anti_csrf_token(first_html)
        form_data = {
            "locationType": "LOCATION_INPUT",
            "zipCode": zip_code[:5],
            "storeContext": "generic",
            "deviceType": "web",
            "pageType": "Detail",
            "actionSource": "glow",
        }
        if csrf_token:
            form_data["anti-csrftoken-a2z"] = csrf_token

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.amazon.com",
            "Referer": product_url,
        }
        _, post_error = self._request_post(self.ADDRESS_CHANGE_URL, form_data, headers=headers)

        if post_error:
            # Keep running even if ZIP switch fails; the next request may still return data.
            return False, post_error

        return True, None

    @staticmethod
    def _strip_html(html_text):
        """
        Remove scripts/styles/tags and normalize spaces.
        """
        if not html_text:
            return ""
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @classmethod
    def extract_delivery_message(cls, html_text):
        """
        Attempt to extract delivery copy from product page content.
        """
        if not html_text:
            return None
        if cls._is_captcha_page(html_text):
            return None

        # First choice: use structured delivery spans in buybox delivery block.
        best_structured = cls._extract_best_structured_delivery_candidate(html_text)
        structured_candidates = [best_structured] if best_structured else []

        direct_patterns = [
            r'id="mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_LARGE"[^>]*>(.*?)</div>',
            r'id="mir-layout-DELIVERY_BLOCK-slot-PRIMARY_DELIVERY_MESSAGE_SMALL"[^>]*>(.*?)</div>',
            r'id="mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_LARGE"[^>]*>(.*?)</div>',
            r'id="mir-layout-DELIVERY_BLOCK-slot-SECONDARY_DELIVERY_MESSAGE_SMALL"[^>]*>(.*?)</div>',
            r'id="deliveryBlockMessage"[^>]*>(.*?)</div>',
            r'id="ddmDeliveryMessage"[^>]*>(.*?)</div>',
            r'id="delivery-message"[^>]*>(.*?)</div>',
        ]
        direct_candidates = []
        for pattern in direct_patterns:
            match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
            if not match:
                continue
            candidate = cls._strip_html(match.group(1))
            if cls._is_valid_delivery_candidate(candidate):
                direct_candidates.append(candidate)

        # Limit fallback phrase scan to buybox delivery-related sections first.
        buybox_region = cls._extract_buybox_delivery_region(html_text)
        flat_text = cls._strip_html(buybox_region) if buybox_region else cls._strip_html(html_text)
        phrase_patterns = [
            r"\b(?:or\s+)?fastest\s+delivery[^.!\n]{0,200}",
            r"\b(?:prime\s+members\s+get\s+)?(?:free\s+)?delivery[^.!\n]{0,200}",
            r"get it[^.!\n]{0,160}",
            r"arrives[^.!\n]{0,160}",
            r"usually ships[^.!\n]{0,160}",
            r"ships in[^.!\n]{0,160}",
        ]
        fallback_candidates = []
        seen_candidates = set()
        for pattern in phrase_patterns:
            for match in re.finditer(pattern, flat_text, flags=re.IGNORECASE):
                candidate = re.sub(r"\s+", " ", match.group(0)).strip(" -:|")
                if not cls._is_valid_delivery_candidate(candidate):
                    continue
                candidate_key = candidate.lower()
                if candidate_key in seen_candidates:
                    continue
                seen_candidates.add(candidate_key)
                fallback_candidates.append(candidate)

        all_candidates = []
        seen_candidates = set()
        for candidate_group in (structured_candidates, direct_candidates, fallback_candidates):
            for candidate in candidate_group:
                normalized_key = re.sub(r"\s+", " ", (candidate or "").strip()).lower()
                if not normalized_key or normalized_key in seen_candidates:
                    continue
                seen_candidates.add(normalized_key)
                all_candidates.append(candidate)

        if all_candidates:
            return cls._select_best_delivery_candidate(all_candidates)

        return None

    @classmethod
    def _extract_best_structured_delivery_candidate(cls, html_text):
        """
        Parse delivery message spans with explicit delivery-time metadata.
        """
        buybox_region = cls._extract_buybox_delivery_region(html_text)
        source_html = buybox_region if buybox_region else html_text

        span_pattern = re.compile(
            r"<span[^>]*data-csa-c-delivery-time=\"([^\"]+)\"[^>]*>(.*?)</span>",
            flags=re.IGNORECASE | re.DOTALL,
        )
        candidates = []
        for match in span_pattern.finditer(source_html):
            delivery_time = cls._strip_html(match.group(1))
            raw_text = cls._strip_html(match.group(2))
            if not delivery_time:
                continue

            if raw_text:
                candidate = raw_text
            else:
                # Fallback when span text is empty but delivery time is present.
                candidate = f"FREE delivery {delivery_time}"

            if not cls._is_valid_delivery_candidate(candidate):
                continue

            candidates.append(candidate)

        if not candidates:
            return None
        return cls._select_best_delivery_candidate(candidates)

    @staticmethod
    def _extract_buybox_delivery_region(html_text):
        """
        Narrow fallback search to delivery block areas to avoid Join Prime content.
        """
        if not html_text:
            return None

        lower_html = html_text.lower()
        start_markers = ['id="deliveryblockmessage"', 'id="mir-layout-delivery_block"']
        for marker in start_markers:
            start_index = lower_html.find(marker)
            if start_index == -1:
                continue

            # Use a bounded window instead of regex tag balancing.
            # This reliably includes primary + secondary delivery lines.
            end_index = min(len(html_text), start_index + 30000)
            return html_text[start_index:end_index]
        return None

    @staticmethod
    def _extract_buybox_seller_region(html_text):
        """
        Narrow seller extraction to right-rail buybox content when possible.
        """
        if not html_text:
            return None

        lower_html = html_text.lower()
        start_markers = [
            'id="desktop_buybox"',
            "id='desktop_buybox'",
            'id="buybox"',
            "id='buybox'",
        ]
        for marker in start_markers:
            start_index = lower_html.find(marker)
            if start_index == -1:
                continue

            # Keep a broad bounded window that includes active offer rows
            # plus nearby shipper/seller blocks.
            end_index = min(len(html_text), start_index + 220000)
            return html_text[start_index:end_index]
        return None

    @classmethod
    def _select_best_delivery_candidate(cls, candidates):
        """
        Select best candidate prioritizing earliest delivery (especially Prime).
        """
        scored = []
        for candidate in candidates:
            normalized_candidate = cls._normalize_delivery_candidate_text(candidate)
            if not cls._is_valid_delivery_candidate(normalized_candidate):
                continue
            days = cls.estimate_delivery_days(normalized_candidate)
            lower = normalized_candidate.lower()
            # If Amazon explicitly labels a line as "fastest delivery",
            # that should be preferred over standard delivery lines.
            fastest_rank = 0 if "fastest delivery" in lower else 1
            prime_rank = 0 if "prime" in lower else 1

            # Unknown days are worst; otherwise pick smallest day value.
            effective_days = days if isinstance(days, int) else 9999
            scored.append((fastest_rank, effective_days, prime_rank, len(normalized_candidate), normalized_candidate))

        if not scored:
            return None

        scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
        return scored[0][4]

    @staticmethod
    def _normalize_delivery_candidate_text(candidate):
        """
        Keep the most relevant delivery clause (especially fastest-delivery segment).
        """
        text = re.sub(r"\s+", " ", (candidate or "").strip())
        lower = text.lower()
        delivery_start_match = re.search(
            r"\b("
            r"fastest delivery|"
            r"prime members get free delivery|"
            r"free delivery|"
            r"delivery|"
            r"get it|arrives|usually ships|ships in"
            r")\b",
            lower,
        )
        if delivery_start_match and delivery_start_match.start() > 0:
            text = text[delivery_start_match.start():].strip(" .")
            lower = text.lower()

        if re.search(r"\s+\bor\b\s+", lower):
            parts = [part.strip(" .") for part in re.split(r"\s+\bor\b\s+", text, flags=re.IGNORECASE)]
            delivery_parts = [part for part in parts if AmazonDeliveryClient._looks_like_delivery_text(part)]
            if delivery_parts:
                text = min(
                    delivery_parts,
                    key=lambda part: (
                        AmazonDeliveryClient.estimate_delivery_days(part)
                        if isinstance(AmazonDeliveryClient.estimate_delivery_days(part), int)
                        else 9999,
                        len(part),
                    ),
                )
                lower = text.lower()

        fastest_index = lower.find("fastest delivery")
        if fastest_index > 0:
            # Include leading "Or " when present for readability.
            start_index = lower.rfind("or ", 0, fastest_index + 1)
            if start_index == -1 or (fastest_index - start_index) > 6:
                start_index = fastest_index
            text = text[start_index:].strip(" .")
        return text

    @classmethod
    def _is_valid_delivery_candidate(cls, text):
        """
        Filter delivery candidates and reject Join Prime marketing copy.
        """
        if not cls._looks_like_delivery_text(text):
            return False
        lowered = text.lower()
        blocked_phrases = [
            "exclusive deals",
            "award-winning movies",
            "tv shows",
            "join prime",
        ]
        return not any(phrase in lowered for phrase in blocked_phrases)

    @staticmethod
    def _looks_like_delivery_text(text):
        if not text:
            return False
        lowered = text.lower()
        keywords = ["delivery", "arrives", "ships", "tomorrow", "today", "overnight"]
        return any(keyword in lowered for keyword in keywords)

    @staticmethod
    def estimate_delivery_days(delivery_text, now=None):
        """
        Convert delivery copy into a numeric day estimate when possible.
        """
        if not delivery_text:
            return None

        now = now or datetime.now()
        text = delivery_text.strip()
        lowered = text.lower()

        # If a combined sentence contains both regular and fastest delivery text,
        # parse the fastest segment to avoid using slower date mentions.
        fastest_index = lowered.find("fastest delivery")
        if fastest_index > 0:
            text = text[fastest_index:]
            lowered = text.lower()

        if "today" in lowered:
            return 0
        if "overnight" in lowered or "tomorrow" in lowered:
            return 1

        range_match = re.search(
            r"(\d+)\s*(?:-|to)\s*(\d+)\s*(?:business\s*)?days?",
            lowered,
            flags=re.IGNORECASE,
        )
        if range_match:
            return int(range_match.group(2))

        single_match = re.search(
            r"(?:within|in)\s+(\d+)\s*(?:business\s*)?days?",
            lowered,
            flags=re.IGNORECASE,
        )
        if single_match:
            return int(single_match.group(1))

        # Parse month/day style strings: "March 18" or "Mar 18".
        month_day_pattern = re.compile(
            r"\b("
            r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
            r"nov(?:ember)?|dec(?:ember)?"
            r")\.?,?\s+(\d{1,2})\b",
            flags=re.IGNORECASE,
        )
        parsed_month_day_deltas = []
        for month_day_match in month_day_pattern.finditer(lowered):
            month_text = month_day_match.group(1).replace(".", "").title()
            day_number = int(month_day_match.group(2))
            parsed_date = None
            for fmt in ("%b %d", "%B %d"):
                try:
                    candidate = datetime.strptime(f"{month_text} {day_number}", fmt)
                    parsed_date = candidate.replace(year=now.year)
                    break
                except ValueError:
                    continue

            if not parsed_date:
                continue
            if parsed_date.date() < now.date() - timedelta(days=2):
                parsed_date = parsed_date.replace(year=now.year + 1)
            delta_days = (parsed_date.date() - now.date()).days
            parsed_month_day_deltas.append(max(delta_days, 0))
        if parsed_month_day_deltas:
            return min(parsed_month_day_deltas)

        weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        weekday_deltas = []
        for weekday_name, weekday_index in weekday_map.items():
            if weekday_name in lowered:
                current_weekday = now.weekday()
                diff = (weekday_index - current_weekday) % 7
                weekday_deltas.append(diff)
        if weekday_deltas:
            return min(weekday_deltas)

        return None

    @staticmethod
    def extract_displayed_zip(html_text):
        """
        Best-effort ZIP extraction from rendered page content.
        """
        if not html_text:
            return None

        glow_match = re.search(
            r'id="glow-ingress-line2"[^>]*>(.*?)<',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if glow_match:
            glow_text = AmazonDeliveryClient._strip_html(glow_match.group(1))
            zip_match = re.search(r"\b\d{5}(?:-\d{4})?\b", glow_text)
            if zip_match:
                return zip_match.group(0)

        json_zip_match = re.search(r'"zipCode"\s*:\s*"(\d{5}(?:-\d{4})?)"', html_text)
        if json_zip_match:
            return json_zip_match.group(1)

        return None

    @classmethod
    def extract_seller(cls, html_text):
        """
        Attempt to extract the current buybox seller name from product page HTML.
        Returns a cleaned seller name string, or None if extraction fails.

        Tries buybox-first strategies before broad page fallbacks, while
        scoping broad phrase matching to the primary buybox area to avoid
        secondary offers (e.g. "Save with Used", "Get it faster").
        """
        if not html_text:
            return None

        seller_anchor_pattern = r"id\s*=\s*['\"]sellerProfileTriggerId['\"][^>]*>(.*?)</a>"
        merchant_info_pattern = r"id\s*=\s*['\"]merchant-info['\"][^>]*>(.*?)</div>"
        active_row_sold_by_pattern = (
            r"data-csa-c-is-in-initial-active-row\s*=\s*['\"]true['\"]"
            r"[\s\S]{0,22000}?"
            r"[Ss]old by\s*:?\s*</span>\s*<span[^>]*>\s*(.*?)\s*</span>"
        )

        def _extract_from_merchant_info(text_block):
            text = cls._strip_html(text_block)
            sold_by = re.search(r"[Ss]old by\s+(.+?)(?:\s+and\s+|\.|$)", text)
            if not sold_by:
                return None
            seller_name = sold_by.group(1).strip()
            return seller_name if seller_name else None

        buybox_region = cls._extract_buybox_seller_region(html_text) or ""
        if buybox_region:
            # Strategy 1: right-rail shipper/seller row for current active offer.
            match = re.search(
                active_row_sold_by_pattern,
                buybox_region,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                seller = cls._strip_html(match.group(1)).strip().rstrip(".")
                if seller:
                    return seller

            # Strategy 2: seller anchor tied to current active buybox row.
            match = re.search(
                r"data-csa-c-is-in-initial-active-row\s*=\s*['\"]true['\"]"
                r"[\s\S]{0,6000}?"
                + seller_anchor_pattern,
                buybox_region,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                seller = cls._strip_html(match.group(1)).strip()
                if seller:
                    return seller

            # Strategy 3: active-row merchant-info with explicit "Sold by ...".
            match = re.search(
                r"data-csa-c-is-in-initial-active-row\s*=\s*['\"]true['\"]"
                r"[\s\S]{0,6000}?"
                + merchant_info_pattern,
                buybox_region,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                seller = _extract_from_merchant_info(match.group(1))
                if seller:
                    return seller

            # Strategy 4a: any buybox sellerProfileTriggerId anchor.
            match = re.search(
                seller_anchor_pattern,
                buybox_region,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                seller = cls._strip_html(match.group(1)).strip()
                if seller:
                    return seller

            # Strategy 4b: any buybox merchant-info block.
            match = re.search(
                merchant_info_pattern,
                buybox_region,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if match:
                seller = _extract_from_merchant_info(match.group(1))
                if seller:
                    return seller

        # Strategy 5a: whole-page seller anchor fallback.
        match = re.search(
            seller_anchor_pattern,
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            seller = cls._strip_html(match.group(1)).strip()
            if seller:
                return seller

        # Strategy 5b: tabular buybox — element with tabular-attribute-name
        # referencing the seller (e.g. "Sold by", "Seller").
        match = re.search(
            r'tabular-attribute-name="[^"]*(?:[Ss]eller|[Ss]old)[^"]*"[^>]*>(.*?)</span>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            content = match.group(1)
            anchor = re.search(r"<a[^>]*>([^<]+)</a>", content, flags=re.IGNORECASE)
            seller = cls._strip_html(anchor.group(1)).strip() if anchor else cls._strip_html(content).strip()
            if seller:
                return seller

        # Strategy 5c: tabular buybox region — locate the "Seller" / "Shipper"
        # label row and extract the adjacent anchor value.
        tabular_start = re.search(
            r'id="tabular-buybox[^"]*"',
            html_text,
            flags=re.IGNORECASE,
        )
        if tabular_start:
            region = html_text[tabular_start.start():tabular_start.start() + 5000]
            seller_match = re.search(
                r"(?:Seller|Shipper)\b[^<]{0,40}</(?:span|div|td)>"
                r"(?:\s*<[^>]+>)*\s*<a[^>]*>([^<]+)</a>",
                region,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if seller_match:
                seller = seller_match.group(1).strip()
                if seller:
                    return seller

        # Strategy 5d: whole-page merchant-info fallback.
        match = re.search(
            merchant_info_pattern,
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            seller = _extract_from_merchant_info(match.group(1))
            if seller:
                return seller

        # Strategy 5e: "Ships from and sold by" or "Sold by" phrases — only
        # within the primary buybox region to avoid matching secondary offers.
        primary_region = cls._extract_primary_buybox_region(html_text)
        if primary_region:
            for pattern in (
                r"[Ss]hips from and sold by\s+([^.<\n]{2,80})",
                r"[Ss]old by[:\s]+([^<\n.]{2,80})",
            ):
                match = re.search(pattern, primary_region)
                if match:
                    seller = cls._strip_html(match.group(1)).strip().rstrip(".")
                    if seller and len(seller) <= 80:
                        return seller

        return None

    @staticmethod
    def _extract_primary_buybox_region(html_text):
        """
        Return a bounded slice of HTML covering the main buybox, stopping
        before secondary offer sections (Get it faster, Save with Used, etc.).
        """
        if not html_text:
            return None

        lower = html_text.lower()
        for marker in ('id="desktop_buybox"', 'id="buybox"', 'id="rightcol"'):
            idx = lower.find(marker)
            if idx == -1:
                continue
            region = html_text[idx:idx + 8000]
            # Truncate at secondary-offer boundaries so broad patterns
            # do not accidentally match alternative seller listings.
            for cutoff in (
                "olp-upd-new",
                "buybox-see-all-buying-choices",
                "get it faster",
                "save with used",
            ):
                cut_idx = region.lower().find(cutoff)
                if cut_idx > 0:
                    region = region[:cut_idx]
            return region
        return None

    def fetch_delivery_speed(self, asin, zip_code):
        """
        Fetch delivery details for a single ASIN + ZIP pair.
        """
        result = {
            "asin": asin,
            "zip_code": zip_code,
            "delivery_text": None,
            "estimated_days": None,
            "displayed_zip": None,
            "zip_verified": False,
            "status": "error",
            "error": None,
            "seller": None,
        }

        zip_set, zip_error = self._set_zip_code(asin, zip_code)

        product_url = self.PRODUCT_URL_TEMPLATE.format(asin=asin)
        page_response, page_error = self._request_get(product_url, params={"zipCode": zip_code[:5]})
        if page_error:
            result["error"] = page_error
            return result

        html_text = page_response.text if page_response is not None else ""
        if self._is_captcha_page(html_text):
            result["status"] = "captcha"
            result["error"] = "Captcha encountered. Slow down requests or use a trusted proxy/session."
            return result

        result["displayed_zip"] = self.extract_displayed_zip(html_text)
        if result["displayed_zip"]:
            result["zip_verified"] = result["displayed_zip"].startswith(zip_code[:5])

        result["seller"] = self.extract_seller(html_text)

        delivery_text = self.extract_delivery_message(html_text)
        if not delivery_text:
            result["status"] = "not_found"
            result["error"] = (
                "Delivery message not found on product page."
                if zip_set
                else f"ZIP update uncertain; message missing ({zip_error or 'unknown reason'})."
            )
            return result

        result["delivery_text"] = delivery_text
        result["estimated_days"] = self.estimate_delivery_days(delivery_text)
        result["status"] = "ok"

        if not zip_set and zip_error:
            result["error"] = f"ZIP update warning: {zip_error}"
        return result


class DeliverySpeedTracker:
    """
    Tkinter flow to gather ASIN/ZIP inputs and display delivery speed matrix.
    """

    def __init__(self):
        self.memory_store = DeliverySpeedMemoryStore()

    def get_user_input(self, parent_window=None):
        root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        root.title("Delivery Speed by ZIP - Input")
        root.resizable(True, True)
        root.minsize(760, 700)

        # Center the window on the same screen as the parent
        center_window_on_parent(root, parent_window, 820, 760)

        root.lift()
        root.attributes("-topmost", True)
        root.after_idle(lambda: root.attributes("-topmost", False))

        result_var = [None]

        asins_var = tk.StringVar()
        zips_var = tk.StringVar()
        min_delay_var = tk.StringVar(value="2.0")
        max_delay_var = tk.StringVar(value="5.0")
        retries_var = tk.StringVar(value="3")
        timeout_var = tk.StringVar(value="30")
        threshold_days_var = tk.StringVar(value="3")
        proxy_var = tk.StringVar()
        export_var = tk.BooleanVar(value=True)
        zip_lists_data = load_all_zip_lists()
        saved_zip_list_var = tk.StringVar(value=sorted(zip_lists_data.keys())[0] if zip_lists_data else "")

        def load_all_saved_asins():
            asins = load_saved_asins()
            if not asins:
                messagebox.showinfo("No ASINs", "No saved ASINs found.", parent=root)
                return
            asin_text.delete("1.0", tk.END)
            asin_text.insert("1.0", "\n".join(sorted(asins)))

        def load_asins_from_list():
            lists_data = load_all_asin_lists()
            if not lists_data:
                messagebox.showinfo("No Lists", "No ASIN lists found.", parent=root)
                return

            pick_window = tk.Toplevel(root)
            pick_window.title("Select ASIN List")
            pick_window.transient(root)
            pick_window.grab_set()
            pick_window.resizable(True, True)
            pick_window.minsize(380, 200)
            center_window_on_parent(pick_window, root, 420, 220)

            ttk.Label(pick_window, text="Choose list:").pack(pady=(20, 8))
            list_var = tk.StringVar(value=sorted(lists_data.keys())[0])
            combo = ttk.Combobox(
                pick_window,
                textvariable=list_var,
                values=sorted(lists_data.keys()),
                state="readonly",
                width=36,
            )
            combo.pack()

            def apply_list():
                selected = list_var.get()
                asins = lists_data.get(selected, {}).get("asins", [])
                asin_text.delete("1.0", tk.END)
                asin_text.insert("1.0", "\n".join(sorted(asins)))
                pick_window.destroy()

            ttk.Button(pick_window, text="Load", command=apply_list, style="Accent.TButton").pack(pady=20)
            pick_window.wait_window()

        def refresh_saved_zip_lists():
            """Refresh saved ZIP list dropdown values."""
            nonlocal zip_lists_data
            zip_lists_data = load_all_zip_lists()
            list_names = sorted(zip_lists_data.keys())
            saved_zip_list_combo["values"] = list_names
            if list_names and saved_zip_list_var.get() not in list_names:
                saved_zip_list_var.set(list_names[0])
            if not list_names:
                saved_zip_list_var.set("")

        def load_selected_zip_list(show_message=True):
            """Load the selected saved ZIP list into the ZIP input box."""
            selected_list = saved_zip_list_var.get().strip()
            if not selected_list:
                if show_message:
                    messagebox.showwarning("No ZIP List", "Please select a saved ZIP list first.", parent=root)
                return False

            current_zip_lists = load_all_zip_lists()
            zips = current_zip_lists.get(selected_list, {}).get("zips", [])
            if not zips:
                if show_message:
                    messagebox.showwarning(
                        "Empty ZIP List",
                        f"ZIP list '{selected_list}' has no ZIP codes.",
                        parent=root,
                    )
                return False

            zip_text.delete("1.0", tk.END)
            zip_text.insert("1.0", "\n".join(zips))
            if show_message:
                messagebox.showinfo(
                    "ZIP List Loaded",
                    f"Loaded {len(zips)} ZIP code(s) from '{selected_list}'.",
                    parent=root,
                )
            return True

        def save_current_zip_list():
            """Save ZIP codes currently in the input box as a named list."""
            zip_raw = zip_text.get("1.0", tk.END).strip()
            valid_zips, invalid_zips = parse_zip_list(zip_raw)
            if invalid_zips:
                preview = ", ".join(invalid_zips[:6])
                if len(invalid_zips) > 6:
                    preview += f" ... and {len(invalid_zips) - 6} more"
                messagebox.showerror(
                    "Validation Error",
                    f"Invalid ZIP code(s): {preview}\nUse 5-digit ZIP format (example: 10001).",
                    parent=root,
                )
                return

            if not valid_zips:
                messagebox.showerror(
                    "Validation Error",
                    "Please enter at least one valid ZIP code before saving.",
                    parent=root,
                )
                return

            suggested_name = saved_zip_list_var.get().strip()
            list_name = simpledialog.askstring(
                "Save ZIP List",
                "Enter a name for this ZIP list:",
                initialvalue=suggested_name,
                parent=root,
            )
            if not list_name or not list_name.strip():
                return
            list_name = list_name.strip()

            current_zip_lists = load_all_zip_lists()
            if list_name in current_zip_lists:
                overwrite = messagebox.askyesno(
                    "Overwrite ZIP List",
                    f"A ZIP list named '{list_name}' already exists.\nOverwrite it?",
                    parent=root,
                )
                if not overwrite:
                    return

            saved, error = save_zip_list(list_name, valid_zips)
            if not saved:
                messagebox.showerror("Save Failed", error or "Unable to save ZIP list.", parent=root)
                return

            refresh_saved_zip_lists()
            saved_zip_list_var.set(list_name)
            messagebox.showinfo(
                "ZIP List Saved",
                f"Saved {len(valid_zips)} ZIP code(s) to '{list_name}'.",
                parent=root,
            )

        def submit_selected_zip_list():
            """Convenience action: load selected ZIP list and submit."""
            if load_selected_zip_list(show_message=False):
                submit()

        def submit():
            asin_raw = asin_text.get("1.0", tk.END).strip()
            valid_asins, asin_error = validate_asin_list(asin_raw)
            if asin_error:
                messagebox.showerror("Validation Error", asin_error, parent=root)
                return
            if not valid_asins:
                messagebox.showerror("Validation Error", "Please provide at least one valid ASIN.", parent=root)
                return

            zip_raw = zip_text.get("1.0", tk.END).strip()
            if not zip_raw and saved_zip_list_var.get().strip():
                selected_zip_list = saved_zip_list_var.get().strip()
                valid_zips = load_all_zip_lists().get(selected_zip_list, {}).get("zips", [])
                invalid_zips = []
            else:
                valid_zips, invalid_zips = parse_zip_list(zip_raw)
            if invalid_zips:
                preview = ", ".join(invalid_zips[:6])
                if len(invalid_zips) > 6:
                    preview += f" ... and {len(invalid_zips) - 6} more"
                messagebox.showerror(
                    "Validation Error",
                    f"Invalid ZIP code(s): {preview}\nUse 5-digit ZIP format (example: 10001).",
                    parent=root,
                )
                return
            if not valid_zips:
                messagebox.showerror("Validation Error", "Please provide at least one ZIP code.", parent=root)
                return

            try:
                min_delay = float(min_delay_var.get().strip())
                max_delay = float(max_delay_var.get().strip())
                retries = int(retries_var.get().strip())
                timeout = int(timeout_var.get().strip())
                threshold_days = int(threshold_days_var.get().strip())
            except ValueError:
                messagebox.showerror(
                    "Validation Error",
                    "Delay values must be numbers, and retries/timeout/threshold must be integers.",
                    parent=root,
                )
                return

            if min_delay < 0 or max_delay < 0 or max_delay < min_delay:
                messagebox.showerror(
                    "Validation Error",
                    "Delay values must be non-negative and max delay must be >= min delay.",
                    parent=root,
                )
                return

            if retries < 0 or retries > 10:
                messagebox.showerror("Validation Error", "Retries must be between 0 and 10.", parent=root)
                return

            if timeout < 5 or timeout > 180:
                messagebox.showerror("Validation Error", "Timeout must be between 5 and 180 seconds.", parent=root)
                return

            if threshold_days < 0 or threshold_days > 30:
                messagebox.showerror(
                    "Validation Error",
                    "Delivery pass threshold must be between 0 and 30 days.",
                    parent=root,
                )
                return

            total_calls = len(valid_asins) * len(valid_zips)
            if total_calls > 100 and min_delay < 2:
                continue_run = messagebox.askyesno(
                    "Rate Limit Warning",
                    (
                        f"You are about to run {total_calls} ASIN/ZIP checks with very low delay.\n\n"
                        "This increases risk of bot challenges or temporary IP throttling.\n"
                        "Recommended: min delay >= 2 seconds.\n\n"
                        "Continue anyway?"
                    ),
                    parent=root,
                )
                if not continue_run:
                    return

            result_var[0] = {
                "asins": valid_asins,
                "zips": valid_zips,
                "min_delay_sec": min_delay,
                "max_delay_sec": max_delay,
                "max_retries": retries,
                "timeout_sec": timeout,
                "pass_threshold_days": threshold_days,
                "proxy_url": proxy_var.get().strip(),
                "export_csv": export_var.get(),
            }
            root.destroy()

        def cancel():
            root.destroy()

        main_frame = ttk.Frame(root, padding="16")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(main_frame, text="Delivery Speed by ZIP", font=scaled_font("Arial", 18, "bold"))
        title.pack(anchor=tk.W, pady=(0, 10))

        subtitle = ttk.Label(
            main_frame,
            text=(
                "Checks Amazon product pages for delivery message text and estimates delivery days.\n"
                "Use conservative delays to reduce bot detection risk."
            ),
            foreground="gray",
        )
        subtitle.pack(anchor=tk.W, pady=(0, 14))

        asin_frame = ttk.LabelFrame(main_frame, text="ASINs", padding="10")
        asin_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        asin_btns = ttk.Frame(asin_frame)
        asin_btns.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(asin_btns, text="Load All Saved ASINs", command=load_all_saved_asins).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(asin_btns, text="Load from List", command=load_asins_from_list).pack(side=tk.LEFT)

        asin_text = tk.Text(asin_frame, height=9)
        asin_text.pack(fill=tk.BOTH, expand=True)
        asin_text.insert("1.0", asins_var.get())

        zip_frame = ttk.LabelFrame(main_frame, text="ZIP Codes", padding="10")
        zip_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        zip_controls = ttk.Frame(zip_frame)
        zip_controls.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(zip_controls, text="Saved ZIP List:").pack(side=tk.LEFT)
        saved_zip_list_combo = ttk.Combobox(
            zip_controls,
            textvariable=saved_zip_list_var,
            values=sorted(zip_lists_data.keys()),
            state="readonly",
            width=28,
        )
        saved_zip_list_combo.pack(side=tk.LEFT, padx=(8, 8))
        ttk.Button(zip_controls, text="Load", command=load_selected_zip_list).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(zip_controls, text="Save Current", command=save_current_zip_list).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(zip_controls, text="Refresh", command=refresh_saved_zip_lists).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(zip_controls, text="Submit Saved List", command=submit_selected_zip_list).pack(side=tk.LEFT)

        zip_help = ttk.Label(zip_frame, text="Enter 5-digit ZIPs separated by comma, space, or newline.")
        zip_help.pack(anchor=tk.W, pady=(0, 5))
        zip_text = tk.Text(zip_frame, height=6)
        zip_text.pack(fill=tk.BOTH, expand=True)
        zip_text.insert("1.0", zips_var.get())
        refresh_saved_zip_lists()

        settings_frame = ttk.LabelFrame(main_frame, text="Request Safety Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 12))

        settings_grid = ttk.Frame(settings_frame)
        settings_grid.pack(fill=tk.X)
        settings_grid.columnconfigure(1, weight=1)
        settings_grid.columnconfigure(3, weight=1)

        ttk.Label(settings_grid, text="Min Delay (sec):").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=4)
        ttk.Entry(settings_grid, textvariable=min_delay_var, width=10).grid(row=0, column=1, sticky=tk.W, pady=4)

        ttk.Label(settings_grid, text="Max Delay (sec):").grid(row=0, column=2, sticky=tk.W, padx=(20, 6), pady=4)
        ttk.Entry(settings_grid, textvariable=max_delay_var, width=10).grid(row=0, column=3, sticky=tk.W, pady=4)

        ttk.Label(settings_grid, text="Max Retries:").grid(row=1, column=0, sticky=tk.W, padx=(0, 6), pady=4)
        ttk.Entry(settings_grid, textvariable=retries_var, width=10).grid(row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(settings_grid, text="Timeout (sec):").grid(row=1, column=2, sticky=tk.W, padx=(20, 6), pady=4)
        ttk.Entry(settings_grid, textvariable=timeout_var, width=10).grid(row=1, column=3, sticky=tk.W, pady=4)

        ttk.Label(settings_grid, text="Pass Threshold (days):").grid(row=2, column=0, sticky=tk.W, padx=(0, 6), pady=4)
        ttk.Entry(settings_grid, textvariable=threshold_days_var, width=10).grid(row=2, column=1, sticky=tk.W, pady=4)

        ttk.Label(settings_grid, text="Optional Proxy URL:").grid(row=3, column=0, sticky=tk.W, padx=(0, 6), pady=4)
        ttk.Entry(settings_grid, textvariable=proxy_var).grid(row=3, column=1, columnspan=3, sticky=(tk.W, tk.E), pady=4)

        ttk.Checkbutton(main_frame, text="Export current run results to CSV", variable=export_var).pack(anchor=tk.W, pady=(0, 12))

        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X)
        ttk.Button(action_frame, text="Run", command=submit, style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(action_frame, text="Cancel", command=cancel).pack(side=tk.LEFT)
        ttk.Button(
            action_frame,
            text="View History",
            command=lambda: self.open_history_viewer(parent_window=root),
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Keyboard shortcuts make submission accessible on smaller displays.
        root.bind("<Return>", lambda _e: submit())
        root.bind("<Escape>", lambda _e: cancel())

        if not parent_window:
            root.mainloop()
        else:
            root.wait_window()

        return result_var[0]

    def _export_history_rows_to_csv(self, rows, parent_window, default_filename):
        if not rows:
            messagebox.showinfo(
                "No Data",
                "No historical rows were found for export.",
                parent=parent_window,
            )
            return

        save_path = filedialog.asksaveasfilename(
            title="Save delivery speed history",
            defaultextension=".csv",
            initialfile=default_filename,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            parent=parent_window,
        )
        if not save_path:
            return

        pd.DataFrame(rows).to_csv(save_path, index=False)
        messagebox.showinfo(
            "Export Complete",
            f"Saved {len(rows)} historical rows to:\n{save_path}",
            parent=parent_window,
        )

    def export_delivery_history(
        self,
        parent_window=None,
        asin=None,
        zip_code=None,
        status=None,
        default_filename="delivery_speed_history_all_records.csv",
    ):
        rows = self.memory_store.get_history_rows(
            asin=asin,
            zip_code=zip_code,
            status=status,
            limit=None,
        )
        self._export_history_rows_to_csv(rows, parent_window=parent_window, default_filename=default_filename)

    def _draw_delivery_history_chart(self, canvas, rows, asin_filter, zip_filter):
        canvas.delete("all")
        width = max(canvas.winfo_width(), 760)
        height = max(canvas.winfo_height(), 260)

        header = f"Delivery Days History | ASIN: {asin_filter or 'All'} | ZIP: {zip_filter or 'All'}"
        canvas.create_text(14, 10, text=header, anchor=tk.NW, fill="#222222", font=scaled_font("Arial", 10, "bold"))

        chart_rows = []
        for row in rows:
            if row.get("status") != "ok":
                continue
            if row.get("estimated_days") is None:
                continue
            try:
                checked_time = datetime.strptime(row["checked_at"], "%Y-%m-%d %H:%M:%S").timestamp()
                days_value = float(row["estimated_days"])
            except (TypeError, ValueError):
                continue
            chart_rows.append((checked_time, days_value, row["checked_at"]))

        if not chart_rows:
            canvas.create_text(
                20,
                40,
                text="No chartable rows in current filter (requires status=ok with estimated days).",
                anchor=tk.NW,
                fill="#555555",
            )
            return

        left_margin = 70
        right_margin = 20
        top_margin = 35
        bottom_margin = 65
        plot_width = width - left_margin - right_margin
        plot_height = height - top_margin - bottom_margin

        time_points = [row[0] for row in chart_rows]
        day_values = [row[1] for row in chart_rows]

        min_days = min(day_values)
        max_days = max(day_values)
        if min_days == max_days:
            min_days -= 1
            max_days += 1

        min_time = min(time_points)
        max_time = max(time_points)
        if min_time == max_time:
            max_time += 1

        def map_x(timestamp_value):
            ratio = (timestamp_value - min_time) / (max_time - min_time)
            return left_margin + (ratio * plot_width)

        def map_y(day_value):
            ratio = (day_value - min_days) / (max_days - min_days)
            return top_margin + ((1 - ratio) * plot_height)

        canvas.create_line(left_margin, top_margin, left_margin, top_margin + plot_height, fill="#666666")
        canvas.create_line(
            left_margin,
            top_margin + plot_height,
            left_margin + plot_width,
            top_margin + plot_height,
            fill="#666666",
        )

        y_tick_count = 4
        for i in range(y_tick_count + 1):
            ratio = i / y_tick_count
            day_tick = max_days - (ratio * (max_days - min_days))
            y = top_margin + (ratio * plot_height)
            canvas.create_line(left_margin - 5, y, left_margin, y, fill="#666666")
            canvas.create_text(
                left_margin - 8,
                y,
                text=f"{day_tick:.1f}",
                anchor=tk.E,
                fill="#444444",
                font=scaled_font("Arial", 8),
            )

        x_tick_indices = sorted(set([0, len(chart_rows) // 2, len(chart_rows) - 1]))
        for idx in x_tick_indices:
            x = map_x(chart_rows[idx][0])
            label = datetime.strptime(chart_rows[idx][2], "%Y-%m-%d %H:%M:%S").strftime("%m-%d %H:%M")
            canvas.create_line(x, top_margin + plot_height, x, top_margin + plot_height + 5, fill="#666666")
            canvas.create_text(
                x,
                top_margin + plot_height + 18,
                text=label,
                anchor=tk.N,
                fill="#444444",
                font=scaled_font("Arial", 8),
            )

        points = []
        for timestamp_value, day_value, _checked_at in chart_rows:
            x = map_x(timestamp_value)
            y = map_y(day_value)
            points.extend([x, y])

        if len(points) >= 4:
            canvas.create_line(*points, fill="#1F77B4", width=2, smooth=True)
        for i in range(0, len(points), 2):
            x_coord = points[i]
            y_coord = points[i + 1]
            canvas.create_oval(
                x_coord - 2.5,
                y_coord - 2.5,
                x_coord + 2.5,
                y_coord + 2.5,
                fill="#1F77B4",
                outline="#1F77B4",
            )

    def open_history_viewer(self, parent_window=None, preselected_asin=None, preselected_zip=None):
        history_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        history_root.title("Delivery Speed History Explorer")
        history_root.resizable(True, True)
        history_root.minsize(1220, 820)

        # Size and position window on the same screen as the parent
        history_root.update_idletasks()
        screen_width = history_root.winfo_screenwidth()
        screen_height = history_root.winfo_screenheight()
        width = min(int(screen_width * 0.95), 1500)
        height = min(int(screen_height * 0.92), 980)
        center_window_on_parent(history_root, parent_window, width, height)

        history_root.lift()
        history_root.attributes("-topmost", True)
        history_root.after_idle(lambda: history_root.attributes("-topmost", False))

        asins = self.memory_store.get_distinct_asins()
        if not asins:
            messagebox.showinfo(
                "No History Available",
                "No delivery speed history found in the database yet.",
                parent=history_root,
            )
            history_root.destroy()
            return

        container = ttk.Frame(history_root, padding="12")
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="Delivery Speed History Explorer", font=scaled_font("Arial", 16, "bold")).pack(anchor=tk.W, pady=(0, 10))

        controls = ttk.Frame(container)
        controls.pack(fill=tk.X, pady=(0, 8))

        asin_var = tk.StringVar(value="All ASINs")
        zip_var = tk.StringVar(value="All ZIPs")
        status_var = tk.StringVar(value="All Statuses")
        limit_var = tk.StringVar(value="2000")

        ttk.Label(controls, text="ASIN:").pack(side=tk.LEFT)
        asin_combo = ttk.Combobox(
            controls,
            textvariable=asin_var,
            state="readonly",
            width=20,
            values=["All ASINs"] + asins,
        )
        asin_combo.pack(side=tk.LEFT, padx=(6, 10))
        if preselected_asin and preselected_asin in asins:
            asin_var.set(preselected_asin)

        ttk.Label(controls, text="ZIP:").pack(side=tk.LEFT)
        zip_combo = ttk.Combobox(
            controls,
            textvariable=zip_var,
            state="readonly",
            width=12,
            values=["All ZIPs"],
        )
        zip_combo.pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(controls, text="Status:").pack(side=tk.LEFT)
        status_combo = ttk.Combobox(
            controls,
            textvariable=status_var,
            state="readonly",
            width=14,
            values=["All Statuses", "ok", "captcha", "not_found", "error"],
        )
        status_combo.pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(controls, text="Row limit:").pack(side=tk.LEFT)
        ttk.Entry(controls, textvariable=limit_var, width=8).pack(side=tk.LEFT, padx=(6, 12))

        summary_var = tk.StringVar(value="")
        ttk.Label(container, textvariable=summary_var, foreground="gray").pack(anchor=tk.W, pady=(0, 8))

        chart_canvas = tk.Canvas(container, bg="white", height=260, highlightthickness=1, highlightbackground="#D9D9D9")
        chart_canvas.pack(fill=tk.X, expand=False, pady=(0, 10))

        columns = (
            "checked_at",
            "asin",
            "zip_code",
            "estimated_days",
            "review",
            "seller",
            "threshold_days",
            "status",
            "zip_verified",
            "displayed_zip",
            "review_reason",
        )
        tree = ttk.Treeview(container, columns=columns, show="headings", height=15)
        tree.heading("checked_at", text="Checked At")
        tree.heading("asin", text="ASIN")
        tree.heading("zip_code", text="ZIP")
        tree.heading("estimated_days", text="Est. Days")
        tree.heading("review", text="Review")
        tree.heading("seller", text="Seller")
        tree.heading("threshold_days", text="Threshold")
        tree.heading("status", text="Status")
        tree.heading("zip_verified", text="ZIP Verified")
        tree.heading("displayed_zip", text="ZIP on Page")
        tree.heading("review_reason", text="Review Reason")

        tree.column("checked_at", width=scaled(150), anchor=tk.W)
        tree.column("asin", width=scaled(120), anchor=tk.W)
        tree.column("zip_code", width=scaled(90), anchor=tk.W)
        tree.column("estimated_days", width=scaled(90), anchor=tk.CENTER)
        tree.column("review", width=scaled(80), anchor=tk.CENTER)
        tree.column("seller", width=scaled(150), anchor=tk.W)
        tree.column("threshold_days", width=scaled(80), anchor=tk.CENTER)
        tree.column("status", width=scaled(100), anchor=tk.W)
        tree.column("zip_verified", width=scaled(95), anchor=tk.CENTER)
        tree.column("displayed_zip", width=scaled(100), anchor=tk.W)
        tree.column("review_reason", width=scaled(380), anchor=tk.W)

        tree_scrollbar_y = ttk.Scrollbar(container, orient=tk.VERTICAL, command=tree.yview)
        tree_scrollbar_x = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=tree_scrollbar_y.set, xscrollcommand=tree_scrollbar_x.set)

        tree.pack(fill=tk.BOTH, expand=True)
        tree_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        tree_scrollbar_x.pack(fill=tk.X)

        tree.tag_configure("pass", background="#EAF8EA")
        tree.tag_configure("review_fail", background="#FFF4E5")
        tree.tag_configure("captcha", background="#FFF4E5")
        tree.tag_configure("error", background="#FDECEC")
        # Seller tags — listed last in the tags tuple so they take visual priority.
        # Amazon = green (#EAF8EA), non-Amazon = red (#FDECEC), unknown = yellow (#FFF4E5).
        tree.tag_configure("seller_amazon", background="#EAF8EA")
        tree.tag_configure("seller_other", background="#FDECEC")
        tree.tag_configure("seller_unknown", background="#FFF4E5")

        details_frame = ttk.LabelFrame(container, text="Selected Row Details", padding="8")
        details_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        details_box = scrolledtext.ScrolledText(details_frame, height=7, wrap=tk.WORD)
        details_box.pack(fill=tk.BOTH, expand=True)
        details_box.insert(
            tk.END,
            "Select a row to inspect full delivery text and notes.",
        )
        details_box.config(state=tk.DISABLED)

        current_rows = {"rows": []}

        def parse_limit_value():
            limit_text = limit_var.get().strip()
            if not limit_text:
                return None
            try:
                parsed_limit = int(limit_text)
                if parsed_limit <= 0:
                    return None
                return parsed_limit
            except ValueError:
                return None

        def selected_filters():
            asin_filter = asin_var.get().strip()
            zip_filter = zip_var.get().strip()
            status_filter = status_var.get().strip()
            return (
                None if asin_filter == "All ASINs" else asin_filter,
                None if zip_filter == "All ZIPs" else zip_filter,
                None if status_filter == "All Statuses" else status_filter,
            )

        def refresh_zip_choices():
            asin_filter, _, _ = selected_filters()
            current_zip_values = self.memory_store.get_distinct_zip_codes(asin=asin_filter)
            zip_options = ["All ZIPs"] + current_zip_values
            previous_zip = zip_var.get().strip()
            zip_combo["values"] = zip_options

            if preselected_zip and preselected_zip in current_zip_values:
                zip_var.set(preselected_zip)
            elif previous_zip in zip_options:
                zip_var.set(previous_zip)
            else:
                zip_var.set("All ZIPs")

        def refresh_view():
            asin_filter, zip_filter, status_filter = selected_filters()
            rows = self.memory_store.get_history_rows(
                asin=asin_filter,
                zip_code=zip_filter,
                status=status_filter,
                limit=parse_limit_value(),
            )
            current_rows["rows"] = rows

            for item in tree.get_children():
                tree.delete(item)

            for row in rows:
                if row.get("review") == "PASS":
                    base_tag = "pass"
                elif row.get("status") == "captcha":
                    base_tag = "captcha"
                elif row.get("status") == "ok":
                    base_tag = "review_fail"
                else:
                    base_tag = "error"

                # Seller tag is listed second so it overrides base_tag for row background.
                seller_val = row.get("seller") or ""
                if not seller_val:
                    s_tag = "seller_unknown"
                elif "amazon" in seller_val.lower():
                    s_tag = "seller_amazon"
                else:
                    s_tag = "seller_other"

                tree.insert(
                    "",
                    tk.END,
                    values=(
                        row.get("checked_at", ""),
                        row.get("asin", ""),
                        row.get("zip_code", ""),
                        row.get("estimated_days", "") if row.get("estimated_days") is not None else "",
                        row.get("review", ""),
                        seller_val,
                        row.get("threshold_days", ""),
                        row.get("status", ""),
                        "Yes" if row.get("zip_verified") else "No",
                        row.get("displayed_zip", "") or "",
                        row.get("review_reason", ""),
                    ),
                    tags=(base_tag, s_tag),
                )

            summary_var.set(
                f"Showing {len(rows)} history row(s) | ASIN={asin_filter or 'All'} | ZIP={zip_filter or 'All'} | Status={status_filter or 'All'}"
            )
            self._draw_delivery_history_chart(chart_canvas, rows, asin_filter, zip_filter)

        def export_filtered():
            asin_filter, zip_filter, _status_filter = selected_filters()
            asin_part = asin_filter if asin_filter else "all_asins"
            zip_part = zip_filter if zip_filter else "all_zips"
            filename = f"delivery_speed_history_{asin_part}_{zip_part}.csv".replace(" ", "_")
            self._export_history_rows_to_csv(current_rows["rows"], parent_window=history_root, default_filename=filename)

        def on_select(_event):
            selection = tree.selection()
            if not selection:
                return
            values = tree.item(selection[0], "values")
            checked_at = values[0]
            asin = values[1]
            zip_code = values[2]
            matched_row = next(
                (
                    row for row in current_rows["rows"]
                    if row.get("checked_at") == checked_at
                    and row.get("asin") == asin
                    and row.get("zip_code") == zip_code
                ),
                None,
            )
            if not matched_row:
                return

            details_box.config(state=tk.NORMAL)
            details_box.delete("1.0", tk.END)
            details_box.insert(
                tk.END,
                (
                    f"Checked at: {matched_row.get('checked_at', '')}\n"
                    f"ASIN: {matched_row.get('asin', '')}\n"
                    f"ZIP requested: {matched_row.get('zip_code', '')}\n"
                    f"Estimated days: {matched_row.get('estimated_days', '')}\n"
                    f"Review: {matched_row.get('review', '')} | Threshold: {matched_row.get('threshold_days', '')}\n"
                    f"Seller: {matched_row.get('seller', '') or 'N/A'}\n"
                    f"Status: {matched_row.get('status', '')}\n"
                    f"ZIP verified on page: {'Yes' if matched_row.get('zip_verified') else 'No'} (page showed: {matched_row.get('displayed_zip', '') or 'N/A'})\n"
                    f"Reason: {matched_row.get('review_reason', '')}\n\n"
                    f"Delivery message:\n{matched_row.get('delivery_text', '') or 'N/A'}\n\n"
                    f"Error / Notes:\n{matched_row.get('error', '') or 'N/A'}"
                ),
            )
            details_box.config(state=tk.DISABLED)

        actions = ttk.Frame(container)
        actions.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(actions, text="Refresh View", command=refresh_view).pack(side=tk.LEFT)
        ttk.Button(actions, text="Export Filtered CSV", command=export_filtered).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            actions,
            text="Export Full History CSV",
            command=lambda: self.export_delivery_history(parent_window=history_root),
        ).pack(side=tk.LEFT, padx=(8, 0))

        asin_combo.bind("<<ComboboxSelected>>", lambda _event: (refresh_zip_choices(), refresh_view()))
        zip_combo.bind("<<ComboboxSelected>>", lambda _event: refresh_view())
        status_combo.bind("<<ComboboxSelected>>", lambda _event: refresh_view())
        tree.bind("<<TreeviewSelect>>", on_select)
        chart_canvas.bind("<Configure>", lambda _event: self._draw_delivery_history_chart(
            chart_canvas,
            current_rows["rows"],
            selected_filters()[0],
            selected_filters()[1],
        ))

        refresh_zip_choices()
        refresh_view()

        if not parent_window:
            history_root.mainloop()
        else:
            history_root.wait_window()

    def process_and_display_results(self, config, parent_window=None):
        asins = config["asins"]
        zips = config["zips"]
        threshold_days = int(config.get("pass_threshold_days", 3))

        client = AmazonDeliveryClient(
            min_delay_sec=config["min_delay_sec"],
            max_delay_sec=config["max_delay_sec"],
            max_retries=config["max_retries"],
            timeout_sec=config["timeout_sec"],
            proxy_url=config["proxy_url"],
        )
        memory_store = self.memory_store

        total = len(asins) * len(zips)
        results = []

        progress_window = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        progress_window.title("Checking Delivery Speeds")
        progress_window.resizable(False, False)
        progress_window.lift()
        progress_window.attributes("-topmost", True)

        # Center on the same screen as the parent
        center_window_on_parent(progress_window, parent_window, 620, 220)

        ttk.Label(progress_window, text="Running ASIN + ZIP checks...", font=scaled_font("Arial", 12)).pack(pady=(20, 14))
        progress = ttk.Progressbar(progress_window, length=420, mode="determinate", maximum=total)
        progress.pack()
        status_var = tk.StringVar(value="Starting...")
        ttk.Label(progress_window, textvariable=status_var, foreground="gray").pack(pady=(12, 0))

        completed = 0
        for asin in asins:
            for zip_code in zips:
                completed += 1
                status_var.set(f"{completed}/{total} | ASIN {asin} | ZIP {zip_code}")
                progress["value"] = completed
                progress_window.update()

                row = client.fetch_delivery_speed(asin, zip_code)
                review_meta = memory_store.log_check(row, threshold_days=threshold_days)
                row.update(review_meta)
                row["threshold_days"] = threshold_days

                pair_summary = memory_store.get_pair_summary(asin=row.get("asin", ""), zip_code=row.get("zip_code", ""))
                row["pair_pass_checks"] = pair_summary["pass_checks"]
                row["pair_total_checks"] = pair_summary["total_checks"]
                row["pair_standard_hits"] = f'{pair_summary["pass_checks"]}/{pair_summary["total_checks"]}'
                results.append(row)

        progress_window.destroy()
        overall_memory = memory_store.get_overall_summary()

        result_root = tk.Toplevel(parent_window) if parent_window else tk.Tk()
        result_root.title("Delivery Speed by ZIP - Results")
        result_root.resizable(True, True)
        result_root.minsize(1200, 760)

        # Size and position window on the same screen as the parent
        result_root.update_idletasks()
        width = min(int(result_root.winfo_screenwidth() * 0.95), 1920)
        height = min(int(result_root.winfo_screenheight() * 0.9), 1080)
        center_window_on_parent(result_root, parent_window, width, height)
        result_root.lift()
        result_root.attributes("-topmost", True)
        result_root.after_idle(lambda: result_root.attributes("-topmost", False))

        container = ttk.Frame(result_root, padding="12")
        container.pack(fill=tk.BOTH, expand=True)

        ok_count = sum(1 for row in results if row["status"] == "ok")
        captcha_count = sum(1 for row in results if row["status"] == "captcha")
        issue_count = sum(1 for row in results if row["status"] not in ("ok", "captcha"))
        run_pass_count = sum(1 for row in results if row.get("review") == "PASS")
        run_fail_count = len(results) - run_pass_count

        summary_text = (
            f"Current run: {len(results)} checks | Status OK: {ok_count} | Captcha: {captcha_count} | Issues: {issue_count} | "
            f"PASS: {run_pass_count} | FAIL: {run_fail_count} (threshold <= {threshold_days} days)"
        )
        ttk.Label(container, text=summary_text, font=scaled_font("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 8))

        historical_text = (
            f"Historical up-to-standard: {overall_memory['pass_checks']} / {overall_memory['total_checks']} checks "
            f"({overall_memory['pass_rate_percent']:.1f}% pass rate)"
        )
        ttk.Label(container, text=historical_text, foreground="#1f4d1f").pack(anchor=tk.W, pady=(0, 8))

        info_text = (
            "Tip: If captcha counts are high, increase delays, reduce batch size, "
            "or use a trusted proxy/session. Each run is logged with timestamp and pass/fail review."
        )
        ttk.Label(container, text=info_text, foreground="gray").pack(anchor=tk.W, pady=(0, 10))

        history_actions = ttk.Frame(container)
        history_actions.pack(fill=tk.X, pady=(0, 8))
        default_asin = asins[0] if len(asins) == 1 else None
        default_zip = zips[0] if len(zips) == 1 else None
        ttk.Button(
            history_actions,
            text="View Delivery History",
            command=lambda: self.open_history_viewer(
                parent_window=result_root,
                preselected_asin=default_asin,
                preselected_zip=default_zip,
            ),
        ).pack(side=tk.LEFT)
        ttk.Button(
            history_actions,
            text="Export Full History CSV",
            command=lambda: self.export_delivery_history(parent_window=result_root),
        ).pack(side=tk.LEFT, padx=(8, 0))

        columns = (
            "asin",
            "zip_code",
            "estimated_days",
            "review",
            "seller",
            "threshold_days",
            "checked_at",
            "pair_standard_hits",
            "review_reason",
            "status",
            "zip_verified",
            "displayed_zip",
            "delivery_text",
            "error",
        )
        tree = ttk.Treeview(container, columns=columns, show="headings", height=18)
        tree.heading("asin", text="ASIN")
        tree.heading("zip_code", text="ZIP Requested")
        tree.heading("estimated_days", text="Est. Days")
        tree.heading("review", text="Review")
        tree.heading("seller", text="Seller")
        tree.heading("threshold_days", text="Threshold")
        tree.heading("checked_at", text="Checked At")
        tree.heading("pair_standard_hits", text="Passes/Checks")
        tree.heading("review_reason", text="Review Reason")
        tree.heading("status", text="Status")
        tree.heading("zip_verified", text="ZIP Verified")
        tree.heading("displayed_zip", text="ZIP on Page")
        tree.heading("delivery_text", text="Delivery Message")
        tree.heading("error", text="Error / Notes")

        tree.column("asin", width=scaled(120), anchor=tk.W)
        tree.column("zip_code", width=scaled(100), anchor=tk.W)
        tree.column("estimated_days", width=scaled(90), anchor=tk.CENTER)
        tree.column("review", width=scaled(80), anchor=tk.CENTER)
        tree.column("seller", width=scaled(150), anchor=tk.W)
        tree.column("threshold_days", width=scaled(80), anchor=tk.CENTER)
        tree.column("checked_at", width=scaled(145), anchor=tk.W)
        tree.column("pair_standard_hits", width=scaled(110), anchor=tk.CENTER)
        tree.column("review_reason", width=scaled(240), anchor=tk.W)
        tree.column("status", width=scaled(90), anchor=tk.W)
        tree.column("zip_verified", width=scaled(90), anchor=tk.CENTER)
        tree.column("displayed_zip", width=scaled(100), anchor=tk.W)
        tree.column("delivery_text", width=scaled(400), anchor=tk.W)
        tree.column("error", width=scaled(280), anchor=tk.W)

        scrollbar_y = ttk.Scrollbar(container, orient=tk.VERTICAL, command=tree.yview)
        scrollbar_x = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        tree.pack(fill=tk.BOTH, expand=True)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x.pack(fill=tk.X)

        tree.tag_configure("pass", background="#EAF8EA")
        tree.tag_configure("review_fail", background="#FFF4E5")
        tree.tag_configure("captcha", background="#FFF4E5")
        tree.tag_configure("error", background="#FDECEC")
        # Seller tags — listed last in the tags tuple so they take visual priority.
        # Amazon = green (#EAF8EA), non-Amazon = red (#FDECEC), unknown = yellow (#FFF4E5).
        tree.tag_configure("seller_amazon", background="#EAF8EA")
        tree.tag_configure("seller_other", background="#FDECEC")
        tree.tag_configure("seller_unknown", background="#FFF4E5")

        def _seller_tag(seller_value):
            if not seller_value:
                return "seller_unknown"
            if "amazon" in seller_value.lower():
                return "seller_amazon"
            return "seller_other"

        for row in results:
            if row.get("review") == "PASS":
                base_tag = "pass"
            elif row["status"] == "captcha":
                base_tag = "captcha"
            elif row["status"] == "ok":
                base_tag = "review_fail"
            else:
                base_tag = "error"

            # Seller tag is listed second so it overrides base_tag for row background.
            s_tag = _seller_tag(row.get("seller"))

            tree.insert(
                "",
                tk.END,
                values=(
                    row.get("asin", ""),
                    row.get("zip_code", ""),
                    row.get("estimated_days", ""),
                    row.get("review", ""),
                    row.get("seller") or "",
                    row.get("threshold_days", ""),
                    row.get("checked_at", ""),
                    row.get("pair_standard_hits", ""),
                    row.get("review_reason", ""),
                    row.get("status", ""),
                    "Yes" if row.get("zip_verified") else "No",
                    row.get("displayed_zip", "") or "",
                    row.get("delivery_text", "") or "",
                    row.get("error", "") or "",
                ),
                tags=(base_tag, s_tag),
            )

        details_frame = ttk.LabelFrame(container, text="Selected Row Details", padding="8")
        details_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        details_box = scrolledtext.ScrolledText(details_frame, height=8, wrap=tk.WORD)
        details_box.pack(fill=tk.BOTH, expand=True)
        details_box.insert(
            tk.END,
            "Click any result row to inspect the full delivery message and notes.",
        )
        details_box.config(state=tk.DISABLED)

        def on_select(_event):
            selection = tree.selection()
            if not selection:
                return
            values = tree.item(selection[0], "values")
            details_box.config(state=tk.NORMAL)
            details_box.delete("1.0", tk.END)
            details_box.insert(
                tk.END,
                (
                    f"ASIN: {values[0]}\n"
                    f"ZIP requested: {values[1]}\n"
                    f"Estimated days: {values[2]}\n"
                    f"Review: {values[3]} | Threshold: {values[5]} day(s)\n"
                    f"Seller: {values[4]}\n"
                    f"Checked at: {values[6]}\n"
                    f"Historical standards hits for this ASIN+ZIP: {values[7]}\n"
                    f"Review reason: {values[8]}\n"
                    f"Status: {values[9]}\n"
                    f"ZIP verified on page: {values[10]} (page showed: {values[11]})\n\n"
                    f"Delivery message:\n{values[12]}\n\n"
                    f"Error / Notes:\n{values[13]}"
                ),
            )
            details_box.config(state=tk.DISABLED)

        tree.bind("<<TreeviewSelect>>", on_select)

        if config.get("export_csv"):
            save_path = filedialog.asksaveasfilename(
                title="Save delivery speed results",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                parent=result_root,
            )
            if save_path:
                pd.DataFrame(results).to_csv(save_path, index=False)
                messagebox.showinfo(
                    "Export Complete",
                    f"Saved {len(results)} result rows to:\n{save_path}",
                    parent=result_root,
                )
            else:
                messagebox.showinfo("Export Skipped", "No file selected. CSV export skipped.", parent=result_root)

        if parent_window:
            result_root.wait_window()
        else:
            result_root.mainloop()

