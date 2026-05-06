#!/usr/bin/env python3
"""
Agente Factory — Gera projetos de agente WhatsApp seguindo a estrutura Vanessa IA.

Uso:
    python factory.py create --config meu_agente.yaml
    python factory.py init    # cria um config.yaml de exemplo interativamente

O que é gerado:
    {nome_agente}/
    ├── src/{nome}/agent/graph.py      ← grafo LangGraph com as etapas definidas
    ├── src/{nome}/agent/nodes.py      ← nós de processamento
    ├── src/{nome}/agent/state.py      ← estado da conversa
    ├── src/{nome}/personality/prompts.py  ← prompt com a personalidade
    ├── src/{nome}/personality/flows.py   ← fluxos predefinidos das etapas
    ├── src/{nome}/services/apis.py    ← integrações externas configuradas
    ├── src/{nome}/api/webhooks.py     ← webhook FastAPI
    ├── src/{nome}/main.py             ← entry point
    ├── docker-compose.yml
    ├── Dockerfile
    ├── .env.example
    ├── AGENTS.md                      ← documentação do agente gerado
    └── pyproject.toml
"""

import argparse
import os
import subprocess
import sys
import yaml
from pathlib import Path
from datetime import datetime
from textwrap import dedent

# ─── Schema de configuração ──────────────────────────────────────────────────

REQUIRED_FIELDS = ['nome', 'descricao', 'prompt_personalidade', 'etapas', 'regras']

EXAMPLE_CONFIG = """\
# ─────────────────────────────────────────────────────────────────────────────
# Configuração do Agente
# ─────────────────────────────────────────────────────────────────────────────

# Identidade
nome: meu_agente          # slug sem espaços (usado nos arquivos gerados)
descricao: "Agente de vendas para clínica de estética"
cliente: "Clínica Bella"

# ─── Prompt de personalidade ─────────────────────────────────────────────────
# Descreva quem é o agente, tom de voz, como fala, o que NÃO faz
prompt_personalidade: |
  Você é Sofia, consultora de vendas da Clínica Bella.
  Fale de forma calorosa, próxima e profissional.
  Você ajuda clientes a agendar procedimentos estéticos.
  Nunca prometa resultados garantidos.
  Nunca fale mal de concorrentes.

# ─── Etapas de atendimento ───────────────────────────────────────────────────
# Cada etapa vira um nó no grafo LangGraph
# intent: identificador interno
# label: nome amigável
# descricao: o que acontece nessa etapa
# resposta_padrao: mensagem base (pode ser personalizada pelo LLM)
etapas:
  - intent: INTERESSE_INICIAL
    label: "Primeiro contato"
    descricao: "Lead acabou de entrar em contato pela primeira vez"
    resposta_padrao: "Olá! Tudo bem? Sou a Sofia da Clínica Bella. Como posso te ajudar hoje?"

  - intent: DUVIDA_PROCEDIMENTO
    label: "Dúvida sobre procedimento"
    descricao: "Lead pergunta sobre um procedimento específico"
    resposta_padrao: "Ótima pergunta! Vou te explicar tudo sobre esse procedimento..."

  - intent: OBJECAO_PRECO
    label: "Objeção de preço"
    descricao: "Lead resistente ao valor do procedimento"
    resposta_padrao: "Entendo sua preocupação com o investimento. Deixa eu te mostrar o custo-benefício..."

  - intent: PRONTO_AGENDAR
    label: "Pronto para agendar"
    descricao: "Lead quer marcar horário"
    resposta_padrao: "Que ótimo! Vamos verificar nossa agenda..."

  - intent: ENCERRAMENTO
    label: "Encerrando atendimento"
    descricao: "Lead quer encerrar a conversa"
    resposta_padrao: "Foi um prazer te atender! Qualquer dúvida, estou aqui."

# ─── APIs externas ────────────────────────────────────────────────────────────
# Cada API vira uma ferramenta (tool) disponível para o agente
apis:
  - nome: agenda
    descricao: "Sistema de agendamento da clínica"
    url_env: AGENDA_API_URL       # nome da variável de ambiente com a URL
    auth_env: AGENDA_API_KEY      # nome da variável de ambiente com a chave
    endpoints:
      - nome: verificar_disponibilidade
        metodo: GET
        path: /slots
        descricao: "Verifica horários disponíveis"
      - nome: criar_agendamento
        metodo: POST
        path: /appointments
        descricao: "Cria um novo agendamento"

  - nome: catalogo
    descricao: "Catálogo de procedimentos e preços"
    url_env: CATALOGO_API_URL
    auth_env: CATALOGO_API_KEY
    endpoints:
      - nome: listar_procedimentos
        metodo: GET
        path: /procedures
        descricao: "Lista todos os procedimentos disponíveis"

# ─── Regras (guardrails) ──────────────────────────────────────────────────────
# Verificações que o agente SEMPRE faz antes de enviar uma mensagem
regras:
  - "Nunca prometar resultado garantido de procedimento estético"
  - "Nunca compartilhar dados de outros clientes"
  - "Nunca mencionar concorrentes pelo nome"
  - "Sempre manter tom profissional e respeitoso"
  - "Se não souber a resposta, admitir e oferecer contato com atendente humano"

# ─── Configurações opcionais ──────────────────────────────────────────────────
llm_model: "gpt-4o-mini"    # ou claude-3-5-haiku-20241022
notificacao_fechamento:
  ativo: true
  whatsapp: "5511999999999"  # número do dono para notificar ao fechar venda
"""

# ─── Gerador de arquivos ─────────────────────────────────────────────────────

def slugify(name: str) -> str:
    return name.lower().replace(' ', '_').replace('-', '_')

def generate_prompts(cfg: dict) -> str:
    nome = cfg['nome']
    etapas = cfg.get('etapas', [])
    regras = cfg.get('regras', [])
    regras_str = '\n'.join(f'- {r}' for r in regras)
    intents_str = ', '.join(e['intent'] for e in etapas)

    estrutura = cfg.get('estrutura_prompt', '').strip()
    estrutura_block = f'\n\n# ESTRUTURA DO PROMPT\n{estrutura}' if estrutura else ''

    return dedent(f'''\
    """Prompts e personalidade do agente {nome}."""

    SYSTEM_PROMPT = """{cfg["prompt_personalidade"].strip()}{estrutura_block}"""

    INTENT_CLASSIFIER_PROMPT = """
    Classifique a mensagem do usuário em uma das categorias: {intents_str}, FORA_ESCOPO
    Retorne APENAS o nome da categoria, sem explicação.
    Mensagem: {{message}}
    """

    HUMANIZER_SYSTEM_PROMPT = """# SUA FUNÇÃO
    Você é {nome} respondendo pessoalmente no WhatsApp. Reescreva a mensagem-base como se fosse um ser humano real digitando agora.

    # REGRAS
    1. PRESERVE O CONTEÚDO — não invente informações além do que está escrito.
    2. QUEBRE EM MENSAGENS CURTAS — máximo 2-3 frases por bloco. Use ||| para separar blocos (cada ||| vira uma mensagem separada com delay entre elas).
    3. SEM ELOGIOS VAZIOS — nunca "Perfeito!", "Incrível!", "Que ótimo!". Seja genuíno.
    4. PRESERVE PERGUNTAS — se termina com pergunta, preserve-a exatamente.
    5. SEM TRAVESSÃO (—) — use ponto final, vírgula, ou quebre com |||.
    6. EMOJIS — no máximo 1 em toda a resposta. Prefira zero.

    # COMO HUMANO ESCREVE NO WHATSAPP
    - Varia como começa cada resposta. Nunca inicie dois blocos com a mesma palavra.
    - Usa conectores naturais: "olha", "sabe", "é que", "então", "a questão é"
    - Às vezes começa com o ponto principal direto, sem prefácio
    - Usa reticências (...) quando há pausa natural de pensamento

    # SAÍDA
    Apenas o texto final com ||| onde houver quebras. Sem explicações."""

    GUARDRAIL_CHECK_PROMPT = """Verifique se a resposta abaixo viola alguma das regras:
    {regras_str}

    Resposta a verificar: {{draft_response}}

    Se violar: responda VIOLATION: [motivo]
    Se estiver ok: responda OK"""

    # Respostas padrão por intenção
    DEFAULT_RESPONSES = {{
    {chr(10).join(f'    "{e["intent"]}": """{e["resposta_padrao"]}""",' for e in etapas)}
    }}
    ''')

