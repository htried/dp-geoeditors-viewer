#!/usr/bin/env python3
import requests
from datetime import datetime
from pathlib import Path
import logging
import sys
import pandas as pd
from io import StringIO
from utils import *

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('update.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

def add_unpublished_rows(df, month, use_legacy=True):
    """Add rows for unpublished countries to the DataFrame"""
    unpublished = LEGACY_UNPUBLISHED if use_legacy else CURRENT_UNPUBLISHED
    new_rows = []
    
    # Get unique projects and activity levels from existing data
    projects = df['project'].unique()
    activity_levels = df['activity_level'].unique()
    
    # Create rows for each unpublished country
    for country, code in unpublished.items():
        for project in projects:
            for activity_level in activity_levels:
                new_rows.append({
                    'wiki_db': project.split('.')[0],
                    'project': project,
                    'country': country,
                    'country_code': code,
                    'activity_level': activity_level,
                    'count_eps': 0,
                    'sum_eps': 0,
                    'count_release_thresh': 0,
                    'editors': -1,  # Use -1 to indicate unpublished
                    'edits': 0,
                    'month': month
                })
    
    # Add new rows to DataFrame
    if new_rows:
        unpublished_df = pd.DataFrame(new_rows)
        return pd.concat([df, unpublished_df], ignore_index=True)
    return df

def download_monthly_data(year_month):
    """Download and save monthly data file"""
    url = f"https://analytics.wikimedia.org/published/datasets/geoeditors_monthly/{year_month}.tsv"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            # Read the TSV data into a DataFrame
            df = pd.read_csv(StringIO(response.text), sep='\t', names=COLUMN_NAMES)
            
            # Add unpublished countries based on date
            cutoff_date = datetime.strptime('2024-01', '%Y-%m')
            current_date = datetime.strptime(year_month, '%Y-%m')
            df = add_unpublished_rows(df, year_month, use_legacy=(current_date < cutoff_date))
            
            # Save the modified DataFrame
            file_path = DATA_DIR / f"{year_month}.tsv"
            df.to_csv(file_path, sep='\t', index=False, header=False)
            logging.info(f"Successfully downloaded and processed data for {year_month}")
            return True
        else:
            logging.error(f"Failed to download data for {year_month}. Status code: {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"Error downloading data for {year_month}: {str(e)}")
        return False

def get_available_months():
    """Get list of available months from 2023-07 to current month"""
    start_date = datetime(2023, 7, 1)
    current_date = datetime.now()
    months = []
    
    while start_date <= current_date:
        months.append(start_date.strftime("%Y-%m"))
        if start_date.month == 12:
            start_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            start_date = start_date.replace(month=start_date.month + 1)
    
    return months

def main():
    logging.info("Starting data update process")
    months = get_available_months()
    
    for month in months:
        file_path = DATA_DIR / f"{month}.tsv"
        if not file_path.exists():
            download_monthly_data(month)
    
    logging.info("Data update process completed")

if __name__ == "__main__":
    main() 