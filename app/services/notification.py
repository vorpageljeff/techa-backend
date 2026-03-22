# ─────────────────────────────────────────────────────────────────
# app/services/notification.py
# Notificações push via Firebase Cloud Messaging (FCM)
# Fallback gracioso se firebase-service-account.json não existir
# ─────────────────────────────────────────────────────────────────

import os
from loguru import logger

# Inicializado uma única vez no processo
_firebase_initialized = False


def _init_firebase() -> bool:
    """Inicializa o Firebase Admin SDK se ainda não foi feito. Retorna True se OK."""
    global _firebase_initialized
    if _firebase_initialized:
        return True

    creds_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
    if not creds_path or not os.path.exists(creds_path):
        logger.warning(
            f"FCM desativado — arquivo de credenciais não encontrado: '{creds_path}'. "
            "Defina FIREBASE_CREDENTIALS_PATH no .env para ativar push notifications."
        )
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred)

        _firebase_initialized = True
        logger.info("Firebase Admin SDK inicializado com sucesso.")
        return True
    except Exception as exc:
        logger.error(f"Falha ao inicializar Firebase: {exc}")
        return False


async def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> bool:
    """
    Envia uma notificação push via FCM.

    Returns:
        True se enviado com sucesso, False se FCM não configurado ou erro.
    """
    if not fcm_token or not fcm_token.strip():
        logger.debug("FCM token ausente — notificação ignorada.")
        return False

    if not _init_firebase():
        logger.info(f"[FCM simulado] Para: {fcm_token[:20]}... | {title}: {body}")
        return False

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=fcm_token,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=1)
                )
            ),
        )
        response = messaging.send(message)
        logger.info(f"FCM enviado: message_id={response} | token={fcm_token[:20]}...")
        return True

    except Exception as exc:
        logger.error(f"Erro ao enviar FCM para {fcm_token[:20]}...: {exc}")
        return False


async def notify_anomaly(
    fcm_token: str,
    farm_name: str,
    field_name: str,
    ndvi_drop_pct: float,
    anomaly_id: str,
) -> bool:
    """Notificação padrão de anomalia detectada no talhão."""
    return await send_push_notification(
        fcm_token=fcm_token,
        title=f"Alerta Techá — {farm_name}",
        body=f"Anomalia em {field_name}: queda de {ndvi_drop_pct:.0f}% no vigor vegetativo.",
        data={
            "type": "anomaly",
            "anomaly_id": anomaly_id,
            "field_name": field_name,
        },
    )
