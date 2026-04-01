#!/usr/bin/env python3
"""
Azure DevOps Metrics — Gerador de Relatório com Storytelling (Gemini)
======================================================================
Puxa métricas das últimas sprints, calcula scope increase e
gera um relatório HTML com narrativa automática via Google Gemini.

Requisitos:
    pip install requests google-generativeai python-dotenv

Como usar:
    1. Configure variáveis de ambiente (AZURE_DEVOPS_PAT e GEMINI_API_KEY)
    2. Edite as configurações abaixo (ORGANIZACAO, PROJETO, TEAM...)
    3. Execute:  python main.py
    4. Abra o arquivo  relatorio_devops.html  gerado na mesma pasta

Chave gratuita do Gemini:
    https://aistudio.google.com/app/apikey
"""

import base64
import importlib
import json
import os
import sys
import webbrowser
from datetime import datetime
from collections import defaultdict

try:
    import requests
except ImportError:
    print("Instale as dependências:  pip install requests google-generativeai python-dotenv")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    genai = importlib.import_module("google.generativeai")
    HAS_GEMINI = True
except ImportError:
    genai = None
    HAS_GEMINI = False
    print("⚠️  google-generativeai não instalado — storytelling desativado.")
    print("   Para ativar:  pip install google-generativeai\n")

# ─────────────────────────────────────────────
#  CONFIGURAÇÕES — edite aqui
# ─────────────────────────────────────────────
ORGANIZACAO  = os.getenv("AZURE_DEVOPS_ORGANIZACAO", "wiipo")      # só o nome, sem URL
PROJETO      = os.getenv("AZURE_DEVOPS_PROJETO", "Wiipo")          # nome exato do projeto
TEAM         = os.getenv("AZURE_DEVOPS_TEAM", "Plataforma")        # nome do time (board)
PAT          = os.getenv("AZURE_DEVOPS_PAT", "")                   # Personal Access Token do Azure DevOps
GEMINI_KEY   = os.getenv("GEMINI_API_KEY", "")                     # API Key do Google Gemini
NUM_SPRINTS  = int(os.getenv("AZURE_DEVOPS_NUM_SPRINTS", "1"))     # quantas sprints analisar
OPEN_BROWSER = os.getenv("OPEN_BROWSER", "true").lower() == "true" # abre HTML no navegador
ARQUIVO_HTML = "relatorio_devops.html"

# Tipos que aparecem no board da sprint (bate com o analytics do board)
TIPOS_BOARD = ("User Story", "Bug")
# ─────────────────────────────────────────────


def headers():
    token = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def proj_api(path):
    return f"https://dev.azure.com/{ORGANIZACAO}/{PROJETO}/_apis/{path}"


def team_api(team, path):
    return f"https://dev.azure.com/{ORGANIZACAO}/{PROJETO}/{requests.utils.quote(team)}/_apis/{path}"


def org_api(path):
    return f"https://dev.azure.com/{ORGANIZACAO}/_apis/{path}"


def get(url):
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    return r.json()


def post(url, body):
    r = requests.post(url, headers=headers(), json=body)
    r.raise_for_status()
    return r.json()


def is_done(state):
    return state in ("Done", "Closed", "Resolved", "Completed")


def parse_date(s):
    if not s:
        return None
    s = s[:19].replace("T", " ")
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def cycle_days(item):
    if not is_done(item["fields"].get("System.State", "")):
        return None
    created = parse_date(item["fields"].get("System.CreatedDate"))
    closed  = (parse_date(item["fields"].get("Microsoft.VSTS.Common.ClosedDate"))
               or parse_date(item["fields"].get("System.ChangedDate")))
    if not created or not closed:
        return None
    return max((closed - created).days, 0)


# ── 1. Descobrir time ─────────────────────────────────────────────────────────

def find_team():
    team_name = TEAM.strip()
    if team_name:
        return team_name
    try:
        data = get(org_api(f"projects/{PROJETO}/teams?api-version=7.1"))
        teams = data.get("value", [])
        if teams:
            return teams[0]["name"]
    except Exception:
        pass
    return PROJETO + " Team"


