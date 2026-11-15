from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any, Iterator
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.config import settings


logger = logging.getLogger(__name__)

BASE_URL = "https://store.steampowered.com"
SEARCH_URL = f"{BASE_URL}/search/results/"
MAX_RETRY_DELAY = 300.0

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


class SteamAdapter:
    """Coleta ofertas pagas da Steam para a região configurada.

    O adapter não grava diretamente no MySQL. Ele retorna dicionários
    compatíveis com app.services.steam_deals_service.run_steam_crawler().
    """

    slug = "steam"
    name = "Steam"
    base_url = BASE_URL

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": f"{BASE_URL}/",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self.collection_complete = True
        self.collection_error: str | None = None

    def iter_pages(
        self,
        max_items: int | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Entrega lotes de ofertas à medida que as páginas são consultadas.

        Em caso de falha depois de uma ou mais páginas, os lotes já entregues
        permanecem disponíveis, mas collection_complete será False.
        """
        self.collection_complete = True
        self.collection_error = None

        seen: set[str] = set()
        collected = 0
        start = 0
        page_number = 0
        total_count: int | None = None

        page_size = max(1, settings.steam_page_size)
        max_pages = max(1, settings.steam_max_pages)

        while page_number < max_pages:
            params = {
                "query": "",
                "start": start,
                "count": page_size,
                "hwtype": 0,
                "supportedlang": settings.steam_language,
                "specials": 1,
                "hidef2p": 1,
                "ndl": 1,
                "cc": settings.steam_country.lower(),
                "l": settings.steam_language,
                "infinite": 1,
                "json": 1,
            }

            logger.info(
                "Steam: consultando página %s/%s (start=%s, count=%s)",
                page_number + 1,
                max_pages,
                start,
                page_size,
            )

            try:
                response = self._get(SEARCH_URL, params)
                html, response_total = self._extract_results(response)
                if response_total is not None:
                    total_count = response_total
            except RuntimeError as exc:
                self._mark_incomplete(str(exc))
                logger.exception(
                    "Steam: falha na página start=%s. "
                    "Foram coletados %s jogos antes da falha.",
                    start,
                    collected,
                )
                break

            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("a.search_result_row")

            if not rows:
                rows = soup.select("#search_resultsRows a, .search_results a")
                rows = [row for row in rows if row.get("data-ds-appid")]

            if not rows:
                # Uma busca vazia na primeira página não deve ser tratada
                # como coleta completa: pode ser bloqueio ou mudança no HTML.
                self._mark_incomplete(
                    "A Steam não retornou resultados na primeira página."
                    if start == 0
                    else "A Steam retornou uma página vazia antes do fim esperado."
                )
                logger.warning(
                    "Steam: nenhuma oferta encontrada. HTTP=%s URL=%s "
                    "total_count=%s HTML length=%s preview=%r",
                    response.status_code,
                    response.url,
                    total_count,
                    len(html),
                    html[:300],
                )
                break

            page_results: list[dict[str, Any]] = []

            for row in rows:
                item = self._parse_row(row)
                if item is None:
                    continue

                external_id = item["external_id"]
                if external_id in seen:
                    continue

                seen.add(external_id)
                page_results.append(item)

                if max_items is not None and collected + len(page_results) >= max_items:
                    page_results = page_results[: max_items - collected]
                    break

            page_number += 1
            collected += len(page_results)

            logger.info(
                "Steam: página %s processada (%s ofertas válidas). Total: %s.",
                page_number,
                len(page_results),
                collected,
            )

            if page_results:
                yield page_results

            if max_items is not None and collected >= max_items:
                logger.info("Steam: limite de %s ofertas atingido.", max_items)
                break

            start += len(rows)

            if total_count is not None and start >= total_count:
                break

            if total_count is None and len(rows) < page_size:
                break

            if page_number >= max_pages:
                # Não declarar uma coleta limitada por max_pages como completa.
                self._mark_incomplete(
                    f"Limite máximo de páginas ({max_pages}) atingido."
                )
                logger.warning("Steam: %s", self.collection_error)
                break

            delay = max(0.0, settings.steam_request_delay)
            if delay:
                time.sleep(delay)

        if self.collection_complete:
            logger.info("Steam: coleta finalizada. %s ofertas entregues.", collected)
        else:
            logger.warning(
                "Steam: coleta incompleta. %s ofertas entregues. Motivo: %s",
                collected,
                self.collection_error,
            )

    def fetch(self, max_items: int | None = None) -> list[dict[str, Any]]:
        """Retorna a lista completa; falha se a coleta ficar incompleta.

        Isso evita que o serviço de persistência interprete uma coleta parcial
        como completa e marque ofertas não encontradas como indisponíveis.
        """
        deals = [
            item
            for page in self.iter_pages(max_items=max_items)
            for item in page
        ]

        if not deals:
            raise RuntimeError(
                "A Steam não forneceu ofertas válidas. "
                "Nenhuma alteração deve ser feita no banco."
            )

        if max_items is None and not self.collection_complete:
            raise RuntimeError(
                "Coleta Steam incompleta; persistência cancelada para "
                "preservar as ofertas existentes. "
                f"Motivo: {self.collection_error or 'desconhecido'}"
            )

        return deals

    @staticmethod
    def _extract_results(
        response: requests.Response,
    ) -> tuple[str, int | None]:
        """Aceita JSON da busca AJAX ou HTML direto."""
        try:
            payload = response.json()
        except (requests.exceptions.JSONDecodeError, ValueError):
            payload = None

        if isinstance(payload, dict):
            if payload.get("success") is False:
                raise RuntimeError("Steam retornou success=false na busca.")

            html = payload.get("results_html")
            if html is not None:
                total = payload.get("total_count")
                try:
                    total_count = int(total) if total is not None else None
                except (TypeError, ValueError):
                    total_count = None
                return str(html), total_count

        return response.text, None

    def _get(
        self,
        url: str,
        params: dict[str, Any],
    ) -> requests.Response:
        max_attempts = max(1, settings.request_retries + 1)
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=settings.request_timeout,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = self._retry_delay(retry_after, attempt)
                    last_error = requests.HTTPError(
                        "429 Too Many Requests",
                        response=response,
                    )

                    logger.warning(
                        "Steam HTTP 429. Tentativa %s/%s; aguardando %.1f s.",
                        attempt + 1,
                        max_attempts,
                        wait_seconds,
                    )

                    if attempt < max_attempts - 1:
                        time.sleep(wait_seconds)
                        continue
                    break

                response.raise_for_status()
                return response

            except requests.RequestException as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    wait_seconds = min(5 * (2**attempt), 60)
                    logger.warning(
                        "Erro HTTP na Steam: %s. Nova tentativa em %.1f s.",
                        exc,
                        wait_seconds,
                    )
                    time.sleep(wait_seconds)

        raise RuntimeError(
            f"Falha ao consultar Steam após {max_attempts} tentativas: "
            f"{last_error}"
        ) from last_error

    @staticmethod
    def _retry_delay(retry_after: str | None, attempt: int) -> float:
        if retry_after:
            try:
                return min(max(float(retry_after), 1.0), MAX_RETRY_DELAY)
            except (ValueError, TypeError):
                try:
                    retry_date = parsedate_to_datetime(retry_after)
                    if retry_date.tzinfo is None:
                        retry_date = retry_date.replace(tzinfo=timezone.utc)
                    seconds = (
                        retry_date - datetime.now(timezone.utc)
                    ).total_seconds()
                    return min(max(seconds, 1.0), MAX_RETRY_DELAY)
                except (ValueError, TypeError, OverflowError):
                    pass

        base_delay = max(1.0, settings.steam_rate_limit_backoff)
        return min(base_delay * (2**attempt), MAX_RETRY_DELAY)

    @staticmethod
    def _parse_row(row: Any) -> dict[str, Any] | None:
        app_id = (row.get("data-ds-appid") or "").split(",")[0].strip()
        if not app_id.isdigit():
            return None

        title_node = row.select_one(".search_name .title")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if not title:
            return None

        price_block = (
            row.select_one(".search_price_discount_combined")
            or row.select_one(".search_price")
        )
        if price_block is None:
            return None

        final_price = SteamAdapter._extract_final_price(row, price_block)
        if final_price is None or final_price <= 0:
            # Não salvar jogos grátis, preços ausentes ou valores inválidos.
            return None

        original_price = SteamAdapter._extract_original_price(row)
        discount = SteamAdapter._extract_discount(row)

        # Quando o desconto percentual não vier no HTML, calcula a partir
        # dos preços original e promocional.
        if discount is None and original_price and original_price > final_price:
            discount = (
                (original_price - final_price) / original_price * Decimal(100)
            ).quantize(Decimal("0.01"))

        href = row.get("href") or f"/app/{app_id}/"
        image_url = SteamAdapter._extract_image(row)

        platforms: list[str] = []
        if row.select_one(".platform_img.win"):
            platforms.append("windows")
        if row.select_one(".platform_img.mac"):
            platforms.append("mac")
        if row.select_one(".platform_img.linux"):
            platforms.append("linux")

        currency = (settings.steam_currency or "brl").upper()
        region = (settings.steam_country or "BR").upper()

        return {
            "external_id": app_id,
            "steam_app_id": int(app_id),
            "title": title,
            "url": urljoin(BASE_URL, href),
            "image_url": image_url,
            # Alias útil para schemas que nomeiam a imagem como banner_img.
            "banner_img": image_url,
            "current_price": final_price.quantize(Decimal("0.01")),
            "original_price": (
                original_price.quantize(Decimal("0.01"))
                if original_price is not None
                else None
            ),
            "currency": currency,
            "discount_percent": (
                discount.quantize(Decimal("0.01"))
                if discount is not None
                else None
            ),
            "region": region,
            "activation_platform": ",".join(platforms) if platforms else "PC",
            "platforms": platforms or ["pc"],
        }

    @staticmethod
    def _extract_final_price(row: Any, price_block: Any) -> Decimal | None:
        raw = (
            price_block.get("data-price-final")
            or row.get("data-price-final")
        )

        if raw not in (None, ""):
            try:
                # A Steam informa data-price-final em centavos.
                return Decimal(str(raw)) / Decimal(100)
            except (InvalidOperation, TypeError, ValueError):
                pass

        final_node = row.select_one(".discount_final_price")
        if final_node:
            try:
                return _parse_brl(final_node.get_text(" ", strip=True))
            except (InvalidOperation, ValueError):
                pass

        try:
            return _parse_brl(price_block.get_text(" ", strip=True))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _extract_original_price(row: Any) -> Decimal | None:
        original_node = row.select_one(".discount_original_price")
        if original_node:
            try:
                return _parse_brl(original_node.get_text(" ", strip=True))
            except (InvalidOperation, ValueError):
                pass

        raw = row.get("data-price-initial")
        if raw not in (None, ""):
            try:
                value = Decimal(str(raw)) / Decimal(100)
                return value if value > 0 else None
            except (InvalidOperation, TypeError, ValueError):
                pass

        return None

    @staticmethod
    def _extract_discount(row: Any) -> Decimal | None:
        discount_node = row.select_one(".discount_pct")
        discount_text = (
            discount_node.get_text(" ", strip=True)
            if discount_node
            else ""
        )

        match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", discount_text)
        if match:
            try:
                return Decimal(match.group(1).replace(",", "."))
            except InvalidOperation:
                pass

        raw = row.get("data-discount")
        if raw not in (None, ""):
            try:
                return abs(Decimal(str(raw)))
            except (InvalidOperation, TypeError, ValueError):
                pass

        return None

    @staticmethod
    def _extract_image(row: Any) -> str | None:
        # data-ds-image costuma conter a imagem de capa usada pela busca Steam.
        candidates = [
            row.get("data-ds-image"),
        ]

        image = row.select_one(".search_capsule img")
        if image:
            candidates.extend(
                [
                    image.get("src"),
                    image.get("data-src"),
                    image.get("data-original"),
                ]
            )

        for candidate in candidates:
            if not candidate:
                continue
            candidate = str(candidate).strip()
            if candidate.startswith("//"):
                return f"https:{candidate}"
            return urljoin(BASE_URL, candidate)

        return None

    def _mark_incomplete(self, reason: str) -> None:
        self.collection_complete = False
        self.collection_error = reason

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "SteamAdapter":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _parse_brl(value: str) -> Decimal:
    """Converte valores localizados, por exemplo R$ 1.299,00 e R$ 16,74."""
    cleaned = (
        value.replace("R$", "")
        .replace("\xa0", "")
        .replace(" ", "")
        .strip()
    )
    cleaned = re.sub(r"[^\d,.-]", "", cleaned)

    if not cleaned:
        raise ValueError(f"Preço vazio ou inválido: {value!r}")

    # Formato brasileiro: ponto de milhar e vírgula decimal.
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # Sem vírgula, preserva ponto decimal quando houver.
        cleaned = re.sub(r"(?<=\d)\.(?=\d{3}(?:\D|$))", "", cleaned)

    match = re.search(r"-?\d+(?:\.\d{1,2})?", cleaned)
    if not match:
        raise ValueError(f"Preço inválido: {value!r}")

    return Decimal(match.group(0))
