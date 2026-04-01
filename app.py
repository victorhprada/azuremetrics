#!/usr/bin/env python3
"""
Servidor web — Status Page + Relatório de Métricas.

Local:
    python app.py          →  http://localhost:5000

Rotas:
    /          →  Status da sprint (kanban, atualiza a cada 5 min)
    /metrics   →  Relatório de métricas (throughput, bugs, scope increase…)

Vercel:
    Sobe automaticamente ao fazer deploy (ver vercel.json).
    Configure as variáveis de ambiente no painel da Vercel.
"""

from flask import Flask, Response

from status_page import (
    fetch_current_sprint,
    fetch_items,
    parse_sprint_dates,
    build_kanban,
    render_page,
    ORGANIZACAO,
    PAT,
)
from main import (
    find_team,
    fetch_iterations,
    fetch_work_items,
    compute,
    generate_storytelling,
    generate_html,
    NUM_SPRINTS,
)

app = Flask(__name__)


def _err(msg: str, status: int = 500) -> Response:
    return Response(
        f"<pre style='font-family:monospace;padding:2rem'>{msg}</pre>",
        status=status,
        mimetype="text/html",
    )


@app.route("/")
def index():
    if not PAT or not ORGANIZACAO:
        return _err(
            "Erro: variáveis de ambiente não configuradas.\n\n"
            "Verifique: AZURE_DEVOPS_PAT, AZURE_DEVOPS_ORGANIZACAO, "
            "AZURE_DEVOPS_PROJETO, AZURE_DEVOPS_TEAM"
        )
    try:
        sprint = fetch_current_sprint()
        items  = fetch_items(sprint["path"])
        start, end, total_days, elapsed_days, pct_time = parse_sprint_dates(sprint)
        columns = build_kanban(items)
        html = render_page(
            sprint, columns, start, end, total_days, elapsed_days, pct_time,
            active_page="status",
        )
        return Response(html, mimetype="text/html")
    except Exception as exc:
        return _err(f"Erro ao buscar dados da sprint:\n\n{exc}")


@app.route("/metrics")
def metrics_page():
    if not PAT or not ORGANIZACAO:
        return _err(
            "Erro: variáveis de ambiente não configuradas.\n\n"
            "Verifique: AZURE_DEVOPS_PAT, AZURE_DEVOPS_ORGANIZACAO, "
            "AZURE_DEVOPS_PROJETO, AZURE_DEVOPS_TEAM"
        )
    try:
        team_name        = find_team()
        used_team, all_iters = fetch_iterations(team_name)

        with_dates   = [i for i in all_iters if i.get("attributes", {}).get("startDate")]
        sorted_iters = sorted(with_dates, key=lambda i: i["attributes"]["startDate"], reverse=True)
        iterations   = list(reversed(sorted_iters[:NUM_SPRINTS]))

        work_items = fetch_work_items(iterations)
        if not work_items:
            return _err("Nenhum work item encontrado para a(s) sprint(s) selecionada(s).")

        metrics          = compute(iterations, work_items)
        storytelling_html = generate_storytelling(metrics, used_team)
        html             = generate_html(used_team, iterations, metrics, storytelling_html)
        return Response(html, mimetype="text/html")
    except Exception as exc:
        return _err(f"Erro ao buscar métricas:\n\n{exc}")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
