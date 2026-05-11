# PROMPT — Criar Novo Agente WhatsApp

> **Como usar:** Coloque este arquivo junto com os arquivos do cliente numa pasta.
> Abra o Claude Code nessa pasta e cole o conteúdo abaixo no terminal.
> O Claude vai ler tudo, gerar o agente completo, subir no GitHub e fazer deploy na VPS.

---

## INSTRUÇÃO PARA O CLAUDE CODE

Você é um engenheiro especializado em criar agentes WhatsApp para a empresa AbelFluxIA.
Sua tarefa agora é criar um agente completo, do zero, seguindo exatamente a mesma
estrutura do agente de referência localizado em `/root/agente-vanessa-ia/`.

---

## PASSO 1 — LER OS ARQUIVOS DE INPUT

Leia TODOS os arquivos presentes no diretório atual. Identifique quais são:

| Tipo de arquivo | O que pode se chamar | O que extrair |
|---|---|---|
| **Formulário do cliente** | `formulario.md`, `formulario.txt`, `briefing.md` | Nome do agente, nome da empresa, nome da atendente, tom de voz, o que faz, o que não faz, número de notificação |
| **Base de conversas** | `conversas.txt`, `conversas.md`, `historico.txt` | Fluxo de atendimento real: quais etapas acontecem, em que ordem, como o lead reage |
| **Perguntas e respostas** | `rag.md`, `faq.md`, `perguntas_respostas.txt` | Base de conhecimento do agente — perguntas frequentes e respostas corretas |
| **Modelos de prompts** | `prompts.md`, `prompt_base.md` | Linguagem já validada, frases-chave, tom de voz |
| **APIs externas** | `apis.yaml`, `apis.md`, `integracoes.md` | Nome da API, URL, autenticação, endpoints disponíveis |

Se algum desses arquivos não existir, prossiga sem ele e anote o que ficou faltando.

---

## PASSO 2 — EXTRAIR INFORMAÇÕES CHAVE

Após ler todos os arquivos, extraia e documente internamente:

### 2.1 Identidade do Agente
- `NOME_AGENTE` — nome da atendente virtual (ex: "Sofia", "Ana", "Clara")
- `NOME_EMPRESA` — nome do negócio (ex: "Clínica Bella", "Academia FitLife")
- `NOME_SLUG` — nome em snake_case para uso no código (ex: `sofia_clinica`, `ana_academia`)
- `DESCRICAO` — uma frase resumindo o propósito
- `NUMERO_NOTIFICACAO` — número WhatsApp do dono para receber alertas de fechamento
- `PORTA` — porta HTTP do serviço (escolha uma não usada na VPS, verifique com `docker ps`)

### 2.2 Personalidade (para `prompts.py`)
- Tom de voz: formal, informal, caloroso, direto?
- O que o agente FARÁ (escopo positivo)
- O que o agente NUNCA fará (guardrails)
- Vocabulário preferido, palavras a evitar
- Emoji: sim ou não?

### 2.3 Etapas de Atendimento (para `graph.py` e `nodes.py`)
A partir das conversas reais, mapeie no máximo 6 etapas sequenciais. Para cada etapa:
- Número e label (ex: `1 — Captura de nome`)
- Intent identificado
- Condições de avanço para próxima etapa
- Ação padrão quando sem contexto claro

### 2.4 Fluxos Predefinidos (para `flows.py`)
Identifique respostas fixas que não precisam de IA (ex: "enviar cardápio", "enviar localização", "transferir para humano"). Esses viram `FLOW_*` em `flows.py`.

### 2.5 Dados a Extrair do Lead
- Quais campos o agente precisa capturar? (nome, interesse, telefone, horário preferido, etc.)
- Esses campos viram campos no `state.py` e entradas do JSON de resposta do LLM.

### 2.6 APIs Externas (se houver)
- Nome, URL base, tipo de autenticação, quais endpoints usar

---

## PASSO 3 — GERAR A ESTRUTURA DE ARQUIVOS

Crie a seguinte estrutura em `/root/{NOME_SLUG}/`:

