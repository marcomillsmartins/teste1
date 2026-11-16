"""Vigia notícias de política e manda ao Telegram rascunhos de comentário.

O agente não publica nada. Ele lê os feeds, decide com o Claude se a notícia
tem aderência ao sustentabilismo progressista e, quando tem, envia a manchete,
o link e três comentários prontos para Marco revisar e postar.

Uso:
    python agente.py            # roda em loop
    python agente.py --teste    # processa uma notícia de exemplo e imprime no terminal
"""

import argparse
import calendar
import html
import json
import os
import sqlite3
import sys
import time
import tomllib
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import anthropic
import feedparser
from pydantic import BaseModel, Field

PASTA = Path(__file__).parent
MODELO = "claude-opus-5-5"


class Comentario(BaseModel):
    tom: Literal["técnico", "político", "humano"]
    texto: str


class Analise(BaseModel):
    relevante: bool = Field(description="Vale Marco comentar esta notícia?")
    pilar: str = Field(description="Pilar do sustentabilismo progressista mais ligado ao caso, ou vazio")
    motivo: str = Field(description="Uma frase explicando por que vale ou não vale comentar")
    comentarios: list[Comentario] = Field(description="Três rascunhos, um por tom; vazio se não for relevante")


def carregar_env():
    arquivo = PASTA / ".env"
    if not arquivo.exists():
        return
    for linha in arquivo.read_text().splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


def abrir_banco():
    banco = sqlite3.connect(PASTA / "vistos.db")
    banco.execute("CREATE TABLE IF NOT EXISTS vistos (link TEXT PRIMARY KEY, quando REAL)")
    return banco


def noticias_novas(fontes, idade_maxima, banco):
    agora = time.time()
    novas = []
    for fonte in fontes:
        feed = feedparser.parse(fonte["url"])
        if feed.bozo and not feed.entries:
            print(f"[aviso] não consegui ler {fonte['nome']}: {feed.bozo_exception}", file=sys.stderr)
            continue
        for item in feed.entries:
            link = item.get("link")
            data = item.get("published_parsed") or item.get("updated_parsed")
            if not link or not data:
                continue
            if agora - calendar.timegm(data) > idade_maxima * 60:
                continue
            if banco.execute("SELECT 1 FROM vistos WHERE link = ?", (link,)).fetchone():
                continue
            banco.execute("INSERT INTO vistos VALUES (?, ?)", (link, agora))
            novas.append({
                "fonte": fonte["nome"],
                "titulo": item.get("title", ""),
                "resumo": item.get("summary", ""),
                "link": link,
            })
    banco.commit()
    return novas


def analisar(cliente, voz, noticia):
    pedido = (
        "Notícia publicada agora há pouco:\n\n"
        f"Veículo: {noticia['fonte']}\n"
        f"Título: {noticia['titulo']}\n"
        f"Resumo: {html.unescape(noticia['resumo'])[:2000]}\n\n"
        "Decida se Marco deve comentar. É relevante quando a notícia toca clima, meio ambiente, "
        "cidades, moradia, mobilidade, desigualdade, direitos, democracia, participação social, "
        "juventude ou a disputa política em torno desses temas, e quando ele tem algo próprio a "
        "acrescentar. Fofoca política, bastidor sem consequência pública e esporte não são relevantes.\n\n"
        "Se for relevante, escreva três comentários, um em cada tom: técnico, político e humano."
    )
    resposta = cliente.beta.messages.parse(
        model=MODELO,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low"},
        system=[{"type": "text", "text": voz, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": pedido}],
        output_format=Analise,
    )
    if resposta.stop_reason == "refusal" or resposta.parsed_output is None:
        return None
    return resposta.parsed_output


def formatar(noticia, analise):
    # No Telegram, tocar num bloco <code> copia o texto inteiro.
    partes = [
        f"<b>{html.escape(noticia['titulo'])}</b>",
        f"{html.escape(noticia['fonte'])} · {html.escape(noticia['link'])}",
        f"<i>{html.escape(analise.motivo)}</i>",
    ]
    for c in analise.comentarios:
        partes.append(f"<b>{c.tom.capitalize()}</b>\n<code>{html.escape(c.texto)}</code>")
    return "\n\n".join(partes)


def enviar_telegram(texto):
    url = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage"
    dados = urllib.parse.urlencode({
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    with urllib.request.urlopen(url, data=dados, timeout=15) as r:
        return json.load(r)["ok"]


def processar(cliente, voz, noticia, terminal):
    try:
        analise = analisar(cliente, voz, noticia)
    except anthropic.APIError as erro:
        print(f"[erro] Claude falhou em '{noticia['titulo']}': {erro}", file=sys.stderr)
        return
    if analise is None or not analise.relevante or not analise.comentarios:
        print(f"[ignorada] {noticia['titulo']}")
        return
    mensagem = formatar(noticia, analise)
    if terminal:
        print(mensagem, end="\n\n")
    else:
        enviar_telegram(mensagem)
        print(f"[enviada] {noticia['titulo']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--teste", action="store_true", help="processa uma notícia de exemplo e imprime no terminal")
    args = parser.parse_args()

    carregar_env()
    cliente = anthropic.Anthropic()
    voz = (PASTA / "voz.md").read_text()

    if args.teste:
        exemplo = {
            "fonte": "Exemplo",
            "titulo": "Câmara aprova projeto que flexibiliza licenciamento ambiental para obras urbanas",
            "resumo": "Texto segue para o Senado. Ambientalistas dizem que a mudança reduz a análise de impacto "
                      "em áreas sujeitas a enchentes; relator afirma que a medida destrava investimentos.",
            "link": "https://exemplo.com/noticia",
        }
        processar(cliente, voz, exemplo, terminal=True)
        return

    config = tomllib.loads((PASTA / "fontes.toml").read_text())
    banco = abrir_banco()
    print(f"Vigiando {len(config['fonte'])} fontes a cada {config['intervalo_segundos']}s.")
    with ThreadPoolExecutor(max_workers=4) as pool:
        while True:
            for noticia in noticias_novas(config["fonte"], config["idade_maxima_minutos"], banco):
                pool.submit(processar, cliente, voz, noticia, False)
            time.sleep(config["intervalo_segundos"])


if __name__ == "__main__":
    main()
