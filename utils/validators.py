"""
Input Validators for ByaHero
Validates user input for forms and API endpoints
"""

import re
from datetime import datetime, time

class InputValidator:
    
    @staticmethod
    def validate_time(time_str):
        """Validate time format HH:MM"""
        try:
            datetime.strptime(time_str, "%H:%M")
            return True, None
        except ValueError:
            return False, "Invalid time format. Use HH:MM (e.g., 07:30)"
    
    @staticmethod
    def validate_date(date_str):
        """Validate date format YYYY-MM-DD"""
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True, None
        except ValueError:
            return False, "Invalid date format. Use YYYY-MM-DD"
    
    @staticmethod
    def validate_not_future(date_str, time_str):
        """Ensure the datetime is not in the future"""
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            if dt > datetime.now():
                return False, "Cannot record arrival in the future"
            return True, None
        except:
            return False, "Invalid date/time"
    
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
        except:
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
    def validate_stop_sequence(sequence):
        """Validate stop sequence number"""
        try:
            seq = int(sequence)
            if seq < 1:
                return False, "Stop sequence must be a positive number"
            return True, None
        except:
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
                               departure_time=None, crowd_level=None):
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
        valid, msg = InputValidator.validate_not_future(arrival_date, arrival_time)
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
        
        # Validate route and location are numbers
        try:
            int(route_id)
            int(location_id)
        except:
            errors.append("Invalid route or location ID")
        
        if errors:
            return False, errors
        return True, None

validator = InputValidator()
