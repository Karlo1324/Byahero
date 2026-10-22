"""Smoke tests for the ByaHero app. Run with: python3 smoke_test.py

The tests write to the real CSV data files, so the originals are captured
before the run and restored afterwards -- the working tree is left untouched.
"""
import json
import shutil
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as app_module  # noqa: E402

FAILURES = []

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILES = [
    os.path.join(ROOT, 'data', 'bus_arrivals.csv'),
    os.path.join(ROOT, 'data', 'locations.csv'),
    os.path.join(ROOT, 'data', 'routes.csv'),
]

# The data manager keeps a .bak copy of every file it writes. Those are
# restored (or removed) alongside the originals so a test run leaves the
# working tree exactly as it found it.
BACKUP_FILES = [path + '.bak' for path in DATA_FILES]


def snapshot_data():
    """Copy the data files aside so they can be restored after the run."""
    backup = tempfile.mkdtemp(prefix='byahero-smoke-')
    for path in DATA_FILES + BACKUP_FILES:
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(backup, os.path.basename(path)))
    return backup


def restore_data(backup):
    """Put the original data files back."""
    for path in DATA_FILES + BACKUP_FILES:
        saved = os.path.join(backup, os.path.basename(path))
        if os.path.exists(saved):
            shutil.copy2(saved, path)
        elif path in BACKUP_FILES:
            # There was no backup before the run, so the one the test created
            # has to go away again.
            if os.path.exists(path):
                os.remove(path)
        else:
            # The file did not exist before the run (the route registry is
            # created on first use), so it has to go away again too.
            if os.path.exists(path):
                os.remove(path)
    shutil.rmtree(backup, ignore_errors=True)


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def to_min(t):
    h, m = str(t).split(':')[:2]
    return int(h) * 60 + int(m)


