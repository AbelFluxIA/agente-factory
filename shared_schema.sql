-- =============================================================================
-- Schema compartilhado — todos os agentes usam o mesmo Supabase
-- Execute este script UMA VEZ no Supabase SQL Editor
-- =============================================================================

-- Adiciona agent_id nas tabelas existentes (Vanessa já existente)
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100) NOT NULL DEFAULT 'vanessa';
ALTER TABLE messages      ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100) NOT NULL DEFAULT 'vanessa';

-- Índices para filtrar por agente rapidamente
CREATE INDEX IF NOT EXISTS idx_conversations_agent ON conversations(agent_id);
CREATE INDEX IF NOT EXISTS idx_messages_agent      ON messages(agent_id);

-- Tabela de logs estruturados de todos os agentes
CREATE TABLE IF NOT EXISTS agent_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id   VARCHAR(100)  NOT NULL,
    level      VARCHAR(20)   NOT NULL DEFAULT 'info',   -- info | warning | error
    event      VARCHAR(200)  NOT NULL,
    data       JSONB,
    created_at TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_agent   ON agent_logs(agent_id);
CREATE INDEX IF NOT EXISTS idx_logs_level   ON agent_logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_created ON agent_logs(created_at DESC);

-- View útil: erros das últimas 24h por agente
CREATE OR REPLACE VIEW v_errors_24h AS
SELECT
    agent_id,
    COUNT(*) AS total,
    MAX(created_at) AS last_error
FROM agent_logs
WHERE level = 'error'
  AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY agent_id
ORDER BY total DESC;

-- View útil: conversas de hoje por agente
CREATE OR REPLACE VIEW v_conversations_today AS
SELECT
    agent_id,
    COUNT(*)                                    AS total,
    COUNT(*) FILTER (WHERE converted = TRUE)    AS converted,
    MAX(last_seen)                              AS last_activity
FROM conversations
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY agent_id
ORDER BY total DESC;
