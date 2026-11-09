CREATE TABLE IF NOT EXISTS usage_events (
    id                BIGSERIAL PRIMARY KEY,
    team              TEXT        NOT NULL,
    model             TEXT        NOT NULL,
    prompt_tokens     INTEGER     NOT NULL,
    completion_tokens INTEGER     NOT NULL,
    latency_ms        INTEGER     NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS usage_events_team_time
    ON usage_events (team, created_at);