```
{NOME_SLUG}/
├── AGENTS.md
├── ARCHITECTURE.md
├── CLAUDE.md
├── RULES.md
├── .env.example
├── .gitignore
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── docker-compose.prod.yml
├── docs/
│   ├── design-docs/
│   │   └── core-beliefs.md
│   └── product-specs/
│       └── personality.md
├── nginx/
│   └── nginx.conf
├── scripts/
│   ├── setup.sh
│   └── deploy.sh
├── src/{NOME_SLUG}/
│   ├── __init__.py
│   ├── main.py
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   ├── state.py
│   │   └── tools.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── webhooks.py
│   │   ├── health.py
│   │   └── dashboard.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── logging.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── redis_memory.py
│   │   └── postgres_history.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── whatsapp.py
│   └── personality/
│       ├── __init__.py
│       ├── prompts.py
│       └── flows.py
└── tests/
    ├── __init__.py
    ├── test_agent.py
    └── test_webhooks.py
```

---

## PASSO 4 — GERAR CADA ARQUIVO

Use o agente da Vanessa em `/root/agente-vanessa-ia/` como **referência técnica exata** para cada arquivo abaixo. Adapte apenas o conteúdo (personalidade, etapas, fluxos) — mantenha a estrutura técnica idêntica.

### 4.1 `src/{NOME_SLUG}/core/config.py`

Copie a estrutura de `/root/agente-vanessa-ia/src/vanessa/core/config.py` e adapte:
- Substitua `vanessa` pelo `NOME_SLUG`
- Adicione campos extras de `.env` se o agente tiver APIs específicas
- Mantenha OBRIGATORIAMENTE os campos Zynk:
  ```python
  zynk_webhook_url: str = Field(default="", description="URL base do zynk-webhook")
  zynk_admin_secret: str = Field(default="", description="Secret para autenticar no zynk-webhook")
  zynk_supabase_url: str = Field(default="", description="URL do Supabase do Zynk para CRM")
  zynk_supabase_service_key: str = Field(default="", description="Service key do Supabase")
  zynk_org_id: str = Field(default="", description="ID da organização no CRM do Zynk")
  ```
- O campo `agent_name` deve ter o nome correto do agente
- Adicione campo `{NOME_SLUG}_notification_phone` com o número de notificação

### 4.2 `src/{NOME_SLUG}/personality/prompts.py`

Este é o arquivo mais importante. Gere com base nos arquivos de input:

```python
SYSTEM_PROMPT = """
[Personalidade completa do agente baseada no formulário e nas conversas reais]
[Tom de voz, quem é, o que faz, o que não faz]
[Inclua regras extraídas do RAG/FAQ como conhecimento base]
"""

STEP_RULES: dict[int, str] = {
    1: """PASSO 1 — [Label da etapa]
[Condições e regras extraídas das conversas reais]
""",
    # ... uma entrada por etapa mapeada
}

BRAIN_DECISION_PROMPT = """
[Adapte o prompt do cérebro da Vanessa para os dados a extrair deste agente]
[Inclua os campos específicos deste agente no JSON de resposta]
"""

HUMANIZER_SYSTEM_PROMPT = """
[Adapte o humanizador com o vocabulário e tom específico deste agente]
"""

GUARDRAIL_CHECK_PROMPT = """
[Liste as regras extraídas do formulário e do RAG que nunca podem ser violadas]
"""
```

Se existir um arquivo `rag.md` ou `perguntas_respostas.md`, incorpore o conhecimento
diretamente no `SYSTEM_PROMPT` como uma seção `## BASE DE CONHECIMENTO`.

### 4.3 `src/{NOME_SLUG}/personality/flows.py`

Para cada fluxo predefinido identificado nas conversas, crie uma constante `FLOW_*`.
Estrutura de cada flow (lista de dicts com `type` e `content`):

```python
FLOW_BOAS_VINDAS = [
    {"type": "text", "content": "Olá! Seja bem-vindo..."},
]

FLOW_ENCERRAMENTO = [
    {"type": "text", "content": "Foi um prazer te atender!"},
]

FLOW_TRANSFERIR = [
    {"type": "text", "content": "Vou te conectar com nossa equipe agora."},
]
```

