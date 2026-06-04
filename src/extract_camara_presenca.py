from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from project_paths import RAW_CAMARA_DIR
from camara_client import CamaraApiClient
from camara_legislatura import get_current_legislature_id, get_legislature_period


PRESENCE_FILE_URL = (
    "https://dadosabertos.camara.leg.br/arquivos/"
    "eventosPresencaDeputados/csv/eventosPresencaDeputados-{year}.csv"
)


def extract_presence_events(reference_date: date | None = None) -> pd.DataFrame:
    current_date = reference_date or date.today()
    url = PRESENCE_FILE_URL.format(year=current_date.year)

    presence_df = pd.read_csv(url, sep=";", encoding="utf-8-sig", low_memory=False)

    if "dataHoraInicio" not in presence_df.columns:
        raise RuntimeError("CSV de presenca nao possui a coluna dataHoraInicio.")

    presence_df["dataHoraInicio"] = pd.to_datetime(
        presence_df["dataHoraInicio"],
        errors="coerce",
    )
    presence_df = presence_df.dropna(subset=["dataHoraInicio"])
    presence_df["ano"] = presence_df["dataHoraInicio"].dt.year
    presence_df["mes"] = presence_df["dataHoraInicio"].dt.month

    return presence_df.loc[
        (presence_df["ano"] == current_date.year)
        & (presence_df["mes"] == current_date.month)
    ].copy()


def extract_presence_events_for_year(year: int) -> pd.DataFrame:
    url = PRESENCE_FILE_URL.format(year=year)
    presence_df = pd.read_csv(url, sep=";", encoding="utf-8-sig", low_memory=False)

    if "dataHoraInicio" not in presence_df.columns:
        raise RuntimeError("CSV de presenca nao possui a coluna dataHoraInicio.")

    presence_df["dataHoraInicio"] = pd.to_datetime(
        presence_df["dataHoraInicio"],
        errors="coerce",
    )
    presence_df = presence_df.dropna(subset=["dataHoraInicio"])
    presence_df["ano"] = presence_df["dataHoraInicio"].dt.year
    presence_df["mes"] = presence_df["dataHoraInicio"].dt.month
    return presence_df


def extract_mandate_presence_events(
    deputies_df: pd.DataFrame,
    reference_date: date | None = None,
) -> pd.DataFrame:
    current_date = reference_date or date.today()
    client = CamaraApiClient()
    id_legislatura = get_current_legislature_id(deputies_df)
    period = get_legislature_period(client, id_legislatura, current_date)

    yearly_frames: list[pd.DataFrame] = []
    for year in period.years:
        try:
            yearly_frames.append(extract_presence_events_for_year(year))
        except Exception as exc:
            print(f"[WARN] Falha ao extrair presenca de {year}: {exc}")

    if not yearly_frames:
        return pd.DataFrame()

    presence_df = pd.concat(yearly_frames, ignore_index=True)
    return presence_df.loc[
        (presence_df["dataHoraInicio"].dt.date >= period.start_date)
        & (presence_df["dataHoraInicio"].dt.date <= period.end_date)
    ].copy()


def summarize_presence_by_deputy(
    presence_df: pd.DataFrame,
    deputies_df: pd.DataFrame,
) -> pd.DataFrame:
    total_events = int(presence_df["idEvento"].nunique()) if not presence_df.empty else 0
    output_columns = [
        "idDeputado",
        "nome",
        "siglaPartido",
        "siglaUf",
        "qtd_presencas_eventos",
        "qtd_eventos_distintos",
        "primeira_presenca",
        "ultima_presenca",
    ]

    if presence_df.empty:
        return pd.DataFrame(columns=output_columns)

    summary_df = (
        presence_df.groupby("idDeputado", as_index=False)
        .agg(
            qtd_presencas_eventos=("idEvento", "size"),
            qtd_eventos_distintos=("idEvento", "nunique"),
            primeira_presenca=("dataHoraInicio", "min"),
            ultima_presenca=("dataHoraInicio", "max"),
        )
    )

    summary_df["primeira_presenca"] = summary_df["primeira_presenca"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    summary_df["ultima_presenca"] = summary_df["ultima_presenca"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    summary_df["total_eventos_periodo"] = total_events
    summary_df["pct_presenca_eventos"] = summary_df.apply(
        lambda row: (row["qtd_eventos_distintos"] / total_events) * 100
        if total_events > 0
        else 0,
        axis=1,
    )
    max_deputy_events = int(summary_df["qtd_eventos_distintos"].max())
    summary_df["indice_presenca_relativa"] = summary_df.apply(
        lambda row: (row["qtd_eventos_distintos"] / max_deputy_events) * 100
        if max_deputy_events > 0
        else 0,
        axis=1,
    )

    result_df = deputies_df[["id", "nome", "siglaPartido", "siglaUf"]].merge(
        summary_df,
        left_on="id",
        right_on="idDeputado",
        how="left",
    ).drop(columns=["id"])
    result_df["total_eventos_periodo"] = total_events
    result_df["pct_presenca_eventos"] = result_df["pct_presenca_eventos"].fillna(0)
    result_df["indice_presenca_relativa"] = result_df[
        "indice_presenca_relativa"
    ].fillna(0)
    return result_df


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
    presence_df = extract_presence_events()
    summary_df = summarize_presence_by_deputy(presence_df, deputies_df)
    mandate_presence_df = extract_mandate_presence_events(deputies_df)
    mandate_summary_df = summarize_presence_by_deputy(mandate_presence_df, deputies_df)

    output_paths = [
        save_csv(presence_df, "presenca_eventos_deputados_mes_atual.csv"),
        save_csv(summary_df, "resumo_presenca_deputados_mes_atual.csv"),
        save_csv(mandate_presence_df, "presenca_eventos_deputados_mandato.csv"),
        save_csv(mandate_summary_df, "resumo_presenca_deputados_mandato.csv"),
    ]

    print(f"Registros de presenca extraidos: {len(presence_df)}")
    print(f"Registros de presenca do mandato: {len(mandate_presence_df)}")
    print(f"Deputados com presenca registrada: {summary_df['idDeputado'].nunique()}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()
