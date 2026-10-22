"""
Input Validators for ByaHero
Validates user input for forms and API endpoints
"""

import re
from datetime import datetime, time, timedelta, timezone

# How far ahead of "now" an arrival may still be recorded.
#
# The arrival time is only precise to the minute and the clock in the
# browser is rarely in step with the clock on the server, so a record that
# is a couple of minutes ahead is a rounding artefact rather than a
# mistake. Anything further ahead is refused.
FUTURE_TOLERANCE_MINUTES = 2

# The real world runs from UTC-12 to UTC+14, so an offset outside that
# range is a broken client rather than a genuine timezone.
MAX_UTC_OFFSET_MINUTES = 14 * 60


def local_now_from_offset(offset_minutes):
    """
    The current wall-clock time in the timezone the user is in.

    The browser sends the value of `getTimezoneOffset()` (UTC minus local,
    in minutes) and the server converts its own UTC clock into that zone.
    The server's own local time is deliberately not used: a hosted
    deployment usually runs in UTC, which is hours behind the user, and
    every arrival the user recorded was then refused as being in the
    future.

    Returns None when the offset is missing or out of range, so the caller
    can fall back to the server's local time.
    """
    if offset_minutes is None or offset_minutes == '':
        return None
    try:
        offset = int(offset_minutes)
    except (TypeError, ValueError):
        return None
    if abs(offset) > MAX_UTC_OFFSET_MINUTES:
        return None

    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    return utc_now - timedelta(minutes=offset)


class InputValidator:

    @staticmethod
    def validate_time(time_str):
        """Validate time format HH:MM"""
        if not time_str:
            return False, "Time is required"
        try:
            datetime.strptime(str(time_str), "%H:%M")
            return True, None
        except (ValueError, TypeError):
            return False, "Invalid time format. Use HH:MM (e.g., 07:30)"

    @staticmethod
    def validate_date(date_str):
        """Validate date format YYYY-MM-DD"""
        if not date_str:
            return False, "Date is required"
        try:
            datetime.strptime(str(date_str), "%Y-%m-%d")
            return True, None
        except (ValueError, TypeError):
            return False, "Invalid date format. Use YYYY-MM-DD"

    @staticmethod
    def validate_not_future(date_str, time_str, tz_offset_minutes=None):
        """
        Ensure the datetime is not in the future.

        `tz_offset_minutes` is the browser's getTimezoneOffset() value.
        When it is given, "now" is the current time in the user's own
        timezone, so the record is compared against the clock the user
        actually looked at. Without it the server's local time is used,
        which is wrong whenever the two are in different timezones.
        """
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return False, "Invalid date/time"

        now = local_now_from_offset(tz_offset_minutes) or datetime.now()

        if dt > now + timedelta(minutes=FUTURE_TOLERANCE_MINUTES):
            return False, "Cannot record arrival in the future"
        return True, None

    @staticmethod
    def validate_departure_before_arrival(departure_time, arrival_time):
        """Ensure departure time is before arrival time"""
        if not departure_time:
            return True, None  # Departure time is optional

        try:
            dep = datetime.strptime(departure_time, "%H:%M").time()
            arr = datetime.strptime(arrival_time, "%H:%M").time()

            if dep >= arr:
                return False, "Departure time must be before arrival time"
            return True, None
        except (ValueError, TypeError):
            return False, "Invalid time format"
    
    @staticmethod
    def validate_location_name(name):
        """Validate location name"""
        if not name or len(name.strip()) == 0:
            return False, "Location name cannot be empty"
        if len(name) > 100:
            return False, "Location name too long (max 100 characters)"
        return True, None
    
    @staticmethod
    def validate_route_name(name):
        """Validate a route name"""
        if not name or len(name.strip()) == 0:
            return False, "Route name cannot be empty"
        if len(name.strip()) > 100:
            return False, "Route name too long (max 100 characters)"
        return True, None

    @staticmethod
    def validate_model_route(model_route, known_routes=None):
        """
        Validate the trained-model route a new route is based on.

        The encoders only know the routes the model was fitted on, so a new
        route has to borrow one of them.
        """
        if not model_route or len(str(model_route).strip()) == 0:
            return False, "Model route is required"
        if known_routes and model_route not in known_routes:
            return False, f"Model route must be one of: {', '.join(known_routes)}"
        return True, None

    @staticmethod
    def validate_model_stop(label, known_stops=None):
        """Validate a stop label the trained model understands"""
        if not label or len(str(label).strip()) == 0:
            return False, "Stop is required"
        if known_stops and label not in known_stops:
            return False, f"Stop must be one of: {', '.join(known_stops)}"
        return True, None

    @staticmethod
    def validate_stop_names(names):
        """
        Validate a list of stop names for a new route.

        Returns the cleaned list (blank lines removed) and a list of errors.
        """
        errors = []
        cleaned = []

        for raw in names or []:
            name = str(raw).strip()
            if not name:
                continue
            if len(name) > 100:
                errors.append(f"Stop name '{name[:20]}...' is too long (max 100 characters)")
                continue
            if name.lower() in [n.lower() for n in cleaned]:
                errors.append(f"Duplicate stop name: '{name}'")
                continue
            cleaned.append(name)

        return cleaned, errors

    @staticmethod
    def validate_stop_sequence(sequence):
        """Validate stop sequence number"""
        try:
            seq = int(sequence)
            if seq < 1:
                return False, "Stop sequence must be a positive number"
            return True, None
        except (ValueError, TypeError):
            return False, "Stop sequence must be a number"
    
    @staticmethod
    def validate_crowd_level(level):
        """Validate crowd level"""
        valid_levels = ["Low", "Medium", "High"]
        if level not in valid_levels:
            return False, f"Crowd level must be one of: {', '.join(valid_levels)}"
        return True, None
    
    @staticmethod
    def validate_arrival_record(route_id, location_id, arrival_time, arrival_date,
                               departure_time=None, crowd_level=None,
                               tz_offset_minutes=None):
        """Validate all fields for arrival record"""
        errors = []

        # Validate times
        valid, msg = InputValidator.validate_time(arrival_time)
        if not valid:
            errors.append(msg)

        if departure_time:
            valid, msg = InputValidator.validate_time(departure_time)
            if not valid:
                errors.append(msg)

        # Validate date
        valid, msg = InputValidator.validate_date(arrival_date)
        if not valid:
            errors.append(msg)

        # Check not in future
        valid, msg = InputValidator.validate_not_future(
            arrival_date, arrival_time, tz_offset_minutes
        )
        if not valid:
            errors.append(msg)
        
        # Check departure before arrival
        if departure_time:
            valid, msg = InputValidator.validate_departure_before_arrival(departure_time, arrival_time)
            if not valid:
                errors.append(msg)
        
        # Validate crowd level
        if crowd_level:
            valid, msg = InputValidator.validate_crowd_level(crowd_level)
            if not valid:
                errors.append(msg)
        
        # Validate route and location are provided and numeric
        if route_id is None or location_id is None:
            errors.append("Route and location are required")
        else:
            try:
                int(route_id)
                int(location_id)
            except (ValueError, TypeError):
                errors.append("Invalid route or location ID")
        
        if errors:
            return False, errors
        return True, None

validator = InputValidator()
