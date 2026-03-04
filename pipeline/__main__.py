import argparse
import sys
from pathlib import Path

from pipeline.log import get_logger
from pipeline.config import load_config, setup_wizard

log = get_logger("main")


def run_pipeline(args) -> None:
    from pipeline.state import PipelineState
    from pipeline.research import research_topic
    from pipeline.draft import generate_draft
    from pipeline.broll import generate_broll
    from pipeline.voiceover import generate_voiceover
    from pipeline.captions import generate_captions
    from pipeline.music import pick_music
    from pipeline.assemble import assemble_video
    from pipeline.thumbnail import generate_thumbnail
    from pipeline.upload import upload_to_youtube

    cfg = load_config()

    # Resolve topic
    topic = args.topic
    if not topic and args.discover:
        topic = _discover_topic(args.auto_pick)
    if not topic:
        print("Error: provide --topic or --discover")
        sys.exit(1)

    log.info(f"Starting pipeline for topic: {topic}")

    # Resume or create new state
    if hasattr(args, "job") and args.job:
        state = PipelineState.load(args.job)
    else:
        state = PipelineState.new(topic)

    job_dir = state.job_dir
    log.info(f"Job ID: {state.job_id} | Output: {job_dir}")

    force = getattr(args, "force", False)

    # Stage 1: Research
    if force or not state.is_done("research"):
        research = research_topic(topic)
        state.mark_done("research", research=research)
    else:
        research = state.artifact("research")
        log.info("Skipping research (already done)")

    # Stage 2: Draft (script generation)
    if force or not state.is_done("draft"):
        channel_context = cfg.get("channel_context", "")
        draft = generate_draft(topic, research, channel_context)
        state.draft = draft
        state.mark_done("draft")
    else:
        draft = state.draft
        log.info("Skipping draft (already done)")

    # Stage 3: B-roll images
    if force or not state.is_done("broll"):
        frames = generate_broll(draft["broll_prompts"], job_dir)
        state.mark_done("broll", frames=[str(f) for f in frames])
    else:
        frames = [Path(f) for f in state.artifact("frames") or []]
        log.info("Skipping broll (already done)")

    # Stage 4: Voiceover
    if force or not state.is_done("voiceover"):
        voiceover = generate_voiceover(draft["script"], job_dir)
        state.mark_done("voiceover", voiceover=str(voiceover))
    else:
        voiceover = Path(state.artifact("voiceover"))
        log.info("Skipping voiceover (already done)")

    # Stage 5: Captions
    if force or not state.is_done("captions"):
        ass_path, srt_path = generate_captions(voiceover, job_dir)
        state.mark_done("captions", captions_ass=str(ass_path), captions_srt=str(srt_path))
    else:
        ass_path = Path(state.artifact("captions_ass"))
        srt_path = Path(state.artifact("captions_srt"))
        log.info("Skipping captions (already done)")

    # Stage 6: Music
    if force or not state.is_done("music"):
        music = pick_music()
        state.mark_done("music", music=str(music) if music else "")
    else:
        music_str = state.artifact("music")
        music = Path(music_str) if music_str else None
        log.info("Skipping music selection (already done)")

    # Stage 7: Assemble
    if force or not state.is_done("assemble"):
        final_video = assemble_video(frames, voiceover, music, ass_path, job_dir, state.job_id)
        state.mark_done("assemble", final_video=str(final_video))
    else:
        final_video = Path(state.artifact("final_video"))
        log.info("Skipping assemble (already done)")

    # Stage 8: Thumbnail
    if force or not state.is_done("thumbnail"):
        thumbnail = generate_thumbnail(
            draft.get("thumbnail_prompt", topic),
            draft.get("youtube_title", topic),
            job_dir,
        )
        state.mark_done("thumbnail", thumbnail=str(thumbnail))
    else:
        thumbnail = Path(state.artifact("thumbnail"))
        log.info("Skipping thumbnail (already done)")

    # Stage 9: Upload
    if args.dry_run:
        log.info(f"DRY RUN — skipping upload. Video: {final_video}")
        print(f"\n✓ Video ready (dry run): {final_video}")
        return

    if force or not state.is_done("upload"):
        url = upload_to_youtube(final_video, draft, srt_path, thumbnail)
        state.mark_done("upload", youtube_url=url)
        print(f"\n✓ Uploaded: {url}")
    else:
        url = state.artifact("youtube_url")
        log.info("Skipping upload (already done)")
        print(f"\n✓ Already uploaded: {url}")


def _discover_topic(auto_pick: bool) -> str:
    from topics.reddit import get_reddit_topics
    from topics.trends import get_google_trends

    topics = []
    try:
        topics += get_reddit_topics()
    except Exception as e:
        log.warning(f"Reddit topics failed: {e}")
    try:
        topics += get_google_trends()
    except Exception as e:
        log.warning(f"Google Trends failed: {e}")

    if not topics:
        print("Could not discover any topics. Try --topic instead.")
        sys.exit(1)

    # Deduplicate
    seen = set()
    unique = []
    for t in topics:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)

    if auto_pick:
        topic = unique[0]
        log.info(f"Auto-selected topic: {topic}")
        return topic

    print("\nDiscovered topics:")
    for i, t in enumerate(unique[:15], 1):
        print(f"  {i:2}. {t}")
    while True:
        choice = input("\nPick a number (or press Enter for #1): ").strip()
        if not choice:
            return unique[0]
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(unique):
                return unique[idx]
        except ValueError:
            pass
        print("Invalid choice, try again.")


def cmd_topics(args) -> None:
    from topics.reddit import get_reddit_topics
    from topics.trends import get_google_trends

    topics = []
    try:
        topics += get_reddit_topics(limit=args.limit // 2)
    except Exception as e:
        print(f"Reddit: {e}")
    try:
        topics += get_google_trends(limit=args.limit // 2)
    except Exception as e:
        print(f"Trends: {e}")

    print(f"\nDiscovered {len(topics)} topics:")
    for i, t in enumerate(topics[:args.limit], 1):
        print(f"  {i:2}. {t}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="YouTube Shorts auto-deploy pipeline",
    )
    sub = parser.add_subparsers(dest="command")

    # run
    run_p = sub.add_parser("run", help="Run the full pipeline")
    run_p.add_argument("--topic", help="Topic to create a Short about")
    run_p.add_argument("--discover", action="store_true", help="Auto-discover trending topic")
    run_p.add_argument("--auto-pick", action="store_true", help="Auto-select topic without prompt")
    run_p.add_argument("--dry-run", action="store_true", help="Skip upload step")
    run_p.add_argument("--force", action="store_true", help="Re-run all stages")
    run_p.add_argument("--verbose", action="store_true", help="Verbose logging")

    # resume
    resume_p = sub.add_parser("resume", help="Resume an interrupted job")
    resume_p.add_argument("--job", required=True, help="Job ID to resume")
    resume_p.add_argument("--dry-run", action="store_true")
    resume_p.add_argument("--force", action="store_true")

    # topics
    topics_p = sub.add_parser("topics", help="List discovered topics")
    topics_p.add_argument("--limit", type=int, default=20)

    # setup
    sub.add_parser("setup", help="Run the setup wizard")

    args = parser.parse_args()

    if args.command == "setup":
        setup_wizard()
    elif args.command == "topics":
        cmd_topics(args)
    elif args.command == "run":
        run_pipeline(args)
    elif args.command == "resume":
        args.topic = None
        args.discover = False
        args.auto_pick = False
        run_pipeline(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
