from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

import requests

from app.config import settings

API_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
USER_AGENT = "Mozilla/5.0 (compatible; GamesDealsCrawler/1.0)"


class EpicGamesAdapter:
    slug = "epic-games"
    name = "Epic Games Store"
    base_url = "https://store.epicgames.com"

    def fetch(self, max_items: int | None = None) -> list[dict]:
        response = self._request(API_URL, params={
            "locale": settings.epic_locale,
            "country": settings.epic_country,
            "allowCountries": settings.epic_country,
        })
        payload = response.json()
        elements = payload.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
        now = datetime.now(timezone.utc)
        results, seen = [], set()
        for element in elements:
            external_id = str(element.get("id") or element.get("productId") or "").strip()
            title = (element.get("title") or "").strip()
            if not external_id or not title or external_id in seen:
                continue
            offer = _active_free_offer((element.get("promotions") or {}).get("promotionalOffers") or [], now)
            if not offer:
                continue
            seen.add(external_id)
            slug = _slug_for(element)
            product_url = f"https://store.epicgames.com/{settings.epic_locale}/p/{quote(slug)}" if slug else f"https://store.epicgames.com/{settings.epic_locale}/free-games"
            price = (element.get("price") or {}).get("totalPrice") or {}
            original = (Decimal(str(price.get("originalPrice", 0))) / Decimal(100)).quantize(Decimal("0.01"))
            results.append({
                "external_id": external_id, "title": title, "banner_img": _image_for(element),
                "starts_at": offer[0].replace(tzinfo=None), "ends_at": offer[1].replace(tzinfo=None),
                "is_on_banner": False, "status": "active", "product_url": product_url,
            })
            if max_items is not None and len(results) >= max_items:
                break
        return results

    @staticmethod
    def _request(url: str, params: dict) -> requests.Response:
        last_error = None
        for attempt in range(settings.request_retries + 1):
            try:
                response = requests.get(url, params=params, timeout=settings.request_timeout,
                                        headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt < settings.request_retries:
                    time.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"Falha ao consultar Epic Games: {last_error}") from last_error


def _active_free_offer(groups: list[dict], now: datetime):
    for group in groups:
        for offer in group.get("promotionalOffers") or []:
            discount = (offer.get("discountSetting") or {}).get("discountPercentage")
            if discount != 0:
                continue
            start, end = offer.get("startDate"), offer.get("endDate")
            if not start or not end:
                continue
            starts_at, ends_at = _parse_datetime(start), _parse_datetime(end)
            if starts_at <= now < ends_at:
                return starts_at, ends_at
    return None


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _image_for(element: dict) -> str | None:
    images = element.get("keyImages") or []
    preferred = ("OfferImageWide", "DieselStoreFrontWide", "Thumbnail", "OfferImageTall")
    for image_type in preferred:
        for item in images:
            if item.get("type") == image_type and item.get("url"):
                return item["url"]
    return next((item.get("url") for item in images if item.get("url")), None)


def _slug_for(element: dict) -> str | None:
    mappings = (element.get("catalogNs") or {}).get("mappings") or []
    for mapping in mappings:
        if mapping.get("pageType") == "productHome" and mapping.get("pageSlug"):
            return mapping["pageSlug"].strip("/").split("/")[-1]
    for mapping in mappings:
        if mapping.get("pageSlug"):
            return mapping["pageSlug"].strip("/").split("/")[-1]
    slug = element.get("productSlug") or element.get("urlSlug")
    return str(slug).strip("/").split("/")[-1] if slug else None
