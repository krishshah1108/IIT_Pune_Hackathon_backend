"""Alert dispatch service."""

import logging

from app.repositories.caregiver_repository import CaregiverRepository
from app.repositories.alert_repository import AlertRepository
from app.utils.email import EmailClient

logger = logging.getLogger(__name__)


class AlertService:
    """Queue and send caregiver alerts."""

    def __init__(self, alert_repo: AlertRepository, caregiver_repo: CaregiverRepository, email_client: EmailClient):
        self.alert_repo = alert_repo
        self.caregiver_repo = caregiver_repo
        self.email_client = email_client

    async def create_and_send(self, user_id: str, severity: str, message: str) -> dict:
        """Persist and send caregiver alert emails."""
        logger.info("alert.create_and_send.started user_id=%s severity=%s", user_id, severity)
        alert = await self.alert_repo.create_alert(user_id=user_id, severity=severity, message=message)
        logger.info("alert.created alert_id=%s user_id=%s", alert["_id"], user_id)
        caregivers = await self.caregiver_repo.list_by_user(user_id, include_inactive=False)
        recipients = [str(c.get("email", "")).strip() for c in caregivers if c.get("notify_on_missed_dose")]
        recipients = [r for r in recipients if r]
        logger.info(
            "alert.recipients.resolved alert_id=%s user_id=%s caregiver_count=%s recipient_count=%s",
            alert["_id"],
            user_id,
            len(caregivers),
            len(recipients),
        )
        if not recipients:
            await self.alert_repo.mark_failed(alert["_id"], "no_active_caregiver_recipients")
            logger.warning("alert.send.skipped_no_recipients alert_id=%s user_id=%s", alert["_id"], user_id)
            return alert
        try:
            for to_email in recipients:
                logger.info("alert.email.sending alert_id=%s user_id=%s to=%s", alert["_id"], user_id, to_email)
                await self.email_client.send_email(
                    to_email=to_email,
                    subject=f"MediReminder Alert ({severity.upper()})",
                    body=message,
                )
                logger.info("alert.email.sent alert_id=%s user_id=%s to=%s", alert["_id"], user_id, to_email)
            await self.alert_repo.mark_sent(alert["_id"])
            logger.info("alert.send.completed alert_id=%s user_id=%s recipients=%s", alert["_id"], user_id, len(recipients))
        except Exception as exc:
            logger.exception("caregiver.alert.email_failed user=%s", user_id)
            await self.alert_repo.mark_failed(alert["_id"], str(exc))
            logger.error("alert.send.failed alert_id=%s user_id=%s error=%s", alert["_id"], user_id, str(exc))
        return alert

    async def list_alerts(self, user_id: str, limit: int = 50) -> list[dict]:
        """Return recent alerts for user timeline."""
        return await self.alert_repo.list_by_user(user_id, limit=limit)
