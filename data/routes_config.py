"""
Route Configuration for ByaHero
Defines the sequence of stops for each bus route

Routes live in data/routes.csv so a route can be added from the app
instead of being hardcoded here. The registry is read on every call, so a
route added in one session is visible to the next one.
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# On Vercel, the filesystem is read-only except for /tmp
if os.environ.get('VERCEL') == '1':
    DATA_DIR = '/tmp/data'
else:
    DATA_DIR = os.path.join(BASE_DIR, "data")
UTILS_DIR = os.path.join(BASE_DIR, "utils")

for _path in (UTILS_DIR, DATA_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from data_manager import data_manager  # noqa: E402


ROUTE_COLUMNS = [
    'route_id', 'name', 'description', 'model_route', 'model_stops',
    'model_stops_default', 'stops', 'active',
]

ROUTES_FILE = "routes.csv"

# The route the app shipped with. It is written to the registry the first
# time an empty one is found, so the seeded data and the old hardcoded
# definition stay in one place.
SEED_ROUTES = [
    {
        "id": 1,
        "name": "Kapatagan to Digos",
        "description": "Main route from Kapatagan through intermediate stops to Digos Terminal",
        "model_route": "Barangay Kapatagan-Digos Terminal",
        # Soong and Binaton are intermediate stops the model never saw, so
        # they collapse onto the route's boarding point.
        "model_stops": {
            1: "Barangay Kapatagan",
            2: "Barangay Kapatagan",
            3: "Barangay Kapatagan",
            4: "Digos Terminal",
        },
        "model_stops_default": "Barangay Kapatagan",
        "stops": [1, 2, 3, 4],
        "active": True,
    }
]

# The route and stop labels the trained model understands. The encoders
# only know the routes and stops the model was fitted on, so a new route
# has to borrow one of them.
_MODEL_ROUTES = []
_MODEL_STOPS = []


def set_model_vocabulary(routes, stops):
    """
    Record the route and stop labels the trained model was fitted on.

    The app calls this once at start-up with the encoders loaded from
    model.pkl, so the route form can only offer labels the model accepts.
    """
    global _MODEL_ROUTES, _MODEL_STOPS
    _MODEL_ROUTES = list(routes or [])
    _MODEL_STOPS = list(stops or [])


def get_known_model_routes():
    """The route labels the trained model understands."""
    return list(_MODEL_ROUTES)


def get_known_model_stops():
    """The stop labels the trained model understands."""
    return list(_MODEL_STOPS)


# ============ SERIALISATION ============

def _serialize_stops(stops):
    """Turn a list of location ids into the comma separated cell."""
    return ",".join(str(int(s)) for s in stops)


def _deserialize_stops(text):
    """Turn the comma separated cell back into a list of location ids."""
    stops = []
    for part in str(text or "").split(","):
        part = part.strip()
        if part.isdigit():
            stops.append(int(part))
    return stops


def _serialize_model_stops(mapping):
    """Turn a location_id -> model stop mapping into a JSON cell."""
    return json.dumps({str(k): v for k, v in (mapping or {}).items()})


def _deserialize_model_stops(text):
    """Turn the JSON cell back into a location_id -> model stop mapping."""
    try:
        raw = json.loads(text or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}

    mapping = {}
    for key, value in raw.items():
        try:
            mapping[int(key)] = value
        except (TypeError, ValueError):
            continue
    return mapping


def _row_to_route(row):
    """Turn a registry row into the route dict the rest of the app uses."""
    try:
        route_id = int(row['route_id'])
    except (TypeError, ValueError, KeyError):
        return None

    name = str(row.get('name') or '').strip()
    if not name:
        return None

    return {
        "id": route_id,
        "name": name,
        "description": str(row.get('description') or ''),
        "model_route": str(row.get('model_route') or ''),
        "model_stops": _deserialize_model_stops(row.get('model_stops')),
        "model_stops_default": str(row.get('model_stops_default') or ''),
        "stops": _deserialize_stops(row.get('stops')),
        "active": str(row.get('active') or '').strip().lower() in ('true', '1', 'yes'),
    }


def _route_to_row(route):
    """Turn a route dict into a registry row."""
    return {
        'route_id': route["id"],
        'name': route["name"],
        'description': route.get('description') or '',
        'model_route': route.get('model_route') or '',
        'model_stops': _serialize_model_stops(route.get('model_stops')),
        'model_stops_default': route.get('model_stops_default') or '',
        'stops': _serialize_stops(route.get('stops') or []),
        'active': 'true' if route.get('active', True) else 'false',
    }


# ============ REGISTRY ============

def _read_rows():
    """Every row in the route registry."""
    return data_manager.read_rows(ROUTES_FILE, ROUTE_COLUMNS)


def _write_rows(rows):
    """Replace the route registry with the given rows."""
    data_manager.write_rows(ROUTES_FILE, rows, ROUTE_COLUMNS)


def get_route_file():
    """Path of the route registry file."""
    return data_manager.data_dir / ROUTES_FILE


def _load_routes():
    """Every route in the registry, keyed by route id."""
    routes = {}
    for row in _read_rows():
        route = _row_to_route(row)
        if route:
            routes[route["id"]] = route
    return routes


def _ensure_seeded():
    """
    Write the seed routes when the registry has none.

    There is no delete-route feature, so an empty registry only happens
    on a fresh checkout (or if the file was emptied by hand). Writing the
    seed back keeps the app usable instead of leaving it route-less.
    """
    rows = _read_rows()
    if rows:
        return
    _write_rows([_route_to_row(route) for route in SEED_ROUTES])


# ============ PUBLIC API ============

def get_all_routes():
    """Returns all active routes"""
    _ensure_seeded()
    return {k: v for k, v in _load_routes().items() if v["active"]}


def get_route(route_id):
    """Returns a single route, or None when it is unknown."""
    _ensure_seeded()
    routes = _load_routes()
    route = routes.get(route_id)
    if route is None:
        # A route id may arrive as a string from a query parameter.
        try:
            route = routes.get(int(route_id))
        except (TypeError, ValueError):
            route = None
    return route


def get_route_stops(route_id):
    """Returns the sequence of stop location_ids for a given route"""
    route = get_route(route_id)
    if route:
        return list(route["stops"])
    return []


def resolve_route_id(route_label):
    """
    Resolve anything the UI might send as a route identifier into a route_id.

    Accepts the route_id (as int or string), the human readable route name, or
    the name the model was trained on. Returns None when nothing matches.
    """
    if route_label is None:
        return None

    text = str(route_label).strip()
    if not text:
        return None

    _ensure_seeded()
    routes = _load_routes()

    if text.isdigit():
        route_id = int(text)
        return route_id if route_id in routes else None

    for route_id, route in routes.items():
        if text in (route["name"], route.get("model_route")):
            return route_id
    return None


def get_model_route_name(route_label):
    """
    Translate a route id, a human-readable route label, or a model route name
    into the route name the trained model was fitted on. Returns the input
    unchanged when it is already a known model route name.
    """
    route_id = resolve_route_id(route_label)
    if route_id is not None:
        route = _load_routes()[route_id]
        return route.get("model_route") or route["name"]
    return route_label


def get_model_stop_name(route_id, location_id=None, fallback_name=None):
    """
    Translate a location (by id, or by name as a fallback) into the stop label
    the trained model understands for the given route.

    The model's stop vocabulary is much smaller than the app's stop registry,
    so this mapping is explicit and per-route rather than guessed.
    """
    route = get_route(route_id)
    if not route:
        return fallback_name

    mapping = route.get("model_stops", {})
    if location_id is not None:
        try:
            location_id = int(location_id)
        except (TypeError, ValueError):
            location_id = None
        if location_id in mapping:
            return mapping[location_id]

    if fallback_name in mapping.values():
        return fallback_name

    return route.get("model_stops_default") or fallback_name


def get_stops_after(route_id, current_stop_id):
    """
    Returns all stops on the route EXCEPT the current stop.
    Previously only returned stops AFTER the current one, which
    prevented reverse trips (e.g. Digos → Kapatagan).
    """
    route_stops = get_route_stops(route_id)
    try:
        current_stop_id = int(current_stop_id)
    except (TypeError, ValueError):
        return []
    if current_stop_id in route_stops:
        return [s for s in route_stops if s != current_stop_id]
    return []


def add_route(name, description, model_route, stops):
    """
    Create a new route and register its stops as locations on it.

    `stops` is a list of dicts with a "name" and a "model_stop": the label
    the trained model uses for that stop. The stops become locations on the
    new route, numbered in the order given.

    Returns a dict with "success"; on failure it carries an "error".
    """
    name = str(name or "").strip()
    if not name:
        return {"success": False, "error": "Route name cannot be empty"}

    _ensure_seeded()
    routes = _load_routes()

    if any(r["name"].lower() == name.lower() for r in routes.values()):
        return {"success": False, "error": f"A route named '{name}' already exists"}

    known_routes = get_known_model_routes()
    if known_routes and model_route not in known_routes:
        return {
            "success": False,
            "error": "The prediction basis must be one of: "
                     + ", ".join(known_routes)
        }

    prepared = []
    for stop in stops or []:
        stop_name = str(stop.get('name') or '').strip()
        model_stop = str(stop.get('model_stop') or '').strip()
        if not stop_name or not model_stop:
            return {"success": False, "error": "Every stop needs a name and a prediction basis"}
        prepared.append({"name": stop_name, "model_stop": model_stop})

    if len(prepared) < 2:
        return {"success": False, "error": "A route needs at least two stops"}

    route_id = max(routes.keys()) + 1 if routes else 1

    # The route is written first so the locations created next always point
    # at a route that exists.
    route = {
        "id": route_id,
        "name": name,
        "description": str(description or '').strip(),
        "model_route": model_route,
        "model_stops": {},
        "model_stops_default": prepared[0]["model_stop"],
        "stops": [],
        "active": True,
    }
    rows = [_route_to_row(r) for r in routes.values()]
    rows.append(_route_to_row(route))
    _write_rows(rows)

    result = data_manager.add_locations(route_id, prepared)
    if not result.get("success"):
        # Roll the route back, so a failed attempt does not leave a route
        # behind that has no stops.
        _write_rows([_route_to_row(r) for r in routes.values()])
        return {"success": False, "error": result.get("error", "Could not add the stops")}

    stop_ids = []
    model_stops = {}
    for location in result["locations"]:
        stop_ids.append(location["location_id"])
        model_stops[location["location_id"]] = location["model_stop"]

    route["stops"] = stop_ids
    route["model_stops"] = model_stops
    route["model_stops_default"] = prepared[0]["model_stop"]

    rows = [_route_to_row(r) for r in routes.values()]
    rows.append(_route_to_row(route))
    _write_rows(rows)

    return {
        "success": True,
        "route_id": route_id,
        "route": route,
        "message": f"Route '{name}' added successfully"
    }