### 4.4 `src/{NOME_SLUG}/agent/state.py`

Baseie em `/root/agente-vanessa-ia/src/vanessa/agent/state.py`. Adapte os campos
extraídos do lead para os específicos deste agente. Mantenha os campos base:
`messages`, `current_step`, `sub_state`, `objection_count`, `action`, `response`,
`next_step`, `notify_operator`.

### 4.5 `src/{NOME_SLUG}/agent/graph.py`

Baseie em `/root/agente-vanessa-ia/src/vanessa/agent/graph.py`.
- Mantenha os nós `main_brain`, `humanize`, `guardrails` obrigatoriamente
- Adicione um nó por fluxo predefinido encontrado em `flows.py`
- A lógica de roteamento via `route_action` deve mapear para os fluxos definidos

### 4.6 `src/{NOME_SLUG}/agent/nodes.py`

Baseie em `/root/agente-vanessa-ia/src/vanessa/agent/nodes.py`.
- Adapte imports para o `NOME_SLUG` correto
- Adapte `_format_history` para usar o nome da atendente do agente
- Adapte `_build_step_rules` para os campos do state deste agente
- Mantenha a estrutura de `main_brain`, `humanize_response`, `apply_guardrails`
- Gere uma função `flow_*` para cada fluxo predefinido

### 4.7 `src/{NOME_SLUG}/services/whatsapp.py`

**COPIE EXATAMENTE** de `/root/agente-vanessa-ia/src/vanessa/services/whatsapp.py`.
Apenas substitua imports e referências ao nome do agente. A integração Zynk deve
permanecer intacta — é ela que conecta ao chat.

### 4.8 `src/{NOME_SLUG}/memory/redis_memory.py` e `postgres_history.py`

**COPIE EXATAMENTE** de `/root/agente-vanessa-ia/src/vanessa/memory/`.
Apenas adapte os imports com o `NOME_SLUG` correto.

### 4.9 `src/{NOME_SLUG}/api/webhooks.py`

Baseie em `/root/agente-vanessa-ia/src/vanessa/api/webhooks.py`.
- Mantenha o debounce de 5 segundos
- Mantenha a transcrição de áudio via Whisper
- Mantenha a integração com Zynk para salvar mensagens
- Adapte apenas o nome do agente nas mensagens de log

### 4.10 `src/{NOME_SLUG}/main.py`

Baseie em `/root/agente-vanessa-ia/src/vanessa/main.py`.
Adapte apenas o título e nome nas strings.

### 4.11 `src/{NOME_SLUG}/core/logging.py`

**COPIE EXATAMENTE** de `/root/agente-vanessa-ia/src/vanessa/core/logging.py`.

### 4.12 `pyproject.toml`

Baseie em `/root/agente-vanessa-ia/pyproject.toml`.
Mude apenas: `name`, `description`, e o script entry point para o `NOME_SLUG`.

### 4.13 `Dockerfile`

**COPIE EXATAMENTE** de `/root/agente-vanessa-ia/Dockerfile`.
Adapte apenas os paths de `src/vanessa/` para `src/{NOME_SLUG}/`.

### 4.14 `docker-compose.yml`

Baseie em `/root/agente-vanessa-ia/docker-compose.yml`. Adapte:
- Nome dos serviços: `{NOME_SLUG}`, `{NOME_SLUG}-redis`, `{NOME_SLUG}-postgres`
- Nome da rede: `{NOME_SLUG}-net`
- Porta do agente: `{PORTA}:8000` (porta escolhida no passo 2.1)
- Nome dos volumes: `{NOME_SLUG}-postgres-data`, `{NOME_SLUG}-redis-data`
- Container names com o slug correto

### 4.15 `nginx/nginx.conf`

Baseie em `/root/agente-vanessa-ia/nginx/nginx.conf`.
A porta interna do proxy deve apontar para `{NOME_SLUG}:8000`.
O `server_name` deve ser deixado em branco (o usuário preencherá com o domínio real).

### 4.16 `.env.example`

Gere um `.env.example` completo com TODAS as variáveis necessárias:

