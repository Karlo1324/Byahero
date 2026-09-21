import pandas as pd
import random

routes = ["kapatagan-digos", "kapatagan-binaton", "kapatagan-soong",
          "stacruz-digos", "stacruz-binaton", "stacruz-soong"]

days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
stops = ["Digos","Binaton","Soong"]
crowds = ["Low","Medium","High"]

data = []

for i in range(300):
    route = random.choice(routes)
    time = random.randint(6, 20)
    day = random.choice(days)
    stop = random.choice(stops)
    crowd = random.choice(crowds)

    # SMART LOGIC (IMPORTANT 🔥)
    if "kapatagan" in route:
        base_time = random.randint(35, 55)
    else:
        base_time = random.randint(20, 35)

    if crowd == "High":
        travel_time = base_time + random.randint(5, 10)
    elif crowd == "Medium":
        travel_time = base_time
    else:
        travel_time = base_time - random.randint(3, 8)

    data.append([route, time, day, stop, crowd, travel_time])

df = pd.DataFrame(data, columns=[
    "route","time","day","stop","crowd_level","travel_time"
])

if crowd == "High":
    decision = "leave_now"
else:
    decision = "wait"
df.to_csv("commute_data.csv", index=False)

print("✅ 300 rows generated!")