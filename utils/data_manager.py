"""
Data Manager for ByaHero
Handles safe reading and writing of CSV files with validation
"""

import pandas as pd
import os
from datetime import datetime
from pathlib import Path

class DataManager:
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.locations_file = self.data_dir / "locations.csv"
        self.arrivals_file = self.data_dir / "bus_arrivals.csv"
        self.commute_file = self.data_dir / "commute_data.csv"
    
    # ============ LOCATIONS ============
    
    def get_locations(self):
        """Load all locations from CSV"""
        try:
            df = pd.read_csv(self.locations_file)
            return df[df['active'] == 'true' or df['active'] == True].to_dict('records')
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"Error loading locations: {e}")
            return []
    
    def get_locations_by_route(self, route_id):
        """Get all locations for a specific route, ordered by sequence"""
        try:
            df = pd.read_csv(self.locations_file)
            df = df[(df['route_id'] == route_id) & ((df['active'] == 'true') | (df['active'] == True))]
            df = df.sort_values('stop_sequence')
            return df.to_dict('records')
        except Exception as e:
            print(f"Error loading locations for route {route_id}: {e}")
            return []
    
    def add_location(self, name, description, route_id, stop_sequence, active=True):
        """Add a new location"""
        try:
            df = pd.read_csv(self.locations_file)
            
            # Check for duplicates
            existing = df[(df['name'] == name) & (df['route_id'] == route_id)]
            if not existing.empty:
                return {"success": False, "error": f"Location '{name}' already exists on this route"}
            
            # Get next location_id
            next_id = int(df['location_id'].max()) + 1 if len(df) > 0 else 1
            
            # Add new location
            new_location = {
                'location_id': next_id,
                'name': name,
                'description': description,
                'route_id': route_id,
                'stop_sequence': stop_sequence,
                'active': 'true' if active else 'false'
            }
            
            df = pd.concat([df, pd.DataFrame([new_location])], ignore_index=True)
            df.to_csv(self.locations_file, index=False)
            
            return {"success": True, "location_id": next_id, "message": f"Location '{name}' added successfully"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def deactivate_location(self, location_id):
        """Deactivate a location"""
        try:
            df = pd.read_csv(self.locations_file)
            df.loc[df['location_id'] == location_id, 'active'] = 'false'
            df.to_csv(self.locations_file, index=False)
            return {"success": True, "message": "Location deactivated"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ============ BUS ARRIVALS ============
    
    def get_arrivals(self, route_id=None, location_id=None, limit=100):
        """Get bus arrivals with optional filters"""
        try:
            df = pd.read_csv(self.arrivals_file)
            
            if route_id:
                df = df[df['route_id'] == route_id]
            if location_id:
                df = df[df['location_id'] == location_id]
            
            df = df.sort_values('recorded_at', ascending=False).head(limit)
            return df.to_dict('records')
        except FileNotFoundError:
            return []
        except Exception as e:
            print(f"Error loading arrivals: {e}")
            return []
    
    def add_arrival_record(self, route_id, location_id, arrival_time, arrival_date, 
                          departure_time=None, crowd_level=None, notes=None):
        """Add a new bus arrival record"""
        try:
            df = pd.read_csv(self.arrivals_file)
            
            # Check for duplicates (same route/location/date/time within 5 min window)
            arrival_dt = pd.to_datetime(f"{arrival_date} {arrival_time}")
            existing = df[(df['route_id'] == route_id) & 
                         (df['location_id'] == location_id) &
                         (df['arrival_date'] == arrival_date)]
            
            if not existing.empty:
                for _, row in existing.iterrows():
                    existing_dt = pd.to_datetime(f"{row['arrival_date']} {row['arrival_time']}")
                    time_diff = abs((arrival_dt - existing_dt).total_seconds() / 60)
                    if time_diff < 5:
                        return {"success": False, "error": "Similar arrival already recorded within 5 minutes"}
            
            # Add new record
            next_id = int(df['arrival_id'].max()) + 1 if len(df) > 0 else 1
            
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
            df.to_csv(self.arrivals_file, index=False)
            
            return {"success": True, "arrival_id": next_id, "message": "Arrival record saved"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_arrival_statistics(self, location_id):
        """Get statistics for a location (average arrival time, frequency, etc.)"""
        try:
            df = pd.read_csv(self.arrivals_file)
            df = df[df['location_id'] == location_id]
            
            if len(df) == 0:
                return {
                    "count": 0,
                    "status": "Insufficient data",
                    "message": "No arrival records for this location"
                }
            
            stats = {
                "count": len(df),
                "status": "Based on " + str(len(df)) + (" record" if len(df) == 1 else " records"),
                "last_arrival": df.iloc[-1]['arrival_time'] if len(df) > 0 else None,
                "first_arrival": df.iloc[0]['arrival_time'] if len(df) > 0 else None,
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


# Create singleton instance
data_manager = DataManager()
