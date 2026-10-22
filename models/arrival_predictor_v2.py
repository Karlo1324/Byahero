"""
Updated Arrival Predictor for ByaHero
Saves trained models with new data for improved predictions
"""

import pandas as pd
from datetime import datetime, timedelta
import os

# Add data path
import sys
data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
if data_dir not in sys.path:
    sys.path.insert(0, data_dir)


def _to_minutes(time_str):
    """Convert an 'HH:MM' string to minutes since midnight, or None."""
    try:
        parts = str(time_str).split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            return None
        return hours * 60 + minutes
    except (ValueError, TypeError, IndexError):
        return None


def _to_hhmm(minutes):
    """Convert minutes since midnight back to an 'HH:MM' string."""
    minutes = int(round(minutes)) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class ArrivalPredictor:
    # Fallback headway (minutes) when there is not enough history to derive one.
    DEFAULT_INTERVAL = 30

    # Gaps longer than this are treated as data errors rather than headways.
    MAX_PLAUSIBLE_GAP = 240

    def __init__(self, arrivals_df):
        """Initialize with arrivals dataframe"""
        self.arrivals_df = arrivals_df
        self.model_dir = os.path.join(os.path.dirname(__file__), '..', 'models', 'models')

    # ============ PREDICTION ============

    def predict_next_arrival(self, location_id, route_id=None, crowd_level=None):
        """
        Predict the next arrival time for a location.
        Returns dict with prediction, confidence, and statistics.
        """
        # Filter arrivals for this location
        arrivals = self._for_location(location_id)

        if route_id:
            arrivals = arrivals[arrivals['route_id'].astype('int64') == int(route_id)]

        # Work from a chronologically ordered copy so "last" means "latest",
        # not "the row that happens to sit at the end of the file".
        arrivals = self._sorted(arrivals)
        record_count = len(arrivals)

        if record_count == 0:
            return {
                "status": "Insufficient data",
                "confidence": "No records",
                "message": "No arrival records for this location",
                "next_arrival": None,
                "last_arrival": None,
                "record_count": 0
            }

        last_arrival = arrivals.iloc[-1]['arrival_time'] if record_count else None
        next_arrival = self._estimate_next_arrival(arrivals, crowd_level)
        interval = self._calculate_average_interval(arrivals)

        if record_count < 5:
            return {
                "status": "Low confidence",
                "confidence": f"Based on {record_count} record" + ("" if record_count == 1 else "s"),
                "message": (
                    f"Limited historical data ({record_count} records). "
                    "Predictions may be unreliable."
                ),
                "next_arrival": next_arrival,
                "record_count": record_count,
                "last_arrival": last_arrival,
                "average_interval": interval
            }

        return {
            "status": "Reliable",
            "confidence": f"Based on {record_count} records",
            "message": f"Prediction based on {record_count} historical records",
            "next_arrival": next_arrival,
            "record_count": record_count,
            "last_arrival": last_arrival,
            "average_interval": interval
        }

    def _sorted(self, arrivals):
        """Return arrivals ordered by date, then by time of day."""
        if arrivals is None or len(arrivals) == 0:
            return arrivals
        ordered = arrivals.copy()

        has_date = 'arrival_date' in ordered.columns
        has_time = 'arrival_time' in ordered.columns

        if has_time:
            # Order by the minute-of-day so same-day records are chronological.
            minutes = ordered['arrival_time'].apply(_to_minutes)
            ordered = ordered.assign(_minutes=minutes)

        if has_date and has_time:
            ordered = ordered.sort_values(
                ['arrival_date', '_minutes'], kind='stable'
            ).drop(columns=['_minutes'])
        elif has_date:
            ordered = ordered.sort_values('arrival_date', kind='stable')
        elif has_time:
            ordered = ordered.sort_values('_minutes', kind='stable').drop(
                columns=['_minutes']
            )

        return ordered

    def _for_location(self, location_id):
        """Rows belonging to one location, matched on an integer id."""
        try:
            location_id = int(location_id)
        except (TypeError, ValueError):
            return self.arrivals_df.iloc[0:0]
        return self.arrivals_df[
            self.arrivals_df['location_id'].astype('int64') == location_id
        ]

    def _estimate_next_arrival(self, arrivals_for_location, crowd_level=None):
        """
        Estimate the next arrival time.

        The next bus is the most recent arrival plus the typical headway
        between buses at this stop. Crowd level nudges the estimate: a
        crowded bus spends longer loading passengers.
        """
        try:
            if arrivals_for_location is None or len(arrivals_for_location) == 0:
                return None

            recent = arrivals_for_location.tail(5)

            times = []
            for time_str in recent['arrival_time']:
                minutes = _to_minutes(time_str)
                if minutes is not None:
                    times.append(minutes)

            if not times:
                return None

            # The arrivals are already in chronological order, so the last
            # one is the most recent and anchors the estimate.
            last_minutes = times[-1]

            # Derive the headway from the gaps between the recent arrivals.
            interval = self._average_gap(times)
            if interval is None:
                interval = self.DEFAULT_INTERVAL

            next_minutes = last_minutes + interval

            # Adjust based on crowd level if provided
            if crowd_level == 'High':
                next_minutes += 5
            elif crowd_level == 'Low':
                next_minutes -= 3

            return _to_hhmm(next_minutes)
        except Exception:
            return None

    @classmethod
    def _average_gap(cls, ordered_minutes):
        """
        Typical gap between consecutive arrival times, in minutes.

        The values are expected in chronological order. Gaps that are
        implausibly long are discarded so a single bad record cannot skew
        the estimate, and the median is used so one odd gap does not
        dominate.
        """
        if len(ordered_minutes) < 2:
            return None
        gaps = []
        for i in range(1, len(ordered_minutes)):
            gap = ordered_minutes[i] - ordered_minutes[i - 1]
            if gap < 0:  # Wrapped around midnight
                gap += 24 * 60
            if 0 <= gap <= cls.MAX_PLAUSIBLE_GAP:
                gaps.append(gap)
        if not gaps:
            return None
        gaps.sort()
        mid = len(gaps) // 2
        if len(gaps) % 2:
            return float(gaps[mid])
        return (gaps[mid - 1] + gaps[mid]) / 2

    def _calculate_average_interval(self, arrivals_for_location):
        """Calculate average interval between arrivals"""
        try:
            if arrivals_for_location is None or len(arrivals_for_location) < 2:
                return None

            times = []
            for time_str in arrivals_for_location['arrival_time']:
                minutes = _to_minutes(time_str)
                if minutes is not None:
                    times.append(minutes)

            if len(times) < 2:
                return None

            # The rows are already chronological, so the gaps between
            # consecutive times reflect the real headway.
            return self._average_gap(times)
        except Exception:
            return None

    # ============ MODEL PERSISTENCE ============

    def save_model(self, location_id):
        """Save a prediction model for this location based on its data"""
        try:
            # Create model directory if it doesn't exist
            os.makedirs(self.model_dir, exist_ok=True)

            # Get this location's data
            arrivals = self._sorted(self._for_location(location_id))

            if len(arrivals) < 5:
                return {"success": False, "message": "Insufficient data to save model"}

            # Calculate average time and interval
            avg_time = self._estimate_next_arrival(arrivals)
            avg_interval = self._calculate_average_interval(arrivals)

            # Save as simple text/Pickle file
            model_data = {
                "location_id": location_id,
                "average_time": avg_time,
                "average_interval": avg_interval,
                "record_count": len(arrivals),
                "last_updated": datetime.now().isoformat()
            }

            model_file = os.path.join(self.model_dir, f"loc_{location_id}.pkl")
            import pickle
            with open(model_file, 'wb') as f:
                pickle.dump(model_data, f)

            return {"success": True, "model_file": model_file}
        except Exception as e:
            print(f"Error saving model: {e}")
            return {"success": False, "message": str(e)}

    def load_model(self, location_id):
        """Load a previously saved prediction model for this location"""
        try:
            model_file = os.path.join(self.model_dir, f"loc_{location_id}.pkl")
            if not os.path.exists(model_file):
                return None

            import pickle
            with open(model_file, 'rb') as f:
                model_data = pickle.load(f)

            return model_data
        except Exception as e:
            print(f"Error loading model: {e}")
            return None

    def get_location_summary(self, location_id):
        """Get summary statistics for a location"""
        arrivals = self._sorted(self._for_location(location_id))

        if len(arrivals) == 0:
            return {
                "location_id": location_id,
                "total_records": 0,
                "status": "No data"
            }

        return {
            "location_id": location_id,
            "total_records": len(arrivals),
            "first_record": arrivals.iloc[0].get('recorded_at'),
            "last_record": arrivals.iloc[-1].get('recorded_at'),
            "status": "Ready for prediction"
        }

    def train_improved_model(self, location_id):
        """
        Train and save an improved model using simple regression
        based on historical data patterns
        """
        try:
            # Get this location's data
            arrivals = self._sorted(self._for_location(location_id)).copy()

            if len(arrivals) < 10:
                return {"success": False, "message": "Need at least 10 records for training"}

            # Convert time to numeric for analysis
            arrivals['time_numeric'] = arrivals['arrival_time'].apply(
                lambda x: _to_minutes(x)
            )
            arrivals = arrivals[arrivals['time_numeric'].notna()]

            if arrivals.empty:
                return {"success": False, "message": "No parsable arrival times to train on"}

            # Simple model per hour
            arrivals['day_of_week'] = pd.to_datetime(
                arrivals['arrival_date'], errors='coerce'
            ).dt.dayofweek
            arrivals['hour'] = (arrivals['time_numeric'] // 60).astype(int)

            models = {}
            for hour in range(24):
                hour_data = arrivals[arrivals['hour'] == hour]
                if len(hour_data) >= 3:
                    # Weighted average by recentness (last 5 records in the hour)
                    recent = hour_data.tail(min(5, len(hour_data)))
                    weights = [2 ** (len(recent) - i) for i in range(len(recent))]
                    avg_time_numeric = (
                        sum(recent['time_numeric'] * weights) / sum(weights)
                    )
                    models[hour] = {
                        "avg_minutes": avg_time_numeric,
                        "confidence": "Based on {} records".format(len(recent))
                    }

            # Save the model
            import pickle
            os.makedirs(self.model_dir, exist_ok=True)
            model_file = os.path.join(self.model_dir, f"loc_{location_id}_improved.pkl")
            model_data = {
                "location_id": location_id,
                "models": models,
                "record_count": len(arrivals),
                "last_updated": datetime.now().isoformat()
            }
            with open(model_file, 'wb') as f:
                pickle.dump(model_data, f)

            return {
                "success": True,
                "model_file": model_file,
                "hours_trained": len(models),
                "message": f"Trained model for {len(models)} hours"
            }

        except Exception as e:
            print(f"Error training model: {e}")
            return {"success": False, "message": str(e)}
