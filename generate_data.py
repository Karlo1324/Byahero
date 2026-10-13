import pandas as pd
import random

# Kapatagan barangays to Digos Terminal routes
routes = [
    "Barangay Kapatagan-Digos Terminal",
    "Barangay Calinog-Digos Terminal",
    "Barangay Tipan-Digos Terminal"
]

# Pickup and destination points
stops = [
    "Digos Terminal",
    "Barangay Kapatagan",
    "Barangay Calinog",
    "Barangay Tipan"
]

days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
crowds = ["Low", "Medium", "High"]
times_of_day = ["6:00 AM", "7:00 AM", "8:00 AM", "9:00 AM", "10:00 AM", "11:00 AM",
                "12:00 PM", "1:00 PM", "2:00 PM", "3:00 PM", "4:00 PM", "5:00 PM",
                "6:00 PM", "7:00 PM", "8:00 PM"]

data = []

for i in range(300):
    route = random.choice(routes)
    time_str = random.choice(times_of_day)
    day = random.choice(days)
    stop = random.choice(stops)
    crowd = random.choice(crowds)

    # SMART LOGIC (IMPORTANT 🔥)
    # Different barangays have different distances to terminal
    if "Kapatagan" in route:
        base_time = random.randint(25, 40)
    elif "Tipan" in route:
        base_time = random.randint(30, 50)
    else:  # Calinog
        base_time = random.randint(20, 35)

    # Crowd level affects travel time
    if crowd == "High":
        travel_time = base_time + random.randint(5, 10)
    elif crowd == "Medium":
        travel_time = base_time
    else:
        travel_time = base_time - random.randint(2, 5)

    # Decision logic based on crowd level
    if crowd == "High":
        decision = "leave_now"
    else:
        decision = "wait"

    data.append([route, time_str, day, stop, crowd, travel_time, decision])

df = pd.DataFrame(data, columns=[
    "route","time","day","stop","crowd_level","travel_time","departure_decision"
])

df.to_csv("commute_data.csv", index=False)

print("✅ 300 rows generated - Kapatagan to Digos Terminal routes!")
