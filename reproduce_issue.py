import json
import pandas as pd
from datetime import datetime
import pytz
from buybox_analyzer import BuyboxAnalyzer

# Constants
AMAZON_SELLER_ID = 'ATVPDKIKX0DER'
KEEPA_EPOCH = datetime(2011, 1, 1)

class MockBuyboxAnalyzer(BuyboxAnalyzer):
    def __init__(self):
        self.api_key = "mock"
        self.keepa_epoch = KEEPA_EPOCH

    def process_single_asin(self, asin, year, months):
        with open('debug_files/debug_raw_B00BGIVI1K_20260108_114333.json', 'r') as f:
            data = json.load(f)
            
        product = data['response_data']['products'][0]
        buybox_history = product.get('buyBoxSellerIdHistory')
        
        records = []
        for i in range(0, len(buybox_history), 2):
            minutes = int(buybox_history[i])
            seller_id = buybox_history[i+1]
            dt = self.keepa_epoch + pd.Timedelta(minutes=minutes)
            records.append({'datetime': dt, 'seller_id': seller_id})
        
        df = pd.DataFrame(records)
        
        results = []
        for month in months:
            start_of_month = datetime(year, month, 1)
            if month == 12:
                end_of_month = datetime(year + 1, 1, 1)
            else:
                end_of_month = datetime(year, month + 1, 1)
            
            month_df = df[(df['datetime'] >= start_of_month) & (df['datetime'] < end_of_month)].sort_values('datetime').reset_index(drop=True)
            
            print(f"\n--- Records for {year}-{month} ---")
            
            # Previous
            prev_records = df[df['datetime'] < start_of_month]
            if not prev_records.empty:
                last_prev = prev_records.iloc[-1]
                print(f"PREV: {last_prev['datetime']} - {last_prev['seller_id']} (Amazon? {last_prev['seller_id'] == AMAZON_SELLER_ID})")
            
            # In month
            for i, row in month_df.iterrows():
                print(f"ROW {i}: {row['datetime']} - {row['seller_id']} (Amazon? {row['seller_id'] == AMAZON_SELLER_ID})")
            
            # Next
            next_records = df[df['datetime'] >= end_of_month]
            if not next_records.empty:
                first_next = next_records.iloc[0]
                print(f"NEXT: {first_next['datetime']} - {first_next['seller_id']}")
            
            # ... (rest of calculation logic is same as before, skipping for brevity as I just want to see records)
            
            # Re-run calculation to get the number
            # (Copy-paste the logic from previous step to ensure I still get the number)
            amazon_time = 0
            total_time = 0
            
            initial_owner_id = None
            if not prev_records.empty:
                initial_owner_id = prev_records.iloc[-1]['seller_id']
            elif not month_df.empty:
                initial_owner_id = month_df.iloc[0]['seller_id']
            
            if not month_df.empty:
                first_record_time = month_df.iloc[0]['datetime']
            else:
                first_record_time = end_of_month
            
            initial_duration = (first_record_time - start_of_month).total_seconds() / 60
            total_time += initial_duration
            if initial_owner_id == AMAZON_SELLER_ID:
                amazon_time += initial_duration

            if not month_df.empty:
                for i in range(len(month_df) - 1):
                    t1 = month_df.loc[i, 'datetime']
                    t2 = month_df.loc[i + 1, 'datetime']
                    delta = (t2 - t1).total_seconds() / 60
                    total_time += delta
                    if month_df.loc[i, 'seller_id'] == AMAZON_SELLER_ID:
                        amazon_time += delta
                
                last_record_time = month_df.iloc[-1]['datetime']
                last_owner_id = month_df.iloc[-1]['seller_id']
                final_duration = (end_of_month - last_record_time).total_seconds() / 60
                total_time += final_duration
                if last_owner_id == AMAZON_SELLER_ID:
                    amazon_time += final_duration
            
            percent_time = (amazon_time / total_time) * 100 if total_time > 0 else 0
            print(f"Calculated: {percent_time}%")

        return [], None

def reproduce():
    analyzer = MockBuyboxAnalyzer()
    analyzer.process_single_asin("B00BGIVI1K", 2025, [12])

if __name__ == "__main__":
    reproduce()