def main():
    c = app_module.app.test_client()

    # --- pages render ---
    for path in ['/', '/bus-arrivals', '/add-arrival', '/manage-locations',
                 '/historical-data']:
        r = c.get(path)
        check(f"page {path} renders", r.status_code == 200, str(r.status_code))

    # --- 404 page ---
    r = c.get('/does-not-exist')
    check("404 page renders", r.status_code == 404)

    # --- prediction: route as id ---
    r = c.post('/api/predict', json={
        'route': '1', 'origin': '1', 'stop': 'Digos Terminal',
        'time': '3:00 PM', 'day': 'Saturday', 'crowd': 'Low'})
    body = r.get_json()
    check("predict with route id", r.status_code == 200 and body.get('success'),
          json.dumps(body))
    check("predict returns travel time", isinstance(body.get('travel_time'), (int, float)),
          json.dumps(body))

    # --- prediction: origin as int ---
    r = c.post('/api/predict', json={
        'route': 1, 'origin': 1, 'stop': 'Digos Terminal',
        'time': '3:00 PM', 'day': 'Saturday', 'crowd': 'Low'})
    check("predict with int route/origin", r.get_json().get('success'),
          json.dumps(r.get_json()))

    # --- prediction: intermediate stop origin ---
    r = c.post('/api/predict', json={
        'route': '1', 'origin': '2', 'stop': 'Binaton',
        'time': '3:00 PM', 'day': 'Saturday', 'crowd': 'Low'})
    check("predict from intermediate stop", r.get_json().get('success'),
          json.dumps(r.get_json()))

    # --- prediction: missing field ---
    r = c.post('/api/predict', json={'route': '1'})
    check("predict rejects missing fields", r.status_code == 400)

    # --- prediction: unknown route ---
    r = c.post('/api/predict', json={
        'route': '999', 'origin': '1', 'stop': 'Digos Terminal',
        'time': '3:00 PM', 'day': 'Saturday', 'crowd': 'Low'})
    check("predict rejects unknown route", r.status_code == 400)

    # --- stops after ---
    r = c.get('/api/get-stops-after?route_id=1&stop_id=1')
    data = r.get_json()
    check("stops-after returns 3 stops", len(data.get('stops', [])) == 3, json.dumps(data))
    check("stops-after names resolved",
          bool(data.get('stops')) and data['stops'][0]['name'] == 'Soong',
          json.dumps(data))

    # --- locations ---
    r = c.get('/api/get-locations?route_id=1')
    check("locations for route", len(r.get_json().get('locations', [])) == 4)

    # --- arrivals json validity (NaN regression) ---
    r = c.get('/api/get-arrivals?limit=1000')
    raw = r.get_data(as_text=True)
    check("arrivals payload has no NaN", 'NaN' not in raw)
    try:
        json.loads(raw)
        valid_json = True
    except Exception:
        valid_json = False
    check("arrivals payload is valid JSON", valid_json)

    # --- add arrival (was NameError) ---
    r = c.post('/api/add-arrival-record', json={
        'route_id': 1, 'location_id': 2, 'arrival_time': '09:00',
        'arrival_date': '2026-10-13', 'departure_time': None,
        'crowd_level': 'Low', 'notes': ''})
    check("add arrival succeeds", r.get_json().get('success'),
          json.dumps(r.get_json()))

    # --- arrival record with empty optional fields must not emit NaN ---
    r = c.get('/api/get-arrivals?limit=1000')
    raw = r.get_data(as_text=True)
    check("arrivals still valid after insert", 'NaN' not in raw)

    # --- predict arrival ---
    r = c.post('/api/predict-arrival', json={'route_id': 1, 'location_id': 2})
    body = r.get_json()
    check("predict-arrival succeeds", body.get('success'), json.dumps(body))
    pred = body.get('prediction', {})
    check("predict-arrival gives next arrival", bool(pred.get('next_arrival')),
          json.dumps(pred))
    check("predict-arrival gives last arrival", bool(pred.get('last_arrival')),
          json.dumps(pred))

    # --- next arrival must come after the last arrival ---
    if pred.get('next_arrival') and pred.get('last_arrival'):
        check("next arrival is after last arrival",
              to_min(pred['next_arrival']) > to_min(pred['last_arrival']),
              f"{pred['last_arrival']} -> {pred['next_arrival']}")

    # --- validation: future arrival rejected ---
    r = c.post('/api/add-arrival-record', json={
        'route_id': 1, 'location_id': 3, 'arrival_time': '10:00',
        'arrival_date': '2099-01-01', 'crowd_level': 'Low'})
    check("future arrival rejected", r.status_code == 400, json.dumps(r.get_json()))

    # --- validation: departure after arrival rejected ---
    r = c.post('/api/add-arrival-record', json={
        'route_id': 1, 'location_id': 3, 'arrival_time': '10:00',
        'arrival_date': '2026-10-13', 'departure_time': '11:00',
        'crowd_level': 'Low'})
    check("departure after arrival rejected", r.status_code == 400,
          json.dumps(r.get_json()))

    # --- add location ---
    r = c.post('/api/add-location', json={
        'route_id': 1, 'name': 'Test Smoke Stop', 'stop_sequence': 9,
        'description': 'temp', 'active': True})
    check("add location succeeds", r.get_json().get('success'),
          json.dumps(r.get_json()))

    # --- duplicate location rejected ---
    r = c.post('/api/add-location', json={
        'route_id': 1, 'name': 'Test Smoke Stop', 'stop_sequence': 10,
        'description': 'temp', 'active': True})
    check("duplicate location rejected", r.get_json().get('success') is False,
          json.dumps(r.get_json()))

    # --- statistics ---
    r = c.get('/api/get-statistics?location_id=2')
    check("statistics endpoint", r.get_json().get('success'), json.dumps(r.get_json()))

    # ============ SPLASH SCREEN ============
    # The splash belongs to opening the app, not to every panel.

    splash_client = app_module.app.test_client()
    r = splash_client.get('/')
    check("splash shows on first open", b'splashScreen' in r.data)

    r = splash_client.get('/bus-arrivals')
    check("no splash on next panel", b'splashScreen' not in r.data)

    r = splash_client.get('/historical-data')
    check("no splash on later panel", b'splashScreen' not in r.data)

    r = splash_client.get('/manage-locations')
    check("no splash on later panel", b'splashScreen' not in r.data)

    # A fresh session is a fresh open of the app.
    fresh_client = app_module.app.test_client()
    r = fresh_client.get('/')
    check("splash shows for a new session", b'splashScreen' in r.data)

    # The replay link brings the splash back on request.
    r = splash_client.get('/restart-splash')
    check("restart-splash redirects", r.status_code in (302, 303), str(r.status_code))
    r = splash_client.get('/')
    check("splash replays after restart", b'splashScreen' in r.data)

    # ============ ADD ROUTE ============

    # The routes the trained model was fitted on. A new route has to borrow
    # one of them, so the tests use them as the prediction basis.
    model_routes = list(app_module.encoders['route'].classes_)
    model_stops = list(app_module.encoders['stop'].classes_)

    r = c.get('/api/get-routes')
    body = r.get_json()
    check("get-routes succeeds", body.get('success'), json.dumps(body))
    check("get-routes lists the seeded route", '1' in body.get('routes', {}),
          json.dumps(body))

    # A new route with its stops.
    r = c.post('/api/add-route', json={
        'name': 'Smoke Test Route',
        'description': 'temp',
        'model_route': model_routes[0],
        'stops': ['Smoke Origin', 'Smoke Destination'],
        'model_stops': {0: model_stops[0], 1: model_stops[-1]}})
    body = r.get_json()
    check("add route succeeds", body.get('success'), json.dumps(body))
    new_route_id = body.get('route_id')

    # The route is usable straight away.
    r = c.get('/api/get-routes')
    routes = r.get_json().get('routes', {})
    check("new route is listed", str(new_route_id) in routes, json.dumps(routes))
    check("new route has its stops",
          len(routes.get(str(new_route_id), {}).get('stops', [])) == 2,
          json.dumps(routes.get(str(new_route_id), {})))

    r = c.get(f'/api/get-locations?route_id={new_route_id}')
    locations = r.get_json().get('locations', [])
    check("new route has its locations", len(locations) == 2, json.dumps(locations))
    check("new route stops are numbered in order",
          [loc['stop_sequence'] for loc in locations] == [1, 2],
          json.dumps(locations))

    # A prediction on the new route has to work: the model vocabulary is
    # what the route was built on.
    r = c.post('/api/predict', json={
        'route': str(new_route_id), 'origin': str(locations[0]['location_id']),
        'stop': locations[1]['name'], 'time': '3:00 PM', 'day': 'Saturday',
        'crowd': 'Low'})
    body = r.get_json()
    check("predict works on a new route", body.get('success'), json.dumps(body))

    # The stops of a new route are ordered, so a destination that is not
    # on the route after the origin is rejected.
    r = c.post('/api/predict', json={
        'route': str(new_route_id), 'origin': str(locations[0]['location_id']),
        'stop': 'Kapatagan', 'time': '3:00 PM', 'day': 'Saturday',
        'crowd': 'Low'})
    check("new route rejects a destination that is not on it",
          r.get_json().get('success') is False, json.dumps(r.get_json()))

    # Duplicate route name.
    r = c.post('/api/add-route', json={
        'name': 'Smoke Test Route', 'model_route': model_routes[0],
        'stops': ['A', 'B'], 'model_stops': {0: model_stops[0], 1: model_stops[0]}})
    check("duplicate route rejected", r.get_json().get('success') is False,
          json.dumps(r.get_json()))

    # A route with a single stop is not a route.
    r = c.post('/api/add-route', json={
        'name': 'Too Short Route', 'model_route': model_routes[0],
        'stops': ['Only One'], 'model_stops': {0: model_stops[0]}})
    check("route with one stop rejected", r.get_json().get('success') is False,
          json.dumps(r.get_json()))

    # A prediction basis the model does not know is refused.
    r = c.post('/api/add-route', json={
        'name': 'Unknown Basis Route', 'model_route': 'Not A Real Route',
        'stops': ['A', 'B'], 'model_stops': {0: model_stops[0], 1: model_stops[0]}})
    check("unknown prediction basis rejected",
          r.get_json().get('success') is False, json.dumps(r.get_json()))

    # A stop without a prediction basis is refused.
    r = c.post('/api/add-route', json={
        'name': 'No Basis Route', 'model_route': model_routes[0],
        'stops': ['A', 'B'], 'model_stops': {0: model_stops[0]}})
    check("stop without a prediction basis rejected",
          r.get_json().get('success') is False, json.dumps(r.get_json()))

    # The route survives a restart of the app.
    reloaded = app_module.get_all_routes()
    check("new route survives a reload", new_route_id in reloaded,
          json.dumps(list(reloaded.keys())))

    # ============ CSV EXPORT ============

    r = c.get('/export/arrivals.csv')
    check("export arrivals returns 200", r.status_code == 200, str(r.status_code))
    check("export arrivals is a csv attachment",
          'text/csv' in (r.headers.get('Content-Type') or '') and
          'attachment' in (r.headers.get('Content-Disposition') or ''),
          str(r.headers))

    body = r.get_data(as_text=True)
    check("export arrivals has a header",
          body.splitlines()[0].startswith('arrival_id,'), body[:120])
    check("export arrivals includes location names",
          'location_name' in body.splitlines()[0], body[:120])
    check("export arrivals has rows", len(body.strip().splitlines()) > 1, body[:200])

    r = c.get('/export/locations.csv')
    check("export locations returns 200", r.status_code == 200, str(r.status_code))
    body = r.get_data(as_text=True)
    check("export locations has a header",
          body.splitlines()[0].startswith('location_id,'), body[:120])
    check("export locations lists the known stops",
          'Kapatagan' in body, body[:200])

    # The export honours the filters the Historical Data page offers.
    r = c.get('/export/arrivals.csv?route_id=999')
    body = r.get_data(as_text=True)
    check("export honours filters", len(body.strip().splitlines()) == 1, body[:200])

    r = c.get('/api/export-preview')
    body = r.get_json()
    check("export preview returns a count",
          body.get('success') and isinstance(body.get('count'), int),
          json.dumps(body))

    # ============ DATA PERSISTENCE ============

    # A record added now has to still be there on the next read.
    before = len(c.get('/api/get-arrivals?limit=1000').get_json()['arrivals'])
    r = c.post('/api/add-arrival-record', json={
        'route_id': 1, 'location_id': 4, 'arrival_time': '11:15',
        'arrival_date': '2026-10-13', 'departure_time': '11:00',
        'crowd_level': 'High', 'notes': 'Persistence check'})
    check("persist: record added", r.get_json().get('success'), json.dumps(r.get_json()))

    after = c.get('/api/get-arrivals?limit=1000').get_json()['arrivals']
    check("persist: record survives the round trip", len(after) == before + 1,
          f"{before} -> {len(after)}")
    check("persist: the new record is the one that was saved",
          any(a.get('notes') == 'Persistence check' for a in after),
          json.dumps(after[:2]))

    # A fresh DataManager must read the same records back from disk.
    reopened = app_module.data_manager.__class__()
    check("persist: records readable from a new manager",
          len(reopened.get_arrivals(limit=1000)) == len(after),
          f"{len(reopened.get_arrivals(limit=1000))} vs {len(after)}")

    # An empty main file must not wipe out the records.
    arrivals_file = os.path.join(ROOT, 'data', 'bus_arrivals.csv')
    with open(arrivals_file, 'r', encoding='utf-8') as fh:
        saved = fh.read()
    try:
        with open(arrivals_file, 'w', encoding='utf-8') as fh:
            fh.write('arrival_id,route_id,location_id,arrival_time,arrival_date,'
                     'departure_time,crowd_level,notes,recorded_at\n')
        recovered = app_module.data_manager.__class__().get_arrivals(limit=1000)
        check("persist: records recovered from the backup",
              len(recovered) == len(after), f"{len(recovered)} vs {len(after)}")
    finally:
        with open(arrivals_file, 'w', encoding='utf-8') as fh:
            fh.write(saved)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): " + ", ".join(FAILURES))
        return 1
    print("All checks passed.")
    return 0


if __name__ == '__main__':
    backup = snapshot_data()
    try:
        sys.exit(main())
    finally:
        restore_data(backup)
