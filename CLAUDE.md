# Casefile: working rules

Read `docs/DECISIONS.md` first: every approved decision, newest last, with links to the step plans
(`docs/00-*` onward). `docs/PLAN.md` is superseded and kept only for its reasoning.

- Build only what is justified by use or measurement. No features for show, no made-up claims in the
  code, docs or pitch. When something is unproven, say so or remove it.
- Do not add self-rewriting prompts or policy, auto-tuning, rule proposing or pauses for a human
  unless asked. A self-evolving or learning layer is planned for later; until the user asks for it,
  nothing in the harness rewrites itself.
- Model calls go through OpenRouter (`OPENROUTER_API` in `.env`), `google/gemini-3.8-flash` for every agent;
  Gemini models only unless the user says otherwise. External
  document-processing vendors (e.g. Extend, Reducto) may be used for ingestion if they measure better.
- The database is the team MongoDB Atlas cluster (`ATLAS_CONNECTION_STRING`, database
  `CASEFILE_DATABASE`), shared by the team. Never drop or overwrite it without the user's go-ahead.
  The local `mongodb-atlas-local` container is only for offline work.
- Build step by step: write a high-level plan for each step, get the user's approval, then build.
- Everything that crosses a boundary in the harness is a typed Pydantic model: documents, pages,
  citations, findings, coverage records, parties and relationships, tool inputs and outputs, subagent
  briefs and results, memory records, and run trace events. Model outputs are parsed into these models
  and rejected if they fail validation. No free dicts between components.
- Where a choice is ambiguous, settle it with a unit test or an ablation run in isolation, not by opinion.
- Every claim the agent makes cites `(document_id, quote)` and is checked by exact match. Negatives
  cite coverage. Tests for the verifier come before the agent.
- The case is the real public NTSB docket HWY06MH024 (Boston Central Artery ceiling collapse), cited
  to source and never altered. The agent reads the 88 files a claims examiner would receive; the 6
  files that are the NTSB's own analysis are withheld and, with final report HAR0702, form the answer
  key. Any synthetic material added later must be labelled as such everywhere it is shown. Casefile
  quotes documents; it never states fault.
- Run long jobs in parallel (case generation, ingest, eval runs), and report failures early.
- Commit only when asked. End commit messages with the attribution trailer the session provides.
