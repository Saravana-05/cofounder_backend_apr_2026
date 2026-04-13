# app/email_utils.py
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, html: str) -> None:
    """Low-level SMTP sender. Falls back to logging if SMTP is not configured."""
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.info("[EMAIL SKIPPED — no SMTP config] To: %s | Subject: %s", to, subject)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = settings.SMTP_FROM
    msg["To"]      = to
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            if settings.SMTP_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, to, msg.as_string())
        logger.info("Email sent to %s — %s", to, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)


# ── templates ─────────────────────────────────────────────────────────────────

def send_connect_request_email(
    *,
    to_email: str,
    to_name: str,
    from_name: str,
    match_score: float,
    app_url: str,
) -> None:
    subject = f"🤝 {from_name} wants to connect with you on Cofounders Matrimony"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;background:#07111D;color:#e2e8f0;border-radius:16px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#1565C0,#4A90D9);padding:32px;text-align:center;">
        <h1 style="margin:0;font-size:1.6rem;color:#fff;">Cofounders <span style="color:#FFD166;">Matrimony</span></h1>
        <p style="margin:8px 0 0;opacity:.8;font-size:.9rem;">STARTUP MATCHMAKING</p>
      </div>
      <div style="padding:32px;">
        <h2 style="color:#F5A623;margin-top:0;">You have a new connection request!</h2>
        <p>Hi <strong>{to_name}</strong>,</p>
        <p><strong>{from_name}</strong> wants to connect with you. Your compatibility score is
          <span style="color:#F5A623;font-weight:700;">{match_score:.0f}/100</span>.
        </p>
        <div style="text-align:center;margin:32px 0;">
          <a href="{app_url}/connections"
             style="background:linear-gradient(135deg,#F5A623,#FFD166);color:#07111D;padding:14px 32px;
                    border-radius:8px;text-decoration:none;font-weight:700;font-size:1rem;">
            View &amp; Accept Request
          </a>
        </div>
        <p style="color:#94a3b8;font-size:.85rem;">
          If you accept, you'll be able to chat directly inside the app.
        </p>
      </div>
      <div style="padding:16px 32px;border-top:1px solid rgba(255,255,255,.08);color:#64748b;font-size:.75rem;text-align:center;">
        Cofounders Matrimony · You're receiving this because someone matched with you.
      </div>
    </div>
    """
    _send(to_email, subject, html)


def send_connection_accepted_email(
    *,
    to_email: str,
    to_name: str,
    accepted_by: str,
    app_url: str,
) -> None:
    subject = f"🎉 {accepted_by} accepted your connection request!"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;background:#07111D;color:#e2e8f0;border-radius:16px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#1565C0,#4A90D9);padding:32px;text-align:center;">
        <h1 style="margin:0;font-size:1.6rem;color:#fff;">Cofounders <span style="color:#FFD166;">Matrimony</span></h1>
      </div>
      <div style="padding:32px;">
        <h2 style="color:#22C55E;margin-top:0;">Connection accepted! 🚀</h2>
        <p>Hi <strong>{to_name}</strong>,</p>
        <p><strong>{accepted_by}</strong> accepted your connection request. You can now chat with them directly inside the app.</p>
        <div style="text-align:center;margin:32px 0;">
          <a href="{app_url}/chat"
             style="background:linear-gradient(135deg,#22C55E,#4ade80);color:#07111D;padding:14px 32px;
                    border-radius:8px;text-decoration:none;font-weight:700;font-size:1rem;">
            Start Chatting
          </a>
        </div>
      </div>
    </div>
    """
    _send(to_email, subject, html)


def send_new_message_email(
    *,
    to_email: str,
    to_name: str,
    from_name: str,
    preview: str,
    app_url: str,
) -> None:
    subject = f"💬 New message from {from_name}"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:auto;background:#07111D;color:#e2e8f0;border-radius:16px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,#1565C0,#4A90D9);padding:32px;text-align:center;">
        <h1 style="margin:0;font-size:1.6rem;color:#fff;">Cofounders <span style="color:#FFD166;">Matrimony</span></h1>
      </div>
      <div style="padding:32px;">
        <h2 style="color:#4A90D9;margin-top:0;">New message from {from_name}</h2>
        <p>Hi <strong>{to_name}</strong>,</p>
        <div style="background:rgba(255,255,255,.05);border-left:3px solid #F5A623;padding:12px 16px;border-radius:0 8px 8px 0;margin:16px 0;">
          <p style="margin:0;font-style:italic;color:#cbd5e1;">"{preview[:120]}{"..." if len(preview) > 120 else ""}"</p>
        </div>
        <div style="text-align:center;margin:32px 0;">
          <a href="{app_url}/chat"
             style="background:linear-gradient(135deg,#F5A623,#FFD166);color:#07111D;padding:14px 32px;
                    border-radius:8px;text-decoration:none;font-weight:700;font-size:1rem;">
            Reply in App
          </a>
        </div>
      </div>
    </div>
    """
    _send(to_email, subject, html)