# ─────────────────────────────────────────────────────────────────
# app/core/email.py
# Envio de e-mail via Resend HTTP API (primary) ou Gmail SMTP (fallback)
# Railway bloqueia porta 587/SMTP — usar Resend resolve isso.
# ─────────────────────────────────────────────────────────────────
from __future__ import annotations

import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Template helpers ──────────────────────────────────────────────

def _reset_html(user_name: str, code: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0"/></head>
<body style="margin:0;padding:0;background:#f4f7f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7f4;padding:32px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:#1a4731;padding:24px 32px;">
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:0.5px;">
              🌱 Techá
            </h1>
            <p style="margin:4px 0 0;color:#86efac;font-size:13px;">Monitoramento NDVI por Satélite</p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px 32px 24px;">
            <p style="margin:0 0 16px;color:#1a202c;font-size:16px;">
              Olá, <strong>{user_name}</strong> 👋
            </p>
            <p style="margin:0 0 24px;color:#4a5568;font-size:14px;line-height:1.6;">
              Recebemos uma solicitação para redefinir a senha da sua conta Techá.
              Use o código abaixo no aplicativo para criar uma nova senha:
            </p>
            <div style="text-align:center;margin:0 0 28px;">
              <div style="display:inline-block;background:#f0fdf4;border:2px solid #16a34a;
                          border-radius:12px;padding:20px 40px;">
                <span style="font-size:40px;font-weight:700;letter-spacing:10px;
                             color:#15803d;font-family:monospace;">{code}</span>
              </div>
              <p style="margin:12px 0 0;color:#6b7280;font-size:12px;">
                ⏱️ Este código expira em <strong>{settings.RESET_CODE_TTL_MINUTES} minutos</strong>
              </p>
            </div>
            <p style="margin:0;color:#4a5568;font-size:13px;line-height:1.6;">
              Se você não solicitou a redefinição de senha, ignore este e-mail.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f9fafb;padding:20px 32px;border-top:1px solid #e5e7eb;">
            <p style="margin:0;color:#9ca3af;font-size:11px;text-align:center;">
              Techá by InnovAgro &nbsp;|&nbsp; Monitoramento de lavouras por satélite &nbsp;|&nbsp;
              Este é um e-mail automático, não responda.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _reset_text(user_name: str, code: str) -> str:
    return (
        f"Olá, {user_name}!\n\n"
        f"Seu código de recuperação de senha Techá: {code}\n\n"
        f"Válido por {settings.RESET_CODE_TTL_MINUTES} minutos.\n\n"
        f"Se não foi você, ignore este e-mail.\n\n"
        f"— Techá by InnovAgro"
    )


def _anomaly_html(
    user_name: str,
    farm_name: str,
    field_name: str,
    ndvi_drop_pct: float,
    affected_area_ha: float,
    anomaly_id: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f7f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7f4;padding:32px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:#7f1d1d;padding:24px 32px;">
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;">&#9888; Alerta Techá</h1>
            <p style="margin:4px 0 0;color:#fca5a5;font-size:13px;">Anomalia detectada por satélite</p>
          </td>
        </tr>
        <tr>
          <td style="padding:32px 32px 24px;">
            <p style="margin:0 0 16px;color:#1a202c;font-size:16px;">
              Olá, <strong>{user_name}</strong> 👋
            </p>
            <p style="margin:0 0 24px;color:#4a5568;font-size:14px;line-height:1.6;">
              O sistema Techá detectou uma <strong>anomalia de vigor vegetativo</strong>
              no seu talhão via imagem Sentinel-2.
            </p>
            <table width="100%" cellpadding="12" cellspacing="0"
                   style="background:#fef2f2;border-radius:8px;margin:0 0 24px;">
              <tr>
                <td style="color:#6b7280;font-size:13px;border-bottom:1px solid #fee2e2;">Fazenda</td>
                <td style="color:#1a202c;font-size:13px;font-weight:600;
                           text-align:right;border-bottom:1px solid #fee2e2;">{farm_name}</td>
              </tr>
              <tr>
                <td style="color:#6b7280;font-size:13px;border-bottom:1px solid #fee2e2;">Talhão</td>
                <td style="color:#1a202c;font-size:13px;font-weight:600;
                           text-align:right;border-bottom:1px solid #fee2e2;">{field_name}</td>
              </tr>
              <tr>
                <td style="color:#6b7280;font-size:13px;border-bottom:1px solid #fee2e2;">Queda de NDVI</td>
                <td style="color:#dc2626;font-size:16px;font-weight:700;
                           text-align:right;border-bottom:1px solid #fee2e2;">{ndvi_drop_pct:.1f}%</td>
              </tr>
              <tr>
                <td style="color:#6b7280;font-size:13px;">Área afetada</td>
                <td style="color:#dc2626;font-size:14px;font-weight:600;
                           text-align:right;">{affected_area_ha:.1f} ha</td>
              </tr>
            </table>
            <p style="margin:0;color:#4a5568;font-size:13px;line-height:1.6;">
              Abra o aplicativo Techá para visualizar o mapa, confirmar no campo e gerar o relatório.
            </p>
          </td>
        </tr>
        <tr>
          <td style="background:#f9fafb;padding:20px 32px;border-top:1px solid #e5e7eb;">
            <p style="margin:0;color:#9ca3af;font-size:11px;text-align:center;">
              Techá by InnovAgro &nbsp;|&nbsp; ID: {anomaly_id[:8]}... &nbsp;|&nbsp;
              Este é um e-mail automático, não responda.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


# ── Resend (HTTP API) ─────────────────────────────────────────────

def _send_via_resend(to_email: str, subject: str, html: str, text: str) -> bool:
    """Envia via Resend HTTP API. Funciona no Railway (sem restrição de porta)."""
    if not settings.RESEND_API_KEY:
        return False
    try:
        import resend as _resend
        _resend.api_key = settings.RESEND_API_KEY
        _resend.Emails.send({
            "from": f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM_ADDRESS}>",
            "to": [to_email],
            "subject": subject,
            "html": html,
            "text": text,
        })
        return True
    except Exception as exc:
        logger.error(f"Resend error: {exc}")
        return False


# ── Gmail SMTP (fallback local) ───────────────────────────────────

def _send_via_smtp(to_email: str, subject: str, html: str, text: str) -> bool:
    """Fallback SMTP para desenvolvimento local. Railway bloqueia porta 587."""
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        return False
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{settings.EMAIL_FROM_NAME} <{settings.GMAIL_USER}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html",  "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
            smtp.sendmail(settings.GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as exc:
        logger.error(f"Gmail SMTP error: {exc}")
        return False


def _send(to_email: str, subject: str, html: str, text: str) -> bool:
    """Tenta Resend primeiro; cai no SMTP se não houver API key."""
    if settings.RESEND_API_KEY:
        ok = _send_via_resend(to_email, subject, html, text)
        if ok:
            logger.info(f"[Resend] e-mail enviado → {to_email}")
            return True
        logger.warning("[Resend] falhou — tentando SMTP...")
    return _send_via_smtp(to_email, subject, html, text)


# ── Funções públicas ─────────────────────────────────────────────

def send_reset_code(to_email: str, user_name: str, code: str) -> bool:
    """
    Envia o código OTP de recuperação de senha.
    Usa Resend se RESEND_API_KEY estiver configurado, senão tenta Gmail SMTP.
    """
    subject = "Techá — Código de Recuperação de Senha"
    html = _reset_html(user_name, code)
    text = _reset_text(user_name, code)
    return _send(to_email, subject, html, text)


def send_anomaly_alert(
    to_email: str,
    user_name: str,
    farm_name: str,
    field_name: str,
    ndvi_drop_pct: float,
    affected_area_ha: float,
    anomaly_id: str,
) -> bool:
    """
    Envia e-mail de alerta quando uma anomalia é detectada no talhão.
    """
    subject = f"Techá — Alerta de Anomalia: {field_name}"
    html = _anomaly_html(user_name, farm_name, field_name, ndvi_drop_pct, affected_area_ha, anomaly_id)
    text = (
        f"Alerta Techá — {user_name}\n\n"
        f"Anomalia detectada em {field_name} ({farm_name})\n"
        f"Queda de NDVI: {ndvi_drop_pct:.1f}%\n"
        f"Área afetada: {affected_area_ha:.1f} ha\n\n"
        f"Abra o app para ver o mapa e confirmar no campo.\n"
        f"ID Anomalia: {anomaly_id}\n\n"
        f"— Techá by InnovAgro"
    )
    return _send(to_email, subject, html, text)
