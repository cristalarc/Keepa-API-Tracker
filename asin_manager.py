"""
ASIN Management Module
This module provides shared functionality for managing ASIN lists across the application.
It follows the Single Responsibility Principle by focusing solely on ASIN data management.
"""

import os
import json
import re


# ASIN file path constant
ASIN_FILE = 'saved_asins.json'
UNKNOWN_PRODUCT_TYPE = "Unknown"


def _normalize_product_type(product_type):
    """
    Normalize product type text to a consistent stored value.

    Args:
        product_type (str | None): Product type text

    Returns:
        str: Normalized product type
    """
    if not isinstance(product_type, str) or not product_type.strip():
        return UNKNOWN_PRODUCT_TYPE
    return product_type.strip()


def _normalize_single_list_data(list_data):
    """
    Normalize one list payload and ensure required fields exist.

    Args:
        list_data (dict): Raw list data

    Returns:
        tuple: (normalized_list_data, changed)
    """
    changed = False

    if not isinstance(list_data, dict):
        list_data = {}
        changed = True

    raw_asins = list_data.get('asins', [])
    if not isinstance(raw_asins, list):
        raw_asins = []
        changed = True

    normalized_asins = []
    seen_asins = set()
    for asin in raw_asins:
        if not isinstance(asin, str):
            changed = True
            continue
        asin_upper = asin.strip().upper()
        if not asin_upper:
            changed = True
            continue
        if asin_upper in seen_asins:
            changed = True
            continue
        seen_asins.add(asin_upper)
        normalized_asins.append(asin_upper)

    if normalized_asins != raw_asins:
        changed = True

    description = list_data.get('description', '')
    if not isinstance(description, str):
        description = str(description)
        changed = True

    raw_product_types = list_data.get('product_types', {})
    if not isinstance(raw_product_types, dict):
        raw_product_types = {}
        changed = True

    normalized_product_types = {}
    for asin in normalized_asins:
        matched_type = None

        # Prefer exact key first, then any key that normalizes to the same ASIN.
        if asin in raw_product_types:
            matched_type = raw_product_types[asin]
        else:
            for key, value in raw_product_types.items():
                if isinstance(key, str) and key.strip().upper() == asin:
                    matched_type = value
                    changed = True
                    break

        normalized_type = _normalize_product_type(matched_type)
        normalized_product_types[asin] = normalized_type

        if matched_type != normalized_type:
            changed = True
        elif asin not in raw_product_types:
            changed = True

    # If product type map contains stale keys, this cleanup is a migration change.
    for key in raw_product_types.keys():
        if not isinstance(key, str) or key.strip().upper() not in seen_asins:
            changed = True
            break

    normalized_list_data = {
        'asins': normalized_asins,
        'description': description,
        'product_types': normalized_product_types
    }
    return normalized_list_data, changed


def _normalize_lists_data(lists_data):
    """
    Normalize all list payloads and ensure stable storage format.

    Args:
        lists_data (dict): Raw lists payload

    Returns:
        tuple: (normalized_lists_data, changed)
    """
    changed = False
    normalized_lists = {}

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

        normalized_list, list_changed = _normalize_single_list_data(list_data)
        normalized_lists[clean_name] = normalized_list
        if list_changed or clean_name != list_name:
            changed = True

    if len(normalized_lists) != len(lists_data):
        changed = True

    return normalized_lists, changed


def load_saved_asins():
    """
    Load saved ASINs from JSON file - returns all ASINs from all lists.
    
    Returns:
        list: All ASINs from all lists combined
    """
    lists_data = load_all_asin_lists()
    all_asins = []
    seen_asins = set()

    for list_data in lists_data.values():
        for asin in list_data.get('asins', []):
            if asin not in seen_asins:
                seen_asins.add(asin)
                all_asins.append(asin)

    return all_asins


