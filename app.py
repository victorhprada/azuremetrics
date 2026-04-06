#!/usr/bin/env python3
"""
Servidor web — Status Page + Relatório de Métricas.

Local:
    python app.py          →  http://localhost:5000

Rotas:
    /          →  Status da sprint (kanban, atualiza a cada 5 min)
    /metrics   →  Lista sprints para escolher a âncora do relatório
    /metrics?latest=1 →  Últimas N sprints (padrão; N = AZURE_DEVOPS_NUM_SPRINTS)
    /metrics?path=... →  Relatório ancorado na sprint (path exato da API)

Vercel:
    Sobe automaticamente ao fazer deploy (ver vercel.json).
    Configure as variáveis de ambiente no painel da Vercel.
"""

from flask import Flask, Response, render_template, request

from status_page import (
    fetch_current_sprint,
    fetch_items,
    parse_sprint_dates,
    build_kanban,
    render_page,
    ORGANIZACAO,
    PAT,
    PROJETO,
    TEAM,
)
from main import (
    NUM_SPRINTS,
    compute,
    fetch_iterations,
    fetch_work_items,
    find_team,
    generate_html,
    generate_storytelling,
    select_iterations_for_metrics,
)

app = Flask(__name__)

_AZURE_KEYS = (
    ("AZURE_DEVOPS_PAT", lambda: PAT),
    ("AZURE_DEVOPS_ORGANIZACAO", lambda: ORGANIZACAO),
    ("AZURE_DEVOPS_PROJETO", lambda: PROJETO),
    ("AZURE_DEVOPS_TEAM", lambda: TEAM),
)


def _azure_env_error_msg() -> str | None:
    missing = [name for name, get in _AZURE_KEYS if not (get() or "").strip()]
    if not missing:
        return None
    lines = "\n".join(f"  - {k}" for k in missing)
    return (
        "Erro: variáveis de ambiente não configuradas.\n\n"
        f"Faltando ou vazias:\n{lines}\n\n"
        "Na Vercel: Project → Settings → Environment Variables.\n"
        "Adicione cada nome acima (mesmos nomes do .env local).\n"
        "Marque Production, Preview e Development conforme o ambiente.\n"
        "Depois: Deployments → … no último deploy → Redeploy."
    )


def _err(msg: str, status: int = 500) -> Response:
    return Response(
        f"<pre style='font-family:monospace;padding:2rem'>{msg}</pre>",
        status=status,
        mimetype="text/html",
    )


def _picker_rows(all_iters: list) -> list[dict]:
    """Linhas para o template: name, start, end, path (bruto; url_for codifica a query)."""
    with_dates = [i for i in all_iters if i.get("attributes", {}).get("startDate")]
    sorted_newest = sorted(
        with_dates,
        key=lambda i: i["attributes"]["startDate"],
        reverse=True,
    )
    rows = []
    for it in sorted_newest:
        attrs = it.get("attributes") or {}
        rows.append({
            "name": it.get("name", ""),
            "start": (attrs.get("startDate") or "")[:10],
            "end": (attrs.get("finishDate") or "")[:10] or "—",
            "path": it.get("path") or "",
        })
    return rows


@app.route("/")
def index():
    env_err = _azure_env_error_msg()
    if env_err:
        return _err(env_err)
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
    env_err = _azure_env_error_msg()
    if env_err:
        return _err(env_err)
    try:
        team_name = find_team()
        used_team, all_iters = fetch_iterations(team_name)

        raw_path = request.args.get("path")
        use_latest = request.args.get("latest", "").lower() in ("1", "true", "yes")

        # Sem path e sem latest → página para escolher sprint
        if raw_path is None and not use_latest:
            rows = _picker_rows(all_iters)
            html = render_template(
                "metrics_picker.html",
                active_page="metrics",
                projeto=PROJETO,
                num_sprints=NUM_SPRINTS,
                sprints=rows,
            )
            return Response(html, mimetype="text/html")

        # latest=1 ou path vazio explícito → últimas N (comportamento padrão)
        sprint_path = None
        if raw_path is not None and str(raw_path).strip():
            sprint_path = str(raw_path).strip()

        try:
            iterations = select_iterations_for_metrics(
                all_iters, sprint_path, NUM_SPRINTS
            )
        except ValueError as err:
            return _err(str(err), status=400)

        work_items = fetch_work_items(iterations)
        if not work_items:
            return _err("Nenhum work item encontrado para a(s) sprint(s) selecionada(s).")

        metrics = compute(iterations, work_items)
        storytelling_html = generate_storytelling(metrics, used_team)
        html = generate_html(
            used_team,
            iterations,
            metrics,
            storytelling_html,
            show_back_to_picker=True,
            metrics_picker_url="/metrics",
        )
        return Response(html, mimetype="text/html")
    except Exception as exc:
        return _err(f"Erro ao buscar métricas:\n\n{exc}")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
