CREATE TABLE concepts (
    concept_id      SERIAL PRIMARY KEY,
    term            TEXT NOT NULL,
    subject_area    TEXT
);

CREATE TABLE occurrences (
    occurrence_id       SERIAL PRIMARY KEY,
    concept_id          INTEGER REFERENCES concepts(concept_id),
    subject             TEXT NOT NULL,
    year                INTEGER NOT NULL,
    term                TEXT NOT NULL,
    unit                TEXT NOT NULL,
    chapter             TEXT,
    slide_number        INTEGER,
    is_introduction     INTEGER NOT NULL,
    term_in_context     TEXT,
    source_path         TEXT,
    needs_review        INTEGER DEFAULT 0,
    review_reason       TEXT,
    validation_status   TEXT,
    vocab_confidence    FLOAT,
    vocab_match_type    TEXT,
    vocab_source        TEXT,
    audit_decision      TEXT,
    audit_notes         TEXT
);

CREATE TABLE edges (
    edge_id             SERIAL PRIMARY KEY,
    from_occurrence     INTEGER REFERENCES occurrences(occurrence_id),
    to_occurrence       INTEGER REFERENCES occurrences(occurrence_id),
    edge_type           TEXT,
    edge_nature         TEXT,
    confirmed_by        TEXT,
    confirmed_date      TEXT
);

CREATE INDEX idx_occurrences_concept_id ON occurrences(concept_id);
CREATE INDEX idx_occurrences_is_introduction ON occurrences(is_introduction);
CREATE INDEX idx_edges_from_occurrence ON edges(from_occurrence);
CREATE INDEX idx_edges_to_occurrence ON edges(to_occurrence);