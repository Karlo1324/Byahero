"""
WSGI entry point for Vercel serverless deployment.
"""
import os
import sys

# Add project root to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Ensure data directory exists
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Import the Flask app
from app import app

# Vercel expects the app to be named 'app'
# This is already the case, but we can also export it
application = app

if __name__ == "__main__":
    app.run()