```bash
# META BUSINESS API (WhatsApp)
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_APP_SECRET=

# LLM
LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-6

# REDIS
REDIS_URL=redis://localhost:6379/0
REDIS_SESSION_TTL=86400

# POSTGRESQL
DATABASE_URL=postgresql+asyncpg://{NOME_SLUG}:senha@localhost:5432/{NOME_SLUG}_db
POSTGRES_USER={NOME_SLUG}
POSTGRES_PASSWORD=
POSTGRES_DB={NOME_SLUG}_db

# AGENTE
AGENT_NAME={NOME_AGENTE}
{NOME_SLUG_UPPER}_NOTIFICATION_PHONE=

# ZYNK CHAT (integração obrigatória)
ZYNK_WEBHOOK_URL=http://localhost:3001
ZYNK_ADMIN_SECRET=
ZYNK_SUPABASE_URL=
ZYNK_SUPABASE_SERVICE_KEY=
ZYNK_ORG_ID=

# [APIs externas do agente, se houver]
# NOME_API_URL=
# NOME_API_KEY=

# DASHBOARD
DASHBOARD_PASSWORD=
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO
```

### 4.17 `.gitignore`

**COPIE EXATAMENTE** de `/root/agente-vanessa-ia/.gitignore`.

### 4.18 `scripts/deploy.sh` e `scripts/setup.sh`

Baseie em `/root/agente-vanessa-ia/scripts/`. Adapte apenas os nomes dos serviços.

### 4.19 `AGENTS.md`

Crie o mapa do projeto com:
- Identidade (nome, empresa, propósito, cliente, stack)
- Estrutura de arquivos
- Fluxo principal de uma mensagem (diagrama)
- Etapas mapeadas (resumo)
- Variáveis de ambiente necessárias
- Como fazer deploy
- Onde está a personalidade e como editar

### 4.20 `CLAUDE.md`

```markdown
# CLAUDE.md — Instruções para o Claude Code

## Primeira Ação em Qualquer Sessão
Leia AGENTS.md antes de qualquer outra coisa.

## Stack e Convenções
- Python 3.11 com uv (uv run, uv sync, nunca pip install diretamente)
- Imports absolutos a partir de src/{NOME_SLUG}/
- Async/await em toda a camada de I/O
- Type hints obrigatórios em todas as funções públicas
- Pydantic para validação de dados

## O que Não Fazer
- Não remova o nó apply_guardrails do grafo LangGraph
- Não commite .env com valores reais
- Não altere personality.md sem atualizar prompts.py junto
- Não desative a integração Zynk

## Referências Rápidas
- Personalidade: docs/product-specs/personality.md
- Grafo: src/{NOME_SLUG}/agent/graph.py
- Prompts: src/{NOME_SLUG}/personality/prompts.py
- Regras: RULES.md
```

### 4.21 `RULES.md`

Liste todas as regras extraídas do formulário e do RAG que são absolutas —
o que o agente jamais pode fazer, dizer ou prometer.

---

## PASSO 5 — INFRAESTRUTURA COMPARTILHADA (Redis e Supabase)

### Redis — use o mesmo Upstash da Vanessa com prefixo por agente

No `.env` do novo agente, use o **mesmo** `REDIS_URL` da Vanessa (Upstash).
O isolamento é garantido pelo prefixo automático: `{NOME_SLUG}:session:{telefone}`.
Não crie um Redis separado.

### Supabase — use o mesmo banco com `agent_id`

No `.env` do novo agente, use o **mesmo** `DATABASE_URL` da Vanessa.
O Supabase já tem a coluna `agent_id` em todas as tabelas.
O `postgres_history.py` do novo agente deve ter:
```python
AGENT_ID = "{NOME_SLUG}"   # identificador único deste agente no banco compartilhado
```

E o modelo `Conversation` deve usar `agent_id=AGENT_ID` ao criar registros
(siga exatamente `/root/agente-vanessa-ia/src/vanessa/memory/postgres_history.py`).

### Registrar no Zynk Monitor