def generate_state(cfg: dict) -> str:
    return dedent(f'''\
    """Estado da conversa do agente {cfg["nome"]}."""
    from typing import Annotated, Literal, Optional
    from dataclasses import dataclass, field
    from langchain_core.messages import BaseMessage
    from langgraph.graph.message import add_messages

    Stage = Literal["nurturing", "qualifying", "closing", "closed", "escalated"]

    @dataclass
    class ConversationState:
        phone: str = ""
        messages: Annotated[list[BaseMessage], add_messages] = field(default_factory=list)

        # Dados extraídos durante o atendimento
        user_name: str = ""
        context: dict = field(default_factory=dict)

        # Intenção classificada pelo LLM
        current_intent: str = ""
        intent_history: list[str] = field(default_factory=list)

        # Funil de vendas
        stage: Stage = "nurturing"

        # Decisão do agente
        draft_response: str = ""

        # Mensagens a enviar (pode ser múltiplas com delays entre elas)
        # Use ||| no draft_response para gerar múltiplas mensagens
        messages_to_send: list[str] = field(default_factory=list)
        message_delays: list[int] = field(default_factory=list)

        # Flags
        guardrail_triggered: bool = False
        notify_operator: bool = False
        error: Optional[str] = None
    ''')

def generate_nodes(cfg: dict) -> str:
    etapas = cfg.get('etapas', [])
    apis = cfg.get('apis', [])
    nome = cfg['nome']

    intent_blocks = '\n'.join(dedent(f'''\
        async def handle_{e["intent"].lower()}(state: ConversationState) -> ConversationState:
            """Nó: {e["label"]} — {e["descricao"]}"""
            # TODO: adicionar lógica específica para {e["intent"]}
            return {{**state, "response": DEFAULT_RESPONSES.get("{e["intent"]}", "")}}
    ''') for e in etapas)

    tools_block = '\n'.join(f'    # {a["nome"]}: {a["descricao"]}' for a in apis)

    return dedent(f'''\
    """Nós de processamento do agente {nome}."""
    import json
    from langchain_core.messages import HumanMessage, AIMessage
    from langchain_openai import ChatOpenAI
    from .state import ConversationState
    from ..personality.prompts import (
        SYSTEM_PROMPT, INTENT_CLASSIFIER_PROMPT,
        HUMANIZER_SYSTEM_PROMPT, GUARDRAIL_CHECK_PROMPT, DEFAULT_RESPONSES,
    )
    from ..services.apis import {", ".join(slugify(a["nome"]) + "_client" for a in apis) if apis else "# nenhuma API configurada"}

    _llm_fast = ChatOpenAI(model="{cfg.get("llm_model", "gpt-4o-mini")}", temperature=0.3)
    _llm_creative = ChatOpenAI(model="{cfg.get("llm_model", "gpt-4o-mini")}", temperature=0.8)


    def _history_text(state: ConversationState) -> str:
        lines = []
        for m in state.messages[-20:]:
            if isinstance(m, HumanMessage):
                lines.append(f"Lead: {{m.content}}")
            elif isinstance(m, AIMessage):
                lines.append(f"Agente: {{m.content}}")
        return "\\n".join(lines) or "(início da conversa)"


    async def classify_intent(state: ConversationState) -> ConversationState:
        """Classifica a intenção da última mensagem."""
        last_msg = next((m.content for m in reversed(state.messages) if isinstance(m, HumanMessage)), "")
        resp = await _llm_fast.ainvoke(
            INTENT_CLASSIFIER_PROMPT.format(message=last_msg)
        )
        intent = resp.content.strip().upper()
        state.current_intent = intent
        state.intent_history = state.intent_history + [intent]
        return state


    {intent_blocks}

    async def handle_fora_escopo(state: ConversationState) -> ConversationState:
        """Responde tópicos fora do escopo sem sair do personagem."""
        state.draft_response = "Esse assunto foge um pouco do meu escopo por aqui. Posso te ajudar com outra coisa?"
        return state


    async def generate_response(state: ConversationState) -> ConversationState:
        """Gera rascunho da resposta com o LLM usando o system prompt do agente."""
        history = _history_text(state)
        base = DEFAULT_RESPONSES.get(state.current_intent, "")
        prompt = (
            f"{{SYSTEM_PROMPT}}\\n\\n"
            f"Histórico:\\n{{history}}\\n\\n"
            f"Resposta base sugerida: {{base}}\\n\\n"
            f"Escreva a resposta final. Use ||| para separar em múltiplas mensagens se necessário."
        )
        resp = await _llm_creative.ainvoke([HumanMessage(content=prompt)])
        state.draft_response = resp.content.strip()
        return state


    async def humanize_response(state: ConversationState) -> ConversationState:
        """Passa o rascunho pelo humanizador — quebra em mensagens curtas com |||."""
        if not state.draft_response:
            return state

        # Se já tem |||, usa direto sem reprocessar
        if "|||" in state.draft_response:
            parts = [p.strip() for p in state.draft_response.split("|||") if p.strip()]
            state.messages_to_send = parts
            state.message_delays = [0] + [3] * (len(parts) - 1)
            return state

        resp = await _llm_creative.ainvoke([
            {{"role": "system", "content": HUMANIZER_SYSTEM_PROMPT}},
            {{"role": "user", "content": f"Transforme mantendo o sentido:\\n\\n{{state.draft_response}}"}},
        ])
        humanized = resp.content.strip()
        parts = [p.strip() for p in humanized.split("|||") if p.strip()]
        if not parts:
            parts = [state.draft_response]

        state.messages_to_send = parts
        # Primeiro delay mínimo 2s (simula digitação), demais 3s
        state.message_delays = [2] + [3] * (len(parts) - 1)
        return state


    async def apply_guardrails(state: ConversationState) -> ConversationState:
        """Verifica se alguma mensagem viola as regras antes de enviar."""
        if not state.messages_to_send:
            return state
        full_text = " ".join(state.messages_to_send)
        check = await _llm_fast.ainvoke(
            GUARDRAIL_CHECK_PROMPT.format(draft_response=full_text)
        )
        if str(check.content).strip().startswith("VIOLATION"):
            state.guardrail_triggered = True
            state.messages_to_send = ["Desculpe, não consigo ajudar com isso agora."]
            state.message_delays = [0]
        return state


    async def send_message(state: ConversationState) -> ConversationState:
        """Envia mensagens via WhatsApp com delays entre elas."""
        from ..services.whatsapp import send_messages_sequence, mark_as_read
        if state.messages_to_send:
            import asyncio
            asyncio.create_task(
                send_messages_sequence(state.phone, state.messages_to_send, state.message_delays)
            )
        return state


    async def persist_history(state: ConversationState) -> ConversationState:
        """Persiste histórico no Redis."""
        from ..memory.redis_memory import redis_memory
        combined = " | ".join(state.messages_to_send)
        if state.messages and isinstance(state.messages[-1], HumanMessage):
            await redis_memory.save_message(state.phone, "user", state.messages[-1].content)
        if combined:
            await redis_memory.save_message(state.phone, "assistant", combined)
        return state


    # APIs disponíveis:
    {tools_block if tools_block else "    # Nenhuma API externa configurada"}
    ''')

