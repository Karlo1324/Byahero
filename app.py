import streamlit as st
import pickle
import numpy as np

# Load model + encoders
saved_data = pickle.load(open("model.pkl","rb"))
model = saved_data["model"]
encoders = saved_data["encoders"]

st.header("🚍 BiyaHero - Smart Commute AI")
st.markdown("Designed for Digos Mini Bus System")
st.markdown("---")

st.subheader("📍 Enter Your Trip")

# Dynamic dropdowns from dataset
route = st.selectbox("Route", encoders["route"].classes_)
time = st.slider("Time", 5, 20)
day = st.selectbox("Day", encoders["day"].classes_)
stop = st.selectbox("Stop", encoders["stop"].classes_)
crowd = st.selectbox("Crowd Level", encoders["crowd_level"].classes_)

# Prediction
if st.button("Predict"):

    data = np.array([[ 
        encoders["route"].transform([route])[0],
        time,
        encoders["day"].transform([day])[0],
        encoders["stop"].transform([stop])[0],
        encoders["crowd_level"].transform([crowd])[0]
    ]])

    result = model.predict(data)[0]

    st.success(f"🕒 Estimated Travel Time: {round(result, 2)} minutes")

    # Smart logic
    if crowd.lower() == "high":
        st.warning("🚌 Bus may leave soon (almost full)")
    else:
        st.info("🕒 Bus may wait for schedule")

    # Decision system
    if result > 25:
        st.error("🚦 Leave NOW or you will be late")
    elif result > 15:
        st.warning("⏰ Leave soon")
    else:
        st.success("✅ You can wait")