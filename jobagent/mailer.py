"""Envio de candidatura por e-mail via Gmail (SMTP + senha de app). Só roda com sua confirmação."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Optional


def build_message(to: str, subject: str, body: str, sender: str, attachments: list[Path]) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.set_content(body)
    for p in attachments:
        if p.exists():
            subtype = "pdf" if p.suffix.lower() == ".pdf" else "octet-stream"
            msg.add_attachment(p.read_bytes(), maintype="application", subtype=subtype, filename=p.name)
    return msg


def send(to: str, subject: str, body: str, attachments: Optional[list[Path]] = None) -> None:
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        raise RuntimeError("Defina GMAIL_ADDRESS e GMAIL_APP_PASSWORD no .env para enviar e-mails.")
    msg = build_message(to, subject, body, sender, attachments or [])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(sender, password)
        s.send_message(msg)
