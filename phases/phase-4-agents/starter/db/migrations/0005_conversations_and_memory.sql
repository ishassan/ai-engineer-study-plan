-- Phase 4, week 12: the conversations and the long-term memory.
-- `make up` applies this file after the migrations of Phase 2.

-- One row for each conversation. A conversation belongs to one user.
CREATE TABLE conversations (
    id text PRIMARY KEY,
    user_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- The messages of each conversation, in the order of `id`. `content` holds a message in the
-- format of the model API: a string, or a list of content blocks. Compaction starts a new
-- context: the old messages stay in the table for the record, and the agent reads only the
-- messages of the last context.
CREATE TABLE conversation_messages (
    id bigserial PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    context integer NOT NULL DEFAULT 0,
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    content jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX conversation_messages_context ON conversation_messages (conversation_id, context, id);

-- The long-term memory: facts about a user that the agent saved. The vector comes from the
-- embedding service of Phase 2 (BAAI/bge-m3, 1024 numbers).
CREATE TABLE memories (
    id bigserial PRIMARY KEY,
    user_id text NOT NULL,
    text text NOT NULL,
    embedding vector(1024) NOT NULL,
    conversation_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX memories_user ON memories (user_id);
