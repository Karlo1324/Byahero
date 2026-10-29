"""
ByaHero - Smart Commute Predictor
Flask application with commute prediction and bus arrival tracking
"""

from flask import (Flask, render_template, request, jsonify, session, Response,
                   redirect, url_for, stream_with_context)
import pickle
import numpy as np
import pandas as pd
import secrets
import sys
import os
import json
import re
from datetime import datetime
from functools import lru_cache

# LLM Integration (optional)
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Add paths for imports
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _sub in ("data", "utils", "models"):
    _path = os.path.join(BASE_DIR, _sub)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from routes_config import (
    get_all_routes,
    get_stops_after,
    get_model_route_name,
    get_model_stop_name,
    resolve_route_id,
    set_model_vocabulary,
    get_known_model_routes,
    get_known_model_stops,
    add_route,
)
from data_manager import data_manager
from validators import validator
from commute_reasoner import CommuteReasoner

# Import arrival predictor v2 for improved predictions
try:
    from arrival_predictor_v2 import ArrivalPredictor as ArrivalPredictorV2
    PREDICTOR_V2_AVAILABLE = True
except ImportError:
    PREDICTOR_V2_AVAILABLE = False

app = Flask(__name__)

# ============ LLM CONFIGURATION ============
# LLM-powered Konduktor (optional, falls back to rule-based)
LLM_CONFIG = {
    'enabled': os.environ.get('KONDUKTOR_USE_LLM', 'auto').lower() not in ('false', '0', 'no'),
    'provider': os.environ.get('KONDUKTOR_LLM_PROVIDER', 'anthropic').lower(),  # 'anthropic' or 'openai'
    'model': os.environ.get('KONDUKTOR_LLM_MODEL', 'claude-3-5-sonnet-20241022'),
    'max_tokens': int(os.environ.get('KONDUKTOR_MAX_TOKENS', '2000')),
    'temperature': float(os.environ.get('KONDUKTOR_TEMPERATURE', '0.3')),
    'anthropic_api_key': os.environ.get('ANTHROPIC_API_KEY'),
    'openai_api_key': os.environ.get('OPENAI_API_KEY'),
}

# Initialize LLM clients
_anthropic_client = None
_openai_client = None

if LLM_CONFIG['enabled'] and LLM_CONFIG['provider'] == 'anthropic' and LLM_CONFIG['anthropic_api_key'] and ANTHROPIC_AVAILABLE:
    try:
        _anthropic_client = anthropic.Anthropic(api_key=LLM_CONFIG['anthropic_api_key'])
        print("✅ Anthropic client initialized for Konduktor LLM")
    except Exception as e:
        print(f"⚠️  Failed to initialize Anthropic client: {e}")

if LLM_CONFIG['enabled'] and LLM_CONFIG['provider'] == 'openai' and LLM_CONFIG['openai_api_key'] and OPENAI_AVAILABLE:
    try:
        _openai_client = openai.OpenAI(api_key=LLM_CONFIG['openai_api_key'])
        print("✅ OpenAI client initialized for Konduktor LLM")
    except Exception as e:
        print(f"⚠️  Failed to initialize OpenAI client: {e}")

def is_llm_available():
    """Check if LLM client is configured and available"""
    if not LLM_CONFIG['enabled']:
        return False
    if LLM_CONFIG['provider'] == 'anthropic':
        return _anthropic_client is not None
    elif LLM_CONFIG['provider'] == 'openai':
        return _openai_client is not None
    return False

# The session stores whether the splash screen has already been shown, so it
# appears when the app is opened rather than on every panel. The key has to
# stay the same across restarts or the browser gets a brand new session and
# the splash comes back on every visit.
SECRET_KEY_FILE = os.path.join(BASE_DIR, "data", ".secret_key")


def _load_or_create_secret_key():
    """Return the app's secret key, creating and storing one if needed."""
    env_key = os.environ.get("BYAHERO_SECRET_KEY")
    if env_key:
        return env_key

    try:
        with open(SECRET_KEY_FILE, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
            if key:
                return key
    except OSError:
        pass

    key = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(SECRET_KEY_FILE), exist_ok=True)
        with open(SECRET_KEY_FILE, "w", encoding="utf-8") as fh:
            fh.write(key)
    except OSError as e:
        print(f"Could not persist secret key: {e}")
    return key


app.secret_key = _load_or_create_secret_key()

# Load model + encoders
with open(os.path.join(BASE_DIR, "model.pkl"), "rb") as _fh:
    saved_data = pickle.load(_fh)
model_time = saved_data["model_time"]
model_depart = saved_data["model_depart"]
encoders = saved_data["encoders"]

ARRIVALS_FILE = os.path.join(BASE_DIR, "data", "bus_arrivals.csv")
COMMUTE_FILE = os.path.join(BASE_DIR, "commute_data.csv")

# The encoders only recognise the routes and stops the model was fitted on.
# A route added at runtime has to borrow one of them, so the vocabulary is
# handed to the route registry and used to validate the route form.
set_model_vocabulary(
    list(encoders["route"].classes_),
    list(encoders["stop"].classes_),
)

# Single shared predictor instance. Retraining is expensive, so it is rebuilt
# only when the underlying CSV changes (see refresh_arrival_predictor).
_arrival_predictor = None
_arrival_predictor_stamp = None


# ============ ARRIVAL PREDICTOR CACHE ============

def _arrivals_stamp():
    """Fingerprint of the arrivals file, used to detect changes cheaply."""
    try:
        stat = os.stat(ARRIVALS_FILE)
        return (stat.st_mtime, stat.st_size)
    except OSError:
        return None


def refresh_arrival_predictor(force=False):
    """
    Rebuild the shared arrival predictor when the arrivals file changed.
    Returns the current predictor instance.
    """
    global _arrival_predictor, _arrival_predictor_stamp

    stamp = _arrivals_stamp()
    if force or _arrival_predictor is None or stamp != _arrival_predictor_stamp:
        try:
            arrivals_df = pd.read_csv(ARRIVALS_FILE)
        except (FileNotFoundError, pd.errors.EmptyDataError):
            arrivals_df = pd.DataFrame(columns=[
                "arrival_id", "route_id", "location_id", "arrival_time",
                "arrival_date", "departure_time", "crowd_level", "notes",
                "recorded_at",
            ])
        if PREDICTOR_V2_AVAILABLE:
            _arrival_predictor = ArrivalPredictorV2(arrivals_df)
        else:
            from arrival_predictor import ArrivalPredictor
            _arrival_predictor = ArrivalPredictor(arrivals_df)
        _arrival_predictor_stamp = stamp

    return _arrival_predictor


# ============ HELPER FUNCTIONS ============

# Key used in the session to remember that the splash has been shown.
SPLASH_SESSION_KEY = 'splash_shown'


def _wants_splash():
    """
    Decide whether this request should show the splash screen.

    The splash belongs to opening the app, not to moving between panels, so
    it is shown only the first time in a session. The flag is cleared when the
    user explicitly asks for it again (the "restart" link on the home page),
    which is why it lives in the session rather than in a cookie: the session
    ends when the browser is closed.
    """
    if session.get(SPLASH_SESSION_KEY):
        return False
    session[SPLASH_SESSION_KEY] = True
    return True


