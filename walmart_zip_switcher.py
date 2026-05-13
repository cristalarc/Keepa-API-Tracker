"""
Walmart ZIP Switcher Module
Encapsulates the in-page flow to change Walmart's delivery ZIP via the
"Update your location" side sheet. The class follows the Single Responsibility
Principle: it only changes the location for an already-open SeleniumBase
session. Scraping (price/seller extraction) stays in WalmartScraper.

Walmart's frontend markup changes frequently, so this module:
- Tries many CSS/XPath selectors per UI element.
- Falls back to a JavaScript "find by visible text" probe when selectors miss.
- Returns rich error messages so the caller can surface WHY a switch failed.
"""

import re
import time


class WalmartZipSwitcher:
    """Switches the Walmart delivery ZIP via the in-page location side sheet."""

    # ------------------------------------------------------------------
    # Element selectors. Tried in order. Mixing CSS and XPath is OK -
    # SeleniumBase auto-detects XPath when the selector starts with "//".
    #
    # IMPORTANT: We deliberately AVOID the top-header "Pickup or delivery?"
    # button. Clicking that opens Walmart's full address-book flow which
    # requires a complete street address. The user-friendly flow is the
    # in-PDP "Ships to <city>, <ZIP>" link in the buy-box, which opens a
    # small side panel that only asks for a 5-digit ZIP. Every selector
    # below targets THAT element, never the header pill.
    # ------------------------------------------------------------------
    LOCATION_PILL_SELECTORS = (
        # GOLD - confirmed via DOM inspection: Walmart tags the "Ships to"
        # link button with a stable semantic SEO id. This should always
        # match on a Walmart PDP and is the safest selector.
        "button[data-seo-id='fulfillment-link']",
        "[data-seo-id='fulfillment-link']",
        # ARIA labels Walmart attaches to the "Ships to" link.
        # The real aria-label looks like:
        #   "Altadena, 91001, Change shipping address"
        # so a substring match on "Change shipping address" works.
        "button[aria-label*='Change shipping address']",
        "a[aria-label*='Change shipping address']",
        "button[aria-label*='shipping address']",
        "a[aria-label*='shipping address']",
        "button[aria-label*='Update your location']",
        "a[aria-label*='Update your location']",
        # Older / alternate test-id attributes seen across past Walmart
        # revisions. Kept as additional fallbacks.
        "[data-testid='fulfillment-shipping-text']",
        "[data-automation-id='fulfillment-shipping-text']",
        "[data-testid='fulfillment-shipping-address']",
        "[data-automation-id='address-search-link']",
        "a[link-identifier='fulfillment-shipping']",
        # XPath - find a clickable INSIDE a small container whose text
        # starts with "Ships to". `normalize-space(string())` flattens any
        # nested whitespace so this matches "Ships to Altadena, 91001".
        "//div[starts-with(normalize-space(string()), 'Ships to')]//a",
        "//div[starts-with(normalize-space(string()), 'Ships to')]//button",
        "//div[starts-with(normalize-space(string()), 'Ships to')]"
        "//*[@role='button']",
        # Alternate: explicit "Ships to" label sibling.
        "//span[normalize-space()='Ships to']/following-sibling::a[1]",
        "//span[normalize-space()='Ships to']/following-sibling::button[1]",
    )

    # The side sheet container itself. Used to scope sub-element lookups
    # so we don't accidentally hit a hidden duplicate elsewhere in the DOM.
    SIDEBAR_CONTAINER_SELECTORS = (
        "[data-testid='fulfillment-flyout']",
        "[data-testid='location-sidebar']",
        "div[role='dialog']",
        "aside[role='dialog']",
        "[aria-label*='location' i]",
    )

    # ZIP input field inside the side sheet.
    ZIP_INPUT_SELECTORS = (
        "input#location-zip-code",
        "input[name='zipCode']",
        "input[aria-label*='Zip code']",
        "input[aria-label*='ZIP code']",
        "input[placeholder*='Zip']",
        "input[autocomplete='postal-code']",
        "input[data-automation-id='zip-input']",
    )

    # Save button inside the side sheet.
    SAVE_BUTTON_SELECTORS = (
        "[data-testid='location-confirm']",
        "[data-automation-id='location-save-button']",
        "button[type='submit']",
        "button[aria-label*='Save']",
        "//button[normalize-space()='Save']",
        "//button[contains(., 'Save')]",
    )

    # Timeouts (seconds). Walmart can be slow when the side sheet loads
    # for the first time, and the post-Save page reload is even slower.
    SIDEBAR_TIMEOUT_SECONDS = 20
    VERIFY_TIMEOUT_SECONDS = 25

    # ==================================================================
    # Public API
    # ==================================================================

    def current_zip(self, sb):
        """
        Read the ZIP currently shown on the page (location pill text).

        Returns:
            str | None: 5-digit ZIP if detected, else None.
        """
        for selector in self.LOCATION_PILL_SELECTORS:
            try:
                if sb.is_element_present(selector):
                    text = sb.get_text(selector) or ""
                    match = re.search(r"\b(\d{5})\b", text)
                    if match:
                        return match.group(1)
            except Exception:
                continue

        # Last-resort: scan the visible body text for "Ships to ... 12345".
        try:
            body_text = sb.get_text("body") or ""
        except Exception:
            body_text = ""
        match = re.search(r"Ships to[^,]*,\s*(\d{5})", body_text)
        if match:
            return match.group(1)
        return None

    def set_zip(self, sb, zip_code):
        """
        Switch Walmart delivery location to `zip_code`.

        Returns:
            tuple: (success: bool, error_message: str | None)
        """
        zip_normalized = str(zip_code).strip()[:5]
        if not re.match(r"^\d{5}$", zip_normalized):
            return False, f"Invalid ZIP format: '{zip_code}'."

        # Step 0 - already at the requested ZIP? Skip the whole UI flow.
        current = self.current_zip(sb)
        if current == zip_normalized:
            return True, None

        # Step 1 - open the side sheet by clicking the location pill.
        click_ok, click_err = self._open_location_sidebar(sb)
        if not click_ok:
            return False, f"Pill: {click_err}"

        # Step 2 - wait for the sidebar to actually render (input visible).
        zip_selector = self._wait_for_first_present(
            sb, self.ZIP_INPUT_SELECTORS, self.SIDEBAR_TIMEOUT_SECONDS
        )
        if zip_selector is None:
            return False, (
                "ZIP input did not appear in the side sheet "
                f"(waited {self.SIDEBAR_TIMEOUT_SECONDS}s)."
            )

        # Step 3 - clear any existing value and type the new ZIP.
        type_ok, type_err = self._fill_zip_input(sb, zip_selector, zip_normalized)
        if not type_ok:
            return False, f"Input: {type_err}"

        # Step 4 - click Save (or press Enter as a last resort).
        save_ok, save_err = self._click_save(sb)
        if not save_ok:
            return False, f"Save: {save_err}"

        # Step 5 - verify by polling the pill text until it shows the new ZIP.
        deadline = time.time() + self.VERIFY_TIMEOUT_SECONDS
        last_seen = current
        while time.time() < deadline:
            now = self.current_zip(sb)
            if now == zip_normalized:
                return True, None
            if now is not None:
                last_seen = now
            time.sleep(0.5)

        return False, (
            f"ZIP did not update after Save (expected {zip_normalized}, "
            f"page still shows '{last_seen}' after {self.VERIFY_TIMEOUT_SECONDS}s)."
        )

    # ==================================================================
    # Step-level helpers
    # ==================================================================

    def _open_location_sidebar(self, sb):
        """
        Click the in-PDP "Ships to <city>, <zip>" link so the small ZIP side
        panel opens.

        Returns:
            tuple: (success: bool, error_message: str | None)
        """
        # First pass - the curated CSS / XPath selectors above.
        selector = self._first_present(sb, self.LOCATION_PILL_SELECTORS)
        if selector is not None:
            return self._scroll_and_click(sb, selector)

        # Second pass - JavaScript probe: walk up to 4 ancestors looking for
        # a container whose visible text starts with "Ships to". This catches
        # Walmart redesigns where the test-id/aria-label has shifted but the
        # visible "Ships to <city>, <zip>" structure is intact. Crucially it
        # never matches the header "Pickup or delivery?" pill, which would
        # otherwise open the wrong (full-address-book) flow.
        clicked_via_js = self._click_ships_to_link(sb)
        if clicked_via_js:
            return True, None

        return False, (
            "Could not find the in-PDP 'Ships to' link. Tried "
            f"{len(self.LOCATION_PILL_SELECTORS)} selectors and a "
            "text-content fallback. Make sure the browser is on a PDP "
            "where the buy-box shows 'Ships to <city>, <zip>'."
        )

    def _click_ships_to_link(self, sb):
        """
        Find and click the underlined city/ZIP link inside a 'Ships to ...'
        container, using JavaScript. Returns True when a click is dispatched.
        """
        js = """
        const candidates = document.querySelectorAll(
            'a, button, [role="button"]'
        );
        for (const el of candidates) {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            // Inspect up to 4 ancestor levels for a container that BEGINS
            // with "Ships to" (case-insensitive). Cap the container text
            // length so we never match large panels that just happen to
            // contain those words elsewhere.
            let ancestor = el.parentElement;
            for (let depth = 0; depth < 4 && ancestor; depth++) {
                const text = (ancestor.textContent || '').trim();
                if (/^Ships to\\b/i.test(text) && text.length < 100) {
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
                ancestor = ancestor.parentElement;
            }
        }
        return false;
        """
        try:
            return bool(sb.execute_script(js))
        except Exception:
            return False

    def _fill_zip_input(self, sb, zip_selector, zip_normalized):
        """Clear and type the ZIP into the side sheet input."""
        # Try the SeleniumBase clear first; some inputs reject it, so fall
        # back to a JS clear that also fires an 'input' event.
        try:
            sb.clear(zip_selector)
        except Exception:
            try:
                sb.execute_script(
                    "var el=document.querySelector(arguments[0]);"
                    "if(el){el.value='';"
                    "el.dispatchEvent(new Event('input',{bubbles:true}));}",
                    zip_selector,
                )
            except Exception:
                pass

        try:
            sb.type(zip_selector, zip_normalized)
        except Exception as exc:
            # Some Walmart variants use a React-controlled input that ignores
            # .value=...; sb.type() typically handles that, but if it fails
            # we still try a JS-driven dispatch as a last resort.
            try:
                sb.execute_script(
                    "var el=document.querySelector(arguments[0]);"
                    "if(el){var setter=Object.getOwnPropertyDescriptor("
                    "window.HTMLInputElement.prototype,'value').set;"
                    "setter.call(el, arguments[1]);"
                    "el.dispatchEvent(new Event('input',{bubbles:true}));}",
                    zip_selector, zip_normalized,
                )
            except Exception as inner_exc:
                return False, f"Could not type ZIP: {exc} / fallback: {inner_exc}"
        return True, None

    def _click_save(self, sb):
        """Click the Save button in the side sheet, or press Enter."""
        save_selector = self._first_present(sb, self.SAVE_BUTTON_SELECTORS)
        if save_selector is not None:
            ok, err = self._scroll_and_click(sb, save_selector)
            if ok:
                return True, None
            # If click failed, fall through to the Enter-key fallback.

        # Enter-key fallback: many Walmart side sheets submit when Enter
        # is pressed in the ZIP input.
        try:
            from selenium.webdriver.common.keys import Keys
            zip_selector = self._first_present(sb, self.ZIP_INPUT_SELECTORS)
            if zip_selector is not None:
                sb.send_keys(zip_selector, Keys.ENTER)
                return True, None
        except Exception as exc:
            return False, f"Save button missing and Enter-key fallback failed: {exc}"
        return False, "Save button not found in the side sheet."

    # ==================================================================
    # Low-level helpers
    # ==================================================================

    def _first_present(self, sb, selectors):
        """Return the first selector in `selectors` that exists on the page."""
        for selector in selectors:
            try:
                if sb.is_element_present(selector):
                    return selector
            except Exception:
                continue
        return None

    def _wait_for_first_present(self, sb, selectors, timeout_seconds):
        """Poll until any selector becomes present or timeout."""
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            selector = self._first_present(sb, selectors)
            if selector is not None:
                return selector
            time.sleep(0.3)
        return None

    def _scroll_and_click(self, sb, selector):
        """
        Scroll the element into view and click it (with a JS-click fallback).

        Returns:
            tuple: (success: bool, error_message: str | None)
        """
        try:
            sb.scroll_to(selector)
        except Exception:
            # Non-fatal: many elements are clickable without scrolling.
            pass
        try:
            sb.click(selector)
            return True, None
        except Exception as click_exc:
            try:
                sb.js_click(selector)
                return True, None
            except Exception as js_exc:
                return False, (
                    f"selector '{selector}' present but not clickable "
                    f"(click: {click_exc}; js_click: {js_exc})"
                )

