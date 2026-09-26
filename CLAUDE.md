# Casefile: working rules

Read `docs/PLAN.md` first. It holds the decision, the design, the build order and the one open question (the domain).

- Build only what is justified by use or measurement. No features for show, no made-up claims in the
  code, docs or pitch. When something is unproven, say so or remove it.
- Do not add self-rewriting prompts or policy, auto-tuning, rule proposing or pauses for a human
  unless asked. The only self-extension is the parser registry, and it is gated by deterministic checks.
- Gemini is the only model provider (key and model in `.env`). Atlas is the only database
  (`MONGO_CONNECTION_STRING`, database `CASEFILE_DATABASE`). No local Mongo.
- Every claim the agent makes cites `(document_id, quote)` and is checked by exact match. Negatives
  cite coverage. Tests for the verifier come before the agent.
- The case data is synthetic and must be labelled as such everywhere it is shown.
- Run long jobs in parallel (case generation, ingest, eval runs), and report failures early.
- Commit only when asked. End commit messages with the attribution trailer the session provides.
