# Azure DevOps Metrics Report

> Gere relatórios completos de sprint em segundos — sem dashboards, sem configurações complexas. Só Python e suas variáveis de ambiente.

---

## O que este projeto faz

Conecta à API do Azure DevOps e gera automaticamente um relatório HTML rico com as métricas mais importantes do seu time de desenvolvimento:

| Métrica | O que mede |
|---|---|
| **Throughput** | Itens entregues por sprint |
| **Bugs abertos / fechados** | Saúde da qualidade do sprint |
| **Scope Increase** | Itens adicionados após o início da sprint |
| **Lead Time / Cycle Time** | Velocidade de entrega dos itens |
| **Narrativa automática** | Storytelling gerado pelo Google Gemini (opcional) |

O relatório é salvo como `relatorio_devops.html` e pode ser aberto diretamente no navegador — sem dependência de servidor, sem login adicional.

---

## Como funciona

```
.env  ──►  main.py  ──►  Azure DevOps API  ──►  relatorio_devops.html
              │
              └──►  Google Gemini API  (opcional — narrativa automática)
```

1. O script lê suas credenciais do `.env`
2. Consulta a API do Azure DevOps para buscar sprints, work items e métricas
3. Calcula throughput, scope increase, lead/cycle time e bugs
4. (Opcional) Envia os dados ao Gemini para gerar uma narrativa em linguagem natural
5. Salva tudo em um único arquivo HTML autocontido

---

## Pré-requisitos

- Python 3.10+
- Acesso a um projeto no Azure DevOps
- PAT (Personal Access Token) com permissão de leitura
- (Opcional) Chave da API do Google Gemini para narrativa automática

---

## Setup em 4 passos

### 1. Clone e crie o ambiente virtual

```bash
git clone <url-do-repo>
cd azuremetrics

python3 -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Configure suas variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` com os dados do seu time:

```env
# Azure DevOps — obrigatório
AZURE_DEVOPS_ORGANIZACAO=nome-da-sua-org     # ex: contoso
AZURE_DEVOPS_PROJETO=nome-do-projeto         # ex: MeuProjeto
AZURE_DEVOPS_TEAM=nome-do-time               # ex: Time Alpha
AZURE_DEVOPS_PAT=seu-pat-aqui                # Personal Access Token

# Quantas sprints analisar (padrão: 1)
AZURE_DEVOPS_NUM_SPRINTS=3

# Google Gemini — opcional (narrativa automática)
GEMINI_API_KEY=

# Abrir o relatório no navegador ao finalizar
OPEN_BROWSER=true
```

> **Onde criar o PAT?** Azure DevOps → User Settings → Personal Access Tokens → New Token. Permissões necessárias: `Work Items (Read)` e `Project and Team (Read)`.

> **Chave gratuita do Gemini:** https://aistudio.google.com/app/apikey

### 4. Execute

```bash
python main.py
```

O relatório `relatorio_devops.html` será gerado na pasta do projeto e aberto automaticamente no navegador (se `OPEN_BROWSER=true`).

---

## Replicando para outros times

Nenhuma linha de código precisa mudar. Cada time configura apenas seu próprio `.env`:

```env
AZURE_DEVOPS_ORGANIZACAO=minha-org
AZURE_DEVOPS_PROJETO=meu-projeto
AZURE_DEVOPS_TEAM=meu-time
AZURE_DEVOPS_PAT=meu-pat
```

Depois é só rodar `python main.py`. Simples assim.

---

## Segurança

- **Nunca** faça commit do `.env` ou inclua chaves diretamente no código
- O `.gitignore` já ignora `.env` e o relatório gerado
- Use PATs com escopo mínimo (princípio do menor privilégio)
- Faça rotação periódica de PATs e API Keys
- Se uma chave foi exposta, **revogue e gere uma nova imediatamente**

---

## Dependências

```
requests            — chamadas à API do Azure DevOps
google-generativeai — narrativa automática via Gemini (opcional)
python-dotenv       — carregamento do .env
```
