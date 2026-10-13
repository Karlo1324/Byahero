"""
Arrival Predictor for ByaHero
Predicts bus arrival times based on historical data
"""

import pandas as pd
from datetime import datetime, timedelta

class ArrivalPredictor:
    def __init__(self, arrivals_df):
        """Initialize with arrivals dataframe"""
        self.arrivals_df = arrivals_df
    
    def predict_next_arrival(self, location_id, route_id=None):
        """
        Predict the next arrival time for a location.
        Returns dict with prediction, confidence, and statistics.
        """
        # Filter arrivals for this location
        arrivals = self.arrivals_df[self.arrivals_df['location_id'] == location_id]
        
        if route_id:
            arrivals = arrivals[arrivals['route_id'] == route_id]
        
        record_count = len(arrivals)
        
        if record_count == 0:
            return {
                "status": "Insufficient data",
                "confidence": "No records",
                "message": "No arrival records for this location",
                "next_arrival": None,
                "record_count": 0
            }
        
        if record_count < 5:
            return {
                "status": "Low confidence",
                "confidence": f"Based on {record_count} record" + ("" if record_count == 1 else "s"),
                "message": f"Limited historical data ({record_count} records). Predictions may be unreliable.",
                "next_arrival": self._estimate_next_arrival(arrivals),
                "record_count": record_count,
                "last_arrival": arrivals.iloc[-1]['arrival_time'] if len(arrivals) > 0 else None
            }
        
        # Calculate average arrival time
        next_arrival = self._estimate_next_arrival(arrivals)
        
        return {
            "status": "Reliable",
            "confidence": f"Based on {record_count} records",
            "message": f"Prediction based on {record_count} historical records",
            "next_arrival": next_arrival,
            "record_count": record_count,
            "last_arrival": arrivals.iloc[-1]['arrival_time'] if len(arrivals) > 0 else None,
            "average_interval": self._calculate_average_interval(arrivals)
        }
    
    def _estimate_next_arrival(self, arrivals_for_location):
        """
        Estimate next arrival time using simple heuristic:
        Average of recent arrivals + typical interval
        """
        try:
            # Get the last 5 arrivals
            recent = arrivals_for_location.tail(5)
            
            times = []
            for time_str in recent['arrival_time']:
                try:
                    h, m = map(int, time_str.split(':'))
                    times.append(h * 60 + m)  # Convert to minutes since midnight
                except:
                    continue
            
            if not times:
                return None
            
            avg_minutes = sum(times) / len(times)
            
            # Convert back to HH:MM
            hours = int(avg_minutes // 60)
            minutes = int(avg_minutes % 60)
            
            return f"{hours:02d}:{minutes:02d}"
        except:
            return None
    
    def _calculate_average_interval(self, arrivals_for_location):
        """
        Calculate average interval between arrivals
        Returns minutes as float
        """
        try:
            if len(arrivals_for_location) < 2:
                return None
            
            times = []
            for time_str in arrivals_for_location['arrival_time']:
                try:
                    h, m = map(int, time_str.split(':'))
                    times.append(h * 60 + m)
                except:
                    continue
            
            if len(times) < 2:
                return None
            
            intervals = []
            for i in range(1, len(times)):
                diff = times[i] - times[i-1]
                if diff < 0:  # Wrapped around midnight
                    diff += 24 * 60
                intervals.append(diff)
            
            if not intervals:
                return None
            
            return sum(intervals) / len(intervals)
        except:
            return None
    
    def get_location_summary(self, location_id):
        """Get summary statistics for a location"""
        arrivals = self.arrivals_df[self.arrivals_df['location_id'] == location_id]
        
        if len(arrivals) == 0:
            return {
                "location_id": location_id,
                "total_records": 0,
                "status": "No data"
            }
        
        return {
            "location_id": location_id,
            "total_records": len(arrivals),
            "first_record": arrivals.iloc[0]['recorded_at'] if len(arrivals) > 0 else None,
            "last_record": arrivals.iloc[-1]['recorded_at'] if len(arrivals) > 0 else None,
            "status": "Ready for prediction"
        }

