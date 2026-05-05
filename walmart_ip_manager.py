"""
Walmart IP Management Module
Manages named lists of Walmart IP numbers for price tracking.
Mirrors the asin_manager.py pattern.
"""

import os
import json
import re


WALMART_IP_FILE = "walmart_ips.json"


def _normalize_single_list_data(list_data):
    changed = False

    if not isinstance(list_data, dict):
        list_data = {}
        changed = True

    raw_ips = list_data.get("ips", [])
    if not isinstance(raw_ips, list):
        raw_ips = []
        changed = True

    normalized_ips = []
    seen_ips = set()
    for ip in raw_ips:
        if not isinstance(ip, str):
            changed = True
            continue
        ip_clean = ip.strip()
        if not ip_clean:
            changed = True
            continue
        if ip_clean in seen_ips:
            changed = True
            continue
        seen_ips.add(ip_clean)
        normalized_ips.append(ip_clean)

    if normalized_ips != raw_ips:
        changed = True

    description = list_data.get("description", "")
    if not isinstance(description, str):
        description = str(description)
        changed = True

    normalized = {"ips": normalized_ips, "description": description}
    return normalized, changed


def _normalize_lists_data(lists_data):
    changed = False
    normalized = {}

    if not isinstance(lists_data, dict):
        return {}, True

    for list_name, list_data in lists_data.items():
        if not isinstance(list_name, str):
            changed = True
            continue
        clean_name = list_name.strip()
        if not clean_name:
            changed = True
            continue
        norm_list, list_changed = _normalize_single_list_data(list_data)
        normalized[clean_name] = norm_list
        if list_changed or clean_name != list_name:
            changed = True

    if len(normalized) != len(lists_data):
        changed = True

    return normalized, changed


def load_all_ip_lists():
    """
    Load all Walmart IP lists from JSON file.

    Returns:
        dict: Mapping of list names to their data (ips, description)
    """
    try:
        if os.path.exists(WALMART_IP_FILE):
            with open(WALMART_IP_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, dict) and "lists" in data:
                raw_lists = data.get("lists", {})
            else:
                raw_lists = {}

            normalized, changed = _normalize_lists_data(raw_lists)
            if changed:
                save_ip_lists(normalized)
            return normalized
        return {}
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_ip_lists(lists_data):
    """
    Save Walmart IP lists to JSON file.

    Args:
        lists_data (dict): Mapping of list names to their data

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        normalized, _ = _normalize_lists_data(lists_data)
        with open(WALMART_IP_FILE, "w") as f:
            json.dump({"lists": normalized}, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving Walmart IP lists: {e}")
        return False


def validate_ip_number(ip_number):
    """
    Validate a Walmart IP number — must be a non-empty digit-only string.

    Args:
        ip_number (str): The IP number string to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(ip_number, str):
        return False
    ip_clean = ip_number.strip()
    return bool(ip_clean) and bool(re.match(r"^\d+$", ip_clean))


def validate_ip_list(ip_text):
    """
    Validate and parse a list of Walmart IP numbers from text input.

    Args:
        ip_text (str): Text containing IP numbers (comma, space, or newline separated)

    Returns:
        tuple: (valid_ips, error_msg) where error_msg is None if all valid
    """
    if not ip_text.strip():
        return [], "No IP numbers provided"

    candidates = re.split(r"[,\n\s]+", ip_text.strip())
    valid_ips = []
    invalid_ips = []

    for candidate in candidates:
        candidate = candidate.strip()
        if candidate:
            if validate_ip_number(candidate):
                valid_ips.append(candidate)
            else:
                invalid_ips.append(candidate)

    if invalid_ips:
        error_msg = f"Invalid IP numbers (must be digits only): {', '.join(invalid_ips[:5])}"
        if len(invalid_ips) > 5:
            error_msg += f" and {len(invalid_ips) - 5} more"
        return valid_ips, error_msg

    return valid_ips, None


def add_ips_to_list(new_ips, list_name="Default List"):
    """
    Add Walmart IP numbers to a named list, avoiding duplicates.

    Args:
        new_ips (list): List of IP number strings to add
        list_name (str): Name of the list to add to

    Returns:
        tuple: (total_count, added_count) after adding
    """
    lists_data = load_all_ip_lists()

    if list_name not in lists_data:
        lists_data[list_name] = {"ips": [], "description": ""}

    current_ips = list(lists_data[list_name].get("ips", []))
    original_count = len(current_ips)
    seen = set(current_ips)

    added_count = 0
    for ip in new_ips:
        ip_clean = ip.strip()
        if ip_clean and ip_clean not in seen:
            current_ips.append(ip_clean)
            seen.add(ip_clean)
            added_count += 1

    lists_data[list_name]["ips"] = current_ips

    if save_ip_lists(lists_data):
        return len(current_ips), added_count
    return original_count, 0
