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


_FALLBACK_TOPICS = [
    # Science & Space
    "Mind-blowing space discoveries in 2025",
    "AI breakthroughs nobody is talking about",
    "Ancient history facts that will blow your mind",
    "How the human brain actually works",
    "Futuristic technologies arriving sooner than you think",
    "Ocean mysteries scientists still cannot explain",
    "Quantum computing explained simply",
    "The world's most extreme natural phenomena",
    "Untold stories from the International Space Station",
    "Strange deep sea creatures discovered recently",
    "How climate change is reshaping the world map",
    "The science behind why music gives you chills",
    "What happens inside a black hole",
    "How CRISPR gene editing will change medicine",
    "The surprising science of déjà vu",
    "Why scientists are excited about nuclear fusion",
    "The mystery of dark matter finally explained",
    "How the James Webb telescope changed astronomy",
    "Why some animals never seem to age",
    "The science of lightning explained simply",
    "What causes northern lights and where to see them",
    "How earthquakes are predicted by scientists today",
    "The strange physics of time dilation",
    "Why the ocean is still mostly unexplored",
    "How satellites keep the internet running",
    "The truth about parallel universes in physics",
    "Why Mars is the next frontier for humanity",
    "How viruses evolved alongside humans for millions of years",
    "The science of supervolcanoes and when they erupt",
    "What would happen if the moon disappeared",
    # Psychology & Mind
    "The psychology of success explained in 60 seconds",
    "Why your memory is less reliable than you think",
    "The psychology of habits and how to change them",
    "The dark side of social media algorithms",
    "How gut bacteria control your mood and decisions",
    "The real reason procrastination happens",
    "Why people believe in conspiracy theories",
    "The science behind falling in love",
    "How color affects your mood and productivity",
    "The psychology of fear and how to overcome it",
    "Why humans are wired to compare themselves to others",
    "The science of confidence and how to build it",
    "How childhood experiences shape adult behavior",
    "The truth about multitasking and your brain",
    "Why first impressions are almost impossible to change",
    "The psychology behind why we buy things we don't need",
    "How your brain makes decisions without you knowing",
    "The surprising psychology of happiness",
    "Why boredom is actually good for creativity",
    "The science of motivation that most people misunderstand",
    "How sleep deprivation changes your personality",
    "Why humans are naturally terrible at risk assessment",
    "The psychology of manipulation and how to spot it",
    "How meditation physically changes your brain",
    "The science of intuition and gut feelings",
    # Health & Fitness
    "The science of sleep and why most people get it wrong",
    "Why walking is the most underrated exercise",
    "The real reason why most diets fail",
    "How your gut controls your mood and brain",
    "Secrets of the world's oldest people",
    "The truth about cold water swimming",
    "Why sitting is the new smoking for your health",
    "The hidden benefits of fasting backed by science",
    "How stress physically damages your body",
    "The surprising effects of cold showers on your health",
    "Why doctors say breakfast might not be the most important meal",
    "How sunlight affects your mental health and hormones",
    "The science of longevity that doctors don't teach",
    "Why strength training is more important than cardio",
    "The truth about supplements most people waste money on",
    "How dehydration secretly affects your brain",
    "The science of why sugar is more addictive than cocaine",
    "Why your posture affects your mood and confidence",
    "The real cause of inflammation and how to reduce it",
    "How breathing techniques can lower anxiety instantly",
    "The surprising link between exercise and memory",
    "Why most people need more vitamin D than they think",
    "The truth about organic food and whether it matters",
    "How gut microbiome determines your health outcomes",
    "The science of why we need 8 hours of sleep",
    # Money & Finance
    "Simple money habits that build real wealth",
    "Hidden habits of billionaires that changed their lives",
    "Life-changing productivity hacks used by CEOs",
    "Why most people stay poor despite working hard",
    "The real reason the rich keep getting richer",
    "How compound interest makes ordinary people millionaires",
    "The psychology of spending money you don't have",
    "Why most people retire broke and how to avoid it",
    "The truth about passive income that gurus won't tell you",
    "How to negotiate your salary and get 20 percent more",
    "The surprising habits of people who achieve financial freedom",
    "Why inflation secretly destroys your savings",
    "How billionaires think about time and money differently",
    "The real cost of buying a house versus renting",
    "Why most small businesses fail in the first year",
    "How credit scores control your financial destiny",
    "The hidden fees that drain your retirement account",
    "Why most investment advice is designed to make others rich",
    "The science of smart decision making when spending",
    "How the world's wealthiest people protect their money",
    # Technology
    "Hidden features in everyday technology",
    "The real story of how the internet was created",
    "How your smartphone knows everything about you",
    "The AI that can clone any voice in seconds",
    "Why electric vehicles are cheaper than gas cars now",
    "How hackers break into your accounts and how to stop them",
    "The chip shortage that changed the entire world economy",
    "Why tech companies know you better than your family",
    "The technology that will replace smartphones in 10 years",
    "How self-driving cars actually work under the hood",
    "The dark side of facial recognition technology",
    "Why 5G is changing everything faster than expected",
    "How renewable energy is finally beating fossil fuels",
    "The robot that can do any job better than humans",
    "Why your old phone data never truly disappears",
    "How deepfake technology is becoming impossible to detect",
    "The real story behind the rise and fall of crypto",
    "Why batteries are the most important technology of this decade",
    "How smart home devices spy on your daily life",
    "The technology that allows humans to control computers with thoughts",
    "Why open source software runs most of the internet",
    "How GPS works and why it changed everything",
    "The algorithm that decides what you see on every app",
    "Why passwords are dead and what replaces them",
    "How the cloud stores all human knowledge",
    # History & Mysteries
    "Ancient civilizations more advanced than we think",
    "The real story behind Cleopatra nobody teaches in school",
    "How the Roman Empire actually fell according to historians",
    "Mysteries of ancient Egypt that science still cannot explain",
    "The forgotten inventions that were ahead of their time",
    "What really caused the extinction of the dinosaurs",
    "The untold story of women who changed history",
    "Conspiracy theories that turned out to be true",
    "The ancient buildings impossible to construct today",
    "How the Silk Road connected the ancient world",
    "The real story of Nikola Tesla and why he was erased",
    "Ancient medical practices that modern science confirms work",
    "The strange disappearances that historians cannot explain",
    "How writing was invented and changed human civilization",
    "The forgotten empires that ruled the world",
    "Ancient astronomical knowledge that baffles modern scientists",
    "The true origin of democracy and how it almost died",
    "How the Black Plague changed the course of history",
    "The real story behind famous historical paintings",
    "Lost cities discovered in the last decade by archaeologists",
    # Nature & Animals
    "How animals sense things humans cannot",
    "Bizarre animal abilities you never knew existed",
    "The most dangerous animals you never knew existed",
    "How trees secretly communicate with each other underground",
    "Why insects are disappearing and why that matters",
    "The intelligence of crows that rivals human children",
    "How dolphins use echolocation with incredible precision",
    "Why some animals hibernate and the science behind it",
    "The most extreme animal migrations on earth",
    "How plants fight back against insects and animals",
    "The secret life of fungi beneath every forest floor",
    "Why ocean coral reefs are disappearing so fast",
    "How bears prepare for winter with stunning biology",
    "The animals that can survive in outer space",
    "Why sharks have survived for 450 million years unchanged",
    "How bees know exactly when flowers will bloom",
    "The mystery of why birds never get lost migrating",
    "How octopus intelligence rivals that of mammals",
    "Why wolves change entire ecosystems when introduced",
    "The endangered species being brought back from extinction",
    # Personal Development
    "The science of confidence and self-belief",
    "Why most people never reach their full potential",
    "The daily routines of the most successful people on earth",
    "How to build discipline when motivation always fails",
    "The surprising benefits of saying no more often",
    "Why rejection makes you stronger according to science",
    "How to develop a growth mindset that changes everything",
    "The real reason why people give up on their dreams",
    "How to train your brain to focus like a champion",
    "The science of willpower and why you keep running out",
    "Why the people you surround yourself with determine success",
    "How to overcome imposter syndrome that holds you back",
    "The morning habits that separate successful people from everyone else",
    "Why reading books makes you more successful according to research",
    "How emotional intelligence predicts success better than IQ",
    "The psychology of resilience and how to build it",
    "Why forgiveness is scientifically proven to improve your life",
    "How to stop overthinking and take action immediately",
    "The power of saying exactly what you mean",
    "Why journaling is one of the most powerful habits",
    # Future & Society
    "How cities of the future will look",
    "The jobs that will disappear in the next 10 years",
    "Why the 4 day work week is becoming mainstream",
    "How AI is changing what it means to be human",
    "The future of food and why we will stop eating meat",
    "Why remote work is reshaping entire cities and economies",
    "How population decline is the real crisis nobody talks about",
    "The countries preparing for climate migration now",
    "Why loneliness has become the biggest health crisis of our time",
    "How social media is rewiring an entire generation",
    "The death of cash and what digital currency means for you",
    "Why trust in institutions is at an all-time low",
    "How the gig economy trapped an entire generation",
    "The surprising countries leading the renewable energy revolution",
    "Why privacy is becoming the luxury good of the future",
    # Food & Lifestyle
    "The surprising origins of your favorite everyday foods",
    "Why coffee is good for you according to new science",
    "The most nutritious foods that cost almost nothing",
    "How your diet affects your mental health more than you think",
    "Why spicy food addicts actually live longer",
    "The science behind why we overeat even when full",
    "How fermented foods are revolutionizing gut health",
    "The foods that secretly cause inflammation in your body",
    "Why some cultures live past 100 eating specific diets",
    "How intermittent fasting changes your body chemistry",
    # Miscellaneous Mind-Blowing
    "The optical illusions that break your brain",
    "Why yawning is contagious and science still cannot explain why",
    "The random facts about the human body that are hard to believe",
    "How fingerprints form and why every one is unique",
    "Why left-handed people have unique brain advantages",
    "The science of laughter and why humans do it",
    "How your name affects your personality and career",
    "Why dreams feel so real and what they actually mean",
    "The paradoxes that even geniuses cannot solve",
    "Why humans are the only animals that cry emotional tears",
    "How your birth order shapes your entire personality",
    "The surprising ways smell controls your memory",
    "Why goosebumps exist and what they reveal about evolution",
    "The hidden meanings behind common everyday phrases",
    "How twins develop different personalities despite same DNA",
]


