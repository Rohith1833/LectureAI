import os

# Base directory of the app package (the app/ directory)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Central storage paths
STORAGE_ROOT = os.path.join(APP_DIR, "storage")
UPLOADS_DIR = os.path.join(STORAGE_ROOT, "uploads")
METADATA_DIR = os.path.join(STORAGE_ROOT, "metadata")
JOBS_DIR = os.path.join(STORAGE_ROOT, "jobs")

# Ensure all central storage directories exist automatically on startup
os.makedirs(STORAGE_ROOT, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(METADATA_DIR, exist_ok=True)
os.makedirs(JOBS_DIR, exist_ok=True)
