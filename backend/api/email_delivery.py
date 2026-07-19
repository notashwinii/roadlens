import os
import smtplib
from email.message import EmailMessage


def send_email(to: str, subject: str, body: str) -> str:
    mode = os.getenv("ROADLENS_EMAIL_MODE", "console").lower()
    if mode == "console":
        print(f"[RoadLens email] to={to} subject={subject}\n{body}", flush=True)
        return "console"

    host = os.environ["ROADLENS_SMTP_HOST"]
    port = int(os.getenv("ROADLENS_SMTP_PORT", "587"))
    message = EmailMessage()
    message["From"] = os.environ["ROADLENS_EMAIL_FROM"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=15) as client:
        if os.getenv("ROADLENS_SMTP_TLS", "true").lower() in {"1", "true", "yes"}:
            client.starttls()
        username = os.getenv("ROADLENS_SMTP_USERNAME")
        if username:
            client.login(username, os.environ["ROADLENS_SMTP_PASSWORD"])
        client.send_message(message)
    return "smtp"