def generate_graph(cfg: dict) -> str:
    etapas = cfg.get('etapas', [])
    intents = [e['intent'] for e in etapas]
    node_imports = ', '.join([
        'classify_intent', 'generate_response', 'humanize_response',
        'apply_guardrails', 'send_message', 'persist_history',
        'handle_fora_escopo',
    ] + [f'handle_{i.lower()}' for i in intents])

    routing_cases = '\n        '.join(
        f'"{i}": "handle_{i.lower()}",' for i in intents
    )

    node_registrations = '\n'.join(
        f'    graph.add_node("handle_{i.lower()}", handle_{i.lower()})' for i in intents
    )

    edges_from_routing = '\n'.join(
        f'    graph.add_edge("handle_{i.lower()}", "generate_response")' for i in intents
    )

    return dedent(f'''\
    """Grafo LangGraph do agente {cfg["nome"]}."""
    from langgraph.graph import StateGraph, END
    from .state import ConversationState
    from .nodes import (
        {node_imports}
    )


    def route_by_intent(state: ConversationState) -> str:
        routes = {{
            {routing_cases}
            "FORA_ESCOPO": "handle_fora_escopo",
        }}
        return routes.get(state.current_intent, "handle_fora_escopo")


    def build_graph():
        graph = StateGraph(ConversationState)

        # Pipeline principal
        graph.add_node("classify_intent", classify_intent)
        graph.add_node("generate_response", generate_response)
        graph.add_node("humanize_response", humanize_response)
        graph.add_node("apply_guardrails", apply_guardrails)
        graph.add_node("send_message", send_message)
        graph.add_node("persist_history", persist_history)
        graph.add_node("handle_fora_escopo", handle_fora_escopo)

        # Nós de intenção
    {node_registrations}

        # Fluxo: classify → roteamento → generate → humanize → guardrails → send → persist
        graph.set_entry_point("classify_intent")
        graph.add_conditional_edges("classify_intent", route_by_intent)

    {edges_from_routing}
        graph.add_edge("handle_fora_escopo", "generate_response")
        graph.add_edge("generate_response", "humanize_response")
        graph.add_edge("humanize_response", "apply_guardrails")
        graph.add_edge("apply_guardrails", "send_message")
        graph.add_edge("send_message", "persist_history")
        graph.add_edge("persist_history", END)

        return graph.compile()


    agent = build_graph()
    ''')

def generate_apis_service(cfg: dict) -> str:
    apis = cfg.get('apis', [])
    if not apis:
        return '"""Sem APIs externas configuradas."""\n'

    clients = []
    for api in apis:
        slug = slugify(api['nome'])
        endpoints = api.get('endpoints', [])
        methods = '\n'.join(dedent(f'''\
            async def {e["nome"]}(self, **kwargs):
                """{e["descricao"]}"""
                resp = await self.session.{e["metodo"].lower()}(f"{{self.base_url}}{e["path"]}", **kwargs)
                resp.raise_for_status()
                return resp.json()
        ''') for e in endpoints)

        clients.append(dedent(f'''\
        class {slug.title().replace("_","")}Client:
            """{api["descricao"]}"""
            def __init__(self):
                import httpx, os
                self.base_url = os.environ["{api["url_env"]}"]
                self.api_key = os.environ["{api["auth_env"]}"]
                self.session = httpx.AsyncClient(headers={{"Authorization": f"Bearer {{self.api_key}}"}})

            {methods}

        {slug}_client = {slug.title().replace("_","")}Client()
        '''))

    return '\n'.join(clients)

def generate_gitignore() -> str:
    return dedent('''\
    __pycache__/
    *.py[cod]
    *.egg-info/
    .env
    .venv/
    venv/
    dist/
    build/
    *.log
    .DS_Store
    ''')

def generate_env_example(cfg: dict) -> str:
    apis = cfg.get('apis', [])
    api_vars = '\n'.join(
        f'# {a["nome"]}\n{a["url_env"]}=\n{a["auth_env"]}='
        for a in apis
    )
    notif = cfg.get('notificacao_fechamento', {})
    return dedent(f'''\
    # WhatsApp (Meta Business API)
    WHATSAPP_VERIFY_TOKEN=
    WHATSAPP_ACCESS_TOKEN=
    WHATSAPP_PHONE_NUMBER_ID=

    # LLM
    OPENAI_API_KEY=
    # ou: ANTHROPIC_API_KEY=

    # Banco de dados
    REDIS_URL=redis://localhost:6379
    DATABASE_URL=postgresql://user:pass@localhost:5432/{cfg["nome"]}

    # APIs externas
    {api_vars}

    # Notificações
    NOTIFICATION_WHATSAPP={notif.get("whatsapp", "")}
    ''')

def generate_agents_md(cfg: dict) -> str:
    etapas = cfg.get('etapas', [])
    apis = cfg.get('apis', [])
    regras = cfg.get('regras', [])
    nome = cfg['nome']
    cliente = cfg.get('cliente', nome)
    ts = datetime.now().strftime('%Y-%m-%d')

    etapas_table = '\n'.join(f'| `{e["intent"]}` | {e["label"]} | {e["descricao"]} |' for e in etapas)
    apis_table = '\n'.join(f'| `{a["nome"]}` | {a["descricao"]} | `{a["url_env"]}` |' for a in apis) if apis else '| — | Nenhuma API externa | — |'
    regras_list = '\n'.join(f'- {r}' for r in regras)

    return dedent(f'''\
    # AGENTS.md — {nome}

    > Gerado por agente-factory em {ts}

    ## Identidade

    | Campo       | Valor                    |
    |-------------|--------------------------|
    | Nome        | {nome}                   |
    | Cliente     | {cliente}                |
    | Gerado em   | {ts}                     |
    | Stack       | Python · LangGraph · FastAPI · Redis · PostgreSQL |

    ## Etapas de Atendimento

    | Intent | Label | Descrição |
    |--------|-------|-----------|
    {etapas_table}

    ## APIs Externas

    | Nome | Descrição | URL env |
    |------|-----------|---------|
    {apis_table}

    ## Regras (Guardrails)

    {regras_list}

    ## Estrutura de Arquivos

    ```
    {nome}/
    ├── src/{nome}/
    │   ├── agent/
    │   │   ├── graph.py       ← grafo LangGraph
    │   │   ├── nodes.py       ← nós de processamento
    │   │   └── state.py       ← estado da conversa
    │   ├── personality/
    │   │   ├── prompts.py     ← system prompt + guardrails
    │   │   └── flows.py       ← fluxos predefinidos
    │   ├── services/
    │   │   ├── apis.py        ← clientes das APIs externas
    │   │   └── whatsapp.py    ← Meta Business API
    │   ├── memory/
    │   │   ├── redis_memory.py
    │   │   └── postgres_history.py
    │   ├── api/
    │   │   └── webhooks.py    ← FastAPI
    │   └── main.py
    ├── docker-compose.yml
    ├── Dockerfile
    ├── .env.example
    └── pyproject.toml
    ```

    ## Comandos

    ```bash
    uv sync
    uv run uvicorn src.{nome}.main:app --reload --port 8000
    docker-compose up -d
    ```
    ''')

def generate_dockerfile(cfg: dict) -> str:
    return dedent(f'''\
    FROM python:3.11-slim
    WORKDIR /app
    RUN pip install uv
    COPY pyproject.toml .
    RUN uv sync --no-dev
    COPY src/ src/
    CMD ["uv", "run", "uvicorn", "src.{cfg["nome"]}.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ''')

def generate_docker_compose(cfg: dict) -> str:
    nome = cfg['nome']
    return dedent(f'''\
    version: "3.9"
    services:
      {nome}:
        build: .
        ports:
          - "8000:8000"
        env_file: .env
        depends_on:
          - redis
          - postgres
        restart: unless-stopped

      redis:
        image: redis:7-alpine
        restart: unless-stopped

      postgres:
        image: postgres:15-alpine
        environment:
          POSTGRES_DB: {nome}
          POSTGRES_USER: user
          POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD}}
        volumes:
          - pgdata:/var/lib/postgresql/data
        restart: unless-stopped

    volumes:
      pgdata:
    ''')

