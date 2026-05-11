-- =============================================================================
-- Limpeza automática de dados antigos — rode UMA VEZ no Supabase SQL Editor
-- =============================================================================
-- ANTES DE RODAR: ative a extensão pg_cron no Supabase
--   Dashboard → Database → Extensions → procure "pg_cron" → ative
-- =============================================================================

-- 1. Ativa a extensão (caso não tenha feito pelo painel)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- =============================================================================
-- ROTINA 1 — Apaga mensagens de conversas encerradas com mais de 90 dias
-- Roda toda domingo às 3h da manhã (horário UTC)
-- =============================================================================
SELECT cron.schedule(
  'limpar-mensagens-antigas',
  '0 3 * * 0',
  $$
    DELETE FROM messages
    WHERE conversation_id IN (
      SELECT id FROM conversations
      WHERE last_seen < NOW() - INTERVAL '90 days'
    );
  $$
);

-- =============================================================================
-- ROTINA 2 — Apaga conversas encerradas com mais de 90 dias
-- Roda logo depois, às 3h05
-- =============================================================================
SELECT cron.schedule(
  'limpar-conversas-antigas',
  '5 3 * * 0',
  $$
    DELETE FROM conversations
    WHERE last_seen < NOW() - INTERVAL '90 days';
  $$
);

-- =============================================================================
-- ROTINA 3 — Apaga logs de erro com mais de 30 dias
-- Roda todo domingo às 3h10
-- =============================================================================
SELECT cron.schedule(
  'limpar-logs-antigos',
  '10 3 * * 0',
  $$
    DELETE FROM agent_logs
    WHERE created_at < NOW() - INTERVAL '30 days';
  $$
);

-- =============================================================================
-- Para verificar se as rotinas foram criadas corretamente:
-- SELECT * FROM cron.job;
--
-- Para ver o histórico de execuções:
-- SELECT * FROM cron.job_run_details ORDER BY start_time DESC LIMIT 20;
--
-- Para remover uma rotina (se precisar):
-- SELECT cron.unschedule('limpar-mensagens-antigas');
-- =============================================================================
