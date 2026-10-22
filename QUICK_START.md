# ByaHero - Quick Start Guide

## Start the App

```bash
cd "/Users/karlofamoso/Documents/vscode files/ByaHero"
python3 app.py
```

Then open: **http://localhost:3000**

## The 5 Pages

### 1. Commute Prediction (Home)
- **What it does:** Predicts travel time from one stop to another
- **How to use:**
  1. Select route: "Kapatagan to Digos"
  2. Select origin: the stops on that route (Kapatagan, Soong, Binaton, Digos Terminal)
  3. Select destination: Only stops after your origin
  4. Select time: Any time of day (6 AM - 8 PM)
  5. Select day: Monday through Sunday
  6. Select crowd level: Low, Medium, or High
  7. Click "Get Prediction"
- **You'll see:** Estimated travel time + recommendation

### 2. Bus Arrivals
- **What it does:** Shows when buses typically arrive at each stop
- **How to use:**
  1. Select route
  2. Select location
  3. Click "Get Arrival Prediction"
- **You'll see:**
  - Last recorded arrival time
  - Estimated next arrival
  - Confidence level ("Insufficient data" to "Reliable")
  - Recent arrivals list

### 3. Add Arrival Record
- **What it does:** Record when a bus actually arrived (real data)
- **How to use:**
  1. Select route and location
  2. Enter date and arrival time
  3. Optional: Add departure time, crowd level, notes
  4. Click "Save Arrival Record"
- **Important:** 
  - Can't record future times
  - Departure time must be before arrival time
  - Prevents duplicate entries (same stop, same time)

### 4. Manage Locations
- **What it does:** Add new bus stops to routes
- **How to use:**
  1. Select route
  2. Enter location name
  3. Enter stop sequence (1 = first, 2 = second, etc.)
  4. Optional: Add description
  5. Click "Add Location"
- **View:** All current locations displayed by route

### 5. Historical Data
- **What it does:** View and analyze all recorded arrivals
- **How to use:**
  1. Filter by route (optional)
  2. Filter by location (optional)
  3. Filter by date range (optional)
  4. View statistics at bottom
- **See:** Total records, locations with data, average times

## Common Tasks

### Record a Bus Arrival
1. Go to "Add Arrival Record"
2. Route: Kapatagan to Digos
3. Location: [Choose a stop]
4. Date: [Today's date]
5. Time: [When the bus arrived in HH:MM format]
6. Crowd: Low/Medium/High
7. Save

### Add a New Bus Stop
1. Go to "Manage Locations"
2. Route: Kapatagan to Digos
3. Name: [Stop name]
4. Sequence: [Number - higher = further along route]
5. Add Location
6. Now it appears in all dropdowns!

### Check Arrival Predictions
1. Go to "Bus Arrivals"
2. Route: Kapatagan to Digos
3. Location: [Choose a stop]
4. Get Arrival Prediction
5. Shows: Last arrival, estimated next arrival, confidence

### View All Recorded Data
1. Go to "Historical Data"
2. See all arrivals in table format
3. Filter by route/location/dates
4. View statistics

## The Route

**Kapatagan to Digos Route:**
```
Kapatagan (Stop 1)
    ↓
Soong (Stop 2)
    ↓
Binaton (Stop 3)
    ↓
Digos Terminal (Stop 4)
```

- You can only travel forward (can't skip stops)
- If you board at Kapatagan, you can get off at: Soong, Binaton, or Digos Terminal
- If you board at Soong, you can get off at: Binaton or Digos Terminal
- If you board at Binaton, you can only get off at: Digos Terminal

## Data Files

All data is saved in the `data/` folder:

- **locations.csv** - All bus stops (add new ones via UI, not this file)
- **bus_arrivals.csv** - Real arrival records (grows as you record arrivals)
- **commute_data.csv** - Training data for predictions (don't edit)
- **routes_config.py** - Route definitions (don't edit)

## Running the Tests

```bash
python3 smoke_test.py
```

Checks every page and API endpoint end to end. The test saves and restores
`data/*.csv`, so your records are left untouched.

## Android App

A native Android build lives in `Byahero/`. It talks to the same API, so run
the server on your computer and point the app at it:

```bash
export BYAHERO_API=http://<your-lan-ip>:3000
```

See `Byahero/README.md` for build instructions.

## Travel Time Predictions

Based on:
- Route (Kapatagan routes take longer than others)
- Time of day (peak hours may vary)
- Day of week
- Crowd level
  - Low crowd: Faster (bus doesn't wait)
  - Medium crowd: Normal
  - High crowd: Slower (bus waits for more passengers)

**Example:** Kapatagan to Binaton at 7 AM with Medium crowd = ~32 minutes

## Arrival Predictions

Shows confidence based on how many arrivals recorded at that location:
- 0 records: "Insufficient data"
- 1-4 records: "Low confidence"
- 5+ records: "Reliable"

The more arrivals you record, the better the predictions!

## Important Rules

✓ **Do This:**
- Record actual arrival times (helps predictions)
- Add new stops as they open
- Check historical data to find patterns
- Use current date format (YYYY-MM-DD)
- Use 24-hour time format (HH:MM, like 14:30 for 2:30 PM)

✗ **Don't Do This:**
- Record future arrival times (system rejects them)
- Add duplicate locations (system prevents it)
- Edit CSV files directly (use the UI instead)
- Record departure time after arrival time (will be rejected)

## Troubleshooting

**App won't start?**
- Check Python is installed: `python3 --version`
- Install dependencies: `pip install -r requirements.txt`
- Check port 3000 isn't in use

**Dropdown empty?**
- Make sure you selected a route first
- Refresh page if needed

**Can't add arrival for new location?**
- First add the location via "Manage Locations"
- Then come back to "Add Arrival Record"

**Predictions seem wrong?**
- Record more arrivals (predictions improve with more data)
- Check that dates/times are correct

**Data disappeared after restart?**
- All data is saved in CSV files
- Should load automatically on app start
- Check `data/` folder for the CSV files

## Next Steps

1. **Explore the app** - Visit each of the 5 pages
2. **Record some arrivals** - Add real bus arrival times
3. **Check predictions** - See how confidence improves
4. **Add locations** - Test adding a new stop
5. **View analytics** - Check historical data trends

## Getting Help

All pages have:
- Clear labels (no icons)
- Error messages if something is wrong
- Success messages after saving
- Intuitive form layouts

If something doesn't work as expected, the error message will tell you why!

---

**Last Updated:** October 13, 2026
**Status:** Ready to use
**Version:** 2.0 - Complete Rewrite