# ── 2. Buscar sprints ─────────────────────────────────────────────────────────

def fetch_iterations(team_name):
    candidates = [team_name, PROJETO + " Team", PROJETO]
    for tc in candidates:
        for timeframe in ["past", None]:
            try:
                url = team_api(tc, "work/teamsettings/iterations?api-version=7.1")
                if timeframe:
                    url += f"&$timeframe={timeframe}"
                data = get(url)
                iters = [i for i in (data.get("value") or [])
                         if i.get("attributes", {}).get("startDate")]
                if iters:
                    print(f"  Sprints encontradas no time '{tc}'")
                    return tc, iters
            except Exception:
                continue
    raise RuntimeError(
        "Nenhuma sprint encontrada. Verifique PROJETO, TEAM e permissões do PAT."
    )


# ── 3. Buscar work items ──────────────────────────────────────────────────────

def fetch_work_items(iterations):
    paths = ", ".join(f"'{i['path']}'" for i in iterations)
    tipos = ", ".join(f"'{t}'" for t in TIPOS_BOARD)
    wiql = {
        "query": (
            f"SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject]='{PROJETO}' "
            f"AND [System.IterationPath] IN ({paths}) "
            f"AND [System.WorkItemType] IN ({tipos}) "
            f"AND [System.State] <> 'Removed' "
            f"ORDER BY [System.CreatedDate] ASC"
        )
    }
    data = post(proj_api("wit/wiql?api-version=7.1"), wiql)
    ids = [w["id"] for w in (data.get("workItems") or [])]
    if not ids:
        return []

    fields = ",".join([
        "System.Id", "System.Title", "System.WorkItemType",
        "System.State", "System.CreatedDate", "System.ChangedDate",
        "Microsoft.VSTS.Common.ClosedDate",
        "System.IterationPath", "System.AssignedTo",
    ])
    items = []
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        url = proj_api(
            f"wit/workitems?ids={','.join(map(str, chunk))}"
            f"&fields={fields}&api-version=7.1"
        )
        batch = get(url)
        items.extend(batch.get("value") or [])
        print(f"  Work items carregados: {len(items)}/{len(ids)}")
    return items


# ── 4. Calcular scope increase ────────────────────────────────────────────────

def compute_scope_increase(iterations, work_items):
    results = []
    for it in iterations:
        sprint_start = parse_date(it["attributes"].get("startDate", ""))
        if not sprint_start:
            continue

        items_in_sprint = [
            w for w in work_items
            if w["fields"].get("System.IterationPath", "") == it["path"]
        ]

        scope_added = []
        for item in items_in_sprint:
            created = parse_date(item["fields"].get("System.CreatedDate"))
            if created and created > sprint_start:
                scope_added.append({
                    "id":         item["id"],
                    "title":      item["fields"].get("System.Title", "")[:80],
                    "type":       item["fields"].get("System.WorkItemType", ""),
                    "state":      item["fields"].get("System.State", ""),
                    "added_date": created.strftime("%d/%m"),
                    "done":       is_done(item["fields"].get("System.State", "")),
                })

        results.append({
            "sprint":      it["name"],
            "start":       sprint_start.strftime("%d/%m/%Y"),
            "scope_added": scope_added,
            "scope_count": len(scope_added),
            "scope_done":  sum(1 for s in scope_added if s["done"]),
        })

    return results


# ── 5. Calcular métricas ──────────────────────────────────────────────────────

