# ByaHero - Smart Commute Predictor

A comprehensive mini bus transportation system for Digos City with travel time predictions and real-time bus arrival tracking.

## Features

### Core Functionality

- **Commute Time Prediction**: Predict travel time based on route, time, day, crowd level, and destination
- **Bus Arrival Forecasting**: Estimate when buses will arrive at each stop based on historical data
- **Real Arrival Records**: Record actual bus arrivals with crowd level and optional notes
- **Location Management**: Add new bus stops without modifying code
- **Historical Analytics**: View and analyze all recorded arrivals with filtering and statistics

### Route Structure

Currently supports:
- **Kapatagan to Digos Route**: Kapatagan → Soong → Binaton → Digos Terminal

The system is designed to easily add new routes and stops as needed.

## Installation

### Prerequisites
- Python 3.8+
- pip

### Setup

1. Clone the repository:
```bash
cd /Users/karlofamoso/Documents/vscode\ files/ByaHero
```

2. Create a virtual environment (recommended):
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python3 app.py
```

5. Open your browser to: `http://localhost:3000`

## Usage

### Pages

#### 1. Commute Prediction
- Select route, origin, destination, time, day, and crowd level
- Get estimated travel time and departure recommendation
- View insights based on conditions

#### 2. Bus Arrivals
- Select route and location
- View estimated next arrival time
- See confidence level based on historical data
- View recent arrivals at that location

#### 3. Add Arrival Record
- Record actual bus arrivals with:
  - Route and location
  - Arrival date and time
  - Optional: Departure time, crowd level, notes
- Form validates against:
  - Future arrival times (rejected)
  - Departure before arrival (rejected)
  - Duplicate entries (within 5-minute window)
- Records are saved to `data/bus_arrivals.csv`

#### 4. Manage Locations
- Add new bus stops to routes
- Specify stop sequence (order along route)
- Add optional description
- View all registered locations by route
- Prevents duplicate locations on same route

#### 5. Historical Data
- View all recorded arrivals in table format
- Filter by:
  - Route
  - Location
  - Date range
- View statistics:
  - Total records
  - Locations with data
  - Average travel times
- Data updates in real-time as new records are added

## Data Files

### `data/locations.csv`
Master registry of all bus stops.

**Columns:**
- `location_id`: Unique identifier
- `name`: Stop name (e.g., "Kapatagan")
- `description`: Optional description
- `route_id`: Route this stop belongs to
- `stop_sequence`: Order along the route (1 = first stop)
- `active`: true/false status

**Initial locations:**
1. Kapatagan (Stop 1)
2. Soong (Stop 2)
3. Binaton (Stop 3)
4. Digos Terminal (Stop 4)

### `data/bus_arrivals.csv`
Historical record of actual bus arrivals.

**Columns:**
- `arrival_id`: Unique identifier
- `route_id`: Route ID
- `location_id`: Location ID
- `arrival_time`: Time in HH:MM format
- `arrival_date`: Date in YYYY-MM-DD format
- `departure_time`: Optional departure time
- `crowd_level`: Low, Medium, or High
- `notes`: Optional notes
- `recorded_at`: ISO timestamp of record creation

### `data/commute_data.csv`
Synthetic training data for ML models (300 records).

**Columns:**
- `route`: Route name
- `time`: Time of day (AM/PM format)
- `day`: Day of week
- `stop`: Location name
- `crowd_level`: Low, Medium, High
- `travel_time`: Minutes (target for regression)
- `departure_decision`: leave_now or wait (target for classification)

### `model.pkl`
Trained machine learning models and label encoders:
- `model_time`: RandomForestRegressor for travel time prediction
- `model_depart`: RandomForestClassifier for departure recommendation
- `encoders`: LabelEncoders for categorical features

## API Endpoints

### Predictions

**POST `/api/predict`**
```json
{
  "route": "1",
  "origin": "1",
  "stop": "Digos Terminal",
  "time": "07:30",
  "day": "Monday",
  "crowd": "Medium"
}
```
Response: `{travel_time: 35.2, decision: "wait"}`

### Arrivals

**GET `/api/get-arrivals`**
- Query params: `route_id`, `location_id`, `limit`
- Returns: Array of arrival records

**POST `/api/predict-arrival`**
```json
{
  "route_id": 1,
  "location_id": 2
}
```
Response: Prediction with confidence level

**POST `/api/add-arrival-record`**
```json
{
  "route_id": 1,
  "location_id": 2,
  "arrival_date": "2026-10-13",
  "arrival_time": "07:30",
  "departure_time": "07:15",
  "crowd_level": "Medium",
  "notes": "On schedule"
}
```

### Locations

**GET `/api/get-locations?route_id=1`**
Returns all locations for a route in sequence order

**GET `/api/get-stops-after?route_id=1&stop_id=1`**
Returns stops after a given stop (for forward travel only)

**POST `/api/add-location`**
```json
{
  "route_id": 1,
  "name": "New Stop",
  "stop_sequence": 5,
  "description": "Description",
  "active": true
}
```

### Statistics

**GET `/api/get-statistics?location_id=1`**
Returns arrival statistics for a location

## Machine Learning

### Travel Time Prediction Model

**Type:** RandomForestRegressor

**Features:**
- route (encoded)
- time (encoded, AM/PM format)
- day (encoded)
- stop (encoded)
- crowd_level (encoded: Low/Medium/High)

