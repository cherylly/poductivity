"""Email delivery: compose and send daily digest emails."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Template

from src.config import settings

logger = logging.getLogger(__name__)

TEMPLATE_PATH = Path(__file__).parent.parent.parent / "templates" / "email_digest.html"


def render_digest_email(date: str, entries: list[dict]) -> str:
    """Render the digest email HTML from template.

    Args:
        date: Formatted date string (e.g., "Jul 3, 2026")
        entries: List of dicts with keys: id, title, url, content_type, source_name, summary
    """
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    template = Template(template_text)
    return template.render(
        date=date,
        entries=entries,
        web_base_url=settings.web_base_url,
    )


def send_email(subject: str, html_body: str) -> bool:
    """Send an HTML email via SMTP.

    Returns True on success, False on failure.
    """
    if not settings.smtp_user or not settings.smtp_pass:
        logger.error("SMTP credentials not configured")
        return False

    recipient = settings.recipient_email or settings.smtp_user

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = recipient

    # Plain text fallback
    plain_text = f"Your daily content digest is ready. View it at: {settings.web_base_url}"
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.sendmail(settings.smtp_user, [recipient], msg.as_string())
        logger.info(f"Digest email sent to {recipient}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def send_daily_digest(date: str, entries: list[dict]) -> bool:
    """Compose and send the daily digest email."""
    if not entries:
        logger.info("No entries for digest, skipping email")
        return True

    html = render_digest_email(date, entries)
    subject = f"📬 Your Daily Content Digest - {date}"
    return send_email(subject, html)
