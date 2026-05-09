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
# Configuração do Agente — Agente Factory
# ─────────────────────────────────────────────────────────────────────────────

nome: clinica_bella
descricao: "Agente de vendas para clínica de estética"
cliente: "Clínica Bella"

# ─── Personalidade ───────────────────────────────────────────────────────────
# Quem é o agente, tom de voz, o que faz e o que NÃO faz
prompt_personalidade: |
  Você é Sofia, consultora da Clínica Bella.
  Tom caloroso, próximo e profissional — como uma amiga especialista.
  Você ajuda clientes a conhecer e agendar procedimentos estéticos.
  Nunca prometa resultados garantidos.
  Nunca fale mal de concorrentes.
  Nunca discuta política, religião ou saúde geral.

# ─── Etapas de atendimento ───────────────────────────────────────────────────
# passo: número sequencial (auto-numerado se omitido)
# regras: instruções em linguagem natural para o LLM neste passo
etapas:
  - passo: 1
    intent: CAPTURA_NOME
    label: "Capturar nome"
    descricao: "Saudar e capturar o primeiro nome do lead"
    regras: |
      SE é o primeiro contato (histórico vazio):
        Envie EXATAMENTE: "Olá! Sou a Sofia da Clínica Bella. Me conta seu nome pra gente continuar?"
        action: converse, next_step: 1
      SE lead informou um nome:
        Extraia em extracted_nome.
        action: converse, next_step: 2
        Resposta: "{nome}, que bom ter você aqui! É sua primeira vez na Clínica Bella?"
    resposta_padrao: "Olá! Sou a Sofia da Clínica Bella. Me conta seu nome pra gente continuar?"

  - passo: 2
    intent: QUALIFICACAO
    label: "Qualificar interesse"
    descricao: "Entender o que o lead busca"
    regras: |
      SE lead é cliente existente: direcione para atendimento especializado. action: transferir
      SE lead mencionou procedimento: extraia em extracted_interesse, avance passo 3.
      SE vago: "Você tá buscando algo mais para rosto, corpo ou bem-estar?"
    resposta_padrao: "É sua primeira vez conosco? Me conta o que você tá buscando."

  - passo: 3
    intent: APRESENTACAO
    label: "Apresentar solução"
    descricao: "Conectar a dor do lead ao procedimento e apresentar o atendimento"
    regras: |
      Valide brevemente o interesse do lead.
      Apresente o procedimento com foco no benefício, não na técnica.
      Termine com: "Faz sentido pra você?"
      action: converse, next_step: 4
    resposta_padrao: "Olha, baseado no que você me contou, acho que temos exatamente o que você precisa..."

  - passo: 4
    intent: FECHAMENTO
    label: "Fechamento e agendamento"
    descricao: "Conduzir para o agendamento ou pagamento"
    regras: |
      SE lead disse SIM: apresente as opções de pagamento/agendamento.
      SE lead perguntou preço: informe valores e formas de pagamento.
      SE lead mencionou forma de pagamento: extraia em payment_method, avance passo 5.
      SE objeção no limite: ofereça alternativa mais acessível ou encerre graciosamente.
    resposta_padrao: "Como você prefere prosseguir? Posso te mostrar as opções de agendamento."

  - passo: 5
    intent: CONFIRMACAO
    label: "Confirmação final"
    descricao: "Confirmar agendamento e notificar operador"
    regras: |
      Confirme os dados do agendamento.
      Informe próximos passos (confirmação, o que trazer, etc.).
      Defina notify_operator: true para alertar o time.
      action: converse, next_step: 5
    resposta_padrao: "Perfeito! Tudo confirmado. Em breve você vai receber a confirmação."

# ─── Dados a extrair do lead ─────────────────────────────────────────────────
dados_extrair:
  - campo: extracted_nome
    descricao: "Primeiro nome do lead"
  - campo: extracted_interesse
    descricao: "Procedimento ou área de interesse do lead"

# ─── Formas de pagamento ─────────────────────────────────────────────────────
formas_pagamento:
  - pix
  - cartao
  - dinheiro

# ─── Limite de objeções ──────────────────────────────────────────────────────
max_objecoes: 2

