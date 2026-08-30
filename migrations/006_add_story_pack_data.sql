-- Migration 006: Add structured story_pack_data column
--
-- Stores the parsed JSON structure of a generated story pack alongside
-- the raw text. Allows rich rendering without re-parsing on the frontend.
-- NULL for packs generated before this migration.

ALTER TABLE generated_story_packs
    ADD COLUMN IF NOT EXISTS story_pack_data jsonb;
