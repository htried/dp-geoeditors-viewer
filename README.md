# Wikimedia Editor Data Explorer

A web application for exploring Wikimedia editor data across different countries and time periods.

## Features

- Interactive map visualization of editor activity by country
- Trend analysis comparing editor counts across multiple countries
- Automatic monthly data updates

## Setup

1. Clone this repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the data update script to download initial data:
   ```bash
   python update_data.py
   ```
5. Start the Flask application:
   ```bash
   python app.py
   ```

## Usage

- Access the web interface at `http://localhost:5000`
- Use the map view to visualize editor activity across countries
- Use the trends view to compare editor counts over time

## Toolforge Deployment

To deploy this application on Toolforge:

1. Create a new tool account on Toolforge
2. Clone this repository into your tool's home directory
3. Set up a virtual environment and install dependencies
4. Configure the web service using the Toolforge web service configuration
5. Set up a cron job to run `update_data.py` monthly

Example cron job (run monthly on the 1st):
```
0 0 1 * * /path/to/venv/bin/python /path/to/update_data.py
```

## Data Source

The application uses data from:
https://analytics.wikimedia.org/published/datasets/geoeditors_monthly/
