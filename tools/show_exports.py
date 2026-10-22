"""Print the CSV exports so the output can be eyeballed.

Run with: python3 tools/show_exports.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402

client = app_module.app.test_client()

print("=== /export/arrivals.csv ===")
print(client.get('/export/arrivals.csv').get_data(as_text=True))

print("=== /export/locations.csv ===")
print(client.get('/export/locations.csv').get_data(as_text=True))

print("=== /export/arrivals.csv?route_id=1&location_id=3 ===")
print(client.get('/export/arrivals.csv?route_id=1&location_id=3').get_data(as_text=True))
