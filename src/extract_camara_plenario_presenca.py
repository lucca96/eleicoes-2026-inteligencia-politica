from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from camara_client import CamaraApiClient
from camara_legislatura import get_current_legislature_id, get_legislature_period
from project_paths import RAW_CAMARA_DIR


DEPUTIES_LEGACY_URL = "https://www.camara.gov.br/SitCamaraWS/Deputados.asmx/ObterDeputados"
PLENARY_PRESENCE_URL = (
    "https://www.camara.gov.br/SitCamaraWS/SessoesReunioes.asmx/"
    "ListarPresencasParlamentar"
)


def parse_text(node: ET.Element | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def br_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def load_legacy_deputy_registry() -> pd.DataFrame:
    response = requests.get(DEPUTIES_LEGACY_URL, timeout=120)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    rows = []
    for deputy in root.findall(".//deputado"):
        rows.append(
            {
                "idDeputado": int(parse_text(deputy.find("ideCadastro")) or 0),
                "matricula": int(parse_text(deputy.find("matricula")) or 0),
                "nomeParlamentarLegado": parse_text(deputy.find("nomeParlamentar")),
                "siglaPartidoLegado": parse_text(deputy.find("partido")),
                "siglaUfLegado": parse_text(deputy.find("uf")),
            }
        )

    return pd.DataFrame(rows)


def fetch_plenary_presence(
    matricula: int,
    start_date: date,
    end_date: date,
) -> list[dict[str, object]]:
    response = requests.get(
        PLENARY_PRESENCE_URL,
        params={
            "dataIni": br_date(start_date),
            "dataFim": br_date(end_date),
            "numMatriculaParlamentar": matricula,
        },
        timeout=120,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    rows: list[dict[str, object]] = []

    for day in root.findall(".//dia"):
        status_day = parse_text(day.find("frequencianoDia"))
        justification = parse_text(day.find("justificativa"))
        sessions = day.findall(".//sessao")

        if sessions:
            for session in sessions:
                rows.append(
                    {
                        "matricula": matricula,
                        "data": parse_text(day.find("data")),
                        "frequencia_dia": status_day,
                        "justificativa": justification,
                        "descricao_sessao": parse_text(session.find("descricao")),
                        "frequencia_sessao": parse_text(session.find("frequencia")),
                    }
                )
        else:
            rows.append(
                {
                    "matricula": matricula,
                    "data": parse_text(day.find("data")),
                    "frequencia_dia": status_day,
                    "justificativa": justification,
                    "descricao_sessao": "",
                    "frequencia_sessao": status_day,
                }
            )

    return rows


def classify_presence(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    status = df["frequencia_sessao"].fillna("").str.lower()
    justification = df["justificativa"].fillna("").str.strip()
    df["presente_plenario"] = status.str.contains("presen")
    df["ausente_plenario"] = ~df["presente_plenario"]
    df["ausencia_justificada"] = df["ausente_plenario"] & justification.ne("")
    df["ausencia_nao_justificada"] = df["ausente_plenario"] & justification.eq("")
    return df


def summarize_absences(plenary_df: pd.DataFrame, deputies_df: pd.DataFrame) -> pd.DataFrame:
    if plenary_df.empty:
        return pd.DataFrame()

    summary_df = (
        plenary_df.groupby("idDeputado", as_index=False)
        .agg(
            qtd_sessoes_plenario=("idDeputado", "size"),
            qtd_presencas_plenario=("presente_plenario", "sum"),
            qtd_ausencias_plenario=("ausente_plenario", "sum"),
            qtd_ausencias_justificadas=("ausencia_justificada", "sum"),
            qtd_ausencias_nao_justificadas=("ausencia_nao_justificada", "sum"),
        )
    )

    for column in [
        "qtd_presencas_plenario",
        "qtd_ausencias_plenario",
        "qtd_ausencias_justificadas",
        "qtd_ausencias_nao_justificadas",
    ]:
        summary_df[column] = summary_df[column].astype(int)

    summary_df["pct_presenca_plenario"] = (
        summary_df["qtd_presencas_plenario"] / summary_df["qtd_sessoes_plenario"] * 100
    )
    summary_df["pct_ausencia_justificada"] = summary_df.apply(
        lambda row: row["qtd_ausencias_justificadas"] / row["qtd_ausencias_plenario"] * 100
        if row["qtd_ausencias_plenario"] > 0
        else 0,
        axis=1,
    )
    summary_df["pct_ausencia_nao_justificada"] = summary_df.apply(
        lambda row: row["qtd_ausencias_nao_justificadas"] / row["qtd_ausencias_plenario"] * 100
        if row["qtd_ausencias_plenario"] > 0
        else 0,
        axis=1,
    )

    return (
        deputies_df[["id", "nome", "siglaPartido", "siglaUf"]]
        .rename(columns={"id": "idDeputado"})
        .merge(summary_df, on="idDeputado", how="left")
        .fillna(0)
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
    client = CamaraApiClient()
    id_legislatura = get_current_legislature_id(deputies_df)
    period = get_legislature_period(client, id_legislatura)
    registry_df = load_legacy_deputy_registry()
    registry_df = registry_df.merge(
        deputies_df[["id"]].rename(columns={"id": "idDeputado"}),
        on="idDeputado",
        how="inner",
    )

    rows: list[dict[str, object]] = []
    for item in registry_df.itertuples(index=False):
        try:
            rows.extend(
                fetch_plenary_presence(
                    int(item.matricula),
                    period.start_date,
                    period.end_date,
                )
            )
        except Exception as exc:
            print(f"[WARN] Falha em matricula {item.matricula}: {exc}")
        time.sleep(0.05)

    plenary_df = pd.DataFrame(rows)
    if not plenary_df.empty:
        plenary_df = plenary_df.merge(
            registry_df[["idDeputado", "matricula"]],
            on="matricula",
            how="left",
        )
        plenary_df = classify_presence(plenary_df)

    summary_df = summarize_absences(plenary_df, deputies_df)
    output_paths = [
        save_csv(plenary_df, "presenca_plenario_deputados_mandato.csv"),
        save_csv(summary_df, "resumo_presenca_plenario_deputados_mandato.csv"),
    ]

    print(f"Registros de plenario extraidos: {len(plenary_df)}")
    print("Arquivos gerados:")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()

