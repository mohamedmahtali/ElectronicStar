import logging
from typing import Any
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

CAPTCHA_INDICATORS = [
    "access denied",
    "403 forbidden",
    "checking your browser",
    "verify you are human",
    "are you a robot",
    "unusual traffic",
    "je ne suis pas un robot",
    "vérifiez que vous n'êtes pas un robot",
    "verifiez que vous n'etes pas un robot",
    "captcha required",
    "captcha obligatoire",
]


class CaptchaDetectionMiddleware:
    """Détecte les CAPTCHAs et ralentit le crawl du domaine concerné."""

    def process_response(self, request, response: Any, spider):
        if self._is_captcha(response):
            domain = urlparse(request.url).hostname or ""
            logger.warning(
                "CAPTCHA détecté sur %s — domaine %s : ralentissement",
                request.url, domain,
            )
            # Augmente le délai sur le slot du domaine si disponible
            slots = spider.crawler.engine.downloader.slots
            slot = slots.get(domain)
            if slot is not None:
                slot.delay = max(getattr(slot, "delay", 0) * 2, 10.0)
            response = response.replace(status=429)
        return response

    def _is_captcha(self, response: Any) -> bool:
        if response.status in (403, 429):
            return True
        body_lower = response.text.lower()
        return any(ind in body_lower for ind in CAPTCHA_INDICATORS)