def generate_pyproject(cfg: dict) -> str:
    nome = cfg['nome']
    return dedent(f'''\
    [project]
    name = "{nome}"
    version = "0.1.0"
    requires-python = ">=3.11"
    dependencies = [
        "fastapi>=0.115",
        "uvicorn[standard]>=0.32",
        "langgraph>=0.2",
        "langchain-openai>=0.3",
        "redis[hiredis]>=5.0",
        "asyncpg>=0.30",
        "httpx>=0.28",
        "pydantic-settings>=2.6",
        "python-dotenv>=1.0",
    ]

    [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"
    ''')

def generate_main(cfg: dict) -> str:
    nome = cfg['nome']
    return dedent(f'''\
    """Entry point do agente {nome}."""
    from fastapi import FastAPI
    from .api.webhooks import router as webhook_router

    app = FastAPI(title="{nome}", version="0.1.0")
    app.include_router(webhook_router)


    @app.get("/health")
    async def health():
        return {{"status": "ok", "agent": "{nome}"}}
    ''')

def generate_webhooks(cfg: dict) -> str:
    nome = cfg['nome']
    return dedent(f'''\
    """Webhook FastAPI — recebe mensagens do WhatsApp com debounce."""
    import asyncio
    import hmac
    import hashlib
    import os
    import re
    from fastapi import APIRouter, Request, Response, HTTPException, Query, Body
    from langchain_core.messages import HumanMessage

    from ..agent.graph import agent
    from ..agent.state import ConversationState
    from ..memory.redis_memory import redis_memory
    from ..services.whatsapp import (
        parse_incoming, send_messages_sequence, mark_as_read,
    )

    router = APIRouter(prefix="/webhook")

    # Janela de debounce: aguarda X segundos de silêncio antes de processar.
    # Isso acumula mensagens quebradas do cliente em um único texto.
    DEBOUNCE_SECONDS = 5

    # Geração por telefone — cancela timers antigos se chegar nova mensagem
    _debounce_gen: dict[str, int] = {{}}

    # Mensagens que são só símbolos (cliente respondia uma mensagem com ".")
    _ONLY_SYMBOLS = re.compile(r"^[^\\w]+$")

    # Saudações que indicam conversa nova
    _GREETINGS = {{
        "oi", "oi!", "olá", "olá!", "ola", "hello", "hi",
        "bom dia", "boa tarde", "boa noite",
    }}


    @router.get("/whatsapp")
    async def verify_webhook(
        hub_mode: str = Query(alias="hub.mode", default=""),
        hub_verify_token: str = Query(alias="hub.verify_token", default=""),
        hub_challenge: str = Query(alias="hub.challenge", default=""),
    ) -> Response:
        if hub_mode == "subscribe" and hub_verify_token == os.environ["WHATSAPP_VERIFY_TOKEN"]:
            return Response(content=hub_challenge, media_type="text/plain")
        raise HTTPException(status_code=403, detail="Verificação falhou")


    @router.post("/whatsapp")
    async def receive_message(request: Request) -> dict:
        """Recebe evento, valida assinatura, acumula no buffer e agenda debounce."""
        raw_body = await request.body()
        sig = request.headers.get("x-hub-signature-256", "")
        secret = os.environ.get("WHATSAPP_APP_SECRET", "")
        if secret:
            expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise HTTPException(status_code=401, detail="Assinatura inválida")

        payload = await request.json()
        try:
            changes = payload["entry"][0]["changes"][0]["value"]
            messages = changes.get("messages", [])
        except (KeyError, IndexError):
            return {{"status": "no_messages"}}

        if not messages:
            return {{"status": "no_messages"}}

        message = messages[0]
        phone = message["from"]
        message_id = message["id"]
        message_type = message.get("type", "")

        if message_type == "text":
            user_text = message["text"]["body"]
        else:
            # Outros tipos (imagem, sticker, etc.) são ignorados por padrão
            return {{"status": "ignored"}}

        await mark_as_read(message_id)

        # Resolve quoted reply com símbolo: lead respondeu uma msg com "."
        context_obj = message.get("context", {{}})
        quoted_wamid = context_obj.get("id", "")
        if quoted_wamid and (len(user_text.strip()) <= 2 or _ONLY_SYMBOLS.match(user_text.strip())):
            original = await redis_memory.get_wamid(quoted_wamid)
            if original:
                user_text = original

        await redis_memory.save_wamid(message_id, user_text)
        await redis_memory.buffer_message(phone, user_text)

        gen = _debounce_gen.get(phone, 0) + 1
        _debounce_gen[phone] = gen
        asyncio.create_task(_debounced_process(phone, gen))

        return {{"status": "ok"}}


    async def _debounced_process(phone: str, gen: int) -> None:
        """Aguarda silêncio e processa todas as mensagens acumuladas como uma só."""
        await asyncio.sleep(DEBOUNCE_SECONDS)

        if _debounce_gen.get(phone) != gen:
            return  # chegou mensagem mais nova, ela vai processar

        buffered = await redis_memory.flush_buffer(phone)
        if not buffered:
            return

        # Combina todas as mensagens quebradas em um único texto
        combined_text = "\\n".join(buffered)

        history = await redis_memory.load_messages(phone)
        session = await redis_memory.load_session(phone)

        # Auto-reset: saudação em sessão avançada = lead recomeçando
        step = session.get("current_step", 1)
        if step > 1 and combined_text.strip().lower().rstrip("!") in _GREETINGS:
            await redis_memory.reset_session(phone)
            session = {{}}
            history = []

        state = ConversationState(
            phone=phone,
            messages=history + [HumanMessage(content=combined_text)],
            stage=session.get("stage", "nurturing"),
            user_name=session.get("user_name", ""),
            context=session.get("context", {{}}),
        )

        raw = await agent.ainvoke(state)

        messages_to_send: list[str] = raw.get("messages_to_send") or []
        message_delays: list[int] = raw.get("message_delays") or []

        if messages_to_send:
            # Garante mínimo de 2s no primeiro (simula digitação)
            if message_delays:
                message_delays[0] = max(message_delays[0], 2)
            asyncio.create_task(send_messages_sequence(phone, messages_to_send, message_delays))

        await redis_memory.save_session(phone, {{
            "stage": raw.get("stage", "nurturing"),
            "current_step": raw.get("current_step", step),
            "user_name": raw.get("user_name", ""),
            "context": raw.get("context", {{}}),
        }})


    @router.post("/reset-session")
    async def reset_session_endpoint(phone: str = Body(..., embed=True)) -> dict:
        """Reseta sessão Redis de um número (chamado ao reiniciar conversa no Zynk)."""
        await redis_memory.reset_session(phone)
        _debounce_gen.pop(phone, None)
        return {{"status": "reset"}}
    ''')

# ─── CLI ─────────────────────────────────────────────────────────────────────

def cmd_init(args):
    """Cria um arquivo config.yaml de exemplo."""
    output = args.output or 'config.yaml'
    if Path(output).exists() and not args.force:
        print(f"Arquivo {output} já existe. Use --force para sobrescrever.")
        sys.exit(1)
    Path(output).write_text(EXAMPLE_CONFIG)
    print(f"✓ Config de exemplo criada em: {output}")
    print(f"  Edite o arquivo e então rode: python factory.py create --config {output}")