def _as_int(value):
    """Coerce a form/query value to an int, or None if it isn't numeric."""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_location_by_id(location_id):
    """Get location name by ID"""
    location_id = _as_int(location_id)
    if location_id is None:
        return None
    try:
        locations = data_manager.get_locations()
        for loc in locations:
            if _as_int(loc['location_id']) == location_id:
                return loc['name']
    except Exception:
        pass
    return None


def get_location_id_by_name(location_name, route_id=None):
    """
    Get location ID by name.

    When a route is given, only that route's stops are considered. Two
    routes may carry a stop with the same name, so the route is what makes
    the lookup unambiguous.
    """
    if not location_name:
        return None
    try:
        locations = data_manager.get_locations()
        for loc in locations:
            if route_id is not None and _as_int(loc.get('route_id')) != _as_int(route_id):
                continue
            if loc['name'] == location_name:
                return _as_int(loc['location_id'])
    except Exception:
        pass
    return None


def _location_name_map():
    """Map of location_id -> name for every known location."""
    return {loc['location_id']: loc['name'] for loc in data_manager.get_locations()}


# ============ PAGE ROUTES ============

@app.route('/')
def index():
    """Redirect to trip planner as the main page"""
    return redirect(url_for('trip_planner'))


@app.route('/trip-planner')
def trip_planner():
    """Unified trip planner: commute prediction + bus arrival timeline"""
    locations = data_manager.get_locations()
    routes = get_all_routes()

    # Get dropdown options from data
    commute_df = pd.read_csv(COMMUTE_FILE)
    times = sorted(commute_df['time'].unique().tolist())
    days = sorted(commute_df['day'].unique().tolist())
    crowds = ["Low", "Medium", "High"]

    return render_template('trip_planner.html',
                           locations=locations,
                           routes=routes,
                           times=times,
                           days=days,
                           crowds=crowds,
                           show_splash=_wants_splash())


@app.route('/add-arrival')
def add_arrival():
    """Form to add arrival record"""
    locations = data_manager.get_locations()
    routes = get_all_routes()

    return render_template('add_arrival.html',
                           locations=locations,
                           routes=routes,
                           show_splash=_wants_splash())


@app.route('/manage-locations')
def manage_locations():
    """Manage locations page"""
    locations = data_manager.get_locations()
    routes = get_all_routes()

    return render_template('manage_locations.html',
                           locations=locations,
                           routes=routes,
                           model_routes=get_known_model_routes(),
                           model_stops=get_known_model_stops(),
                           show_splash=_wants_splash())


@app.route('/historical-data')
def historical_data():
    """View historical arrival data"""
    locations = data_manager.get_locations()
    routes = get_all_routes()

    return render_template('historical_data.html',
                           locations=locations,
                           routes=routes,
                           show_splash=_wants_splash())


@app.route('/restart-splash')
def restart_splash():
    """
    Clear the splash flag so the next page load shows the splash again.

    This is the escape hatch for the case where someone closed the tab
    quickly and never actually saw the opening screen.
    """
    session.pop(SPLASH_SESSION_KEY, None)
    return redirect(url_for('index'))


# ============ API ENDPOINTS - PREDICTIONS ============