# ─── Vocabulário e humanização ───────────────────────────────────────────────
vocabulario:
  substituicoes:
    problema: desafio
    para: pra
    ajuda: apoio
  conectores:
    - "olha"
    - "sabe?"
    - "então"
    - "é que"

# ─── APIs externas ────────────────────────────────────────────────────────────
apis:
  - nome: agenda
    descricao: "Sistema de agendamento da clínica"
    url_env: AGENDA_API_URL
    auth_env: AGENDA_API_KEY
    endpoints:
      - nome: verificar_disponibilidade
        metodo: GET
        path: /slots
        descricao: "Verifica horários disponíveis"
      - nome: criar_agendamento
        metodo: POST
        path: /appointments
        descricao: "Cria um novo agendamento"

# ─── Regras (guardrails) ──────────────────────────────────────────────────────
regras:
  - "Nunca prometer resultado garantido de procedimento estético"
  - "Nunca compartilhar dados de outros clientes"
  - "Nunca mencionar concorrentes pelo nome"
  - "Nunca revelar que é uma IA"

# ─── Configurações opcionais ──────────────────────────────────────────────────
llm_model: "gpt-4o-mini"
notificacao_fechamento:
  ativo: true
  whatsapp: "5511999999999"
"""

# ─── Gerador de arquivos ─────────────────────────────────────────────────────

def slugify(name: str) -> str:
    return name.lower().replace(' ', '_').replace('-', '_')

def generate_prompts(cfg: dict) -> str:
    nome = cfg['nome']
    etapas = cfg.get('etapas', [])
    regras = cfg.get('regras', [])
    dados_extrair = cfg.get('dados_extrair', [])
    formas_pagamento = cfg.get('formas_pagamento', [])
    max_objecoes = cfg.get('max_objecoes', 2)
    vocabulario = cfg.get('vocabulario', {})

    # Auto-numerar etapas se passo não definido
    for i, e in enumerate(etapas):
        if 'passo' not in e:
            e['passo'] = i + 1

    regras_str = '\n'.join(f'- {r}' for r in regras)

    # STEP_RULES dict entries
    step_entries = []
    for e in etapas:
        passo = e['passo']
        label = e['label']
        descricao = e['descricao']
        regras_passo = e.get('regras', f'Lide com esta etapa conforme o contexto: {descricao}').strip()
        # indent the rules block
        regras_indented = '\n'.join(f'    {line}' for line in regras_passo.splitlines())
        step_entries.append(
            f'    {passo}: """\nPASSO {passo} — {label}\n{descricao}\n\n{regras_indented}\n""",'
        )
    step_rules_block = '\n'.join(step_entries)

    # Campos extraídos
    campos = [d['campo'] for d in dados_extrair]
    campos_repr = repr(campos)

    # Formas de pagamento
    formas_repr = repr(formas_pagamento)

    # JSON schema para BRAIN_DECISION_PROMPT
    dados_json_fields = '\n'.join(f'  "{d["campo"]}": "",' for d in dados_extrair)

    # Vocabulário para humanizador
    subs = vocabulario.get('substituicoes', {})
    vocab_str = ', '.join(f'"{k}" -> "{v}"' for k, v in subs.items()) if subs else 'nenhuma configurada'
    conectores = vocabulario.get('conectores', ['olha', 'sabe', 'então', 'é que', 'pensa comigo'])
    conectores_str = ', '.join(f'"{c}"' for c in conectores)

    return dedent(f'''\
"""Prompts e personalidade do agente {nome}."""

SYSTEM_PROMPT = """{cfg["prompt_personalidade"].strip()}"""

# Regras específicas por passo — geradas do YAML
STEP_RULES: dict[int, str] = {{
{step_rules_block}
}}

DADOS_EXTRAIR: list[str] = {campos_repr}

FORMAS_PAGAMENTO: list[str] = {formas_repr}

MAX_OBJECOES: int = {max_objecoes}

BRAIN_DECISION_PROMPT = """
Você é um agente de atendimento via WhatsApp. Analise o contexto e responda em JSON.

╔══════════════════════════════════════════════════════════════╗
║  CAMADA 1 — LEITURA DO LEAD (avalie ANTES das regras)      ║
╚══════════════════════════════════════════════════════════════╝

