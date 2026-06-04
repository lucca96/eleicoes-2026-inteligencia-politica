from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from camara_client import CamaraApiClient
from camara_legislatura import get_current_legislature_id, get_legislature_period
from project_paths import RAW_CAMARA_DIR


FILE_URL = "https://dadosabertos.camara.leg.br/arquivos/{dataset}/csv/{dataset}-{year}.csv"


def read_year_file(dataset: str, year: int) -> pd.DataFrame:
    return pd.read_csv(
        FILE_URL.format(dataset=dataset, year=year),
        sep=";",
        encoding="utf-8-sig",
        low_memory=False,
    )


def extract_pec_votes(
    deputies_df: pd.DataFrame,
    reference_date: date | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    current_date = reference_date or date.today()
    client = CamaraApiClient()
    id_legislatura = get_current_legislature_id(deputies_df)
    period = get_legislature_period(client, id_legislatura, current_date)
    deputy_ids = set(deputies_df["id"].astype(int).tolist())

    votes_frames: list[pd.DataFrame] = []
    vote_meta_frames: list[pd.DataFrame] = []
    vote_props_frames: list[pd.DataFrame] = []

    for year in period.years:
        try:
            props_df = read_year_file("votacoesProposicoes", year)
            pec_props_df = props_df.loc[
                props_df["proposicao_siglaTipo"].fillna("").str.upper().eq("PEC")
            ].copy()

            if pec_props_df.empty:
                continue

            pec_vote_ids = set(pec_props_df["idVotacao"].dropna().astype(str).tolist())
            votes_df = read_year_file("votacoesVotos", year)
            votes_df = votes_df.loc[
                votes_df["idVotacao"].astype(str).isin(pec_vote_ids)
                & votes_df["deputado_id"].isin(deputy_ids)
            ].copy()

            if votes_df.empty:
                continue

            meta_df = read_year_file("votacoes", year)
            meta_df = meta_df.loc[meta_df["id"].astype(str).isin(pec_vote_ids)].copy()

            votes_frames.append(votes_df)
            vote_meta_frames.append(meta_df)
            vote_props_frames.append(pec_props_df)

        except Exception as exc:
            print(f"[WARN] Falha ao extrair votacoes de PEC em {year}: {exc}")

    if not votes_frames:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    votes_df = pd.concat(votes_frames, ignore_index=True)
    meta_df = pd.concat(vote_meta_frames, ignore_index=True).drop_duplicates("id")
    props_df = pd.concat(vote_props_frames, ignore_index=True).drop_duplicates(
        ["idVotacao", "proposicao_id"]
    )

    votes_df = votes_df.merge(
        meta_df[
            [
                "id",
                "data",
                "dataHoraRegistro",
                "siglaOrgao",
                "aprovacao",
                "descricao",
            ]
        ].rename(columns={"id": "idVotacao", "descricao": "descricaoVotacao"}),
        on="idVotacao",
        how="left",
    )
    votes_df = votes_df.merge(
        props_df[
            [
                "idVotacao",
                "proposicao_id",
                "proposicao_titulo",
                "proposicao_ementa",
                "proposicao_siglaTipo",
                "proposicao_numero",
                "proposicao_ano",
            ]
        ],
        on="idVotacao",
        how="left",
    )

    votes_df = votes_df.rename(
        columns={
            "deputado_id": "idDeputado",
            "deputado_nome": "nome",
            "deputado_siglaPartido": "siglaPartido",
            "deputado_siglaUf": "siglaUf",
        }
    )

    summary_df = summarize_pec_votes(votes_df, deputies_df)
    propositions_df = summarize_pec_propositions(votes_df)
    return votes_df, summary_df, propositions_df


def summarize_pec_votes(votes_df: pd.DataFrame, deputies_df: pd.DataFrame) -> pd.DataFrame:
    votes_df["voto_normalizado"] = votes_df["voto"].fillna("").str.upper()
    summary_df = (
        votes_df.groupby("idDeputado", as_index=False)
        .agg(
            qtd_votos_pec=("idVotacao", "size"),
            qtd_votacoes_pec=("idVotacao", "nunique"),
            votos_sim=("voto_normalizado", lambda s: (s == "SIM").sum()),
            votos_nao=("voto_normalizado", lambda s: (s == "NÃO").sum() + (s == "NAO").sum()),
            votos_obstrucao=("voto_normalizado", lambda s: s.str.contains("OBSTRU").sum()),
            votos_outros=("voto_normalizado", lambda s: (~s.isin(["SIM", "NÃO", "NAO"]) & ~s.str.contains("OBSTRU")).sum()),
        )
    )
    summary_df["pct_sim_pec"] = summary_df["votos_sim"] / summary_df["qtd_votos_pec"] * 100
    summary_df["pct_nao_pec"] = summary_df["votos_nao"] / summary_df["qtd_votos_pec"] * 100

    return (
        deputies_df[["id", "nome", "siglaPartido", "siglaUf"]]
        .rename(columns={"id": "idDeputado"})
        .merge(summary_df, on="idDeputado", how="left")
        .fillna(0)
    )


def summarize_pec_propositions(votes_df: pd.DataFrame) -> pd.DataFrame:
    return (
        votes_df.groupby(
            [
                "idVotacao",
                "data",
                "proposicao_id",
                "proposicao_titulo",
                "proposicao_ementa",
            ],
            as_index=False,
        )
        .agg(
            votos_registrados=("idDeputado", "nunique"),
            votos_sim=("voto", lambda s: s.fillna("").str.upper().eq("SIM").sum()),
            votos_nao=("voto", lambda s: s.fillna("").str.upper().isin(["NÃO", "NAO"]).sum()),
        )
        .sort_values("data", ascending=False)
    )


def save_csv(df: pd.DataFrame, filename: str) -> Path:
    RAW_CAMARA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_CAMARA_DIR / filename
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def main() -> None:
    deputies_path = RAW_CAMARA_DIR / "deputados_em_exercicio.csv"
    if not deputies_path.exists():
        raise FileNotFoundError("Execute src/extract_camara_deputados.py antes.")

    deputies_df = pd.read_csv(deputies_path)
    votes_df, summary_df, propositions_df = extract_pec_votes(deputies_df)
    output_paths = [
        save_csv(votes_df, "votos_pec_deputados_mandato.csv"),
        save_csv(summary_df, "resumo_votos_pec_deputados_mandato.csv"),
        save_csv(propositions_df, "resumo_votacoes_pec_mandato.csv"),
    ]

    print(f"Votos em PECs extraidos: {len(votes_df)}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()

