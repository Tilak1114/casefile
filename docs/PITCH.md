# Casefile: 3-minute pitch

Demo run: **v2-full-3**. Start the UI with `cd web && CASEFILE_RUN=v2-full-3 npm run dev`, then open http://localhost:3000.

## One sentence

Casefile turns an insurance claim file into a cited timeline and party map, using a team of AI agents organised the
way a real liability claim is handled, and every line it shows is quoted from the documents and checked by code.

## Numbers to quote (v2-full-3)

| | Casefile team | Same model, one prompt |
|---|---|---|
| Answer-key events found | **49 of 49** (35/35 development, 14/14 held out) | 18 of 49 (14/35, 4/14) |
| Parties found | 18 of 19 | 7 of 19 |
| Relationships found | 4 of 13 (weak spot) | 0 of 13 |
| Claims kept after checking (refused) | 1,277 (5% refused) | 35 (35% refused) |
| Pages read | 1,737 of 1,737 | all, in one prompt |
| Time and cost | 14 minutes, 181 model calls, $5.18 | 1 call, $0.60 |

Collaboration: 8 disputes between the specialists over dates, each ruled by the lead from the quotes.

Against a general-purpose agent: 8 Claude (Sonnet) agents in parallel, no harness, same pages, same verifier and key:
**36 of 49** events (11/14 held out), 15/19 parties, 2/13 relationships, 369 claims kept, **16% refused**, no record of
which pages were read.

## Script

**0:00–0:30 · Board: the problem and the result**
"When a structure fails, the insurer's claim handler gets a claim file: contracts, letters, test reports, daily logs.
Before anything can be decided, someone has to work out who did what, and when. Document review is about 73% of
e-discovery cost. This is a real public record: the NTSB's file on the 2006 Boston tunnel ceiling collapse, 88 PDFs
and 1,737 pages. This is the project's history our agents rebuilt, one row per company. Every card is a quote."
*Click a card: the page image opens with the quote highlighted.*

**0:30–1:30 · Trajectory: the harness**
"It's organised like a real claims team. The claim professional (the lead) owns the file but never reads a page. It
assigns a defense lawyer, who works out the parties and what they agreed to, and hires a forensic engineer, who works
out the technical record. The engineer can't start until the lead approves it, as in real life. They read through
short-lived readers, up to 16 at once."
*Point at the lanes.* "The agents never call each other. They post messages to a log in MongoDB, and code decides who
wakes up and when."
*Click a `work.assigned` or `dispute.ruled` mark.* "Here's why: the lead's own reasoning, then the decision the harness
acted on. The two specialists disagreed on dates eight times; the lead ruled each one from the quotes."
"It read every page in 14 minutes for $5.18, and the lead could close the file only when code confirmed every document
was read."

**1:30–1:55 · Chronology or Parties: why it can be trusted**
*Open any line.* "Code checks every quote against the page, letter for letter, and that the names and dates are really
in it. Claims that fail are refused, never softened: 1,277 kept, 5% refused."
"It also says what is not in the record. For example, no test reports of long-term creep testing of the epoxy before
the collapse. It can only say that because every relevant page was read and a search found nothing."

**1:55–2:30 · Memory: the reading coverage and the long run**
*Point at the coverage map.* "One square per document: 172 of 172 read, 75 of them by both specialists, each through
their own lens. Nothing was skipped."
*Point at the lead's prompt chart.* "The run's memory lives in MongoDB, not in the prompt. The lead's prompt stayed under
10,000 tokens while the team read 1,737 pages. That's what makes a long job possible."

**2:30–3:00 · Evaluation: measured, not claimed**
"We held back the NTSB's own analysis as the answer key. The same model given all the pages in one prompt found 18 of 49
events. Claude agents working in parallel without a harness found 36, and one in six of their claims failed our quote
check. The team found all 49, including 14 of 14 we never tuned on, with 5% refused. Our weak spot is relationships between companies,
4 of 13. And it quotes the record: it never says who is at fault."

## Memory, explained simply

**In one line:** no agent remembers anything in its head. Everything goes into a shared case binder (MongoDB), and
every time an agent starts a task it gets a short briefing sheet printed fresh from that binder.

