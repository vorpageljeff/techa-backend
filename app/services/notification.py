# ─────────────────────────────────────────────────────────────────
# app/services/notification.py
# Notificações push via Firebase Cloud Messaging (FCM)
# Fallback gracioso se firebase-service-account.json não existir
# ─────────────────────────────────────────────────────────────────

import os
import json
import base64
import httpx
from loguru import logger

# Inicializado uma única vez no processo
_firebase_initialized = False


def _init_firebase() -> bool:
    """Inicializa o Firebase Admin SDK. Suporta arquivo local ou base64 via env var."""
    global _firebase_initialized
    if _firebase_initialized:
        return True

    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_initialized = True
            return True

        # Opção 1: base64 via env var (produção / Railway)
        b64 = os.getenv("FIREBASE_CREDENTIALS_BASE64", "")
        if b64:
            cred_dict = json.loads(base64.b64decode(b64).decode())
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info("Firebase inicializado via FIREBASE_CREDENTIALS_BASE64.")
            return True

        # Opção 2: arquivo local (desenvolvimento)
        creds_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "")
        if creds_path and os.path.exists(creds_path):
            cred = credentials.Certificate(creds_path)
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info("Firebase inicializado via arquivo local.")
            return True

        logger.warning("FCM desativado — configure FIREBASE_CREDENTIALS_BASE64 ou FIREBASE_CREDENTIALS_PATH.")
        return False

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

    token = fcm_token.strip()
    if token.startswith(("ExponentPushToken[", "ExpoPushToken[")):
        return await _send_expo_push(token, title, body, data)

    if not _init_firebase():
        logger.info(f"[FCM simulado] Para: {token[:20]}... | {title}: {body}")
        return False

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=1)
                )
            ),
        )
        response = messaging.send(message)
        logger.info(f"FCM enviado: message_id={response} | token={token[:20]}...")
        return True

    except Exception as exc:
        logger.error(f"Erro ao enviar FCM para {token[:20]}...: {exc}")
        return False


async def _send_expo_push(
    expo_token: str,
    title: str,
    body: str,
    data: dict | None = None,
) -> bool:
    payload = {
        "to": expo_token,
        "title": title,
        "body": body,
        "sound": "default",
        "priority": "high",
        "data": {k: str(v) for k, v in (data or {}).items()},
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://exp.host/--/api/v2/push/send",
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "Content-Type": "application/json",
                },
            )
        response.raise_for_status()
        result = response.json()
        if result.get("data", {}).get("status") == "ok":
            logger.info(f"Expo push enviado | token={expo_token[:24]}...")
            return True
        logger.error(f"Expo push rejeitado | token={expo_token[:24]}... | resposta={result}")
        return False
    except Exception as exc:
        logger.error(f"Erro ao enviar Expo push para {expo_token[:24]}...: {exc}")
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
