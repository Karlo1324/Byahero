"""
ByaHero - Smart Commute Predictor
Flask application with commute prediction and bus arrival tracking
"""

from flask import Flask, render_template, request, jsonify
import pickle
import numpy as np
import pandas as pd
import sys
import os

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'data'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'models'))

from routes_config import get_all_routes, get_stops_after
from data_manager import data_manager
from validators import validator
from arrival_predictor import ArrivalPredictor

app = Flask(__name__)

# Load model + encoders
saved_data = pickle.load(open("model.pkl", "rb"))
model_time = saved_data["model_time"]
model_depart = saved_data["model_depart"]
encoders = saved_data["encoders"]

# Initialize arrival predictor
arrivals_df = pd.read_csv("data/bus_arrivals.csv")
arrival_predictor = ArrivalPredictor(arrivals_df)

# ============ HELPER FUNCTIONS ============

def get_location_by_id(location_id):
    """Get location name by ID"""
    try:
        locations = data_manager.get_locations()
        for loc in locations:
            if loc['location_id'] == location_id:
                return loc['name']
    except:
        pass
    return None

def get_location_id_by_name(location_name):
    """Get location ID by name"""
    try:
        locations = data_manager.get_locations()
        for loc in locations:
            if loc['name'] == location_name:
                return loc['location_id']
    except:
        pass
    return None

# ============ PAGE ROUTES ============

@app.route('/')
def index():
    """Commute prediction page"""
    locations = data_manager.get_locations()
    routes = get_all_routes()
    
    # Get dropdown options from data
    times = sorted(pd.read_csv("commute_data.csv")['time'].unique().tolist())
    days = sorted(pd.read_csv("commute_data.csv")['day'].unique().tolist())
    crowds = ["Low", "Medium", "High"]
    
    return render_template('index.html',
                         locations=locations,
                         routes=routes,
                         times=times,
                         days=days,
                         crowds=crowds)

@app.route('/bus-arrivals')
def bus_arrivals():
    """View bus arrival predictions"""
    locations = data_manager.get_locations()
    routes = get_all_routes()
    
    return render_template('bus_arrivals.html',
                         locations=locations,
                         routes=routes)

@app.route('/add-arrival')
def add_arrival():
    """Form to add arrival record"""
    locations = data_manager.get_locations()
    routes = get_all_routes()
    
    return render_template('add_arrival.html',
                         locations=locations,
                         routes=routes)

@app.route('/manage-locations')
def manage_locations():
    """Manage locations page"""
    locations = data_manager.get_locations()
    routes = get_all_routes()
    
    return render_template('manage_locations.html',
                         locations=locations,
                         routes=routes)

@app.route('/historical-data')
def historical_data():
    """View historical arrival data"""
    locations = data_manager.get_locations()
    routes = get_all_routes()
    
    return render_template('historical_data.html',
                         locations=locations,
                         routes=routes)

# ============ API ENDPOINTS - PREDICTIONS ============

