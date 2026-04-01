#!/usr/bin/env python3
"""
Azure DevOps Status Page
========================
Gera uma página HTML simples e visual com as demandas da sprint atual —
pensada para pessoas que não têm acesso ao Azure DevOps.

Exibe:
  - Sprint atual com datas de início e fim
  - Barra de progresso da sprint (dias decorridos)
  - Barra de conclusão (itens entregues)
  - Kanban visual: A Fazer | Em Andamento | Concluído

Como usar:
    1. Configure o .env (mesmo arquivo do main.py)
    2. Execute:  python status_page.py
    3. Abra:     status_page.html
"""

import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from azure_client import AzureClient
from jinja2 import Environment, FileSystemLoader, select_autoescape

# ─────────────────────────────────────────────
#  CONFIGURAÇÕES — lidas do .env (igual ao main.py)
# ─────────────────────────────────────────────
ORGANIZACAO  = os.getenv("AZURE_DEVOPS_ORGANIZACAO", "")
PROJETO      = os.getenv("AZURE_DEVOPS_PROJETO", "")
TEAM         = os.getenv("AZURE_DEVOPS_TEAM", "")
PAT          = os.getenv("AZURE_DEVOPS_PAT", "")
OPEN_BROWSER = os.getenv("OPEN_BROWSER", "true").lower() == "true"
ARQUIVO_HTML = "status_page.html"
PAGE_TITLE   = os.getenv("STATUS_PAGE_TITLE", f"Status da Sprint — {TEAM or PROJETO}")
# ─────────────────────────────────────────────

ESTADO_LABEL: dict[str, str] = {
    # A Fazer
    "New": "A Fazer", "To Do": "A Fazer", "Backlog": "A Fazer", "Ready": "A Fazer",
    # Em Andamento
    "Active": "Em Andamento", "In Progress": "Em Andamento", "Committed": "Em Andamento",
    "Design": "Em Andamento", "Development": "Em Andamento", "In Review": "Em Andamento",
    "Testing": "Em Andamento", "Validating": "Em Andamento",
    # Concluído
    "Done": "Concluído", "Closed": "Concluído", "Resolved": "Concluído", "Completed": "Concluído",
}
COLUNAS = ["A Fazer", "Em Andamento", "Concluído"]

client = AzureClient(ORGANIZACAO, PROJETO, TEAM, PAT)

_jinja = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


# ── 1. Buscar sprint atual ────────────────────────────────────────────────────

def fetch_current_sprint() -> dict:
    """Retorna a iteração marcada como 'current' pelo Azure DevOps."""
    url  = client.team_url("work/teamsettings/iterations?$timeframe=current&api-version=7.1")
    data = client.get(url)
    iterations = data.get("value") or []
    if not iterations:
        raise RuntimeError(
            "Nenhuma sprint atual encontrada. "
            "Verifique se o time tem uma sprint ativa e se o TEAM está correto."
        )
    return iterations[0]


# ── 2. Buscar work items da sprint ────────────────────────────────────────────

def fetch_items(sprint_path: str) -> list:
    """Busca todos os work items (User Story + Bug) da sprint."""
    wiql = {
        "query": (
            f"SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.TeamProject]='{PROJETO}' "
            f"AND [System.IterationPath]='{sprint_path}' "
            f"AND [System.WorkItemType] IN ('User Story','Bug') "
            f"AND [System.State] <> 'Removed' "
            f"ORDER BY [System.WorkItemType] ASC, [System.ChangedDate] DESC"
        )
    }
    data = client.post(client.proj_url("wit/wiql?api-version=7.1"), wiql)
    ids  = [w["id"] for w in (data.get("workItems") or [])]
    if not ids:
        return []

    fields = ",".join([
        "System.Id", "System.Title", "System.WorkItemType",
        "System.State", "System.AssignedTo",
    ])
    items = []
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        url   = client.proj_url(
            f"wit/workitems?ids={','.join(map(str, chunk))}&fields={fields}&api-version=7.1"
        )
        items.extend(client.get(url).get("value") or [])
    return items


# ── 3. Processar dados ────────────────────────────────────────────────────────

