"""
ByaHero - Smart Commute Predictor
Flask application with commute prediction and bus arrival tracking
"""

from flask import (Flask, render_template, request, jsonify, session, Response,
                   redirect, url_for)
import pickle
import numpy as np
import pandas as pd
import secrets
import sys
import os
from datetime import datetime

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

# Import arrival predictor v2 for improved predictions
try:
    from arrival_predictor_v2 import ArrivalPredictor as ArrivalPredictorV2
    PREDICTOR_V2_AVAILABLE = True
except ImportError:
    PREDICTOR_V2_AVAILABLE = False

app = Flask(__name__)

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
    """Commute prediction page"""
    locations = data_manager.get_locations()
    routes = get_all_routes()

    # Get dropdown options from data
    commute_df = pd.read_csv(COMMUTE_FILE)
    times = sorted(commute_df['time'].unique().tolist())
    days = sorted(commute_df['day'].unique().tolist())
    crowds = ["Low", "Medium", "High"]

    return render_template('index.html',
                           locations=locations,
                           routes=routes,
                           times=times,
                           days=days,
                           crowds=crowds,
                           show_splash=_wants_splash())


@app.route('/bus-arrivals')
def bus_arrivals():
    """View bus arrival predictions"""
    locations = data_manager.get_locations()
    routes = get_all_routes()

    return render_template('bus_arrivals.html',
                           locations=locations,
                           routes=routes,
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
    app.run(debug=True, port=3000)