A) SINAL DE COMPRA ANTECIPADO
   Lead demonstrou intenção clara de fechar/comprar/agendar?
   → Pule direto para o passo de fechamento

B) ESTADO EMOCIONAL
   Lead está frustrado, empolgado ou confuso?
   → Adapte o tom brevemente antes de prosseguir

C) PERGUNTA TANGENCIAL (dentro do escopo, fora do fluxo)
   → Responda em 1-2 frases e volte ao fluxo normalmente

D) MENSAGEM VAGA OU MUITO CURTA
   → Interprete pelo contexto do passo atual

╔══════════════════════════════════════════════════════════════╗
║  CAMADA 2 — REGRAS DO PASSO ATUAL                          ║
╚══════════════════════════════════════════════════════════════╝

Siga as regras do passo atual fornecidas no contexto dinâmico.

╔══════════════════════════════════════════════════════════════╗
║  FORMATO DE RESPOSTA — JSON OBRIGATÓRIO                    ║
╚══════════════════════════════════════════════════════════════╝

Responda APENAS JSON válido (sem markdown, sem explicações):
{{{{
  "action": "converse",
  "response": "texto da resposta (use ||| para separar em blocos de mensagem)",
  "next_step": 1,
  "next_sub_state": "",
  "increment_objection": false,
  "notify_operator": false,
  "payment_method": "",
{dados_json_fields}
}}}}

REGRAS DO JSON:
- "response": texto completo. Use ||| para enviar como múltiplas mensagens.
- "next_step": só mude quando as regras indicarem avanço claro de passo.
- "increment_objection": true APENAS para recusas/objeções explícitas.
- "notify_operator": true quando lead fechar/confirmar (notifica o dono).
- Campos de extração: preencha SOMENTE quando tiver certeza do valor.
"""

HUMANIZER_SYSTEM_PROMPT = """# SUA FUNÇÃO
Você é um humano real respondendo no WhatsApp. Reescreva a mensagem de forma natural.

# REGRAS
1. PRESERVE O CONTEÚDO — não invente informações além do que está escrito.
2. QUEBRE EM CURTAS — máximo 2-3 frases por bloco. Use ||| para separar blocos.
3. SEM ELOGIOS VAZIOS — nunca "Perfeito!", "Incrível!", "Que ótimo!", "Claro!".
4. PRESERVE PERGUNTAS — se termina com pergunta, preserve-a exatamente.
5. SEM TRAVESSÃO (—) — use ponto final, vírgula ou quebre com |||.
6. EMOJIS — máximo 1 em toda a resposta. Prefira zero.
7. VOCABULÁRIO — substitua naturalmente: {vocab_str}

# COMO HUMANO ESCREVE NO WHATSAPP
- Varia o início de cada bloco. Nunca inicie dois blocos com a mesma palavra.
- Conectores naturais: {conectores_str}
- Às vezes começa com o ponto principal direto, sem prefácio.
- Usa reticências (...) quando há pausa natural de pensamento.

# SAÍDA
Apenas o texto final com ||| onde houver quebras. Sem explicações."""

GUARDRAIL_CHECK_PROMPT = """Verifique se a resposta viola alguma das regras:

REGRAS:
{regras_str}

Resposta a verificar:
{{draft_response}}

Responda APENAS:
- "OK" se não viola nenhuma regra
- "VIOLATION: [motivo específico]" se violar