def load_all_asin_lists():
    """
    Load all ASIN lists with their names.
    
    Returns:
        dict: Dictionary of list names to their data (asins, description)
    """
    try:
        if os.path.exists(ASIN_FILE):
            with open(ASIN_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'lists' in data:
                    raw_lists = data.get('lists', {})
                else:
                    # Convert old format to new format
                    old_asins = data.get('asins', []) if isinstance(data, dict) else []
                    raw_lists = {
                        'Default List': {
                            'asins': old_asins,
                            'description': 'Migrated from old format'
                        }
                    }

                normalized_lists, changed = _normalize_lists_data(raw_lists)

                # Auto-upgrade legacy storage when we detect old/incomplete format.
                if changed:
                    save_asin_lists(normalized_lists)

                return normalized_lists
        return {}
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_asin_lists(lists_data):
    """
    Save ASIN lists to JSON file.
    
    Args:
        lists_data (dict): Dictionary of list names to their data
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        normalized_lists, _ = _normalize_lists_data(lists_data)
        with open(ASIN_FILE, 'w') as f:
            json.dump({'lists': normalized_lists}, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving ASIN lists: {e}")
        return False


def save_asins_to_file(asins):
    """
    Save ASINs to JSON file - legacy function for backward compatibility.
    
    Args:
        asins (list): List of ASINs to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        with open(ASIN_FILE, 'w') as f:
            json.dump({'asins': asins}, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving ASINs: {e}")
        return False


def validate_asin(asin):
    """
    Validate if a string is a valid ASIN format.
    
    Args:
        asin (str): The ASIN string to validate
        
    Returns:
        bool: True if valid ASIN format, False otherwise
    """
    if not asin:
        return False
    # ASINs are 10 characters long and contain only letters and numbers
    asin = asin.strip().upper()
    return len(asin) == 10 and re.match(r'^[A-Z0-9]{10}$', asin)


def validate_asin_list(asin_text):
    """
    Validate and parse a list of ASINs from text input.
    
    Args:
        asin_text (str): Text containing ASINs (comma, space, or newline separated)
        
    Returns:
        tuple: (valid_asins, error_msg) where error_msg is None if all valid
    """
    if not asin_text.strip():
        return [], "No ASINs provided"
    
    # Split by common delimiters (comma, newline, space)
    asin_candidates = re.split(r'[,\n\s]+', asin_text.strip())
    
    valid_asins = []
    invalid_asins = []
    
    for candidate in asin_candidates:
        candidate = candidate.strip()
        if candidate:  # Skip empty strings
            if validate_asin(candidate):
                valid_asins.append(candidate.upper())
            else:
                invalid_asins.append(candidate)
    
    if invalid_asins:
        error_msg = f"Invalid ASINs found: {', '.join(invalid_asins[:5])}"
        if len(invalid_asins) > 5:
            error_msg += f" and {len(invalid_asins) - 5} more"
        return valid_asins, error_msg
    
    return valid_asins, None


def add_asins_to_saved_list(new_asins, list_name="Default List", product_type=None):
    """
    Add new ASINs to a specific list, avoiding duplicates.
    
    Args:
        new_asins (list): List of new ASINs to add
        list_name (str): Name of the list to add to
        product_type (str | dict | None): Product type to assign for new ASINs.
            Can be a single string for all ASINs or a dict of {asin: product_type}.
        
    Returns:
        tuple: (total_asins_count, new_asins_count) after adding
    """
    lists_data = load_all_asin_lists()
    
    # Create the list if it doesn't exist
    if list_name not in lists_data:
        lists_data[list_name] = {'asins': [], 'description': '', 'product_types': {}}
    
    # Get current ASINs from the specific list
    current_asins = lists_data[list_name]['asins']
    product_types = lists_data[list_name].get('product_types', {})

    # Build a per-ASIN product type map from the provided value.
    provided_type_by_asin = {}
    if isinstance(product_type, dict):
        for asin_key, asin_type in product_type.items():
            if isinstance(asin_key, str):
                provided_type_by_asin[asin_key.strip().upper()] = _normalize_product_type(asin_type)
    elif product_type is not None:
        common_product_type = _normalize_product_type(product_type)
        for asin in new_asins:
            provided_type_by_asin[asin.strip().upper()] = common_product_type
    
    # Convert to uppercase and remove duplicates while preserving order.
    added_count = 0
    for asin in new_asins:
        asin_upper = asin.strip().upper()
        if asin_upper and asin_upper not in current_asins:
            current_asins.append(asin_upper)
            added_count += 1

        if asin_upper:
            product_types[asin_upper] = provided_type_by_asin.get(
                asin_upper,
                product_types.get(asin_upper, UNKNOWN_PRODUCT_TYPE)
            )
    
    # Update the list
    lists_data[list_name]['asins'] = current_asins
    lists_data[list_name]['product_types'] = product_types
    
    # Save updated lists
    if save_asin_lists(lists_data):
        return len(current_asins), added_count
    return len(current_asins), 0


def update_asin_product_types(product_type_by_asin, list_name=None):
    """
    Update product types for one or more ASINs in saved lists.

    Args:
        product_type_by_asin (dict): Mapping of ASIN to product type text
        list_name (str | None): Optional specific list name. If None, update all lists.

    Returns:
        int: Number of ASIN entries updated across all targeted lists
    """
    if not isinstance(product_type_by_asin, dict) or not product_type_by_asin:
        return 0

    lists_data = load_all_asin_lists()
    if not lists_data:
        return 0

    normalized_updates = {}
    for asin, asin_type in product_type_by_asin.items():
        if not isinstance(asin, str):
            continue
        asin_upper = asin.strip().upper()
        if asin_upper:
            normalized_updates[asin_upper] = _normalize_product_type(asin_type)

    if not normalized_updates:
        return 0

    list_names = [list_name] if list_name else list(lists_data.keys())
    update_count = 0

    for target_list_name in list_names:
        if target_list_name not in lists_data:
            continue

        list_data = lists_data[target_list_name]
        list_asins = set(list_data.get('asins', []))
        product_types = list_data.get('product_types', {})

        for asin, asin_type in normalized_updates.items():
            if asin in list_asins:
                if product_types.get(asin) != asin_type:
                    product_types[asin] = asin_type
                    update_count += 1

        list_data['product_types'] = product_types

    if update_count > 0:
        save_asin_lists(lists_data)

    return update_count

