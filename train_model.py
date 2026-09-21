import pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import pickle

df = pd.read_csv("commute_data.csv")

encoders = {}

# Encode text columns
for col in ["route","day","stop","crowd_level","departure_decision"]:
    le = LabelEncoder()
    df[col] = le.fit_transform(df[col])
    encoders[col] = le

# FEATURES
X = df[["route","time","day","stop","crowd_level"]]

# TARGETS
y_time = df["travel_time"]
y_depart = df["departure_decision"]

# MODELS
model_time = RandomForestRegressor()
model_depart = RandomForestClassifier()

# TRAIN
model_time.fit(X, y_time)
model_depart.fit(X, y_depart)

# SAVE EVERYTHING
pickle.dump({
    "model_time": model_time,
    "model_depart": model_depart,
    "encoders": encoders
}, open("model.pkl","wb"))

print("✅ 2 models trained and saved!")