Marque VIOLATION apenas para violações claras e inequívocas."""
''')

def generate_state(cfg: dict) -> str:
    dados_extrair = cfg.get('dados_extrair', [])
    extracted_fields = '\n'.join(
        f'    {d["campo"]}: str = ""  # {d["descricao"]}'
        for d in dados_extrair
    )
    if extracted_fields:
        extracted_fields = '\n    # Dados extraídos do lead\n' + extracted_fields

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

    # Fluxo numerado por passos
    current_step: int = 1
    sub_state: str = ""
    stage: Stage = "nurturing"
{extracted_fields}

    # Tracking de vendas
    objection_count: int = 0
    payment_method: str = ""

    # Resposta gerada
    draft_response: str = ""
    messages_to_send: list[str] = field(default_factory=list)
    message_delays: list[int] = field(default_factory=list)

    # Flags
    guardrail_triggered: bool = False
    notify_operator: bool = False
    error: Optional[str] = None
''')

def generate_nodes(cfg: dict) -> str:
    apis = cfg.get('apis', [])
    nome = cfg['nome']
    model = cfg.get('llm_model', 'gpt-4o-mini')
    etapas = cfg.get('etapas', [])
    total_steps = len(etapas)
    tools_block = '\n'.join(f'# {a["nome"]}: {a["descricao"]}' for a in apis)

    return dedent(f'''\
"""Nós de processamento do agente {nome}."""
import json
import logging
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from .state import ConversationState
from ..personality.prompts import (
    SYSTEM_PROMPT, BRAIN_DECISION_PROMPT, STEP_RULES,
    DADOS_EXTRAIR, FORMAS_PAGAMENTO, MAX_OBJECOES,
    HUMANIZER_SYSTEM_PROMPT, GUARDRAIL_CHECK_PROMPT,
)

logger = logging.getLogger(__name__)

_llm_brain = ChatOpenAI(model="{model}", temperature=0.6)
_llm_humanizer = ChatOpenAI(model="{model}", temperature=0.8)
_llm_guardrail = ChatOpenAI(model="{model}", temperature=0.0)


def _history_text(state: ConversationState) -> str:
    lines = []
    for m in state.messages[-20:]:
        if isinstance(m, HumanMessage):
            lines.append(f"Lead: {{m.content}}")
        elif isinstance(m, AIMessage):
            lines.append(f"Agente: {{m.content}}")
    return "\\n".join(lines) or "(início da conversa)"


async def main_brain(state: ConversationState) -> ConversationState:
    """Cérebro central: analisa contexto + decide resposta + avança passo."""
    history = _history_text(state)
    last_msg = next(
        (m.content for m in reversed(state.messages) if isinstance(m, HumanMessage)), ""
    )
    step_rules = STEP_RULES.get(state.current_step, "Sem regras específicas. Use bom senso.")

    # Contexto de dados extraídos do lead
    extracted_lines = []
    for campo in DADOS_EXTRAIR:
        val = getattr(state, campo, "") or "(não informado)"
        extracted_lines.append(f"  {{campo}}: {{val}}")
    extracted_ctx = "\\n".join(extracted_lines) or "  (nenhum dado extraído ainda)"

    # Contexto de objeções
    if state.objection_count >= MAX_OBJECOES:
        objecao_ctx = "⚠️ LIMITE DE OBJEÇÕES ATINGIDO: pivot para alternativa ou encerramento."
    elif state.objection_count > 0:
        objecao_ctx = f"Objeções registradas: {{state.objection_count}}/{{MAX_OBJECOES}}"
    else:
        objecao_ctx = ""

    prompt = (
        f"PERSONALIDADE DO AGENTE:\\n{{SYSTEM_PROMPT}}\\n\\n"
        f"INSTRUÇÕES GERAIS:\\n{{BRAIN_DECISION_PROMPT}}\\n\\n"
        f"=== CONTEXTO DO ATENDIMENTO ===\\n"
        f"Passo atual: {{state.current_step}}\\n"
        f"Sub-estado: {{state.sub_state or 'nenhum'}}\\n"
        f"Stage: {{state.stage}}\\n"
        f"{{objecao_ctx}}\\n\\n"
        f"=== DADOS DO LEAD ===\\n{{extracted_ctx}}\\n\\n"
        f"=== REGRAS DO PASSO {{state.current_step}} ===\\n{{step_rules}}\\n\\n"
        f"=== HISTÓRICO DA CONVERSA ===\\n{{history}}\\n\\n"
        f"=== ÚLTIMA MENSAGEM DO LEAD ===\\n{{last_msg}}"
    )

    try:
        resp = await _llm_brain.ainvoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\\n", 1)[1].rsplit("```", 1)[0].strip()
        decision = json.loads(raw)
    except Exception as exc:
        logger.error(f"main_brain parse error: {{exc}}")
        state.draft_response = "Desculpe, tive um probleminha aqui. Pode repetir?"
        return state

    state.draft_response = decision.get("response", "")
    state.current_step = int(decision.get("next_step", state.current_step))
    state.sub_state = decision.get("next_sub_state", "") or ""

    if decision.get("increment_objection"):
        state.objection_count = state.objection_count + 1

    if decision.get("notify_operator"):
        state.notify_operator = True

    pm = decision.get("payment_method", "")
    if pm and pm in FORMAS_PAGAMENTO:
        state.payment_method = pm

    for campo in DADOS_EXTRAIR:
        val = decision.get(campo, "")
        if val:
            setattr(state, campo, val)

    if state.current_step >= {total_steps}:
        state.stage = "closing"

    logger.info({{"step": state.current_step, "action": decision.get("action"), "stage": state.stage}})
    return state


async def humanize_response(state: ConversationState) -> ConversationState:
    """Humanizador: reescreve o rascunho como mensagens curtas e naturais."""
    if not state.draft_response:
        return state

    if "|||" in state.draft_response:
        parts = [p.strip() for p in state.draft_response.split("|||") if p.strip()]
        state.messages_to_send = parts
        state.message_delays = [0] + [3] * (len(parts) - 1)
        return state

    resp = await _llm_humanizer.ainvoke([
        {{"role": "system", "content": HUMANIZER_SYSTEM_PROMPT}},
        {{"role": "user", "content": f"Reescreva naturalmente:\\n\\n{{state.draft_response}}"}},
    ])
    humanized = resp.content.strip()
    parts = [p.strip() for p in humanized.split("|||") if p.strip()]
    if not parts:
        parts = [state.draft_response]

    state.messages_to_send = parts
    state.message_delays = [2] + [3] * (len(parts) - 1)
    return state


async def apply_guardrails(state: ConversationState) -> ConversationState:
    """Verifica violações de regras antes de enviar."""
    if not state.messages_to_send:
        return state
    full_text = " ".join(state.messages_to_send)
    check = await _llm_guardrail.ainvoke(
        GUARDRAIL_CHECK_PROMPT.format(draft_response=full_text)
    )
    if str(check.content).strip().startswith("VIOLATION"):
        state.guardrail_triggered = True
        state.messages_to_send = ["Desculpe, não consigo ajudar com isso agora."]
        state.message_delays = [0]
    return state


async def send_message(state: ConversationState) -> ConversationState:
    """Envia mensagens via WhatsApp com delays."""
    from ..services.whatsapp import send_messages_sequence, notify_operator
    import asyncio
    if state.messages_to_send:
        asyncio.create_task(
            send_messages_sequence(state.phone, state.messages_to_send, state.message_delays)
        )
    if state.notify_operator:
        import os
        lead_info = ", ".join(
            f"{{campo}}={{getattr(state, campo, '')}}" for campo in DADOS_EXTRAIR
        )
        asyncio.create_task(
            notify_operator(
                state.phone,
                f"🔔 Lead fechou/confirmou! {{lead_info}} | Passo {{state.current_step}}",
            )
        )
    return state


async def persist_history(state: ConversationState) -> ConversationState:
    """Persiste mensagem no Redis."""
    from ..memory.redis_memory import redis_memory
    combined = " | ".join(state.messages_to_send)
    if state.messages and isinstance(state.messages[-1], HumanMessage):
        await redis_memory.save_message(state.phone, "user", state.messages[-1].content)
    if combined:
        await redis_memory.save_message(state.phone, "assistant", combined)
    return state


{tools_block if tools_block else "# Nenhuma API externa configurada"}
''')

def generate_graph(cfg: dict) -> str:
    return dedent(f'''\
"""Grafo LangGraph do agente {cfg["nome"]}."""
from langgraph.graph import StateGraph, END
from .state import ConversationState
from .nodes import (
    main_brain, humanize_response, apply_guardrails, send_message, persist_history,
)


def build_graph():
    graph = StateGraph(ConversationState)

    graph.add_node("main_brain", main_brain)
    graph.add_node("humanize_response", humanize_response)
    graph.add_node("apply_guardrails", apply_guardrails)
    graph.add_node("send_message", send_message)
    graph.add_node("persist_history", persist_history)

    graph.set_entry_point("main_brain")
    graph.add_edge("main_brain", "humanize_response")
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

def generate_crm_tools(cfg: dict) -> str:
    nome = cfg['nome']
    return dedent(f'''\
    """
    Ferramentas de CRM que a IA pode chamar autonomamente.
    Mapeia para os endpoints do zynk-webhook.
    """
    import json
    import os
    import httpx
    from langchain_core.tools import tool


    def _headers() -> dict:
        return {{"x-admin-secret": os.environ.get("ZYNK_ADMIN_SECRET", ""), "Content-Type": "application/json"}}

    def _base() -> str:
        return os.environ.get("ZYNK_WEBHOOK_URL", "").rstrip("/")

    def _org() -> str:
        return os.environ.get("ZYNK_ORG_ID", "")


    @tool
    async def listar_estagios_crm() -> str:
        """Lista todas as etapas disponíveis no kanban do CRM."""
        if not _base() or not _org():
            return "CRM não configurado."
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{{_base()}}/crm/stages", params={{"orgId": _org()}}, headers=_headers())
            stages = r.json()
            if not isinstance(stages, list):
                return "Erro ao listar etapas."
            return json.dumps([{{"id": s["id"], "nome": s["name"]}} for s in stages], ensure_ascii=False)


    @tool
    async def buscar_contexto_crm(phone: str) -> str:
        """Busca o contexto completo do lead no CRM: deal, etapa, notas.

        Args:
            phone: Número de telefone do lead
        """
        if not _base() or not _org():
            return "CRM não configurado."
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{{_base()}}/crm/contact/{{phone}}", params={{"orgId": _org()}}, headers=_headers())
            if r.status_code == 404:
                return "Lead ainda não cadastrado no CRM."
            return json.dumps(r.json(), ensure_ascii=False, default=str)


    @tool
    async def mover_lead(deal_id: str, stage_id: str, nome_etapa_destino: str) -> str:
        """Move o lead para uma etapa do kanban.

        Args:
            deal_id: ID do deal no CRM
            stage_id: ID da etapa de destino (use listar_estagios_crm para obter)
            nome_etapa_destino: Nome legível da etapa
        """
        if not _base() or not _org():
            return "CRM não configurado."
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(
                f"{{_base()}}/crm/deal/{{deal_id}}/move",
                json={{"orgId": _org(), "stageId": stage_id, "toStageName": nome_etapa_destino}},
                headers=_headers(),
            )
            return f"Lead movido para '{{nome_etapa_destino}}'." if r.status_code == 200 else f"Erro: {{r.text}}"


    @tool
    async def adicionar_nota_crm(deal_id: str, conteudo: str) -> str:
        """Adiciona uma nota ao deal do lead. Use para objeções, interesses, contexto relevante.

        Args:
            deal_id: ID do deal no CRM
            conteudo: Texto objetivo da nota
        """
        if not _base() or not _org():
            return "CRM não configurado."
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.post(
                f"{{_base()}}/crm/deal/{{deal_id}}/note",
                json={{"orgId": _org(), "content": conteudo, "authorType": "ai"}},
                headers=_headers(),
            )
            return "Nota adicionada." if r.status_code == 200 else f"Erro: {{r.text}}"


    @tool
    async def fechar_deal_crm(deal_id: str, status: str) -> str:
        """Fecha o deal como ganho ('won') ou perdido ('lost').

        Args:
            deal_id: ID do deal no CRM
            status: 'won' ou 'lost'
        """
        if status not in ("won", "lost"):
            return "Status inválido. Use 'won' ou 'lost'."
        if not _base() or not _org():
            return "CRM não configurado."
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.patch(
                f"{{_base()}}/crm/deal/{{deal_id}}",
                json={{"orgId": _org(), "status": status}},
                headers=_headers(),
            )
            label = "ganho" if status == "won" else "perdido"
            return f"Deal marcado como {{label}}." if r.status_code == 200 else f"Erro: {{r.text}}"


    ALL_CRM_TOOLS = [listar_estagios_crm, buscar_contexto_crm, mover_lead, adicionar_nota_crm, fechar_deal_crm]
    ''')


def generate_crm_updater(cfg: dict) -> str:
    nome = cfg['nome']
    descricao = cfg.get('descricao', nome)
    return dedent(f'''\
    """
    CRM Updater — roda em background após cada mensagem processada.
    A IA analisa o contexto e decide autonomamente que ações tomar no CRM.
    """
    import os
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    from ..agent.crm_tools import ALL_CRM_TOOLS


    _SYSTEM = """\\
    Você é o módulo de CRM do agente {descricao}.
    Analise o contexto da conversa e execute as ações corretas no CRM.

    Diretrizes:
    - Chame buscar_contexto_crm primeiro para obter o deal_id e etapa atual
    - Mova o lead quando houver progressão clara no funil
    - Adicione notas para objeções, interesses, contexto relevante
    - Feche como won apenas com compra confirmada, lost apenas com desistência explícita
    - Se nada relevante aconteceu, não faça nada
    """

    _PROMPT = """\\
    Contexto do lead {{phone_masked}}:
    Nome: {{user_name}} | Etapa: {{stage}} | Ação da IA: {{action}}
    Objeções: {{objection_count}} | Pagamento detectado: {{payment_method}}

    Histórico recente:
    {{history}}

    Execute as ações de CRM necessárias.
    """


    def _get_llm():
        if os.environ.get("ANTHROPIC_API_KEY"):
            return ChatAnthropic(model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"), temperature=0).bind_tools(ALL_CRM_TOOLS)
        return ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"), temperature=0).bind_tools(ALL_CRM_TOOLS)


    async def run_crm_update(phone: str, user_name: str, stage: str, action: str,
                             objection_count: int, payment_method: str, history_messages: list) -> None:
        """Executa atualização do CRM em background. Chame com asyncio.create_task()."""
        if not os.environ.get("ZYNK_WEBHOOK_URL") or not os.environ.get("ZYNK_ORG_ID"):
            return

        lines = []
        for msg in history_messages[-12:]:
            if isinstance(msg, HumanMessage):
                lines.append(f"Lead: {{msg.content}}")
            elif isinstance(msg, AIMessage) and msg.content:
                lines.append(f"IA: {{msg.content}}")

        prompt = _PROMPT.format(
            phone_masked=f"***{{phone[-4:]}}" if len(phone) >= 4 else "****",
            user_name=user_name or "não identificado",
            stage=stage, action=action,
            objection_count=objection_count,
            payment_method=payment_method or "não detectado",
            history="\\n".join(lines) or "(sem histórico)",
        )

        try:
            llm = _get_llm()
            messages = [HumanMessage(content=_SYSTEM), HumanMessage(content=prompt)]
            tool_map = {{t.name: t for t in ALL_CRM_TOOLS}}

            for _ in range(5):
                response = await llm.ainvoke(messages)
                messages.append(response)
                tool_calls = getattr(response, "tool_calls", []) or []
                if not tool_calls:
                    break
                for tc in tool_calls:
                    fn = tool_map.get(tc["name"])
                    if not fn:
                        continue
                    try:
                        result = await fn.ainvoke(tc["args"])
                        messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
                    except Exception as te:
                        messages.append(ToolMessage(content=f"Erro: {{te}}", tool_call_id=tc["id"]))
        except Exception:
            pass
    ''')


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

    # Zynk CRM (opcional — preencha para habilitar atualizações automáticas no kanban)
    ZYNK_WEBHOOK_URL=https://zynk-webhook.caxgyu.easypanel.host
    ZYNK_ADMIN_SECRET=
    ZYNK_ORG_ID=
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
    from ..services.crm_updater import run_crm_update

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

        from ..personality.prompts import DADOS_EXTRAIR

        state_kwargs = dict(
            phone=phone,
            messages=history + [HumanMessage(content=combined_text)],
            stage=session.get("stage", "nurturing"),
            current_step=session.get("current_step", 1),
            sub_state=session.get("sub_state", ""),
            objection_count=session.get("objection_count", 0),
            payment_method=session.get("payment_method", ""),
        )
        for campo in DADOS_EXTRAIR:
            state_kwargs[campo] = session.get(campo, "")

        state = ConversationState(**state_kwargs)

        raw = await agent.ainvoke(state)

        messages_to_send: list[str] = raw.get("messages_to_send") or []
        message_delays: list[int] = raw.get("message_delays") or []

        if messages_to_send:
            if message_delays:
                message_delays[0] = max(message_delays[0], 2)
            asyncio.create_task(send_messages_sequence(phone, messages_to_send, message_delays))

        session_data = {{
            "stage": raw.get("stage", "nurturing"),
            "current_step": raw.get("current_step", step),
            "sub_state": raw.get("sub_state", ""),
            "objection_count": raw.get("objection_count", 0),
            "payment_method": raw.get("payment_method", ""),
        }}
        for campo in DADOS_EXTRAIR:
            session_data[campo] = raw.get(campo, "")
        await redis_memory.save_session(phone, session_data)

        # CRM update autônomo (fire-and-forget)
        asyncio.create_task(run_crm_update(
            phone=phone,
            user_name=raw.get("user_name", ""),
            stage=raw.get("stage", "nurturing"),
            action=raw.get("current_intent", ""),
            objection_count=raw.get("objection_count", 0),
            payment_method=raw.get("payment_method", ""),
            history_messages=raw.get("messages", []),
        ))


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
        f'src/{nome}/agent/graph.py':           generate_graph(cfg),
        f'src/{nome}/agent/nodes.py':            generate_nodes(cfg),
        f'src/{nome}/agent/state.py':            generate_state(cfg),
        f'src/{nome}/agent/crm_tools.py':        generate_crm_tools(cfg),
        f'src/{nome}/personality/prompts.py':    generate_prompts(cfg),
        f'src/{nome}/services/apis.py':          generate_apis_service(cfg),
        f'src/{nome}/services/crm_updater.py':   generate_crm_updater(cfg),
        f'src/{nome}/api/webhooks.py':           generate_webhooks(cfg),
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

    # ── Dados a extrair ──────────────────────────────────────────────────────
    print('\n── 3.5. DADOS DO LEAD A EXTRAIR ───────────────────────')
    print('Quais informações o agente deve extrair do lead durante a conversa?')
    print('Ex: nome, interesse, área de problema, empresa, cargo...')
    print()
    dados_extrair = []
    k = 1
    while True:
        campo_label = ask(f'Dado {k} — nome/label (ex: nome, interesse, empresa; vazio para terminar)')
        if not campo_label:
            break
        campo_slug = 'extracted_' + slugify(campo_label)
        descricao_campo = ask(f'  Descrição de "{campo_label}"', f'{campo_label} do lead')
        dados_extrair.append({'campo': campo_slug, 'descricao': descricao_campo})
        k += 1
    if not dados_extrair:
        dados_extrair = [{'campo': 'extracted_nome', 'descricao': 'Primeiro nome do lead'}]
        print('  (usando apenas: extracted_nome)')
    cfg['dados_extrair'] = dados_extrair

    # ── Humanização ──────────────────────────────────────────────────────────
    print('\n── 3.6. HUMANIZAÇÃO E VOCABULÁRIO ─────────────────────')
    print('Configure como o agente vai soar mais humano.')
    print()
    subs = {}
    print('Substituições de vocabulário (ex: "problema" -> "desafio"):')
    while True:
        palavra = ask('  Palavra original (vazio para terminar)')
        if not palavra:
            break
        substituto = ask(f'  Substituir "{palavra}" por')
        if substituto:
            subs[palavra] = substituto
    conectores_input = ask(
        'Conectores naturais (separados por vírgula)',
        'olha, sabe?, então, é que'
    )
    conectores = [c.strip() for c in conectores_input.split(',') if c.strip()]
    cfg['vocabulario'] = {'substituicoes': subs, 'conectores': conectores}

    # ── Pagamento e objeções ─────────────────────────────────────────────────
    print('\n── 3.7. PAGAMENTO E OBJEÇÕES ──────────────────────────')
    formas_input = ask('Formas de pagamento (separadas por vírgula)', 'pix, cartao')
    cfg['formas_pagamento'] = [f.strip() for f in formas_input.split(',') if f.strip()]
    cfg['max_objecoes'] = int(ask('Máximo de objeções antes de pivotar', '2'))

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
    print(f'  Dados extrair: {len(cfg.get("dados_extrair", []))} campos')
    print(f'  Formas de pagamento: {", ".join(cfg.get("formas_pagamento", []))}')
    print(f'  Max objeções: {cfg.get("max_objecoes", 2)}')
    vocab = cfg.get("vocabulario", {})
    print(f'  Substituições vocab: {len(vocab.get("substituicoes", {}))}')
    print(f'  APIs: {len(cfg["apis"])}')
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
