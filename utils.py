import json
import requests
import pycountry
from datetime import datetime
from pathlib import Path
from models import SessionLocal, EditorData
from sqlalchemy import and_


# Pre-2024 unpublished countries
LEGACY_UNPUBLISHED = {
    'Afghanistan': 'AF', 'Azerbaijan': 'AZ', 'Bahrain': 'BH', 'Bangladesh': 'BD',
    'Belarus': 'BY', 'China': 'CN', 'Cuba': 'CU', 'Djibouti': 'DJ',
    'Egypt': 'EG', 'Eritrea': 'ER', 'Ethiopia': 'ET', 'Honduras': 'HN',
    'Iran': 'IR', 'Iraq': 'IQ', 'Kazakhstan': 'KZ', 'Kuwait': 'KW',
    'Laos': 'LA', 'Myanmar': 'MM', 'Nicaragua': 'NI', 'North Korea': 'KP',
    'Oman': 'OM', 'Pakistan': 'PK', 'Russia': 'RU', 'Rwanda': 'RW',
    'Saudi Arabia': 'SA', 'Sudan': 'SD', 'Syria': 'SY', 'Thailand': 'TH',
    'Turkey': 'TR', 'Turkmenistan': 'TM', 'United Arab Emirates': 'AE',
    'Uzbekistan': 'UZ', 'Venezuela': 'VE', 'Vietnam': 'VN', 'Yemen': 'YE'
}

# Current unpublished countries (2024-01 onwards)
CURRENT_UNPUBLISHED = {
    'China': 'CN', 'Hong Kong': 'HK', 'Cuba': 'CU', 'Iran': 'IR',
    'Macau': 'MO', 'Myanmar': 'MM', 'North Korea': 'KP', 'Syria': 'SY',
    'Vietnam': 'VN'
}

# Column names for the TSV files
COLUMN_NAMES = [
    'wiki_db', 'project', 'country', 'country_code', 'activity_level',
    'count_eps', 'sum_eps', 'count_release_thresh', 'editors', 'edits', 'month'
]

# Define risk levels and their properties
RISK_LEVELS = {
    'low': {'ci': 2.72, 'can_show_edits': True},
    'medium': {'ci': 14.98, 'can_show_edits': False},
    'high': {'ci': 29.96, 'can_show_edits': False},
    'not_published': {'ci': None, 'can_show_edits': False}
}

COUNTRY_RISK_LEVELS = {
    'medium': {
        'AF',  # Afghanistan
        'AZ',  # Azerbaijan
        'BD',  # Bangladesh
        'DJ',  # Djibouti
        'ET',  # Ethiopia
        'HN',  # Honduras
        'IQ',  # Iraq
        'KZ',  # Kazakhstan
        'KW',  # Kuwait
        'LA',  # Laos
        'NI',  # Nicaragua
        'OM',  # Oman
        'PK',  # Pakistan
        'PS',  # Palestine
        'SD',  # Sudan
        'TJ',  # Tajikistan
        'AE',  # United Arab Emirates
        'UZ',  # Uzbekistan
        'VE',  # Venezuela
        'YE',  # Yemen
    },
    'high': {
        'BH',  # Bahrain
        'BY',  # Belarus
        'EG',  # Egypt
        'ER',  # Eritrea
        'RU',  # Russia
        'SA',  # Saudi Arabia
        'TR',  # Türkiye
        'TM',  # Turkmenistan
    },
    'not_published': {
        'CN',  # China
        'HK',  # Hong Kong
        'CU',  # Cuba
        'IR',  # Iran
        'MO',  # Macau
        'MM',  # Myanmar
        'KP',  # North Korea
        'SY',  # Syria
        'VN',  # Vietnam
    }
}

def download_geojson():
    """Download GeoJSON file with country boundaries if it doesn't exist"""
    geojson_path = Path("data") / 'countries.geojson'
    if not geojson_path.exists():
        url = "https://raw.githubusercontent.com/python-visualization/folium/master/examples/data/world-countries.json"
        response = requests.get(url)
        if response.status_code == 200:
            with open(geojson_path, 'wb') as f:
                f.write(response.content)
            return True
    return False

def alpha2_to_alpha3(alpha2):
    """Convert ISO alpha-2 to alpha-3 country code"""
    if alpha2 is None or alpha2 == '--':
        return None
    try:
        return pycountry.countries.get(alpha_2=alpha2).alpha_3
    except (AttributeError, KeyError):
        return None

# Create data directory if it doesn't exist
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Download GeoJSON file if needed
download_geojson()

# Load GeoJSON data
with open(DATA_DIR / 'countries.geojson') as f:
    countries_geojson = json.load(f)

# Create a lookup for country codes to GeoJSON features
country_features = {}
for feature in countries_geojson['features']:
    if 'id' in feature:  # GeoJSON file uses 3-letter codes as IDs
        country_features[feature['id']] = feature

def get_risk_level(country_code):
    """Determine risk level based on country"""
    if country_code is None or country_code == '--':
        return 'not_published'
    
    # Check if the country is in any of the risk level lists
    for level, countries in COUNTRY_RISK_LEVELS.items():
        if country_code in countries:
            return level
    return 'low'  # Default to low risk if not in any other category

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

def get_all_unique_countries(months):
    """
    Get a list of all unique countries from all available data files.
    
    Args:
        months (list): List of month strings in format 'YYYY-MM'
        
    Returns:
        list: List of dictionaries with 'country' and 'country_code' keys
    """
    all_countries = set()
    countries_list = []
    
    for month in months:
        file_path = DATA_DIR / f"{month}.tsv"
        if file_path.exists():
            try:
                df = pd.read_csv(file_path, sep='\t', names=COLUMN_NAMES)
                # Create tuples of (country, country_code) for uniqueness
                country_tuples = set(zip(df['country'], df['country_code']))
                all_countries.update(country_tuples)
            except Exception:
                # Skip files that can't be read
                continue
    
    # Convert set of tuples back to list of dictionaries
    countries_list = [{'country': country, 'country_code': code} 
                      for country, code in all_countries 
                      if not pd.isna(country) and not pd.isna(code)]
    
    # Sort by country name
    countries_list = sorted(countries_list, key=lambda x: x['country'])
    
    return countries_list