Após criar o agente, adicione-o no arquivo `/root/zynk-monitor/agents.json`:
```json
{
  "id": "{NOME_SLUG}",
  "name": "{NOME_AGENTE}",
  "container": "{NOME_SLUG}-ia",
  "port": {PORTA},
  "color": "[escolha uma cor hex que não esteja em uso]"
}
```
Cores disponíveis (use uma diferente das já usadas):
- Vanessa: #7c3aed (roxo)
- Débora: #0ea5e9 (azul)
- Sol: #f97316 (laranja)
- JP Eventos: #22c55e (verde)
- Próximas: #ec4899 (rosa), #f59e0b (amarelo), #14b8a6 (teal), #ef4444 (vermelho)

Depois reinicie o monitor para ele começar a capturar logs do novo container:
```bash
cd /root/zynk-monitor && docker compose restart
```

---

## PASSO 6 — CRIAR REPOSITÓRIO NO GITHUB E FAZER PUSH

```bash
# Inicializar git
cd /root/{NOME_SLUG}
git init
git add .
git commit -m "feat: agente {NOME_AGENTE} — estrutura inicial"

# Criar repositório no GitHub (org: AbelFluxIA)
gh repo create AbelFluxIA/{NOME_SLUG} --private --description "{DESCRICAO}"

# Push
git remote add origin https://github.com/AbelFluxIA/{NOME_SLUG}.git
git branch -M main
git push -u origin main
```

Se o comando `gh` não estiver autenticado, informe o usuário para rodar:
`gh auth login`

---

## PASSO 7 — CONFIGURAR E FAZER DEPLOY NA VPS

### 6.1 Criar o arquivo .env

Duplique o `.env.example` e preencha o que for possível automaticamente:
```bash
cp .env.example .env
```

Informe o usuário que ele precisa preencher manualmente:
- `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`
- `OPENAI_API_KEY` ou `ANTHROPIC_API_KEY`
- `POSTGRES_PASSWORD` e `DASHBOARD_PASSWORD`
- Campos Zynk: `ZYNK_ADMIN_SECRET`, `ZYNK_SUPABASE_URL`, `ZYNK_SUPABASE_SERVICE_KEY`, `ZYNK_ORG_ID`

Os valores do Zynk o usuário pode encontrar em `/root/agente-vanessa-ia/.env` —
são os mesmos para todos os agentes da organização.

### 6.2 Verificar porta disponível

```bash
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep -E ":[0-9]+"
```

Confirme que a porta escolhida no Passo 2.1 não está em uso.

### 6.3 Fazer o deploy

```bash
cd /root/{NOME_SLUG}
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

### 6.4 Verificar se está rodando

```bash
curl http://localhost:{PORTA}/health
docker logs {NOME_SLUG} --tail=30
```

---

## PASSO 8 — RELATÓRIO FINAL

Ao terminar, apresente ao usuário um resumo com:

1. **Agente criado:** nome, slug, porta
2. **GitHub:** URL do repositório
3. **Deploy:** status (online/erro)
4. **O que falta o usuário fazer:**
   - Preencher variáveis do `.env` (liste quais)
   - Configurar o webhook no painel Meta Business
   - Configurar domínio/nginx (se quiser HTTPS)
   - Registrar o agente no Zynk Chat (qual `ORG_ID` usar)
5. **Arquivos gerados que merecem revisão manual:**
   - `src/{NOME_SLUG}/personality/prompts.py` — verifique se o tom está correto
   - `RULES.md` — confirme as regras com o cliente

---

## REFERÊNCIA TÉCNICA

Sempre que tiver dúvida sobre como implementar algo, leia o arquivo equivalente em:
`/root/agente-vanessa-ia/src/vanessa/`

Essa é a implementação de referência. Mantenha 100% de compatibilidade estrutural.

---

## NOTAS IMPORTANTES

- **Nunca** commite `.env` com valores reais
- **Sempre** inclua a integração Zynk em `whatsapp.py` e em `config.py`
- **Sempre** mantenha o nó `apply_guardrails` no grafo
- **Sempre** use `uv` para gerenciar dependências, nunca `pip` direto
- **Sempre** use async/await na camada de I/O
- Os agentes Vanessa, Débora, Sol, JP Eventos já estão rodando na VPS —
  não interfira nas portas e redes deles
