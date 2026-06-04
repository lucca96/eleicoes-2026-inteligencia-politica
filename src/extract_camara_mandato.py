from __future__ import annotations

import time
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

from camara_client import CamaraApiClient
from camara_legislatura import get_current_legislature_id, get_legislature_period
from project_paths import RAW_CAMARA_DIR


COTA_YEAR_URL = "https://www.camara.leg.br/cotas/Ano-{year}.csv.zip"


def valid_months_for_year(year: int, start_date: date, end_date: date) -> list[int]:
    first_month = start_date.month if year == start_date.year else 1
    last_month = end_date.month if year == end_date.year else 12
    return list(range(first_month, last_month + 1))


def download_year_expenses(year: int) -> pd.DataFrame:
    url = COTA_YEAR_URL.format(year=year)
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    with zipfile.ZipFile(BytesIO(response.content)) as zip_file:
        csv_name = zip_file.namelist()[0]
        with zip_file.open(csv_name) as csv_file:
            return pd.read_csv(
                csv_file,
                sep=";",
                encoding="utf-8-sig",
                low_memory=False,
                decimal=",",
            )


def normalize_cota_columns(expenses_df: pd.DataFrame) -> pd.DataFrame:
    column_map = {
        "ideCadastro": "idDeputado",
        "numAno": "ano",
        "numMes": "mes",
        "txtDescricao": "tipoDespesa",
        "ideDocumento": "codDocumento",
        "indTipoDocumento": "tipoDocumento",
        "datEmissao": "dataDocumento",
        "txtNumero": "numDocumento",
        "vlrDocumento": "valorDocumento",
        "urlDocumento": "urlDocumento",
        "txtFornecedor": "nomeFornecedor",
        "txtCNPJCPF": "cnpjCpfFornecedor",
        "vlrLiquido": "valorLiquido",
        "vlrGlosa": "valorGlosa",
        "numRessarcimento": "numRessarcimento",
        "numLote": "codLote",
        "numParcela": "parcela",
        "txNomeParlamentar": "nomeParlamentarArquivo",
        "sgPartido": "siglaPartidoArquivo",
        "sgUF": "siglaUfArquivo",
    }

    normalized_df = expenses_df.rename(columns=column_map)
    expected_columns = [
        "ano",
        "mes",
        "tipoDespesa",
        "codDocumento",
        "tipoDocumento",
        "dataDocumento",
        "numDocumento",
        "valorDocumento",
        "urlDocumento",
        "nomeFornecedor",
        "cnpjCpfFornecedor",
        "valorLiquido",
        "valorGlosa",
        "numRessarcimento",
        "codLote",
        "parcela",
        "idDeputado",
        "nomeParlamentarArquivo",
        "siglaPartidoArquivo",
        "siglaUfArquivo",
    ]

    for column in expected_columns:
        if column not in normalized_df.columns:
            normalized_df[column] = None

    return normalized_df[expected_columns].copy()


