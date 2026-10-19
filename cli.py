import argparse
import sys
import time
from pathlib import Path

from backend.app.config import settings
from backend.app.modules.ingestion.job_store import JobStore, JobStatus
from backend.app.pipeline import PipelineOrchestrator


def cmd_process(args):
    source = args.source.strip()
    if not source:
        print("[ERROR] Please provide a valid video URL or local file path.")
        sys.exit(1)

    store = JobStore(settings.WORKSPACE_DIR)
    source_type = "url" if source.startswith("http://") or source.startswith("https://") else "local"
    manifest = store.create_job(source_input=source, source_type=source_type)

    print(f"\n=======================================================")
    print(f"  PillarPrism Repurposing Pipeline")
    print(f"  Job ID: {manifest.job_id}")
    print(f"  Source: {source} ({source_type})")
    print(f"=======================================================\n")

    orchestrator = PipelineOrchestrator(job_store=store)

    def on_progress(p: float, step: str):
        bar_len = 30
        filled = int(round(p * bar_len))
        bar = "=" * filled + "-" * (bar_len - filled)
        print(f"[{bar}] {int(p*100):3d}% | {step}")

    try:
        final_manifest = orchestrator.run_pipeline(manifest.job_id, progress_callback=on_progress)
        print("\n[SUCCESS] Pipeline completed successfully!")
        print(f"Rendered {len(final_manifest.clips)} vertical shorts in: {store.get_job_dir(manifest.job_id) / 'clips'}")
        for c in final_manifest.clips:
            print(f"  - [{c.id}] {c.title} ({c.duration:.1f}s, Hook Score: {c.hook_score}/100)")
        print(f"\nSocial copy generated for LinkedIn, X (Twitter), and Newsletter.")
    except Exception as e:
        print(f"\n[FAILED] Pipeline encountered an error: {e}")
        sys.exit(1)


def cmd_list(args):
    store = JobStore(settings.WORKSPACE_DIR)
    jobs = store.list_jobs()
    if not jobs:
        print("No jobs found in workspace.")
        return

    print(f"\n{'JOB ID':<15} {'STATUS':<12} {'PROGRESS':<10} {'CLIPS':<8} {'SOURCE'}")
    print("-" * 75)
    for j in jobs:
        clip_count = len(j.clips)
        print(f"{j.job_id:<15} {j.status.value:<12} {int(j.progress*100):>3}%      {clip_count:<8} {j.source_input[:35]}")


def cmd_status(args):
    store = JobStore(settings.WORKSPACE_DIR)
    try:
        j = store.get_job(args.job_id)
        print(f"Job ID:      {j.job_id}")
        print(f"Status:      {j.status.value} ({int(j.progress*100)}%)")
        print(f"Step:        {j.current_step}")
        print(f"Source:      {j.source_input}")
        print(f"Clips:       {len(j.clips)}")
        if j.error:
            print(f"Error:       {j.error}")
    except FileNotFoundError:
        print(f"Job '{args.job_id}' not found.")


def main():
    parser = argparse.ArgumentParser(description="PillarPrism Headless Automation CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Process command
    p_proc = subparsers.add_parser("process", help="Process a long-form video into vertical shorts and social copy")
    p_proc.add_argument("source", help="URL or local path to video file")
    p_proc.set_defaults(func=cmd_process)

    # List command
    p_list = subparsers.add_parser("list", help="List all jobs in workspace")
    p_list.set_defaults(func=cmd_list)

    # Status command
    p_stat = subparsers.add_parser("status", help="Check status of a specific job")
    p_stat.add_argument("job_id", help="Job ID")
    p_stat.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
