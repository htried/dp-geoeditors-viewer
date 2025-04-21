#!/usr/bin/env python3
import requests
from datetime import datetime
import logging
import sys
import pandas as pd
from io import StringIO
from utils import *
from models import SessionLocal, EditorData
from sqlalchemy import and_
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('update.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

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
    """Download and save monthly data file to PostgreSQL"""
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    # Define data types for each column
    dtype = {
        'wiki_db': str,
        'project': str,
        'country': str,
        'country_code': str,
        'activity_level': str,
        'count_eps': float,
        'sum_eps': float,
        'count_release_thresh': 'Int64',
        'editors': 'Int64',
        'edits': 'Int64',
        'month': str
    }
    
    # Try to load from local file first
    local_file = data_dir / f"{year_month}.tsv"
    if local_file.exists():
        logging.info(f"Loading data from local file for {year_month}")
        try:
            df = pd.read_csv(local_file, sep='\t', names=COLUMN_NAMES, dtype=dtype)
        except Exception as e:
            logging.error(f"Error reading local file for {year_month}: {str(e)}")
            return False
    else:
        # Download the file if it doesn't exist locally
        url = f"https://analytics.wikimedia.org/published/datasets/geoeditors_monthly/{year_month}.tsv"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                # Save the file locally
                with open(local_file, 'w') as f:
                    f.write(response.text)
                
                # Read the downloaded file
                df = pd.read_csv(local_file, sep='\t', names=COLUMN_NAMES, dtype=dtype)
            else:
                logging.error(f"Failed to download data for {year_month}. Status code: {response.status_code}")
                return False
        except Exception as e:
            logging.error(f"Error downloading data for {year_month}: {str(e)}")
            return False
    
    # Add unpublished countries based on date
    cutoff_date = datetime.strptime('2024-01', '%Y-%m')
    current_date = datetime.strptime(year_month, '%Y-%m')
    df = add_unpublished_rows(df, year_month, use_legacy=(current_date < cutoff_date))
    
    # Convert month string to date with explicit format
    df['month'] = pd.to_datetime(df['month'], format='%Y-%m')
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Delete existing data for this month if it exists
        db.query(EditorData).filter(EditorData.month == df['month'].iloc[0]).delete()
        
        # Convert numeric columns to proper types
        for col in ['count_release_thresh', 'editors', 'edits']:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')

        for col in ['count_eps', 'sum_eps']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Bulk insert the data
        records = df.to_dict('records')
        db.bulk_insert_mappings(EditorData, records)
        
        db.commit()
        logging.info(f"Successfully processed data for {year_month}")
        return True
    except Exception as e:
        db.rollback()
        logging.error(f"Database error for {year_month}: {str(e)}")
        return False
    finally:
        db.close()

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
        download_monthly_data(month)
    
    logging.info("Data update process completed")

if __name__ == "__main__":
    main() 