@app.route('/api/predict', methods=['POST'])
def predict():
    """Predict travel time and departure decision"""
    try:
        data = request.json
        
        # Prepare input data
        input_array = np.array([[
            encoders["route"].transform([data['route']])[0],
            encoders["time"].transform([data['time']])[0],
            encoders["day"].transform([data['day']])[0],
            encoders["stop"].transform([data['stop']])[0],
            encoders["crowd_level"].transform([data['crowd']])[0]
        ]])
        
        # Make predictions
        travel_time = float(model_time.predict(input_array)[0])
        depart_pred = int(model_depart.predict(input_array)[0])
        depart_decision = encoders["departure_decision"].inverse_transform([depart_pred])[0]
        
        return jsonify({
            'success': True,
            'travel_time': round(travel_time, 1),
            'decision': depart_decision,
            'crowd': data['crowd']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ============ API ENDPOINTS - ARRIVALS ============

@app.route('/api/get-arrivals', methods=['GET'])
def get_arrivals_api():
    """Get bus arrivals for a location"""
    try:
        location_id = request.args.get('location_id', type=int)
        route_id = request.args.get('route_id', type=int)
        limit = request.args.get('limit', default=20, type=int)
        
        arrivals = data_manager.get_arrivals(route_id=route_id, location_id=location_id, limit=limit)
        
        return jsonify({
            'success': True,
            'arrivals': arrivals,
            'count': len(arrivals)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/predict-arrival', methods=['POST'])
def predict_arrival_api():
    """Predict next arrival for a location"""
    try:
        data = request.json
        location_id = data.get('location_id')
        route_id = data.get('route_id')
        
        # Reload fresh arrivals data
        arrivals_df = pd.read_csv("data/bus_arrivals.csv")
        predictor = ArrivalPredictor(arrivals_df)
        
        prediction = predictor.predict_next_arrival(location_id, route_id)
        
        return jsonify({
            'success': True,
            'prediction': prediction
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/add-arrival-record', methods=['POST'])
def add_arrival_record_api():
    """Add a new arrival record"""
    try:
        data = request.json
        
        # Validate input
        valid, errors = validator.validate_arrival_record(
            data.get('route_id'),
            data.get('location_id'),
            data.get('arrival_time'),
            data.get('arrival_date'),
            data.get('departure_time'),
            data.get('crowd_level')
        )
        
        if not valid:
            return jsonify({
                'success': False,
                'errors': errors
            }), 400
        
        # Add record
        result = data_manager.add_arrival_record(
            route_id=data.get('route_id'),
            location_id=data.get('location_id'),
            arrival_time=data.get('arrival_time'),
            arrival_date=data.get('arrival_date'),
            departure_time=data.get('departure_time'),
            crowd_level=data.get('crowd_level'),
            notes=data.get('notes')
        )
        
        if result['success']:
            # Reload arrival predictor with new data
            global arrival_predictor
            arrivals_df = pd.read_csv("data/bus_arrivals.csv")
            arrival_predictor = ArrivalPredictor(arrivals_df)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ============ API ENDPOINTS - LOCATIONS ============

@app.route('/api/get-locations', methods=['GET'])
def get_locations_api():
    """Get locations by route"""
    try:
        route_id = request.args.get('route_id', type=int)
        locations = data_manager.get_locations_by_route(route_id)
        
        return jsonify({
            'success': True,
            'locations': locations
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/get-stops-after', methods=['GET'])
def get_stops_after_api():
    """Get stops after a given stop in the route"""
    try:
        route_id = request.args.get('route_id', type=int)
        current_stop_id = request.args.get('stop_id', type=int)
        
        stops_after = get_stops_after(route_id, current_stop_id)
        
        # Convert stop IDs to location names
        locations = data_manager.get_locations()
        stop_names = {}
        for loc in locations:
            stop_names[loc['location_id']] = loc['name']
        
        result_stops = [
            {"id": sid, "name": stop_names.get(sid, f"Stop {sid}")}
            for sid in stops_after
        ]
        
        return jsonify({
            'success': True,
            'stops': result_stops
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/add-location', methods=['POST'])
def add_location_api():
    """Add a new location"""
    try:
        data = request.json
        
        # Validate
        valid, msg = validator.validate_location_name(data.get('name'))
        if not valid:
            return jsonify({'success': False, 'error': msg}), 400
        
        valid, msg = validator.validate_stop_sequence(data.get('stop_sequence'))
        if not valid:
            return jsonify({'success': False, 'error': msg}), 400
        
        result = data_manager.add_location(
            name=data.get('name'),
            description=data.get('description', ''),
            route_id=data.get('route_id'),
            stop_sequence=data.get('stop_sequence'),
            active=data.get('active', True)
        )
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ============ API ENDPOINTS - STATISTICS ============

@app.route('/api/get-statistics', methods=['GET'])
def get_statistics_api():
    """Get statistics for a location"""
    try:
        location_id = request.args.get('location_id', type=int)
        stats = data_manager.get_arrival_statistics(location_id)
        
        return jsonify({
            'success': True,
            'statistics': stats
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# ============ MAIN ============

if __name__ == '__main__':
    app.run(debug=True, port=3000)
