# Vigia de notícias de política

Agente que acompanha as editorias de política dos principais veículos e, poucos minutos depois de uma matéria sair, manda ao Telegram a manchete, o link e três comentários prontos (técnico, político e humano) na voz de Marco Martins.

O agente não publica nada. Quem revisa e posta é você. A velocidade vem do alerta: o site costuma publicar antes ou junto com o post nas redes, então o rascunho chega quando o post ainda está nascendo.

## Como funciona

1. A cada 60 segundos, o agente lê os feeds listados em `fontes.toml`.
2. Cada notícia nova, de até 20 minutos, vai para o Claude, que decide se ela tem aderência ao sustentabilismo progressista.
3. Se tiver, o Claude escreve três comentários seguindo `voz.md`.
4. O Telegram recebe a mensagem. Tocar no comentário copia o texto. Depois é só abrir o post, colar e publicar.

## Instalação

```bash
pip install -r requirements.txt
cp .env.example .env
```

Preencha o `.env`:

- `ANTHROPIC_API_KEY`: chave criada em platform.claude.com.
- `TELEGRAM_BOT_TOKEN`: no Telegram, fale com o @BotFather, envie `/newbot` e copie o token.
- `TELEGRAM_CHAT_ID`: mande qualquer mensagem ao seu bot e abra `https://api.telegram.org/bot<TOKEN>/getUpdates`. O número em `"chat":{"id":...}` é o seu chat.

## Uso

```bash
python agente.py --teste   # gera comentários para uma notícia de exemplo e imprime no terminal
python agente.py           # começa a vigiar
```

Para funcionar o tempo todo, o agente precisa rodar num computador sempre ligado ou num servidor barato.

## Ajustes

- **Fontes:** edite `fontes.toml`. Confira se cada endereço de feed ainda responde, porque os veículos mudam essas URLs sem aviso.
- **Tom e regras:** edite `voz.md`. É ali que ficam o conceito, o estilo e as proibições (não inventar dados, não usar travessão, não fazer autopromoção).
- **Frequência:** `intervalo_segundos` e `idade_maxima_minutos` em `fontes.toml`.