**Output:** Estimated travel time in minutes

**Training Data:** 300 synthetic records with realistic patterns
- Kapatagan base: 25-40 min
- Tipan base: 30-50 min
- Calinog base: 20-35 min
- High crowd: +5-10 min
- Low crowd: -2-5 min

### Arrival Time Prediction

**Type:** Heuristic (averaging + interval calculation)

**Logic:**
1. For locations with 5+ records: Calculate average arrival time from recent records
2. For locations with 1-4 records: Show "Low confidence" with available data
3. For locations with 0 records: Show "Insufficient data"

**Display:** 
- Last recorded arrival time
- Estimated next arrival time
- Confidence level and record count

### Handling New Locations

When a new location is added:
1. It appears immediately in all dropdowns
2. No crash when selecting it for predictions (uses safe encoding)
3. Arrival predictions show "Insufficient data" until 5+ records collected
4. After sufficient data, predictions become reliable

## Data Persistence

All data is persisted to CSV files:
- New locations added via UI are saved to `data/locations.csv`
- Arrival records are appended to `data/bus_arrivals.csv`
- Changes persist across app restarts

## Validation

### Input Validation

**Arrival Records:**
- Time format: HH:MM (24-hour)
- Date format: YYYY-MM-DD
- No future arrivals allowed
- Departure time must be before arrival time
- Prevents duplicate entries (within 5-minute window)

**Locations:**
- Name cannot be empty or exceed 100 characters
- Prevents duplicate names on same route
- Stop sequence must be positive integer

## Design

### UI/UX Principles

- **Clean and Professional:** No icons or emojis, text labels only
- **Minimalist Design:** Soft colors, simple borders, clear hierarchy
- **Responsive:** Works on desktop, tablet, and mobile
- **Accessible:** Clear labels, good contrast, keyboard navigation
- **Fast:** Lightweight design with minimal dependencies

### Color Scheme

- **Primary:** Deep blue (#1f4788)
- **Success:** Green (#10b981)
- **Warning:** Orange (#f59e0b)
- **Danger:** Red (#ef4444)
- **Background:** White/light gray
- **Text:** Dark gray/black

## Project Structure

```
ByaHero/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── data/
│   ├── routes_config.py       # Route definitions
│   ├── locations.csv          # Location registry
│   ├── bus_arrivals.csv       # Arrival records
│   └── commute_data.csv       # Training data
├── utils/
│   ├── data_manager.py        # CSV operations
│   └── validators.py          # Input validation
├── models/
│   ├── model.pkl              # Trained models
│   └── arrival_predictor.py   # Arrival predictions
├── templates/
│   ├── base.html              # Base template with nav
│   ├── index.html             # Commute prediction
│   ├── bus_arrivals.html      # Arrival forecasting
│   ├── add_arrival.html       # Record form
│   ├── manage_locations.html  # Location management
│   └── historical_data.html   # Analytics
└── static/
    ├── css/
    │   └── style.css          # Styling (no icons)
    └── js/
        └── script.js          # Frontend logic
```

## Troubleshooting

### Port Already in Use
If port 3000 is in use:
```bash
# Find process using port 3000
lsof -i :3000
# Kill the process
kill -9 <PID>
```

### CSS Not Loading
Clear browser cache (Ctrl+Shift+Delete or Cmd+Shift+Delete)

### No Arrival Predictions
Add more arrival records (need minimum 1-5 depending on location)

### Location Not Appearing in Dropdowns
Check that location is set to `active: true` in `data/locations.csv`

## Future Enhancements

- Real GPS data integration
- Mobile app for recording arrivals
- SMS notifications for schedule changes
- Route optimization suggestions
- Real-time crowd level updates
- Weather impact on travel times
- Historical trend analysis
- Integration with mobile ticketing

## Technical Details

**Framework:** Flask 2.3.2
**ML Library:** scikit-learn 1.3.0
**Data Processing:** pandas 2.0.3
**Frontend:** Vanilla JavaScript (no frameworks)
**Styling:** CSS 3 with CSS variables
**Database:** CSV files (simple, portable, versionable)

## Testing the Application

### Test Commute Prediction
1. Go to "Commute Prediction"
2. Select: Kapatagan to Digos route, Kapatagan origin, Binaton destination
3. Select: 7:00 AM, Monday, Medium crowd
4. Click "Get Prediction"
5. Should show travel time ~32 minutes, "You Can Wait"

### Test Adding Arrival Record
1. Go to "Add Arrival Record"
2. Select: Kapatagan to Digos, Soong location
3. Today's date, 7:15 AM, Medium crowd
4. Click "Save Arrival Record"
5. Go to "Bus Arrivals" and select Soong - should see new record

### Test Adding New Location
1. Go to "Manage Locations"
2. Route: Kapatagan to Digos, Name: "Nueva", Stop Sequence: 5
3. Click "Add Location"
4. Refresh page - Nueva should appear in locations list
5. Go to "Bus Arrivals" - Nueva should be available in location dropdown

## Support

For issues or questions, check:
1. Browser console for JavaScript errors
2. Flask server output for backend errors
3. Data files for corruption or malformed CSV
4. Ensure all dependencies are installed: `pip install -r requirements.txt`

## License

MIT

## Author

ByaHero Team - Digos City Smart Transportation
