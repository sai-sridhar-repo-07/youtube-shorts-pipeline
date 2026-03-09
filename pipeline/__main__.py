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
    # ── Science & Space ───────────────────────────────────────────────────────
    "The science behind why music gives you chills",
    "What happens inside a black hole",
    "How CRISPR gene editing will change medicine",
    "The surprising science of deja vu",
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
    "How DNA stores information better than any hard drive",
    "The planets in our solar system that could support life",
    "Why Pluto lost its planet status and the real story behind it",
    "How space radiation affects astronauts long term",
    "The science of wormholes and whether they could exist",
    "Why the universe is expanding faster than the speed of light",
    "How neutron stars are the densest objects in the universe",
    "The real science behind time travel and is it possible",
    "Why the sun will eventually destroy the earth",
    "How cosmic rays from space hit your body every second",
    "The mystery of fast radio bursts from across the universe",
    "Why there are more stars than grains of sand on earth",
    "How the Hubble telescope rewrote our view of the cosmos",
    "The strange behavior of light that baffled Einstein",
    "Why scientists think the universe might be a simulation",
    "How tidal forces from the moon cause earthquakes on earth",
    "The planets made entirely of diamonds that actually exist",
    "Why space smells like burning metal according to astronauts",
    "How microgravity changes the human body in unexpected ways",
    "The day a meteor almost ended civilization in 1908",
    # ── Psychology & Mind ─────────────────────────────────────────────────────
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
    "Why we feel nostalgic and what it does to the brain",
    "The psychological trick behind every great advertisement",
    "How trauma changes the structure of your brain",
    "Why some people are natural leaders and others are not",
    "The science of envy and how it secretly motivates you",
    "How social isolation physically damages your health",
    "Why we remember embarrassing moments more than happy ones",
    "The psychology of why kindness is actually selfish",
    "How anchoring bias makes you pay more than you should",
    "Why humans form cults and what makes people follow them",
    "The science of why arguments rarely change anyone's mind",
    "How body language reveals what people really think",
    "Why we trust attractive people more than we should",
    "The neuroscience of addiction and how the brain gets trapped",
    "How gratitude physically rewires neural pathways",
    "Why people in groups make worse decisions than individuals",
    "The strange psychology of why we love horror movies",
    "How the placebo effect proves the mind controls the body",
    "Why humans are the only animals that blush from embarrassment",
    "The dark psychology techniques used by every cult leader",
    "How childhood attachment style affects every adult relationship",
    "Why some people have a higher pain tolerance than others",
    "The bizarre effect of music on athletic performance",
    "How smiling tricks your brain into actually feeling happier",
    # ── Health & Fitness ──────────────────────────────────────────────────────
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
    "Why ice baths are now used by elite athletes worldwide",
    "The hidden link between loneliness and heart disease",
    "How your liver detoxes your body every single night",
    "Why napping for exactly 20 minutes makes you sharper",
    "The foods that act like medicine according to scientists",
    "How chronic pain changes the structure of the brain",
    "Why humans are the only mammals who drink milk as adults",
    "The science of hangover cures and why most don't work",
    "How your immune system remembers every disease you ever had",
    "Why the appendix is not actually useless according to new research",
    "The surprising health benefits of dark chocolate",
    "How laughter literally heals the body according to science",
    "Why your body clock controls more than just when you sleep",
    "The real reason some people never get sick",
    "How running barefoot changes the way your feet work",
    "Why people who work with their hands live longer",
    "The science of why we age and whether it can be reversed",
    "How your kidneys filter 200 liters of blood every day",
    "Why the heart is far more complex than a simple pump",
    "The truth about detox diets and what actually works",
    "How plants in your home improve your air quality and mood",
    "Why red meat is not as bad as everyone says",
    "The science behind why some people never gain weight",
    # ── Money & Finance ───────────────────────────────────────────────────────
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
    "Why the stock market always recovers no matter what happens",
    "The psychological tricks casinos use to make you lose more",
    "How Warren Buffett made his first million before age 30",
    "Why most lottery winners end up broke within 5 years",
    "The real difference between assets and liabilities simply explained",
    "How banks create money out of thin air",
    "Why gold has been valuable for 5000 years",
    "The simple budgeting rule that changes everything",
    "How people in poor countries save more than rich people",
    "Why your biggest financial enemy is your lifestyle inflation",
    "How one email can double your freelance income overnight",
    "The hidden cost of buying things on sale",
    "Why starting to invest at 20 vs 30 makes a million dollar difference",
    "How insurance companies make billions from your fear",
    "The truth about buying brand new cars",
    "Why paying off debt is almost always better than investing",
    "How the 1 percent legally pay almost no taxes",
    "The real reason why housing is so expensive everywhere",
    "Why most financial influencers make money teaching you not using it",
    "How to spot a Ponzi scheme before you lose everything",
    # ── Technology ────────────────────────────────────────────────────────────
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
    "Why quantum encryption will make all current passwords worthless",
    "How your phone battery degrades and how to slow it down",
    "The dark web explained simply and what actually lives there",
    "Why the next big thing in tech is not AI but biotech",
    "How brain implants are already giving people superpowers",
    "The real story of how Steve Jobs stole the iPhone idea",
    "Why almost every social media app is designed to be addictive",
    "How a teenager created one of the most used apps ever",
    "The technology that will end cancer in the next decade",
    "Why your smart TV is watching you more than you watch it",
    "How 3D printing is being used to build houses in 24 hours",
    "The tech billionaires are secretly building survival bunkers",
    "Why robots have not replaced humans as fast as predicted",
    "How drones are delivering medicine to remote villages in Africa",
    "The company that owns more of your daily life than you realize",
    "Why the next war will be fought with code not guns",
    # ── History & Ancient Civilizations ──────────────────────────────────────
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
    "Why the Library of Alexandria really burned and what was lost",
    "The forgotten African kingdoms that rivaled Rome",
    "How ancient Greeks had a computer 2000 years ago",
    "The real reason why the Mayan civilization collapsed",
    "How the Mongols conquered most of the world in 50 years",
    "The mystery of who built Stonehenge and why",
    "Why the ancient Romans had better plumbing than medieval Europe",
    "How Genghis Khan killed so many people the planet actually cooled",
    "The lost technology of ancient Egypt scientists still cannot replicate",
    "Why the Viking age was nothing like what movies show",
    "How the Ottoman Empire held power for 600 years",
    "The real Christopher Columbus and the horror of what he did",
    "How pirates had a democratic society before most nations did",
    "The woman who secretly ruled China for 47 years",
    "Why the ancient city of Pompeii was perfectly preserved",
    "How Alexander the Great conquered the world before age 30",
    "The forgotten Indus Valley civilization more advanced than Egypt",
    "Why ancient cave paintings are more sophisticated than we thought",
    "How the French Revolution changed the entire world forever",
    "The real story of the Trojan War and whether it actually happened",
    "Why the Aztec Empire fell so quickly to a handful of Spanish soldiers",
    "How ancient India invented concepts we still use today",
    "The real reason medieval knights wore such heavy armor",
    "Why the Roman Colosseum could flood for naval battle spectacles",
    "How ancient Egyptians mummified their dead so perfectly",
    "The untold story of the real King Arthur",
    "Why Constantinople fell and changed the world forever",
    "How the printing press ended the dark ages almost overnight",
    "The strange reasons why kings and queens married their cousins",
    # ── Nature & Animals ──────────────────────────────────────────────────────
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
    "How elephants grieve their dead just like humans",
    "Why some fish can change their gender whenever they want",
    "The plant that moves and eats insects faster than you can blink",
    "How mantis shrimp can punch harder than a bullet",
    "Why tardigrades are the most indestructible creatures on earth",
    "How ants build cities more complex than any human architecture",
    "Why cats always land on their feet and the physics behind it",
    "The tree that has been alive for 5000 years",
    "How salmon always find their way back to where they were born",
    "Why some birds in Australia start wildfires on purpose",
    "The deep sea fish that produces its own light in the dark",
    "How whales communicate across entire ocean basins",
    "Why crows recognize and remember human faces for years",
    "The parasite that hijacks an ant's brain and controls it",
    "How hummingbirds can slow their heartbeat to near zero",
    "Why some lizards can run on water using physics",
    "The spider that builds fake decoy spiders to confuse predators",
    "How electric eels use their power to hunt in groups",
    "Why dogs can smell cancer before any medical test can detect it",
    "The flower that only blooms once every 100 years",
    "How jellyfish are biologically immortal and can restart their life",
    "Why some frogs survive being completely frozen all winter",
    "The ant colony that has been alive for millions of years",
    "How plants know when they are being eaten and fight back",
    "Why the pistol shrimp creates a flash hotter than the sun",
    "How bears remember every berry bush they ever visited",
    "The bird that can mimic chainsaws and camera shutters perfectly",
    "Why cuttlefish can change color even though they are colorblind",
    # ── Personal Development ──────────────────────────────────────────────────
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
    "How atomic habits stack to create massive change over time",
    "Why sleeping on a problem actually works according to science",
    "The reason why your comfort zone is slowly killing your growth",
    "How to communicate with anyone using one simple technique",
    "Why the most successful people say they almost quit",
    "The habit that separated Einstein from everyone else",
    "How to learn any skill twice as fast using the Feynman technique",
    "Why deep work is the superpower of the modern era",
    "How to reprogram limiting beliefs that hold you back",
    "The 5 second rule that stops procrastination immediately",
    "Why your morning alarm is setting you up to fail every day",
    "How to master public speaking without years of practice",
    "The counterintuitive reason why helping others makes you succeed",
    "Why the most creative people have a very specific daily routine",
    "How to deal with failure the way champions do",
    "The surprising thing that happens when you stop seeking approval",
    "Why introverts have a massive hidden advantage in the modern world",
    "How to build confidence by doing one small scary thing per day",
    "Why delayed gratification is the single biggest predictor of success",
    "The secret of people who never feel overwhelmed",
    # ── Future & Society ──────────────────────────────────────────────────────
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
    "How universal basic income is being tested around the world",
    "Why the next pandemic will be worse unless we prepare now",
    "How lab-grown meat will end factory farming in 20 years",
    "The generation that has less wealth than their grandparents at the same age",
    "Why birth rates are collapsing across the developed world",
    "How climate change will redraw every border on the map",
    "The countries that are already underwater and disappearing",
    "Why China will or will not be the next superpower",
    "How space tourism will become affordable within 15 years",
    "The age of humans is ending according to scientists",
    "Why the attention economy is making everyone mentally unwell",
    "How the metaverse will change where people live and work",
    "The countries where people are happiest and what they do differently",
    "Why gene editing in babies will start in the next decade",
    "How the electric vehicle revolution is creating a new oil crisis",
    # ── Food & Cooking ────────────────────────────────────────────────────────
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
    "Why bread was banned and caused a revolution in France",
    "How ancient Romans used fish sauce on almost everything they ate",
    "The real history of how chocolate became the world's favorite treat",
    "Why sushi was originally a fast food for poor people in Japan",
    "How the avocado almost went extinct without giant animals",
    "The spice that was once worth more than gold",
    "Why eating alone is worse for your health than smoking",
    "How the microwave was invented by accident from radar technology",
    "The country where people eat the healthiest diet on earth",
    "Why your taste buds completely replace themselves every 10 days",
    "How food packaging is secretly making you eat more",
    "The real reason fast food tastes the same everywhere in the world",
    "Why cooking your food actually makes you smarter according to science",
    "How the keto diet changes brain function in surprising ways",
    "The fermented foods that ancient civilizations used as medicine",
    # ── Famous People & Biographies ───────────────────────────────────────────
    "The dark secret life of Leonardo da Vinci nobody talks about",
    "How Einstein failed school and became the greatest mind ever",
    "Why Elon Musk works 100 hours a week and what it actually does to him",
    "The real story of Coco Chanel and how she rose from poverty",
    "How Steve Jobs was adopted and how it shaped his obsession with perfection",
    "The woman scientist who discovered DNA but got no credit",
    "Why Beethoven composed his greatest music when he was completely deaf",
    "How Walt Disney was fired for lacking imagination before he built Disney",
    "The tragic real story of Alan Turing who saved the world",
    "Why Napoleon was not actually short and where the myth came from",
    "How Warren Buffett lives in the same house he bought in 1958",
    "The unbelievable childhood of Oprah Winfrey",
    "Why Gandhi had controversial views that are never mentioned",
    "How Mozart started composing at age 5 and what his brain was like",
    "The real story of Marie Curie and the radiation that killed her",
    "Why Isaac Newton was almost completely unknown during his lifetime",
    "How Michael Jordan was cut from his high school basketball team",
    "The real life of Nikola Tesla who died alone and penniless",
    "Why JK Rowling was rejected by 12 publishers before Harry Potter",
    "How Mark Zuckerberg stole the idea for Facebook and got away with it",
    "The forgotten inventor who created more than Edison and got nothing",
    "Why Abraham Lincoln had severe depression his whole life",
    "How Bruce Lee changed the entire world with one philosophy",
    "The real reason why Princess Diana died and what was covered up",
    "How Freddie Mercury recorded music even as he was dying",
    # ── Geography & Countries ─────────────────────────────────────────────────
    "The countries that most people cannot find on a map",
    "Why some cities below sea level still exist and thrive",
    "The world's most remote inhabited island you never heard of",
    "How the borders of modern countries were drawn by one man",
    "Why Switzerland has stayed neutral for over 500 years",
    "The tiny countries that have their own laws and currencies",
    "How some places on earth experience 6 months of darkness per year",
    "The country with the most lakes in the entire world",
    "Why some rivers in the world flow uphill according to locals",
    "How the Sahara Desert was a lush green paradise 10000 years ago",
    "The underground cities built thousands of years ago still in use",
    "Why New Zealand was the last place on earth to be settled by humans",
    "How Iceland has almost zero crime and what they do differently",
    "The country where the average person is the tallest in the world",
    "Why some countries have never been colonized or conquered",
    "How the Amazon rainforest produces oxygen for half the planet",
    "The ghost towns that were once the most populated cities on earth",
    "Why Japan is building a city entirely underground",
    "How the Maldives is preparing for the day it disappears underwater",
    "The country with the youngest population in the world and what that means",
    # ── Languages & Communication ─────────────────────────────────────────────
    "The languages that are disappearing and being lost forever",
    "Why some languages have no word for certain emotions",
    "How body language says more than your actual words",
    "The language that is spoken by over 1 billion people as a second language",
    "Why children under 7 can learn any language perfectly without trying",
    "How sign language varies completely between countries",
    "The words that exist in other languages with no English equivalent",
    "Why some languages have no word for right or left",
    "How the way you speak changes how you think about time and money",
    "The ancient language that influenced almost every language on earth",
    "Why swearing actually reduces pain according to science",
    "How bilingual people have measurably different brains than others",
    "The constructed languages like Esperanto and why they mostly failed",
    "Why certain accents make people seem more trustworthy",
    "How emojis are evolving into a true universal language",
    # ── Art & Culture ─────────────────────────────────────────────────────────
    "The most expensive paintings ever sold and why they are worth that",
    "How ancient cave art proves humans were artists 40000 years ago",
    "Why the Mona Lisa is smaller than everyone imagines",
    "The artist who cut off his ear and the real reason behind it",
    "How street art went from illegal vandalism to museum exhibitions",
    "Why certain songs make everyone feel the same emotion",
    "The hidden messages inside Renaissance paintings",
    "How film music manipulates your emotions without you knowing",
    "The real story behind the world's most photographed painting",
    "Why architecture affects how happy or sad people feel",
    "How Japanese anime took over the entire world",
    "The cultural traditions that science has proven are good for health",
    "Why some colors are banned in certain countries",
    "How the original fairy tales were extremely dark before Disney cleaned them",
    "The art heist that baffled every detective in the world",
    # ── Sports & Athletics ────────────────────────────────────────────────────
    "The science behind what makes a perfect athlete",
    "Why some humans can run 100 miles without stopping",
    "How the brain of a chess grandmaster is structurally different",
    "The forgotten Olympians who changed sport forever",
    "Why some sports were created for entirely different purposes",
    "How marathon runners enter a state beyond normal human limits",
    "The psychological tricks elite athletes use to win under pressure",
    "Why free divers can hold their breath for 24 minutes",
    "How the human body can survive extreme cold athletic events",
    "The sport that was played on the moon by an astronaut",
    "Why some people are born faster runners due to a specific gene",
    "How soccer became the world's most popular sport",
    "The athlete who won gold with a broken bone and felt nothing",
    "Why female athletes recover faster from injuries than males",
    "How training at high altitude permanently changes your blood",
    # ── Music & Entertainment ─────────────────────────────────────────────────
    "Why certain songs get stuck in your head and how to remove them",
    "The hidden mathematics inside every piece of music",
    "How the Beatles almost broke up before they were famous",
    "Why listening to music while studying makes some people worse",
    "The real story behind the most sampled song in music history",
    "How music festivals became billion dollar industries",
    "Why sad music actually makes some people feel happy",
    "The neuroscience of why bass makes you want to dance",
    "How one song changed the entire music industry forever",
    "The artists who predicted the future in their lyrics",
    "Why vinyl records are making a comeback in the digital age",
    "How streaming services changed what music sounds like",
    "The musicians who were more popular after they died",
    "Why certain chords create tension and others create peace",
    "How movies have been using the same 4 chords for 100 years",
    # ── Military & War History ────────────────────────────────────────────────
    "The most genius military strategies in all of history",
    "How a tiny mistake caused the First World War",
    "The secret weapons of World War 2 that were never used",
    "Why the D-Day invasion should have failed but succeeded",
    "The war that lasted only 38 minutes and who won",
    "How carrier pigeons saved thousands of lives in both world wars",
    "The women spies of World War 2 who the Nazis never caught",
    "Why nuclear bombs are never used despite many countries having them",
    "The forgotten war that shaped the modern world completely",
    "How Hannibal crossed the Alps with elephants and nearly destroyed Rome",
    "The battle where a tiny army defeated the most powerful on earth",
    "Why soldiers in World War 1 stopped fighting on Christmas Day",
    "The special forces operation so secretive it was denied for 20 years",
    "How ancient armies used animal warfare to defeat their enemies",
    "The accidental inventions created for war that changed everyday life",
    # ── Inventions & Discoveries ──────────────────────────────────────────────
    "The invention that was stolen and who really deserves credit",
    "How penicillin was discovered by complete accident",
    "The scientist who discovered something revolutionary and was laughed at",
    "Why the microwave was invented by a man who melted a chocolate bar",
    "How velcro was invented by a man who looked at burrs on his dog",
    "The technologies invented in ancient times still used today",
    "Why the internet was originally designed only for scientists",
    "How one scientist accidentally discovered X-rays",
    "The 19th century inventions that were decades ahead of their time",
    "Why some of the greatest discoveries were made while sleeping",
    "How the rubber tire was accidentally vulcanized by Charles Goodyear",
    "The invention that has saved more lives than any medicine in history",
    "Why the greatest inventions usually come from the poorest countries",
    "How post-it notes were invented from a failed super glue attempt",
    "The invention that accidentally discovered that radiation causes cancer",
    # ── Philosophy & Thinking ─────────────────────────────────────────────────
    "The philosophy of Stoicism and why billionaires study it",
    "Why the smartest people are often the most uncertain",
    "The greatest philosophical question that has never been answered",
    "How ancient philosophy predicted modern psychology by 2000 years",
    "Why free will might be an illusion according to neuroscience",
    "The thought experiments that changed how we see reality",
    "How Socrates was executed for asking too many questions",
    "Why Eastern philosophy handles mental health better than Western",
    "The paradox that proves mathematics has limits",
    "How philosophers have debated the meaning of life for 3000 years",
    "Why nihilism is actually a liberating philosophy not a depressing one",
    "The ethical dilemma that every self-driving car must solve",
    "How the trolley problem reveals your hidden moral code",
    "Why Marcus Aurelius is the most read philosopher in Silicon Valley",
    "The philosophy behind why suffering is necessary for growth",
    # ── Weird & Strange Facts ─────────────────────────────────────────────────
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
    "Why you cannot tickle yourself no matter how hard you try",
    "The town that has been on fire underground for over 50 years",
    "How there is a place on earth where compasses do not work",
    "Why humans are the only animals that get embarrassed",
    "The country where it is illegal to own a guinea pig alone",
    "How a solar storm in 1859 would destroy the internet if it happened today",
    "Why Antarctica is technically the largest desert on earth",
    "The lake that turns animals into stone when they touch the water",
    "How there is a place in the US where it is always 1950",
    "Why some people are immune to getting drunk no matter how much they drink",
    "The mathematical pattern found in every flower and galaxy",
    "How a woman survived falling from a plane with no parachute",
    "Why the sky on other planets would look completely different colors",
    "The village where every house is painted exactly the same color",
    "How humans share 60 percent of their DNA with a banana",
    # ── Human Body Facts ──────────────────────────────────────────────────────
    "The human body facts that will make you see yourself differently",
    "How your stomach completely replaces its lining every 5 days",
    "Why the human eye can see 10 million different colors",
    "How the body produces enough electricity to power a light bulb",
    "Why your bones are stronger than steel pound for pound",
    "The organ that grows back even when 75 percent of it is removed",
    "How your nose can detect 1 trillion different smells",
    "Why humans have more bacterial cells than human cells in their body",
    "The part of the brain that is only active when you daydream",
    "How the heart beats 100000 times per day without ever resting",
    "Why your body is literally glowing with a faint light you cannot see",
    "How your DNA would stretch from earth to Pluto and back 17 times",
    "Why humans are the only animals with a chin and nobody knows why",
    "The part of the brain that activates when you see someone you love",
    "How your skin is completely replaced every month you are alive",
    # ── Ocean & Marine Mysteries ──────────────────────────────────────────────
    "The ocean zone so deep even submarines cannot reach it",
    "How the ocean is making a sound so loud it confuses scientists",
    "The underwater waterfall that is larger than any land waterfall",
    "Why the ocean contains more history than all museums combined",
    "How rivers flow inside the ocean without mixing with the surrounding water",
    "The creature in the deep sea that has lived unchanged for 500 million years",
    "Why the ocean floor has mountain ranges twice the height of Everest",
    "How scientists discovered an ocean under Antarctica larger than all surface oceans",
    "The sunken city discovered that matches the description of Atlantis",
    "Why some areas of ocean are completely dead and scientists cannot explain why",
    # ── Mathematics & Logic ───────────────────────────────────────────────────
    "The math problem worth a million dollars nobody has solved",
    "Why infinity is not just a number but many different sizes",
    "How mathematics predicted the existence of black holes before we found them",
    "The number pattern found in everything from sunflowers to galaxies",
    "Why some mathematical truths can never be proven even if they are true",
    "How a 10 year old solved a math problem that stumped professors",
    "The real reason why 1 divided by 0 breaks computers",
    "Why prime numbers are used to protect every password on the internet",
    "How ancient Babylonians used calculus 1400 years before Newton",
    "The beautiful mathematics hidden inside every rainbow",
    # ── Environment & Climate ─────────────────────────────────────────────────
    "Why the ozone layer hole is actually closing and nobody talks about it",
    "How one company polluted an entire town and got away with it for decades",
    "The natural solution to plastic pollution that scientists discovered",
    "Why forests in Siberia are burning and what it means for everyone",
    "How electric cars can actually be worse for the environment if done wrong",
    "The simple technology that can pull carbon out of the air at massive scale",
    "Why the Great Barrier Reef has partially recovered against all predictions",
    "How recycling is mostly a myth created by plastic companies",
    "The country that became completely carbon neutral and what everyone else can learn",
    "Why coral reefs are more important than rainforests for life on earth",
    # ── Architecture & Engineering ────────────────────────────────────────────
    "How the Romans built concrete that has lasted 2000 years",
    "The building techniques of the pyramids that engineers still argue about",
    "Why the Eiffel Tower was supposed to be demolished after 20 years",
    "How the world's longest tunnel was built under a mountain",
    "The skyscraper designed to sway in the wind on purpose",
    "Why Tokyo has virtually no building collapses despite massive earthquakes",
    "How ancient aqueducts moved water hundreds of miles without pumps",
    "The bridge that was built so precisely it adjusts to temperature changes",
    "Why the Leaning Tower of Pisa has not fallen after 800 years",
    "How Dubai built an entire island in the shape of a palm tree",
    # ── Relationships & Social ────────────────────────────────────────────────
    "The science of what makes relationships last for decades",
    "Why the strongest friendships follow a very specific pattern",
    "How social status affects your health as much as smoking does",
    "The real reason why divorce rates are so high in modern society",
    "Why people who have more friends live significantly longer",
    "How kindness spreads through social networks like a virus",
    "The surprising things that make people deeply attractive beyond looks",
    "Why arranged marriages statistically last longer than love marriages",
    "How loneliness actually changes the structure of your brain",
    "The science of why some families stay close and others fall apart",
    # ── Additional Science & Discovery ───────────────────────────────────────
    "Why the human body can survive without food for weeks but not water for days",
    "The planet that rains glass sideways at 5000 miles per hour",
    "How scientists revived a 48000 year old zombie virus from permafrost",
    "Why some materials become superconductive at room temperature",
    "The biological clock inside every cell of your body",
    "How the discovery of fire changed human brain size forever",
    "Why every atom in your body was forged inside a dying star",
    "The chemical reaction that makes bread rise and why it matters",
    "How scientists are using sound waves to levitate objects in midair",
    "Why some deserts get colder than the Arctic at night",
    "The creature that can regenerate its entire brain after injury",
    "How a single gene difference separates humans from chimpanzees",
    "Why water is the only substance that expands when it freezes",
    "The microplastics found in every human brain tested so far",
    "How coral communicates through chemical signals across miles of ocean",
    "Why the sky on Venus looks completely orange from the surface",
    "The discovery that trees can count and remember drought years",
    "How scientists created living robots from frog cells in 2020",
    "Why the color blue was almost invisible to ancient humans",
    "The island that appeared from the ocean in 2023 and keeps growing",
    "How photosynthesis produces enough oxygen for every breath you take",
    "Why some stars pulse like a heartbeat with perfect regularity",
    "The bacteria that eats plastic and could save the oceans",
    "How animals predicted earthquakes days before they happened",
    "Why the Voyager probe launched in 1977 is still sending data",
    "The chemical in your brain that makes you fall in love",
    "How scientists are printing human organs with living cells",
    "Why some people are born without fingerprints and what that means",
    "The moon of Jupiter that has a deeper ocean than all Earth oceans",
    "How the Earth generates its own magnetic field from liquid iron",
    # ── Additional Psychology & Behavior ─────────────────────────────────────
    "The experiment that proved most people will obey authority blindly",
    "Why humans are hardwired to care more about one person than thousands",
    "The psychology of why we remember faces but forget names instantly",
    "How your birth month statistically affects your career success",
    "Why people in flow state lose all sense of time and hunger",
    "The dark psychological reason why people enjoy watching others fail",
    "How social media validation activates the same brain pathway as cocaine",
    "Why the funniest people are often hiding the deepest pain",
    "The psychological reason why we trust people who speak confidently",
    "How anxiety evolved as a survival tool and why it now backfires",
    "Why humans feel physical pain from social rejection",
    "The cognitive bias that makes every generation think they are special",
    "How loneliness causes the same inflammation as a physical wound",
    "Why music from your teenage years hits differently than any other",
    "The psychology of why bad news spreads six times faster than good news",
    "How your sleeping position reveals personality traits according to research",
    "Why the same joke is not funny the second time you hear it",
    "The reason why some people never feel satisfied no matter what they achieve",
    "How nostalgia literally reduces physical pain according to scientists",
    "Why humans are the only animals that get bored",
    "The psychology behind why revenge never actually makes you feel better",
    "How childhood boredom builds creativity in adults",
    "Why your brain physically hurts when you try to learn new things",
    "The counterintuitive way that having too many options paralyzes decisions",
    "How the words you use change the way you perceive reality",
    # ── Additional Health & Body ──────────────────────────────────────────────
    "Why your body heals faster when you believe it will",
    "The surprising health benefits of being slightly cold all the time",
    "How your gut bacteria can be transplanted to treat depression",
    "Why people who nap regularly have 37 percent lower heart disease risk",
    "The connection between oral health and heart attacks scientists discovered",
    "How oxytocin from hugs physically strengthens your immune system",
    "Why your body stores trauma in specific muscle groups",
    "The real reason why some people need more sleep than others",
    "How the circadian rhythm controls over 24000 genes in your body",
    "Why your appendix is actually a safe house for good gut bacteria",
    "The surprising link between loneliness and accelerated aging",
    "How petting a dog lowers cortisol levels within 10 minutes",
    "Why some people feel pain more intensely than others genetically",
    "The Japanese practice that has been proven to extend lifespan",
    "How chronic stress literally shrinks the hippocampus in your brain",
    "Why outdoor exercise gives more mental health benefits than indoor",
    "The link between your thyroid and almost every system in your body",
    "How dancing is one of the best exercises for brain health",
    "Why spending time in forests measurably lowers blood pressure",
    "The blood type connection to disease risk most doctors ignore",
    "How volunteering adds years to your life according to science",
    "Why laughter yoga is now used in cancer treatment centers",
    "The gut bacteria that produces most of your serotonin and dopamine",
    "How your body composition changes every decade of life",
    "Why pessimists get sick less often but optimists live longer",
    # ── Additional Money & Business ───────────────────────────────────────────
    "Why the richest people in the world are getting richer during every recession",
    "The business model that made Amazon the most valuable company",
    "How one decision by Steve Jobs saved Apple from bankruptcy in 1997",
    "Why small businesses outperform corporations in employee satisfaction",
    "The pricing psychology trick that makes 9.99 always beat 10.00",
    "How Warren Buffett reads 500 pages every single day",
    "Why some countries have free healthcare and others cannot afford it",
    "The story of the company that turned down buying Google for 750000 dollars",
    "How the Fed printing money affects your grocery bill explained simply",
    "Why the middle class is shrinking faster than economists predicted",
    "The financial habits of people who retire before age 45",
    "How airlines make most of their money not from ticket prices",
    "Why the gig economy workers earn less than minimum wage on average",
    "The economic reason why doctors in America earn 3 times more than Europe",
    "How microfinance loans changed the lives of millions in developing nations",
    "Why starting a business during a recession has a higher success rate",
    "The company that was rejected by every investor and became worth billions",
    "How psychological pricing tricks make you spend 23 percent more",
    "Why some currencies are stronger than others and what determines value",
    "The reason rent is so high in cities and what actually fixes it",
    "How the minimum wage debate completely misses the real issue",
    "Why investing in index funds beats 95 percent of professional managers",
    "The tax loophole that allows billionaires to legally earn zero taxable income",
    "How one email to a stranger changed Jeff Bezos forever",
    "Why employee-owned businesses outperform shareholder-owned ones",
    # ── Additional Technology & AI ────────────────────────────────────────────
    "How AI learned to write better than most humans in just 5 years",
    "Why the most dangerous cyberattack in history almost nobody heard about",
    "The hidden cost of sending one email to the environment",
    "How your phone screen is engineered to be impossible to put down",
    "Why the internet is running out of space and what happens next",
    "The real story behind how Bitcoin was created and who Satoshi really is",
    "How AI is being used to predict earthquakes three days in advance",
    "Why every photo you post online contains hidden metadata about you",
    "The military technology that became the smartphone in your pocket",
    "How augmented reality will make glasses the next iPhone",
    "Why the next billion dollar startup will come from Africa",
    "The algorithm that predicts crime before it happens and its problems",
    "How quantum computers will crack every password on earth within a decade",
    "Why most robots fail because of their hands not their brains",
    "The dark pattern design techniques that trap you in subscriptions",
    "How a 19 year old built software that runs in half the world's computers",
    "Why your recommendation algorithm knows what you want before you do",
    "The country that has the fastest internet in the world and why",
    "How neural interfaces will let you control devices with thoughts by 2030",
    "Why the most powerful AI models are trained on your public posts",
    "The tech company worth more than the GDP of most countries",
    "How screen time under age 2 changes brain development permanently",
    "Why the most successful apps are designed to feel like slot machines",
    "The simple reason why most AI chatbots confidently say wrong things",
    "How satellite internet is connecting the last billion people on earth",
    # ── Additional World History ──────────────────────────────────────────────
    "The real reason Napoleon sold Louisiana for almost nothing",
    "How a single assassination killed 20 million people in World War One",
    "The woman who discovered radioactivity and won two Nobel prizes",
    "Why the ancient Romans had vending machines and fast food restaurants",
    "How a typing mistake triggered the fall of the Berlin Wall",
    "The forgotten kingdom in Africa that was richer than all of Europe",
    "Why the Ottoman sultans killed all their brothers when crowned",
    "How tea caused two revolutions in America and China",
    "The Japanese soldier who kept fighting World War Two until 1974",
    "Why the Inca Empire had no writing but ran perfectly complex cities",
    "How a 12 year old sailor accidentally started the age of exploration",
    "The city that was so advanced it had street lighting in 1000 AD",
    "Why the shortest war in history lasted 38 minutes and who started it",
    "How the invention of air conditioning completely changed where people live",
    "The pirate republic that lasted 11 years with its own democracy",
    "Why historians believe Cleopatra was actually Greek not Egyptian",
    "How one banker funded both sides of the American Civil War",
    "The ancient city built on the water that is still standing after 1500 years",
    "Why the Black Death accidentally improved wages for surviving peasants",
    "How a 14 year old girl led an army that changed French history forever",
    "The spy who changed the outcome of the entire Second World War",
    "Why the Aztecs willingly surrendered to a much smaller Spanish force",
    "How the printing press created the Protestant Reformation within a decade",
    "The forgotten plague that killed more people than World War Two",
    "Why ancient Greek athletes competed completely naked in the Olympics",
    # ── Additional Nature & Environment ──────────────────────────────────────
    "How a single wolf pack turned rivers into different shapes in Yellowstone",
    "Why some caterpillars dissolve into liquid inside their cocoon completely",
    "The flower that only blooms for one night and never again",
    "How trees can detect the sound of running water underground",
    "Why elephants hold funerals and mourn their dead for days",
    "The marine worm that regenerates a completely new head and brain",
    "How termite mounds stay exactly 87 degrees without air conditioning",
    "Why some birds in New Caledonia are smarter than great apes at tool use",
    "The living rock that is actually an animal not a plant",
    "How dolphins have names for each other and respond when called",
    "Why mountain gorillas have been successfully brought back from near extinction",
    "The butterfly that navigates 3000 miles using the sun and its internal clock",
    "How some trees can live for 10000 years and share memories through roots",
    "Why the ocean produces more than half of the oxygen in every breath",
    "The spider that builds traps more sophisticated than any human invention",
    "How crows solve multi-step puzzles that require planning ahead",
    "Why some deep sea fish are completely transparent so you see their organs",
    "The plant that moves its leaves away from caterpillar attacks in real time",
    "How whales sing songs that evolve and spread across ocean basins",
    "Why African wild dogs are the most successful hunters on earth",
    # ── Additional Personal Growth ────────────────────────────────────────────
    "Why your biggest failures are the ones you will thank later",
    "The Japanese concept of wabi-sabi that changes how you see imperfection",
    "How to stop caring what people think using one simple mental shift",
    "Why the most successful entrepreneurs have failed more than anyone",
    "The ancient Stoic trick that neutralizes anxiety in under one minute",
    "How to get better at anything twice as fast using deliberate practice",
    "Why people who write their goals down are 42 percent more likely to achieve them",
    "The productivity technique used by the most effective CEOs",
    "How to build the habit of consistency when motivation always fades",
    "Why your inner critic is the biggest obstacle to achieving anything",
    "The power of asking for what you want and why most people never do",
    "How to turn any rejection into fuel for the next attempt",
    "Why doing less with more focus beats doing more with scattered attention",
    "The one question that reveals whether you are living your own life",
    "How to have the hard conversation you have been avoiding for years",
    "Why most people overthink starting and underthink finishing",
    "The counterintuitive truth about how confidence is actually built",
    "How to make a decision when both options seem equally good or bad",
    "Why the best version of you is already inside you waiting to emerge",
    "The habit that Navy SEALs use to stay calm under extreme pressure",
    # ── Culture & Society ─────────────────────────────────────────────────────
    "Why every culture on earth has stories about a great flood",
    "The hidden social rules that govern every human interaction",
    "How tattoos went from criminal marking to mainstream fashion globally",
    "Why some cultures sleep twice per night and science says they are right",
    "The universal gestures that mean the same thing in every country",
    "How the concept of childhood was only invented 200 years ago",
    "Why gift-giving is one of the most complex social rituals in human history",
    "The cultural practice that measurably reduces anxiety and depression",
    "How social class affects your health more than smoking or obesity",
    "Why the concept of romantic love is surprisingly modern and recent",
    "The countries where failure is celebrated not punished",
    "How street food culture reveals the true soul of a city",
    "Why some cultures have no concept of linear time like Western societies",
    "The ritual practiced by every known human civilization throughout history",
    "How clothing carries more social information than any spoken word",
    # ── Famous Mysteries & Unsolved Cases ────────────────────────────────────
    "The disappearance that baffled investigators for over 100 years",
    "Why the Voynich manuscript has never been decoded despite a century of trying",
    "The civilization that disappeared overnight leaving food on the table",
    "How the Zodiac Killer taunted police for decades without being caught",
    "The shipwreck found perfectly preserved at the bottom of the Black Sea",
    "Why the Mary Celeste was found sailing with no crew and no explanation",
    "The medieval mass hysteria that made hundreds of people dance for weeks",
    "How a mathematician predicted his own death to the exact hour",
    "The airport that has had planes disappear in clear weather for decades",
    "Why hundreds of birds fell dead from the sky in one small town overnight",
    "The man who survived three separate lightning strikes and kept records",
    "How a 3500 year old temple was discovered under a farmers field in 2022",
    "The unsolved mystery of why identical twins have different fingerprints",
    "Why some ancient sites around the world share exact same coordinates",
    "The door in a famous temple that has never been opened in recorded history",
    # ── Geography & Extreme Places ────────────────────────────────────────────
    "The town where the sun does not set for two full months every year",
    "How a village in India gets more rainfall in one month than most places in a century",
    "The country that has no natural rivers despite being full of water",
    "Why some places on earth experience four different seasons in one day",
    "The lake that changes color from blue to pink to red with the seasons",
    "How an entire island chain appeared from the ocean in the last 50 years",
    "The valley where it has not rained for more than 2 million years",
    "Why some mountains produce sounds that locals call the voice of the gods",
    "The underground river longer than the Amazon that nobody knew existed",
    "How a town in Australia was built entirely underground to escape the heat",
    "The place on earth where two oceans meet but never mix",
    "Why certain forests in the world glow blue at night naturally",
    "The volcano island that appeared then disappeared three times in history",
    "How the Nile flows uphill for a section and why nobody talks about it",
    "The country where it rains fish and frogs during storm season",
    # ── Inventions That Changed Everything ───────────────────────────────────
    "How the zipper took 20 years to be accepted by the public",
    "Why the most important invention in history is one nobody ever thinks about",
    "The invention that accidentally created an entirely new industry worth trillions",
    "How bubble wrap was originally designed to be textured wallpaper",
    "Why Teflon was discovered by a scientist trying to make a new refrigerant",
    "The invention that was rejected 1000 times before changing the world",
    "How matches were accidentally discovered while someone was cleaning a stick",
    "Why the inventor of dynamite used his fortune to create the Nobel Peace Prize",
    "The woman who invented Kevlar that saved millions of lives",
    "How the internet was nearly shut down in 1995 by the US government",
    "Why the microchip was simultaneously invented by two people who never met",
    "The parachute inventor who died testing it by jumping off the Eiffel Tower",
    "How wireless charging was invented in 1894 by Nikola Tesla",
    "Why the first programmers were all women and how that history was erased",
    "The invention that was so far ahead of its time it was forgotten for 100 years",
    # ── Ethics & Philosophy ───────────────────────────────────────────────────
    "The moral dilemma that every society must eventually face",
    "Why artificial intelligence forces us to redefine what it means to be human",
    "The philosophical question that has no answer but changes everything you think",
    "How Plato predicted social media and democracy's downfall 2400 years ago",
    "Why determinism suggests free will might be the greatest illusion of all",
    "The ethical problem with autonomous weapons that nobody has solved",
    "How ancient Stoics dealt with grief that modern therapy still uses",
    "Why the trolley problem reveals that ethics is fundamentally unsolvable",
    "The philosophical tradition that says suffering is the path to wisdom",
    "How different cultures answer the question of what makes a good life",
    # ── Sports Science ────────────────────────────────────────────────────────
    "Why some athletes enter a zone where they literally cannot miss",
    "The science of why ice baths work and how cold should they actually be",
    "How altitude training changes blood chemistry permanently",
    "Why female marathon runners peak at older ages than male runners",
    "The mental visualization technique that improves performance without practice",
    "How the brain of a cricket batsman processes information faster than thought",
    "Why swimming produces the most balanced athletic body according to science",
    "The diet secret of Olympic athletes that contradicts popular nutrition advice",
    "How some athletes appear to slow time down during competition",
    "Why certain sports cause permanent personality changes in their players",
    # ── Relationships & Human Connection ─────────────────────────────────────
    "Why the strongest relationships always have conflict not absence of it",
    "The psychological reason why long distance relationships sometimes last longer",
    "How mirroring someone's body language builds instant deep trust",
    "Why people fall in love with those who remind them of their parents",
    "The attachment style quiz that predicts relationship success with 80 percent accuracy",
    "How gratitude expressed out loud transforms the chemistry of a relationship",
    "Why couples who laugh together stay together according to 40 year studies",
    "The hidden reason why people stay in relationships they know are wrong",
    "How making eye contact for four minutes creates emotional connection with a stranger",
    "Why the happiest marriages have a specific ratio of positive to negative moments",
    # ── Economics & Global Affairs ────────────────────────────────────────────
    "How one decision by OPEC in 1973 reshaped the entire modern world",
    "Why countries with the most natural resources are often the poorest",
    "The economic theory that explains why the middle class keeps shrinking",
    "How microplastics are now inside the global food supply chain permanently",
    "Why some cities are sinking into the ocean faster than expected",
    "The trade route that controlled world history for a thousand years",
    "How remittances from immigrants contribute more to poor countries than foreign aid",
    "Why the global economy almost collapsed in 2008 due to one product",
    "The country that became rich by doing the opposite of what economists advised",
    "How food waste costs the global economy over a trillion dollars annually",
    # ── Mental Health & Wellbeing ─────────────────────────────────────────────
    "Why the mental health crisis is worst in the wealthiest countries on earth",
    "How talking to yourself out loud improves focus and emotional regulation",
    "The therapy technique that cures phobias in a single two-hour session",
    "Why social comparison is the fastest path to depression in the modern world",
    "How art therapy physically changes brain patterns in trauma survivors",
    "The reason why doing nothing is essential for mental health and creativity",
    "Why gratitude journaling rewires the brain in ways antidepressants cannot",
    "How spending time in natural light resets mental health within three days",
    "The psychological effect of clutter on anxiety and decision fatigue",
    "Why helping others is scientifically the fastest way to improve your own mood",
    # ── Quirky Human Behavior ─────────────────────────────────────────────────
    "Why humans are the only animals that willingly eat spicy food for pleasure",
    "The psychology of why we collect things we will never use",
    "How the way you shake hands predicts your economic earnings",
    "Why people are more honest in handwritten notes than typed messages",
    "The strange effect of speaking a foreign language on moral decisions",
    "How your handwriting reveals specific personality traits according to graphologists",
    "Why people apologize to objects they bump into and what it reveals",
    "The reason humans instinctively make eye contact to share surprising moments",
    "How the order in which you list your name and job shapes your identity",
    "Why humans are uniquely obsessed with other peoples drama and gossip",
    # ── Survival & Extreme Situations ────────────────────────────────────────
    "How the human body adapts to extreme cold in ways science only just discovered",
    "The psychological stages of being lost that can save your life",
    "Why some people survive things that should be statistically impossible",
    "How ultra-marathon runners train their minds more than their bodies",
    "The survival instincts that kick in automatically under mortal danger",
    "Why staying calm in an emergency is a trainable skill not a personality trait",
    "How people trapped for months maintain sanity with specific mental techniques",
    "The difference in survival outcomes between people who kept hope and those who lost it",
    "Why some soldiers become immune to post traumatic stress over time",
    "How the Wim Hof method allows humans to consciously control immune response",
    # ── Language & Communication ──────────────────────────────────────────────
    "Why the structure of a language changes how its speakers perceive time",
    "How learning a new language after 60 measurably slows Alzheimer's",
    "The lost language discovered that has no known connection to any other",
    "Why some words create physical sensations when you say them out loud",
    "How tone of voice carries 38 percent of meaning in any conversation",
    "The country where children grow up fluent in four languages by default",
    "Why ancient Sanskrit has more precise words for emotions than English",
    "How the words you use when describing pain change how much it hurts",
    "The sign language that emerged spontaneously in a Nicaraguan school in the 1980s",
    "Why children raised bilingual have measurably better impulse control",
    # ── Art History & Culture ─────────────────────────────────────────────────
    "How graffiti artists in New York accidentally created a global art movement",
    "The painting that was found in a charity shop worth 25 million dollars",
    "Why ancient Egyptian art never showed people from the front",
    "How architecture controls human behavior without anyone realizing it",
    "The artist who was blind from birth and created sculptures other artists envy",
    "Why some pieces of music are physically impossible for humans to perform",
    "How film noir was created because Hollywood could not afford good lighting",
    "The original Disney villain designs that were rejected for being too terrifying",
    "Why some colors were illegal to wear in medieval Europe",
    "How jazz was deliberately suppressed by governments who feared its influence",
    # ── Food Science ──────────────────────────────────────────────────────────
    "Why bread in France by law cannot contain more than four ingredients",
    "How ancient Romans preserved food for years without refrigeration",
    "The reason spicy food feels hot even though it produces no actual heat",
    "Why umami the fifth taste was only officially recognized in 1985",
    "How the taste of food changes completely depending on what music is playing",
    "The chemistry of why caramelized onions can never be made in five minutes",
    "Why eating together as a family is linked to better academic performance in children",
    "How the food industry engineered snacks to be impossible to stop eating",
    "The indigenous food systems that sustained populations for thousands of years",
    "Why cooking with fire fundamentally changed the course of human evolution",
    # ── Space Exploration ─────────────────────────────────────────────────────
    "How astronauts describe the first sight of earth from space changing them forever",
    "Why the moon is slowly moving away from earth at 1.5 inches per year",
    "The dark side of the moon that has never been photographed until 2019",
    "How sound in space is different from what every movie has ever shown",
    "Why some scientists believe the universe is inside a black hole",
    "The day a solar storm nearly triggered nuclear war by accident",
    "How humanity will extract water from the moon to fuel space travel",
    "Why the most Earth-like planet discovered is 1200 light years away",
    "The spacecraft that has been travelling for 46 years and is still working",
    "How gravity on different planets would completely change human physiology",
    # ── Hidden History ────────────────────────────────────────────────────────
    "The history that was deliberately erased and is only now being recovered",
    "Why the winners of wars decide what goes into history books",
    "The woman who ran the most powerful empire in history for 20 years",
    "How indigenous knowledge systems solved problems modern science is just discovering",
    "The real reason Columbus was not the hero that was taught in schools",
    "Why the most important battles in history were never fought with weapons",
    "How propaganda turned ordinary people into willing participants of atrocities",
    "The empire that controlled half of world trade and nobody teaches about",
    "Why certain historical facts are still classified as state secrets today",
    "How the history of medicine was almost entirely discovered by women",
    # ── Mind-Blowing Facts ────────────────────────────────────────────────────
    "Why your eyes are so sensitive you can see a single photon of light",
    "How your nose works as a time machine pulling you to past memories instantly",
    "The fact that every human shares 99.9 percent identical DNA",
    "Why your heart has its own nervous system and can function outside the body",
    "How the brain processes reading faster than any computer currently built",
    "The mathematical certainty that two people in any group of 23 share a birthday",
    "Why hot water freezes faster than cold water and scientists still debate why",
    "How the universe is so vast that this sentence is already ancient history out there",
    "The fact that your body contains enough carbon to make 9000 pencils",
    "Why the total weight of all ants on earth equals the weight of all humans",
]


def _fallback_topics() -> list:
    import datetime
    now = datetime.datetime.utcnow()
    # day*24+hour ensures morning and evening runs pick DIFFERENT topics
    slot = (now.toordinal() * 24 + now.hour) % len(_FALLBACK_TOPICS)
    rotated = _FALLBACK_TOPICS[slot:] + _FALLBACK_TOPICS[:slot]
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
        import datetime
        now = datetime.datetime.utcnow()
        # Use day*24+hour so 11am and 9:30pm always pick DIFFERENT topics
        slot = (now.toordinal() * 24 + now.hour) % len(unique)
        topic = unique[slot]
        log.info(f"Auto-selected topic (slot {slot}/{len(unique)}): {topic}")
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
