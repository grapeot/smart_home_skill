import html
import logging
import os
import re
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)


TRUE_VALUES = {"1", "true", "yes", "on"}


class NotificationService:
    def __init__(self):
        self.api_url = os.getenv("RESEND_API_URL", "https://api.resend.com/emails")

    def _enabled(self) -> bool:
        return os.getenv("GARAGE_NOTIFY_ENABLED", "").strip().lower() in TRUE_VALUES

    def _recipients(self) -> list[str]:
        raw = os.getenv("GARAGE_NOTIFY_RECIPIENTS", "")
        return [part.strip() for part in re.split(r"[;,]", raw) if part.strip()]

    def is_configured(self) -> bool:
        return bool(
            self._enabled()
            and os.getenv("RESEND_API_KEY")
            and os.getenv("RESEND_FROM_EMAIL")
            and self._recipients()
        )

    def send_garage_toggle(self, result: dict[str, Any]) -> dict[str, Any]:
        if not self.is_configured():
            return {"enabled": False, "sent": False, "reason": "not_configured"}

        api_key = os.environ["RESEND_API_KEY"]
        from_email = os.environ["RESEND_FROM_EMAIL"]
        recipients = self._recipients()
        door = result.get("door", "unknown")
        timestamp = result.get("timestamp") or datetime.now().isoformat()

        subject = f"Smart Home Garage door {door} toggle triggered"
        html_body = self._render_garage_toggle_html(result, recipients)
        response = requests.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": from_email,
                "to": recipients,
                "subject": subject,
                "html": html_body,
                "text": (
                    f"Garage door {door} toggle triggered at {timestamp}."
                ),
            },
            timeout=10,
        )
        response.raise_for_status()
        body = response.json() if response.content else {}
        logger.info("Garage notification sent via Resend to %d recipient(s)", len(recipients))
        return {"enabled": True, "sent": True, "recipients": len(recipients), "resend_id": body.get("id")}

    def _render_garage_toggle_html(self, result: dict[str, Any], recipients: list[str]) -> str:
        rows = []
        for key in ("door", "action", "timestamp"):
            rows.append(
                "<tr>"
                f"<th align='left'>{html.escape(str(key))}</th>"
                f"<td>{html.escape(str(result.get(key)))}</td>"
                "</tr>"
            )
        rows.append(
            "<tr>"
            "<th align='left'>recipient_count</th>"
            f"<td>{len(recipients)}</td>"
            "</tr>"
        )
        return (
            "<h2>Garage door toggle triggered</h2>"
            "<p>A Smart Home garage door toggle endpoint was called.</p>"
            "<table>"
            + "".join(rows)
            + "</table>"
        )


notification_service = NotificationService()
