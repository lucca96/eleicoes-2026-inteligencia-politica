from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://legis.senado.leg.br/dadosabertos"
DEFAULT_TIMEOUT = 120


class SenadoApiClient:
    """Cliente simples para endpoints XML dos Dados Abertos do Senado."""

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
                "Accept": "application/xml,text/xml,*/*",
                "User-Agent": "eleicoes-2026-bi/0.1",
            }
        )

    def get_xml(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        sleep_seconds: float = 0,
    ) -> ET.Element:
        if sleep_seconds:
            time.sleep(sleep_seconds)

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

        return ET.fromstring(response.content)


def text_at(node: ET.Element | None, path: str, default: str = "") -> str:
    if node is None:
        return default

    child = node.find(path)
    if child is None or child.text is None:
        return default

    return child.text.strip()
