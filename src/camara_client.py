from __future__ import annotations

import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
DEFAULT_TIMEOUT = 30
ITEMS_PER_PAGE = 100


class CamaraApiClient:
    """Cliente simples para a API v2 de Dados Abertos da Camara."""

    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            respect_retry_after_header=True,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "eleicoes-2026-bi/0.1",
            }
        )

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Erro ao acessar {url}. "
                f"Status={response.status_code}. "
                f"Resposta={response.text[:500]}"
            ) from exc

        return response.json()

    def get_paginated(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        sleep_seconds: float = 0.2,
    ) -> list[dict[str, Any]]:
        params = dict(params or {})
        params.setdefault("itens", ITEMS_PER_PAGE)

        page = 1
        records: list[dict[str, Any]] = []

        while True:
            params["pagina"] = page
            payload = self.get(endpoint, params=params)
            data = payload.get("dados", [])

            if not data:
                break

            records.extend(data)

            links = payload.get("links", [])
            has_next = any(link.get("rel") == "next" for link in links)

            if not has_next:
                break

            page += 1
            time.sleep(sleep_seconds)

        return records

