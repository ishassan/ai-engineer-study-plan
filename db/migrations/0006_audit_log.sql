-- Phase 4, week 15: the audit log of the tool calls of the agent.
-- `make up` applies this file after the migrations of week 12.
--
-- The agent writes one row for each tool call, after the call ends or after a person refuses
-- it. The checks of weeks 15 and 16 read this table, so keep the names of the table and of its
-- columns.

CREATE TABLE audit_log (
    id bigserial PRIMARY KEY,
    -- The time of the row: when the call ended, or when a person refused it.
    called_at timestamptz NOT NULL DEFAULT now(),
    -- The user who asked the question (the header X-User of POST /ask).
    user_id text NOT NULL,
    conversation_id text,
    tool text NOT NULL,
    -- The arguments of the call, as the model sent them.
    arguments jsonb NOT NULL,
    -- The text that went back to the model: the result, the error, or the refusal.
    result text NOT NULL,
    -- not_needed: the tool does not need an approval.
    -- approved or refused: the decision of a person (POST /approve).
    approval text NOT NULL CHECK (approval IN ('not_needed', 'approved', 'refused')),
    -- The person who approved or refused the call (the header X-User of POST /approve).
    approver text,
    CHECK ((approval = 'not_needed') = (approver IS NULL))
);

CREATE INDEX audit_log_conversation ON audit_log (conversation_id, id);