def compute(iterations, work_items):
    iter_map = {i["path"]: i["name"] for i in iterations}

    def iter_name(path):
        return iter_map.get(path, (path or "").split("\\")[-1])

    by_iter = defaultdict(list)
    for w in work_items:
        by_iter[w["fields"].get("System.IterationPath", "")].append(w)

    sprints = []
    for it in iterations:
        its  = by_iter.get(it["path"], [])
        bugs = [w for w in its if w["fields"]["System.WorkItemType"] == "Bug"]
        done = sum(1 for w in its if is_done(w["fields"]["System.State"]))
        cts  = [c for c in (cycle_days(w) for w in its) if c is not None]
        sprints.append({
            "name":        it["name"],
            "total":       len(its),
            "done":        done,
            "throughput":  done,
            "bugs_open":   sum(1 for w in bugs if not is_done(w["fields"]["System.State"])),
            "bugs_closed": sum(1 for w in bugs if is_done(w["fields"]["System.State"])),
            "avg_cycle":   round(sum(cts) / len(cts)) if cts else 0,
        })

    all_bugs  = [w for w in work_items if w["fields"]["System.WorkItemType"] == "Bug"]
    open_bugs = [w for w in all_bugs   if not is_done(w["fields"]["System.State"])]
    all_cts   = [c for c in (cycle_days(w) for w in work_items) if c is not None]
    s_cts     = sorted(all_cts)
    med = s_cts[len(s_cts) // 2] if s_cts else 0
    p85 = s_cts[min(int(len(s_cts) * 0.85), len(s_cts) - 1)] if s_cts else 0

    state_map = defaultdict(int)
    type_map  = defaultdict(int)
    for w in work_items:
        state_map[w["fields"].get("System.State", "?")] += 1
        type_map[w["fields"].get("System.WorkItemType", "?")] += 1

    buckets = {"0-3": 0, "4-7": 0, "8-14": 0, "15-30": 0, "31+": 0}
    for c in all_cts:
        if   c <= 3:  buckets["0-3"]   += 1
        elif c <= 7:  buckets["4-7"]   += 1
        elif c <= 14: buckets["8-14"]  += 1
        elif c <= 30: buckets["15-30"] += 1
        else:         buckets["31+"]   += 1

    assignee_map = defaultdict(lambda: {"total": 0, "done": 0})
    for w in work_items:
        a    = w["fields"].get("System.AssignedTo") or {}
        name = a.get("displayName", "Sem responsável") if isinstance(a, dict) else str(a)
        assignee_map[name]["total"] += 1
        if is_done(w["fields"].get("System.State", "")):
            assignee_map[name]["done"] += 1

    scope_data = compute_scope_increase(iterations, work_items)

    return {
        "sprints":      sprints,
        "scope_data":   scope_data,
        "total_items":  len(work_items),
        "total_done":   sum(1 for w in work_items if is_done(w["fields"]["System.State"])),
        "open_bugs":    len(open_bugs),
        "all_bugs":     len(all_bugs),
        "avg_cycle":    round(sum(all_cts) / len(all_cts)) if all_cts else 0,
        "med_cycle":    med,
        "p85_cycle":    p85,
        "has_cycle":    len(all_cts) > 0,
        "state_map":    dict(sorted(state_map.items(), key=lambda x: -x[1])),
        "type_map":     dict(type_map),
        "buckets":      buckets,
        "assignee_map": dict(sorted(assignee_map.items(), key=lambda x: -x[1]["done"])),
        "open_bugs_list": [
            {
                "id":    w["id"],
                "title": w["fields"].get("System.Title", "")[:80],
                "state": w["fields"].get("System.State", ""),
                "iter":  iter_name(w["fields"].get("System.IterationPath", "")),
            }
            for w in open_bugs[:30]
        ],
    }


# ── 6. Storytelling via Gemini ────────────────────────────────────────────────

def build_prompt(metrics, team_name):
    sprints = metrics["sprints"]
    scope   = metrics["scope_data"]
    s       = sprints[0] if sprints else {}
    sc      = scope[0]   if scope   else {}

    pct_done    = round(s.get("done", 0) / s.get("total", 1) * 100) if s.get("total") else 0
    scope_count = sc.get("scope_count", 0)
    scope_done  = sc.get("scope_done",  0)

    return f"""Você é um Scrum Master experiente preparando o resumo da sprint para a reunião de revisão.
Analise os dados abaixo e escreva um storytelling claro, honesto e direto ao ponto em português brasileiro.

## Dados da {s.get('name', 'sprint')} — Time {team_name}

**Throughput:**
- Total de items no board: {s.get('total', 0)} (User Stories + Bugs)
- Items concluídos (Closed): {s.get('done', 0)} ({pct_done}%)
- Items ainda em progresso ou não iniciados: {s.get('total', 0) - s.get('done', 0)}

**Distribuição por status:**
{json.dumps(metrics['state_map'], ensure_ascii=False, indent=2)}

**Bugs:**
- Bugs em aberto: {metrics['open_bugs']} (estados: {', '.join(b['state'] for b in metrics['open_bugs_list'])})
- Bugs fechados nesta sprint: {s.get('bugs_closed', 0)}
- Taxa de resolução: {round(s.get('bugs_closed', 0) / metrics['all_bugs'] * 100) if metrics['all_bugs'] else 0}%

**Scope increase (itens adicionados após início da sprint):**
- Quantidade: {scope_count} items adicionados no meio da sprint
- Desses, {scope_done} foram concluídos

**Lead time (itens fechados):**
- Média: {metrics['avg_cycle']}d | Mediana: {metrics['med_cycle']}d | P85: {metrics['p85_cycle']}d

**Throughput por responsável:**
{json.dumps(metrics['assignee_map'], ensure_ascii=False, indent=2)}

## Instruções

Estruture em 4 blocos com este formato HTML exato (use exatamente estas classes, sem markdown, sem texto fora das tags):

<div class="story-block">
  <div class="story-title">Resumo executivo</div>
  <p>2-3 frases sobre o que a sprint entregou e o cenário geral, com números específicos.</p>
</div>
<div class="story-block story-positive">
  <div class="story-title">Destaques positivos</div>
  <p>O que funcionou bem, com exemplos concretos dos dados.</p>
</div>
<div class="story-block story-warning">
  <div class="story-title">Pontos de atenção</div>
  <p>Riscos, gargalos ou padrões preocupantes. Seja honesto e específico.</p>
</div>
<div class="story-block story-action">
  <div class="story-title">Recomendações para a próxima sprint</div>
  <ul>
    <li>Ação concreta 1</li>
    <li>Ação concreta 2</li>
    <li>Ação concreta 3</li>
  </ul>
</div>
"""


def generate_storytelling(metrics, team_name):
    if not HAS_GEMINI or not GEMINI_KEY:
        return "<p style='color:#6b6b80'>Storytelling desativado — configure GEMINI_KEY para ativar.</p>"

    print("  Gerando storytelling com Gemini...")

    try:
        genai.configure(api_key=GEMINI_KEY)
        response = None
        for model_name in ("gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash-preview-05-20"):
            try:
                model    = genai.GenerativeModel(model_name)
                response = model.generate_content(build_prompt(metrics, team_name))
                print(f"  Modelo usado: {model_name}")
                break
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower() or "not found" in str(e).lower():
                    print(f"  Modelo {model_name} indisponível, tentando próximo...")
                    continue
                raise
        if response is None:
            return "<p style='color:#f04a4a'>Todos os modelos Gemini atingiram o limite de quota.</p>"
        text = response.text.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = "\n".join(text.split("\n")[:-1])
        return text.strip()
    except Exception as e:
        return f"<p style='color:#f04a4a'>Erro ao gerar storytelling: {e}</p>"


# ── 7. Gerar HTML ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DevOps Metrics · {projeto}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
:root{{
  --bg:#0f0f13;--surface:#18181f;--border:#2a2a35;
  --text:#e8e8f0;--muted:#6b6b80;--accent:#7c6fff;
  --green:#3ecf8e;--red:#f04a4a;--amber:#f0a030;--blue:#4a9cf0;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.6;padding:2rem 1.5rem;max-width:1100px;margin:0 auto}}
h1{{font-size:26px;font-weight:700;letter-spacing:-0.5px}}
.sub{{color:var(--muted);font-size:13px;margin-top:4px;margin-bottom:2rem}}
.note{{font-size:11px;color:var(--muted);background:#1e1e28;border:1px solid var(--border);border-radius:8px;padding:8px 12px;margin-bottom:1.5rem}}
.grid-5{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:1.5rem}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.25rem}}
.card-label{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-bottom:6px}}
.card-value{{font-size:28px;font-weight:700}}
.card-sub{{font-size:11px;color:var(--muted);margin-top:3px}}
.accent{{color:var(--accent)}}.green{{color:var(--green)}}.red{{color:var(--red)}}.amber{{color:var(--amber)}}.blue{{color:var(--blue)}}.muted{{color:var(--muted)}}.orange{{color:#f97316}}
.section{{margin-bottom:2rem}}
.section-title{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:1rem;padding-bottom:6px;border-bottom:1px solid var(--border)}}
.charts-row{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem}}
@media(max-width:640px){{.charts-row{{grid-template-columns:1fr}}}}
.chart-box{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.25rem}}
.chart-box h3{{font-size:13px;font-weight:600;margin-bottom:1rem;color:var(--text)}}
.canvas-wrap{{position:relative;width:100%}}
.status-list{{display:flex;flex-direction:column;gap:8px}}
.status-row{{display:flex;align-items:center;gap:8px;font-size:13px}}
.status-name{{min-width:160px;color:var(--muted)}}
.bar-track{{flex:1;height:4px;background:var(--border);border-radius:2px}}
.bar-fill{{height:4px;border-radius:2px}}
.status-n{{min-width:32px;text-align:right;font-weight:600}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);padding:6px 10px;border-bottom:1px solid var(--border)}}
td{{padding:8px 10px;border-bottom:1px solid var(--border)}}
tr:last-child td{{border-bottom:none}}
.badge{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;font-weight:500}}
.badge-test{{background:#2a2035;color:var(--amber)}}
.badge-ready{{background:#1e2a1e;color:var(--green)}}
.badge-active{{background:#1e2035;color:var(--blue)}}
.badge-scope{{background:#2a1a10;color:#f97316}}
.badge-other{{background:#252525;color:var(--muted)}}
.footer{{margin-top:2rem;font-size:11px;color:var(--muted);text-align:center}}
.dimmed{{color:var(--muted)}}
.story-block{{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--border);border-radius:12px;padding:1.25rem;margin-bottom:1rem}}
.story-block.story-positive{{border-left-color:var(--green)}}
.story-block.story-warning{{border-left-color:var(--amber)}}
.story-block.story-action{{border-left-color:var(--accent)}}
.story-title{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:8px;font-weight:600}}
.story-block p{{color:var(--text);line-height:1.7;font-size:14px}}
.story-block ul{{padding-left:1.2rem;color:var(--text);line-height:1.9;font-size:14px}}
.story-block strong{{color:var(--accent)}}
</style>
</head>
<body>
<h1>📊 {projeto} <span style="font-weight:400;font-size:18px;color:var(--muted)">/ {team}</span></h1>
<div class="sub">Gerado em {gerado} · {num_sprints} sprint(s) · {total_items} items (User Story + Bug)</div>

{cycle_note}

<div class="section">
  <div class="section-title">Narrativa da sprint</div>
  {storytelling}
</div>

<div class="section">
  <div class="section-title">Visão geral</div>
  <div class="grid-5">
    <div class="card">
      <div class="card-label">Items na sprint</div>
      <div class="card-value accent">{total_items}</div>
      <div class="card-sub">{total_done} concluídos ({pct_done}%)</div>
    </div>
    <div class="card">
      <div class="card-label">Scope increase</div>
      <div class="card-value orange">{scope_count}</div>
      <div class="card-sub">adicionados após início · {scope_done} concluídos</div>
    </div>
    <div class="card">
      <div class="card-label">Bugs em aberto</div>
      <div class="card-value red">{open_bugs}</div>
      <div class="card-sub">{all_bugs} total · {bugs_closed_total} fechados</div>
    </div>
    <div class="card">
      <div class="card-label">Taxa resolução bugs</div>
      <div class="card-value amber">{bug_resolution}%</div>
      <div class="card-sub">{bugs_closed_total} de {all_bugs} fechados</div>
    </div>
    <div class="card">
      <div class="card-label">Lead time médio</div>
      <div class="card-value {cycle_color}">{avg_cycle}</div>
      <div class="card-sub">mediana {med_cycle} · p85 {p85_cycle}</div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">Scope increase — itens adicionados após início da sprint</div>
  <div class="chart-box" style="overflow-x:auto">
    <table><thead><tr><th>ID</th><th>Tipo</th><th>Título</th><th>Adicionado em</th><th>Estado</th></tr></thead>
    <tbody id="scope-tbody"></tbody></table>
  </div>
</div>

<div class="section">
  <div class="section-title">Throughput por sprint</div>
  <div class="chart-box">
    <h3>Items concluídos vs total na sprint</h3>
    <div class="canvas-wrap" style="height:220px"><canvas id="c-thru"></canvas></div>
  </div>
</div>

<div class="section">
  <div class="section-title">Distribuição por status</div>
  <div class="chart-box">
    <div class="status-list" id="status-list"></div>
  </div>
</div>

<div class="section">
  <div class="section-title">Bugs</div>
  <div class="charts-row">
    <div class="chart-box">
      <h3>Abertos vs fechados por sprint</h3>
      <div class="canvas-wrap" style="height:220px"><canvas id="c-bugs"></canvas></div>
    </div>
    <div class="chart-box">
      <h3>Bugs em aberto</h3>
      <div style="overflow-x:auto">
        <table><thead><tr><th>ID</th><th>Título</th><th>Estado</th></tr></thead>
        <tbody id="bugs-tbody"></tbody></table>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <div class="section-title">Lead / Cycle time {cycle_disclaimer}</div>
  <div class="charts-row">
    <div class="chart-box"><h3>Lead time médio por sprint (dias)</h3><div class="canvas-wrap" style="height:200px"><canvas id="c-ct"></canvas></div></div>
    <div class="chart-box"><h3>Distribuição por faixa (dias)</h3><div class="canvas-wrap" style="height:200px"><canvas id="c-dist"></canvas></div></div>
  </div>
</div>

<div class="section">
  <div class="section-title">Throughput por responsável</div>
  <div class="chart-box">
    <div class="status-list" id="assignee-list"></div>
  </div>
</div>

<div class="footer">Gerado por azure_devops_metrics.py · {gerado}</div>

<script>
const DATA = {data_json};
const C = {{acc:'#7c6fff',grn:'#3ecf8e',red:'#f04a4a',amb:'#f0a030',blu:'#4a9cf0',mut:'#6b6b80'}};
const GRID = {{color:'#2a2a35'}};
const TICK = {{color:'#6b6b80'}};

// Scope table
const st = document.getElementById('scope-tbody');
const allScope = DATA.scope_data.flatMap(s=>s.scope_added);
if(allScope.length===0){{
  st.innerHTML='<tr><td colspan="5" style="color:#6b6b80">Nenhum item adicionado após o início da sprint.</td></tr>';
}}else{{
  allScope.forEach(item=>{{
    const tag = item.done
      ? '<span class="badge badge-ready">Concluído</span>'
      : '<span class="badge badge-scope">Em aberto</span>';
    st.innerHTML+=`<tr><td class="dimmed">#${{item.id}}</td><td>${{item.type==='Bug'?'🐛':'📋'}} ${{item.type}}</td><td>${{item.title}}</td><td style="color:#f97316;white-space:nowrap">${{item.added_date}}</td><td>${{tag}}</td></tr>`;
  }});
}}

// Throughput
new Chart(document.getElementById('c-thru'),{{
  type:'bar',
  data:{{labels:DATA.sprints.map(s=>s.name),datasets:[
    {{label:'Total',data:DATA.sprints.map(s=>s.total),backgroundColor:'rgba(74,156,240,0.2)',borderColor:C.blu,borderWidth:1,borderRadius:4}},
    {{label:'Concluídos',data:DATA.sprints.map(s=>s.done),backgroundColor:C.grn,borderRadius:4}},
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{labels:{{color:C.mut,font:{{size:11}}}}}}}},scales:{{x:{{grid:GRID,ticks:TICK}},y:{{grid:GRID,ticks:TICK,beginAtZero:true}}}}}}
}});

// Status
const sc={{Closed:C.grn,Done:C.grn,Resolved:C.grn,Test:C.amb,Ready:C.blu,Active:'#a78bfa',Review:'#f472b6',New:C.mut}};
const maxS=Math.max(...Object.values(DATA.state_map),1);
const sl=document.getElementById('status-list');
Object.entries(DATA.state_map).forEach(([s,c])=>{{
  const color=sc[s]||C.mut;
  sl.innerHTML+=`<div class="status-row"><span class="status-name">${{s}}</span><div class="bar-track"><div class="bar-fill" style="width:${{Math.round(c/maxS*100)}}%;background:${{color}}"></div></div><span class="status-n" style="color:${{color}}">${{c}}</span><span style="font-size:11px;color:${{C.mut}};min-width:36px;text-align:right">${{Math.round(c/DATA.total_items*100)}}%</span></div>`;
}});

// Bugs
new Chart(document.getElementById('c-bugs'),{{
  type:'bar',
  data:{{labels:DATA.sprints.map(s=>s.name),datasets:[
    {{label:'Abertos',data:DATA.sprints.map(s=>s.bugs_open),backgroundColor:C.red,borderRadius:4}},
    {{label:'Fechados',data:DATA.sprints.map(s=>s.bugs_closed),backgroundColor:C.grn,borderRadius:4}},
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{labels:{{color:C.mut,font:{{size:11}}}}}}}},scales:{{x:{{grid:GRID,ticks:TICK}},y:{{grid:GRID,ticks:TICK,beginAtZero:true}}}}}}
}});
const tb=document.getElementById('bugs-tbody');
const bc=s=>({{'Test':'badge-test','Ready':'badge-ready','Active':'badge-active'}}[s]||'badge-other');
DATA.open_bugs_list.length===0
  ? tb.innerHTML='<tr><td colspan="3" style="color:#6b6b80">Nenhum bug em aberto</td></tr>'
  : DATA.open_bugs_list.forEach(b=>{{tb.innerHTML+=`<tr><td class="dimmed">#${{b.id}}</td><td>${{b.title}}</td><td><span class="badge ${{bc(b.state)}}">${{b.state}}</span></td></tr>`;}});

// Cycle time
new Chart(document.getElementById('c-ct'),{{
  type:'bar',
  data:{{labels:DATA.sprints.map(s=>s.name),datasets:[{{label:'Média (dias)',data:DATA.sprints.map(s=>s.avg_cycle||null),backgroundColor:C.amb,borderRadius:4}}]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:GRID,ticks:TICK}},y:{{grid:GRID,ticks:TICK,beginAtZero:true}}}}}}
}});
new Chart(document.getElementById('c-dist'),{{
  type:'bar',
  data:{{labels:Object.keys(DATA.buckets),datasets:[{{label:'Items',data:Object.values(DATA.buckets),backgroundColor:['#9FE1CB','#5DCAA5','#1D9E75','#0F6E56','#085041'],borderRadius:4}}]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{display:false}},ticks:TICK}},y:{{grid:GRID,ticks:TICK,beginAtZero:true}}}}}}
}});

