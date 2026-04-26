"""Email transport utilities."""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailClient:
    """Async SMTP email transport."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def send_email(self, to_email: str, subject: str, body: str) -> None:
        """Send email via SMTP using non-blocking thread offload."""
        message = EmailMessage()
        message["From"] = self.settings.email_from
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)
        await asyncio.to_thread(self._send_blocking, message)
        logger.info("email.sent to=%s subject=%s", to_email, subject)

    def _send_blocking(self, message: EmailMessage) -> None:
        """Perform blocking SMTP operation in dedicated thread."""
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.smtp_timeout_seconds) as smtp:
            if self.settings.smtp_starttls:
                smtp.starttls()
            smtp.login(self.settings.smtp_user, self.settings.smtp_pass)
            smtp.send_message(message)
