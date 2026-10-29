"""
SQLite Database Manager for ByaHero
Provides thread-safe atomic database storage and CSV synchronization.
"""

import json
import os
import sqlite3
from pathlib import Path
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# On Vercel, the filesystem is read-only except for /tmp
# Use /tmp for writable data files in serverless environment
if os.environ.get('VERCEL') == '1':
    DATA_DIR = '/tmp/data'
else:
    DATA_DIR = os.path.join(BASE_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'byahero.db')

def get_db_connection():
    """Get a row-factory SQLite connection."""
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables and sync initial data from CSV if database is empty."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            location_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            route_id INTEGER NOT NULL,
            stop_sequence INTEGER NOT NULL,
            active TEXT DEFAULT 'true'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bus_arrivals (
            arrival_id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            arrival_time TEXT NOT NULL,
            arrival_date TEXT NOT NULL,
            departure_time TEXT,
            crowd_level TEXT DEFAULT 'Medium',
            notes TEXT,
            recorded_at TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bus_locations (
            bus_id TEXT PRIMARY KEY,
            route_id INTEGER NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            speed REAL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    ''')

    conn.commit()

    # Populate from CSV if tables are empty
    cursor.execute("SELECT COUNT(*) FROM locations")
    if cursor.fetchone()[0] == 0:
        csv_locations = os.path.join(DATA_DIR, "locations.csv")
        if os.path.exists(csv_locations):
            try:
                df = pd.read_csv(csv_locations)
                for _, row in df.iterrows():
                    cursor.execute('''
                        INSERT OR REPLACE INTO locations (location_id, name, description, route_id, stop_sequence, active)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        int(row['location_id']),
                        str(row['name']),
                        str(row.get('description', '') or ''),
                        int(row['route_id']),
                        int(row['stop_sequence']),
                        str(row.get('active', 'true')).lower()
                    ))
                conn.commit()
            except Exception as e:
                print(f"Error seeding locations from CSV: {e}")

    cursor.execute("SELECT COUNT(*) FROM bus_arrivals")
    if cursor.fetchone()[0] == 0:
        csv_arrivals = os.path.join(DATA_DIR, "bus_arrivals.csv")
        if os.path.exists(csv_arrivals):
            try:
                df = pd.read_csv(csv_arrivals)
                for _, row in df.iterrows():
                    cursor.execute('''
                        INSERT OR REPLACE INTO bus_arrivals
                        (arrival_id, route_id, location_id, arrival_time, arrival_date, departure_time, crowd_level, notes, recorded_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        int(row['arrival_id']) if pd.notnull(row.get('arrival_id')) else None,
                        int(row['route_id']),
                        int(row['location_id']),
                        str(row['arrival_time']),
                        str(row['arrival_date']),
                        str(row.get('departure_time', '') or ''),
                        str(row.get('crowd_level', 'Medium') or 'Medium'),
                        str(row.get('notes', '') or ''),
                        str(row.get('recorded_at', '') or '')
                    ))
                conn.commit()
            except Exception as e:
                print(f"Error seeding arrivals from CSV: {e}")

    # Seed initial demo bus location if empty
    cursor.execute("SELECT COUNT(*) FROM bus_locations")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT OR REPLACE INTO bus_locations (bus_id, route_id, lat, lng, speed, updated_at)
            VALUES ('BUS-101', 1, 6.7580, 125.3520, 35.5, datetime('now'))
        ''')
        cursor.execute('''
            INSERT OR REPLACE INTO bus_locations (bus_id, route_id, lat, lng, speed, updated_at)
            VALUES ('BUS-102', 1, 6.8200, 125.3350, 40.0, datetime('now'))
        ''')
        conn.commit()

    conn.close()

# Initialize DB on module import
init_db()


def update_bus_location(bus_id, route_id, lat, lng, speed=0.0):
    """Upsert a live bus GPS position."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO bus_locations (bus_id, route_id, lat, lng, speed, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(bus_id) DO UPDATE SET
            route_id = excluded.route_id,
            lat = excluded.lat,
            lng = excluded.lng,
            speed = excluded.speed,
            updated_at = datetime('now')
    ''', (bus_id, int(route_id), float(lat), float(lng), float(speed)))
    conn.commit()
    conn.close()


def get_live_bus_locations():
    """Return all known live bus positions."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bus_locations")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_weather(lat, lng):
    """Fetch current weather from Open-Meteo (no API key required)."""
    import urllib.request
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&current=temperature_2m,weather_code,precipitation,rain&timezone=auto"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Weather fetch failed: {e}")
        return None