// Assignees
const al=document.getElementById('assignee-list');
const maxA=Math.max(...Object.values(DATA.assignee_map).map(v=>v.total),1);
Object.entries(DATA.assignee_map).slice(0,20).forEach(([name,v])=>{{
  const pct=v.total>0?Math.round(v.done/v.total*100):0;
  al.innerHTML+=`<div class="status-row"><span class="status-name">${{name}}</span><div class="bar-track"><div class="bar-fill" style="width:${{Math.round(v.total/maxA*100)}}%;background:${{C.acc}}"></div></div><span class="status-n accent">${{v.done}}</span><span style="font-size:11px;color:${{C.mut}};min-width:80px;text-align:right">/ ${{v.total}} (${{pct}}%)</span></div>`;
}});
</script>
</body>
</html>
"""


def generate_html(team_name, iterations, metrics, storytelling_html):
    sc = metrics["scope_data"][0] if metrics["scope_data"] else {}
    scope_count       = sc.get("scope_count", 0)
    scope_done        = sc.get("scope_done",  0)
    bugs_closed_total = sum(s["bugs_closed"] for s in metrics["sprints"])
    bug_resolution    = round(bugs_closed_total / metrics["all_bugs"] * 100) if metrics["all_bugs"] else 0
    pct_done          = round(metrics["total_done"] / metrics["total_items"] * 100) if metrics["total_items"] else 0
    has_cycle         = metrics["has_cycle"]

    html = HTML_TEMPLATE.format(
        projeto=PROJETO,
        team=team_name,
        gerado=datetime.now().strftime("%d/%m/%Y %H:%M"),
        num_sprints=len(iterations),
        total_items=metrics["total_items"],
        total_done=metrics["total_done"],
        pct_done=pct_done,
        scope_count=scope_count,
        scope_done=scope_done,
        open_bugs=metrics["open_bugs"],
        all_bugs=metrics["all_bugs"],
        avg_cycle=f"{metrics['avg_cycle']}d" if has_cycle else "—",
        med_cycle=f"{metrics['med_cycle']}d" if has_cycle else "—",
        p85_cycle=f"{metrics['p85_cycle']}d" if has_cycle else "—",
        cycle_color="amber" if has_cycle else "muted",
        cycle_disclaimer="· baseado em CreatedDate → ChangedDate (itens Closed)" if has_cycle else "",
        cycle_note="" if has_cycle else '<div class="note">⚠️ Lead time não calculado: nenhum item Closed tinha datas suficientes.</div>',
        bugs_closed_total=bugs_closed_total,
        bug_resolution=bug_resolution,
        storytelling=storytelling_html,
        data_json=json.dumps(metrics, ensure_ascii=False),
    )
    with open(ARQUIVO_HTML, "w", encoding="utf-8") as f:
        f.write(html)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not PAT:
        print("❌ Configure AZURE_DEVOPS_PAT na sua variável de ambiente.")
        print("   Exemplo (macOS/Linux): export AZURE_DEVOPS_PAT='seu_token'")
        sys.exit(1)

    print(f"\n🔄 Conectando em dev.azure.com/{ORGANIZACAO}/{PROJETO}...")
    print(f"   Tipos de item: {TIPOS_BOARD}")

    team_name = find_team()

    print(f"  Buscando as últimas {NUM_SPRINTS} sprint(s)...")
    used_team, all_iters = fetch_iterations(team_name)

    with_dates   = [i for i in all_iters if i.get("attributes", {}).get("startDate")]
    sorted_iters = sorted(with_dates, key=lambda i: i["attributes"]["startDate"], reverse=True)
    iterations   = list(reversed(sorted_iters[:NUM_SPRINTS]))

    print(f"  Sprints selecionadas: {', '.join(i['name'] for i in iterations)}")

    print("  Buscando work items...")
    work_items = fetch_work_items(iterations)
    print(f"  Total de work items: {len(work_items)}")

    if not work_items:
        print("⚠️  Nenhum work item encontrado.")
        sys.exit(0)

    print("  Calculando métricas...")
    metrics = compute(iterations, work_items)

    sc = metrics["scope_data"][0] if metrics["scope_data"] else {}
    print(f"\n  📊 Resumo:")
    for s in metrics["sprints"]:
        pct = round(s["done"] / s["total"] * 100) if s["total"] else 0
        print(f"     {s['name']}: {s['total']} items · {s['done']} concluídos ({pct}%) · "
              f"{s['bugs_open']} bugs abertos · scope increase: {sc.get('scope_count', 0)}")

    storytelling_html = generate_storytelling(metrics, used_team)

    generate_html(used_team, iterations, metrics, storytelling_html)
    print(f"\n✅ Relatório gerado: {os.path.abspath(ARQUIVO_HTML)}")
    if OPEN_BROWSER:
        webbrowser.open(f"file://{os.path.abspath(ARQUIVO_HTML)}")


if __name__ == "__main__":
    main()