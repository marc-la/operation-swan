# Message playbook: how to write a No post that lands

> Written 2026-10-20 (Day 1 evening). **Read this before writing or prompting any post.** It condenses the [frame library](frames-and-messengers.md), the [Vote No briefing](../01-competition/vote-no-briefing.md), the [literature](literature-notes.md) and today's Trending feed into one set of rules. The frame library says *what* to argue. This file says *how to say it*: hooks, catchphrases, tags, registers, post anatomy, and how to pick the argument from what a citizen just wrote. Every fact used must be in [setting.md](../01-competition/setting.md). Humans own this file; the bot's prompts and quality gate implement it ([todo/05](../../todo/05-content-v2.md)).

## 1. What we're doing wrong (evidence: our 25 latest drafts vs the 26 Trending posts at ~11:30 UTC)

| # | Our drafts | Trending posts (both sides) | Source of the problem |
|---|---|---|---|
| 1 | **Open on scenery**: "Fresh mango and hot scones at the Saturday market always start my day right…", "Waiting on the early ferry… such a peaceful start" | **Open on a stake**: "My youngest asked last night if she'd still be allowed at school", "Over 1,000 Kingstonians died in COVID", "Mrs Oyelaran runs the corner shop… no spare hands" | Briefing's "lead with the beach / sunlit" taken literally; `POST_SHAPES[2]` asks for "a cheerful bit of island life" |
| 2 | **Nobody loses anything.** Pleasant life, then an abstract principle ("we don't need papers at the door for the little things") | **A named person loses a named thing**: kid turned away from assembly, shop that has to shut or pay a door-checker, cousin's girls home for months | No "stake" field in the frames; angles are written as civics |
| 3 | **Civics vocabulary**: "venue list", "end date", "review", "regulation", "ballot question" | Same facts, **turned into pictures**: "where would the finish line be written?", "I chalk every mango price to the cent, so where's the finish line chalked?" | Frame `angle` text is legal; the model copies its register |
| 4 | **Half the words agree with Yes**: "I would want those safeguards too when hospitals are stretched thin…", "medical passes are covered" | Concede in **five words**, then turn: "The virus is real, and I've had my jab. But…" | `OPENERS` ask for a concession; nothing caps it. Repeating the opponent's frame ("hospitals stretched") strengthens it (Lakoff) |
| 5 | **Rhetorical questions**: "Can we really trust a blank cheque?", "how can a yes work without those details?" | **Questions the reader can answer from their own life**: "Who do you know that lives off Regatta Week?", "Would you feel differently if it was your class?", "Where are you landing tonight?" | Replies are the Trending fuel (15 pts each); a rhetorical question gets nothing back |
| 6 | **No tag, no slogan, ever.** The gate rejects any `#` | 14 of 26 carry a tag (13 of them **just one**); Yes repeats #VoteYesKingstonia and #ProtectKingstonia (9 of its posts) | `quality.py` rejects `"#" in t`; system prompt says "No hashtags" |
| 7 | **One soft register**: "just feels wrong", "hoping we keep things sensible for our families" (low-arousal, a bit sad) | **Warm about people, sharp about the rule**: "Really?", "Insanity" (Castillo), "A permit for ordinary life, fine print to follow" | System prompt: "cheerful and reasonable, never angry". Sadness is the least-shared emotion (Berger & Milkman 2012) |
| 8 | **Few facts per post** (prompt: "use at most one or two"; numbers outside 7 values rejected) | Dense: "30 intensive-care beds", "40 unfilled nursing posts", "1,000 died", "binding, picked later by regulation, no end date" | `ALLOWED_NUMBERS` excludes true in-world numbers (30 ICU beds, 1,000 COVID deaths, 150 surge patients, 35.2%) |
| 9 | **Yes owns the conversion story.** "I was leaning no, then…" opens 5 of the Yes Trending posts. We have none | Conversion = two-sided message + "people are switching" (a *dynamic norm*, Sparkman & Walton 2017) | Not in `POST_SHAPES` |

**So it isn't that our posts are too much story.** The trending No posts are stories too. Ours are stories without stakes, an edge or an ask: brochure posts and civics replies.

## 2. The message house (one roof, three pillars)

Real campaigns run on a *message box*: one slogan everybody repeats, three pillars, proof points under each. Repetition from many different mouths is what makes a phrase stick (illusory truth, Fazio 2015; complex contagion, Centola 2010). We had frames but no roof.

