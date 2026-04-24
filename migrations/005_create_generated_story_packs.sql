-- Migration 005: Create generated_story_packs table
--
-- Stores AI-generated teacher story packs alongside their QA results.
-- Each pack is associated with a single unit (lesson + booklet both on that unit row).
-- human_approved is the gate before any pack is delivered to schools.

CREATE TABLE IF NOT EXISTS generated_story_packs (
    id                  serial          PRIMARY KEY,
    unit_id             integer         NOT NULL REFERENCES units(unit_id),
    year                integer         NOT NULL,
    model               varchar(64)     NOT NULL,
    story_pack_text     text,
    fact_check_results  jsonb,
    rubric_scores       jsonb,
    context_metadata    jsonb,
    input_tokens        integer,
    output_tokens       integer,
    warnings            text[],
    human_approved      boolean         NOT NULL DEFAULT false,
    approved_by         varchar(128),
    approved_at         timestamptz,
    created_at          timestamptz     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_story_packs_unit     ON generated_story_packs(unit_id);
CREATE INDEX IF NOT EXISTS idx_story_packs_approved ON generated_story_packs(human_approved);
