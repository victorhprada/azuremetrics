# DevOps Dashboard

O Azure DevOps é uma ferramenta poderosa — mas só para quem tem acesso a ela.

Times de desenvolvimento vivem com esse atrito todo dia: o restante da empresa quer saber o que está sendo entregue, qual o status das demandas, se o time está saudável — mas não tem como ver. Criar um relatório manualmente a cada sprint consome tempo, fica desatualizado em horas e ainda exige que quem recebe entenda o vocabulário técnico da ferramenta.

Este projeto resolve isso automaticamente.

---

## As duas dores que resolvemos

**1. Falta de visibilidade para quem não usa o Azure DevOps**

Stakeholders, produto, gestão e outras áreas precisam saber o que o time está fazendo — mas não têm acesso ao Azure DevOps e não sabem navegar nele. O resultado é uma cadeia de perguntas, prints de tela e reuniões que poderiam ser evitadas.

**Solução:** uma Status Page pública com o kanban da sprint atual, datas de início e fim, progresso e busca por demanda — atualizada automaticamente, sem login, sem treinamento.

**2. Falta de métricas consolidadas para o próprio time**

Montar um relatório de sprint com throughput, scope increase, cycle time e análise de bugs manualmente é trabalhoso e propenso a erro. E ainda precisa de alguém pra interpretar os dados e transformar em narrativa.

**Solução:** um Relatório de Métricas gerado em segundos a partir da API do Azure DevOps, com gráficos interativos e narrativa automática em português via Google Gemini.

---

## O que o projeto entrega

Dois dashboards acessíveis pelo mesmo servidor, com navegação integrada e visual padronizado:

### Status Page `/`
Visão do dia a dia para toda a empresa.

| O que mostra | Para quem |
|---|---|
| Sprint atual com datas de início e fim | Qualquer pessoa da empresa |
| Progresso da sprint (tempo e itens concluídos) | Gestão, produto, stakeholders |
| Kanban: A Fazer / Em Andamento / Concluído | Time e liderança |
| Busca por título, #ID ou responsável | Qualquer pessoa |

### Relatório de Métricas `/metrics`
Visão analítica para o time e liderança técnica.

| Métrica | O que mede |
|---|---|
| **Throughput** | Itens entregues por sprint |
| **Scope Increase** | Itens adicionados após o início da sprint |
| **Bugs abertos / fechados** | Saúde da qualidade |
| **Lead Time / Cycle Time** | Velocidade de entrega (mediana e P85) |
| **Narrativa automática** | Análise em português gerada pelo Google Gemini |

---

## Como funciona

```
.env
 ├── Azure DevOps API ──► Status Page     (/)
 └── Azure DevOps API ──► Relatório       (/metrics)
                               └── Gemini API  (narrativa — opcional)
```

Tudo sobe com um único comando. O servidor busca os dados em tempo real a cada acesso.

---

## Pré-requisitos

- Python 3.10+
- Acesso a um projeto no Azure DevOps
- PAT com permissão de leitura (`Work Items` e `Project and Team`)
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

### 3. Configure o `.env`

```bash
cp .env.example .env
```

```env
# Azure DevOps — obrigatório
AZURE_DEVOPS_ORGANIZACAO=nome-da-sua-org
AZURE_DEVOPS_PROJETO=nome-do-projeto
AZURE_DEVOPS_TEAM=nome-do-time
AZURE_DEVOPS_PAT=seu-pat-aqui

# Quantas sprints analisar no relatório de métricas (padrão: 1)
AZURE_DEVOPS_NUM_SPRINTS=3

# Google Gemini — opcional (narrativa automática no relatório)
GEMINI_API_KEY=

# Abrir no navegador ao gerar arquivos HTML locais
OPEN_BROWSER=true

# Título exibido na Status Page
STATUS_PAGE_TITLE=Status da Sprint — Meu Time
```

> **Onde criar o PAT?** Azure DevOps → User Settings → Personal Access Tokens → New Token.
> Permissões mínimas: `Work Items (Read)` e `Project and Team (Read)`.

> **Chave gratuita do Gemini:** https://aistudio.google.com/app/apikey

### 4. Suba o servidor

```bash
python app.py
```

Acesse `http://localhost:5000` — as duas páginas já estão disponíveis com navegação entre elas.

---

## Deploy na Vercel (hospedagem gratuita)

1. Suba o código para o GitHub
2. Acesse [vercel.com](https://vercel.com) → New Project → importe o repositório
3. **Antes ou depois do primeiro deploy**, abra o projeto → **Settings → Environment Variables** e crie **as mesmas chaves do seu `.env` local** (o arquivo `.env` **não** sobe no Git e a Vercel **não** lê o `.env` da sua máquina):
   - `AZURE_DEVOPS_PAT`
   - `AZURE_DEVOPS_ORGANIZACAO`
   - `AZURE_DEVOPS_PROJETO`
   - `AZURE_DEVOPS_TEAM`
   - (opcional) `GEMINI_API_KEY`, `AZURE_DEVOPS_NUM_SPRINTS`, `STATUS_PAGE_TITLE`, `OPEN_BROWSER`
4. Para cada variável, marque os ambientes em que ela vale (**Production**, **Preview**, **Development**). Se marcar só Production, deploys de branch (Preview) podem falhar.
5. **Redeploy** após salvar: **Deployments** → menu **⋯** no último deploy → **Redeploy** (ou faça um commit novo).

Via CLI (na pasta do projeto), você pode adicionar uma a uma, por exemplo:

```bash
vercel env add AZURE_DEVOPS_PAT
```

Repita para as demais; depois `vercel --prod` ou redeploy no painel.

A Vercel detecta o `vercel.json` automaticamente. A URL gerada pode ser compartilhada com toda a empresa — sem VPN, sem login, sem configuração adicional.

---

## Replicando para outros times

Nenhuma linha de código precisa mudar. Cada time usa seu próprio `.env`:

```env
AZURE_DEVOPS_ORGANIZACAO=minha-org
AZURE_DEVOPS_PROJETO=meu-projeto
AZURE_DEVOPS_TEAM=meu-time
AZURE_DEVOPS_PAT=meu-pat
```

---

## Segurança

- **Nunca** faça commit do `.env` ou inclua chaves diretamente no código
- O `.gitignore` já ignora `.env` e os arquivos HTML gerados
- O workflow **Secret scan (Gitleaks)** (`.github/workflows/gitleaks.yml`) roda em push/PR e ajuda a bloquear commits com segredos acidentais
- Localmente: `brew install gitleaks` e `gitleaks detect --source . --verbose`
- Use PATs com escopo mínimo (princípio do menor privilégio)
- Faça rotação periódica de PATs e API Keys
- Se uma chave foi exposta, **revogue e gere uma nova imediatamente**

---

## Estrutura do projeto

```
azuremetrics/
├── .github/
│   └── workflows/
│       └── gitleaks.yml  # varredura de segredos no CI
├── app.py              # Servidor Flask (/ e /metrics)
├── main.py             # Relatório de métricas (CLI ou via Flask)
├── status_page.py      # Status Page (CLI ou via Flask)
├── azure_client.py     # Cliente HTTP compartilhado para a API do Azure DevOps
├── templates/
│   ├── base.html       # Layout base: design tokens, navegação
│   ├── status_page.html
│   └── metrics.html
├── .env.example
├── requirements.txt
└── vercel.json
```