def build_mandate_expenses_dataset(
    deputies_df: pd.DataFrame,
    reference_date: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    current_date = reference_date or date.today()
    client = CamaraApiClient()
    id_legislatura = get_current_legislature_id(deputies_df)
    period = get_legislature_period(client, id_legislatura, current_date)

    all_expenses: list[pd.DataFrame] = []
    current_deputy_ids = set(deputies_df["id"].astype(int).tolist())

    for year in period.years:
        try:
            year_df = normalize_cota_columns(download_year_expenses(year))
            year_df = year_df.dropna(subset=["idDeputado"])
            year_df["idDeputado"] = year_df["idDeputado"].astype(int)
            year_df = year_df.loc[year_df["idDeputado"].isin(current_deputy_ids)].copy()

            if not year_df.empty:
                all_expenses.append(year_df)

        except Exception as exc:
            print(f"[WARN] Falha ao extrair arquivo anual de despesas {year}: {exc}")

    expenses_df = (
        pd.concat(all_expenses, ignore_index=True)
        if all_expenses
        else pd.DataFrame()
    )

    if expenses_df.empty:
        return expenses_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    for column in ["ano", "mes", "valorDocumento", "valorGlosa", "valorLiquido"]:
        if column in expenses_df.columns:
            expenses_df[column] = pd.to_numeric(expenses_df[column], errors="coerce")

    expenses_df = expenses_df.dropna(subset=["ano", "mes"])
    expenses_df["ano"] = expenses_df["ano"].astype(int)
    expenses_df["mes"] = expenses_df["mes"].astype(int)

    expenses_df = expenses_df.loc[
        expenses_df.apply(
            lambda row: int(row["mes"])
            in valid_months_for_year(int(row["ano"]), period.start_date, period.end_date),
            axis=1,
        )
    ].copy()

    summary_df = summarize_mandate_expenses(deputies_df, expenses_df)
    yoy_df = summarize_yoy(deputies_df, expenses_df, current_date)
    category_df = summarize_categories(expenses_df)

    return expenses_df, summary_df, yoy_df, category_df


def summarize_mandate_expenses(
    deputies_df: pd.DataFrame,
    expenses_df: pd.DataFrame,
) -> pd.DataFrame:
    summary_df = (
        expenses_df.groupby("idDeputado", as_index=False)
        .agg(
            qtd_lancamentos=("idDeputado", "size"),
            valor_documento_total=("valorDocumento", "sum"),
            valor_glosa_total=("valorGlosa", "sum"),
            valor_liquido_total=("valorLiquido", "sum"),
        )
    )
    monthly_df = (
        expenses_df.groupby(["idDeputado", "ano", "mes"], as_index=False)["valorLiquido"]
        .sum()
        .groupby("idDeputado", as_index=False)["valorLiquido"]
        .mean()
        .rename(columns={"valorLiquido": "gasto_medio_mensal"})
    )
    summary_df = summary_df.merge(monthly_df, on="idDeputado", how="left")

    return (
        deputies_df[["id", "nome", "siglaPartido", "siglaUf", "idLegislatura"]]
        .rename(columns={"id": "idDeputado"})
        .merge(summary_df, on="idDeputado", how="left")
        .fillna(
            {
                "qtd_lancamentos": 0,
                "valor_documento_total": 0,
                "valor_glosa_total": 0,
                "valor_liquido_total": 0,
                "gasto_medio_mensal": 0,
            }
        )
        .sort_values("valor_liquido_total", ascending=False)
    )


def summarize_yoy(
    deputies_df: pd.DataFrame,
    expenses_df: pd.DataFrame,
    reference_date: date,
) -> pd.DataFrame:
    current_year = reference_date.year
    previous_year = current_year - 1
    comparable_months = list(range(1, reference_date.month + 1))

    comparable_df = expenses_df.loc[
        expenses_df["ano"].isin([current_year, previous_year])
        & expenses_df["mes"].isin(comparable_months)
    ].copy()

    yearly_df = (
        comparable_df.groupby(["idDeputado", "ano"], as_index=False)["valorLiquido"]
        .sum()
        .pivot(index="idDeputado", columns="ano", values="valorLiquido")
        .reset_index()
        .rename(
            columns={
                current_year: "gasto_ytd_ano_atual",
                previous_year: "gasto_ytd_ano_anterior",
            }
        )
    )

    base_df = deputies_df[["id"]].rename(columns={"id": "idDeputado"})
    yearly_df = base_df.merge(yearly_df, on="idDeputado", how="left").fillna(0)

    for column in ["gasto_ytd_ano_atual", "gasto_ytd_ano_anterior"]:
        if column not in yearly_df.columns:
            yearly_df[column] = 0.0

    yearly_df["diferenca_yoy"] = (
        yearly_df["gasto_ytd_ano_atual"] - yearly_df["gasto_ytd_ano_anterior"]
    )
    yearly_df["variacao_yoy_pct"] = yearly_df.apply(
        lambda row: (row["diferenca_yoy"] / row["gasto_ytd_ano_anterior"]) * 100
        if row["gasto_ytd_ano_anterior"] > 0
        else 0,
        axis=1,
    )

    return yearly_df


def summarize_categories(expenses_df: pd.DataFrame) -> pd.DataFrame:
    category_df = (
        expenses_df.groupby("tipoDespesa", as_index=False)
        .agg(
            qtd_lancamentos=("tipoDespesa", "size"),
            valor_liquido_total=("valorLiquido", "sum"),
        )
        .sort_values("valor_liquido_total", ascending=False)
    )
    total_value = category_df["valor_liquido_total"].sum()
    category_df["share_gasto_pct"] = category_df.apply(
        lambda row: (row["valor_liquido_total"] / total_value) * 100
        if total_value > 0
        else 0,
        axis=1,
    )
    return category_df


def save_csv(df: pd.DataFrame, filename: str) -> Path:
    RAW_CAMARA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_CAMARA_DIR / filename
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    deputies_path = RAW_CAMARA_DIR / "deputados_em_exercicio.csv"

    if not deputies_path.exists():
        raise FileNotFoundError(
            "Arquivo de deputados nao encontrado. Execute "
            "src/extract_camara_deputados.py antes."
        )

    deputies_df = pd.read_csv(deputies_path)
    expenses_df, summary_df, yoy_df, category_df = build_mandate_expenses_dataset(
        deputies_df
    )

    output_paths = [
        save_csv(expenses_df, "despesas_deputados_mandato.csv"),
        save_csv(summary_df, "resumo_despesas_deputados_mandato.csv"),
        save_csv(yoy_df, "despesas_yoy_deputados_mandato.csv"),
        save_csv(category_df, "resumo_gastos_categoria_mandato.csv"),
    ]

    print(f"Lancamentos de despesas do mandato: {len(expenses_df)}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()
