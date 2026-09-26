// UI types derived from the generated Bundle type, so they always match the Python export models.
import type { Bundle } from "./bundle";

export type { Bundle };
export type Claim = Bundle["claims"][number];
export type Highlight = Claim["highlights"][number];
export type DocumentRow = Bundle["documents"][number];
export type PageRef = Bundle["pages"][string];
export type ChronologyRow = Bundle["chronology"][number];
export type Lane = Bundle["lanes"][number];
export type PartyRow = Bundle["parties"][number];
export type LinkRow = Bundle["links"][number];
export type TraceRow = Bundle["trace"][number];
export type WorkerRow = Bundle["workers"][number];
export type ScoreRow = NonNullable<Bundle["score"]>;
export type KeyEventRow = Bundle["answer_key"][number];