@app.route('/api/predict', methods=['POST'])
def predict():
    """Predict travel time and departure decision"""
    try:
        data = request.get_json(silent=True) or {}

        required = ['route', 'time', 'day', 'stop', 'crowd']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({
                'success': False,
                'error': f"Missing required field(s): {', '.join(missing)}"
            }), 400

        # The UI sends the route id; the model was trained on the
        # commute_data.csv route names, so translate before encoding.
        route_id = resolve_route_id(data['route'])
        if route_id is None:
            return jsonify({
                'success': False,
                'error': f"Unknown route: {data['route']}"
            }), 400

        model_route = get_model_route_name(route_id)

        # The model's "stop" feature is the boarding point, so the origin is
        # what has to be translated into the model's stop vocabulary.
        origin_id = _as_int(data.get('origin'))
        origin_name = get_location_by_id(origin_id) if origin_id is not None else None
        if origin_name is None and isinstance(data.get('origin'), str):
            # The form may send a name instead of an id. The lookup is
            # scoped to the route, because two routes may share a stop name.
            origin_name = data['origin'].strip() or None
            origin_id = get_location_id_by_name(origin_name, route_id=route_id)

        model_stop = get_model_stop_name(
            route_id, origin_id, fallback_name=origin_name
        )
        if not model_stop:
            return jsonify({
                'success': False,
                'error': "Could not determine the boarding stop for this route"
            }), 400

        # Destination is optional context, but if supplied it must be a stop
        # that actually sits after the origin on the route. The name is
        # matched against this route's stops rather than looked up
        # globally, because two routes may share a stop name.
        destination_name = data.get('stop')
        if destination_name and origin_id is not None:
            valid_dests = get_stops_after(route_id, origin_id)
            if valid_dests:
                stop_names = _location_name_map()
                valid_names = {stop_names.get(sid) for sid in valid_dests}
                if destination_name not in valid_names:
                    return jsonify({
                        'success': False,
                        'error': "Destination must come after the origin on this route"
                    }), 400

        # Prepare input data
        try:
            input_array = np.array([[
                encoders["route"].transform([model_route])[0],
                encoders["time"].transform([data['time']])[0],
                encoders["day"].transform([data['day']])[0],
                encoders["stop"].transform([model_stop])[0],
                encoders["crowd_level"].transform([data['crowd']])[0]
            ]])
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': f"The model has no data for that combination ({e})"
            }), 400

        # Make predictions
        travel_time = float(model_time.predict(input_array)[0])
        depart_pred = int(model_depart.predict(input_array)[0])
        depart_decision = encoders["departure_decision"].inverse_transform([depart_pred])[0]

        return jsonify({
            'success': True,
            'travel_time': round(travel_time, 1),
            'decision': depart_decision,
            'crowd': data['crowd'],
            'origin': origin_name,
            'destination': destination_name,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/trip-plan', methods=['POST'])
def trip_plan_api():
    """Unified trip plan: commute prediction + bus arrival timeline"""
    try:
        data = request.get_json(silent=True) or {}

        required = ['route', 'origin', 'destination', 'time', 'day', 'crowd']
        missing = [f for f in required if not data.get(f)]
        if missing:
            return jsonify({
                'success': False,
                'error': f"Missing required field(s): {', '.join(missing)}"
            }), 400

        route_id = resolve_route_id(data['route'])
        if route_id is None:
            return jsonify({
                'success': False,
                'error': f"Unknown route: {data['route']}"
            }), 400

        model_route = get_model_route_name(route_id)

        # Origin (boarding point)
        origin_id = _as_int(data.get('origin'))
        origin_name = get_location_by_id(origin_id) if origin_id is not None else None
        if origin_name is None and isinstance(data.get('origin'), str):
            origin_name = data['origin'].strip() or None
            origin_id = get_location_id_by_name(origin_name, route_id=route_id)

        model_stop = get_model_stop_name(
            route_id, origin_id, fallback_name=origin_name
        )
        if not model_stop:
            return jsonify({
                'success': False,
                'error': "Could not determine the boarding stop for this route"
            }), 400

        # Destination
        destination_id = _as_int(data.get('destination'))
        destination_name = get_location_by_id(destination_id) if destination_id is not None else None

        # Validate destination comes after origin
        if destination_id is not None and origin_id is not None:
            valid_dests = get_stops_after(route_id, origin_id)
            if valid_dests and destination_id not in valid_dests:
                return jsonify({
                    'success': False,
                    'error': "Destination must come after the origin on this route"
                }), 400

        # Prepare input for commute prediction
        try:
            input_array = np.array([[
                encoders["route"].transform([model_route])[0],
                encoders["time"].transform([data['time']])[0],
                encoders["day"].transform([data['day']])[0],
                encoders["stop"].transform([model_stop])[0],
                encoders["crowd_level"].transform([data['crowd']])[0]
            ]])
        except ValueError as e:
            return jsonify({
                'success': False,
                'error': f"The model has no data for that combination ({e})"
            }), 400

        # Make commute predictions
        travel_time = float(model_time.predict(input_array)[0])
        depart_pred = int(model_depart.predict(input_array)[0])
        depart_decision = encoders["departure_decision"].inverse_transform([depart_pred])[0]

        # Generate insights
        insights = []
        if data['crowd'] == 'High':
            insights.append("High crowd level — expect delays and standing room only")
        elif data['crowd'] == 'Medium':
            insights.append("Moderate crowd — some seats may be available")
        else:
            insights.append("Low crowd — comfortable seating likely available")

        hour = int(data['time'].split(':')[0])
        if 6 <= hour <= 9 or 17 <= hour <= 19:
            insights.append("Peak hours — traffic may increase travel time")
        if data['day'] in ['Saturday', 'Sunday']:
            insights.append("Weekend schedule — fewer buses may be running")

        # Get bus arrival timeline for all stops on this route
        predictor = refresh_arrival_predictor()
        all_locations = data_manager.get_locations_by_route(route_id)

        arrivals = []
        for loc in all_locations:
            loc_id = loc['location_id']
            loc_name = loc['name']
            prediction = predictor.predict_next_arrival(loc_id, route_id, data['crowd'])

            arrivals.append({
                'location_id': loc_id,
                'location_name': loc_name,
                'last_arrival': prediction.get('last_arrival'),
                'next_arrival': prediction.get('next_arrival'),
                'confidence': prediction.get('confidence', 'Unknown'),
                'status': prediction.get('status', 'Unknown'),
            })

        # Smart unified recommendation
        # If next bus at origin arrives AFTER recommended departure time, suggest waiting for it
        origin_arrival = next((a for a in arrivals if a['location_id'] == origin_id), None)
        next_bus_time = None
        if origin_arrival and origin_arrival['next_arrival']:
            next_bus_time = origin_arrival['next_arrival']
            if depart_decision == 'leave_now':
                # Check if bus comes within 10 minutes
                try:
                    from datetime import datetime
                    bus_dt = datetime.strptime(origin_arrival['next_arrival'], '%H:%M')
                    now_dt = datetime.strptime(data['time'], '%I:%M %p') if ' ' in data['time'] else datetime.strptime(data['time'], '%H:%M')
                    diff_minutes = (bus_dt - now_dt).total_seconds() / 60
                    if 0 <= diff_minutes <= 10:
                        depart_decision = 'catch_next_bus'
                        insights.append(f"Next bus arrives in {int(diff_minutes)} min — wait for it!")
                except:
                    pass

        return jsonify({
            'success': True,
            'trip_plan': {
                'commute': {
                    'travel_time': round(travel_time, 1),
                    'decision': depart_decision,
                    'insights': insights,
                    'next_bus_time': next_bus_time,
                },
                'arrivals': arrivals,
                'origin_stop_id': origin_id,
                'destination_stop_id': destination_id,
            }
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

        # Guard against absurd limits from a hand-crafted query string.
        limit = max(1, min(limit, 1000))

        arrivals = data_manager.get_arrivals(
            route_id=route_id, location_id=location_id, limit=limit
        )

        return jsonify({
            'success': True,
            'arrivals': arrivals,
            'count': len(arrivals)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/predict-arrival', methods=['POST'])
def predict_arrival_api():
    """Predict next arrival for a location using improved predictor"""
    try:
        data = request.get_json(silent=True) or {}
        location_id = data.get('location_id')
        route_id = data.get('route_id')
        crowd_level = data.get('crowd_level')

        if location_id is None:
            return jsonify({
                'success': False, 'error': 'location_id is required'
            }), 400

        try:
            location_id = int(location_id)
            route_id = int(route_id) if route_id not in (None, '') else None
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'location_id and route_id must be numbers'
            }), 400

        predictor = refresh_arrival_predictor()
        prediction = predictor.predict_next_arrival(
            location_id, route_id, crowd_level
        )

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
        data = request.get_json(silent=True) or {}

        # Validate input
        valid, errors = validator.validate_arrival_record(
            data.get('route_id'),
            data.get('location_id'),
            data.get('arrival_time'),
            data.get('arrival_date'),
            data.get('departure_time'),
            data.get('crowd_level'),
            data.get('tz_offset_minutes')
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
            # The arrivals file changed, so drop the cached predictor and let
            # the next request rebuild it from the new data.
            refresh_arrival_predictor(force=True)

        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============ API ENDPOINTS - ROUTES ============

@app.route('/api/get-routes', methods=['GET'])
def get_routes_api():
    """
    Get the active routes.

    The route form lives on a page that was rendered before a route was
    added, so the page re-reads the routes from here rather than relying on
    the markup it was served with.
    """
    try:
        routes = get_all_routes()
        return jsonify({
            'success': True,
            'routes': {
                route_id: {
                    'id': route['id'],
                    'name': route['name'],
                    'description': route.get('description', ''),
                    'stops': route.get('stops', []),
                    'model_route': route.get('model_route', ''),
                }
                for route_id, route in routes.items()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/add-route', methods=['POST'])
def add_route_api():
    """
    Add a new route, together with the stops that belong to it.

    The stops are created as locations on the new route, numbered in the
    order they are given.
    """
    try:
        data = request.get_json(silent=True) or {}

        valid, msg = validator.validate_route_name(data.get('name'))
        if not valid:
            return jsonify({'success': False, 'error': msg}), 400

        valid, msg = validator.validate_model_route(
            data.get('model_route'), get_known_model_routes()
        )
        if not valid:
            return jsonify({'success': False, 'error': msg}), 400

        stops, errors = validator.validate_stop_names(data.get('stops'))
        if errors:
            return jsonify({'success': False, 'error': '; '.join(errors)}), 400

        if len(stops) < 2:
            return jsonify({
                'success': False,
                'error': 'A route needs at least two stops'
            }), 400

        # Every stop needs the model label it maps onto, so the prediction
        # still works once the route is in use.
        model_stops = data.get('model_stops') or {}
        prepared = []
        for index, stop_name in enumerate(stops):
            model_stop = model_stops.get(index) or model_stops.get(str(index))
            if not model_stop:
                return jsonify({
                    'success': False,
                    'error': f"No prediction basis selected for '{stop_name}'"
                }), 400

            valid, msg = validator.validate_model_stop(
                model_stop, get_known_model_stops()
            )
            if not valid:
                return jsonify({'success': False, 'error': msg}), 400

            prepared.append({'name': stop_name, 'model_stop': model_stop})

        result = add_route(
            name=data.get('name'),
            description=data.get('description', ''),
            model_route=data.get('model_route'),
            stops=prepared
        )

        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error')}), 400

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
        stop_names = _location_name_map()

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
        data = request.get_json(silent=True) or {}

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


@app.route('/api/edit-location/<int:location_id>', methods=['POST'])
def edit_location_api(location_id):
    """Edit an existing location's name, description, route, or sequence"""
    try:
        data = request.get_json(silent=True) or {}

        existing = data_manager.read_rows('locations.csv',
                                            ['location_id', 'name', 'description',
                                             'route_id', 'stop_sequence', 'active'])

        match = [r for r in existing if _as_int(r.get('location_id')) == location_id]
        if not match:
            return jsonify({'success': False, 'error': f"Location {location_id} not found"}), 404

        row = dict(match[0])

        if 'name' in data and data['name']:
            valid, msg = validator.validate_location_name(data['name'])
            if not valid:
                return jsonify({'success': False, 'error': msg}), 400
            row['name'] = data['name']

        if 'description' in data:
            row['description'] = data['description'] or ''

        if 'route_id' in data:
            try:
                int(data['route_id'])
                row['route_id'] = int(data['route_id'])
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Invalid route ID'}), 400

        if 'stop_sequence' in data:
            try:
                int(data['stop_sequence'])
                if int(data['stop_sequence']) < 1:
                    return jsonify({'success': False, 'error': 'Stop sequence must be a positive number'}), 400
                row['stop_sequence'] = int(data['stop_sequence'])
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Stop sequence must be a number'}), 400

        if 'active' in data:
            row['active'] = 'true' if bool(data['active']) else 'false'

        new_rows = []
        updated = False
        for r in existing:
            if _as_int(r.get('location_id')) == location_id:
                new_rows.append(row)
                updated = True
            else:
                new_rows.append(r)

        if not updated:
            new_rows.append(row)

        columns = ['location_id', 'name', 'description', 'route_id',
                   'stop_sequence', 'active']
        data_manager.write_rows('locations.csv', new_rows, columns)

        return jsonify({'success': True, 'message': 'Location updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/delete-location/<int:location_id>', methods=['DELETE'])
def delete_location_api(location_id):
    """Remove a location entirely from the registry"""
    try:
        existing = data_manager.read_rows('locations.csv',
                                           ['location_id', 'name', 'description',
                                            'route_id', 'stop_sequence', 'active'])
        if not any(r.get('location_id') == location_id for r in existing):
            return jsonify({'success': False, 'error': f"Location {location_id} not found"}), 404

        remaining = [r for r in existing if r.get('location_id') != location_id]
        columns = ['location_id', 'name', 'description', 'route_id',
                   'stop_sequence', 'active']
        data_manager.write_rows('locations.csv', remaining, columns)
        return jsonify({'success': True, 'message': f"Location {location_id} deleted"})
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


# ============ API ENDPOINTS - TIMEZONE ============

@app.route('/api/get-timezone', methods=['GET'])
def get_timezone_api():
    """
    Report the user's timezone offset in minutes.

    The browser sends `getTimezoneOffset()` (UTC minus local, in minutes),
    so the server can compare an arrival against the clock the user actually
    looked at. Without this the server's own clock is used, which is wrong
    whenever the two are in different timezones -- and a hosted deployment
    usually runs in UTC, hours behind the user.
    """
    try:
        offset = request.args.get('tz_offset_minutes', type=int)
        return jsonify({
            'success': True,
            'tz_offset_minutes': offset if offset is not None else 0
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============ CSV EXPORT ============

def _csv_response(csv_text, filename):
    """Send CSV text back as a downloadable file."""
    response = Response(csv_text)
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@app.route('/export/arrivals.csv')
def export_arrivals_csv():
    """
    Download the arrival records as a CSV file.

    The same filters the Historical Data page offers can be applied through
    the query string, so the export matches what is on screen.
    """
    try:
        route_id = request.args.get('route_id', type=int)
        location_id = request.args.get('location_id', type=int)
        start_date = request.args.get('start_date') or None
        end_date = request.args.get('end_date') or None

        csv_text, count = data_manager.export_arrivals_csv(
            route_id=route_id,
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
        )

        stamp = datetime.now().strftime('%Y%m%d-%H%M')
        return _csv_response(csv_text, f'byahero-arrivals-{stamp}.csv')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/export/locations.csv')
def export_locations_csv():
    """Download the location registry as a CSV file."""
    try:
        csv_text, count = data_manager.export_locations_csv()
        stamp = datetime.now().strftime('%Y%m%d-%H%M')
        return _csv_response(csv_text, f'byahero-locations-{stamp}.csv')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/export-preview')
def export_preview_api():
    """
    Report how many rows an export would contain.

    The Historical Data page calls this so it can warn when the export is
    empty instead of handing the user a file with nothing in it.
    """
    try:
        route_id = request.args.get('route_id', type=int)
        location_id = request.args.get('location_id', type=int)
        start_date = request.args.get('start_date') or None
        end_date = request.args.get('end_date') or None

        csv_text, count = data_manager.export_arrivals_csv(
            route_id=route_id,
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
        )
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============ KONDUKTOR CHATBOT API ============

@app.route('/api/konduktor/status', methods=['GET'])
def konduktor_status_api():
    """Check LLM availability status"""
    return jsonify({
        'success': True,
        'llm_available': is_llm_available(),
        'llm_mode': is_llm_available(),
        'provider': LLM_CONFIG['provider'] if is_llm_available() else None,
        'model': LLM_CONFIG['model'] if is_llm_available() else None,
    })


@app.route('/api/konduktor/chat', methods=['POST'])
def konduktor_chat_api():
    """Konduktor AI chat endpoint with data integration"""
    try:
        data = request.get_json(silent=True) or {}
        message = data.get('message', '').strip()
        context = data.get('context', {})

        if not message:
            return jsonify({'success': False, 'error': 'Empty message'}), 400

        # Try LLM if enabled and configured
        if is_llm_available():
            return stream_llm_response(message, context)

        # Use enhanced rule-based with trip planning
        response_text, suggestions, trip_plan, updated_context = generate_konduktor_response(message, context)

        return jsonify({
            'success': True,
            'response': response_text,
            'suggestions': suggestions,
            'tripPlan': trip_plan,
            'context': updated_context,
            'mode': 'rule-based'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============ LIVE BUS TRACKING & WEATHER ============

@app.route('/api/retrain-model', methods=['POST'])
def retrain_model_api():
    """Trigger a fresh retrain of the per-location arrival predictor on all logged arrivals."""
    try:
        from arrival_predictor_v2 import ArrivalPredictor
        df = data_manager.get_commute_data()
        if df is None or len(df) == 0:
            return jsonify({'success': False, 'error': 'No training data available'}), 400
        locations = data_manager.get_locations()
        trained = 0
        for loc in locations:
            try:
                predictor = ArrivalPredictor(df)
                predictor.train_improved_model(loc['location_id'])
                trained += 1
            except Exception as e:
                print(f"Error training for location {loc.get('location_id')}: {e}")
        return jsonify({'success': True, 'message': f'Retrained {trained} location models'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/weather', methods=['GET'])
def weather_api():
    """Return current weather for a stop, with optional caching and fallback."""
    try:
        from weather_service import get_weather_for_location
        location_id = request.args.get('location_id', type=int)
        locations = data_manager.get_locations() if location_id is None else [
            loc for loc in data_manager.get_locations() if loc.get('location_id') == location_id
        ]
        if not locations:
            return jsonify({'success': False, 'error': 'Location not found'}), 404
        force_refresh = request.args.get('refresh', type=str, default='0') == '1'
        if force_refresh:
            from weather_service import _load_cache, _save_cache, _cache_key
            cache = _load_cache()
            for loc in locations:
                lat, lng = loc.get('latitude'), loc.get('longitude')
                if lat and lng:
                    cache.pop(_cache_key(float(lat), float(lng)), None)
            _save_cache(cache)
        results = []
        for loc in locations:
            info = get_weather_for_location(loc)
            if info:
                results.append(info)
        if not results:
            return jsonify({'success': False, 'error': 'Weather data unavailable for location'}), 503
        return jsonify({'success': True, 'weather': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def stream_llm_response(message, context):
    """Call LLM API and return response"""
    system_prompt = get_konduktor_system_prompt(context)

    try:
        if LLM_CONFIG['provider'] == 'anthropic':
            response = _anthropic_client.messages.create(
                model=LLM_CONFIG['model'],
                max_tokens=LLM_CONFIG['max_tokens'],
                temperature=LLM_CONFIG['temperature'],
                system=system_prompt,
                messages=[{"role": "user", "content": message}]
            )
            response_text = response.content[0].text
        else: # OpenAI
            response = _openai_client.chat.completions.create(
                model=LLM_CONFIG['model'],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                max_tokens=LLM_CONFIG['max_tokens'],
                temperature=LLM_CONFIG['temperature'],
            )
            response_text = response.choices[0].message.content

        # Extract suggestions from LLM response or use defaults
        suggestions = ['Plan a trip', 'Next bus times', 'How predictions work']

        # Try to extract trip plan context from LLM response if needed
        updated_context = context.copy()
        if 'destination' in message.lower() or 'arrive' in message.lower():
            updated_context['trip_intent'] = 'planning'

        return jsonify({
            'success': True,
            'response': response_text,
            'suggestions': suggestions,
            'context': updated_context,
            'mode': 'llm'
        })
    except Exception as e:
        # Fallback if LLM fails
        print(f"LLM Error: {e}")
        response_text, suggestions, trip_plan, updated_context = generate_konduktor_response(message, context)
        return jsonify({
            'success': True,
            'response': f"(Fallback) {response_text}",
            'suggestions': suggestions,
            'tripPlan': trip_plan,
            'context': updated_context,
            'mode': 'fallback'
        })


def get_konduktor_system_prompt(context):
    """Build the full system prompt for LLM"""

    # 1. Base IDENTITY and STYLE (from user provided prompt)
    base_prompt = """# SYSTEM PROMPT: Helpful, Intelligent, Human-Like AI Assistant

## ROLE AND IDENTITY
You are Konduktor, an advanced AI assistant designed to help users with the ByaHero bus system in Digos City. Communicate naturally and intelligently.

Your goal is not merely to answer questions, but to understand the user intent and provide the most useful response possible.

## 1. COMMUNICATION STYLE
- Speak naturally, clearly, and conversationally.
- Be friendly, respectful, patient, and professional.
- Match the user language, tone, and level of understanding.
- Explain complicated concepts using simple words and relatable examples.
- Avoid unnecessary introductions, repetitive conclusions, and filler.
- Use headings, bullet points, and code blocks when they improve readability.

## 2. UNDERSTAND BEFORE ANSWERING
- Identify what the user actually wants, even with typos or informal language.
- Use context to avoid asking for information the user already provided.
- Remember details throughout the conversation (starting point, destination, time).

## 3. REASONING AND PROBLEM-SOLVING
- Analyze complex problems systematically.
- Distinguish facts, assumptions, and estimates.
- Admit uncertainty when information is incomplete.
- Never invent facts, sources, or results.
- When data is insufficient, clearly state that estimates are uncertain.

## 4. ByaHero SPECIFIC KNOWLEDGE
You are the expert on ByaHero, a mini-bus predictor for Digos City.
- Route: Currently focused on Kapatagan to Digos Terminal.
- Stops: Kapatagan, Soong, Binaton, Digos Terminal.
- Prediction: Uses a Random Forest ML model for travel time and statistical analysis for bus arrivals.
- Crowd Levels: Low (Comfortable), Medium (Normal), High (Standing room only/Delays).
- Validation: Future arrivals are not allowed; departures must be after arrivals.
- Weather Integration: Weather can affect travel times. Rain, thunderstorms, and heavy precipitation typically add 15-40% to travel time. When users ask about weather, check the /api/weather endpoint and reference actual conditions, but never invent delays or claim weather directly confirms a bus delay.

## 5. TRIP PLANNING CAPABILITIES
When users ask about trips:
- Understand natural language: "I want to go to Digos at 2 PM"
- Extract: destination, desired time, starting location
- Recommend: best waiting time, predicted arrival, departure time
- Support follow-ups: "What if I leave 30 minutes later?"
- Always distinguish predicted from confirmed arrivals
- Explain uncertainty when data is limited
"""

    # 2. Inject Current DATA CONTEXT
    data_context = f"""
## CURRENT DATA CONTEXT
- Page: {context.get('currentPage', '/')}
- Selected Route ID: {context.get('routeId', 'None')}
- Selected Origin ID: {context.get('originId', 'None')}
- Selected Destination ID: {context.get('destinationId', 'None')}
"""

    if context.get('lastTripPlan'):
        tp = context['lastTripPlan']
        data_context += f"- Last Trip Plan Result: Travel time {tp['commute']['travel_time']}m, Decision: {tp['commute']['decision']}\n"

    # 3. CORE PRINCIPLE (from user provided prompt)
    footer = """
## CORE PRINCIPLE
Be helpful without being blindly agreeable, intelligent without being condescending, detailed without being overwhelming, and conversational without sacrificing accuracy.

Prioritize usefulness, honesty, clarity, adaptability, and respect in every interaction.
"""

    return base_prompt + data_context + footer


def generate_konduktor_response(message, context):
    """Generate contextual response using available data"""
    msg_lower = message.lower()
    msg_stripped = message.strip()

    # Get current page context
    current_page = context.get('currentPage', '/')
    route_id = context.get('routeId')
    origin_id = context.get('originId')
    destination_id = context.get('destinationId')

    # Initialize context tracking for multi-turn conversations
    active_trip = context.get('active_trip', {})

    # ===== SMART FOLLOW-UP: detect location mentions even without trip keywords =====
    # If the user has an active trip context, pick up on location mentions
    active_trip = context.get('active_trip', {})
    if active_trip and any(kw in msg_lower for kw in ['from', 'boarding', 'at ', 'starting', 'to ', 'terminal']):
        return handle_trip_planning(msg_lower, msg_stripped, active_trip, context)

    # ===== INTELLIGENT TRIP PLANNING =====
    if any(kw in msg_lower for kw in ['plan', 'trip', 'go to', 'want to go', 'heading', 'getting to', 'arrive at', 'make it to']):
        return handle_trip_planning(msg_lower, msg_stripped, active_trip, context)

    # ===== NEXT BUS / ARRIVAL TIMES =====
    if any(kw in msg_lower for kw in ['next bus', 'when is the next', 'when will the bus', 'bus arrival', 'when does the bus', 'next mini', 'mini bus next']):
        if route_id and origin_id:
            return handle_next_bus_query(route_id, origin_id, msg_lower)
        elif route_id:
            return (
                "To show you the next bus times, I need to know where you're boarding. "
                "Which stop will you be at? (e.g., Binaton, Soong, Kapatagan)"
            ), ['Show all stops', 'Plan a trip', 'How predictions work'], None, active_trip
        return (
            "I can check next bus arrival times! First, select a route on the Trip Planner. "
            "I'll show you the predicted next arrival at each stop with confidence levels."
        ), ['Go to Trip Planner', 'Plan a trip', 'Explain confidence'], None, active_trip

    # ===== WAITING TIME / HOW LONG TO WAIT =====
    if any(kw in msg_lower for kw in ['wait', 'how long', 'when should i wait', 'when to wait', 'at binaton', 'at soong']):
        return handle_waiting_time_query(msg_lower, active_trip, context)

    # ===== CROWD LEVEL =====
    if any(kw in msg_lower for kw in ['crowd', 'busy', 'packed', 'empty', 'seats', 'how crowded']):
        return (
            "Crowd level affects both travel time and bus arrival predictions:\n\n"
            "🟢 **Low** - Comfortable seating, faster travel\n"
            "🟡 **Medium** - Some seats available, normal travel time\n"
            "🔴 **High** - Standing room only, expect delays (+5-10 min)\n\n"
            "The model was trained on historical data with these crowd levels. "
            "Select the level that matches what you're experiencing!"
        ), ['Current crowd level', 'How crowd affects time', 'Plan a trip'], None, active_trip

    # ===== DEPARTURE DECISION =====
    if any(kw in msg_lower for kw in ['leave now', 'should i leave', 'catch next', 'wait or go']):
        return (
            "The departure decision is based on:\n\n"
            "• **Leave Now** - Wait longer than the travel time; catch the next bus\n"
            "• **Wait** - A bus arrives soon, better to wait for it\n"
            "• **Catch Next Bus** - The next bus is within 10 minutes\n\n"
            "If you're already at the stop, I can estimate when the next one comes!"
        ), ['Next bus time', 'Plan a trip', 'Explain predictions'], None, active_trip

    # ===== PREDICTION EXPLANATION =====
    if any(kw in msg_lower for kw in ['predict', 'how', 'work', 'model', 'algorithm', 'ml', 'machine learning', 'confidence']):
        return (
            "Here's how ByaHero predictions work:\n\n"
            "**Travel Time Prediction:**\n"
            "• Uses a Random Forest model trained on 300+ synthetic trips\n"
            "• Factors: Route, Time, Day, Origin Stop, Crowd Level\n"
            "• Outputs: Estimated minutes + Departure recommendation\n\n"
            "**Bus Arrival Prediction:**\n"
            "• Statistical model based on YOUR recorded arrivals\n"
            "• Calculates average intervals between buses per stop\n"
            "• Confidence = number of historical records\n"
            "• More records = higher confidence\n\n"
            "**Smart Recommendation:**\n"
            "• Combines both: if bus arrives within 10 min of your departure, suggests 'Catch Next Bus'\n"
            "• Otherwise uses ML departure decision (Leave Now / Wait)"
        ), ['See example prediction', 'Record arrival data', 'Improve accuracy'], None, active_trip

    # ===== RECORD ARRIVALS =====
    if any(kw in msg_lower for kw in ['record', 'add arrival', 'log', 'input', 'enter', 'save arrival']):
        return (
            "To record a bus arrival:\n\n"
            "1. Go to **Add Arrival** page\n"
            "2. Select **Route** and **Location**\n"
            "3. Enter **Arrival Date & Time** (past only, no future!)\n"
            "4. Optional: **Departure Time**, **Crowd Level**, **Notes**\n"
            "5. Click **Save Arrival**\n\n"
            "**Validation rules:**\n"
            "• No future arrival times\n"
            "• Departure must be after arrival\n"
            "• No duplicates within 5 minutes\n\n"
            "Your records improve predictions for everyone!"
        ), ['Go to Add Arrival', 'Validation rules', 'Why record data'], None, active_trip

    # ===== STATISTICS / HISTORICAL DATA =====
    if any(kw in msg_lower for kw in ['stat', 'statistic', 'data', 'export', 'history', 'average', 'trends']):
        return (
            "The **Historical Data** page shows all recorded arrivals with:\n\n"
            "• **Filterable table** - by route, location, date range\n"
            "• **Statistics** - total records, stops with data, avg travel times\n"
            "• **Export to CSV** - downloads filtered data\n\n"
            "Each arrival record helps improve the bus arrival predictions. "
            "The more data we have, the better the confidence!"
        ), ['Go to Historical Data', 'Export data', 'View statistics'], None, active_trip

    # ===== MANAGE LOCATIONS =====
    if any(kw in msg_lower for kw in ['location', 'stop', 'add stop', 'new stop', 'manage', 'route', 'add route']):
        return (
            "On **Manage Locations** you can:\n\n"
            "• **Add new stops** to existing routes (specify sequence order)\n"
            "• **Add new routes** with multiple stops\n"
            "• **Edit/Delete** existing locations\n"
            "• **Map stops to model vocabulary** for predictions\n\n"
            "Each stop needs a 'model stop' mapping so the ML model "
            "knows which training data to use for predictions."
        ), ['Go to Manage Locations', 'Add new route', 'Model mapping help'], None, active_trip

    # ===== CONTEXT FOLLOW-UP QUESTIONS =====
    if any(kw in msg_lower for kw in ['what if', 'later', 'earlier', '30 minutes', 'adjust', 'change']):
        return handle_followup_question(msg_lower, active_trip, context)

    # ===== GREETING / GENERAL =====
    if any(kw in msg_lower for kw in ['hi', 'hello', 'hey', 'konduktor', 'who', 'what']):
        return (
            "Hello! I'm **Konduktor**, your ByaHero assistant. 🚌\n\n"
            "I can help you with:\n"
            "• **Trip planning** - best times, routes, crowd levels\n"
            "• **Bus arrivals** - predictions, confidence, schedules\n"
            "• **Recording data** - how to log arrivals, validation\n"
            "• **Understanding predictions** - how the ML works\n"
            "• **Historical data** - stats, exports, analysis\n\n"
            "Try asking: *\"I want to go to Digos at 2 PM\"* or *\"When's the next bus at Binaton?\"*"
        ), ['Plan a trip', 'Next bus times', 'How predictions work', 'Record an arrival'], None, active_trip

    # ===== DEFAULT FALLBACK =====
    return (
        "I'm not sure I understand. Could you rephrase that?\n\n"
        "Try asking me about:\n"
        "• \"I want to go to Digos at 2 PM\"\n"
        "• \"When's the next bus at Binaton?\"\n"
        "• \"What if I leave 30 minutes later?\"\n"
        "• \"How do predictions work?\""
    ), ['Plan a trip', 'Next bus times', 'How predictions work', 'Record an arrival'], None, active_trip


def handle_trip_planning(msg_lower, msg_stripped, active_trip, context):
    """Handle trip planning requests with natural language understanding"""
    route_id = active_trip.get('route_id') or context.get('routeId')
    origin_id = active_trip.get('origin_id') or context.get('originId')
    destination_id = active_trip.get('destination_id') or context.get('destinationId')
    target_time = active_trip.get('target_time')

    # Parse user message for route, stops, and time
    if not route_id and ('kapatagan' in msg_lower or 'digos' in msg_lower):
        route_id = 1  # Default route
        active_trip['route_id'] = route_id

    # Check for origin mentions
    locations = data_manager.get_locations()
    for loc in locations:
        loc_name = loc['name'].lower()
        if loc_name in msg_lower:
            if 'from' in msg_lower.split(loc_name)[0] or 'boarding' in msg_lower.split(loc_name)[0]:
                active_trip['origin_id'] = loc['location_id']
                active_trip['origin_name'] = loc['name']
                origin_id = loc['location_id']
            elif 'to' in msg_lower.split(loc_name)[0] or 'going to' in msg_lower.split(loc_name)[0]:
                active_trip['destination_id'] = loc['location_id']
                active_trip['destination_name'] = loc['name']
                destination_id = loc['location_id']
            elif 'at' in msg_lower.split(loc_name)[0]:
                if not active_trip.get('origin_id'):
                    active_trip['origin_id'] = loc['location_id']
                    active_trip['origin_name'] = loc['name']
                    origin_id = loc['location_id']
                else:
                    active_trip['destination_id'] = loc['location_id']
                    active_trip['destination_name'] = loc['name']
                    destination_id = loc['location_id']

    # Parse time from message (must have AM/PM suffix or HH:MM format)
    time_match = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', msg_lower)
    if time_match:
        hour_str = time_match.group(1)
        minute_str = time_match.group(2) or '0'
        ampm = time_match.group(3)
        # Only accept if it looks like an actual time (has AM/PM or colon = HH:MM)
        has_ampm = ampm is not None
        has_colon = ':' in time_match.group(0)
        if not (has_ampm or has_colon):
            time_match = None  # Reject plain digit without time context
        else:
            hour = int(hour_str)
            minute = int(minute_str)
            if ampm == 'pm' and hour < 12:
                hour += 12
            if ampm == 'am' and hour == 12:
                hour = 0
            # Clamp to valid range
            hour = max(0, min(23, hour))
            minute = max(0, min(59, minute))
            target_time = f"{hour:02d}:{minute:02d}"
            active_trip['target_time'] = target_time
            # Determine if it's arrival or departure time
            prefix = msg_lower.split(time_match.group(0))[0][-15:]
            if any(w in prefix for w in ['by', 'at', 'arrive', 'reach']):
                active_trip['time_type'] = 'arrival'
            else:
                active_trip['time_type'] = 'departure'

    # Check if we have all required info
    if not origin_id:
        active_trip_names = ', '.join([loc['name'] for loc in locations[:5]])
        return (
            "Sure! I can help you plan a trip. Where will you be boarding the bus? "
            f"For example: {active_trip_names}. "
            "I'll estimate when you should wait for a bus so you can reach your destination on time."
        ), ['Plan a trip', 'Next bus times', 'How predictions work'], None, active_trip

    if not destination_id:
        if route_id:
            dest_stops = get_stops_after(route_id, origin_id)
            stop_names = _location_name_map()
            available_dests = [stop_names.get(sid) for sid in dest_stops if stop_names.get(sid)]
            if available_dests:
                return (
                    f"Got it, you're starting at **{active_trip.get('origin_name', 'your location')}**. "
                    f"Where are you heading? Available stops: {', '.join(available_dests)}"
                ), ['Plan a trip', 'Next bus times', 'How predictions work'], None, active_trip
        return (
            f"You're at **{active_trip.get('origin_name', 'your location')}**. "
            "Where are you going?"
        ), ['Plan a trip', 'Next bus times', 'How predictions work'], None, active_trip

    if not target_time:
        return (
            f"Great! You want to go from **{active_trip.get('origin_name')}** to **{active_trip.get('destination_name')}**. "
            "What time do you want to travel? (e.g., 2 PM, 14:00)"
        ), ['Plan a trip', 'Next bus times', 'How predictions work'], None, active_trip

    # We have all info - call trip planner API
    trip_data, response_text, plan, _ = generate_trip_recommendation(active_trip)
    return response_text, ['Recalculate trip', 'Next bus times', 'How predictions work'], plan, active_trip


def handle_next_bus_query(route_id, origin_id, msg_lower):
    """Handle queries about next bus arrival times"""
    predictor = refresh_arrival_predictor()
    prediction = predictor.predict_next_arrival(origin_id, route_id, "Medium")

    if not prediction.get('next_arrival'):
        return (
            f"I don't have enough data to predict the next bus at this stop. "
            "Try recording some arrivals to improve predictions!"
        ), ['Record an arrival', 'Plan a trip', 'Show all stops'], None

    location_name = get_location_by_id(origin_id)
    return (
        f"The next bus at **{location_name or 'your stop'}** is predicted to arrive at "
        f"**{prediction.get('next_arrival')}**.\n\n"
        f"Confidence: {prediction.get('confidence', 'Unknown')}\n"
        f"Status: {prediction.get('status', 'Unknown')}"
    ), ['Plan a trip', 'Show all stop times', 'Record arrival'], None


def handle_waiting_time_query(msg_lower, active_trip, context):
    """Handle queries about waiting times"""
    origin_id = active_trip.get('origin_id') or context.get('originId')
    route_id = active_trip.get('route_id') or context.get('routeId')

    if not origin_id or not route_id:
        return (
            "To check waiting times, I need to know which stop you're at and which route. "
            "Could you tell me your location?"
        ), ['Plan a trip', 'Next bus times', 'How predictions work'], None, active_trip

    predictor = refresh_arrival_predictor()
    prediction = predictor.predict_next_arrival(origin_id, route_id, "Medium")
    next_bus = prediction.get('next_arrival')

    if not next_bus:
        return (
            "I don't have enough historical data to predict when the next bus will arrive. "
            "Try recording some arrivals to help improve predictions!"
        ), ['Record an arrival', 'Plan a trip'], None, active_trip

    # Calculate wait time
    try:
        bus_dt = datetime.strptime(next_bus, '%H:%M')
        now_dt = datetime.now().replace(microsecond=0)
        # Use user's local time from context if available
        if context.get('tz_offset_minutes'):
            # Adjust for timezone
            from datetime import timedelta
            now_dt = now_dt + timedelta(minutes=context['tz_offset_minutes'])
        diff_minutes = (bus_dt - now_dt).total_seconds() / 60
        if diff_minutes < 0:
            diff_minutes += 24 * 60  # Handle midnight crossing

        location_name = get_location_by_id(origin_id)
        return (
            f"The next bus at **{location_name or 'your stop'}** arrives at **{next_bus}**. "
            f"That's approximately **{int(diff_minutes)} minutes** from now.\n\n"
            f"Confidence: {prediction.get('confidence', 'Unknown')}"
        ), ['Plan a trip', 'Show all stop times', 'Record arrival'], None, active_trip
    except Exception:
        return (
            f"The next bus is predicted at **{next_bus}**. "
            f"Confidence: {prediction.get('confidence', 'Unknown')}"
        ), ['Plan a trip', 'Show all stop times'], None, active_trip


def handle_followup_question(msg_lower, active_trip, context):
    """Handle follow-up questions like 'what if I leave 30 minutes later'"""
    # Extract time adjustment
    time_adjust = 0
    match = re.search(r'(\d+)\s*(minutes?|mins?|hours?)', msg_lower)
    if match:
        time_adjust = int(match.group(1))
        if 'hour' in match.group(2):
            time_adjust *= 60

    # Determine direction
    if any(kw in msg_lower for kw in ['later', 'delay', 'push']):
        time_adjust = abs(time_adjust)
    elif any(kw in msg_lower for kw in ['earlier', 'sooner', 'advance']):
        time_adjust = -abs(time_adjust)

    if active_trip.get('target_time') and time_adjust:
        try:
            from datetime import timedelta
            current_dt = datetime.strptime(active_trip['target_time'], '%H:%M')
            new_dt = current_dt + timedelta(minutes=time_adjust)
            new_time = new_dt.strftime('%H:%M')

            action = "leave" if active_trip.get('time_type') == 'departure' else "arrive"
            return (
                f"If you {action} at **{new_time}** instead of {active_trip['target_time']}, "
                f"here's what changes...\n\n"
                "Let me recalculate your trip plan with the new time."
            ), ['Recalculate trip', 'Show original plan', 'Adjust again'], None, active_trip
        except Exception:
            pass

    return (
        "I can adjust your trip plan! Tell me the new time or how many minutes to shift."
    ), ['Plan a trip', 'Show current plan', 'How predictions work'], None, active_trip


def generate_trip_recommendation(trip_data):
    """Generate a full trip recommendation using the trip-plan API"""
    route_id = trip_data.get('route_id')
    origin_id = trip_data.get('origin_id')
    destination_id = trip_data.get('destination_id')
    target_time = trip_data.get('target_time')

    # Convert target_time from HH:MM to model format like "2:00 PM"
    try:
        dt = datetime.strptime(target_time, '%H:%M')
        model_time = dt.strftime('%-I:%M %p')
    except (ValueError, TypeError):
        model_time = target_time

    if not all([route_id, origin_id, destination_id, model_time]):
        return None, "I need more information to plan your trip.", None, trip_data

    # Call the trip plan API
    try:
        payload = {
            'route': route_id,
            'origin': origin_id,
            'destination': destination_id,
            'time': model_time,
            'day': datetime.now().strftime('%A'),
            'crowd': 'Medium'
        }
        with app.test_client() as client:
            response = client.post('/api/trip-plan',
                                   data=json.dumps(payload),
                                   content_type='application/json')
            data = response.get_json()

        if data and data.get('success'):
            plan = data['trip_plan']
            commute = plan['commute']

            # Format response
            origin_name = trip_data.get('origin_name', get_location_by_id(origin_id))
            dest_name = trip_data.get('destination_name', get_location_by_id(destination_id))

            parts = [
                f"**Your Trip Plan: {origin_name} → {dest_name}**",
                "",
                f"🚌 **Travel Time:** {commute['travel_time']} minutes",
                f"🎯 **Recommendation:** {commute['decision'].replace('_', ' ').title()}",
            ]
            if commute.get('next_bus_time'):
                parts.append(f"⏰ **Next Bus:** {commute['next_bus_time']}")
            if commute.get('insights'):
                parts.append("")
                parts.append("**Insights:**")
                for insight in commute['insights']:
                    parts.append(f"• {insight}")
            response_text = "\n".join(parts)
            return trip_data, response_text, plan, trip_data
        else:
            err = data.get('error', 'Unknown error') if data else 'No response'
            return None, f"Error planning trip: {err}", None, trip_data
    except Exception as e:
        print(f"Trip plan error: {e}")
        # Fallback: provide a human-readable message with available data
        origin_name = trip_data.get('origin_name', get_location_by_id(origin_id))
        dest_name = trip_data.get('destination_name', get_location_by_id(destination_id))
        return trip_data, (
            f"🗺️ **Trip: {origin_name} → {dest_name}**\n\n"
            f"⏰ **Target Time:** {target_time}\n"
            f"ℹ️ To see the full prediction with travel time and bus schedule, "
            f"please use the Trip Planner page directly."
        ), None, trip_data


def get_konduktor_system_prompt(context):
    """Build the full system prompt for LLM"""

    # 1. Base IDENTITY and STYLE (from user provided prompt)
    base_prompt = """# SYSTEM PROMPT: Helpful, Intelligent, Human-Like AI Assistant

## ROLE AND IDENTITY
You are Konduktor, an advanced AI assistant designed to help users with the ByaHero bus system in Digos City. Communicate naturally and intelligently.

Your goal is not merely to answer questions, but to understand the user intent and provide the most useful response possible.

## 1. COMMUNICATION STYLE
- Speak naturally, clearly, and conversationally.
- Be friendly, respectful, patient, and professional.
- Match the user language, tone, and level of understanding.
- Explain complicated concepts using simple words and relatable examples.
- Avoid unnecessary introductions, repetitive conclusions, and filler.
- Use headings, bullet points, and code blocks when they improve readability.

## 2. UNDERSTAND BEFORE ANSWERING
- Identify what the user actually wants, even with typos or informal language.
- Use context to avoid asking for information the user already provided.
- Remember details throughout the conversation (starting point, destination, time).

## 3. REASONING AND PROBLEM-SOLVING
- Analyze complex problems systematically.
- Distinguish facts, assumptions, and estimates.
- Admit uncertainty when information is incomplete.
- Never invent facts, sources, or results.
- When data is insufficient, clearly state that estimates are uncertain.

## 4. ByaHero SPECIFIC KNOWLEDGE
You are the expert on ByaHero, a mini-bus predictor for Digos City.
- Route: Currently focused on Kapatagan to Digos Terminal.
- Stops: Kapatagan, Soong, Binaton, Digos Terminal.
- Prediction: Uses a Random Forest ML model for travel time and statistical analysis for bus arrivals.
- Crowd Levels: Low (Comfortable), Medium (Normal), High (Standing room only/Delays).
- Validation: Future arrivals are not allowed; departures must be after arrivals.
- Weather Integration: Weather can affect travel times. Rain, thunderstorms, and heavy precipitation typically add 15-40% to travel time. When users ask about weather, check the /api/weather endpoint and reference actual conditions, but never invent delays or claim weather directly confirms a bus delay.

## 5. TRIP PLANNING CAPABILITIES
When users ask about trips:
- Understand natural language: "I want to go to Digos at 2 PM"
- Extract: destination, desired time, starting location
- Recommend: best waiting time, predicted arrival, departure time
- Support follow-ups: "What if I leave 30 minutes later?"
- Always distinguish predicted from confirmed arrivals
- Explain uncertainty when data is limited
"""

    # 2. Inject Current DATA CONTEXT
    data_context = f"""
## CURRENT DATA CONTEXT
- Page: {context.get('currentPage', '/')}
- Selected Route ID: {context.get('routeId', 'None')}
- Selected Origin ID: {context.get('originId', 'None')}
- Selected Destination ID: {context.get('destinationId', 'None')}
"""

    if context.get('lastTripPlan'):
        tp = context['lastTripPlan']
        data_context += f"- Last Trip Plan Result: Travel time {tp['commute']['travel_time']}m, Decision: {tp['commute']['decision']}\n"

    # 3. CORE PRINCIPLE (from user provided prompt)
    footer = """
## CORE PRINCIPLE
Be helpful without being blindly agreeable, intelligent without being condescending, detailed without being overwhelming, and conversational without sacrificing accuracy.

Prioritize usefulness, honesty, clarity, adaptability, and respect in every interaction.
"""

    return base_prompt + data_context + footer


# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found(error):
    """Return JSON for API calls, HTML for page navigations."""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    # The error page never shows the splash, so it does not use up the
    # session's one splash either.
    return render_template('error.html', code=404,
                           message="We couldn't find that page.",
                           show_splash=False), 404


@app.errorhandler(500)
def internal_error(error):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('error.html', code=500,
                           message="Something went wrong on our end.",
                           show_splash=False), 500


# ============ MAIN ============

if __name__ == '__main__':
    refresh_arrival_predictor(force=True)
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        port=int(os.environ.get("PORT", "3000")),
        host="0.0.0.0")

# ============ MAIN ============
