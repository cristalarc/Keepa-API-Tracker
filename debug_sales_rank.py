"""
Sales Rank Debug Script
Run this script to debug sales rank issues for a specific ASIN.
It will print detailed information about each step of the processing.

Usage:
    python debug_sales_rank.py
    
    Or modify the ASIN and days variables below to test different values.
"""

import os
from dotenv import load_dotenv
from sales_rank_module import SalesRankAnalyzer

# Load API key from .env.local
load_dotenv('.env.local')
KEEPA_API_KEY = os.getenv('Keepa_API_KEY')

if not KEEPA_API_KEY:
    print("Error: Keepa_API_KEY not found in .env.local file.")
    exit(1)

# ============================================
# CONFIGURATION - Modify these values to test
# ============================================
ASIN = "B00BGIWCV0"  # The ASIN to analyze
DAYS = 60            # Number of days to analyze
# ============================================

print("=" * 70)
print("SALES RANK DEBUG SCRIPT")
print("=" * 70)
print(f"ASIN: {ASIN}")
print(f"Days: {DAYS}")
print("=" * 70)
print()

# Create analyzer with verbose mode enabled
analyzer = SalesRankAnalyzer(KEEPA_API_KEY, verbose=True)

# Fetch and analyze
print("Step 1: Fetching product data from Keepa API...")
print("-" * 50)
product_data = analyzer.get_product_sales_rank(ASIN)

if not product_data:
    print("\nFATAL: No product data returned from API")
    exit(1)

print(f"\nProduct Title: {product_data.get('title', 'N/A')}")
print()

print("Step 2: Checking categoryTree (hierarchy)...")
print("-" * 50)
category_tree = product_data.get('categoryTree', [])
print(f"categoryTree has {len(category_tree)} levels:")
for i, cat in enumerate(category_tree):
    if isinstance(cat, dict):
        cat_id = cat.get('catId')
        cat_name = cat.get('name', 'Unknown')
    else:
        cat_id = cat
        cat_name = 'Unknown'
    marker = " <-- MOST SPECIFIC (will be selected)" if i == len(category_tree) - 1 else ""
    print(f"  {i+1}. {cat_name} (ID: {cat_id}){marker}")

# Get target category (last in tree = most specific)
target_cat_id = None
if category_tree:
    last_cat = category_tree[-1]
    target_cat_id = last_cat.get('catId') if isinstance(last_cat, dict) else last_cat
    print(f"\nTarget category ID: {target_cat_id}")
print()

print("Step 3: Checking salesRanks field structure...")
print("-" * 50)
sales_ranks = product_data.get('salesRanks', {})
print(f"salesRanks type: {type(sales_ranks)}")
print(f"salesRanks is empty: {not sales_ranks}")

if sales_ranks:
    print(f"Number of categories in salesRanks: {len(sales_ranks)}")
    for cat_id, data in sales_ranks.items():
        is_target = str(cat_id) == str(target_cat_id) if target_cat_id else False
        marker = " <-- TARGET CATEGORY" if is_target else ""
        print(f"  Category {cat_id}{marker}:")
        print(f"    Type: {type(data)}")
        if isinstance(data, list):
            print(f"    Length: {len(data)}")
            valid_ranks = [r for r in data[1::2] if r != -1]
            print(f"    Valid ranks (non -1): {len(valid_ranks)}")
            if len(data) >= 4:
                print(f"    First 2 entries (raw): {data[:4]}")
                print(f"    Last 2 entries (raw): {data[-4:]}")
        else:
            print(f"    Value: {data}")
    
    # Check if target is in salesRanks
    if target_cat_id:
        found = any(str(k) == str(target_cat_id) for k in sales_ranks.keys())
        print(f"\nTarget category {target_cat_id} found in salesRanks: {found}")
print()

print("Step 4: Parsing sales rank history...")
print("-" * 50)
df = analyzer.parse_sales_rank_history(product_data)
print(f"\nResulting DataFrame shape: {df.shape}")
print(f"DataFrame is empty: {df.empty}")

if not df.empty:
    print(f"\nDataFrame columns: {list(df.columns)}")
    print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    print(f"\nFirst 5 rows:")
    print(df.head().to_string())
    print(f"\nLast 5 rows:")
    print(df.tail().to_string())
print()

print("Step 5: Calculating statistics...")
print("-" * 50)
stats = analyzer.calculate_sales_rank_stats(df, DAYS)
print(f"\nStats result: {stats}")
print()

print("=" * 70)
print("SUMMARY")
print("=" * 70)
if stats['data_points'] == 0:
    print("❌ NO DATA AVAILABLE for the specified period")
    if not df.empty:
        print(f"\n   Data exists ({len(df)} records total)")
        print(f"   Data range: {df['datetime'].min()} to {df['datetime'].max()}")
        print(f"   Requested period: last {DAYS} days")
        print(f"\n   💡 SOLUTION: The data is older than {DAYS} days.")
        print(f"      Try increasing the 'Days to analyze' value.")
else:
    print(f"✅ SUCCESS: Found {stats['data_points']} data points")
    print(f"   Average Rank: {stats['average_rank']:.0f}")
    print(f"   Best Rank: {stats['min_rank']}")
    print(f"   Worst Rank: {stats['max_rank']}")
print("=" * 70)

