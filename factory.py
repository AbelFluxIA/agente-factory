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

    return dedent(f'''\
    """Prompts e personalidade do agente {nome}."""

    SYSTEM_PROMPT = """
    {cfg["prompt_personalidade"].strip()}
    """

    INTENT_CLASSIFIER_PROMPT = """
    Você é um classificador de intenção. Analise a mensagem do usuário e classifique em uma das categorias:
    {intents_str}, FORA_ESCOPO

    Retorne APENAS o nome da categoria, sem explicação.
    """

    GUARDRAILS_PROMPT = """
    Verifique se a resposta abaixo viola alguma das regras. Se violar, corrija ou recuse.

    REGRAS:
    {regras_str}

    Resposta a verificar: {{response}}

    Se OK: retorne a resposta original.
    Se violar: corrija ou responda "Desculpe, não posso ajudar com isso."
    """

    # Respostas padrão por intenção
    DEFAULT_RESPONSES = {{
    {chr(10).join(f'    "{e["intent"]}": """{e["resposta_padrao"]}""",' for e in etapas)}
    }}
    ''')

def generate_state(cfg: dict) -> str:
    return dedent(f'''\
    """Estado da conversa do agente {cfg["nome"]}."""
    from typing import TypedDict, Annotated, List, Optional
    import operator

    class ConversationState(TypedDict):
        messages: Annotated[List[dict], operator.add]
        phone: str
        user_name: Optional[str]
        current_intent: Optional[str]
        intent_history: List[str]
        stage: str  # nurturing | closing | closed
        context: dict  # dados coletados durante o atendimento (ex: procedimento escolhido)
        response: Optional[str]
        should_send: bool
        error: Optional[str]
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
    from langchain_openai import ChatOpenAI
    from .state import ConversationState
    from ..personality.prompts import SYSTEM_PROMPT, INTENT_CLASSIFIER_PROMPT, GUARDRAILS_PROMPT, DEFAULT_RESPONSES
    from ..services.apis import {", ".join(slugify(a["nome"]) + "_client" for a in apis) if apis else "# nenhuma API configurada"}

    llm = ChatOpenAI(model="{cfg.get("llm_model", "gpt-4o-mini")}")


    async def validate_message(state: ConversationState) -> ConversationState:
        """Filtra mensagens inválidas, duplicadas ou de bots."""
        if not state["messages"] or not state["messages"][-1].get("content", "").strip():
            return {{**state, "should_send": False}}
        return state


    async def load_context(state: ConversationState) -> ConversationState:
        """Carrega contexto da sessão (Redis) e histórico (PostgreSQL)."""
        # Implementado em memory/redis_memory.py
        return state


    async def classify_intent(state: ConversationState) -> ConversationState:
        """Classifica a intenção da última mensagem."""
        last_msg = state["messages"][-1]["content"]
        response = await llm.ainvoke(
            INTENT_CLASSIFIER_PROMPT + f"\\nMensagem: {{last_msg}}"
        )
        intent = response.content.strip()
        return {{
            **state,
            "current_intent": intent,
            "intent_history": state.get("intent_history", []) + [intent],
        }}


    {intent_blocks}

    async def handle_fora_escopo(state: ConversationState) -> ConversationState:
        """Redireciona tópicos fora do escopo."""
        return {{**state, "response": "Hmm, esse assunto foge um pouco do meu escopo. Posso te ajudar com outra coisa?"}}


    async def generate_response(state: ConversationState) -> ConversationState:
        """Gera resposta humanizada com LLM usando a personalidade do agente."""
        history = "\\n".join(f'{{m["role"]}}: {{m["content"]}}' for m in state["messages"][-10:])
        base = state.get("response", "")
        prompt = f"{{SYSTEM_PROMPT}}\\n\\nHistórico:\\n{{history}}\\n\\nBase da resposta: {{base}}\\n\\nResponda de forma natural e humanizada:"
        response = await llm.ainvoke(prompt)
        return {{**state, "response": response.content}}


    async def apply_guardrails(state: ConversationState) -> ConversationState:
        """Verifica guardrails antes de enviar."""
        check = await llm.ainvoke(GUARDRAILS_PROMPT.format(response=state["response"]))
        return {{**state, "response": check.content, "should_send": True}}


    async def send_message(state: ConversationState) -> ConversationState:
        """Envia mensagem via WhatsApp."""
        from ..services.whatsapp import send_whatsapp_message
        if state.get("should_send") and state.get("response"):
            await send_whatsapp_message(state["phone"], state["response"])
        return state


    async def persist_history(state: ConversationState) -> ConversationState:
        """Persiste histórico no Redis e PostgreSQL."""
        # Implementado em memory/
        return state


    # Ferramentas disponíveis via APIs:
    {tools_block if tools_block else "    # Nenhuma API externa configurada"}
    ''')

