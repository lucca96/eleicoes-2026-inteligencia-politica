from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from camara_client import CamaraApiClient
from camara_legislatura import get_current_legislature_id, get_legislature_period
from project_paths import RAW_CAMARA_DIR


SUBSIDIO_DEPUTADO_FEDERAL = 46366.19
FONTE_REMUNERACAO_URL = "https://www.camara.leg.br/transparencia/gastos-parlamentares"


def build_monthly_remuneration(
    deputies_df: pd.DataFrame,
    reference_date: date | None = None,
) -> pd.DataFrame:
    current_date = reference_date or date.today()

    remuneration_df = deputies_df[
        ["id", "nome", "siglaPartido", "siglaUf", "idLegislatura"]
    ].copy()
    remuneration_df = remuneration_df.rename(columns={"id": "idDeputado"})
    remuneration_df["ano"] = current_date.year
    remuneration_df["mes"] = current_date.month
    remuneration_df["cargo"] = "Deputado Federal"
    remuneration_df["tipo_remuneracao"] = "Subsidio parlamentar bruto"
    remuneration_df["valor_subsidio_bruto"] = SUBSIDIO_DEPUTADO_FEDERAL
    remuneration_df["fonte_url"] = FONTE_REMUNERACAO_URL
    remuneration_df["data_referencia"] = current_date.isoformat()

    return remuneration_df


def months_between(start_date: date, end_date: date) -> int:
    return ((end_date.year - start_date.year) * 12) + end_date.month - start_date.month + 1


def build_mandate_remuneration(
    deputies_df: pd.DataFrame,
    reference_date: date | None = None,
) -> pd.DataFrame:
    current_date = reference_date or date.today()
    client = CamaraApiClient()
    id_legislatura = get_current_legislature_id(deputies_df)
    period = get_legislature_period(client, id_legislatura, current_date)
    mandate_months = months_between(period.start_date, period.end_date)

    remuneration_df = deputies_df[
        ["id", "nome", "siglaPartido", "siglaUf", "idLegislatura"]
    ].copy()
    remuneration_df = remuneration_df.rename(columns={"id": "idDeputado"})
    remuneration_df["data_inicio_periodo"] = period.start_date.isoformat()
    remuneration_df["data_fim_periodo"] = period.end_date.isoformat()
    remuneration_df["meses_considerados"] = mandate_months
    remuneration_df["cargo"] = "Deputado Federal"
    remuneration_df["tipo_remuneracao"] = "Subsidio parlamentar bruto"
    remuneration_df["valor_subsidio_mensal"] = SUBSIDIO_DEPUTADO_FEDERAL
    remuneration_df["valor_subsidio_bruto_total"] = (
        SUBSIDIO_DEPUTADO_FEDERAL * mandate_months
    )
    remuneration_df["fonte_url"] = FONTE_REMUNERACAO_URL
    remuneration_df["data_referencia"] = current_date.isoformat()

    return remuneration_df


def save_remuneration(df: pd.DataFrame) -> Path:
    RAW_CAMARA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_CAMARA_DIR / "remuneracao_deputados_mes_atual.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def save_mandate_remuneration(df: pd.DataFrame) -> Path:
    RAW_CAMARA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_CAMARA_DIR / "remuneracao_deputados_mandato.csv"
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
    monthly_df = build_monthly_remuneration(deputies_df)
    mandate_df = build_mandate_remuneration(deputies_df)
    output_paths = [
        save_remuneration(monthly_df),
        save_mandate_remuneration(mandate_df),
    ]

    print(f"Registros de remuneracao mensal gerados: {len(monthly_df)}")
    print(f"Registros de remuneracao do mandato gerados: {len(mandate_df)}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()