def cmd_create(args):
    """Gera o projeto do agente a partir de um config.yaml."""
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Arquivo de config não encontrado: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    # Validação
    missing = [k for k in REQUIRED_FIELDS if k not in cfg]
    if missing:
        print(f"Campos obrigatórios faltando: {', '.join(missing)}")
        sys.exit(1)

    nome = slugify(cfg['nome'])
    cfg['nome'] = nome
    output_dir = Path(args.output or nome)

    print(f"\n🤖 Gerando agente: {nome}")
    print(f"   Destino: {output_dir}/\n")

    # Estrutura de diretórios
    dirs = [
        output_dir / f'src/{nome}/agent',
        output_dir / f'src/{nome}/personality',
        output_dir / f'src/{nome}/services',
        output_dir / f'src/{nome}/memory',
        output_dir / f'src/{nome}/api',
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        (d / '__init__.py').touch()

    # __init__ do pacote raiz
    (output_dir / f'src/{nome}/__init__.py').touch()

    # Gerar arquivos
    files = {
        f'src/{nome}/agent/graph.py':        generate_graph(cfg),
        f'src/{nome}/agent/nodes.py':         generate_nodes(cfg),
        f'src/{nome}/agent/state.py':         generate_state(cfg),
        f'src/{nome}/personality/prompts.py': generate_prompts(cfg),
        f'src/{nome}/services/apis.py':       generate_apis_service(cfg),
        f'src/{nome}/api/webhooks.py':        generate_webhooks(cfg),
        f'src/{nome}/main.py':                generate_main(cfg),
        'AGENTS.md':                          generate_agents_md(cfg),
        '.env.example':                       generate_env_example(cfg),
        '.gitignore':                         generate_gitignore(),
        'Dockerfile':                         generate_dockerfile(cfg),
        'docker-compose.yml':                 generate_docker_compose(cfg),
        'pyproject.toml':                     generate_pyproject(cfg),
    }

    for path, content in files.items():
        full = output_dir / path
        full.write_text(content)
        print(f"   ✓ {path}")

    # Copiar serviços base da Vanessa (whatsapp.py, memory/)
    _copy_base_services(output_dir, nome)
    generate_docs_structure(cfg, output_dir)

    print(f"\n✅ Agente '{nome}' gerado em {output_dir}/")

    repo_url = None
    github_owner = getattr(args, 'github', None)
    if github_owner:
        repo_url = push_to_github(output_dir, nome, github_owner)

    print(f"\nPróximos passos:")
    print(f"  1. cd {output_dir}")
    print(f"  2. cp .env.example .env && preencha com suas chaves")
    if repo_url:
        print(f"  3. No EasyPanel: New App → GitHub → {repo_url}")
        print(f"  4. Adicione as variáveis do .env no EasyPanel → Environment")
    else:
        print(f"  3. uv sync")
        print(f"  4. uv run uvicorn src.{nome}.main:app --reload")


def push_to_github(output_dir: Path, nome: str, github_owner: str, private: bool = True) -> str | None:
    """Cria repo no GitHub e faz o primeiro push. Retorna a URL ou None se falhar."""
    repo_name = nome.replace('_', '-')
    visibility = '--private' if private else '--public'

    # Verifica se gh está instalado
    if subprocess.run(['which', 'gh'], capture_output=True).returncode != 0:
        print('   ✗ GitHub CLI (gh) não encontrado. Instale em: https://cli.github.com')
        return None

    print(f'\n   Criando repositório {github_owner}/{repo_name}...')
    r = subprocess.run(
        ['gh', 'repo', 'create', f'{github_owner}/{repo_name}', visibility,
         '--description', f'Agente IA: {nome} — gerado por agente-factory'],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f'   ✗ Erro ao criar repo: {r.stderr.strip() or r.stdout.strip()}')
        return None

    repo_url = r.stdout.strip()
    print(f'   ✓ Repositório criado: {repo_url}')

    git_cmds = [
        ['git', 'init'],
        ['git', 'checkout', '-b', 'main'],
        ['git', 'add', '.'],
        ['git', 'commit', '-m', f'Initial commit — {nome} gerado por agente-factory'],
        ['git', 'remote', 'add', 'origin', f'https://github.com/{github_owner}/{repo_name}.git'],
        ['git', 'push', '-u', 'origin', 'main'],
    ]
    for cmd in git_cmds:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(output_dir))
        if r.returncode != 0:
            print(f'   ✗ Erro em `{" ".join(cmd)}`: {r.stderr.strip()}')
            return None

    print(f'   ✓ Código enviado!')
    return f'https://github.com/{github_owner}/{repo_name}'


def _copy_base_services(output_dir: Path, nome: str):
    """Gera serviços base com as técnicas da Vanessa IA."""
    whatsapp_content = dedent('''\
    """Cliente Meta Business API — envia mensagens com delays e suporte a imagens."""
    import asyncio
    import hmac
    import hashlib
    import os
    import httpx

    BASE_URL = "https://graph.facebook.com/v21.0"


    def verify_signature(payload: bytes, signature: str) -> bool:
        secret = os.environ.get("WHATSAPP_APP_SECRET", "")
        if not secret:
            return True
        expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


    async def send_text_message(to: str, text: str) -> bool:
        token = os.environ["WHATSAPP_ACCESS_TOKEN"]
        phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": "text",
                    "text": {"body": text, "preview_url": False},
                },
            )
        return resp.status_code == 200


    async def send_image_message(to: str, image_url: str) -> bool:
        token = os.environ["WHATSAPP_ACCESS_TOKEN"]
        phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{BASE_URL}/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "image",
                    "image": {"link": image_url},
                },
            )
        return resp.status_code == 200


    async def send_messages_sequence(to: str, texts: list[str], delays: list[int]) -> None:
        """Envia múltiplas mensagens com delay entre elas.
        Suporta [IMAGE:url] para enviar imagens inline na sequência.
        """
        for delay, text in zip(delays, texts):
            if delay > 0:
                await asyncio.sleep(delay)
            if text.startswith("[IMAGE:") and text.endswith("]"):
                await send_image_message(to, text[7:-1])
            else:
                await send_text_message(to, text)


    async def mark_as_read(message_id: str) -> None:
        """Marca mensagem como lida (duplo check azul)."""
        token = os.environ["WHATSAPP_ACCESS_TOKEN"]
        phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{BASE_URL}/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
            )


    async def notify_operator(phone: str, message: str) -> None:
        """Notifica o número do operador/dono sobre evento importante."""
        operator_phone = os.environ.get("OPERATOR_NOTIFICATION_PHONE", "")
        if operator_phone:
            await send_text_message(operator_phone, message)


    def parse_incoming(body: dict) -> dict | None:
        """Extrai dados da mensagem recebida. Retorna None para eventos sem mensagem."""
        try:
            entry = body["entry"][0]["changes"][0]["value"]
            msg = entry["messages"][0]
            contact = entry["contacts"][0]
            return {
                "phone": msg["from"],
                "name": contact["profile"].get("name", ""),
                "text": msg.get("text", {}).get("body", ""),
                "message_id": msg["id"],
                "type": msg.get("type", "text"),
            }
        except (KeyError, IndexError):
            return None
    ''')

    redis_content = dedent('''\
    """Memória de sessão via Redis — buffer de debounce, histórico e estado."""
    import json
    import os
    from typing import Optional
    import redis.asyncio as aioredis
    from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

    SESSION_TTL = int(os.environ.get("REDIS_SESSION_TTL", 86400))  # 24h = janela WhatsApp


    class RedisMemory:
        def __init__(self) -> None:
            self._client: Optional[aioredis.Redis] = None

        async def client(self) -> aioredis.Redis:
            if self._client is None:
                self._client = await aioredis.from_url(
                    os.environ["REDIS_URL"], encoding="utf-8", decode_responses=True
                )
            return self._client

        def _key(self, phone: str) -> str:
            return f"session:{phone}"

        async def load_messages(self, phone: str) -> list[BaseMessage]:
            r = await self.client()
            raw = await r.get(self._key(phone))
            if not raw:
                return []
            data = json.loads(raw)
            result: list[BaseMessage] = []
            for m in data.get("messages", []):
                if m["role"] == "user":
                    result.append(HumanMessage(content=m["content"]))
                else:
                    result.append(AIMessage(content=m["content"]))
            return result

        async def load_session(self, phone: str) -> dict:
            r = await self.client()
            raw = await r.get(self._key(phone))
            if not raw:
                return {}
            data = json.loads(raw)
            return {k: v for k, v in data.items() if k != "messages"}

        async def save_message(self, phone: str, role: str, content: str) -> None:
            r = await self.client()
            raw = await r.get(self._key(phone))
            data = json.loads(raw) if raw else {"messages": []}
            data.setdefault("messages", [])
            data["messages"].append({"role": role, "content": content})
            data["messages"] = data["messages"][-40:]  # mantém últimas 40 mensagens
            await r.setex(self._key(phone), SESSION_TTL, json.dumps(data))

        async def save_session(self, phone: str, fields: dict) -> None:
            r = await self.client()
            raw = await r.get(self._key(phone))
            data = json.loads(raw) if raw else {"messages": []}
            data.update(fields)
            await r.setex(self._key(phone), SESSION_TTL, json.dumps(data))

        async def reset_session(self, phone: str) -> None:
            r = await self.client()
            await r.delete(self._key(phone))
            await r.delete(f"msgbuf:{phone}")

        # ── Debounce buffer ──────────────────────────────────────────────────
        # Acumula mensagens quebradas do cliente antes de processar

        async def buffer_message(self, phone: str, text: str) -> None:
            r = await self.client()
            await r.rpush(f"msgbuf:{phone}", text)
            await r.expire(f"msgbuf:{phone}", 30)

        async def flush_buffer(self, phone: str) -> list[str]:
            r = await self.client()
            key = f"msgbuf:{phone}"
            msgs = await r.lrange(key, 0, -1)
            await r.delete(key)
            return msgs or []

        # ── Quoted reply lookup ──────────────────────────────────────────────
        # Resolve quando o lead responde uma mensagem com "."

        async def save_wamid(self, wamid: str, text: str) -> None:
            r = await self.client()
            await r.setex(f"wamid:{wamid}", 86400, text)

        async def get_wamid(self, wamid: str) -> str | None:
            r = await self.client()
            return await r.get(f"wamid:{wamid}")


    redis_memory = RedisMemory()
    ''')

    (output_dir / f'src/{nome}/services/whatsapp.py').write_text(whatsapp_content)
    (output_dir / f'src/{nome}/memory/redis_memory.py').write_text(redis_content)
    print(f"   ✓ src/{nome}/services/whatsapp.py")
    print(f"   ✓ src/{nome}/memory/redis_memory.py")


