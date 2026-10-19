import argparse
import sys
import time
from pathlib import Path

from backend.app.config import settings
from backend.app.modules.ingestion.job_store import JobStore, JobStatus
from backend.app.pipeline import PipelineOrchestrator
from backend.app.modules.discovery.finder import discover_copyright_free_videos
from backend.app.modules.publishing.dispatcher import SocialDispatcher
from backend.app.modules.publishing.schemas import PublishRequest


def cmd_discover(args):
    query = args.query.strip()
    print(f"\nSearching for copyright-free / Creative Commons videos for: '{query}'...")
    results = discover_copyright_free_videos(query=query, max_results=args.max)
    if not results:
        print("No copyright-free videos found.")
        return

    print(f"\n{'ID':<15} {'PLATFORM':<16} {'DURATION':<10} {'TITLE'}")
    print("-" * 80)
    for r in results:
        print(f"{r.id:<15} {r.source_platform:<16} {r.duration_formatted:<10} {r.title[:38]}")
        print(f"  URL: {r.url}")
        print(f"  License: {r.license_type}")
        print()


def cmd_process(args):
    source = args.source.strip()
    if not source:
        print("[ERROR] Please provide a valid video URL or local file path.")
        sys.exit(1)

    store = JobStore(settings.WORKSPACE_DIR)
    source_type = "url" if source.startswith("http://") or source.startswith("https://") else "local"
    target_clips = max(1, min(10, args.clips))

    manifest = store.create_job(
        source_input=source,
        source_type=source_type,
        target_clip_count=target_clips
    )

    print(f"\n=======================================================")
    print(f"  PillarPrism Repurposing Pipeline")
    print(f"  Job ID: {manifest.job_id}")
    print(f"  Source: {source} ({source_type})")
    print(f"  Target Clip Count: {target_clips}")
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
        print(f"Status: {final_manifest.approval_status}")
        print(f"Rendered {len(final_manifest.clips)} vertical shorts in: {store.get_job_dir(manifest.job_id) / 'clips'}")
        for c in final_manifest.clips:
            print(f"  - [{c.id}] {c.title} ({c.duration:.1f}s, Hook Score: {c.hook_score}/100)")
        print(f"\nSocial copy generated for LinkedIn, X (Twitter), and Newsletter.")
        print(f"Ready for review! Run: 'python cli.py publish {manifest.job_id}' to distribute.")
    except Exception as e:
        print(f"\n[FAILED] Pipeline encountered an error: {e}")
        sys.exit(1)


def cmd_publish(args):
    store = JobStore(settings.WORKSPACE_DIR)
    try:
        manifest = store.get_job(args.job_id)
    except FileNotFoundError:
        print(f"[ERROR] Job '{args.job_id}' not found.")
        sys.exit(1)

    platforms = args.platforms.split(",") if args.platforms else ["youtube_shorts", "twitter", "linkedin"]
    dispatcher = SocialDispatcher()
    req = PublishRequest(platforms=platforms, simulate=args.simulate)
    
    print(f"\nPublishing job {manifest.job_id} to: {', '.join(platforms)}...")
    results = dispatcher.dispatch(manifest, req)
    store.save_manifest(manifest)

    for r in results:
        status_label = f"[{r.status}]"
        print(f"  {status_label:<12} {r.platform:<16} {r.post_url or r.message}")
    print("\nPublishing dispatch complete.")


def cmd_list(args):
    store = JobStore(settings.WORKSPACE_DIR)
    jobs = store.list_jobs()
    if not jobs:
        print("No jobs found in workspace.")
        return

    print(f"\n{'JOB ID':<15} {'STATUS':<12} {'APPROVAL':<18} {'CLIPS':<8} {'SOURCE'}")
    print("-" * 80)
    for j in jobs:
        clip_count = len(j.clips)
        print(f"{j.job_id:<15} {j.status.value:<12} {j.approval_status:<18} {clip_count:<8} {j.source_input[:25]}")


def cmd_status(args):
    store = JobStore(settings.WORKSPACE_DIR)
    try:
        j = store.get_job(args.job_id)
        print(f"Job ID:          {j.job_id}")
        print(f"Status:          {j.status.value} ({int(j.progress*100)}%)")
        print(f"Approval:        {j.approval_status}")
        print(f"Step:            {j.current_step}")
        print(f"Source:          {j.source_input}")
        print(f"Target Clips:    {j.target_clip_count}")
        print(f"Rendered Clips:  {len(j.clips)}")
        if j.published_records:
            print(f"Published Posts: {len(j.published_records)}")
        if j.error:
            print(f"Error:           {j.error}")
    except FileNotFoundError:
        print(f"Job '{args.job_id}' not found.")


def main():
    parser = argparse.ArgumentParser(description="PillarPrism Autonomous Content Studio CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Discover command
    p_disc = subparsers.add_parser("discover", help="Search for copyright-free / Creative Commons videos")
    p_disc.add_argument("query", help="Keyword or niche topic to search")
    p_disc.add_argument("--max", type=int, default=5, help="Max results to fetch")
    p_disc.set_defaults(func=cmd_discover)

    # Process command
    p_proc = subparsers.add_parser("process", help="Repurpose a long video into vertical shorts and copy")
    p_proc.add_argument("source", help="URL or local path to video file")
    p_proc.add_argument("--clips", type=int, default=3, help="How many repurpose clips to generate (1-10)")
    p_proc.set_defaults(func=cmd_process)

    # Publish command
    p_pub = subparsers.add_parser("publish", help="Publish approved content to social platforms")
    p_pub.add_argument("job_id", help="Job ID to publish")
    p_pub.add_argument("--platforms", default="youtube_shorts,twitter,linkedin", help="Comma-separated platforms")
    p_pub.add_argument("--simulate", action="store_true", help="Simulate publishing without posting")
    p_pub.set_defaults(func=cmd_publish)

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
