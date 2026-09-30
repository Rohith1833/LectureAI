import os
import sys

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set all isolated configuration variables before any application imports
os.environ["PORT"] = "8001"
os.environ["DATABASE_URL"] = (
    "sqlite:///C:/Users/rohit/.gemini/antigravity-ide/brain/8d485f93-7a2a-49ba-b72d-3fa779158f26/scratch/storage_phase6a/isolated_lectureai.db"
)
os.environ["LECTUREAI_STORAGE_ROOT"] = (
    r"C:\Users\rohit\.gemini\antigravity-ide\brain\8d485f93-7a2a-49ba-b72d-3fa779158f26\scratch\storage_phase6a"
)
os.environ["LECTUREAI_ARTIFACTS_DIR"] = (
    r"C:\Users\rohit\.gemini\antigravity-ide\brain\8d485f93-7a2a-49ba-b72d-3fa779158f26\scratch\storage_phase6a\artifacts"
)
os.environ["LLM_PROVIDER"] = "mock"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:5174,http://127.0.0.1:5174"

if __name__ == "__main__":
    import uvicorn
    from app.main import app

    print("Starting isolated LectureAI backend on port 8001...")
    print(f"DATABASE_URL={os.environ['DATABASE_URL']}")
    print(f"LECTUREAI_STORAGE_ROOT={os.environ['LECTUREAI_STORAGE_ROOT']}")
    print(f"LECTUREAI_ARTIFACTS_DIR={os.environ['LECTUREAI_ARTIFACTS_DIR']}")
    print(f"LLM_PROVIDER={os.environ['LLM_PROVIDER']}")
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
