import requests
import time
import sys
import os

BASE_URL = "http://localhost:8001/api/v1"

def wait_for_job(job_id, desc=""):
    print(f"Waiting for {desc} (Job: {job_id})...")
    while True:
        resp = requests.get(f"{BASE_URL}/jobs/{job_id}")
        resp.raise_for_status()
        status = resp.json().get("data", {}).get("status")
        print(f"Status: {status}")
        if status and status.upper() == "COMPLETED":
            return
        elif status and status.upper() == "FAILED":
            raise Exception(f"{desc} failed: {resp.json()}")
        time.sleep(2)

def main():
    pdf_path = r"C:\Users\rohit\.gemini\antigravity-ide\brain\8d485f93-7a2a-49ba-b72d-3fa779158f26\scratch\sample.pdf"
    
    # 1. Upload PDF
    print(f"Uploading {pdf_path}")
    with open(pdf_path, "rb") as f:
        resp = requests.post(f"{BASE_URL}/upload", files={"file": ("sample.pdf", f, "application/pdf")})
    resp.raise_for_status()
    upload_id = resp.json()["data"]["upload_id"]
    print(f"Upload ID: {upload_id}")

    # 2. Start extraction job
    print("Starting extraction job...")
    resp = requests.post(f"{BASE_URL}/jobs", json={"upload_id": upload_id})
    resp.raise_for_status()
    job_id = resp.json()["data"]["job_id"]
    
    wait_for_job(job_id, "Extraction")

    # 2.5 Get Document ID
    print("Getting Document ID...")
    resp = requests.get(f"{BASE_URL}/documents/upload/{upload_id}")
    resp.raise_for_status()
    doc_id = resp.json()["data"]["id"]
    print(f"Document ID: {doc_id}")

    # 3. Approve review
    print("Fetching approval readiness to get revision...")
    resp = requests.get(f"{BASE_URL}/academic/review/{upload_id}/approval-readiness")
    resp.raise_for_status()
    revision = resp.json().get("data", {}).get("current_revision", 0)

    print("Accepting all nodes...")
    resp = requests.post(
        f"{BASE_URL}/academic/review/{upload_id}/actions",
        json={
            "action_type": "ACCEPT_ALL_NODES",
            "payload": {},
            "expected_version": revision,
            "comment": "E2E bulk accept"
        }
    )
    resp.raise_for_status()
    
    # We must fetch readiness again because accepting nodes increments the revision
    resp = requests.get(f"{BASE_URL}/academic/review/{upload_id}/approval-readiness")
    resp.raise_for_status()
    new_revision = resp.json().get("data", {}).get("current_revision", 0)

    print("Approving review...")
    resp = requests.post(
        f"{BASE_URL}/academic/review/{upload_id}/approve", 
        json={"expected_revision": new_revision}
    )
    resp.raise_for_status()
    print("Approved.")

    # 4. Get finalized knowledge version
    print("Fetching knowledge versions...")
    # Polling slightly in case compilation is background, but it's likely sync
    version_id = None
    for _ in range(10):
        resp = requests.get(f"{BASE_URL}/knowledge/document/{doc_id}/versions")
        resp.raise_for_status()
        versions = resp.json().get("data", []) if "data" in resp.json() else resp.json()
        finalized = [v for v in versions if v["status"] == "FINALIZED"]
        if finalized:
            version_id = finalized[0]["id"]
            break
        time.sleep(1)

    if not version_id:
        raise Exception("No finalized version found")
    print(f"Version ID: {version_id}")

    # 5. Generate Artifact
    print("Requesting artifact generation...")
    payload = {
        "upload_id": upload_id,
        "knowledge_version_id": version_id,
        "artifact_type": "PPTX",
        "config": {
            "num_units": 1,
            "provider": "mock"
        }
    }
    resp = requests.post(f"{BASE_URL}/artifacts/generate", json=payload)
    resp.raise_for_status()
    job_data = resp.json()
    # The artifact endpoint returns the job in 'data' usually, or directly if it's the schema
    job_id = job_data.get("data", job_data).get("id")
    print(f"Artifact Job ID: {job_id}")

    # 6. Wait for artifact job
    print("Waiting for artifact job to complete...")
    while True:
        resp = requests.get(f"{BASE_URL}/artifacts/{job_id}")
        resp.raise_for_status()
        job_info = resp.json().get("data", resp.json())
        status = job_info.get("status")
        print(f"Job Status: {status}")
        if status and status.upper() == "COMPLETED":
            break
        elif status and status.upper() == "FAILED":
            print(f"Job failed! Error: {job_info.get('error_message')}")
            sys.exit(1)
        time.sleep(2)

    # 7. Download artifact
    print("Downloading artifact...")
    resp = requests.get(f"{BASE_URL}/artifacts/{job_id}/download")
    resp.raise_for_status()
    print(f"Downloaded {len(resp.content)} bytes of artifact data.")
    print("E2E Acceptance Test Passed Successfully!")

if __name__ == "__main__":
    main()
