from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

from project_paths import RAW_ALERJ_DIR


ALERJ_BASE_URL = "https://www.alerj.rj.gov.br"
TRANSPARENCIA_BASE_URL = "https://transparencia.alerj.rj.gov.br"
DEPUTIES_URL = f"{ALERJ_BASE_URL}/Deputados/QuemSao"
TRANSPARENCY_REPORTS = {
    "presenca": f"{TRANSPARENCIA_BASE_URL}/section/report/17",
    "beneficios": f"{TRANSPARENCIA_BASE_URL}/section/report/33",
    "subsidio": f"{TRANSPARENCIA_BASE_URL}/section/report/34",
    "atividade_legislativa_anuario": f"{TRANSPARENCIA_BASE_URL}/section/report/114",
}
PROCESSO_LEGISLATIVO_LINKS = [
    {
        "tipo": "leis_e_projetos_2023_2027",
        "url": "http://www3.alerj.rj.gov.br/lotus_notes/default.asp?id=161",
        "observacao": "Portal oficial de projetos da 13a legislatura; votacoes podem exigir consulta por proposicao.",
    },
    {
        "tipo": "ordem_do_dia",
        "url": "http://www2.alerj.rj.gov.br/ordemdodia/",
        "observacao": "Agenda do plenario; fonte auxiliar para cruzar sessoes e votacoes.",
    },
]


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = dict(attrs)
        self._current_href = attrs_dict.get("href")
        self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._current_href is None:
            return
        text = " ".join(part.strip() for part in self._current_text if part.strip())
        self.links.append({"href": self._current_href, "text": html.unescape(text)})
        self._current_href = None
        self._current_text = []


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def extract_current_deputies() -> pd.DataFrame:
    page = fetch_html(DEPUTIES_URL)
    pattern = re.compile(
        r'<div class="controle_deputado(?P<leader>[^"]*)">.*?'
        r'<div class="partido">(?P<party>.*?)</div>.*?'
        r'<div class="nome"><a href="(?P<href>[^"]+)">(?P<name>.*?)</a></div>',
        re.DOTALL | re.IGNORECASE,
    )

    rows: list[dict[str, object]] = []
    for match in pattern.finditer(page):
        href = html.unescape(match.group("href"))
        deputy_id_match = re.search(r"PerfilDeputado/(\d+)", href)
        legislature_match = re.search(r"Legislatura=(\d+)", href)
        rows.append(
            {
                "idAlerj": int(deputy_id_match.group(1)) if deputy_id_match else None,
                "legislaturaAlerj": int(legislature_match.group(1)) if legislature_match else None,
                "nome": html.unescape(re.sub(r"\s+", " ", match.group("name")).strip()),
                "siglaPartido": html.unescape(re.sub(r"\s+", " ", match.group("party")).strip()),
                "perfilUrl": urljoin(ALERJ_BASE_URL, href),
                "lideranca": "lider" in match.group("leader"),
                "casaLegislativa": "ALERJ",
                "siglaUf": "RJ",
            }
        )

    return pd.DataFrame(rows).sort_values("nome")


def extract_links(url: str) -> list[dict[str, str]]:
    parser = AnchorParser()
    parser.feed(fetch_html(url))
    return [
        {
            "text": item["text"],
            "url": urljoin(url, item["href"]),
        }
        for item in parser.links
        if item.get("href")
    ]


def build_transparency_resource_catalog() -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for resource_type, url in TRANSPARENCY_REPORTS.items():
        rows.append(
            {
                "tipo": resource_type,
                "formato": "html",
                "titulo": resource_type,
                "url": url,
                "observacao": "Pagina oficial do Portal da Transparencia da ALERJ.",
            }
        )
        for link in extract_links(url):
            rows.append(
                {
                    "tipo": resource_type,
                    "formato": "pdf" if "pdf" in link["text"].lower() or link["url"].lower().endswith(".pdf") else "link",
                    "titulo": link["text"],
                    "url": link["url"],
                    "observacao": "Recurso listado na pagina oficial de transparencia.",
                }
            )

    rows.extend(PROCESSO_LEGISLATIVO_LINKS)
    return pd.DataFrame(rows).drop_duplicates(["tipo", "url"]).sort_values(["tipo", "titulo"])


def build_activity_pdf_catalog(resources_df: pd.DataFrame) -> pd.DataFrame:
    activity_df = resources_df.loc[
        resources_df["tipo"].eq("atividade_legislativa_anuario")
        & resources_df["formato"].eq("pdf")
    ].copy()
    return activity_df.rename(columns={"titulo": "nomeDeputadoOuRelatorio"})


def save_csv(df: pd.DataFrame, filename: str) -> Path:
    RAW_ALERJ_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_ALERJ_DIR / filename
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    deputies_df = extract_current_deputies()
    resources_df = build_transparency_resource_catalog()
    activity_pdfs_df = build_activity_pdf_catalog(resources_df)

    output_paths = [
        save_csv(deputies_df, "deputados_estaduais_rj_alerj_em_exercicio.csv"),
        save_csv(resources_df, "alerj_fontes_transparencia_e_legislativo.csv"),
        save_csv(activity_pdfs_df, "alerj_anuario_atividade_legislativa_pdfs.csv"),
    ]

    print(f"Deputados estaduais em exercicio na ALERJ: {len(deputies_df)}")
    print(f"Recursos oficiais catalogados: {len(resources_df)}")
    print(f"PDFs de atividade legislativa catalogados: {len(activity_pdfs_df)}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()