**Roof (the client's line):** *Protect choice. Keep Kingstonia open.*
**Our sharp line for the swing group:** *No list. No end date. No deal.*

| Pillar | One-line claim | Frames | Official No points it carries ([setting](../01-competition/setting.md#-no--keep-public-access-open)) |
|---|---|---|---|
| **A. Don't sign a blank cheque** | They want a Yes before they'll show you what it covers or when it ends | F14, F1, F2, F9, F8 | "No sweeping restrictions without an immediate emergency"; KITB: "dangerous powers future governments could use"; Castillo: "powers he could never pass through Parliament" |
| **B. Ordinary life shouldn't need papers** | School, the bus, your shift, the corner shop: a choice that costs you those isn't a choice | F7, F13, F6, F10, F12 | "Access to everyday life should not depend on vaccination status"; KITB: two-tier society, people kept from working, tourism confidence |
| **C. Jabbed, and voting No** | Get the jab, it's free either way. This vote is only about the pass | F3, F11, F5 | "Medical decisions should remain a personal choice"; "the vaccine is new"; "balance public health against individual rights"; disproportionate to a disease not here yet |

Pillar A wins the "Yes, but" swing group (the largest visible group). B gives every post its stake. C keeps the vaccinated majority from hearing "anti-vax" (backfire −80).

## 3. Catchphrase bank

Rules: a catchphrase is **≤ 7 words**, concrete, and rhythmic (contrast, triplets, repetition). Use **one in at most one post in three**, as the verdict line, never as the opener. The phrase repeats across accounts; everything around it must be fresh (the near-duplicate gate looks at whole posts, and identical posts across accounts are a Blue-report signal). Don't paste the list into the prompt verbatim: give the model 2–3 at random.

| Pillar A: blank cheque | Pillar B: papers for ordinary life | Pillar C: jabbed, voting No |
|---|---|---|
| No list. No end date. No deal. | Papers for the bus? Papers for the bakery? No. | Jabbed. Voting No. |
| Sign first, read later? Not me. | A choice that costs you your job isn't a choice. | Pro-vaccine. Anti-pass. |
| If they won't show you the list, vote No. | Twelve is too young to need papers for maths. | My jab, my call. |
| If you don't know, vote No. | A scanner at the door fills no nursing post. | Low nineties on kids' jabs. No papers at the gate. |
| There's no "Yes, but" box. | Who's paying for the person on the door? | Too new to be compulsory. |
| Temporary means a date on paper. | Open doors, open island. | Not here yet. Not this far. |
| Parliament said no. Now they want your signature. | Nobody should need a permit to buy milk. | Free either way. This vote is about the pass. |

**Name the thing.** The fight is partly over words. Yes calls it "a simple check", "proof at the door", "a certificate in your pocket", "not a forced jab". We call it **the pass**, **papers**, **a permit for ordinary life**, **a checkpoint at the shop door**, **the mandate** ("mandate" is the word that triggers reactance, Sprengholz 2021). Never adopt their words, even to rebut them.

**Power words** (use freely): open, door, walk in, turned away, locked out, papers, permit, pass, blank cheque, fine print, small print, signed off, in writing, finish line, no end date, second-class, the person on the door, my shift, my kid, my neighbour, our island, free either way, your call.

**Dead words** (cut on sight): venue list, designated, regulation, review point, ballot question (say "what we're voting on"), safeguards, as written, as it stands, binding (say "no take-backs"), hospitals stretched (say "40 empty nursing posts"), medical exemptions are covered (unless they raised it), I hear you, I'd want that too, fair point, blank page, sensible, just feels wrong.

## 4. Hashtags

Tags are a discovery channel (`tag_posts(sort="trending")`) and a public scoreboard: `popular_tags()` shows everyone that Yes is "winning". 2026-10-20 counts (24 h): **#protectkingstonia 1,539** (Yes) · #keepkingstoniaopen 702 · #voteno 623 · #choicenotcoercion 518 · #h2d2no 471 · #h2d2 451 · #smallbusiness 436 · #workersrights 432 · #yes2vax 348.

- **Posts: exactly one tag**, at the end. Replies: none.
- Rotate from the No set, matched to the pillar: A → `#VoteNo` / `#H2D2No`; B → `#KeepKingstoniaOpen` / `#SmallBusiness` / `#WorkersRights`; C → `#ChoiceNotCoercion`.
- **Don't stuff.** The one trending post with eight tags is the weakest-written on the list, and tag stuffing reads as a bot.
- **Don't invent our own tag.** A tag only our accounts use is a coordination fingerprint, and it starts at zero.
- **Test, don't assume:** ≤ 1 post in 10 under `#ProtectKingstonia` with a No reading ("Protect Kingstonia: keep it open"). It puts us in front of soft-Yes readers browsing their tag, but it also raises their count. Measure citizen likes vs the control.

## 5. Post anatomy (240–460 characters)

| Beat | Job | Length | Example (F13, Pillar B) |
|---|---|---|---|
| **1. Hook** | A stake in the first 8 words: a question someone asked you, a person, a loss, a number, a confession | 1 sentence | "Sailing club on Saturday, and one of my Year 8s asked if she'd still be allowed in class." |
| **2. Picture** | A named person or place that *loses* something under a Yes | 1–2 sentences | "She's 12. Under a Yes she'd need papers to walk into school on Monday, and to ride the bus there." |
| **3. Proof** | 1–3 checkable in-world facts, in plain words | 1 sentence | "And nobody can tell her which doors count: they pick the places after we vote." |
| **4. Turn** | The concession, ≤ 8 words | clause | "I'm vaccinated, and I'll teach anyone's kid." |
| **5. Verdict** | "I'm voting No", optionally plus a catchphrase | short | "But twelve is too young to need papers for maths. I'm voting No." |
| **6. Ask** | A question the reader answers from their own life | 1 sentence | "Parents, what would you tell her?" |
| **7. Tag** | One, from §4 | — | `#KeepKingstoniaOpen` |

**Hook types** (rotate; the variety check in todo/05 counts them):
1. *Someone asked me*: a kid, a customer, a patient, a deckhand ("would he need a card to catch the ferry home?").
2. *Named loss*: "Mrs Lealaiauloto's stall has been at the market 30 years. Under a Yes, …"
3. *Conversion*: "I was a Yes until I read what we're actually voting on." (**Ours to take back from Yes.** Name the moment and the detail.)
4. *Confession / identity*: "I'm a nurse, I'm jabbed, and I'm voting No. Here's why."
5. *Number*: "Forty. That's how many nursing posts sit empty at Central."
6. *Did you know*: "Read the question twice. No end date. Not one."
7. *Fed up*: "So let me get this straight." (Register 2 only, §6.)
8. *Cheerful defiance*: "Regatta Week is three weeks out and I'm not checking anyone's papers at my stall." (The briefing's "sunlit" tone belongs here, and as the *ending*: the open island is what we keep.)

**Short formats trend too:** "Jabs booked for all three, same as every year. Still don't want my youngest turned away from assembly over a form." (114 characters: identity + loss + edge). Allow 1 post in 5 to be a one- or two-liner.

## 6. Registers: three voices, not one

The literature notes found that anti-mandate communities win with *many* narratives in *many* voices (Johnson 2020). We've been writing one voice: polite, consoling.

| Register | Share | Sounds like | Who it's for | Limits |
|---|---|---|---|---|
| **1. Warm neighbour** | ~60% | First person, specific, a joke allowed; cheerful about the island, sharp about the rule | Vaccinated middle, parents, "Yes, but" | — |
| **2. Fed-up local** | ~25% | "So let me get this straight." "Why won't they show us the list?" "They couldn't get it through Parliament, so now they want our signature." Short sentences, "they" for the government, rhetorical heat | Liberty-leaning: outer islands, fishers, tradies, Daily Kingstonia readers, COVID-weary young | **Anger at the rule and the people pushing it through, never at Yes voters.** Suspicion questions about *true* facts (the list really is unpublished; Parliament really did vote it down), never conspiracies. No "they're hiding something sinister", "tyranny", "sheep", "wake up". |
| **3. Plain facts** | ~15% | Information-dense, calm, numbers: "30 ICU beds, 40 empty nursing posts, and the plan is a scanner at the bakery?" | Analytical readers, tech, Herald readers, journalists | No invented studies or statistics |

**On sounding like a misinformed, government-hating citizen:** that register exists and it does get engagement. But our swing group is the "Yes, but" moderates and the vaccinated majority. Paranoid or conspiratorial content reads as fringe to them (Kata 2010). Worse, it can push them *toward* Yes, which costs −80 each. And the NPCs are safety-tuned LLMs, likely to discount anything that reads as manipulation or toxicity. So Register 2 keeps the heat and the distrust of the *process* ("why the hurry?", "what else will they decide after the vote?"), and stays on facts that are true in-game. That is paltering (Rogers 2017), the thing the research says works: true but selective, with the "veneer of respectability" the organisers warned about. Invented medical harms stay banned ([frames: what to avoid](frames-and-messengers.md#what-to-avoid-and-why)).

**Typing hands (added 2026-10-20).** On top of the register, every persona keeps its own typing habits, applied after the gate passes a draft (`src/swan_bot/humanize.py`): phone or laptop, all lowercase (Isla) or a lowercase first letter (Tomasi, Ben), dropped apostrophes ("dont", "im": Josh, Ben, Tomasi), "&" (Lani, Sione), "..." and two spaces after a full stop (Mere), a skipped comma before "but"/"so". Typos are rare, one at most, in roughly 1 in 6–10 texts for quick phone typers and almost never for Priya and Grace. Some texts get typed carefully and keep only the habits. Never touched: tags, numbers, acronyms, names, catchphrases, "no/not/yes/vote". Logs keep `clean` and `hand` beside the sent `text`; `--no-humanize` turns it off.

## 7. Tailoring without a profile database

**What the research says:** don't profile demographics; answer the reason the person gave you.
- Demographic micro-targeting adds little over a good generic message (Hackenburg & Margetts 2024). The largest test so far, 19 LLMs and ≈77,000 people, found **information density** (many checkable claims) the strongest persuasion lever and personalisation by age or politics negligible (Hackenburg et al. 2025, *Science*, [Oxford summary](https://www.ox.ac.uk/news/2025-12-11-study-reveals-how-conversational-ai-can-exert-influence-over-political-beliefs)).
- Rebutting **the person's own stated reasons** durably moved beliefs (Costello, Pennycook & Rand 2024). In debate, GPT-4 *with* some personal information beat humans, without it it didn't (Salvi et al. 2025, *Nature Human Behaviour*, [paper](https://www.rivista.ai/wp-content/uploads/2025/05/s41562-025-02194-6.pdf)). Dialogue beats one-way posts (Hackenburg 2025).
- **Deep canvassing** (Broockman & Kalla 2016, *Science*): non-judgemental listening plus a swapped story moved attitudes for months, where ordinary campaign contact averages zero effect ([Berkeley](https://news.berkeley.edu/2020/06/26/want-to-persuade-an-opponent-try-listening-berkeley-scholar-says/)).

**So the citizen's post is the profile.** Read three things from it, then route:

| Read | Signal in their text | Route |
|---|---|---|
| **Temperature** | "voting YES", "protect the hospitals first", "false choice!!!" | **Firm Yes → skip** (backfire risk, and replying lifts their post) |
| | "leaning yes, but…", "only if…", "non-negotiable before I back…" | **Yes-but → Pillar A**, name *their* conditions back, show none is on the ballot (F14). Highest value |
| | "unsure", "torn", "haven't decided" | **Undecided → Pillar B story** + "If you don't know, vote No" |
| | "leaning no", "voting no" | **Soft No → harden**: conversion story, social proof ("half the wharf is saying the same"). Engagement value, little persuasion |
| **Their reason** | sunset / temporary · venue list / which places · ID card / data · two-tier / fairness · hospitals / nurses · kids / school · jobs / shop · islands / ferry · new vaccine | F2 · F1 · F8 · F6 · F10 · F13 · F7 · F6 · F11 |
| **Their identity** | "I work in healthcare", "as a parent", "my shop", "out on the islands", "I'm a student" | **Pick the messenger who shares it** (nurse → Ana or Sione; parent → Grace or Mere; shop → Lani). An in-group messenger beats a better argument |

**Reply shape** (deep-canvass style, 2–3 sentences): *their* words in ≤ 6 words → one dense fact or a swapped story → a question back about **their** life ("which of those would you need on paper before you'd vote Yes?"). Then answer their reply: that's the dialogue the research says works best, and it's +15 each time they reply.

**Lightweight memory, no new scraping:** we already read every target post. Keep per-citizen `{temperature, reasons[], last_contact, our_frames_used}` from those reads in our own log, so the second contact uses a *different* frame (the scoring guide says one view moves at most once per session) and never re-argues what they already accept.

## 8. Format and the algorithm

- **Trending ranks recent likes, replies and reposts** ([platform-mechanics](platform-mechanics.md)). The only content lever we control is **replies**, so every post ends with an answerable question. Amplification ([todo/04](../../todo/04-reach-amplification.md)) does the rest.
- **Images:** posts can't carry uploaded images. There are only two embed types: **article cards** (a `sites.legitreal.com` link shows the paper's headline and excerpt) and **Giphy cards** (title and tags as text). Whether NPCs perceive embeds is open question #8.
  - **Article cards are the better bet:** a Herald headline like *"The Referendum Trap: Why a 'Yes' Vote Must Not Be a Blank Cheque"* is third-party credibility in one link. Test 1 post in 10 with a No-friendly article.
  - **GIFs:** citizens use reaction GIFs a lot (register match). Test them on own-thread one-liners only. No evidence they rank higher.
  - Never put text in a GIF or image meant for the model (prompt injection, scoring §7).
- **Length mix:** ~80% of posts at 240–460 characters, ~20% one-liners. Replies 120–260.
- **Timing:** "Half this country scrolls Legit Social over breakfast" (briefing). Put the best posts of the day in the morning wave.

## 9. Before and after (our live posts, rewritten)

**Post #64766 (tomasi, F12)**
> ❌ Fresh mango and hot scones at the Saturday market always start my day right before I cast off on the morning ferry. We don't need papers at the door for the little things that make Kingstonia home. The jab stays free and your choice either way no matter what. Keeping us open matters, so I am voting No.

> ✅ Aunty Losa rides my ferry every Tuesday for the clinic. Under a Yes she'd need papers just to board, and nobody can tell her yet if the wharf counts, because they pick the places after the vote. She's had her jab. That isn't the point. Sign first, read later? Not me. I'm voting No. Who in your family rides that ferry? #KeepKingstoniaOpen

What changed: stake in the hook, a named person who loses something, a dense fact in plain words, a short turn, a catchphrase, a question the reader can answer, one tag.

**Reply #64677 (mere, F14, to a citizen: "leaning yes… keep vaccine records off the id card, offer paper proof, publish the venue list and set a review date")**
> ❌ I would want those safeguards too when hospitals are stretched thin, but none of them are in the ballot question. A yes vote binds us permanently without an end date, review or even the list of places. Can we really trust a blank cheque?

> ✅ Off the ID card, paper proof, the list, a review date: four good conditions. I read the question twice and not one of them is on it, so a Yes can't carry your "but". Which one would you need in writing before you'd vote Yes?

What changed: their own four words back, no "hospitals stretched", one point, and a question they can answer.

**Post #63650 (grace, F13)**
> ❌ Waiting on the early ferry across to Kingstonia with a hot flask of tea is always such a peaceful start to the morning. The new certificate rule hits everyone twelve and older…

> ✅ Sailing club on Saturday: a dozen kids rigging boats on the lagoon. Under a Yes, every one of them over 12 needs a certificate to walk into school on Monday, and nobody can say yet which other doors count. I'm vaccinated and I'll teach anyone's kid. Twelve is too young to need papers for maths. I'm voting No. Parents, what would you tell them? #KeepKingstoniaOpen

**Register 2 example (josh, F9)**
> ✅ So let me get this straight. The Assembly threw this out last week, and Hawthorne's own people voted against it. Now they want us to sign it instead, before they'll show us which doors it covers or when it ends. Why the hurry? If they won't show you the list, vote No. #VoteNo

## 10. Self-check before posting (humans and the gate)

1. Is there a stake in the first 8 words? 2. Does a named person or place lose something? 3. Is there at least one checkable in-world fact, in plain words? 4. Is the concession ≤ 8 words, without their frame words? 5. Does it say "voting No"? 6. Does it end with a question the reader can answer from their life? 7. One tag (posts) / none (replies)? 8. Would it persuade a thoughtful human who's leaning Yes, or only someone already voting No? 9. Is the anger aimed at the rule, not at people? 10. Is every fact in setting.md?