def _fallback_topics() -> list:
    import datetime
    day = datetime.date.today().toordinal()
    # Rotate through list so each day gets a different topic first
    rotated = _FALLBACK_TOPICS[day % len(_FALLBACK_TOPICS):] + _FALLBACK_TOPICS[:day % len(_FALLBACK_TOPICS)]
    return rotated


def _discover_topic(auto_pick: bool) -> str:
    import os
    from topics.rss import get_rss_topics

    topics = []
    on_ci = os.environ.get("GITHUB_ACTIONS") == "true"

    if not on_ci:
        # Reddit and Google Trends only work from home/office IPs, skip on CI
        from topics.reddit import get_reddit_topics
        from topics.trends import get_google_trends
        try:
            topics += get_reddit_topics()
        except Exception as e:
            log.warning(f"Reddit topics failed: {e}")
        try:
            topics += get_google_trends()
        except Exception as e:
            log.warning(f"Google Trends failed: {e}")

    # RSS feeds work from any IP including GitHub Actions
    if not topics:
        log.info("Fetching topics from RSS feeds...")
        try:
            topics += get_rss_topics(limit=20)
        except Exception as e:
            log.warning(f"RSS topics failed: {e}")

    if not topics:
        log.warning("All topic sources failed — using built-in fallback list")
        topics = _fallback_topics()

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
    import os
    from topics.rss import get_rss_topics

    topics = []
    if not os.environ.get("GITHUB_ACTIONS") == "true":
        from topics.reddit import get_reddit_topics
        from topics.trends import get_google_trends
        try:
            topics += get_reddit_topics(limit=args.limit // 3)
        except Exception as e:
            print(f"Reddit: {e}")
        try:
            topics += get_google_trends(limit=args.limit // 3)
        except Exception as e:
            print(f"Trends: {e}")
    try:
        topics += get_rss_topics(limit=args.limit // 3)
    except Exception as e:
        print(f"RSS: {e}")

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

    # drive — upload videos from a Google Drive folder
    drive_p = sub.add_parser("drive", help="Upload videos from a Google Drive folder to YouTube")
    drive_p.add_argument("--folder", required=True, help="Google Drive folder URL or ID")
    drive_p.add_argument("--limit", type=int, default=0, help="Max videos to upload (0 = all)")
    drive_p.add_argument("--reupload", action="store_true", help="Re-upload already uploaded videos")

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
    elif args.command == "drive":
        from pipeline.drive_upload import upload_drive_folder
        urls = upload_drive_folder(
            folder_url=args.folder,
            limit=args.limit,
            skip_uploaded=not args.reupload,
        )
        print(f"\nDone. Uploaded {len(urls)} video(s).")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
