"""
ZIP List Management Module
Handles validation and persistent storage for reusable ZIP code lists.
"""

import json
import os
import re


ZIP_LIST_FILE = "saved_zip_lists.json"


def validate_zip_code(zip_code):
    """
    Validate a US ZIP code format.

    Args:
        zip_code (str): ZIP input value

    Returns:
        bool: True when valid
    """
    if not isinstance(zip_code, str):
        return False
    return bool(re.match(r"^\d{5}(?:-\d{4})?$", zip_code.strip()))


def parse_zip_list(zip_text):
    """
    Parse ZIPs from comma/space/newline separated text.

    Args:
        zip_text (str): Raw ZIP text

    Returns:
        tuple: (valid_zips, invalid_tokens)
    """
    if not isinstance(zip_text, str):
        return [], []

    candidates = re.split(r"[,\n\s]+", zip_text.strip())
    valid = []
    invalid = []
    seen = set()

    for token in candidates:
        token = token.strip()
        if not token:
            continue
        if validate_zip_code(token):
            normalized = token[:5]
            if normalized not in seen:
                seen.add(normalized)
                valid.append(normalized)
        else:
            invalid.append(token)

    return valid, invalid


def _normalize_zip_lists_data(raw_lists):
    """
    Normalize list payload into a stable storage schema.

    Args:
        raw_lists (dict): Raw zip list dictionary

    Returns:
        tuple: (normalized_lists, changed)
    """
    changed = False
    normalized = {}

    if not isinstance(raw_lists, dict):
        return {}, True

    for raw_name, raw_data in raw_lists.items():
        if not isinstance(raw_name, str):
            changed = True
            continue

        list_name = raw_name.strip()
        if not list_name:
            changed = True
            continue

        if not isinstance(raw_data, dict):
            raw_data = {}
            changed = True

        raw_zips = raw_data.get("zips", [])
        if not isinstance(raw_zips, list):
            raw_zips = []
            changed = True

        zips = []
        seen = set()
        for zip_code in raw_zips:
            if not isinstance(zip_code, str):
                changed = True
                continue
            normalized_zip = zip_code.strip()[:5]
            if not validate_zip_code(normalized_zip):
                changed = True
                continue
            if normalized_zip in seen:
                changed = True
                continue
            seen.add(normalized_zip)
            zips.append(normalized_zip)

        description = raw_data.get("description", "")
        if not isinstance(description, str):
            description = str(description)
            changed = True

        normalized[list_name] = {"zips": zips, "description": description}

        if list_name != raw_name:
            changed = True
        if zips != raw_zips:
            changed = True

    if len(normalized) != len(raw_lists):
        changed = True

    return normalized, changed


def load_all_zip_lists():
    """
    Load all saved ZIP lists.

    Returns:
        dict: {list_name: {"zips": [...], "description": "..."}}
    """
    try:
        if not os.path.exists(ZIP_LIST_FILE):
            return {}

        with open(ZIP_LIST_FILE, "r") as handle:
            data = json.load(handle)

        if isinstance(data, dict) and "lists" in data:
            raw_lists = data.get("lists", {})
        else:
            legacy_zips = data.get("zips", []) if isinstance(data, dict) else []
            raw_lists = {
                "Default ZIP List": {
                    "zips": legacy_zips,
                    "description": "Migrated from legacy ZIP format",
                }
            }

        normalized_lists, changed = _normalize_zip_lists_data(raw_lists)
        if changed:
            save_zip_lists(normalized_lists)
        return normalized_lists
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_zip_lists(zip_lists_data):
    """
    Save ZIP lists in normalized format.

    Args:
        zip_lists_data (dict): ZIP list payload

    Returns:
        bool: True when successful
    """
    try:
        normalized_lists, _ = _normalize_zip_lists_data(zip_lists_data)
        with open(ZIP_LIST_FILE, "w") as handle:
            json.dump({"lists": normalized_lists}, handle, indent=2)
        return True
    except Exception as exc:
        print(f"Error saving ZIP lists: {exc}")
        return False


def save_zip_list(list_name, zips, description=""):
    """
    Save or update a named ZIP list.

    Args:
        list_name (str): List name
        zips (list): ZIP values
        description (str): Optional description

    Returns:
        tuple: (saved, error_message)
    """
    if not isinstance(list_name, str) or not list_name.strip():
        return False, "List name is required."

    if not isinstance(zips, list) or not zips:
        return False, "At least one ZIP code is required."

    cleaned_zips = []
    seen = set()
    for zip_code in zips:
        if not isinstance(zip_code, str):
            continue
        normalized = zip_code.strip()[:5]
        if not validate_zip_code(normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned_zips.append(normalized)

    if not cleaned_zips:
        return False, "No valid ZIP codes to save."

    all_lists = load_all_zip_lists()
    all_lists[list_name.strip()] = {
        "zips": cleaned_zips,
        "description": description if isinstance(description, str) else str(description),
    }
    if save_zip_lists(all_lists):
        return True, None
    return False, "Failed to save ZIP list."