def generate_graph(cfg: dict) -> str:
    etapas = cfg.get('etapas', [])
    intents = [e['intent'] for e in etapas]
    node_imports = ', '.join([
        'validate_message', 'load_context', 'classify_intent',
        'generate_response', 'apply_guardrails', 'send_message', 'persist_history',
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
        intent = state.get("current_intent", "FORA_ESCOPO")
        routes = {{
            {routing_cases}
            "FORA_ESCOPO": "handle_fora_escopo",
        }}
        return routes.get(intent, "handle_fora_escopo")


    def build_graph():
        graph = StateGraph(ConversationState)

        # Nós fixos do pipeline
        graph.add_node("validate_message", validate_message)
        graph.add_node("load_context", load_context)
        graph.add_node("classify_intent", classify_intent)
        graph.add_node("generate_response", generate_response)
        graph.add_node("apply_guardrails", apply_guardrails)
        graph.add_node("send_message", send_message)
        graph.add_node("persist_history", persist_history)
        graph.add_node("handle_fora_escopo", handle_fora_escopo)

        # Nós de intenção (gerados a partir da config)
    {node_registrations}

        # Fluxo principal
        graph.set_entry_point("validate_message")
        graph.add_edge("validate_message", "load_context")
        graph.add_edge("load_context", "classify_intent")
        graph.add_conditional_edges("classify_intent", route_by_intent)

        # Cada intenção → generate_response
    {edges_from_routing}
        graph.add_edge("handle_fora_escopo", "generate_response")

        graph.add_edge("generate_response", "apply_guardrails")
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
    return dedent(f'''\
    """Webhook FastAPI — recebe mensagens do WhatsApp."""
    import hmac, hashlib, os
    from fastapi import APIRouter, Request, HTTPException
    from ..agent.graph import agent
    from ..agent.state import ConversationState
    from ..services.whatsapp import parse_incoming

    router = APIRouter(prefix="/webhook")


    @router.get("/whatsapp")
    async def verify(hub_mode: str, hub_verify_token: str, hub_challenge: str):
        if hub_mode == "subscribe" and hub_verify_token == os.environ["WHATSAPP_VERIFY_TOKEN"]:
            return int(hub_challenge)
        raise HTTPException(status_code=403)


    @router.post("/whatsapp")
    async def receive(request: Request):
        payload = await request.body()
        sig = request.headers.get("x-hub-signature-256", "")
        secret = os.environ.get("WHATSAPP_APP_SECRET", "")
        if secret:
            expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise HTTPException(status_code=403)

        msg = parse_incoming(await request.json())
        if not msg:
            return {{"status": "ignored"}}

        initial_state = ConversationState(
            messages=[{{"role": "user", "content": msg["text"]}}],
            phone=msg["phone"],
            user_name=msg.get("name"),
            current_intent=None,
            intent_history=[],
            stage="nurturing",
            context={{}},
            response=None,
            should_send=False,
            error=None,
        )

        await agent.ainvoke(initial_state)
        return {{"status": "processed"}}
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

    print(f"\n✅ Agente '{nome}' gerado em {output_dir}/")
    print(f"\nPróximos passos:")
    print(f"  1. cd {output_dir}")
    print(f"  2. cp .env.example .env && edite com suas chaves")
    print(f"  3. uv sync")
    print(f"  4. uv run uvicorn src.{nome}.main:app --reload")


def _copy_base_services(output_dir: Path, nome: str):
    """Copia serviços base (whatsapp.py, memory/) da estrutura padrão."""
    whatsapp_content = dedent('''\
    """Cliente Meta Business API."""
    import os, httpx

    BASE_URL = "https://graph.facebook.com/v19.0"

    async def send_whatsapp_message(phone: str, text: str) -> dict:
        token = os.environ["WHATSAPP_ACCESS_TOKEN"]
        phone_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BASE_URL}/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={"messaging_product": "whatsapp", "to": phone, "type": "text", "text": {"body": text}},
            )
            resp.raise_for_status()
            return resp.json()

    def parse_incoming(body: dict) -> dict | None:
        try:
            entry = body["entry"][0]["changes"][0]["value"]
            msg = entry["messages"][0]
            contact = entry["contacts"][0]
            return {
                "phone": msg["from"],
                "name": contact["profile"]["name"],
                "text": msg.get("text", {}).get("body", ""),
                "message_id": msg["id"],
            }
        except (KeyError, IndexError):
            return None
    ''')

    redis_content = dedent('''\
    """Memória de sessão via Redis."""
    import json, os
    from redis.asyncio import from_url

    redis = None

    async def get_redis():
        global redis
        if redis is None:
            redis = await from_url(os.environ["REDIS_URL"], decode_responses=True)
        return redis

    async def load_session(phone: str) -> dict:
        r = await get_redis()
        data = await r.get(f"session:{phone}")
        return json.loads(data) if data else {}

    async def save_session(phone: str, data: dict, ttl: int = 86400):
        r = await get_redis()
        await r.setex(f"session:{phone}", ttl, json.dumps(data))
    ''')

    (output_dir / f'src/{nome}/services/whatsapp.py').write_text(whatsapp_content)
    (output_dir / f'src/{nome}/memory/redis_memory.py').write_text(redis_content)
    print(f"   ✓ src/{nome}/services/whatsapp.py")
    print(f"   ✓ src/{nome}/memory/redis_memory.py")


# ─── Entry point ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Agente Factory — cria agentes WhatsApp IA')
    sub = parser.add_subparsers(dest='command')

    init_p = sub.add_parser('init', help='Cria um config.yaml de exemplo')
    init_p.add_argument('--output', '-o', help='Nome do arquivo de saída (default: config.yaml)')
    init_p.add_argument('--force', '-f', action='store_true')

    create_p = sub.add_parser('create', help='Gera o projeto do agente')
    create_p.add_argument('--config', '-c', required=True, help='Arquivo config.yaml')
    create_p.add_argument('--output', '-o', help='Diretório de saída (default: nome do agente)')

    args = parser.parse_args()

    if args.command == 'init':
        cmd_init(args)
    elif args.command == 'create':
        cmd_create(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
