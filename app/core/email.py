# ─────────────────────────────────────────────────────────────────
# app/core/email.py
# Envio de e-mail via Gmail SMTP (TLS porta 587)
# ─────────────────────────────────────────────────────────────────
from __future__ import annotations

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_reset_code(to_email: str, user_name: str, code: str) -> bool:
    """
    Envia o código OTP de recuperação de senha via Gmail.
    Retorna True se enviado com sucesso, False caso contrário.
    """
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        logger.warning("Gmail não configurado (GMAIL_USER / GMAIL_APP_PASSWORD vazios).")
        return False

    subject = "Techá — Código de Recuperação de Senha"

    # Corpo HTML do e-mail
    html = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
</head>
<body style="margin:0;padding:0;background:#f4f7f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7f4;padding:32px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- Header verde -->
        <tr>
          <td style="background:#1a4731;padding:24px 32px;">
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;
                       letter-spacing:0.5px;">🌱 Techá</h1>
            <p style="margin:4px 0 0;color:#86efac;font-size:13px;">
              Monitoramento NDVI por Satélite
            </p>
          </td>
        </tr>

        <!-- Corpo -->
        <tr>
          <td style="padding:32px 32px 24px;">
            <p style="margin:0 0 16px;color:#1a202c;font-size:16px;">
              Olá, <strong>{user_name}</strong> 👋
            </p>
            <p style="margin:0 0 24px;color:#4a5568;font-size:14px;line-height:1.6;">
              Recebemos uma solicitação para redefinir a senha da sua conta Techá.
              Use o código abaixo no aplicativo para criar uma nova senha:
            </p>

            <!-- Código OTP em destaque -->
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

            <p style="margin:0 0 8px;color:#4a5568;font-size:13px;line-height:1.6;">
              Se você não solicitou a redefinição de senha, ignore este e-mail.
              Sua senha permanecerá a mesma.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;padding:20px 32px;
                     border-top:1px solid #e5e7eb;">
            <p style="margin:0;color:#9ca3af;font-size:11px;text-align:center;">
              Techá by InnovAgro &nbsp;|&nbsp;
              Monitoramento de lavouras por satélite &nbsp;|&nbsp;
              Este é um e-mail automático, não responda.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    # Corpo texto simples (fallback)
    text = (
        f"Olá, {user_name}!\n\n"
        f"Seu código de recuperação de senha Techá: {code}\n\n"
        f"Válido por {settings.RESET_CODE_TTL_MINUTES} minutos.\n\n"
        f"Se não foi você, ignore este e-mail.\n\n"
        f"— Techá by InnovAgro"
    )

    try:
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

        logger.info(f"E-mail de recuperação enviado para {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("Gmail: falha de autenticação — verifique GMAIL_USER e GMAIL_APP_PASSWORD")
        return False
    except smtplib.SMTPException as exc:
        logger.error(f"Gmail SMTP error: {exc}")
        return False
    except Exception as exc:
        logger.error(f"Erro inesperado ao enviar e-mail: {exc}")
        return False


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
    if not settings.GMAIL_USER or not settings.GMAIL_APP_PASSWORD:
        logger.warning("Gmail não configurado — alerta de anomalia não enviado por e-mail.")
        return False

    subject = f"Techá — Alerta de Anomalia: {field_name}"

    html = f"""
<!DOCTYPE html>
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
            <p style="margin:4px 0 0;color:#fca5a5;font-size:13px;">
              Anomalia detectada por satélite
            </p>
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
                <td style="color:#6b7280;font-size:13px;border-bottom:1px solid #fee2e2;">
                  Fazenda
                </td>
                <td style="color:#1a202c;font-size:13px;font-weight:600;
                           text-align:right;border-bottom:1px solid #fee2e2;">
                  {farm_name}
                </td>
              </tr>
              <tr>
                <td style="color:#6b7280;font-size:13px;border-bottom:1px solid #fee2e2;">
                  Talhão
                </td>
                <td style="color:#1a202c;font-size:13px;font-weight:600;
                           text-align:right;border-bottom:1px solid #fee2e2;">
                  {field_name}
                </td>
              </tr>
              <tr>
                <td style="color:#6b7280;font-size:13px;border-bottom:1px solid #fee2e2;">
                  Queda de NDVI
                </td>
                <td style="color:#dc2626;font-size:16px;font-weight:700;
                           text-align:right;border-bottom:1px solid #fee2e2;">
                  {ndvi_drop_pct:.1f}%
                </td>
              </tr>
              <tr>
                <td style="color:#6b7280;font-size:13px;">Área afetada</td>
                <td style="color:#dc2626;font-size:14px;font-weight:600;text-align:right;">
                  {affected_area_ha:.1f} ha
                </td>
              </tr>
            </table>

            <p style="margin:0 0 8px;color:#4a5568;font-size:13px;line-height:1.6;">
              Abra o aplicativo Techá para visualizar o mapa da anomalia,
              confirmar no campo e gerar o relatório completo.
            </p>
          </td>
        </tr>

        <tr>
          <td style="background:#f9fafb;padding:20px 32px;border-top:1px solid #e5e7eb;">
            <p style="margin:0;color:#9ca3af;font-size:11px;text-align:center;">
              Techá by InnovAgro &nbsp;|&nbsp; ID Anomalia: {anomaly_id[:8]}... &nbsp;|&nbsp;
              Este é um e-mail automático, não responda.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""

    text = (
        f"Alerta Techá — {user_name}\n\n"
        f"Anomalia detectada em {field_name} ({farm_name})\n"
        f"Queda de NDVI: {ndvi_drop_pct:.1f}%\n"
        f"Área afetada: {affected_area_ha:.1f} ha\n\n"
        f"Abra o app para ver o mapa e confirmar no campo.\n"
        f"ID Anomalia: {anomaly_id}\n\n"
        f"— Techá by InnovAgro"
    )

    try:
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

        logger.info(f"E-mail de anomalia enviado para {to_email} (anomalia {anomaly_id[:8]})")
        return True

    except Exception as exc:
        logger.error(f"Erro ao enviar e-mail de anomalia: {exc}")
        return False
