from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd

from camara_client import CamaraApiClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "camara"


def extract_current_deputies(
    client: CamaraApiClient,
    reference_date: date,
) -> pd.DataFrame:
    deputies = client.get_paginated(
        "/deputados",
        params={
            "dataInicio": reference_date.isoformat(),
            "dataFim": reference_date.isoformat(),
            "ordem": "ASC",
            "ordenarPor": "nome",
        },
    )

    return pd.DataFrame(deputies)


def extract_deputy_expenses(
    client: CamaraApiClient,
    deputy_id: int,
    year: int,
    month: int,
) -> pd.DataFrame:
    expenses = client.get_paginated(
        f"/deputados/{deputy_id}/despesas",
        params={
            "ano": year,
            "mes": month,
            "ordem": "ASC",
            "ordenarPor": "dataDocumento",
        },
    )

    if not expenses:
        return pd.DataFrame()

    df = pd.DataFrame(expenses)
    df["idDeputado"] = deputy_id
    return df


def build_monthly_expenses_dataset(
    reference_date: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    client = CamaraApiClient()
    current_date = reference_date or date.today()

    deputies_df = extract_current_deputies(client, current_date)

    if deputies_df.empty:
        raise RuntimeError("Nenhum deputado em exercicio foi retornado pela API.")

    all_expenses: list[pd.DataFrame] = []

    for row in deputies_df.itertuples(index=False):
        deputy_id = int(row.id)

        try:
            expenses_df = extract_deputy_expenses(
                client=client,
                deputy_id=deputy_id,
                year=current_date.year,
                month=current_date.month,
            )

            if not expenses_df.empty:
                all_expenses.append(expenses_df)

        except Exception as exc:
            print(f"[WARN] Falha ao extrair despesas do deputado {deputy_id}: {exc}")

        time.sleep(0.2)

    expenses_df = (
        pd.concat(all_expenses, ignore_index=True)
        if all_expenses
        else pd.DataFrame()
    )

    if not expenses_df.empty:
        for column in ["valorDocumento", "valorGlosa", "valorLiquido"]:
            if column in expenses_df.columns:
                expenses_df[column] = pd.to_numeric(expenses_df[column], errors="coerce")

    return deputies_df, expenses_df


def summarize_expenses_by_deputy(
    deputies_df: pd.DataFrame,
    expenses_df: pd.DataFrame,
) -> pd.DataFrame:
    output_columns = [
        "id",
        "nome",
        "siglaPartido",
        "siglaUf",
        "qtd_lancamentos",
        "valor_documento_total",
        "valor_glosa_total",
        "valor_liquido_total",
    ]

    if expenses_df.empty:
        return pd.DataFrame(columns=output_columns)

    summary_df = (
        expenses_df.groupby("idDeputado", as_index=False)
        .agg(
            qtd_lancamentos=("idDeputado", "size"),
            valor_documento_total=("valorDocumento", "sum"),
            valor_glosa_total=("valorGlosa", "sum"),
            valor_liquido_total=("valorLiquido", "sum"),
        )
    )

    return (
        deputies_df[["id", "nome", "siglaPartido", "siglaUf"]]
        .merge(summary_df, left_on="id", right_on="idDeputado", how="left")
        .drop(columns=["idDeputado"])
        .fillna(
            {
                "qtd_lancamentos": 0,
                "valor_documento_total": 0,
                "valor_glosa_total": 0,
                "valor_liquido_total": 0,
            }
        )
        .sort_values("valor_liquido_total", ascending=False)
    )


def save_csv(df: pd.DataFrame, filename: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / filename
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    deputies, expenses = build_monthly_expenses_dataset()
    summary = summarize_expenses_by_deputy(deputies, expenses)

    output_paths = [
        save_csv(deputies, "deputados_em_exercicio.csv"),
        save_csv(expenses, "despesas_deputados_mes_atual.csv"),
        save_csv(summary, "resumo_despesas_deputados_mes_atual.csv"),
    ]

    print(f"Deputados extraidos: {len(deputies)}")
    print(f"Lancamentos de despesas extraidos: {len(expenses)}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()

