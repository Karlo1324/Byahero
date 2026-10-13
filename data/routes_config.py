"""
Route Configuration for ByaHero
Defines the sequence of stops for each bus route
"""

ROUTES = {
    1: {
        "id": 1,
        "name": "Kapatagan to Digos",
        "description": "Main route from Kapatagan through intermediate stops to Digos Terminal",
        "stops": [1, 2, 3, 4],  # location_ids in order: Kapatagan -> Soong -> Binaton -> Digos Terminal
        "active": True
    }
}

def get_route_stops(route_id):
    """Returns the sequence of stop location_ids for a given route"""
    if route_id in ROUTES:
        return ROUTES[route_id]["stops"]
    return []

def get_stops_after(route_id, current_stop_id):
    """
    Returns stops that come after the current stop in the route sequence.
    Useful for destination selection (can't go backwards).
    """
    route_stops = get_route_stops(route_id)
    if current_stop_id in route_stops:
        idx = route_stops.index(current_stop_id)
        return route_stops[idx + 1:]
    return []

def get_all_routes():
    """Returns all active routes"""
    return {k: v for k, v in ROUTES.items() if v["active"]}
