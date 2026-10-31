"""Outgoing email (Phase 19): welcome emails for new accounts, password resets.

Sent over SMTP from a background task, so the HTTP answer never waits for the mail server and its
timing doesn't reveal whether an address exists. In Compose the server is Mailpit, a local inbox at
http://localhost:8025 (nothing leaves the machine). Failures are logged, never raised: a down mail server
must not break the request that sent it. The message body is never logged, because a reset link in it is a password.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("backend.mailer")


def app_url() -> str:
    """Where links in emails point: the dashboard as the user's browser reaches it."""
    return os.getenv("APP_BASE_URL", "https://localhost:8443").rstrip("/")


def send_email(to: str, subject: str, body: str) -> bool:
    """Send one plain-text email. True if the server accepted it."""
    host = os.getenv("SMTP_HOST", "")
    if not host:
        logger.warning("Email to %s not sent (%s): SMTP_HOST is not set", to, subject)
        return False
    message = EmailMessage()
    message["From"] = os.getenv("SMTP_FROM", "SmartIoT <no-reply@smartiot.local>")
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "25")), timeout=10) as smtp:
            if os.getenv("SMTP_STARTTLS") == "1":
                smtp.starttls()
            if os.getenv("SMTP_USER"):
                smtp.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("Email to %s (%s) failed: %s", to, subject, exc)
        return False
    logger.info("Email sent to %s: %s", to, subject)
    return True