def parse_sprint_dates(sprint: dict) -> tuple:
    """Retorna (start, end, dias_totais, dias_decorridos, pct_tempo)."""
    attrs = sprint.get("attributes", {})

    def _parse(s: str) -> datetime | None:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s[:19])
        except ValueError:
            return None

    start = _parse(attrs.get("startDate", ""))
    end   = _parse(attrs.get("finishDate", ""))
    now   = datetime.now()

    if start and end:
        total    = max((end - start).days, 1)
        elapsed  = max(min((now - start).days, total), 0)
        pct_time = round(elapsed / total * 100)
    else:
        total, elapsed, pct_time = 0, 0, 0

    return start, end, total, elapsed, pct_time


def build_kanban(items: list) -> dict:
    """Agrupa itens nas 3 colunas do kanban."""
    columns = {col: [] for col in COLUNAS}
    unknown = []

    for item in items:
        f            = item["fields"]
        state        = f.get("System.State", "")
        col          = ESTADO_LABEL.get(state)
        assignee_raw = f.get("System.AssignedTo") or {}
        assignee     = (
            assignee_raw.get("displayName", "")
            if isinstance(assignee_raw, dict)
            else str(assignee_raw)
        )
        card = {
            "id":       item["id"],
            "title":    f.get("System.Title", "(sem título)")[:90],
            "type":     f.get("System.WorkItemType", ""),
            "state":    state,
            "assignee": assignee or "Não atribuído",
        }
        (columns[col] if col in columns else unknown).append(card)

    # Itens com estado desconhecido entram em "Em Andamento" para não sumir
    columns["Em Andamento"].extend(unknown)
    return columns


# ── 4. Renderizar página ──────────────────────────────────────────────────────

def render_page(sprint: dict, columns: dict, start, end,
                total_days: int, elapsed_days: int, pct_time: int,
                active_page: str = "status") -> str:
    """Renderiza o HTML da status page via template Jinja2."""
    total_items = sum(len(v) for v in columns.values())
    done_items  = len(columns["Concluído"])
    days_left   = max(total_days - elapsed_days, 0)

    return _jinja.get_template("status_page.html").render(
        active_page     = active_page,
        page_title      = PAGE_TITLE,
        now_str         = datetime.now().strftime("%d/%m/%Y às %H:%M"),
        sprint_name     = sprint["name"],
        start_date      = start.strftime("%d/%m/%Y") if start else "—",
        end_date        = end.strftime("%d/%m/%Y")   if end   else "—",
        days_left_label = (
            f"{days_left} dia{'s' if days_left != 1 else ''} restante{'s' if days_left != 1 else ''}"
            if total_days > 0 else "Datas não configuradas"
        ),
        done_items  = done_items,
        total_items = total_items,
        pct_time    = pct_time,
        pct_done    = round(done_items / total_items * 100) if total_items else 0,
        columns     = [
            {"title": "A Fazer",      "css_class": "col-todo",       "cards": columns["A Fazer"]},
            {"title": "Em Andamento", "css_class": "col-inprogress", "cards": columns["Em Andamento"]},
            {"title": "Concluído",    "css_class": "col-done",       "cards": columns["Concluído"]},
        ],
        projeto = PROJETO,
        team    = TEAM,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not PAT:
        print("Erro: AZURE_DEVOPS_PAT não configurado. Verifique seu .env")
        sys.exit(1)
    if not ORGANIZACAO or not PROJETO:
        print("Erro: AZURE_DEVOPS_ORGANIZACAO e AZURE_DEVOPS_PROJETO são obrigatórios.")
        sys.exit(1)

    print(f"Buscando sprint atual — {ORGANIZACAO}/{PROJETO} [{TEAM}]")

    sprint = fetch_current_sprint()
    print(f"  Sprint: {sprint['name']}")

    print("  Buscando work items...")
    items = fetch_items(sprint["path"])
    print(f"  {len(items)} itens encontrados")

    start, end, total_days, elapsed_days, pct_time = parse_sprint_dates(sprint)
    columns = build_kanban(items)
    html    = render_page(sprint, columns, start, end, total_days, elapsed_days, pct_time)

    with open(ARQUIVO_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nStatus page gerada: {ARQUIVO_HTML}")
    print(f"  A Fazer:      {len(columns['A Fazer'])}")
    print(f"  Em Andamento: {len(columns['Em Andamento'])}")
    print(f"  Concluído:    {len(columns['Concluído'])}")

    if OPEN_BROWSER:
        webbrowser.open(ARQUIVO_HTML)


if __name__ == "__main__":
    main()