# ─── Gerador da estrutura de docs (padrão artigo OpenAI Codex) ───────────────

def generate_docs_structure(cfg: dict, output_dir: Path):
    """Gera docs/ organizado como índice — AGENTS.md curto aponta para cá."""
    nome = cfg['nome']
    cliente = cfg.get('cliente', nome)
    etapas = cfg.get('etapas', [])
    regras = cfg.get('regras', [])
    apis = cfg.get('apis', [])

    docs = output_dir / 'docs'

    # ── design-docs/core-beliefs.md ──────────────────────────────────────────
    (docs / 'design-docs').mkdir(parents=True, exist_ok=True)
    (docs / 'design-docs' / 'core-beliefs.md').write_text(dedent(f'''\
    # Crenças Centrais — {nome}

    > Por que este agente existe e o que NÃO abrimos mão.

    ## 1. O agente serve o humano, não o contrário
    Cada interação deve deixar o lead com uma sensação positiva, independente
    de fechar ou não. Nunca pressionar, nunca mentir.

    ## 2. Transparência sobre limitações
    Se o agente não sabe, ele diz "não sei" e oferece escalar para humano.
    Prometer o que não existe destrói confiança.

    ## 3. Contexto é memória
    O agente lembra o que foi dito na conversa. Não repete perguntas.
    Não finge que não houve mensagens anteriores.

    ## 4. Velocidade não é pressa
    Responder rápido é bom. Responder errado rápido é pior que demorar.
    Guardrails existem para isso.

    ## 5. Dados pertencem ao cliente
    Nenhuma informação do lead é compartilhada, vendida ou usada fora
    do contexto de atendimento de {cliente}.
    '''))

    # ── design-docs/index.md ─────────────────────────────────────────────────
    (docs / 'design-docs' / 'index.md').write_text(dedent(f'''\
    # Índice — Design Docs

    | Documento | O que contém |
    |-----------|-------------|
    | [core-beliefs.md](core-beliefs.md) | Princípios inegociáveis do agente |
    '''))

    # ── product-specs/ ────────────────────────────────────────────────────────
    (docs / 'product-specs').mkdir(parents=True, exist_ok=True)
    etapas_block = '\n'.join(f'### {e["label"]} (`{e["intent"]}`)\n{e["descricao"]}\n\n**Resposta base:** {e["resposta_padrao"]}\n' for e in etapas)
    (docs / 'product-specs' / 'fluxo-atendimento.md').write_text(dedent(f'''\
    # Fluxo de Atendimento — {nome}

    ## Etapas

    {etapas_block}

    ## Transições
    - Qualquer etapa pode ir para `ENCERRAMENTO` se o lead quiser parar
    - `OBJECAO_PRECO` tem até 2 tentativas antes de oferecer alternativa
    - Após fechamento, notificar operador humano
    '''))

    regras_block = '\n'.join(f'- [ ] {r}' for r in regras)
    (docs / 'product-specs' / 'guardrails.md').write_text(dedent(f'''\
    # Guardrails — {nome}

    Verificações executadas **antes de todo envio**. Se uma falhar, a
    resposta é corrigida ou substituída por escalada para humano.

    {regras_block}

    ## Como verificar
    O nó `apply_guardrails` em `src/{nome}/agent/nodes.py` executa
    essas regras via LLM antes de cada `send_message`.
    '''))

    # ── product-specs/transferencias.md ──────────────────────────────────────
    transferencias = cfg.get('casos_transferencia', [])
    if transferencias:
        trans_block = '\n'.join(f'- {t}' for t in transferencias)
        (docs / 'product-specs' / 'transferencias.md').write_text(dedent(f'''\
        # Casos de Transferência para Humano — {nome}

        Quando qualquer um dos casos abaixo ocorrer, o agente para de responder
        e notifica o operador humano via WhatsApp.

        {trans_block}

        ## Como funciona no código
        O nó `classify_intent` detecta esses casos e retorna intent `TRANSFERENCIA`.
        O nó `handle_transferencia` envia notificação e define `stage = "human_takeover"`.
        '''))

    # ── product-specs/fluxo-crm.md ────────────────────────────────────────────
    fluxo_crm = cfg.get('fluxo_crm', [])
    if fluxo_crm:
        crm_rows = '\n'.join(f'| {f["etapa_conversa"]} | {f["stage_crm"]} | {f["acao"]} |' for f in fluxo_crm)
        (docs / 'product-specs' / 'fluxo-crm.md').write_text(dedent(f'''\
        # Fluxo CRM — {nome}

        Mapeamento de etapas da conversa para stages no CRM.
        O agente executa a ação automaticamente ao detectar cada etapa.

        | Etapa da Conversa | Stage CRM | Ação |
        |------------------|-----------|------|
        {crm_rows}

        ## Como funciona no código
        `src/{nome}/services/crm.py` — função `sync_crm_stage(phone, intent)`
        é chamada após cada classificação de intent bem-sucedida.
        '''))

    # ── product-specs/follow-up.md ────────────────────────────────────────────
    follow_up = cfg.get('follow_up', {})
    if follow_up.get('ativo'):
        (docs / 'product-specs' / 'follow-up.md').write_text(dedent(f'''\
        # Follow-up Automático — {nome}

        **Ativo:** Sim
        **Tempo de espera:** {follow_up.get("minutos", 60)} minutos
        **Máximo de tentativas:** {follow_up.get("max_tentativas", 2)}

        ## Mensagem
        {follow_up.get("mensagem", "")}

        ## Regras
        - Só envia se conversa ainda estiver aberta (não fechada, não transferida)
        - Só dentro da janela de 24h do WhatsApp (sem custo extra)
        - Para de enviar após {follow_up.get("max_tentativas", 2)} tentativas sem resposta
        - Não envia se lead já foi para agendamento/fechamento

        ## Implementação
        Job agendado em `src/{nome}/services/followup.py` consultando
        Redis para conversas abertas sem atividade no período configurado.
        '''))

    (docs / 'product-specs' / 'index.md').write_text(dedent(f'''\
    # Índice — Product Specs

    | Documento | O que contém |
    |-----------|-------------|
    | [fluxo-atendimento.md](fluxo-atendimento.md) | Etapas e transições do atendimento |
    | [guardrails.md](guardrails.md) | Regras de segurança verificadas em todo envio |
    {"| [transferencias.md](transferencias.md) | Quando escalar para humano |" if transferencias else ""}
    {"| [fluxo-crm.md](fluxo-crm.md) | Mapeamento conversa → CRM |" if fluxo_crm else ""}
    {"| [follow-up.md](follow-up.md) | Follow-up automático |" if follow_up.get("ativo") else ""}
    '''))

    # ── exec-plans/ ───────────────────────────────────────────────────────────
    (docs / 'exec-plans' / 'active').mkdir(parents=True, exist_ok=True)
    (docs / 'exec-plans' / 'completed').mkdir(parents=True, exist_ok=True)
    (docs / 'exec-plans' / 'active' / '001-setup-inicial.md').write_text(dedent(f'''\
    # 001 — Setup Inicial

    **Status:** Em andamento
    **Objetivo:** Colocar o agente {nome} em produção

    ## Checklist

    - [ ] Preencher `.env` com credenciais reais
    - [ ] Configurar webhook no Meta Business
    - [ ] Testar fluxo completo em ambiente de staging
    - [ ] Configurar Redis e PostgreSQL em produção
    - [ ] Deploy via `docker-compose up -d`
    - [ ] Monitorar primeiros 48h de atendimento
    - [ ] Ajustar prompts com base nos primeiros atendimentos reais

    ## Critério de conclusão
    Agente atende 10 leads reais sem intervenção humana com avaliação positiva.
    '''))

    (docs / 'exec-plans' / 'tech-debt-tracker.md').write_text(dedent(f'''\
    # Tech Debt Tracker — {nome}

    | Item | Prioridade | Criado em |
    |------|-----------|-----------|
    | Adicionar testes de integração para cada nó do grafo | Média | setup |
    | Implementar retry com backoff para chamadas à Meta API | Alta | setup |
    | Dashboard de métricas de conversas | Baixa | setup |
    '''))

    # ── references/ ───────────────────────────────────────────────────────────
    (docs / 'references').mkdir(parents=True, exist_ok=True)
    apis_ref = '\n\n'.join(
        f'## {a["nome"]}\nURL: ${{{a["url_env"]}}}\nEndpoints: {", ".join(e["nome"] for e in a.get("endpoints", []))}'
        for a in apis
    ) if apis else '(sem APIs externas configuradas)'

    (docs / 'references' / 'apis-externas.md').write_text(dedent(f'''\
    # APIs Externas — Referência

    {apis_ref}
    '''))

    (docs / 'references' / 'whatsapp-api.md').write_text(dedent('''\
    # Meta Business API — Referência Rápida

    ## Enviar mensagem de texto
    POST https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages
    Authorization: Bearer {WHATSAPP_ACCESS_TOKEN}
    Body: {"messaging_product":"whatsapp","to":"{phone}","type":"text","text":{"body":"..."}}

    ## Webhook verification
    GET /webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...

    ## Tipos de mensagem suportados
    - text, image, document, audio, video, location, template
    '''))

    # ── DESIGN.md e FRONTEND.md (se aplicável) ────────────────────────────────
    (docs / 'DESIGN.md').write_text(dedent(f'''\
    # Design System — {nome}

    ## Voz e Tom
    {cfg.get("prompt_personalidade", "").split(chr(10))[0]}

    ## Princípios de mensagem
    - Máximo 3 parágrafos por mensagem
    - Emojis com moderação (1-2 por mensagem)
    - Sempre terminar com uma pergunta ou CTA claro
    - Nunca enviar blocos de texto > 300 palavras
    '''))

    (docs / 'PLANS.md').write_text(dedent(f'''\
    # Planos Ativos — {nome}

    Ver [exec-plans/active/](exec-plans/active/) para planos detalhados.

    ## Resumo
    | Plano | Status |
    |-------|--------|
    | [001-setup-inicial](exec-plans/active/001-setup-inicial.md) | Em andamento |
    '''))

    print(f"   ✓ docs/ (design-docs, product-specs, exec-plans, references)")


