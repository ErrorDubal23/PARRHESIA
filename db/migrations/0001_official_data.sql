-- 0001: official data (block A of the data model), contrasts and alerts.
--
-- Source of truth (docs/PROYECTO.md):
--   git        -> fichas, approvals, contrast-source config, evidence manifests.
--                 The tables marked "copy of git" are rewritten by app.db.sync on
--                 every run and are never edited by hand.
--   PostgreSQL -> downloads, observations, contrasts and alerts with their review
--                 history. Append-only tables cannot be updated or deleted.
--
-- Values are NUMERIC without scale: exact decimals as published, never floats.
-- Names follow the data model of docs/PROYECTO.md, in English:
--   fuente -> source, indicador -> indicator, serie -> series, descarga -> download,
--   observacion -> observation, nota_serie -> series_note, trampa -> context_gap.

-- Append-only guard ---------------------------------------------------------

CREATE FUNCTION forbid_update_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP;
END;
$$;

CREATE FUNCTION touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- Catalog (copy of git) -------------------------------------------------------

CREATE TABLE source (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text NOT NULL UNIQUE,          -- producer name or access channel code
    name        text NOT NULL,
    role        text NOT NULL CHECK (role IN ('producer', 'access_channel')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE indicator (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text NOT NULL UNIQUE,          -- inflation, unemployment, minimum_wage, homicides, ...
    category    text NOT NULL CHECK (category IN ('economy', 'security')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE series (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code                      text NOT NULL UNIQUE,     -- ficha code (catalog/series/<code>.yaml)
    indicator_id              uuid NOT NULL REFERENCES indicator (id),
    producer_source_id        uuid NOT NULL REFERENCES source (id),
    access_channel_source_id  uuid NOT NULL REFERENCES source (id),
    variant                   text NOT NULL,
    name                      text NOT NULL,            -- Spanish, as in the ficha
    unit                      text NOT NULL,
    unit_label                text NOT NULL,
    frequency                 text NOT NULL CHECK (frequency IN ('monthly', 'annual')),
    geography                 text NOT NULL,
    content_sha256            text NOT NULL,            -- ficha text without its approval block
    approved                  boolean NOT NULL,         -- approval valid for content_sha256
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now()
);

-- Every approval state seen in git, kept even after the ficha changes.
CREATE TABLE series_approval (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id       uuid NOT NULL REFERENCES series (id),
    status          text NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    content_sha256  text,
    approved_by     text,
    approved_on     date,
    comments        text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (series_id, status, content_sha256, approved_by, approved_on)
);

CREATE TABLE series_note (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id   uuid NOT NULL REFERENCES series (id) ON DELETE CASCADE,
    note_key    text NOT NULL,                 -- the note id in the ficha, or its position
    type        text NOT NULL,
    valid_from  text,                          -- YYYY, YYYY-MM or YYYY-MM-DD
    valid_to    text,
    status      text NOT NULL,                 -- confirmed, pending_official_source, official_sources_in_conflict
    body        jsonb NOT NULL,                -- text, quotes and sources exactly as in the ficha
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (series_id, note_key)
);

CREATE TABLE known_version_difference (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id     uuid NOT NULL REFERENCES series (id) ON DELETE CASCADE,
    period        text NOT NULL,
    level         text NOT NULL CHECK (level IN ('monthly', 'annual')),
    source        text NOT NULL,
    source_value  numeric NOT NULL,
    series_value  numeric NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (series_id, period, level, source)
);

-- Lines of the evidence manifests (evidence/*.jsonl).
CREATE TABLE evidence_file (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    manifest       text NOT NULL,              -- manifest file name, e.g. dane_publications
    source         text NOT NULL,              -- source key inside the manifest
    url            text NOT NULL,
    downloaded_at  timestamptz NOT NULL,
    sha256         text NOT NULL,
    size           bigint NOT NULL,
    location       text NOT NULL,              -- in the raw store (data/, not in git)
    changed        boolean NOT NULL,
    last_modified  text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (manifest, source, sha256, downloaded_at)
);

-- Context gaps ("trampas" in the working document; neutral glossary pending).
CREATE TABLE context_gap (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code         text NOT NULL UNIQUE,
    name         text NOT NULL,                -- Spanish, user-facing
    explanation  text NOT NULL,                -- Spanish, user-facing
    check_name   text,                         -- robustness check that detects it
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Data (source of truth in PostgreSQL; append-only) ---------------------------

CREATE TABLE download (
    id              uuid PRIMARY KEY,
    series_id       uuid NOT NULL REFERENCES series (id),
    channel         text NOT NULL,
    downloaded_at   timestamptz NOT NULL,
    source_updated  text,                      -- as the source states it
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX download_series_idx ON download (series_id, downloaded_at);

CREATE TABLE raw_file (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    download_id  uuid NOT NULL REFERENCES download (id),
    name         text NOT NULL,                -- role in the download: menu, metadata, rows, ...
    url          text NOT NULL,
    sha256       text NOT NULL,
    location     text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE observation (
    id               uuid PRIMARY KEY,
    seq              bigint GENERATED ALWAYS AS IDENTITY UNIQUE,   -- insertion order
    series_id        uuid NOT NULL REFERENCES series (id),
    download_id      uuid NOT NULL REFERENCES download (id),
    period           text NOT NULL CHECK (period ~ '^\d{4}(-\d{2}(-\d{2})?)?$'),
    territory        text NOT NULL,
    value            numeric,                  -- NULL only when the source published no value
    status           text NOT NULL CHECK (status IN ('quarantined', 'accepted')),
    contrast_status  text NOT NULL CHECK (contrast_status IN ('passed', 'pending', 'not_applicable', 'unavailable', 'failed')),
    contrast_level   text CHECK (contrast_level IN ('monthly', 'annual')),
    flags            text[] NOT NULL DEFAULT '{}',
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX observation_latest_idx ON observation (series_id, period, territory, seq DESC);

-- Every comparison behind an observation's contrast status.
CREATE TABLE contrast_check (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    observation_id    uuid NOT NULL REFERENCES observation (id),
    source            text NOT NULL,
    level             text NOT NULL CHECK (level IN ('monthly', 'annual')),
    compared_period   text NOT NULL,           -- the month, or the year for annual checks
    source_value      numeric,                 -- NULL when the check could not run (pending)
    series_value      numeric,
    tolerance         numeric NOT NULL,
    outcome           text NOT NULL CHECK (outcome IN ('passed', 'pending', 'failed')),
    known_difference  boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX contrast_check_observation_idx ON contrast_check (observation_id);

-- Alerts: one open alert per (series, period, territory, kind, value). Its
-- review history (who, when, why) lives in alert_event, which is append-only.
CREATE TABLE alert (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id       uuid NOT NULL REFERENCES series (id),
    observation_id  uuid NOT NULL REFERENCES observation (id),   -- first observation that raised it
    period          text NOT NULL,
    territory       text NOT NULL,
    kind            text NOT NULL,             -- the flag that raised it
    value           numeric,
    status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX alert_one_open_idx ON alert (series_id, period, territory, kind, value) NULLS NOT DISTINCT
    WHERE status = 'open';

CREATE TABLE alert_event (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id    uuid NOT NULL REFERENCES alert (id),
    event       text NOT NULL CHECK (event IN ('opened', 'commented', 'closed', 'reopened')),
    actor       text NOT NULL,                 -- 'system' or the reviewer's name
    reason      text,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX alert_event_alert_idx ON alert_event (alert_id, created_at);

-- Guards ---------------------------------------------------------------------

CREATE TRIGGER download_append_only BEFORE UPDATE OR DELETE ON download
    FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER raw_file_append_only BEFORE UPDATE OR DELETE ON raw_file
    FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER observation_append_only BEFORE UPDATE OR DELETE ON observation
    FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER contrast_check_append_only BEFORE UPDATE OR DELETE ON contrast_check
    FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER alert_event_append_only BEFORE UPDATE OR DELETE ON alert_event
    FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER series_approval_append_only BEFORE UPDATE OR DELETE ON series_approval
    FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
CREATE TRIGGER evidence_file_append_only BEFORE UPDATE OR DELETE ON evidence_file
    FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();

CREATE TRIGGER source_touch BEFORE UPDATE ON source FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER indicator_touch BEFORE UPDATE ON indicator FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER series_touch BEFORE UPDATE ON series FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER series_note_touch BEFORE UPDATE ON series_note FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER known_version_difference_touch BEFORE UPDATE ON known_version_difference
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER context_gap_touch BEFORE UPDATE ON context_gap FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER alert_touch BEFORE UPDATE ON alert FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- An alert can only change its status (open <-> closed), and only together with an
-- alert_event explaining it (enforced by app.db: status changes go through one function).
CREATE FUNCTION alert_only_status_changes() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.series_id, NEW.observation_id, NEW.period, NEW.territory, NEW.kind, NEW.value, NEW.created_at)
       IS DISTINCT FROM (OLD.series_id, OLD.observation_id, OLD.period, OLD.territory, OLD.kind, OLD.value, OLD.created_at) THEN
        RAISE EXCEPTION 'alert: only status may change';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER alert_only_status BEFORE UPDATE ON alert FOR EACH ROW EXECUTE FUNCTION alert_only_status_changes();
CREATE TRIGGER alert_no_delete BEFORE DELETE ON alert FOR EACH ROW EXECUTE FUNCTION forbid_update_delete();
