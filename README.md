# Agente de busca e candidatura a vagas

Agente pessoal que **procura vagas todos os dias**, **dá uma nota de aderência** a cada uma com
base no seu perfil e CV, e **prepara a candidatura** (carta, e-mail, respostas de formulário) no
idioma da vaga. O envio é **semi-automático**: nada sai sem você revisar e confirmar.

Ajustado para: política climática e ambiental, adaptação urbana, Soluções Baseadas na Natureza,
justiça climática, advocacy, comunicação estratégica e articulação institucional. Cargos de Program
Lead, Policy/Advocacy Manager e Strategic Communications Lead em organizações internacionais,
fundações e ONGs. São Paulo, Brasília, remoto, híbrido em SP ou curta duração em outros locais.

## Como funciona

```
fontes ──► pré-filtro ──► banco local ──► nota do Claude ──► candidatura pronta ──► você revisa ──► envio
(web/Gupy/   (sem IA:      (sem          (0-100, pontos     (carta, e-mail,        (`apply`)       (e-mail ou
 ReliefWeb/   estágio,      duplicatas)   fortes, lacunas)   respostas)                             formulário)
 Greenhouse/  vencidas…)
 Lever)
```

| Fonte | O que cobre |
|---|---|
| **Busca na web (Claude)** | Google, LinkedIn, Indeed, Devex, Impactpool, UNjobs, Climatebase, Idealist, Vagas.com, Catho, sites de fundações. O Claude busca e só lista vagas que viu de fato. |
| **Gupy** | API pública do portal Gupy (muitas ONGs e empresas brasileiras). |
| **ReliefWeb** | Vagas da ONU, cooperação internacional e ONGs. Exige um `appname` aprovado. |
| **Greenhouse / Lever** | Quadros de vagas de organizações específicas que você listar. |

LinkedIn e Indeed proíbem robôs nos termos de uso. Por isso o agente **não faz login nem se
candidata por lá**: ele encontra as vagas via busca e você conclui a candidatura no site.

## Instalação

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # coloque sua ANTHROPIC_API_KEY
cp cv/cv.example.md cv/cv.md      # cole seu CV completo em texto
# opcional: salve seu CV em PDF em cv/cv.pdf (vai anexo nos e-mails)
```

Revise `config/profile.yaml` (nome, idiomas, senioridade) e `config/search.yaml` (consultas,
nota mínima, organizações a acompanhar).

## Uso

```bash
python -m jobagent run                 # rotina completa: busca + nota + candidaturas + relatório
python -m jobagent list --min-score 70 # vagas ranqueadas
python -m jobagent show <id>           # detalhes e justificativa da nota
python -m jobagent prepare <id>        # gerar a candidatura de uma vaga específica
python -m jobagent apply <id>          # revisar e enviar (pede confirmação)
python -m jobagent status <id> interview --note "entrevista 20/11"
```

- O relatório do dia fica em `output/relatorio-AAAA-MM-DD.md`.
- Cada candidatura fica em `output/applications/<id>/candidatura.md` (e `carta.md`).
- `apply`: se a vaga aceita **e-mail**, mostra o texto e só envia depois do seu "s" (via Gmail com
  senha de app, CV em PDF anexo). Se for **formulário/site**, abre o link e você usa as respostas
  prontas. Depois, a vaga é marcada como `applied`.

## Rodar sozinho todo dia (GitHub Actions)

O arquivo `.github/workflows/daily.yml` roda `python -m jobagent run` em dias úteis às 07:17
(horário de Brasília) e guarda o relatório e as candidaturas como *artifact* da execução.
Em **Settings → Secrets and variables → Actions**, crie:

- `ANTHROPIC_API_KEY`
- `CV_MARKDOWN`: o texto completo do seu CV (assim ele não fica no repositório)
- `RELIEFWEB_APPNAME` (opcional)

Mantenha o repositório **privado**: os relatórios trazem dados do seu perfil.

## Custos e privacidade

- Usa o modelo `claude-opus-5-5`. O perfil e o CV ficam em cache entre as chamadas, o que barateia
  o ranqueamento. `max_jobs_to_score` e `max_searches` limitam o gasto por execução.
- `cv/cv.md`, `cv/*.pdf`, `.env`, `data/` e `output/` estão no `.gitignore`.
- O agente é instruído a **nunca inventar** experiência. Campos que ele não conhece (pretensão
  salarial, por exemplo) saem como `[PREENCHER]`. Revise sempre antes de enviar.

## Testes

```bash
pip install pytest && python -m pytest -q   # sem rede: simulam a API e as fontes
```