# ─── Wizard interativo ────────────────────────────────────────────────────────

def ask(prompt: str, default: str = '') -> str:
    suffix = f' [{default}]' if default else ''
    try:
        resp = input(f'{prompt}{suffix}: ').strip()
        return resp or default
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

def ask_multiline(prompt: str) -> str:
    print(f'{prompt} (termine com uma linha vazia):')
    lines = []
    try:
        while True:
            line = input('  ')
            if not line and lines:
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        print()
    return '\n'.join(lines)

def ask_list(prompt: str) -> list[str]:
    print(f'{prompt} (uma por linha, vazio para terminar):')
    items = []
    try:
        while True:
            item = input('  → ').strip()
            if not item:
                break
            items.append(item)
    except (EOFError, KeyboardInterrupt):
        print()
    return items

def cmd_wizard(args):
    """Modo interativo — o factory te pergunta tudo e gera o agente."""
    print('\n' + '='*60)
    print('  AGENTE FACTORY — Modo Wizard')
    print('  Vou te fazer perguntas. No final, gero tudo.')
    print('='*60 + '\n')

    cfg = {}

    # ── Identidade ───────────────────────────────────────────────────────────
    print('── 1. IDENTIDADE ──────────────────────────────────────')
    cfg['nome'] = slugify(ask('Nome do agente (ex: clinica_bella, pet_shop_rex)'))
    cfg['cliente'] = ask('Nome do cliente/empresa (ex: Clínica Bella)')
    cfg['descricao'] = ask('Uma linha descrevendo o que o agente faz')

    # ── Personalidade ────────────────────────────────────────────────────────
    print('\n── 2. PERSONALIDADE ───────────────────────────────────')
    print('Descreva quem é o agente: nome, tom de voz, o que ele faz,')
    print('o que NÃO faz. Seja específico — isso vira o system prompt.')
    cfg['prompt_personalidade'] = ask_multiline('Personalidade')

    # ── Etapas ───────────────────────────────────────────────────────────────
    print('\n── 3. ETAPAS DE ATENDIMENTO ───────────────────────────')
    print('Quais são as situações que o agente vai encontrar?')
    print('Ex: primeiro contato, dúvida sobre produto, objeção de preço,')
    print('pronto para comprar, quer cancelar, etc.')
    print()
    etapas = []
    i = 1
    while True:
        print(f'Etapa {i} (vazio para terminar):')
        label = ask('  Nome da etapa (ex: Primeiro Contato)')
        if not label:
            break
        intent = slugify(label).upper()
        descricao = ask(f'  O que acontece nessa etapa', f'Lead em etapa de {label}')
        resposta = ask(f'  Mensagem base do agente nessa etapa')
        etapas.append({
            'intent': intent,
            'label': label,
            'descricao': descricao,
            'resposta_padrao': resposta or f'...',
        })
        i += 1

    if not etapas:
        # etapas padrão mínimas
        etapas = [
            {'intent': 'INTERESSE_INICIAL', 'label': 'Primeiro Contato', 'descricao': 'Lead entrou em contato pela primeira vez', 'resposta_padrao': 'Olá! Como posso te ajudar?'},
            {'intent': 'FECHAMENTO', 'label': 'Fechamento', 'descricao': 'Lead quer fechar', 'resposta_padrao': 'Ótimo! Vamos finalizar...'},
        ]
        print('  (usando etapas padrão)')
    cfg['etapas'] = etapas

    # ── APIs ─────────────────────────────────────────────────────────────────
    print('\n── 4. APIS EXTERNAS ───────────────────────────────────')
    print('O agente precisa consultar algum sistema externo?')
    print('Ex: sistema de agendamento, catálogo de produtos, CRM, ERP...')
    print()
    apis = []
    j = 1
    while True:
        nome_api = ask(f'API {j} — nome (vazio para pular)')
        if not nome_api:
            break
        descricao_api = ask(f'  O que essa API faz')
        url_env = ask(f'  Nome da variável de ambiente com a URL', f'{nome_api.upper()}_API_URL')
        auth_env = ask(f'  Nome da variável de ambiente com a chave', f'{nome_api.upper()}_API_KEY')
        print(f'  Endpoints dessa API (vazio para terminar):')
        endpoints = []
        while True:
            ep_nome = ask('    Nome do endpoint (ex: verificar_disponibilidade)')
            if not ep_nome:
                break
            ep_metodo = ask('    Método HTTP', 'GET').upper()
            ep_path = ask('    Path (ex: /slots)', f'/{ep_nome}')
            ep_desc = ask('    Descrição', ep_nome.replace('_', ' '))
            endpoints.append({'nome': ep_nome, 'metodo': ep_metodo, 'path': ep_path, 'descricao': ep_desc})
        apis.append({'nome': slugify(nome_api), 'descricao': descricao_api, 'url_env': url_env, 'auth_env': auth_env, 'endpoints': endpoints})
        j += 1
    cfg['apis'] = apis

    # ── Estrutura do prompt ──────────────────────────────────────────────────
    print('\n── 5. ESTRUTURA DO PROMPT ─────────────────────────────')
    print('Tem algum template/estrutura que o prompt deve seguir?')
    print('Ex: "você receberá o histórico assim: ...", formato de resposta,')
    print('estrutura de etapas numeradas, etc.')
    print('(pode colar o template aqui, ou deixar vazio para usar padrão)')
    cfg['estrutura_prompt'] = ask_multiline('Estrutura do prompt (opcional)')

    # ── Casos de transferência ───────────────────────────────────────────────
    print('\n── 6. CASOS DE TRANSFERÊNCIA ──────────────────────────')
    print('Quando o agente deve parar e passar para um humano?')
    print('Ex: cliente muito nervoso, pedido de reembolso, problema técnico')
    transferencias = ask_list('Casos de transferência para humano')
    if not transferencias:
        transferencias = [
            'Cliente solicitar falar com humano explicitamente',
            'Reclamação grave ou ameaça de processo',
            'Pergunta fora do escopo após 2 tentativas de redirecionamento',
        ]
    cfg['casos_transferencia'] = transferencias

    # ── Fluxo CRM ────────────────────────────────────────────────────────────
    print('\n── 7. FLUXO CRM ───────────────────────────────────────')
    print('Como o agente deve mover o lead no CRM conforme a conversa avança?')
    print('Mapeie etapa da conversa → stage do CRM')
    print('Ex: "Primeiro Contato → Leads Novos", "Agendou → Agendados"')
    fluxo_crm = []
    k = 1
    while True:
        etapa_conv = ask(f'  Etapa {k} da conversa (vazio para terminar)')
        if not etapa_conv:
            break
        stage_crm = ask(f'  Stage CRM correspondente')
        acao = ask(f'  O que fazer nesse momento', 'mover lead para este stage')
        fluxo_crm.append({
            'etapa_conversa': etapa_conv,
            'stage_crm': stage_crm,
            'acao': acao,
        })
        k += 1
    if fluxo_crm:
        cfg['fluxo_crm'] = fluxo_crm

    # ── Follow-up ────────────────────────────────────────────────────────────
    print('\n── 8. FOLLOW-UP ───────────────────────────────────────')
    print('O agente deve mandar mensagem se o lead sumir?')
    ativo = ask('Ativar follow-up automático? (s/n)', 's')
    if ativo.lower() in ('s', 'sim', 'y', 'yes'):
        tempo = ask('Depois de quantos minutos sem resposta enviar?', '60')
        msg_followup = ask_multiline('Mensagem de follow-up (pode usar {nome} para o nome do lead)')
        cfg['follow_up'] = {
            'ativo': True,
            'minutos': int(tempo) if tempo.isdigit() else 60,
            'mensagem': msg_followup or 'Oi {nome}, tudo bem? Ficou com alguma dúvida? 😊',
            'max_tentativas': int(ask('Máximo de tentativas', '2')),
        }
    else:
        cfg['follow_up'] = {'ativo': False}

    # ── Regras ───────────────────────────────────────────────────────────────
    print('\n── 9. REGRAS (GUARDRAILS) ─────────────────────────────')
    print('O que o agente NUNCA pode fazer ou dizer?')
    regras = ask_list('Regras')
    if not regras:
        regras = ['Nunca prometer resultados garantidos', 'Nunca compartilhar dados de outros clientes']
    cfg['regras'] = regras

    # ── Extras ───────────────────────────────────────────────────────────────
    print('\n── 10. EXTRAS ─────────────────────────────────────────')
    cfg['llm_model'] = ask('Modelo LLM', 'gpt-4o-mini')
    notif_wp = ask('WhatsApp para notificar ao fechar (ex: 5511999999999, vazio para não notificar)')
    if notif_wp:
        cfg['notificacao_fechamento'] = {'ativo': True, 'whatsapp': notif_wp}

    # ── GitHub ───────────────────────────────────────────────────────────────
    print('\n── 11. GITHUB (OPCIONAL) ──────────────────────────────')
    print('Posso criar o repositório no GitHub e fazer o primeiro push agora.')
    print('Você precisará do GitHub CLI (gh) autenticado.')
    push_github = ask('Criar repositório no GitHub? (s/n)', 'n')
    github_owner = None
    if push_github.lower() in ('s', 'sim', 'y', 'yes'):
        github_owner = ask('Usuário ou organização no GitHub (ex: AbelFluxIA)')

    # ── Confirmar e gerar ────────────────────────────────────────────────────
    print('\n' + '='*60)
    print(f'  Agente: {cfg["nome"]}')
    print(f'  Cliente: {cfg["cliente"]}')
    print(f'  Etapas: {len(cfg["etapas"])}')
    print(f'  APIs: {len(cfg["apis"])}')
    print(f'  Transferências: {len(cfg["casos_transferencia"])}')
    print(f'  Fluxo CRM: {len(cfg.get("fluxo_crm", []))} mapeamentos')
    print(f'  Follow-up: {"ativo" if cfg.get("follow_up", {}).get("ativo") else "desativado"}')
    print(f'  Regras: {len(cfg["regras"])}')
    if github_owner:
        print(f'  GitHub: {github_owner}/{cfg["nome"].replace("_", "-")} (privado)')
    print('='*60)
    confirma = ask('\nGerar o projeto? (s/n)', 's')
    if confirma.lower() not in ('s', 'sim', 'y', 'yes', ''):
        print('Cancelado.')
        return

    # Salva o config para referência futura
    config_file = Path(f'{cfg["nome"]}.yaml')
    with open(config_file, 'w') as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    print(f'\n✓ Config salva em: {config_file}')

    # Gera o projeto
    class FakeArgs:
        config = str(config_file)
        output = None
        github = github_owner
    cmd_create(FakeArgs())


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Agente Factory — cria agentes WhatsApp IA')
    sub = parser.add_subparsers(dest='command')

    sub.add_parser('wizard', help='Modo interativo — te pergunta tudo e gera o agente')

    init_p = sub.add_parser('init', help='Cria um config.yaml de exemplo')
    init_p.add_argument('--output', '-o', help='Nome do arquivo de saída (default: config.yaml)')
    init_p.add_argument('--force', '-f', action='store_true')

    create_p = sub.add_parser('create', help='Gera o projeto a partir de um config.yaml existente')
    create_p.add_argument('--config', '-c', required=True, help='Arquivo config.yaml')
    create_p.add_argument('--output', '-o', help='Diretório de saída (default: nome do agente)')
    create_p.add_argument('--github', '-g', help='Usuário/org GitHub para criar repo e fazer push (ex: AbelFluxIA)')

    args = parser.parse_args()

    if args.command == 'wizard':
        cmd_wizard(args)
    elif args.command == 'init':
        cmd_init(args)
    elif args.command == 'create':
        cmd_create(args)
    else:
        parser.print_help()
        print('\nDica: comece com "python3 factory.py wizard" para modo interativo.')


if __name__ == '__main__':
    main()
