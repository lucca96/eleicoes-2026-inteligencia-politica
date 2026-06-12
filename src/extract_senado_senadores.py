from __future__ import annotations

import argparse
import time
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

from project_paths import RAW_SENADO_DIR
from senado_client import SenadoApiClient, text_at


CEAPS_URL = "https://www.senado.gov.br/transparencia/LAI/verba/despesa_ceaps_{year}.csv"


def parse_current_senators(client: SenadoApiClient) -> pd.DataFrame:
    root = client.get_xml("/senador/lista/atual")
    rows: list[dict[str, object]] = []

    for senator in root.findall(".//Parlamentar"):
        ident = senator.find("IdentificacaoParlamentar")
        mandate = senator.find("Mandato")
        first_leg = mandate.find("PrimeiraLegislaturaDoMandato") if mandate is not None else None
        second_leg = mandate.find("SegundaLegislaturaDoMandato") if mandate is not None else None

        rows.append(
            {
                "codigoParlamentar": text_at(ident, "CodigoParlamentar"),
                "codigoPublicoLegAtual": text_at(ident, "CodigoPublicoNaLegAtual"),
                "nome": text_at(ident, "NomeParlamentar"),
                "nomeCompleto": text_at(ident, "NomeCompletoParlamentar"),
                "sexo": text_at(ident, "SexoParlamentar"),
                "siglaPartido": text_at(ident, "SiglaPartidoParlamentar"),
                "siglaUf": text_at(ident, "UfParlamentar"),
                "email": text_at(ident, "EmailParlamentar"),
                "urlFoto": text_at(ident, "UrlFotoParlamentar"),
                "urlPagina": text_at(ident, "UrlPaginaParlamentar"),
                "codigoMandato": text_at(mandate, "CodigoMandato"),
                "descricaoParticipacao": text_at(mandate, "DescricaoParticipacao"),
                "primeiraLegislatura": text_at(first_leg, "NumeroLegislatura"),
                "inicioPrimeiraLegislatura": text_at(first_leg, "DataInicio"),
                "fimPrimeiraLegislatura": text_at(first_leg, "DataFim"),
                "segundaLegislatura": text_at(second_leg, "NumeroLegislatura"),
                "inicioSegundaLegislatura": text_at(second_leg, "DataInicio"),
                "fimSegundaLegislatura": text_at(second_leg, "DataFim"),
            }
        )

    df = pd.DataFrame(rows)
    for column in ["codigoParlamentar", "codigoPublicoLegAtual", "codigoMandato"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
    return df.sort_values(["siglaUf", "nome"])


def read_ceaps_year(year: int) -> pd.DataFrame:
    response = requests.get(CEAPS_URL.format(year=year), timeout=120)
    response.raise_for_status()

    raw = BytesIO(response.content)
    try:
        df = pd.read_csv(
            raw,
            sep=";",
            encoding="latin1",
            decimal=",",
            skiprows=1,
            low_memory=False,
        )
    except pd.errors.ParserError:
        raw.seek(0)
        df = pd.read_csv(
            raw,
            sep=";",
            encoding="latin1",
            decimal=",",
            low_memory=False,
        )

    df["ano"] = year
    return df


def normalize_ceaps(expenses_df: pd.DataFrame) -> pd.DataFrame:
    column_map = {
        "ANO": "ano",
        "MES": "mes",
        "SENADOR": "nome",
        "TIPO_DESPESA": "tipoDespesa",
        "CNPJ_CPF": "cnpjCpfFornecedor",
        "FORNECEDOR": "nomeFornecedor",
        "DOCUMENTO": "numDocumento",
        "DATA": "dataDocumento",
        "DETALHAMENTO": "detalhamento",
        "VALOR_REEMBOLSADO": "valorReembolsado",
        "COD_DOCUMENTO": "codDocumento",
    }
    df = expenses_df.rename(columns=column_map)
    expected_columns = [
        "ano",
        "mes",
        "nome",
        "tipoDespesa",
        "cnpjCpfFornecedor",
        "nomeFornecedor",
        "numDocumento",
        "dataDocumento",
        "detalhamento",
        "valorReembolsado",
        "codDocumento",
    ]
    for column in expected_columns:
        if column not in df.columns:
            df[column] = None
    df = df[expected_columns].copy()
    df["valorReembolsado"] = pd.to_numeric(df["valorReembolsado"], errors="coerce")
    return df


def extract_ceaps_mandate(reference_date: date | None = None) -> pd.DataFrame:
    current_date = reference_date or date.today()
    years = range(2023, current_date.year + 1)
    frames: list[pd.DataFrame] = []

    for year in years:
        try:
            frames.append(normalize_ceaps(read_ceaps_year(year)))
        except Exception as exc:
            print(f"[WARN] Falha ao extrair CEAPS {year}: {exc}")

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def extract_senator_votes(
    client: SenadoApiClient,
    senators_df: pd.DataFrame,
    reference_date: date | None = None,
    max_senators: int | None = None,
) -> pd.DataFrame:
    current_date = reference_date or date.today()
    start_date = date(2023, 2, 1)
    rows: list[dict[str, object]] = []

    scoped_senators_df = senators_df.head(max_senators) if max_senators else senators_df
    for index, senator in enumerate(scoped_senators_df.itertuples(index=False), start=1):
        codigo = int(senator.codigoParlamentar)
        try:
            print(f"Extraindo votacoes do senador {index}/{len(scoped_senators_df)}: {codigo}")
            root = client.get_xml(f"/senador/{codigo}/votacoes", sleep_seconds=0.2)
        except Exception as exc:
            print(f"[WARN] Falha ao extrair votacoes do senador {codigo}: {exc}")
            continue

        for vote in root.findall(".//Votacao"):
            data_sessao = text_at(vote, "SessaoPlenaria/DataSessao")
            if data_sessao:
                parsed_date = pd.to_datetime(data_sessao, errors="coerce")
                if pd.isna(parsed_date):
                    continue
                if not (start_date <= parsed_date.date() <= current_date):
                    continue

            rows.append(
                {
                    "codigoParlamentar": codigo,
                    "nome": senator.nome,
                    "siglaPartido": senator.siglaPartido,
                    "siglaUf": senator.siglaUf,
                    "codigoSessao": text_at(vote, "SessaoPlenaria/CodigoSessao"),
                    "dataSessao": data_sessao,
                    "codigoMateria": text_at(vote, "Materia/Codigo"),
                    "descricaoMateria": text_at(vote, "Materia/DescricaoIdentificacao"),
                    "siglaMateria": text_at(vote, "Materia/Sigla"),
                    "numeroMateria": text_at(vote, "Materia/Numero"),
                    "anoMateria": text_at(vote, "Materia/Ano"),
                    "ementaMateria": text_at(vote, "Materia/Ementa"),
                    "codigoSessaoVotacao": text_at(vote, "CodigoSessaoVotacao"),
                    "sequencial": text_at(vote, "Sequencial"),
                    "descricaoVotacao": text_at(vote, "DescricaoVotacao"),
                    "descricaoResultado": text_at(vote, "DescricaoResultado"),
                    "voto": text_at(vote, "SiglaDescricaoVoto"),
                    "descricaoVoto": text_at(vote, "DescricaoVoto"),
                }
            )

    return pd.DataFrame(rows)


def summarize_expenses(senators_df: pd.DataFrame, expenses_df: pd.DataFrame) -> pd.DataFrame:
    if expenses_df.empty:
        return senators_df.assign(qtd_lancamentos=0, valor_reembolsado_total=0)

    summary_df = (
        expenses_df.groupby("nome", as_index=False)
        .agg(
            qtd_lancamentos=("nome", "size"),
            valor_reembolsado_total=("valorReembolsado", "sum"),
        )
    )
    return senators_df.merge(summary_df, on="nome", how="left").fillna(
        {"qtd_lancamentos": 0, "valor_reembolsado_total": 0}
    )


def summarize_votes(senators_df: pd.DataFrame, votes_df: pd.DataFrame) -> pd.DataFrame:
    if votes_df.empty:
        return senators_df.assign(qtd_votos=0, qtd_votacoes=0)

    votes_df = votes_df.copy()
    votes_df["voto_normalizado"] = votes_df["voto"].fillna("").str.upper()
    summary_df = (
        votes_df.groupby("codigoParlamentar", as_index=False)
        .agg(
            qtd_votos=("codigoSessaoVotacao", "size"),
            qtd_votacoes=("codigoSessaoVotacao", "nunique"),
            votos_sim=("voto_normalizado", lambda s: (s == "SIM").sum()),
            votos_nao=("voto_normalizado", lambda s: s.isin(["NAO", "NÃO"]).sum()),
            votos_outros=("voto_normalizado", lambda s: (~s.isin(["SIM", "NAO", "NÃO"])).sum()),
        )
    )
    return senators_df.merge(summary_df, on="codigoParlamentar", how="left").fillna(0)


def save_csv(df: pd.DataFrame, filename: str) -> Path:
    RAW_SENADO_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_SENADO_DIR / filename
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai cadastro, CEAPS e votacoes de senadores.",
    )
    parser.add_argument(
        "--skip-votes",
        action="store_true",
        help="Nao extrai votacoes nominais; util para validar cadastro e CEAPS rapidamente.",
    )
    parser.add_argument(
        "--max-senators",
        type=int,
        default=None,
        help="Limita a quantidade de senadores na extracao de votacoes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = SenadoApiClient()
    senators_df = parse_current_senators(client)
    expenses_df = extract_ceaps_mandate()
    expenses_summary_df = summarize_expenses(senators_df, expenses_df)

    output_paths = [
        save_csv(senators_df, "senadores_em_exercicio.csv"),
        save_csv(expenses_df, "despesas_ceaps_senadores_mandato.csv"),
        save_csv(expenses_summary_df, "resumo_despesas_ceaps_senadores_mandato.csv"),
    ]

    if not args.skip_votes:
        votes_df = extract_senator_votes(
            client,
            senators_df,
            max_senators=args.max_senators,
        )
        votes_summary_df = summarize_votes(senators_df, votes_df)

        if args.max_senators:
            votes_filename = f"votos_senadores_mandato_amostra_{args.max_senators}.csv"
            summary_filename = f"resumo_votos_senadores_mandato_amostra_{args.max_senators}.csv"
        else:
            votes_filename = "votos_senadores_mandato.csv"
            summary_filename = "resumo_votos_senadores_mandato.csv"

        output_paths.extend(
            [
                save_csv(votes_df, votes_filename),
                save_csv(votes_summary_df, summary_filename),
            ]
        )
    else:
        votes_df = pd.DataFrame()

    print(f"Senadores extraidos: {len(senators_df)}")
    print(f"Lancamentos CEAPS extraidos: {len(expenses_df)}")
    print(f"Votos extraidos: {len(votes_df)}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()
