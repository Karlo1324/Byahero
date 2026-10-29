"""
Data Manager for ByaHero
Handles safe reading and writing of CSV files with validation
"""

import io
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

# Import arrival predictor v2
models_dir = os.path.join(os.path.dirname(__file__), '..', 'models')
if models_dir not in sys.path:
    sys.path.insert(0, models_dir)

# The project root and its data directory. These have to be absolute: a
# relative path only resolves when the process happens to be started from the
# project root, and starting the app from anywhere else made it come up
# looking like every record the user had entered had vanished.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# The route definitions live next to the data files.
if DATA_DIR not in sys.path:
    sys.path.insert(0, DATA_DIR)

try:
    from arrival_predictor_v2 import ArrivalPredictor
    PREDICTOR_AVAILABLE = True
except ImportError:
    PREDICTOR_AVAILABLE = False

try:
    from db_manager import get_db_connection, init_db
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# Suffix of the safety copy kept next to every data file.
BACKUP_SUFFIX = ".bak"


class DataManager:
    ARRIVAL_COLUMNS = [
        'arrival_id', 'route_id', 'location_id', 'arrival_time',
        'arrival_date', 'departure_time', 'crowd_level', 'notes',
        'recorded_at',
    ]

    LOCATION_COLUMNS = [
        'location_id', 'name', 'description', 'route_id', 'stop_sequence',
        'active', 'latitude', 'longitude',
    ]

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir) if data_dir else Path(DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.locations_file = self.data_dir / "locations.csv"
        self.arrivals_file = self.data_dir / "bus_arrivals.csv"

        # commute_data.csv sits in the project root; older copies also lived
        # in data/. Accept either so the training data is always found.
        root_commute = Path(BASE_DIR) / "commute_data.csv"
        self.commute_file = (root_commute if root_commute.exists()
                             else self.data_dir / "commute_data.csv")

        self._ensure_file(self.arrivals_file, self.ARRIVAL_COLUMNS)
        self._ensure_file(self.locations_file, self.LOCATION_COLUMNS)

    # ============ HELPERS ============

    @staticmethod
    def _records(df):
        """
        Convert a dataframe to JSON-safe records.

        pandas turns empty cells into NaN, and NaN is not valid JSON -- Flask
        emits it verbatim, producing a payload the browser cannot parse. Every
        missing value is normalised to None (null) and numpy scalars are
        converted to plain Python types.
        """
        if df is None or len(df) == 0:
            return []
        df = df.astype(object).where(pd.notnull(df), None)
        return df.to_dict('records')

    @staticmethod
    def _ensure_file(path, columns):
        """
        Make sure a data file exists with the expected header.

        A missing file used to make every read return an empty list, which
        looked exactly like the user's records had been deleted. Creating the
        file up front keeps the shape of the data stable.
        """
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=columns).to_csv(path, index=False)

    def _read_csv(self, path, columns):
        """
        Read a data file, falling back to its backup if the main copy is
        unreadable or was emptied out.
        """
        backup = Path(str(path) + BACKUP_SUFFIX)

        df = self._read_one(path)
        if df is not None and not df.empty:
            return df

        # The main file is missing, damaged or empty. The backup may still
        # hold the records.
        backup_df = self._read_one(backup)
        if backup_df is not None and not backup_df.empty:
            print(f"Recovered {backup.name} for {path.name}")
            return backup_df

        # Nothing usable anywhere -- hand back the empty shape so callers
        # still see the expected columns.
        if df is not None:
            return df
        return pd.DataFrame(columns=columns)

    @staticmethod
    def _read_one(path):
        """Read a single CSV file, returning None when it cannot be used."""
        if not path.exists():
            return None
        try:
            return pd.read_csv(path)
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            return None
        except Exception as e:
            print(f"Error reading {path}: {e}")
            return None

    def _write_csv(self, path, df):
        """
        Write a data file so that a failure can never destroy the existing
        records.

        The new content goes to a temporary file in the same directory, a
        copy of the current file is kept as <file>.bak, and only then is the
        temporary file moved into place. os.replace is atomic, so an
        interrupted write leaves the old data intact instead of a
        half-written file.

        After the swap the backup is refreshed so it mirrors what is on
        disk. That way the backup is a full copy of the data rather than the
        version from before the last write, and recovering from it does not
        lose the newest record.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        backup = Path(str(path) + BACKUP_SUFFIX)

        # A copy of the current file, so there is always something to go
        # back to if this write goes wrong.
        if path.exists():
            try:
                shutil.copy2(path, backup)
            except OSError as e:
                print(f"Could not back up {path}: {e}")

        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=path.name + '.', suffix='.tmp'
        )
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        try:
            df.to_csv(tmp_path, index=False)
            os.replace(str(tmp_path), str(path))
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        # The write succeeded, so the backup should match the file on disk.
        try:
            shutil.copy2(path, backup)
        except OSError as e:
            print(f"Could not refresh backup for {path}: {e}")

    @staticmethod
    def _next_id(df, column):
        """Next free id for a column, or 1 when the table is empty."""
        if df is None or len(df) == 0 or column not in df.columns:
            return 1
        try:
            return int(df[column].max()) + 1
        except (TypeError, ValueError):
            return 1

    # ============ GENERIC TABLE IO ============

    def _table_path(self, filename):
        """Path of a data table in the data directory."""
        return self.data_dir / filename

    def read_rows(self, filename, columns):
        """
        Read a data table as a list of dicts.

        Used by the tables that are not part of the fixed schema (the route
        registry), so they can be read and written without a dedicated
        accessor for each one.
        """
        try:
            df = self._read_csv(self._table_path(filename), columns)
            return self._records(df)
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            return []

    def write_rows(self, filename, rows, columns):
        """
        Replace a data table with the given rows.

        The write goes through the same backup-and-replace path as the other
        tables, so an interrupted write cannot empty the file.
        """
        try:
            df = pd.DataFrame(rows, columns=columns)
            self._write_csv(self._table_path(filename), df)
            return True
        except Exception as e:
            print(f"Error writing {filename}: {e}")
            return False

    # ============ LOCATIONS ============

    def get_locations(self):
        """Load all locations from SQLite, falling back to CSV if unavailable."""
        if DB_AVAILABLE:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM locations WHERE active IN ('true', '1', 'yes') ORDER BY stop_sequence")
                rows = cursor.fetchall()
                conn.close()
                return [dict(row) for row in rows]
            except Exception as e:
                print(f"Error loading locations from DB: {e}")
        try:
            df = self._read_csv(self.locations_file, self.LOCATION_COLUMNS)
            if 'active' not in df.columns:
                return self._records(df)
            active = df['active'].astype(str).str.strip().str.lower()
            df = df[active.isin(['true', '1', 'yes'])]
            return self._records(df)
        except Exception as e:
            print(f"Error loading locations: {e}")
            return []

    def get_locations_by_route(self, route_id):
        """Get all active locations for a route, ordered by sequence."""
        if DB_AVAILABLE:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM locations WHERE route_id = ? AND active IN ('true', '1', 'yes') ORDER BY stop_sequence",
                    (route_id,)
                )
                rows = cursor.fetchall()
                conn.close()
                return [dict(row) for row in rows]
            except Exception as e:
                print(f"Error loading locations for route {route_id} from DB: {e}")
        try:
            df = self._read_csv(self.locations_file, self.LOCATION_COLUMNS)
            if 'route_id' not in df.columns:
                return []
            df = df[df['route_id'].astype('int64') == int(route_id)]
            if 'active' in df.columns:
                active = df['active'].astype(str).str.strip().str.lower()
                df = df[active.isin(['true', '1', 'yes'])]
            df = df.sort_values('stop_sequence')
            return self._records(df)
        except Exception as e:
            print(f"Error loading locations for route {route_id}: {e}")
            return []

    def add_location(self, name, description, route_id, stop_sequence, active=True, latitude=None, longitude=None):
        """Add a new location to SQLite or CSV."""
        if DB_AVAILABLE:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT location_id FROM locations WHERE name = ? AND route_id = ?",
                    (name, route_id)
                )
                if cursor.fetchone():
                    conn.close()
                    return {"success": False, "error": f"Location '{name}' already exists on this route"}
                cursor.execute(
                    "INSERT INTO locations (name, description, route_id, stop_sequence, active, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (name, description or '', route_id, stop_sequence, 'true' if active else 'false', latitude, longitude)
                )
                conn.commit()
                new_id = cursor.lastrowid
                conn.close()
                self._sync_to_csv('locations.csv', self.LOCATION_COLUMNS)
                return {"success": True, "location_id": new_id, "message": f"Location '{name}' added successfully"}
            except Exception as e:
                print(f"Error adding location to DB: {e}")
        try:
            df = self._read_csv(self.locations_file, self.LOCATION_COLUMNS)
            existing = df[(df['name'] == name) &
                          (df['route_id'].astype('int64') == int(route_id))]
            if not existing.empty:
                return {"success": False, "error": f"Location '{name}' already exists on this route"}
            next_id = self._next_id(df, 'location_id')
            new_location = {
                'location_id': next_id,
                'name': name,
                'description': description or '',
                'route_id': route_id,
                'stop_sequence': stop_sequence,
                'active': 'true' if active else 'false',
                'latitude': latitude,
                'longitude': longitude
            }
            df = pd.concat([df, pd.DataFrame([new_location])], ignore_index=True)
            self._write_csv(self.locations_file, df)
            return {"success": True, "location_id": next_id, "message": f"Location '{name}' added successfully"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _sync_to_csv(self, filename, columns):
        """Write current SQLite state for a table back to CSV for legacy fallback."""
        if not DB_AVAILABLE or not self._table_path(filename).exists():
            return
        try:
            conn = get_db_connection()
            df = pd.read_sql_query(f"SELECT * FROM {filename[:-4]}", conn)
            conn.close()
            self._write_csv(self._table_path(filename), df)
        except Exception as e:
            print(f"Error syncing {filename} to CSV: {e}")

    def add_locations(self, route_id, stops):
        """
        Add several stops to a route in one go.

        `stops` is a list of dicts with a "name", an optional "description"
        and an optional "model_stop". The locations are numbered in the order
        given and each one carries its own "model_stop" in the returned list,
        so the caller can map them onto the route's model vocabulary.

        Returns a dict with "success" and the created "locations".
        """
        if DB_AVAILABLE:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                # Check existing names on this route
                cursor.execute(
                    "SELECT name FROM locations WHERE route_id = ? AND active IN ('true', '1', 'yes')",
                    (route_id,)
                )
                existing_names = {row['name'].strip().lower() for row in cursor.fetchall()}

                for stop in stops or []:
                    name = str(stop.get('name') or '').strip()
                    if name.lower() in existing_names:
                        conn.close()
                        return {"success": False, "error": f"Location '{name}' already exists on this route"}
                    existing_names.add(name.lower())

                # Get max location_id for this route
                cursor.execute("SELECT COALESCE(MAX(location_id), 0) FROM locations WHERE route_id = ?", (route_id,))
                next_id = cursor.fetchone()[0] + 1

                rows = []
                created = []

                for index, stop in enumerate(stops or []):
                    location_id = next_id + index
                    cursor.execute(
                        "INSERT INTO locations (location_id, name, description, route_id, stop_sequence, active, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (location_id,
                         str(stop.get('name') or '').strip(),
                         stop.get('description') or '',
                         route_id,
                         index + 1,
                         'true',
                         stop.get('latitude'),
                         stop.get('longitude'))
                    )
                    rows.append({
                        'location_id': location_id,
                        'name': str(stop.get('name') or '').strip(),
                        'description': stop.get('description') or '',
                        'route_id': route_id,
                        'stop_sequence': index + 1,
                        'active': 'true',
                        'latitude': stop.get('latitude'),
                        'longitude': stop.get('longitude')
                    })
                    created.append({
                        'location_id': location_id,
                        'name': str(stop.get('name') or '').strip(),
                        'model_stop': stop.get('model_stop') or '',
                    })

                conn.commit()
                conn.close()
                self._sync_to_csv('locations.csv', self.LOCATION_COLUMNS)

                return {"success": True, "locations": created}
            except Exception as e:
                print(f"Error adding locations to DB: {e}")

        # CSV fallback
        try:
            df = self._read_csv(self.locations_file, self.LOCATION_COLUMNS)

            # Names already used on this route.
            existing_names = set()
            if 'name' in df.columns and 'route_id' in df.columns:
                on_route = df[df['route_id'].astype('int64') == int(route_id)]
                existing_names = {
                    str(name).strip().lower() for name in on_route['name'].tolist()
                }

            for stop in stops or []:
                name = str(stop.get('name') or '').strip()
                if name.lower() in existing_names:
                    return {"success": False, "error": f"Location '{name}' already exists on this route"}
                existing_names.add(name.lower())

            next_id = self._next_id(df, 'location_id')
            rows = []
            created = []

            for index, stop in enumerate(stops or []):
                location_id = next_id + index
                rows.append({
                    'location_id': location_id,
                    'name': str(stop.get('name') or '').strip(),
                    'description': stop.get('description') or '',
                    'route_id': route_id,
                    'stop_sequence': index + 1,
                    'active': 'true',
                    'latitude': stop.get('latitude'),
                    'longitude': stop.get('longitude')
                })
                created.append({
                    'location_id': location_id,
                    'name': str(stop.get('name') or '').strip(),
                    'model_stop': stop.get('model_stop') or '',
                })

            if rows:
                df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
                self._write_csv(self.locations_file, df)

            return {"success": True, "locations": created}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def deactivate_location(self, location_id):
        """Deactivate a location in SQLite or CSV."""
        if DB_AVAILABLE:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE locations SET active = 'false' WHERE location_id = ?", (location_id,))
                conn.commit()
                conn.close()
                self._sync_to_csv('locations.csv', self.LOCATION_COLUMNS)
                return {"success": True, "message": "Location deactivated"}
            except Exception as e:
                print(f"Error deactivating location in DB: {e}")
        try:
            df = self._read_csv(self.locations_file, self.LOCATION_COLUMNS)
            df.loc[df['location_id'].astype('int64') == int(location_id), 'active'] = 'false'
            self._write_csv(self.locations_file, df)
            return {"success": True, "message": "Location deactivated"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ============ BUS ARRIVALS ============

    def get_arrivals(self, route_id=None, location_id=None, limit=100):
        """Get bus arrivals with optional filters, from SQLite or CSV."""
        if DB_AVAILABLE:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                query = "SELECT * FROM bus_arrivals WHERE 1=1"
                params = []
                if route_id:
                    query += " AND route_id = ?"
                    params.append(int(route_id))
                if location_id:
                    query += " AND location_id = ?"
                    params.append(int(location_id))
                query += " ORDER BY recorded_at DESC LIMIT ?"
                params.append(limit)
                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.close()
                return [dict(row) for row in rows]
            except Exception as e:
                print(f"Error loading arrivals from DB: {e}")
        try:
            df = self._read_csv(self.arrivals_file, self.ARRIVAL_COLUMNS)

            if route_id and 'route_id' in df.columns:
                df = df[df['route_id'].astype('int64') == int(route_id)]
            if location_id and 'location_id' in df.columns:
                df = df[df['location_id'].astype('int64') == int(location_id)]

            if 'recorded_at' in df.columns:
                df = df.sort_values('recorded_at', ascending=False)
            df = df.head(limit)
            return self._records(df)
        except Exception as e:
            print(f"Error loading arrivals: {e}")
            return []

    def add_arrival_record(self, route_id, location_id, arrival_time, arrival_date,
                           departure_time=None, crowd_level=None, notes=None):
        """Add a new bus arrival record to SQLite or CSV."""
        if DB_AVAILABLE:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                # Check for duplicates (same route/location/date/time within 5 min window)
                cursor.execute(
                    "SELECT arrival_time, arrival_date FROM bus_arrivals WHERE route_id = ? AND location_id = ? AND arrival_date = ?",
                    (int(route_id), int(location_id), arrival_date)
                )
                rows = cursor.fetchall()
                try:
                    arrival_dt = pd.to_datetime(f"{arrival_date} {arrival_time}")
                except Exception:
                    arrival_dt = None
                for row in rows:
                    try:
                        existing_dt = pd.to_datetime(f"{row['arrival_date']} {row['arrival_time']}")
                        if arrival_dt and abs((arrival_dt - existing_dt).total_seconds() / 60) < 5:
                            conn.close()
                            return {"success": False, "error": "Similar arrival already recorded within 5 minutes"}
                    except Exception:
                        continue

                cursor.execute(
                    "INSERT INTO bus_arrivals (route_id, location_id, arrival_time, arrival_date, departure_time, crowd_level, notes, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (int(route_id), int(location_id), arrival_time, arrival_date, departure_time or '', crowd_level or 'Medium', notes or '', datetime.now().isoformat())
                )
                conn.commit()
                new_id = cursor.lastrowid
                conn.close()
                self._sync_to_csv('bus_arrivals.csv', self.ARRIVAL_COLUMNS)

                # Retrain the per-location model with the new data included.
                if PREDICTOR_AVAILABLE:
                    try:
                        df = self._read_csv(self.arrivals_file, self.ARRIVAL_COLUMNS)
                        predictor = ArrivalPredictor(df)
                        predictor.train_improved_model(location_id)
                    except Exception as e:
                        print(f"Error training improved model: {e}")

                return {"success": True, "arrival_id": new_id, "message": "Arrival record saved"}
            except Exception as e:
                print(f"Error adding arrival to DB: {e}")
        try:
            df = self._read_csv(self.arrivals_file, self.ARRIVAL_COLUMNS)

            # Check for duplicates (same route/location/date/time within 5 min window)
            arrival_dt = pd.to_datetime(f"{arrival_date} {arrival_time}")
            existing = df[(df['route_id'].astype('int64') == int(route_id)) &
                          (df['location_id'].astype('int64') == int(location_id)) &
                          (df['arrival_date'] == arrival_date)]

            if not existing.empty:
                for _, row in existing.iterrows():
                    existing_dt = pd.to_datetime(f"{row['arrival_date']} {row['arrival_time']}")
                    time_diff = abs((arrival_dt - existing_dt).total_seconds() / 60)
                    if time_diff < 5:
                        return {
                            "success": False,
                            "error": "Similar arrival already recorded within 5 minutes"
                        }

            # Add new record
            next_id = self._next_id(df, 'arrival_id')

            new_arrival = {
                'arrival_id': next_id,
                'route_id': route_id,
                'location_id': location_id,
                'arrival_time': arrival_time,
                'arrival_date': arrival_date,
                'departure_time': departure_time or '',
                'crowd_level': crowd_level or 'Medium',
                'notes': notes or '',
                'recorded_at': datetime.now().isoformat()
            }

            df = pd.concat([df, pd.DataFrame([new_arrival])], ignore_index=True)
            self._write_csv(self.arrivals_file, df)

            # Retrain the per-location model with the new data included.
            if PREDICTOR_AVAILABLE:
                try:
                    predictor = ArrivalPredictor(df)
                    predictor.train_improved_model(location_id)
                except Exception as e:
                    print(f"Error training improved model: {e}")

            return {
                "success": True,
                "arrival_id": next_id,
                "message": "Arrival record saved"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_arrival_statistics(self, location_id):
        """Get statistics for a location (average arrival time, frequency, etc.)"""
        try:
            df = self._read_csv(self.arrivals_file, self.ARRIVAL_COLUMNS)
            df = df[df['location_id'].astype('int64') == int(location_id)]

            if len(df) == 0:
                return {
                    "count": 0,
                    "status": "Insufficient data",
                    "message": "No arrival records for this location"
                }

            # Sort chronologically so "first" really is the earliest record.
            if 'arrival_date' in df.columns:
                df = df.sort_values(['arrival_date', 'arrival_time'])

            stats = {
                "count": len(df),
                "status": "Based on " + str(len(df)) + (" record" if len(df) == 1 else " records"),
                "last_arrival": df.iloc[-1]['arrival_time'],
                "first_arrival": df.iloc[0]['arrival_time'],
            }

            return stats
        except Exception as e:
            print(f"Error calculating statistics: {e}")
            return {"status": "Error", "message": str(e)}

    # ============ COMMUTE DATA ============

    def get_commute_data(self):
        """Load commute data"""
        try:
            return pd.read_csv(self.commute_file)
        except Exception as e:
            print(f"Error loading commute data: {e}")
            return pd.DataFrame()

    # ============ CSV EXPORT ============

    def export_arrivals_csv(self, route_id=None, location_id=None,
                            start_date=None, end_date=None):
        """
        Build the arrival records as CSV text.

        The location and route names are folded in so the exported file is
        readable on its own, without needing the app to look the ids up.
        """
        records = self.get_arrivals(route_id=route_id, location_id=location_id,
                                    limit=100000)

        # Newest first in the app, oldest first in the export.
        records = list(reversed(records))

        if start_date:
            records = [r for r in records if str(r.get('arrival_date') or '') >= start_date]
        if end_date:
            records = [r for r in records if str(r.get('arrival_date') or '') <= end_date]

        names = self._location_name_map()
        route_names = self._route_name_map()

        columns = [
            'arrival_id', 'route_id', 'route_name', 'location_id',
            'location_name', 'arrival_date', 'arrival_time', 'departure_time',
            'crowd_level', 'notes', 'recorded_at',
        ]

        rows = []
        for r in records:
            row_location_id = r.get('location_id')
            row_route_id = r.get('route_id')
            rows.append({
                'arrival_id': r.get('arrival_id'),
                'route_id': row_route_id,
                'route_name': route_names.get(row_route_id, ''),
                'location_id': row_location_id,
                'location_name': names.get(row_location_id, ''),
                'arrival_date': r.get('arrival_date'),
                'arrival_time': r.get('arrival_time'),
                'departure_time': r.get('departure_time') or '',
                'crowd_level': r.get('crowd_level') or '',
                'notes': r.get('notes') or '',
                'recorded_at': r.get('recorded_at') or '',
            })

        df = pd.DataFrame(rows, columns=columns)
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        return buffer.getvalue(), len(rows)

    def export_locations_csv(self):
        """Build the location registry as CSV text."""
        records = self.get_locations()

        route_names = self._route_name_map()
        columns = ['location_id', 'name', 'description', 'route_id',
                   'route_name', 'stop_sequence', 'active']

        rows = []
        for r in records:
            route_id = r.get('route_id')
            rows.append({
                'location_id': r.get('location_id'),
                'name': r.get('name'),
                'description': r.get('description') or '',
                'route_id': route_id,
                'route_name': route_names.get(route_id, ''),
                'stop_sequence': r.get('stop_sequence'),
                'active': r.get('active'),
            })

        df = pd.DataFrame(rows, columns=columns)
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        return buffer.getvalue(), len(rows)

    def _location_name_map(self):
        """Map of location_id -> name for every known location."""
        try:
            df = self._read_csv(self.locations_file, self.LOCATION_COLUMNS)
            if 'location_id' not in df.columns or 'name' not in df.columns:
                return {}
            return dict(zip(df['location_id'], df['name']))
        except Exception:
            return {}

    @staticmethod
    def _route_name_map():
        """Map of route_id -> route name, taken from the route config."""
        try:
            from routes_config import get_all_routes
            return {rid: route.get('name', '')
                    for rid, route in get_all_routes().items()}
        except Exception:
            return {}


# Create singleton instance
data_manager = DataManager()
