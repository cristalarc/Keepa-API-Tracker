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


def load_saved_asins():
    """
    Load saved ASINs from JSON file - returns all ASINs from all lists.
    
    Returns:
        list: All ASINs from all lists combined
    """
    try:
        if os.path.exists(ASIN_FILE):
            with open(ASIN_FILE, 'r') as f:
                data = json.load(f)
                # Support both old format (single list) and new format (named lists)
                if 'lists' in data:
                    # New format: multiple named lists
                    all_asins = []
                    for list_name, list_data in data['lists'].items():
                        all_asins.extend(list_data.get('asins', []))
                    return all_asins
                else:
                    # Old format: single list
                    return data.get('asins', [])
        return []
    except (json.JSONDecodeError, FileNotFoundError):
        return []


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
                if 'lists' in data:
                    return data['lists']
                else:
                    # Convert old format to new format
                    old_asins = data.get('asins', [])
                    return {'Default List': {'asins': old_asins, 'description': 'Migrated from old format'}}
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
        with open(ASIN_FILE, 'w') as f:
            json.dump({'lists': lists_data}, f, indent=2)
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


def add_asins_to_saved_list(new_asins, list_name="Default List"):
    """
    Add new ASINs to a specific list, avoiding duplicates.
    
    Args:
        new_asins (list): List of new ASINs to add
        list_name (str): Name of the list to add to
        
    Returns:
        tuple: (total_asins_count, new_asins_count) after adding
    """
    lists_data = load_all_asin_lists()
    
    # Create the list if it doesn't exist
    if list_name not in lists_data:
        lists_data[list_name] = {'asins': [], 'description': ''}
    
    # Get current ASINs from the specific list
    current_asins = lists_data[list_name]['asins']
    
    # Convert to uppercase and remove duplicates
    new_asins_upper = [asin.upper() for asin in new_asins]
    all_asins = list(set(current_asins + new_asins_upper))
    
    # Update the list
    lists_data[list_name]['asins'] = all_asins
    
    # Save updated lists
    if save_asin_lists(lists_data):
        return len(all_asins), len(new_asins)
    return len(current_asins), 0

