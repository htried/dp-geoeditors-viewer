from flask import Flask, render_template, request
import folium
import branca.colormap as cm
import logging
import numpy as np
import math
from utils import *
import plotly.graph_objects as go
import argparse
from models import SessionLocal, EditorData
from sqlalchemy import and_
from datetime import datetime
import pandas as pd

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler('app.log')  # Log to file
    ]
)

app = Flask(__name__)

@app.route('/')
def index():
    months = get_available_months()
    return render_template('index.html', months=months)

@app.route('/map')
def map_view():
    # Get available months first
    months = get_available_months()
    if not months:
        return "No data available in the database.", 404
        
    # Get parameters with validation
    month = request.args.get('month')
    if not month or month not in months:
        month = months[-2]  # Default to most recent month if invalid or not provided
        
    activity_level = request.args.get('activity_level', '1 to 4')
    project = request.args.get('project', 'en.wikipedia')
    
    # Query data from PostgreSQL
    db = SessionLocal()
    try:
        # Convert month string to date
        month_date = datetime.strptime(month, '%Y-%m')
        
        # Query data for the selected month, activity level, and project
        results = db.query(EditorData).filter(
            and_(
                EditorData.month == month_date,
                EditorData.activity_level == activity_level,
                EditorData.project == project
            )
        ).all()
        
        if not results:
            logging.warning(f"No data found for month={month_date}, activity_level={activity_level}, project={project}")
            return "No data found for the selected parameters.", 404
        
        # Convert results to DataFrame-like structure
        data = []
        for row in results:
            data.append({
                'country': row.country,
                'country_code': row.country_code,
                'editors': row.editors,
                'activity_level': row.activity_level,
                'project': row.project
            })
        
        # Create filtered DataFrame
        filtered_df = pd.DataFrame(data)
        
        # Convert country codes and ensure numeric data
        filtered_df['country_code_alpha3'] = filtered_df['country_code'].apply(alpha2_to_alpha3)
        filtered_df['editors'] = pd.to_numeric(filtered_df['editors'], errors='coerce')
        
        # Add risk level information
        filtered_df['risk_level'] = filtered_df['country_code'].apply(get_risk_level)
        
        # Create hover text
        def create_hover_text(row):
            risk_info = RISK_LEVELS[row['risk_level']]
            base_text = f"<b>{row['country']}</b><br>"
            
            # For unpublished countries or those with -1 editors
            if row['risk_level'] == 'not_published' or row['editors'] == -1:
                return base_text + "Data not published for safety reasons"
            
            editor_text = f"Editors: {int(row['editors']):,}<br>"
            if risk_info['ci'] is not None:
                lower_ci = max(0, int(row['editors'] - risk_info['ci']))
                upper_ci = int(row['editors'] + risk_info['ci'])
                ci_text = f"95% CI: {lower_ci:,} to {upper_ci:,}<br>"
            else:
                ci_text = ""
            
            return base_text + editor_text + ci_text
        
        filtered_df['hover_text'] = filtered_df.apply(create_hover_text, axis=1)
        
        # Create the map with tighter bounds
        m = folium.Map(
            location=[20, 0],
            zoom_start=2,
            min_lat=-60,
            max_lat=85,
            min_lon=-180,
            max_lon=180,
            tiles='cartodbpositron',
            control_scale=True,
            max_bounds=True,  # Prevent infinite scrolling
            min_zoom=2,  # Prevent zooming out too far
            max_zoom=8  # Prevent zooming in too far
        )
        
        # Set the bounds
        m.fit_bounds([[-60, -180], [85, 180]])

        # Set editors to -1 for unpublished countries
        filtered_df.loc[filtered_df['risk_level'] == 'not_published', 'editors'] = -1
        
        # Calculate color scale for published countries
        min_editors = 1
        max_editors = math.ceil(filtered_df[filtered_df['editors'] > 0]['editors'].max() / 100) * 100
        
        def get_color(editors):
            if pd.isna(editors) or editors == -1:
                return '#404040'  # Dark grey for unpublished countries
            # Use log scale for coloring
            log_val = np.log10(editors)
            log_min = np.log10(min_editors)
            log_max = np.log10(max_editors)
            # Normalize to 0-1 range
            normalized = (log_val - log_min) / (log_max - log_min)
            color = cm.LinearColormap(['#440154', '#21918c', '#fde725'], vmin=0, vmax=1)(normalized)
            return color

        # Create GeoJSON features for all countries
        features = []
        for _, row in filtered_df.iterrows():
            if row['country_code_alpha3'] in country_features:
                editors_val = int(row['editors'])
                feature = country_features[row['country_code_alpha3']].copy()
                feature['properties'].update({
                    'name': row['country'],
                    'editors': editors_val,
                    'hover_text': row['hover_text']
                })
                features.append(feature)
        
        # Add all countries in a single layer
        if features:
            folium.GeoJson(
                {'type': 'FeatureCollection', 'features': features},
                name='All Countries',
                style_function=lambda x: {
                    'fillColor': get_color(x['properties'].get('editors')),
                    'color': '#303030' if x['properties'].get('editors') == -1 else 'gray',
                    'weight': 1,
                    'fillOpacity': 0.7
                },
                tooltip=folium.GeoJsonTooltip(
                    fields=['hover_text'],
                    aliases=[''],
                    style=('background-color: white; color: black; font-family: arial; font-size: 12px; padding: 2px;')
                )
            ).add_to(m)

        # Add layer control
        folium.LayerControl().add_to(m)
        
        # Add title with adjusted position and z-index
        title_html = f'''
            <div style="position: fixed; 
                        top: 10px; 
                        left: 50px; 
                        right: 50px; 
                        background-color: white; 
                        padding: 10px; 
                        border-radius: 5px; 
                        z-index: 401; 
                        font-family: Arial; 
                        font-size: 16px; 
                        text-align: center;">
                <h3 style="margin: 0;">Editor Activity Map - {project} - {activity_level} edits - {month}</h3>
                <p style="font-size: 12px; margin: 5px 0 0 0;">Dark grey countries: data not published for safety reasons 
                (<a href="https://foundation.wikimedia.org/wiki/Legal:Wikimedia_Foundation_Country_and_Territory_Protection_List" target="_blank">WMF Country and Territory Protection List</a>)</p>
            </div>
        '''
        m.get_root().html.add_child(folium.Element(title_html))

        # Add custom CSS to adjust map container and controls
        custom_css = '''
            <style>
                .leaflet-container {
                    height: 100%;
                }
                .leaflet-control-layers {
                    margin-top: 60px !important;
                }
            </style>
        '''
        m.get_root().html.add_child(folium.Element(custom_css))
        
        # Add color scale legend
        tick_values = np.logspace(np.log10(min_editors), np.log10(max_editors), 6)
        
        # Create a custom legend container
        legend_html = f'''
            <div style="
                position: fixed;
                bottom: 20px;
                right: 20px;
                z-index: 1000;
                background-color: white;
                padding: 10px;
                border-radius: 5px;
                border: 2px solid rgba(0,0,0,0.2);
                font-family: Arial;
                ">
                <div style="margin-bottom: 5px;"><strong>Number of Editors</strong></div>
                <div style="
                    width: 200px;
                    display: flex;
                    flex-direction: column;
                    gap: 5px;
                    ">
                    <div style="
                        background: linear-gradient(to right, #440154, #21918c, #fde725);
                        height: 15px;
                        width: 100%;
                        ">
                    </div>
                    <div style="
                        display: flex;
                        justify-content: space-between;
                        font-size: 12px;
                        ">
                        <span>1</span>
                        <span>{int(max_editors):,}</span>
                    </div>
                </div>
            </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # Save the map to HTML
        map_html = m._repr_html_()
        
        return render_template('map.html', 
                            plot=map_html,
                            months=get_available_months(),
                            month=month,
                            activity_level=activity_level,
                            project=project)
    except Exception as e:
        logging.error(f"Error creating visualization: {str(e)}")
        return f"Error creating visualization: {str(e)}", 500
    finally:
        db.close()

@app.route('/trends')
def trends_view():
    # Get parameters first
    project = request.args.get('project', 'en.wikipedia')
    activity_level = request.args.get('activity_level', '1 to 4')
    countries = request.args.getlist('countries')
    
    if not countries:
        # Default to US, Britain, and India for English Wikipedia
        if project == 'en.wikipedia':
            countries = ['US', 'GB', 'IN']
    
    try:
        # Query unique countries from database
        db = SessionLocal()
        try:
            countries_list = db.query(EditorData.country, EditorData.country_code).distinct().all()
            countries_list = [{'country': c[0], 'country_code': c[1]} for c in countries_list]
            countries_list = sorted(countries_list, key=lambda x: x['country'])
            
            # Only proceed with trend data if countries are selected
            if countries:
                # Query data for selected countries
                results = db.query(EditorData).filter(
                    and_(
                        EditorData.activity_level == activity_level,
                        EditorData.project == project,
                        EditorData.country_code.in_(countries)
                    )
                ).order_by(EditorData.month).all()
                
                if results:
                    # Convert results to DataFrame
                    data = []
                    for row in results:
                        data.append({
                            'country': row.country,
                            'country_code': row.country_code,
                            'editors': row.editors,
                            'month': row.month.strftime('%Y-%m')
                        })
                    
                    combined_df = pd.DataFrame(data)
                    combined_df['editors'] = pd.to_numeric(combined_df['editors'], errors='coerce')
                    
                    # Create line plot using Plotly
                    fig = go.Figure()
                    
                    # Create a list to store traces and their ordering
                    traces = []
                    
                    # Process each country
                    for country_name in combined_df['country'].unique():
                        country_data = combined_df[combined_df['country'] == country_name]
                        country_code = country_data['country_code'].iloc[0]
                        risk_level = get_risk_level(country_code)
                        risk_info = RISK_LEVELS[risk_level]
                        
                        # Split data into published and unpublished segments
                        published_mask = country_data['editors'] != -1
                        unpublished_mask = country_data['editors'] == -1
                        
                        # Get the most recent editor count for ordering
                        most_recent_count = country_data['editors'].iloc[-1] if not country_data.empty else 0
                        
                        # Handle published data if any exists
                        if published_mask.any():
                            published_data = country_data[published_mask]
                            hover_text = [
                                f"{country_code}: {int(editors):,} ± {risk_info['ci']}"
                                for editors in published_data['editors']
                            ]
                            
                            # Create trace for published data
                            published_trace = go.Scatter(
                                x=published_data['month'],
                                y=published_data['editors'],
                                name=country_name,
                                mode='lines',
                                line=dict(width=2),
                                error_y=dict(
                                    type='constant',
                                    value=risk_info['ci'] if risk_info['ci'] is not None else 0,
                                    visible=True,
                                    color='rgba(68, 68, 68, 0.3)',
                                    thickness=1,
                                    width=0
                                ),
                                hovertext=hover_text,
                                hovertemplate='%{hovertext}<extra></extra>'
                            )
                            traces.append((most_recent_count, published_trace))
                        
                        # Handle unpublished data if any exists
                        if unpublished_mask.any():
                            unpublished_data = country_data[unpublished_mask]
                            hover_text = ["Data not published for safety reasons"] * len(unpublished_data)
                            
                            # Create trace for unpublished data
                            unpublished_trace = go.Scatter(
                                x=unpublished_data['month'],
                                y=[0] * len(unpublished_data),
                                name=f"{country_name} (unpublished)",
                                mode='lines',
                                line=dict(
                                    width=1,
                                    color='rgba(128, 128, 128, 0.3)',
                                    dash='dot'
                                ),
                                hovertext=hover_text,
                                hovertemplate='%{hovertext}<extra></extra>',
                                showlegend=False
                            )
                            traces.append((most_recent_count, unpublished_trace))
                    
                    # Sort traces by most recent count in descending order
                    traces.sort(key=lambda x: x[0], reverse=True)
                    
                    # Add traces to figure in sorted order
                    for _, trace in traces:
                        fig.add_trace(trace)
                    
                    # Customize the layout
                    fig.update_layout(
                        title=f'Editor Count Trends - {project} - {activity_level} edits',
                        xaxis_title="Month",
                        yaxis_title="Number of Editors",
                        yaxis=dict(rangemode='tozero'),
                        hovermode='x unified',
                        plot_bgcolor='white',
                        paper_bgcolor='white',
                        font=dict(family="Arial"),
                        margin=dict(t=50, l=50, r=50, b=50),
                        showlegend=True,
                        legend=dict(
                            yanchor="top",
                            y=0.99,
                            xanchor="left",
                            x=0.01
                        )
                    )
                    
                    plot_html = fig.to_html(
                        full_html=False,
                        include_plotlyjs='cdn',
                        config={'displayModeBar': True, 'scrollZoom': True}
                    )
                else:
                    plot_html = "<div class='alert alert-info'>No data available for the selected parameters.</div>"
            else:
                plot_html = "<div class='alert alert-info'>Select one or more countries to view trends.</div>"
            
            return render_template('trends.html',
                                 plot=plot_html,
                                 countries=countries_list,
                                 selected_countries=countries,
                                 activity_level=activity_level,
                                 project=project)
        
        finally:
            db.close()
    
    except Exception as e:
        logging.error(f"Error creating visualization: {str(e)}")
        return f"Error creating visualization: {str(e)}", 500

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    parser.add_argument('--host', default='0.0.0.0', help='Host to run the server on')
    parser.add_argument('--port', default=5001, type=int, help='Port to run the server on')
    args = parser.parse_args()
    
    if args.debug:
        app.run(host=args.host, port=args.port, debug=True)
    else:
        app.run(host=args.host, port=args.port)