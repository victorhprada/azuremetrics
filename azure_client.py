"""Cliente HTTP compartilhado para a API REST do Azure DevOps."""

import base64
import requests


class AzureClient:
    """Encapsula autenticação e chamadas HTTP à API do Azure DevOps."""

    def __init__(self, organizacao: str, projeto: str, team: str, pat: str):
        self.organizacao = organizacao
        self.projeto     = projeto
        self.team        = team
        self._pat        = pat

    # ── Auth ──────────────────────────────────────────────────────────────────

    @property
    def _headers(self) -> dict:
        token = base64.b64encode(f":{self._pat}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}

    # ── URL builders ──────────────────────────────────────────────────────────

    def org_url(self, path: str) -> str:
        return f"https://dev.azure.com/{self.organizacao}/_apis/{path}"

    def proj_url(self, path: str) -> str:
        return f"https://dev.azure.com/{self.organizacao}/{self.projeto}/_apis/{path}"

    def team_url(self, path: str, team: str | None = None) -> str:
        t = requests.utils.quote(team or self.team)
        return f"https://dev.azure.com/{self.organizacao}/{self.projeto}/{t}/_apis/{path}"

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def get(self, url: str) -> dict:
        r = requests.get(url, headers=self._headers)
        r.raise_for_status()
        return r.json()

    def post(self, url: str, body: dict) -> dict:
        r = requests.post(url, headers=self._headers, json=body)
        r.raise_for_status()
        return r.json()
