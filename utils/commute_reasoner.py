"""
Commute Reasoner for ByaHero
Handles natural language understanding and trip planning logic for Konduktor
"""

import re
from datetime import datetime, timedelta
import pandas as pd
from routes_config import get_all_routes, resolve_route_id, get_stops_after
from data_manager import data_manager

try:
    from weather_service import get_weather, get_weather_for_location, get_weather_factor, _weather_text
    WEATHER_AVAILABLE = True
except ImportError:
    WEATHER_AVAILABLE = False

# Approximate coordinates for Digos City / Kapatagan route stops (fallback).
STOP_COORDS = {
    1: (6.7580, 125.3520),   # Kapatagan
    2: (6.8000, 125.3400),   # Soong
    3: (6.8300, 125.3300),   # Binaton
    4: (6.8500, 125.3200),   # Digos Terminal
}

WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "freezing drizzle",
    57: "freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "freezing rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}

class CommuteReasoner:
    def __init__(self, predictor_factory):
        self.get_predictor = predictor_factory

    def parse_message(self, message, context):
        """Extract intent and entities from message"""
        msg = message.lower()

        # Current context
        active_trip = context.get('active_trip', {})

        # Route detection (default to Kapatagan to Digos if mentioned)
        if any(w in msg for w in ['kapatagan', 'digos']):
            active_trip['route_id'] = 1  # Hardcoded default for now as it's the main route

        # Origin/Destination detection
        locations = data_manager.get_locations()
        for loc in locations:
            loc_name = loc['name'].lower()
            if loc_name in msg:
                if 'from' in msg.split(loc_name)[0] or 'boarding' in msg.split(loc_name)[0] or 'at' in msg.split(loc_name)[0]:
                    active_trip['origin_id'] = loc['location_id']
                    active_trip['origin_name'] = loc['name']
                elif 'to' in msg.split(loc_name)[0] or 'going to' in msg.split(loc_name)[0] or 'destination' in msg.split(loc_name)[0]:
                    active_trip['destination_id'] = loc['location_id']
                    active_trip['destination_name'] = loc['name']
                else:
                    # Ambiguous, if we don't have origin, assume origin
                    if not active_trip.get('origin_id'):
                        active_trip['origin_id'] = loc['location_id']
                        active_trip['origin_name'] = loc['name']
                    else:
                        active_trip['destination_id'] = loc['location_id']
                        active_trip['destination_name'] = loc['name']

        # Time detection (e.g. "2 PM", "14:00")
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', msg)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            ampm = time_match.group(3)

            if ampm == 'pm' and hour < 12: hour += 12
            if ampm == 'am' and hour == 12: hour = 0

            active_trip['target_time'] = f"{hour:02d}:{minute:02d}"
            active_trip['time_type'] = 'arrival' if 'at' in msg or 'by' in msg else 'departure'

        return active_trip

    def get_recommendation(self, trip_data):
        """Generate trip plan and recommendations based on extracted data"""
        route_id = trip_data.get('route_id')
        origin_id = trip_data.get('origin_id')
        destination_id = trip_data.get('destination_id')
        target_time = trip_data.get('target_time')

        if not (route_id and origin_id and destination_id and target_time):
            return None, self._get_missing_info_prompt(trip_data)

        # Logic for recommendation
        predictor = self.get_predictor()

        # 1. Get predicted next bus at origin
        prediction = predictor.predict_next_arrival(origin_id, route_id, "Medium")
        next_bus = prediction.get('next_arrival')

        # 2. Get travel time estimate (simplified logic using historical average if ML fails)
        # In a real app, we'd call the ML model here
        travel_time = 45 # Default fallback

        # 3. Adjust travel time for current weather at the origin stop.
        weather_factor = 1.0
        weather_label = None
        weather_reason = None
        if WEATHER_AVAILABLE:
            # Prefer coordinates from the DB if available, fallback to STOP_COORDS.
            locs = data_manager.get_locations()
            origin_loc = next((l for l in locs if l.get('location_id') == origin_id), None)
            if origin_loc and origin_loc.get('latitude') is not None and origin_loc.get('longitude') is not None:
                w = get_weather_for_location(origin_loc)
                if w:
                    weather_factor, weather_reason = get_weather_factor(
                        w.get('weather_code'),
                        w.get('precipitation_mm', 0.0),
                        w.get('temperature_c', 25.0)
                    )
                    weather_label = _weather_text(w.get('weather_code'))
            elif origin_id in STOP_COORDS:
                lat, lng = STOP_COORDS[origin_id]
                w = get_weather(lat, lng)
                if w and 'current' in w:
                    c = w['current']
                    weather_factor, weather_reason = get_weather_factor(
                        c.get('weather_code', 0),
                        c.get('precipitation', 0.0) or 0.0,
                        c.get('temperature_2m', 25.0)
                    )
                    weather_label = _weather_text(c.get('weather_code'))
        travel_time = int(travel_time * weather_factor)

        # 3. Calculate recommended departure
        target_dt = datetime.strptime(target_time, '%H:%M')
        if trip_data.get('time_type') == 'arrival':
            recommended_arrival_at_origin = target_dt - timedelta(minutes=travel_time + 15) # 15m buffer
            rec_time = recommended_arrival_at_origin.strftime('%H:%M')
            action = f"wait at {trip_data['origin_name']} by {rec_time}"
        else:
            rec_time = target_time
            action = f"leave {trip_data['origin_name']} at {rec_time}"

        response = f"I've planned your trip from {trip_data['origin_name']} to {trip_data['destination_name']}. "
        if trip_data.get('time_type') == 'arrival':
            response += f"To arrive by {target_time}, I recommend being at the stop by **{rec_time}**. "
        else:
            response += f"If you leave at {target_time}, you should arrive around **{(target_dt + timedelta(minutes=travel_time)).strftime('%H:%M')}**. "

        if next_bus:
            response += f"The next bus is predicted to arrive at {next_bus}."

        if weather_label and weather_reason:
            response += f" Current weather: {weather_label} ({weather_reason}), so travel time is adjusted accordingly."

        return trip_data, response

    def _get_missing_info_prompt(self, trip_data):
        if not trip_data.get('origin_id'):
            return "Sure! Where will you be boarding the bus? (e.g., Binaton, Soong, Kapatagan)"
        if not trip_data.get('destination_id'):
            return f"Got it, you're at {trip_data['origin_name']}. Where are you heading to? (e.g., Digos Terminal)"
        if not trip_data.get('target_time'):
            return "What time are you planning to travel?"
        return "I need a few more details to plan your trip."

# Helper to avoid circular imports in app.py
def get_reasoner(predictor_factory):
    return CommuteReasoner(predictor_factory)
