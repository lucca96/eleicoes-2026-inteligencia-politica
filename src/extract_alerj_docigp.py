from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Any

import pandas as pd
import requests

from project_paths import RAW_ALERJ_DIR


BASE_URL = "https://docigp.alerj.rj.gov.br"
LEGISLATURE_ID = 2
LEGISLATURE_NUMBER = 12
USER_AGENT = "Mozilla/5.0"
NON_SPENDING_COST_CENTER_CODES = {"1", "2", "3", "4"}


@dataclass
class DocigpClient:
    base_url: str = BASE_URL
    pause_seconds: float = 0.1

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": USER_AGENT,
            }
        )

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}{path}", params=params, timeout=120)
        response.raise_for_status()
        sleep(self.pause_seconds)
        return response.json()

    def fetch_paginated(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.get_json(path, params={**(params or {}), "page": page})
            rows.extend(payload.get("rows", []))
            pagination = payload.get("links", {}).get("pagination", {})
            if page >= int(pagination.get("last_page") or 1):
                return rows
            page += 1


def to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def flatten_congressman(row: dict[str, Any]) -> dict[str, Any]:
    party = row.get("party") or {}
    return {
        "idDocigpDeputado": row.get("id"),
        "idAlerjRemoto": row.get("remote_id"),
        "nome": row.get("name"),
        "nomeParlamentar": row.get("nickname"),
        "siglaPartido": party.get("code"),
        "partido": party.get("name"),
        "temMandatoDocigp": row.get("has_mandate"),
        "publicadoDocigp": row.get("is_published"),
        "fotoUrl": row.get("photo_url_linkable"),
        "miniaturaUrl": row.get("thumbnail_url_linkable"),
    }


def flatten_budget(congressman: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    budget = row.get("budget") or {}
    return {
        "idDocigpDeputado": congressman.get("id"),
        "nome": congressman.get("name"),
        "nomeParlamentar": congressman.get("nickname"),
        "siglaPartido": (congressman.get("party") or {}).get("code"),
        "idOrcamentoDeputado": row.get("id"),
        "idLegislaturaDeputado": row.get("congressman_legislature_id"),
        "idOrcamentoMensal": row.get("budget_id"),
        "legislaturaAlerj": LEGISLATURE_NUMBER,
        "dataCompetencia": budget.get("date"),
        "valorLimiteMensal": to_float(row.get("value")),
        "valorCredito": to_float(row.get("sum_credit")),
        "valorDebito": abs(to_float(row.get("sum_debit"))),
        "qtdLancamentos": int(row.get("entries_count") or 0),
        "publicadoEm": row.get("published_at"),
        "analisadoEm": row.get("analysed_at"),
        "fechadoEm": row.get("closed_at"),
    }


def flatten_entry(congressman: dict[str, Any], budget: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    return {
        "idDocigpDeputado": congressman.get("id"),
        "nome": congressman.get("name"),
        "nomeParlamentar": congressman.get("nickname"),
        "siglaPartido": (congressman.get("party") or {}).get("code"),
        "idOrcamentoDeputado": budget.get("id"),
        "idLancamento": row.get("id"),
        "legislaturaAlerj": LEGISLATURE_NUMBER,
        "dataLancamento": row.get("date"),
        "valor": to_float(row.get("value")),
        "valorAbsoluto": to_float(row.get("value_abs")) or abs(to_float(row.get("value"))),
        "idCentroCusto": row.get("cost_center_id"),
        "codigoCentroCusto": row.get("cost_center_code"),
        "centroCusto": row.get("cost_center_name"),
        "objeto": row.get("object"),
        "favorecido": row.get("to") or row.get("provider_name"),
        "cpfCnpjFavorecido": row.get("provider_cpf_cnpj"),
        "tipoFavorecido": row.get("provider_type"),
        "tipoLancamento": row.get("entry_type_name"),
        "ehTransporteOuCredito": row.get("is_transport_or_credit"),
        "ehTransporte": row.get("is_transport"),
        "publicadoEm": row.get("published_at"),
        "verificadoEm": row.get("verified_at"),
        "analisadoEm": row.get("analysed_at"),
        "qtdDocumentos": row.get("documents_count"),
    }


def build_summary(entries_df: pd.DataFrame, budgets_df: pd.DataFrame) -> pd.DataFrame:
    if entries_df.empty:
        return pd.DataFrame()

    spending_df = entries_df.loc[
        (entries_df["valor"] < 0)
        & ~entries_df["codigoCentroCusto"].astype(str).isin(NON_SPENDING_COST_CENTER_CODES)
    ].copy()
    summary = (
        spending_df.groupby(["idDocigpDeputado", "nome", "nomeParlamentar", "siglaPartido"], dropna=False)
        .agg(
            valorGastoParlamentar=("valorAbsoluto", "sum"),
            qtdLancamentos=("idLancamento", "count"),
            qtdCategorias=("centroCusto", "nunique"),
            qtdFornecedores=("cpfCnpjFavorecido", "nunique"),
        )
        .reset_index()
    )
    if not budgets_df.empty:
        budget_summary = (
            budgets_df.groupby("idDocigpDeputado", dropna=False)
            .agg(valorLimitePeriodo=("valorLimiteMensal", "sum"), qtdMesesComOrcamento=("idOrcamentoDeputado", "count"))
            .reset_index()
        )
        summary = summary.merge(budget_summary, on="idDocigpDeputado", how="left")

    summary["usoLimitePct"] = summary.apply(
        lambda row: row["valorGastoParlamentar"] / row["valorLimitePeriodo"] * 100
        if row.get("valorLimitePeriodo", 0) > 0
        else 0,
        axis=1,
    )
    return summary.sort_values("valorGastoParlamentar", ascending=False)


def build_category_summary(entries_df: pd.DataFrame) -> pd.DataFrame:
    if entries_df.empty:
        return pd.DataFrame()
    spending_df = entries_df.loc[
        (entries_df["valor"] < 0)
        & ~entries_df["codigoCentroCusto"].astype(str).isin(NON_SPENDING_COST_CENTER_CODES)
    ].copy()
    category = (
        spending_df.groupby(["centroCusto", "codigoCentroCusto"], dropna=False)
        .agg(valorGastoParlamentar=("valorAbsoluto", "sum"), qtdLancamentos=("idLancamento", "count"))
        .reset_index()
    )
    total = category["valorGastoParlamentar"].sum()
    category["shareGastoPct"] = category["valorGastoParlamentar"] / total * 100 if total else 0
    return category.sort_values("valorGastoParlamentar", ascending=False)


def save_csv(df: pd.DataFrame, filename: str) -> None:
    RAW_ALERJ_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(RAW_ALERJ_DIR / filename, index=False, encoding="utf-8-sig")


def main() -> None:
    client = DocigpClient()
    congressmen = client.fetch_paginated("/api/v1/congressmen")

    congressmen_rows: list[dict[str, Any]] = []
    budget_rows: list[dict[str, Any]] = []
    entry_rows: list[dict[str, Any]] = []

    for congressman in congressmen:
        budgets = client.fetch_paginated(
            f"/api/v1/congressmen/{congressman['id']}/legislatures/{LEGISLATURE_ID}/budgets"
        )
        if not budgets:
            continue
        congressmen_rows.append(flatten_congressman(congressman))
        for budget in budgets:
            budget_rows.append(flatten_budget(congressman, budget))
            entries = client.fetch_paginated(
                f"/api/v1/congressmen/{congressman['id']}/legislatures/{LEGISLATURE_ID}/budgets/{budget['id']}/entries"
            )
            entry_rows.extend(flatten_entry(congressman, budget, entry) for entry in entries)

    congressmen_df = pd.DataFrame(congressmen_rows)
    budgets_df = pd.DataFrame(budget_rows)
    entries_df = pd.DataFrame(entry_rows)
    summary_df = build_summary(entries_df, budgets_df)
    category_df = build_category_summary(entries_df)

    save_csv(congressmen_df, "docigp_deputados_estaduais_rj.csv")
    save_csv(budgets_df, "docigp_orcamentos_deputados_estaduais_rj.csv")
    save_csv(entries_df, "docigp_lancamentos_deputados_estaduais_rj.csv")
    save_csv(summary_df, "docigp_resumo_gastos_deputados_estaduais_rj.csv")
    save_csv(category_df, "docigp_resumo_gastos_categoria_deputados_estaduais_rj.csv")

    print(f"Deputados com DOCIGP: {len(congressmen_df)}")
    print(f"Orcamentos mensais: {len(budgets_df)}")
    print(f"Lancamentos: {len(entries_df)}")
    print(f"Gasto parlamentar estadual: R$ {summary_df['valorGastoParlamentar'].sum():,.2f}")


if __name__ == "__main__":
    main()
