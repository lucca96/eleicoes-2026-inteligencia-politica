from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

from project_paths import RAW_TSE_DIR


TSE_CDN_BASE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
ELECTION_YEAR = 2022
UF = "RJ"
STATE_DEPUTY_CARGO_CODE = 7


def read_tse_zip(dataset: str, year: int, inner_filename: str) -> pd.DataFrame:
    url = f"{TSE_CDN_BASE}/{dataset}/{dataset}_{year}.zip"
    response = requests.get(url, timeout=180)
    response.raise_for_status()

    with zipfile.ZipFile(BytesIO(response.content)) as zip_file:
        with zip_file.open(inner_filename) as csv_file:
            return pd.read_csv(
                csv_file,
                sep=";",
                encoding="latin1",
                low_memory=False,
            )


def normalize_candidates(candidates_df: pd.DataFrame) -> pd.DataFrame:
    df = candidates_df.loc[
        (candidates_df["SG_UF"].eq(UF))
        & (candidates_df["CD_CARGO"].eq(STATE_DEPUTY_CARGO_CODE))
    ].copy()

    selected_columns = [
        "ANO_ELEICAO",
        "SQ_CANDIDATO",
        "NR_CANDIDATO",
        "NM_URNA_CANDIDATO",
        "NM_CANDIDATO",
        "SG_PARTIDO",
        "NM_PARTIDO",
        "SG_UF",
        "DS_CARGO",
        "DS_SIT_TOT_TURNO",
        "DS_SITUACAO_CANDIDATURA",
        "DS_GENERO",
        "DS_COR_RACA",
        "DS_GRAU_INSTRUCAO",
        "DS_OCUPACAO",
    ]
    for column in selected_columns:
        if column not in df.columns:
            df[column] = None

    df = df[selected_columns].rename(
        columns={
            "ANO_ELEICAO": "anoEleicao",
            "SQ_CANDIDATO": "sequencialCandidato",
            "NR_CANDIDATO": "numeroCandidato",
            "NM_URNA_CANDIDATO": "nomeUrna",
            "NM_CANDIDATO": "nomeCompleto",
            "SG_PARTIDO": "siglaPartido",
            "NM_PARTIDO": "nomePartido",
            "SG_UF": "siglaUf",
            "DS_CARGO": "cargo",
            "DS_SIT_TOT_TURNO": "situacaoTotalTurno",
            "DS_SITUACAO_CANDIDATURA": "situacaoCandidatura",
            "DS_GENERO": "genero",
            "DS_COR_RACA": "corRaca",
            "DS_GRAU_INSTRUCAO": "grauInstrucao",
            "DS_OCUPACAO": "ocupacao",
        }
    )
    status = df["situacaoTotalTurno"].fillna("").str.upper().str.strip()
    df["eleito"] = status.isin(["ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "ELEITO POR MEDIA"])
    return df.sort_values(["eleito", "nomeUrna"], ascending=[False, True])


def normalize_vote_totals(votes_df: pd.DataFrame) -> pd.DataFrame:
    df = votes_df.loc[
        (votes_df["SG_UF"].eq(UF))
        & (votes_df["CD_CARGO"].eq(STATE_DEPUTY_CARGO_CODE))
    ].copy()

    df["QT_VOTOS_NOMINAIS"] = pd.to_numeric(
        df["QT_VOTOS_NOMINAIS"],
        errors="coerce",
    ).fillna(0)

    summary_df = (
        df.groupby("SQ_CANDIDATO", as_index=False)
        .agg(
            votos_nominais=("QT_VOTOS_NOMINAIS", "sum"),
            municipios_com_voto=("NM_MUNICIPIO", "nunique"),
            zonas_com_voto=("NR_ZONA", "nunique"),
        )
        .rename(columns={"SQ_CANDIDATO": "sequencialCandidato"})
    )
    return summary_df


def build_deputados_estaduais_rj_dataset() -> tuple[pd.DataFrame, pd.DataFrame]:
    candidates_raw_df = read_tse_zip(
        "consulta_cand",
        ELECTION_YEAR,
        f"consulta_cand_{ELECTION_YEAR}_{UF}.csv",
    )
    votes_raw_df = read_tse_zip(
        "votacao_candidato_munzona",
        ELECTION_YEAR,
        f"votacao_candidato_munzona_{ELECTION_YEAR}_{UF}.csv",
    )

    candidates_df = normalize_candidates(candidates_raw_df)
    votes_summary_df = normalize_vote_totals(votes_raw_df)
    enriched_df = candidates_df.merge(
        votes_summary_df,
        on="sequencialCandidato",
        how="left",
    ).fillna(
        {
            "votos_nominais": 0,
            "municipios_com_voto": 0,
            "zonas_com_voto": 0,
        }
    )
    elected_df = enriched_df.loc[enriched_df["eleito"]].copy()
    return enriched_df.sort_values("votos_nominais", ascending=False), elected_df


def save_csv(df: pd.DataFrame, filename: str) -> Path:
    RAW_TSE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_TSE_DIR / filename
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    candidates_df, elected_df = build_deputados_estaduais_rj_dataset()
    output_paths = [
        save_csv(candidates_df, "deputados_estaduais_rj_candidatos_2022.csv"),
        save_csv(elected_df, "deputados_estaduais_rj_eleitos_2022.csv"),
    ]

    print(f"Candidatos a deputado estadual RJ extraidos: {len(candidates_df)}")
    print(f"Eleitos deputado estadual RJ extraidos: {len(elected_df)}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()