**Why it matters.** A model's only built-in memory is its prompt. 1,737 pages don't fit, and summarising to make room
loses details. If the team kept the case in their prompts, the lead would drown in text and facts would quietly drop out.

**The binder's tabs** (MongoDB collections), all written the moment something happens:

| Tab | What goes in it | Collection |
|---|---|---|
| Message board | every note between roles: assignments, reports, disputes, rulings | `events` |
| To-do list | who must do what, and what they wait for | `tasks` |
| Sign-out sheet | "I'm reading document 42", so no role reads it twice | `reservations` |
| Reading log | every page each reader was handed, and why | `coverage` |
| Verified facts | each fact with its exact quote and page | `findings` |
| Rejected facts | facts that failed the check, with the reason | `refusals` |
| Bookmarks | where each task was, to resume after an interruption | LangGraph `checkpoints` |
| Decision log | every decision, its reasoning summary and cost | `model_calls` |

**The briefing each role gets:**
- **Lead:** one line per document (type, date, author, who has read it), the counts, and the latest reports. Never page
  text, which is why its prompt stayed under about 10k tokens while 1,737 pages were read.
- **Counsel and the engineer:** the document list plus their own verified facts and open questions, to decide what to read next.
- **A reader:** only its batch of pages; it files its facts and ends.

**Example from the run:** a counsel reader reads a 1999 letter, and its pages go into the reading log. It proposes "B/PB
rejected the repair procedure on 23 Dec 1999" with a quote; the verifier checks it and files it under verified facts.
Counsel posts a report, which wakes the lead; the lead's briefing now shows that document as read and the new count,
never the letter itself. At the end, assembly builds the chronology from verified facts, not from anyone's memory.

**Why it's the long-horizon point:** nothing is forgotten (facts are on file, not summarised away), nothing overflows
(briefings stay small), nothing is done twice (sign-out sheet), everything is auditable (the binder is the record, shown on
Trajectory and Memory), and a task can resume from its bookmark (designed and unit-tested; not yet tested by a real
failover). It does not learn across cases: the binder belongs to one claim file.

**Say it like this:** "Our agents don't remember the case; MongoDB does. Each agent gets a fresh, short briefing from it
for every task, so the lead's prompt stayed under 10k tokens while the team read 1,737 pages."

## The reading coverage report: where it is and how to read it

**Where:** the **Memory** tab, section "Coverage of the claim file". The top bar also shows "Pages read 1,737 / 1,737".

**What it is:** a record of which pages were actually handed to a reader, by which specialist, and with what focus. The
harness writes it *before* the model runs. It is the evidence behind two claims we make:
1. **Nothing was skipped.** Every document was read before the file could close.
2. **Absences are earned.** "The record contains no X" is accepted only if every page in scope was read.

**How to read the map:** one square per document (172), in source-PDF order. Hover a square to see its file, type, date,
page count and who read it.
- **Solid blue:** read by both specialists (75 documents).
- **Light blue outline:** read by counsel only (42).
- **Green:** read by the engineer only (55).
- **Red outline:** not read (0 in this run).

**Say it like this:** "In insurance, 'coverage' means what a policy pays for. Here it means *reading coverage*: which
pages were read, and by whom. Every square is filled, so nothing in the file went unread, and 75 documents were read
twice, once by the lawyer and once by the engineer."

## If asked

- **Did you tune the answer key to your runs?** No. It comes from the NTSB report; its evidence pages were audited
  against the input files without looking at any run, and every run is scored against the same key.
- **Why not one big prompt?** Same model, same pages, one prompt: 18 of 49 events, 35% of claims refused.
- **Why not just use Claude Code?** We tried: 8 Claude agents in parallel, no harness, found 36 of 49 events and 16% of
  their claims failed the quote check, with no record of what they read. It is a different, stronger model, so this
  compares model and harness together; the fair next test is a generic agent loop on the same Gemini model.
- **What stops it running forever?** Token budget, task deadlines, a stall detector that wakes the lead, and a close check
  in code.
- **Is the data real?** Yes: the public NTSB docket HWY06MH024, unaltered. The NTSB's own analysis files are withheld and
  used only to score.
