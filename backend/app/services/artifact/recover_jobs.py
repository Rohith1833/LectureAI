"""
Offline recovery utility for interrupted LectureAI artifact jobs.

Policy:
- Must only be run when background workers / web server processes are stopped,
  to avoid terminating healthy jobs running on another worker.
- Scans for jobs stuck in transitional states (PLANNING, RENDERING, and optionally PENDING).
- Transitions them to FAILED with a clear, actionable explanation.
- Cleans up any incomplete/corrupt artifact files on disk.
- COMPLETED and existing FAILED jobs are never modified. Completed artifacts remain untouched.
- Interrupted jobs are not automatically resumed to avoid silent token charges or duplicate artifacts.

Usage:
    python -m app.services.artifact.recover_jobs [--include-pending] [--dry-run]
"""

import argparse
import sys
from app.db.session import SessionLocal
from app.services.artifact.artifact_service import ArtifactService
from app.models.artifact import ArtifactJob, ArtifactStatus


def main():
    parser = argparse.ArgumentParser(
        description="Offline recovery tool for interrupted LectureAI artifact generation jobs."
    )
    parser.add_argument(
        "--include-pending",
        action="store_true",
        help="Also recover jobs stuck in PENDING status."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List stranded jobs without modifying database or files."
    )
    args = parser.parse_args()

    print("=" * 60)
    print("LectureAI Offline Artifact Job Recovery")
    print("POLICY: Only execute when all active workers/servers are STOPPED.")
    print("=" * 60)

    db = SessionLocal()
    try:
        target_statuses = [ArtifactStatus.PLANNING.value, ArtifactStatus.RENDERING.value]
        if args.include_pending:
            target_statuses.append(ArtifactStatus.PENDING.value)

        stranded = db.query(ArtifactJob).filter(ArtifactJob.status.in_(target_statuses)).all()
        print(f"Target statuses: {', '.join(target_statuses)}")
        print(f"Found {len(stranded)} stranded job(s).")

        for job in stranded:
            print(f"  - Job ID: {job.id} | Status: {job.status} | Created: {job.created_at}")

        if args.dry_run:
            print("\n[DRY RUN] No changes were applied.")
            return

        if not stranded:
            print("\nNo stranded jobs to recover.")
            return

        service = ArtifactService(db)
        recovered_count = service.recover_interrupted_jobs(include_pending=args.include_pending)
        print(f"\nSuccessfully transitioned {recovered_count} job(s) to FAILED status.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
