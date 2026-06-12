from __future__ import annotations

import json
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

from project_paths import RAW_ALERJ_DIR, RAW_CAMARA_DIR, RAW_SENADO_DIR, RAW_TSE_DIR, REPORTS_DIR


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def first_existing_csv(paths: list[Path]) -> pd.DataFrame:
    for path in paths:
        df = read_csv_if_exists(path)
        if not df.empty:
            return df
    return pd.DataFrame()


def number_or_zero(value: object) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def latest_data_update_label() -> str:
    paths = list(RAW_CAMARA_DIR.glob("*.csv"))
    if not paths:
        return "sem data local"
    latest_mtime = max(path.stat().st_mtime for path in paths)
    return datetime.fromtimestamp(latest_mtime).strftime("%d/%m/%Y")


def add_group_differences(report_df: pd.DataFrame, group_column: str, suffix: str) -> pd.DataFrame:
    metrics = ["valor_liquido_total", "indice_presenca_relativa"]
    means_df = (
        report_df.groupby(group_column, as_index=False)[metrics]
        .mean()
        .rename(
            columns={
                "valor_liquido_total": f"media_gasto_{suffix}",
                "indice_presenca_relativa": f"media_presenca_{suffix}",
            }
        )
    )
    report_df = report_df.merge(means_df, on=group_column, how="left")
    report_df[f"dif_gasto_media_{suffix}"] = (
        report_df["valor_liquido_total"] - report_df[f"media_gasto_{suffix}"]
    )
    report_df[f"dif_presenca_media_{suffix}"] = (
        report_df["indice_presenca_relativa"] - report_df[f"media_presenca_{suffix}"]
    )
    return report_df


def build_category_dataset() -> pd.DataFrame:
    category_df = read_csv_if_exists(RAW_CAMARA_DIR / "resumo_gastos_categoria_mandato.csv")
    if category_df.empty:
        return category_df

    def normalize_category(value: object) -> str:
        text = str(value or "").upper()
        if "DIVULGA" in text:
            return "Divulgação parlamentar"
        if "VEÍCULO" in text or "VEICULO" in text or "FRETAMENTO" in text:
            return "Locação e transporte"
        if "PASSAGEM AÉREA" in text or "PASSAGEM AEREA" in text:
            return "Passagens aéreas"
        if "PASSAGENS TERRESTRES" in text:
            return "Passagens terrestres e fluviais"
        if "ESCRITÓRIO" in text or "ESCRITORIO" in text:
            return "Escritório de apoio"
        if "COMBUST" in text:
            return "Combustíveis"
        if "HOSPEDAGEM" in text:
            return "Hospedagem"
        if "TELEFONIA" in text:
            return "Telefonia"
        if "SEGURANÇA" in text or "SEGURANCA" in text:
            return "Segurança"
        if "TÁXI" in text or "TAXI" in text or "PEDÁGIO" in text or "PEDAGIO" in text:
            return "Táxi, pedágio e estacionamento"
        if "ALIMENTAÇÃO" in text or "ALIMENTACAO" in text:
            return "Alimentação"
        if "PUBLICA" in text:
            return "Publicações"
        if "POSTAIS" in text:
            return "Serviços postais"
        if "CURSO" in text or "PALESTRA" in text or "EVENTO" in text:
            return "Cursos e eventos"
        if "TOKEN" in text or "CERTIFICADO" in text:
            return "Certificados digitais"
        return "Outros"

    category_df["categoria_tratada"] = category_df["tipoDespesa"].map(normalize_category)
    grouped_df = (
        category_df.groupby("categoria_tratada", as_index=False)
        .agg(
            qtd_lancamentos=("qtd_lancamentos", "sum"),
            valor_liquido_total=("valor_liquido_total", "sum"),
        )
        .sort_values("valor_liquido_total", ascending=False)
    )
    total_value = grouped_df["valor_liquido_total"].sum()
    grouped_df["share_gasto_pct"] = grouped_df.apply(
        lambda row: row["valor_liquido_total"] / total_value * 100
        if total_value > 0
        else 0,
        axis=1,
    )
    return grouped_df


def build_party_dataset(report_df: pd.DataFrame) -> pd.DataFrame:
    party_df = (
        report_df.groupby("siglaPartido", as_index=False)
        .agg(
            qtd_candidatos=("idDeputado", "nunique"),
            gasto_total=("valor_liquido_total", "sum"),
            remuneracao_total=("valor_subsidio_bruto_total", "sum"),
            custo_total=("custo_total_estimado", "sum"),
            presenca_media=("indice_presenca_relativa", "mean"),
            ausencia_nao_just_media=("pct_ausencia_nao_justificada", "mean"),
            votacoes_pec=("qtd_votacoes_pec", "sum"),
        )
        .assign(
            gasto_medio_por_candidato=lambda df: df["gasto_total"]
            / df["qtd_candidatos"].replace(0, 1)
        )
    )
    total_deputies = party_df["qtd_candidatos"].sum()
    total_cost = party_df["custo_total"].sum()
    party_df["share_deputados_pct"] = party_df.apply(
        lambda row: row["qtd_candidatos"] / total_deputies * 100
        if total_deputies > 0
        else 0,
        axis=1,
    )
    party_df["share_custo_pct"] = party_df.apply(
        lambda row: row["custo_total"] / total_cost * 100 if total_cost > 0 else 0,
        axis=1,
    )
    party_df["custo_por_deputado"] = (
        party_df["custo_total"] / party_df["qtd_candidatos"].replace(0, 1)
    )
    party_df["pecs_por_deputado"] = (
        party_df["votacoes_pec"] / party_df["qtd_candidatos"].replace(0, 1)
    )
    return party_df.sort_values("custo_por_deputado", ascending=False)


def build_pec_vote_detail_dataset() -> pd.DataFrame:
    votes_df = read_csv_if_exists(RAW_CAMARA_DIR / "votos_pec_deputados_mandato.csv")
    if votes_df.empty:
        return pd.DataFrame()

    expected_columns = [
        "idDeputado",
        "nome",
        "siglaPartido",
        "siglaUf",
        "data",
        "voto",
        "proposicao_titulo",
        "proposicao_ementa",
        "descricaoVotacao",
        "siglaOrgao",
    ]
    for column in expected_columns:
        if column not in votes_df.columns:
            votes_df[column] = ""

    detail_df = votes_df[expected_columns].copy()
    detail_df["proposicao_titulo"] = detail_df["proposicao_titulo"].fillna("PEC")
    detail_df["proposicao_ementa"] = detail_df["proposicao_ementa"].fillna("")
    detail_df["descricaoVotacao"] = detail_df["descricaoVotacao"].fillna("")
    detail_df["voto_normalizado"] = detail_df["voto"].fillna("").str.upper()
    detail_df["voto_grupo"] = detail_df["voto_normalizado"].replace(
        {"NÃO": "NAO", "OBSTRUÇÃO": "OBSTRUCAO"}
    )

    grouped_df = (
        detail_df.groupby(
            [
                "idDeputado",
                "nome",
                "siglaPartido",
                "siglaUf",
                "proposicao_titulo",
            ],
            as_index=False,
        )
        .agg(
            data_ultima=("data", "max"),
            siglaOrgao=("siglaOrgao", "last"),
            ementa_curta=("proposicao_ementa", lambda s: str(s.iloc[0])[:260]),
            qtd_votacoes=("voto", "size"),
            votos_sim=("voto_grupo", lambda s: (s == "SIM").sum()),
            votos_nao=("voto_grupo", lambda s: (s == "NAO").sum()),
            votos_obstrucao=("voto_grupo", lambda s: s.str.contains("OBSTRU").sum()),
            votos_outros=(
                "voto_grupo",
                lambda s: (~s.isin(["SIM", "NAO"]) & ~s.str.contains("OBSTRU")).sum(),
            ),
        )
    )

    vote_columns = ["votos_sim", "votos_nao", "votos_obstrucao", "votos_outros"]
    vote_labels = {
        "votos_sim": "Sim",
        "votos_nao": "Não",
        "votos_obstrucao": "Obstrução",
        "votos_outros": "Outros",
    }
    grouped_df["voto_predominante"] = grouped_df[vote_columns].idxmax(axis=1).map(
        vote_labels
    )

    return grouped_df.sort_values(
        ["data_ultima", "proposicao_titulo", "nome"],
        ascending=False,
    )


def build_report_dataset() -> pd.DataFrame:
    expenses_df = first_existing_csv(
        [
            RAW_CAMARA_DIR / "resumo_despesas_deputados_mandato.csv",
            RAW_CAMARA_DIR / "resumo_despesas_deputados_mes_atual.csv",
        ]
    )
    remuneration_df = first_existing_csv(
        [
            RAW_CAMARA_DIR / "remuneracao_deputados_mandato.csv",
            RAW_CAMARA_DIR / "remuneracao_deputados_mes_atual.csv",
        ]
    )
    presence_df = first_existing_csv(
        [
            RAW_CAMARA_DIR / "resumo_presenca_deputados_mandato.csv",
            RAW_CAMARA_DIR / "resumo_presenca_deputados_mes_atual.csv",
        ]
    )
    plenary_df = read_csv_if_exists(
        RAW_CAMARA_DIR / "resumo_presenca_plenario_deputados_mandato.csv"
    )
    pec_votes_df = read_csv_if_exists(
        RAW_CAMARA_DIR / "resumo_votos_pec_deputados_mandato.csv"
    )
    yoy_df = read_csv_if_exists(RAW_CAMARA_DIR / "despesas_yoy_deputados_mandato.csv")

    if expenses_df.empty:
        raise FileNotFoundError(
            "Resumo de despesas nao encontrado. Execute "
            "src/extract_camara_deputados.py ou src/extract_camara_mandato.py antes."
        )

    report_df = expenses_df.copy()
    if "id" in report_df.columns:
        report_df = report_df.rename(columns={"id": "idDeputado"})

    if not remuneration_df.empty:
        if "valor_subsidio_bruto_total" in remuneration_df.columns:
            salary_columns = [
                "idDeputado",
                "valor_subsidio_mensal",
                "valor_subsidio_bruto_total",
                "meses_considerados",
                "tipo_remuneracao",
                "fonte_url",
            ]
            report_df = report_df.merge(
                remuneration_df[[column for column in salary_columns if column in remuneration_df.columns]],
                on="idDeputado",
                how="left",
            )
        else:
            report_df = report_df.merge(
                remuneration_df[
                    ["idDeputado", "valor_subsidio_bruto", "tipo_remuneracao", "fonte_url"]
                ],
                on="idDeputado",
                how="left",
            )
            report_df["valor_subsidio_bruto_total"] = report_df["valor_subsidio_bruto"]
    else:
        report_df["valor_subsidio_bruto_total"] = 0.0

    if not presence_df.empty:
        presence_columns = [
            "idDeputado",
            "qtd_presencas_eventos",
            "qtd_eventos_distintos",
            "total_eventos_periodo",
            "pct_presenca_eventos",
            "indice_presenca_relativa",
        ]
        report_df = report_df.merge(
            presence_df[[column for column in presence_columns if column in presence_df.columns]],
            on="idDeputado",
            how="left",
        )
    else:
        report_df["qtd_presencas_eventos"] = 0
        report_df["qtd_eventos_distintos"] = 0
        report_df["total_eventos_periodo"] = 0
        report_df["pct_presenca_eventos"] = 0.0
        report_df["indice_presenca_relativa"] = 0.0

    if not yoy_df.empty:
        report_df = report_df.merge(yoy_df, on="idDeputado", how="left")

    if not plenary_df.empty:
        plenary_columns = [
            "idDeputado",
            "qtd_sessoes_plenario",
            "qtd_presencas_plenario",
            "qtd_ausencias_plenario",
            "qtd_ausencias_justificadas",
            "qtd_ausencias_nao_justificadas",
            "pct_presenca_plenario",
            "pct_ausencia_justificada",
            "pct_ausencia_nao_justificada",
        ]
        report_df = report_df.merge(
            plenary_df[[column for column in plenary_columns if column in plenary_df.columns]],
            on="idDeputado",
            how="left",
        )

    if not pec_votes_df.empty:
        pec_columns = [
            "idDeputado",
            "qtd_votos_pec",
            "qtd_votacoes_pec",
            "votos_sim",
            "votos_nao",
            "votos_obstrucao",
            "votos_outros",
            "pct_sim_pec",
            "pct_nao_pec",
        ]
        report_df = report_df.merge(
            pec_votes_df[[column for column in pec_columns if column in pec_votes_df.columns]],
            on="idDeputado",
            how="left",
        )

    numeric_columns = [
        "qtd_lancamentos",
        "valor_documento_total",
        "valor_glosa_total",
        "valor_liquido_total",
        "valor_subsidio_bruto_total",
        "qtd_presencas_eventos",
        "qtd_eventos_distintos",
        "total_eventos_periodo",
        "pct_presenca_eventos",
        "indice_presenca_relativa",
        "gasto_ytd_ano_atual",
        "gasto_ytd_ano_anterior",
        "diferenca_yoy",
        "variacao_yoy_pct",
        "qtd_sessoes_plenario",
        "qtd_presencas_plenario",
        "qtd_ausencias_plenario",
        "qtd_ausencias_justificadas",
        "qtd_ausencias_nao_justificadas",
        "pct_presenca_plenario",
        "pct_ausencia_justificada",
        "pct_ausencia_nao_justificada",
        "qtd_votos_pec",
        "qtd_votacoes_pec",
        "votos_sim",
        "votos_nao",
        "votos_obstrucao",
        "votos_outros",
        "pct_sim_pec",
        "pct_nao_pec",
    ]

    for column in numeric_columns:
        if column not in report_df.columns:
            report_df[column] = 0.0
        report_df[column] = report_df[column].fillna(0)

    report_df["custo_total_estimado"] = (
        report_df["valor_liquido_total"] + report_df["valor_subsidio_bruto_total"]
    )

    report_df["custo_por_presenca"] = report_df.apply(
        lambda row: number_or_zero(row["custo_total_estimado"])
        / number_or_zero(row["qtd_presencas_eventos"])
        if number_or_zero(row["qtd_presencas_eventos"]) > 0
        else 0.0,
        axis=1,
    )

    report_df = add_group_differences(report_df, "siglaPartido", "partido")
    report_df = add_group_differences(report_df, "siglaUf", "uf")
    media_gasto_candidato = report_df["valor_liquido_total"].mean()
    media_presenca_candidato = report_df["indice_presenca_relativa"].mean()
    report_df["dif_gasto_media_candidato"] = (
        report_df["valor_liquido_total"] - media_gasto_candidato
    )
    report_df["dif_presenca_media_candidato"] = (
        report_df["indice_presenca_relativa"] - media_presenca_candidato
    )

    return report_df.sort_values("custo_total_estimado", ascending=False)


def render_html(report_df: pd.DataFrame) -> str:
    records = report_df.to_dict(orient="records")
    categories_df = build_category_dataset()
    category_records = categories_df.to_dict(orient="records") if not categories_df.empty else []
    party_records = build_party_dataset(report_df).to_dict(orient="records")
    pec_vote_df = build_pec_vote_detail_dataset()
    pec_vote_records = pec_vote_df.to_dict(orient="records")
    pec_options = (
        sorted(pec_vote_df["proposicao_titulo"].dropna().unique().tolist())
        if not pec_vote_df.empty
        else []
    )
    states = sorted(report_df["siglaUf"].dropna().unique().tolist())
    parties = sorted(report_df["siglaPartido"].dropna().unique().tolist())
    data_updated_label = latest_data_update_label()
    senate_expenses_df = read_csv_if_exists(
        RAW_SENADO_DIR / "resumo_despesas_ceaps_senadores_mandato.csv"
    )
    senate_votes_df = read_csv_if_exists(
        RAW_SENADO_DIR / "resumo_votos_senadores_mandato.csv"
    )
    if not senate_expenses_df.empty and not senate_votes_df.empty:
        vote_columns = [
            "codigoParlamentar",
            "qtd_votos",
            "qtd_votacoes",
            "votos_sim",
            "votos_nao",
            "votos_outros",
        ]
        senate_df = senate_expenses_df.merge(
            senate_votes_df[[column for column in vote_columns if column in senate_votes_df.columns]],
            on="codigoParlamentar",
            how="left",
        )
    else:
        senate_df = senate_expenses_df.copy()
    for column in [
        "qtd_lancamentos",
        "valor_reembolsado_total",
        "qtd_votos",
        "qtd_votacoes",
        "votos_sim",
        "votos_nao",
        "votos_outros",
    ]:
        if column not in senate_df.columns:
            senate_df[column] = 0
        if not senate_df.empty:
            senate_df[column] = senate_df[column].fillna(0)
    if not senate_df.empty and float(senate_df["valor_reembolsado_total"].sum()) == 0:
        senate_expense_detail_df = read_csv_if_exists(
            RAW_SENADO_DIR / "despesas_ceaps_senadores_mandato.csv"
        )
        if not senate_expense_detail_df.empty and "valorReembolsado" in senate_expense_detail_df.columns:
            def normalize_name(value: object) -> str:
                text = unicodedata.normalize("NFKD", str(value or ""))
                text = "".join(char for char in text if not unicodedata.combining(char))
                return " ".join(text.upper().split())

            senate_df["_nome_norm"] = senate_df["nome"].map(normalize_name)
            detail_df = senate_expense_detail_df.copy()
            detail_df["_nome_norm"] = detail_df["nome"].map(normalize_name)
            detail_df["valorReembolsado"] = pd.to_numeric(
                detail_df["valorReembolsado"],
                errors="coerce",
            ).fillna(0)
            grouped_expenses_df = (
                detail_df.groupby("_nome_norm", as_index=False)
                .agg(
                    qtd_lancamentos_calc=("valorReembolsado", "size"),
                    valor_reembolsado_total_calc=("valorReembolsado", "sum"),
                )
            )
            senate_df = senate_df.merge(grouped_expenses_df, on="_nome_norm", how="left")
            senate_df["qtd_lancamentos"] = senate_df["qtd_lancamentos_calc"].fillna(
                senate_df["qtd_lancamentos"]
            )
            senate_df["valor_reembolsado_total"] = senate_df[
                "valor_reembolsado_total_calc"
            ].fillna(senate_df["valor_reembolsado_total"])
            senate_df = senate_df.drop(
                columns=[
                    "_nome_norm",
                    "qtd_lancamentos_calc",
                    "valor_reembolsado_total_calc",
                ],
                errors="ignore",
            )

    rj_elected_df = read_csv_if_exists(
        RAW_TSE_DIR / "deputados_estaduais_rj_eleitos_2022.csv"
    )
    for column in ["votos_nominais", "municipios_com_voto", "zonas_com_voto"]:
        if column not in rj_elected_df.columns:
            rj_elected_df[column] = 0
        if not rj_elected_df.empty:
            rj_elected_df[column] = rj_elected_df[column].fillna(0)

    alerj_deputies_df = read_csv_if_exists(
        RAW_ALERJ_DIR / "deputados_estaduais_rj_alerj_em_exercicio.csv"
    )
    alerj_sources_df = read_csv_if_exists(
        RAW_ALERJ_DIR / "alerj_fontes_transparencia_e_legislativo.csv"
    )
    alerj_pdfs_df = read_csv_if_exists(
        RAW_ALERJ_DIR / "alerj_anuario_atividade_legislativa_pdfs.csv"
    )
    rj_expense_df = read_csv_if_exists(
        RAW_ALERJ_DIR / "docigp_resumo_gastos_deputados_estaduais_rj.csv"
    )
    rj_expense_category_df = read_csv_if_exists(
        RAW_ALERJ_DIR / "docigp_resumo_gastos_categoria_deputados_estaduais_rj.csv"
    )
    for column in [
        "valorGastoParlamentar",
        "qtdLancamentos",
        "qtdCategorias",
        "qtdFornecedores",
        "valorLimitePeriodo",
        "qtdMesesComOrcamento",
        "usoLimitePct",
    ]:
        if column not in rj_expense_df.columns:
            rj_expense_df[column] = 0
        if not rj_expense_df.empty:
            rj_expense_df[column] = pd.to_numeric(rj_expense_df[column], errors="coerce").fillna(0)
    for column in ["valorGastoParlamentar", "qtdLancamentos", "shareGastoPct"]:
        if column not in rj_expense_category_df.columns:
            rj_expense_category_df[column] = 0
        if not rj_expense_category_df.empty:
            rj_expense_category_df[column] = pd.to_numeric(
                rj_expense_category_df[column], errors="coerce"
            ).fillna(0)

    def compact_money(value: float) -> str:
        abs_value = abs(value)
        def scaled_label(divisor: float, suffix: str, decimals: int) -> str:
            scaled = value / divisor
            text = f"{scaled:,.{decimals}f}"
            text = text.rstrip("0").rstrip(".")
            text = text.replace(",", "X").replace(".", ",").replace("X", ".")
            return f"R$ {text} {suffix}"

        if abs_value >= 1_000_000_000:
            return scaled_label(1_000_000_000, "bi", 3)
        if abs_value >= 1_000_000:
            return scaled_label(1_000_000, "mi", 3)
        if abs_value >= 1_000:
            return scaled_label(1_000, "mil", 1)
        return f"R$ {value:,.0f}".replace(",", ".")

    initial_kpis = {
        "deputies": f"{len(report_df):,}".replace(",", "."),
        "expenses": compact_money(float(report_df["valor_liquido_total"].sum())),
        "salary": compact_money(float(report_df["valor_subsidio_bruto_total"].sum())),
        "cost": compact_money(float(report_df["custo_total_estimado"].sum())),
        "presence": f"{report_df['indice_presenca_relativa'].mean():.1f}%".replace(".", ","),
        "yoy": compact_money(float(report_df["diferenca_yoy"].sum())),
        "unjustified_absence": f"{report_df['pct_ausencia_nao_justificada'].mean():.1f}%".replace(".", ","),
        "pec_votes": f"{int(report_df['qtd_votacoes_pec'].sum()):,}".replace(",", "."),
        "expense_yoy": compact_money(float(report_df["diferenca_yoy"].sum())),
    }

    data_json = json.dumps(records, ensure_ascii=False)
    categories_json = json.dumps(category_records, ensure_ascii=False)
    party_json = json.dumps(party_records, ensure_ascii=False)
    pec_vote_json = json.dumps(pec_vote_records, ensure_ascii=False)
    pec_options_json = json.dumps(pec_options, ensure_ascii=False)
    states_json = json.dumps(states, ensure_ascii=False)
    parties_json = json.dumps(parties, ensure_ascii=False)
    senate_json = json.dumps(senate_df.to_dict(orient="records"), ensure_ascii=False)
    rj_elected_json = json.dumps(rj_elected_df.to_dict(orient="records"), ensure_ascii=False)
    rj_expense_json = json.dumps(rj_expense_df.to_dict(orient="records"), ensure_ascii=False)
    rj_expense_category_json = json.dumps(
        rj_expense_category_df.to_dict(orient="records"),
        ensure_ascii=False,
    )
    alerj_deputies_json = json.dumps(alerj_deputies_df.to_dict(orient="records"), ensure_ascii=False)
    alerj_sources_json = json.dumps(alerj_sources_df.to_dict(orient="records"), ensure_ascii=False)
    alerj_pdfs_json = json.dumps(alerj_pdfs_df.to_dict(orient="records"), ensure_ascii=False)
    senate_kpis = {
        "senators": f"{len(senate_df):,}".replace(",", "."),
        "ceaps": compact_money(float(senate_df["valor_reembolsado_total"].sum()) if not senate_df.empty else 0),
        "votes": f"{int(senate_df['qtd_votos'].sum()) if not senate_df.empty else 0:,}".replace(",", "."),
        "avg_ceaps": compact_money(float(senate_df["valor_reembolsado_total"].mean()) if not senate_df.empty else 0),
    }
    rj_kpis = {
        "elected": f"{len(rj_elected_df):,}".replace(",", "."),
        "votes": f"{int(rj_elected_df['votos_nominais'].sum()) if not rj_elected_df.empty else 0:,}".replace(",", "."),
        "top_votes": f"{int(rj_elected_df['votos_nominais'].max()) if not rj_elected_df.empty else 0:,}".replace(",", "."),
        "parties": f"{rj_elected_df['siglaPartido'].nunique() if not rj_elected_df.empty else 0:,}".replace(",", "."),
    }
    rj_expense_kpis = {
        "deputies": f"{len(rj_expense_df):,}".replace(",", "."),
        "spending": compact_money(float(rj_expense_df["valorGastoParlamentar"].sum()) if not rj_expense_df.empty else 0),
        "entries": f"{int(rj_expense_df['qtdLancamentos'].sum()) if not rj_expense_df.empty else 0:,}".replace(",", "."),
        "avg": compact_money(float(rj_expense_df["valorGastoParlamentar"].mean()) if not rj_expense_df.empty else 0),
    }
    alerj_kpis = {
        "deputies": f"{len(alerj_deputies_df):,}".replace(",", "."),
        "sources": f"{len(alerj_sources_df):,}".replace(",", "."),
        "pdfs": f"{len(alerj_pdfs_df):,}".replace(",", "."),
    }

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Painel de Inteligencia Politica 2026</title>
  <style>
    @import url('https://fonts.cdnfonts.com/css/rawline');
    :root {{
      --bg: #f7f9fb;
      --panel: #ffffff;
      --ink: #1b1b1b;
      --muted: #5d6873;
      --line: #dfe5ec;
      --gov-blue: #1351b4;
      --gov-blue-dark: #071d41;
      --gov-blue-soft: #eaf2ff;
      --gov-green: #168821;
      --gov-yellow: #ffcd07;
      --gov-cyan: #0c326f;
      --red: #b91c1c;
      --radius: 8px;
      --shadow: 0 8px 20px rgba(7, 29, 65, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    html {{
      width: 100%;
      scroll-behavior: smooth;
      scroll-padding-top: var(--sticky-offset, 150px);
      -webkit-text-size-adjust: 100%;
    }}
    body {{
      width: 100%;
      min-width: 0;
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Rawline, Raleway, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow-x: clip;
    }}
    img, svg, canvas, table, input, select, textarea, button {{
      max-width: 100%;
    }}
    p, h1, h2, h3, span, strong, label, .notice, .source-line, .metric-label, .metric-value, .metric-sub, .pec-desc {{
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .govbar {{
      min-height: 44px;
      background: #ffffff;
      color: var(--gov-blue-dark);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 28px;
      font-size: 13px;
      font-weight: 650;
      border-bottom: 1px solid var(--line);
    }}
    .govbar span:first-child {{ color: var(--gov-blue); }}
    .govbar span:last-child {{ color: var(--muted); font-weight: 500; }}
    header {{
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    .brand-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      min-height: 62px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
    }}
    .gov-logo {{
      width: 112px;
      height: auto;
      display: block;
    }}
    .brand-meta {{
      color: var(--muted);
      font-size: 13px;
      text-align: right;
    }}
    .author-meta {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .author-meta strong {{
      color: var(--gov-blue-dark);
      font-size: 12px;
      font-weight: 720;
    }}
    .author-meta a {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      color: var(--gov-blue);
      font-size: 12px;
      font-weight: 680;
      text-decoration: none;
    }}
    .author-meta a:hover {{ text-decoration: underline; }}
    .linkedin-icon {{
      width: 15px;
      height: 15px;
      display: inline-block;
      color: #0a66c2;
    }}
    .hero {{
      width: 100%;
      max-width: 1380px;
      margin: 0 auto;
      padding: 24px 28px 18px;
      min-width: 0;
    }}
    .eyebrow {{
      color: var(--gov-blue);
      font-size: 12px;
      font-weight: 760;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    h1 {{
      margin: 18px 0 0;
      font-size: 30px;
      font-weight: 780;
      letter-spacing: 0;
      color: var(--gov-blue-dark);
    }}
    .subtitle {{
      width: 100%;
      max-width: 860px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }}
    .section-tabs {{
      display: flex;
      flex-wrap: nowrap;
      gap: 8px;
      margin-top: 18px;
      overflow-x: auto;
      -webkit-overflow-scrolling: touch;
      white-space: nowrap;
      scroll-snap-type: x proximity;
    }}
    .section-tabs::-webkit-scrollbar {{ display: none; }}
    .section-tabs a {{
      flex: 0 0 auto;
      scroll-snap-align: start;
      min-height: 36px;
      display: inline-flex;
      align-items: center;
      border: 1px solid #b8c8df;
      border-radius: 999px;
      padding: 8px 14px;
      background: #fff;
      color: var(--gov-blue);
      font-size: 13px;
      font-weight: 680;
      text-decoration: none;
    }}
    .section-tabs a.is-active {{
      background: var(--gov-blue);
      border-color: var(--gov-blue);
      color: #fff;
    }}
    .sticky-controls {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(247, 249, 251, 0.96);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line);
      box-shadow: 0 10px 30px rgba(19, 46, 91, 0.11);
      margin: -1px -28px 0;
      padding: 10px 28px 12px;
    }}
    .sticky-controls .section-tabs {{
      margin-top: 0;
      margin-bottom: 10px;
    }}
    .sticky-controls .insight-row {{
      display: none;
    }}
    .section-select-wrap {{
      display: none;
    }}
    .sticky-brand {{
      display: none;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 8px;
    }}
    .sticky-brand-main {{
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }}
    .sticky-brand .gov-logo {{
      width: 78px;
    }}
    .sticky-title {{
      display: grid;
      gap: 2px;
      min-width: 0;
    }}
    .sticky-title strong {{
      color: var(--gov-blue-dark);
      font-size: 15px;
      line-height: 1.1;
    }}
    .sticky-title span {{
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .sticky-brand .author-meta {{
      flex: 0 0 auto;
    }}
    main {{
      width: 100%;
      max-width: 1380px;
      margin: 0 auto;
      padding: 0 28px 34px;
      display: grid;
      gap: 18px;
      min-width: 0;
    }}
    main > section {{
      scroll-margin-top: var(--sticky-offset, 150px);
      min-width: 0;
    }}
    .section-block {{
      display: grid;
      gap: 12px;
    }}
    .block-heading {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 34px;
    }}
    .block-heading h2 {{
      margin: 0;
      font-size: 18px;
      color: var(--gov-blue-dark);
    }}
    .block-heading span {{
      color: var(--muted);
      font-size: 13px;
    }}
    .filters {{
      display: grid;
      grid-template-columns: repeat(4, minmax(160px, 1fr));
      gap: 12px;
      align-items: end;
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 5px solid var(--gov-green);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 14px;
      min-width: 0;
      max-width: 100%;
    }}
    .filter-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }}
    .filter-actions .action-button {{
      min-height: 34px;
    }}
    .is-hidden {{
      display: none !important;
    }}
    #toggleFilters {{
      display: none;
    }}
    .hero .section-tabs {{ display: none; }}
    label {{
      display: grid;
      gap: 6px;
      color: var(--gov-blue-dark);
      font-size: 12px;
      font-weight: 720;
      text-transform: uppercase;
    }}
    select, input {{
      width: 100%;
      min-width: 0;
      min-height: 42px;
      border: 1px solid #b8c8df;
      border-radius: 999px;
      background: #fff;
      color: var(--ink);
      padding: 8px 14px;
      font-size: 14px;
      outline-color: var(--gov-blue);
    }}
    .kpis {{
      display: grid;
      grid-template-columns: repeat(3, minmax(210px, 1fr));
      gap: 14px;
    }}
    .card {{
      min-width: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 16px;
      min-height: 100px;
    }}
    .kpis .card {{
      min-height: 134px;
      padding: 18px;
    }}
    .card.accent-blue {{ border-top: 4px solid var(--gov-blue); }}
    .card.accent-green {{ border-top: 4px solid var(--gov-green); }}
    .card.accent-yellow {{ border-top: 4px solid var(--gov-yellow); }}
    .card.loading, .chart-loading {{
      opacity: 0.52;
      pointer-events: none;
      animation: pulse 0.7s ease-in-out infinite alternate;
    }}
    @keyframes pulse {{ to {{ opacity: 0.78; }} }}
    .metric-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      font-weight: 740;
      display: flex;
      align-items: center;
      gap: 5px;
    }}
    .info-tip {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 17px;
      height: 17px;
      border: 1px solid #b8c8df;
      border-radius: 999px;
      color: var(--gov-blue);
      background: #fff;
      font-size: 11px;
      font-style: normal;
      cursor: help;
      position: relative;
      text-transform: none;
    }}
    .info-tip:hover::after, .info-tip:focus::after {{
      content: attr(data-tip);
      position: absolute;
      left: 50%;
      bottom: calc(100% + 8px);
      transform: translateX(-50%);
      z-index: 40;
      width: min(280px, 82vw);
      border-radius: 10px;
      background: var(--gov-blue-dark);
      color: #fff;
      padding: 9px 10px;
      font-size: 12px;
      line-height: 1.35;
      box-shadow: var(--shadow);
      text-transform: none;
      font-weight: 560;
    }}
    .metric-value {{
      margin-top: 10px;
      color: var(--gov-blue-dark);
      font-size: 32px;
      font-weight: 780;
      white-space: nowrap;
    }}
    .metric-sub {{
      margin-top: 10px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .metric-sub.positive {{ color: var(--red); }}
    .metric-sub.negative {{ color: var(--gov-green); }}
    .definition-row {{
      display: grid;
      grid-template-columns: repeat(3, minmax(180px, 1fr));
      gap: 12px;
      margin-top: -4px;
    }}
    .definition {{
      display: grid;
      gap: 5px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      padding: 13px 14px;
    }}
    .definition strong {{
      color: var(--gov-blue-dark);
      font-size: 13px;
    }}
    .definition span {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .public-intro {{
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(280px, 0.9fr);
      gap: 14px;
      align-items: stretch;
      min-width: 0;
    }}
    .intro-card {{
      display: grid;
      gap: 14px;
      border-radius: var(--radius);
      background: #fff;
      border: 1px solid var(--line);
      border-left: 5px solid var(--gov-blue);
      box-shadow: var(--shadow);
      padding: 18px;
      min-width: 0;
      max-width: 100%;
    }}
    .intro-card h2 {{
      margin: 0;
      color: var(--gov-blue-dark);
      font-size: 22px;
    }}
    .intro-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .main-search {{
      display: grid;
      gap: 8px;
      min-width: 0;
    }}
    .main-search input {{
      min-height: 54px;
      border-radius: 16px;
      font-size: 17px;
      padding: 10px 18px;
    }}
    .notice {{
      border-radius: var(--radius);
      background: #fff8df;
      border: 1px solid #f4d06f;
      color: #604a00;
      padding: 12px 14px;
      font-size: 13px;
      line-height: 1.4;
      max-width: 100%;
    }}
    .quick-insights {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}
    .quick-card {{
      display: grid;
      gap: 5px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      padding: 12px;
      min-height: 90px;
    }}
    .quick-card span {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 720;
      text-transform: uppercase;
    }}
    .quick-card strong {{
      color: var(--gov-blue-dark);
      font-size: 15px;
      line-height: 1.2;
    }}
    .quick-card em {{
      color: var(--muted);
      font-style: normal;
      font-size: 12px;
    }}
    .profile-card {{
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 16px;
      align-items: start;
    }}
    .avatar {{
      width: 74px;
      height: 74px;
      border-radius: 50%;
      background: var(--gov-blue);
      color: #fff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      font-weight: 800;
    }}
    .profile-main {{
      display: grid;
      gap: 10px;
    }}
    .profile-main h2 {{
      margin: 0;
      color: var(--gov-blue-dark);
      font-size: 22px;
    }}
    .profile-meta {{
      color: var(--muted);
      font-weight: 700;
    }}
    .profile-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(120px, 1fr));
      gap: 10px;
    }}
    .profile-stat {{
      display: grid;
      gap: 3px;
      background: #f7f9fb;
      border-radius: 12px;
      padding: 10px;
    }}
    .profile-stat span {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 760;
    }}
    .profile-stat strong {{
      color: var(--gov-blue-dark);
      font-size: 17px;
    }}
    .comparison-list {{
      display: grid;
      gap: 6px;
      color: var(--ink);
      font-size: 13px;
      line-height: 1.35;
    }}
    .rank-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(280px, 1fr));
      gap: 14px;
    }}
    .ranking-list {{
      display: grid;
      gap: 9px;
    }}
    .rank-item {{
      display: grid;
      gap: 3px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 8px;
    }}
    .rank-item:last-child {{ border-bottom: 0; padding-bottom: 0; }}
    .rank-head {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--gov-blue-dark);
      font-weight: 760;
    }}
    .rank-context {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .matrix {{
      position: relative;
      min-height: 360px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background:
        linear-gradient(90deg, transparent calc(50% - 1px), #d6e0ef calc(50% - 1px), #d6e0ef calc(50% + 1px), transparent calc(50% + 1px)),
        linear-gradient(0deg, transparent calc(50% - 1px), #d6e0ef calc(50% - 1px), #d6e0ef calc(50% + 1px), transparent calc(50% + 1px)),
        #fff;
      overflow: hidden;
    }}
    .matrix-label {{
      position: absolute;
      color: var(--muted);
      font-size: 11px;
      max-width: 160px;
      line-height: 1.25;
      background: rgba(255,255,255,.82);
      border-radius: 8px;
      padding: 5px 7px;
    }}
    .matrix-label.tl {{ top: 8px; left: 8px; }}
    .matrix-label.tr {{ top: 8px; right: 8px; text-align: right; }}
    .matrix-label.bl {{ bottom: 8px; left: 8px; }}
    .matrix-label.br {{ bottom: 8px; right: 8px; text-align: right; }}
    .matrix-dot {{
      position: absolute;
      transform: translate(-50%, 50%);
      border-radius: 50%;
      border: 2px solid #fff;
      box-shadow: 0 3px 10px rgba(19, 46, 91, 0.2);
      background: var(--gov-blue);
      cursor: pointer;
    }}
    .creator-grid {{
      display: grid;
      grid-template-columns: minmax(280px, 0.9fr) minmax(280px, 1.1fr);
      gap: 14px;
    }}
    .creator-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    textarea {{
      width: 100%;
      min-height: 220px;
      resize: vertical;
      border: 1px solid #b8c8df;
      border-radius: 14px;
      padding: 12px;
      color: var(--ink);
      font: inherit;
      line-height: 1.45;
    }}
    .source-line {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      margin-top: 10px;
    }}
    .filter-context {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    .filter-context strong {{ color: var(--gov-blue-dark); }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid #b8c8df;
      border-radius: 999px;
      background: #fff;
      color: var(--gov-blue-dark);
      padding: 5px 9px;
      font-weight: 700;
    }}
    .chip button {{
      width: 18px;
      height: 18px;
      border: 0;
      border-radius: 999px;
      background: #e7eef8;
      color: var(--gov-blue);
      cursor: pointer;
      font-weight: 800;
      line-height: 1;
    }}
    .insight-row {{
      display: grid;
      grid-template-columns: repeat(4, minmax(180px, 1fr));
      gap: 12px;
    }}
    .insight {{
      display: grid;
      gap: 6px;
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: #fff;
      padding: 13px 14px;
    }}
    .insight strong {{
      color: var(--gov-blue-dark);
      font-size: 14px;
    }}
    .insight span {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }}
    .section-title {{
      margin: 0 0 12px;
      color: var(--gov-blue-dark);
      font-size: 15px;
      font-weight: 760;
    }}
    .chart-tools {{
      display: grid;
      grid-template-columns: minmax(180px, 280px) 1fr;
      gap: 10px;
      align-items: end;
      margin-bottom: 12px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(74px, 150px) 1fr minmax(90px, 128px);
      gap: 10px;
      align-items: center;
      min-height: 30px;
      font-size: 13px;
    }}
    .bar-row strong {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--gov-blue-dark);
    }}
    .bar-row span {{
      color: var(--muted);
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .bar-track {{
      height: 11px;
      background: #edf2f7;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      background: var(--gov-green);
    }}
    .bar-fill.party {{ background: var(--gov-blue); }}
    .bar-fill.presence {{ background: var(--gov-yellow); }}
    .stack-row {{
      display: grid;
      gap: 6px;
      padding: 7px 0;
      font-size: 13px;
    }}
    .stack-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      color: var(--gov-blue-dark);
      font-weight: 720;
    }}
    .stack-track {{
      display: flex;
      height: 13px;
      overflow: hidden;
      border-radius: 999px;
      background: #edf2f7;
    }}
    .stack-segment-expense {{ background: var(--gov-green); }}
    .stack-segment-salary {{ background: var(--gov-blue); }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .legend span {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}
    .legend i {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      display: inline-block;
    }}
    .table-wrap {{
      width: 100%;
      max-width: 100%;
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      background: #fff;
    }}
    .table-actions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }}
    .table-actions .table-status {{
      color: var(--muted);
      font-size: 13px;
    }}
    .action-button {{
      min-height: 36px;
      border: 1px solid #b8c8df;
      border-radius: 999px;
      background: #fff;
      color: var(--gov-blue);
      padding: 7px 12px;
      font: inherit;
      font-size: 13px;
      font-weight: 760;
      cursor: pointer;
    }}
    .action-button:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
    }}
    .pagination {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    .full-span {{ grid-column: 1 / -1; }}
    .pec-tools {{
      display: grid;
      grid-template-columns: minmax(220px, 420px) 1fr;
      gap: 12px;
      align-items: end;
      margin-bottom: 12px;
    }}
    .pec-note {{
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .pec-table td {{
      vertical-align: top;
      line-height: 1.35;
    }}
    .pec-title {{
      color: var(--gov-blue-dark);
      font-weight: 720;
    }}
    .pec-desc {{
      margin-top: 4px;
      color: var(--muted);
      max-width: 560px;
    }}
    .mobile-toggle {{
      display: none;
      min-height: 38px;
      border: 1px solid #b8c8df;
      border-radius: 999px;
      background: #fff;
      color: var(--gov-blue);
      font: inherit;
      font-size: 13px;
      font-weight: 760;
      padding: 8px 14px;
      cursor: pointer;
    }}
    .detail-toggle {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      justify-self: start;
    }}
    .detail-body.is-collapsed {{
      display: none;
    }}
    .mobile-card-list {{
      display: none;
    }}
    .always-card-list {{
      display: grid;
      gap: 10px;
    }}
    .mobile-data-card {{
      display: grid;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      box-shadow: var(--shadow);
      padding: 13px;
      min-width: 0;
    }}
    .mobile-data-card strong {{
      color: var(--gov-blue-dark);
    }}
    .mobile-card-title {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      color: var(--gov-blue-dark);
      font-weight: 760;
      min-width: 0;
    }}
    .mobile-card-title span:first-child {{
      min-width: 0;
      overflow-wrap: anywhere;
    }}
    .mobile-card-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .mobile-card-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      font-size: 12px;
    }}
    .mobile-card-grid span {{
      display: grid;
      gap: 2px;
      color: var(--muted);
    }}
    .mobile-card-grid b {{
      color: var(--ink);
      font-size: 13px;
    }}
    table {{
      width: 100%;
      min-width: 1120px;
      border-collapse: collapse;
      background: #fff;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 11px;
      text-align: left;
      font-size: 13px;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      color: var(--gov-blue-dark);
      font-size: 12px;
      text-transform: uppercase;
      background: #f0f5ff;
    }}
    th[data-sort] {{
      cursor: pointer;
      user-select: none;
    }}
    th[data-sort]::after {{
      content: " ↕";
      color: var(--muted);
      font-weight: 700;
    }}
    th[data-sort].sorted-asc::after {{ content: " ↑"; color: var(--gov-blue); }}
    th[data-sort].sorted-desc::after {{ content: " ↓"; color: var(--gov-blue); }}
    tr:nth-child(even) td {{ background: #fbfcff; }}
    td.num, th.num {{ text-align: right; }}
    .positive {{ color: var(--red); }}
    .negative {{ color: var(--gov-green); }}
    footer {{
      width: 100%;
      max-width: 1380px;
      margin: 0 auto;
      padding: 0 28px 32px;
      color: var(--muted);
      font-size: 13px;
    }}
    footer a {{ color: var(--gov-blue); font-weight: 720; }}
    @media (max-width: 1100px) {{
      .kpis, .insight-row, .grid, .definition-row {{ grid-template-columns: 1fr 1fr; }}
      .public-intro, .creator-grid {{ grid-template-columns: 1fr; }}
      .rank-grid {{ grid-template-columns: 1fr; }}
      .filters {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 720px) {{
      .govbar {{
        align-items: flex-start;
        flex-direction: column;
        gap: 3px;
        padding: 8px 16px;
      }}
      .brand-row {{
        align-items: flex-start;
        flex-direction: column;
        gap: 8px;
      }}
      .brand-meta {{ text-align: left; }}
      .author-meta {{ justify-content: flex-start; }}
      .gov-logo {{ width: 96px; }}
      .hero, main {{
        width: 100%;
        max-width: none;
        padding-left: 14px;
        padding-right: 14px;
      }}
      .hero {{
        padding-top: 16px;
        padding-bottom: 12px;
      }}
      main {{
        gap: 12px;
        padding-top: 0;
        padding-bottom: 24px;
      }}
      main > section {{
        scroll-margin-top: var(--sticky-offset, 116px);
      }}
      h1 {{ font-size: 24px; }}
      .subtitle {{ font-size: 14px; }}
      .section-tabs {{
        display: none;
      }}
      .section-select-wrap {{
        display: grid;
        gap: 5px;
        margin-bottom: 8px;
      }}
      .section-select-wrap label {{
        font-size: 11px;
      }}
      #sectionSelect {{
        min-height: 38px;
        border-radius: 12px;
      }}
      .sticky-controls {{
        top: 0;
        margin-left: -14px;
        margin-right: -14px;
        padding: 8px 14px 9px;
      }}
      .sticky-controls.section-block {{
        gap: 6px;
      }}
      .sticky-brand {{
        display: none;
      }}
      .sticky-brand-main {{
        flex: 1 1 auto;
        width: 100%;
      }}
      .sticky-brand .author-meta {{
        display: none;
      }}
      .sticky-brand .gov-logo {{
        width: 54px;
      }}
      .sticky-title strong {{
        font-size: 13px;
      }}
      .sticky-title span {{
        font-size: 11px;
      }}
      .sticky-controls .filter-context {{
        display: flex;
        gap: 6px;
        overflow: hidden;
        max-height: 34px;
        margin-top: 6px;
      }}
      #toggleFilters {{
        display: inline-flex;
      }}
      #clearAllFilters.is-hidden {{
        display: none;
      }}
      .sticky-controls.is-filters-collapsed .filters {{
        display: none;
      }}
      .sticky-controls .filters {{
        gap: 8px;
        padding: 10px;
      }}
      .sticky-controls label {{
        font-size: 11px;
      }}
      .sticky-controls select,
      .sticky-controls input {{
        min-height: 38px;
        font-size: 13px;
        border-radius: 12px;
        padding: 7px 10px;
      }}
      .filters, .grid {{ grid-template-columns: 1fr; }}
      .sticky-controls .filters {{
        grid-template-columns: 1fr 1fr;
      }}
      .sticky-controls .filters label:nth-child(3) {{
        grid-column: 1 / -1;
      }}
      .kpis {{
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }}
      .public-intro, .quick-insights, .profile-card, .profile-grid, .rank-grid, .creator-grid {{
        grid-template-columns: 1fr;
      }}
      .public-intro {{
        margin-top: 0;
      }}
      .avatar {{ width: 58px; height: 58px; font-size: 19px; }}
      .matrix {{ min-height: 300px; }}
      .kpis .card {{
        min-height: 104px;
        padding: 12px;
      }}
      .kpis .card:first-child {{
        grid-column: 1 / -1;
      }}
      .card {{
        padding: 13px;
      }}
      .intro-card {{
        padding: 14px;
      }}
      .intro-card h2,
      .profile-main h2 {{
        font-size: 19px;
      }}
      .main-search input {{
        min-height: 48px;
        border-radius: 14px;
        font-size: 15px;
      }}
      .definition-row {{ grid-template-columns: 1fr; }}
      .insight-row {{ display: none; }}
      .mobile-toggle {{ display: inline-flex; align-items: center; justify-content: center; }}
      .mobile-collapsible .card:nth-child(n+3) {{ display: none; }}
      .mobile-collapsible.is-expanded .card {{ display: block; }}
      .mobile-collapsible .bar-row:nth-child(n+6) {{ display: none; }}
      .mobile-collapsible.is-expanded .bar-row {{ display: grid; }}
      .pec-tools {{ grid-template-columns: 1fr; }}
      .chart-tools {{ grid-template-columns: 1fr; }}
      .block-heading {{
        align-items: flex-start;
        flex-direction: column;
        gap: 4px;
      }}
      .metric-label {{
        align-items: flex-start;
        font-size: 11px;
        line-height: 1.25;
      }}
      .metric-value {{
        font-size: 22px;
        line-height: 1.12;
        white-space: normal;
        overflow-wrap: anywhere;
      }}
      .metric-sub {{
        font-size: 11px;
        line-height: 1.25;
      }}
      .bar-row {{
        grid-template-columns: 1fr;
        gap: 5px;
        padding: 8px 0;
      }}
      .bar-row span {{ text-align: left; }}
      .pec-table .pec-desc {{ max-width: 320px; }}
      .desktop-table {{ display: none; }}
      .mobile-card-list {{
        display: grid;
        gap: 10px;
      }}
      .mobile-card-title {{
        display: grid;
        grid-template-columns: 1fr auto;
        align-items: start;
      }}
      .mobile-card-grid {{
        grid-template-columns: 1fr;
      }}
      .table-actions {{
        align-items: stretch;
        flex-direction: column;
      }}
      .action-button,
      .pagination button {{
        width: 100%;
      }}
      .filter-actions {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 6px;
        margin-bottom: 6px;
      }}
      .pagination {{
        justify-content: stretch;
      }}
      footer {{ padding-left: 14px; padding-right: 14px; }}
      th, td {{ padding: 9px; }}
    }}
    @media (max-width: 430px) {{
      .govbar {{
        display: none;
      }}
      .brand-row {{
        padding-bottom: 10px;
      }}
      .hero {{
        padding-left: 12px;
        padding-right: 12px;
      }}
      main {{
        padding-left: 10px;
        padding-right: 10px;
      }}
      .sticky-controls {{
        margin-left: -10px;
        margin-right: -10px;
        padding-left: 10px;
        padding-right: 10px;
      }}
      .sticky-title span {{
        display: none;
      }}
      .sticky-controls .filters {{
        grid-template-columns: 1fr 1fr;
      }}
      .sticky-controls .filters label:nth-child(3) {{
        grid-column: auto;
      }}
      main > section {{
        scroll-margin-top: var(--sticky-offset, 112px);
      }}
      .kpis {{
        grid-template-columns: 1fr;
      }}
      .section-tabs a {{
        min-height: 34px;
        padding: 7px 11px;
        font-size: 12px;
      }}
      .mobile-data-card {{
        padding: 11px;
      }}
    }}
  </style>
</head>
<body>
  <div class="govbar">
    <span>Dados públicos legislativos</span>
    <span>Camara, Senado, TSE RJ e ALERJ | Mandato atual</span>
  </div>
  <header>
    <div class="hero">
      <div class="brand-row">
        <img
          class="gov-logo"
          src="https://www.gov.br/governodigital/pt-br/acessibilidade-e-usuario/atendimento-gov.br/imagens/gov-br_logo-svg.png/@@images/image"
          alt="gov.br"
        >
        <div class="author-meta">
          <strong>Por Lucca Lanzellotti, BI Expert</strong>
          <a href="https://www.linkedin.com/in/lucca-lanzellotti" target="_blank" rel="noopener">
            <svg class="linkedin-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path fill="currentColor" d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.33 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12ZM7.11 20.45H3.55V9h3.56v11.45ZM22.23 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.46c.98 0 1.77-.77 1.77-1.72V1.72C24 .77 23.21 0 22.23 0Z"/>
            </svg>
            LinkedIn
          </a>
        </div>
      </div>
      <div class="eyebrow">Painel de inteligência política</div>
      <h1>Painel de Inteligencia Politica 2026</h1>
      <div class="subtitle">Dados publicos da Camara, Senado, TSE RJ, ALERJ e DOCIGP para comparar gasto parlamentar, remuneracao estimada, presenca, votacoes e recortes eleitorais.</div>
    </div>
  </header>
  <main>
    <section class="section-block sticky-controls is-filters-collapsed" id="visao-geral">
      <div class="sticky-brand">
        <div class="sticky-brand-main">
          <img
            class="gov-logo"
            src="https://www.gov.br/governodigital/pt-br/acessibilidade-e-usuario/atendimento-gov.br/imagens/gov-br_logo-svg.png/@@images/image"
            alt="gov.br"
          >
          <div class="sticky-title">
            <strong>Painel Politico 2026</strong>
            <span>Camara, Senado, TSE RJ e ALERJ</span>
          </div>
        </div>
        <div class="author-meta">
          <strong>Por Lucca Lanzellotti, BI Expert</strong>
          <a href="https://www.linkedin.com/in/lucca-lanzellotti" target="_blank" rel="noopener">
            <svg class="linkedin-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path fill="currentColor" d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.33 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12ZM7.11 20.45H3.55V9h3.56v11.45ZM22.23 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.46c.98 0 1.77-.77 1.77-1.72V1.72C24 .77 23.21 0 22.23 0Z"/>
            </svg>
            LinkedIn
          </a>
        </div>
      </div>
      <nav class="section-tabs" aria-label="Seções do relatório">
        <a href="#visao-geral">Visão geral</a>
        <a href="#buscar-deputado">Buscar deputado</a>
        <a href="#rankings">Rankings</a>
        <a href="#gastos">Gasto parlamentar</a>
        <a href="#presenca">Presença</a>
        <a href="#pecs">Votações</a>
        <a href="#videos-posts">Para vídeos e posts</a>
        <a href="#detalhes">Detalhes</a>
        <a href="#metodologia">Metodologia</a>
      </nav>
      <div class="section-select-wrap">
        <label>Secoes<select id="sectionSelect" aria-label="Ir para secao do relatorio"></select></label>
      </div>
      <div class="filter-actions">
        <button class="action-button" type="button" id="toggleFilters">Filtros</button>
        <button class="action-button" type="button" id="clearAllFilters">Limpar filtros</button>
      </div>
      <div class="filters">
        <label>Estado<select id="stateFilter"></select></label>
        <label>Partido<select id="partyFilter"></select></label>
        <label>Deputado<input id="nameFilter" list="deputySearchList" type="search" placeholder="Pesquisar deputado"></label>
        <datalist id="deputySearchList"></datalist>
        <label>Ordenar<select id="sortFilter">
          <option value="custo_total_estimado">Custo total</option>
          <option value="valor_liquido_total">Gasto parlamentar</option>
          <option value="indice_presenca_relativa">% presença relativa</option>
          <option value="pct_ausencia_nao_justificada">% ausência não just.</option>
          <option value="qtd_votacoes_pec">Votações PEC</option>
          <option value="diferenca_yoy">Diferença YoY</option>
          <option value="custo_por_presenca">Custo por presença</option>
        </select></label>
      </div>
      <div class="filter-context" id="activeFilters">
        <strong>Mostrando:</strong>
        <span class="chip">Brasil</span>
        <span class="chip">Todos os partidos</span>
        <span class="chip">Todos os deputados</span>
      </div>
      <div class="insight-row">
        <div class="insight"><strong>Mandato atual</strong><span>Dados acumulados da legislatura vigente até a data de referência.</span></div>
        <div class="insight"><strong>Presença formal</strong><span>Ausências justificadas e não justificadas vêm das sessões de plenário.</span></div>
        <div class="insight"><strong>PECs</strong><span>Votos nominais vinculados a proposições do tipo PEC.</span></div>
        <div class="insight"><strong>YoY</strong><span>Comparação do ano atual contra o mesmo período do ano anterior.</span></div>
      </div>
    </section>

    <section class="public-intro" id="buscar-deputado">
      <div class="intro-card">
        <h2>Entenda em 30 segundos</h2>
        <p>Este painel ajuda você a entender como deputados federais usam recursos públicos, comparecem às atividades parlamentares e votam em PECs. Use a busca para encontrar um deputado, partido ou estado.</p>
        <div class="main-search">
          <label>Busca principal<input id="mainSearch" list="mainSearchList" type="search" placeholder="Digite o nome de um deputado, partido ou estado"></label>
          <datalist id="mainSearchList"></datalist>
        </div>
        <div class="notice">Use estes dados com responsabilidade. O painel aponta padrões e comparações, mas não comprova irregularidades individualmente.</div>
      </div>
      <div class="quick-insights" id="quickInsights"></div>
    </section>

    <section class="section-block" id="ficha-deputado">
      <div class="block-heading">
        <h2>Ficha do deputado</h2>
        <span>Resumo simples do recorte atual</span>
      </div>
      <div class="card profile-card" id="deputyProfile"></div>
    </section>

    <section class="kpis" aria-label="Indicadores principais">
      <div class="card accent-blue"><div class="metric-label">Deputados</div><div class="metric-value" id="kpiDeputies">{initial_kpis["deputies"]}</div></div>
      <div class="card accent-green"><div class="metric-label">Gasto parlamentar <i class="info-tip" tabindex="0" data-tip="Gasto parlamentar = verba/cota usada no mandato: passagens, divulgação, escritório, combustível e outras despesas de atividade parlamentar.">i</i></div><div class="metric-value" id="kpiExpenses">{initial_kpis["expenses"]}</div><div class="metric-sub" id="kpiExpensesYoy">Dif. YoY: {initial_kpis["expense_yoy"]}</div></div>
      <div class="card accent-yellow"><div class="metric-label">Remuneração <i class="info-tip" tabindex="0" data-tip="Remuneração = subsídio bruto parlamentar estimado no mandato. Não é cota parlamentar.">i</i></div><div class="metric-value" id="kpiSalary">{initial_kpis["salary"]}</div><div class="metric-sub" id="kpiSalaryContext">Subsídio estimado, sem série YoY</div></div>
      <div class="card accent-blue"><div class="metric-label">Custo total <i class="info-tip" tabindex="0" data-tip="Custo total = gasto parlamentar + remuneração bruta estimada no mandato.">i</i></div><div class="metric-value" id="kpiCost">{initial_kpis["cost"]}</div><div class="metric-sub" id="kpiCostYoy">Impacto YoY no custo: {initial_kpis["expense_yoy"]}</div></div>
      <div class="card accent-green"><div class="metric-label">% presença relativa <i class="info-tip" tabindex="0" data-tip="Presença relativa = eventos com presença do deputado divididos pelo maior volume de presença registrado por qualquer deputado no período.">i</i></div><div class="metric-value" id="kpiPresencePct">{initial_kpis["presence"]}</div><div class="metric-sub" id="kpiPresenceContext">Vs. média Brasil: 0,0 p.p.</div></div>
      <div class="card accent-blue"><div class="metric-label">% ausência não just. <i class="info-tip" tabindex="0" data-tip="Média percentual das ausências não justificadas em sessões de plenário para os deputados filtrados.">i</i></div><div class="metric-value" id="kpiUnjustifiedAbsence">{initial_kpis["unjustified_absence"]}</div><div class="metric-sub" id="kpiAbsenceContext">Vs. média Brasil: 0,0 p.p.</div></div>
      <div class="card accent-green"><div class="metric-label">Votações PEC <i class="info-tip" tabindex="0" data-tip="Total de registros nominais de votação em proposições classificadas como PEC no mandato.">i</i></div><div class="metric-value" id="kpiPecVotes">{initial_kpis["pec_votes"]}</div><div class="metric-sub" id="kpiPecContext">Média por deputado: 0</div></div>
    </section>

    <section class="definition-row" aria-label="Definições rápidas">
      <div class="definition"><strong>Gasto parlamentar</strong><span>É a verba/cota usada no mandato: reembolsos e despesas de atividade parlamentar.</span></div>
      <div class="definition"><strong>Remuneração</strong><span>É o subsídio bruto estimado. Entra no custo, mas não é gasto de cota.</span></div>
      <div class="definition"><strong>Custo total</strong><span>É gasto parlamentar + remuneração. Use para estimar o custo público agregado.</span></div>
    </section>

    <section class="section-block" id="rankings">
      <div class="block-heading">
        <h2>Rankings com contexto</h2>
        <span>Listas comparativas para responder perguntas rápidas</span>
      </div>
      <div class="rank-grid">
        <div class="card"><h2 class="section-title">Quem teve o maior custo total aproximado?</h2><div class="ranking-list" id="rankCost"></div><div class="source-line">Fonte: Dados públicos da Câmara dos Deputados · Atualizado em {data_updated_label}</div></div>
        <div class="card"><h2 class="section-title">Quem teve maior custo por presença registrada?</h2><div class="ranking-list" id="rankCostPresence"></div><div class="source-line">Fonte: Dados públicos da Câmara dos Deputados · Atualizado em {data_updated_label}</div></div>
        <div class="card"><h2 class="section-title">Quem teve maior aumento de gasto parlamentar no ano?</h2><div class="ranking-list" id="rankYoy"></div><div class="source-line">Fonte: Dados públicos da Câmara dos Deputados · Atualizado em {data_updated_label}</div></div>
        <div class="card"><h2 class="section-title">Quem tem mais ausência não justificada?</h2><div class="ranking-list" id="rankAbsence"></div><div class="source-line">Fonte: Dados públicos da Câmara dos Deputados · Atualizado em {data_updated_label}</div></div>
      </div>
    </section>

    <section class="section-block" id="matriz">
      <div class="block-heading">
        <h2>Matriz gasto parlamentar x presença</h2>
        <span>Identifique rapidamente deputados fora do padrão</span>
      </div>
      <div class="card">
        <div class="matrix" id="attentionMatrix">
          <div class="matrix-label tl">Baixo custo + alta presença<br>Boa eficiência relativa</div>
          <div class="matrix-label tr">Alto custo + alta presença<br>Custo alto, mas com atividade registrada</div>
          <div class="matrix-label bl">Baixo custo + baixa presença<br>Baixa atividade aparente</div>
          <div class="matrix-label br">Alto custo + baixa presença<br>Ponto de atenção</div>
        </div>
        <div class="source-line">Eixo X: custo total aproximado · Eixo Y: presença comparada aos demais · tamanho: gasto parlamentar</div>
      </div>
    </section>

    <section class="section-block" id="gastos">
      <div class="block-heading">
        <h2>Gasto parlamentar</h2>
        <span>Verba/cota parlamentar, categorias e média por partido</span>
      </div>
      <button class="mobile-toggle" type="button" data-toggle-section="gastosGrid">Mostrar todos os gráficos de gasto parlamentar</button>
      <div class="grid mobile-collapsible" id="gastosGrid">
      <div class="card">
        <h2 class="section-title">Partidos por métrica</h2>
        <div class="chart-tools">
          <label>Métrica<select id="partyMetricFilter">
            <option value="custo_total">Custo total</option>
            <option value="custo_por_deputado">Custo por deputado</option>
            <option value="share_custo_pct">Share % do custo</option>
            <option value="qtd_candidatos">Quantidade de deputados</option>
            <option value="share_deputados_pct">Share % da bancada</option>
            <option value="pecs_por_deputado">PECs por deputado</option>
          </select></label>
        </div>
        <div id="partyBars"></div>
      </div>
      <div class="card">
        <h2 class="section-title">Custo total por estado</h2>
        <div id="stateBars"></div>
      </div>
      <div class="card">
        <h2 class="section-title">Share do gasto parlamentar por categoria</h2>
        <div id="categoryShareBars"></div>
      </div>
      <div class="card">
        <h2 class="section-title">Gasto parlamentar médio por candidato do partido</h2>
        <div id="partyAverageBars"></div>
      </div>
      <div class="card">
        <h2 class="section-title">Custo: gasto parlamentar x remuneração</h2>
        <div class="legend"><span><i style="background: var(--gov-green)"></i>Gasto parlamentar</span><span><i style="background: var(--gov-blue)"></i>Remuneração</span></div>
        <div id="partyCostStack"></div>
      </div>
      <div class="card">
        <h2 class="section-title">Representatividade: bancada x custo</h2>
        <div id="partyShareCompare"></div>
      </div>
      </div>
    </section>

    <section class="section-block" id="presenca">
      <div class="block-heading">
        <h2>Presença e ausências</h2>
        <span>Eventos legislativos e sessões de plenário</span>
      </div>
      <button class="mobile-toggle" type="button" data-toggle-section="presencaGrid">Mostrar todos os gráficos de presença</button>
      <div class="grid mobile-collapsible" id="presencaGrid">
      <div class="card">
        <h2 class="section-title">% presença relativa por partido</h2>
        <div id="partyPresenceBars"></div>
      </div>
      <div class="card">
        <h2 class="section-title">% presença relativa por estado</h2>
        <div id="statePresenceBars"></div>
      </div>
      <div class="card">
        <h2 class="section-title">Ausências no plenário por partido</h2>
        <div id="partyAbsenceBars"></div>
      </div>
      </div>
    </section>

    <section class="section-block" id="pecs">
      <div class="block-heading">
        <h2>Votações em PECs</h2>
        <span>Histórico nominal no mandato</span>
      </div>
      <div class="grid">
      <div class="card">
        <h2 class="section-title">Votos em PEC por partido</h2>
        <div id="partyPecBars"></div>
      </div>
      <div class="card full-span">
        <h2 class="section-title">Votos por PEC</h2>
        <div class="pec-tools">
          <label>Selecionar PEC<select id="pecSelect"></select></label>
          <label>Buscar PEC<input id="pecFilter" type="search" placeholder="PEC, deputado, voto ou trecho da ementa"></label>
          <div class="pec-note">A tabela abaixo acompanha os filtros de estado, partido e deputado aplicados no topo.</div>
        </div>
        <button class="mobile-toggle detail-toggle" type="button" data-toggle-detail="pecDetailBody">Expandir detalhes das PECs</button>
        <div class="detail-body is-collapsed" id="pecDetailBody">
        <div class="table-actions">
          <span class="table-status" id="pecTableStatus">Mostrando 0 de 0 votos</span>
          <button class="action-button" type="button" id="exportPecCsv">Exportar CSV</button>
        </div>
        <div class="table-wrap desktop-table">
          <table class="pec-table">
            <thead>
              <tr>
                <th data-sort="data_ultima" data-table="pec">Última votação</th>
                <th data-sort="nome" data-table="pec">Deputado</th>
                <th data-sort="siglaPartido" data-table="pec">Partido</th>
                <th data-sort="siglaUf" data-table="pec">UF</th>
                <th data-sort="proposicao_titulo" data-table="pec">PEC</th>
                <th data-sort="voto_predominante" data-table="pec">Voto predominante</th>
                <th class="num" data-sort="votos_sim" data-table="pec">Sim</th>
                <th class="num" data-sort="votos_nao" data-table="pec">Não</th>
                <th class="num" data-sort="votos_outros" data-table="pec">Outros</th>
                <th data-sort="siglaOrgao" data-table="pec">Órgão</th>
              </tr>
            </thead>
            <tbody id="pecVoteBody"></tbody>
          </table>
        </div>
        <div class="mobile-card-list" id="pecVoteCards"></div>
        <div class="pagination">
          <button class="action-button" type="button" id="pecPrevPage">Anterior</button>
          <span id="pecPageStatus">Página 1</span>
          <button class="action-button" type="button" id="pecNextPage">Próxima</button>
        </div>
        </div>
      </div>
      </div>
    </section>

    <section class="section-block" id="detalhes">
      <div class="block-heading">
        <h2>Detalhamento por deputado</h2>
        <span>Até 120 registros conforme os filtros atuais</span>
      </div>
      <button class="mobile-toggle detail-toggle" type="button" data-toggle-detail="candidateDetailBody">Expandir detalhes por deputado</button>
      <div class="detail-body is-collapsed" id="candidateDetailBody">
      <div class="table-actions">
        <span class="table-status" id="candidateTableStatus">Mostrando 0 de 0 deputados</span>
        <button class="action-button" type="button" id="exportCandidateCsv">Exportar CSV</button>
      </div>
      <div class="table-wrap desktop-table">
        <table>
        <thead>
          <tr>
            <th data-sort="nome" data-table="candidate">Deputado</th>
            <th data-sort="siglaPartido" data-table="candidate">Partido</th>
            <th data-sort="siglaUf" data-table="candidate">UF</th>
            <th class="num" data-sort="valor_liquido_total" data-table="candidate">Gasto parlamentar</th>
            <th class="num" data-sort="valor_subsidio_bruto_total" data-table="candidate">Remun.</th>
            <th class="num" data-sort="custo_total_estimado" data-table="candidate">Custo</th>
            <th class="num" data-sort="indice_presenca_relativa" data-table="candidate">% pres. rel.</th>
            <th class="num" data-sort="pct_ausencia_justificada" data-table="candidate">Aus. just.</th>
            <th class="num" data-sort="pct_ausencia_nao_justificada" data-table="candidate">Aus. nao just.</th>
            <th class="num" data-sort="qtd_votacoes_pec" data-table="candidate">PECs</th>
            <th class="num" data-sort="diferenca_yoy" data-table="candidate">YoY</th>
            <th class="num" data-sort="dif_gasto_media_candidato" data-table="candidate">Dif. media candidato</th>
            <th class="num" data-sort="custo_por_presenca" data-table="candidate">Custo/pres.</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
      </div>
      <div class="mobile-card-list" id="deputyCardList"></div>
      <div class="pagination">
        <button class="action-button" type="button" id="candidatePrevPage">Anterior</button>
        <span id="candidatePageStatus">Página 1</span>
        <button class="action-button" type="button" id="candidateNextPage">Próxima</button>
      </div>
      </div>
    </section>

    <section class="section-block" id="senado">
      <div class="block-heading">
        <h2>Senado Federal</h2>
        <span>Gasto parlamentar (CEAPS) e votacoes nominais dos senadores em exercicio</span>
      </div>
      <section class="kpis" aria-label="Indicadores do Senado">
        <div class="card accent-blue"><div class="metric-label">Senadores</div><div class="metric-value" id="senateKpiSenators">{senate_kpis["senators"]}</div></div>
        <div class="card accent-green"><div class="metric-label">Gasto parlamentar</div><div class="metric-value" id="senateKpiCeaps">{senate_kpis["ceaps"]}</div></div>
        <div class="card accent-blue"><div class="metric-label">Votos nominais</div><div class="metric-value" id="senateKpiVotes">{senate_kpis["votes"]}</div></div>
        <div class="card accent-yellow"><div class="metric-label">Media gasto parlamentar</div><div class="metric-value" id="senateKpiAvgCeaps">{senate_kpis["avg_ceaps"]}</div></div>
      </section>
      <div class="filters">
        <label>UF<select id="senateStateFilter"></select></label>
        <label>Partido<select id="senatePartyFilter"></select></label>
        <label>Senador<input id="senateNameFilter" type="search" placeholder="Pesquisar senador"></label>
        <label>Ordenar<select id="senateSortFilter">
          <option value="valor_reembolsado_total">Gasto parlamentar</option>
          <option value="qtd_votacoes">Qtd votacoes</option>
          <option value="qtd_votos">Votos nominais</option>
          <option value="nome">Nome</option>
        </select></label>
      </div>
      <div class="table-actions">
        <span class="table-status" id="senateTableStatus">Mostrando 0 senadores</span>
      </div>
      <div class="mobile-card-list always-card-list" id="senateCards"></div>
    </section>

    <section class="section-block" id="rj-estadual">
      <div class="block-heading">
        <h2>RJ Estadual - gasto parlamentar</h2>
        <span>Descentralizacao Orcamentaria de Custeio Individualizado para Gabinete Parlamentar (DOCIGP)</span>
      </div>
      <section class="kpis" aria-label="Indicadores de gasto parlamentar estadual">
        <div class="card accent-blue"><div class="metric-label">Deputados com gasto</div><div class="metric-value" id="rjExpenseKpiDeputies">{rj_expense_kpis["deputies"]}</div></div>
        <div class="card accent-green"><div class="metric-label">Gasto parlamentar</div><div class="metric-value" id="rjExpenseKpiSpending">{rj_expense_kpis["spending"]}</div></div>
        <div class="card accent-blue"><div class="metric-label">Lancamentos</div><div class="metric-value" id="rjExpenseKpiEntries">{rj_expense_kpis["entries"]}</div></div>
        <div class="card accent-yellow"><div class="metric-label">Media por deputado</div><div class="metric-value" id="rjExpenseKpiAvg">{rj_expense_kpis["avg"]}</div></div>
      </section>
      <div class="filters">
        <label>Partido<select id="rjExpensePartyFilter"></select></label>
        <label>Deputado<input id="rjExpenseNameFilter" type="search" placeholder="Pesquisar deputado"></label>
        <label>Ordenar<select id="rjExpenseSortFilter">
          <option value="valorGastoParlamentar">Gasto parlamentar</option>
          <option value="qtdLancamentos">Lancamentos</option>
          <option value="qtdFornecedores">Fornecedores</option>
          <option value="usoLimitePct">Uso do limite</option>
          <option value="nome">Nome</option>
        </select></label>
      </div>
      <div class="table-actions">
        <span class="table-status" id="rjExpenseTableStatus">Mostrando 0 deputados</span>
      </div>
      <div class="grid">
        <div class="card">
          <h2 class="section-title">Deputados por gasto parlamentar</h2>
          <div class="mobile-card-list always-card-list" id="rjExpenseCards"></div>
        </div>
        <div class="card">
          <h2 class="section-title">Categorias do gasto parlamentar</h2>
          <div class="mobile-card-list always-card-list" id="rjExpenseCategoryCards"></div>
        </div>
      </div>
      <div class="source-line">Fonte: DOCIGP/ALERJ. Totais excluem credito, transporte de saldo e devolucao de saldo.</div>
    </section>

    <section class="section-block" id="rj-eleitoral">
      <div class="block-heading">
        <h2>RJ Estadual - TSE 2022</h2>
        <span>Deputados estaduais eleitos e votos nominais</span>
      </div>
      <section class="kpis" aria-label="Indicadores do RJ Estadual">
        <div class="card accent-blue"><div class="metric-label">Eleitos</div><div class="metric-value" id="rjKpiElected">{rj_kpis["elected"]}</div></div>
        <div class="card accent-green"><div class="metric-label">Votos nominais</div><div class="metric-value" id="rjKpiVotes">{rj_kpis["votes"]}</div></div>
        <div class="card accent-yellow"><div class="metric-label">Maior votacao</div><div class="metric-value" id="rjKpiTopVotes">{rj_kpis["top_votes"]}</div></div>
        <div class="card accent-blue"><div class="metric-label">Partidos eleitos</div><div class="metric-value" id="rjKpiParties">{rj_kpis["parties"]}</div></div>
      </section>
      <div class="filters">
        <label>Partido<select id="rjPartyFilter"></select></label>
        <label>Genero<select id="rjGenderFilter"></select></label>
        <label>Nome<input id="rjNameFilter" type="search" placeholder="Pesquisar eleito"></label>
        <label>Ordenar<select id="rjSortFilter">
          <option value="votos_nominais">Votos nominais</option>
          <option value="municipios_com_voto">Municipios com voto</option>
          <option value="nomeUrna">Nome</option>
        </select></label>
      </div>
      <div class="table-actions">
        <span class="table-status" id="rjTableStatus">Mostrando 0 eleitos</span>
      </div>
      <div class="mobile-card-list always-card-list" id="rjCards"></div>
    </section>

    <section class="section-block" id="fontes-alerj">
      <div class="block-heading">
        <h2>Fontes ALERJ</h2>
        <span>Camada de rastreabilidade oficial para mandato estadual</span>
      </div>
      <section class="kpis" aria-label="Indicadores de fontes ALERJ">
        <div class="card accent-blue"><div class="metric-label">Deputados ALERJ</div><div class="metric-value" id="alerjKpiDeputies">{alerj_kpis["deputies"]}</div></div>
        <div class="card accent-green"><div class="metric-label">Fontes catalogadas</div><div class="metric-value" id="alerjKpiSources">{alerj_kpis["sources"]}</div></div>
        <div class="card accent-yellow"><div class="metric-label">PDFs catalogados</div><div class="metric-value" id="alerjKpiPdfs">{alerj_kpis["pdfs"]}</div></div>
      </section>
      <div class="notice">Esta secao lista fontes oficiais da ALERJ para auditoria posterior. Gasto parlamentar estadual ja entra pela secao DOCIGP; presenca e votacao ainda dependem de extracao estruturada adicional.</div>
      <div class="grid">
        <div class="card">
          <h2 class="section-title">Deputados em exercicio</h2>
          <div id="alerjDeputyCards" class="mobile-card-list always-card-list"></div>
        </div>
        <div class="card">
          <h2 class="section-title">Fontes oficiais</h2>
          <label>Buscar fonte<input id="alerjSourceFilter" type="search" placeholder="Tipo, titulo ou observacao"></label>
          <div id="alerjSourceCards" class="mobile-card-list always-card-list"></div>
        </div>
      </div>
    </section>

    <section class="section-block" id="videos-posts">
      <div class="block-heading">
        <h2>Para vídeos e posts</h2>
        <span>Texto neutro pronto para usar como base</span>
      </div>
      <div class="creator-grid">
        <div class="card">
          <h2 class="section-title">Roteiro de 30 segundos</h2>
          <p class="source-line">Selecione um deputado na busca principal para gerar um roteiro individual. O texto é neutro e inclui ressalva metodológica.</p>
          <div class="creator-actions">
            <button class="action-button" type="button" id="copyVideoScript">Copiar roteiro</button>
            <button class="action-button" type="button" id="exportStoryCard">Exportar card PNG</button>
            <button class="action-button" type="button" id="copySource">Copiar fonte dos dados</button>
          </div>
        </div>
        <div class="card">
          <textarea id="videoScript" readonly></textarea>
          <div class="notice">Antes de publicar, confira o contexto completo: gasto parlamentar sozinho nao conta a historia toda. Compare presenca, justificativas, estado, partido, tipo de despesa e votacoes.</div>
        </div>
      </div>
    </section>

    <section class="section-block" id="metodologia">
      <div class="block-heading">
        <h2>Como ler estes dados</h2>
        <span>Transparência e prevenção contra interpretações erradas</span>
      </div>
      <div class="card">
        <p>Este painel organiza dados publicos da Camara dos Deputados, Senado Federal, TSE, ALERJ e DOCIGP. As metricas apresentadas servem para comparacao e fiscalizacao cidada, mas nao devem ser interpretadas isoladamente.</p>
        <p>Maior gasto parlamentar nao significa automaticamente irregularidade. Menor presenca comparada aos demais nao significa automaticamente falta ao trabalho. Os dados precisam ser analisados com contexto, fonte e metodologia.</p>
        <p><strong>Fontes:</strong> Camara dos Deputados, Senado Federal, TSE, ALERJ e DOCIGP/ALERJ · <strong>Atualizado em:</strong> {data_updated_label}</p>
      </div>
    </section>
  </main>
  <footer>
    Dados atualizados em: <strong>{data_updated_label}</strong> · Fontes:
    <a href="https://dadosabertos.camara.leg.br" target="_blank" rel="noopener">Dados Abertos da Camara</a>
    ·
    <a href="https://docigp.alerj.rj.gov.br/transparencia" target="_blank" rel="noopener">DOCIGP/ALERJ</a>
  </footer>
  <script>
    const DATA = {data_json};
    const CATEGORY_DATA = {categories_json};
    const PARTY_DATA = {party_json};
    const PEC_VOTE_DATA = {pec_vote_json};
    const PEC_OPTIONS = {pec_options_json};
    const STATES = {states_json};
    const PARTIES = {parties_json};
    const SENATE_DATA = {senate_json};
    const RJ_ELECTED_DATA = {rj_elected_json};
    const RJ_EXPENSE_DATA = {rj_expense_json};
    const RJ_EXPENSE_CATEGORY_DATA = {rj_expense_category_json};
    const ALERJ_DEPUTY_DATA = {alerj_deputies_json};
    const ALERJ_SOURCE_DATA = {alerj_sources_json};
    const ALERJ_PDF_DATA = {alerj_pdfs_json};

    const formatMoney = new Intl.NumberFormat('pt-BR', {{
      style: 'currency',
      currency: 'BRL',
      maximumFractionDigits: 0,
      minimumFractionDigits: 0
    }});
    const formatNumber = new Intl.NumberFormat('pt-BR');
    const formatPct = new Intl.NumberFormat('pt-BR', {{ maximumFractionDigits: 1 }});
    const nationalPresenceAvg = DATA.length ? DATA.reduce((acc, row) => acc + Number(row.indice_presenca_relativa || 0), 0) / DATA.length : 0;
    const nationalUnjustifiedAbsenceAvg = DATA.length ? DATA.reduce((acc, row) => acc + Number(row.pct_ausencia_nao_justificada || 0), 0) / DATA.length : 0;

    const stateFilter = document.getElementById('stateFilter');
    const partyFilter = document.getElementById('partyFilter');
    const nameFilter = document.getElementById('nameFilter');
    const deputySearchList = document.getElementById('deputySearchList');
    const mainSearch = document.getElementById('mainSearch');
    const mainSearchList = document.getElementById('mainSearchList');
    const sortFilter = document.getElementById('sortFilter');
    const pecFilter = document.getElementById('pecFilter');
    const pecSelect = document.getElementById('pecSelect');
    const partyMetricFilter = document.getElementById('partyMetricFilter');
    const pageSize = 25;
    let candidatePage = 1;
    let pecPage = 1;
    let candidateSort = {{ field: 'custo_total_estimado', direction: 'desc' }};
    let pecSort = {{ field: 'data_ultima', direction: 'desc' }};
    let lastCandidateRows = [];
    let lastPecRows = [];
    let selectedDeputy = null;
    const sourceText = 'Fontes: Camara dos Deputados, Senado Federal, TSE, ALERJ e DOCIGP/ALERJ. Consulta realizada em {data_updated_label}.';
    const sectionLinks = [
      ['#visao-geral', 'Visao geral'],
      ['#buscar-deputado', 'Buscar deputado'],
      ['#rankings', 'Rankings'],
      ['#gastos', 'Gasto parlamentar'],
      ['#presenca', 'Presenca'],
      ['#pecs', 'Votacoes'],
      ['#senado', 'Senado'],
      ['#rj-estadual', 'Gasto RJ'],
      ['#rj-eleitoral', 'TSE RJ'],
      ['#fontes-alerj', 'Fontes ALERJ'],
      ['#videos-posts', 'Videos e posts'],
      ['#detalhes', 'Detalhes'],
      ['#metodologia', 'Metodologia']
    ];

    function setOptions(select, values, allLabel) {{
      select.innerHTML = '<option value="">' + allLabel + '</option>' +
        values.map(value => '<option value="' + value + '">' + value + '</option>').join('');
    }}

    function formatCompactMoney(value) {{
      const number = Number(value || 0);
      const abs = Math.abs(number);
      const scaled = (divisor, suffix, decimals) => {{
        const formatter = new Intl.NumberFormat('pt-BR', {{
          maximumFractionDigits: decimals,
          minimumFractionDigits: 0
        }});
        return 'R$ ' + formatter.format(number / divisor) + ' ' + suffix;
      }};
      if (abs >= 1_000_000_000) return scaled(1_000_000_000, 'bi', 3);
      if (abs >= 1_000_000) return scaled(1_000_000, 'mi', 3);
      if (abs >= 1_000) return scaled(1_000, 'mil', 1);
      return new Intl.NumberFormat('pt-BR', {{
        style: 'currency',
        currency: 'BRL',
        maximumFractionDigits: 0,
        minimumFractionDigits: 0
      }}).format(number);
    }}

    function formatCompactMoneyPrecise(value) {{
      return formatCompactMoney(value);
    }}

    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, char => ({{
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }}[char]));
    }}

    function fixEncodingText(value) {{
      return String(value ?? '')
        .replace(/ÃƒÂ§/g, 'c')
        .replace(/ÃƒÂ£/g, 'a')
        .replace(/ÃƒÂ©/g, 'e')
        .replace(/ÃƒÂª/g, 'e')
        .replace(/ÃƒÂ¡/g, 'a')
        .replace(/ÃƒÂ³/g, 'o')
        .replace(/ÃƒÂº/g, 'u')
        .replace(/ÃƒÂ­/g, 'i')
        .replace(/ÃƒÂ¢/g, 'a')
        .replace(/ÃƒÂ´/g, 'o')
        .replace(/Ã§/g, 'c')
        .replace(/Ã£/g, 'a')
        .replace(/Ã©/g, 'e')
        .replace(/Ãª/g, 'e')
        .replace(/Ã¡/g, 'a')
        .replace(/Ã³/g, 'o')
        .replace(/Ãº/g, 'u')
        .replace(/Ã­/g, 'i')
        .replace(/Ã¢/g, 'a')
        .replace(/Ã´/g, 'o')
        .replace(/Â·/g, '|')
        .replace(/Âº/g, '')
        .replace(/Ã‚/g, '')
        .replace(/Â/g, '');
    }}

    function normalizeVisibleText(root = document.body) {{
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {{
        acceptNode(node) {{
          const parent = node.parentElement;
          if (!parent || ['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
          return /Ã|Â/.test(node.nodeValue || '') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
        }}
      }});
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(node => {{
        node.nodeValue = fixEncodingText(node.nodeValue);
      }});
    }}

    function compareRows(a, b, field, direction) {{
      const leftRaw = a[field] ?? '';
      const rightRaw = b[field] ?? '';
      const leftNumber = Number(leftRaw);
      const rightNumber = Number(rightRaw);
      const bothNumeric = !Number.isNaN(leftNumber) && !Number.isNaN(rightNumber) && leftRaw !== '' && rightRaw !== '';
      const result = bothNumeric
        ? leftNumber - rightNumber
        : String(leftRaw).localeCompare(String(rightRaw), 'pt-BR', {{ sensitivity: 'base' }});
      return direction === 'asc' ? result : -result;
    }}

    function sortRows(rows, state) {{
      return [...rows].sort((a, b) => compareRows(a, b, state.field, state.direction));
    }}

    function getPageRows(rows, page) {{
      const start = (page - 1) * pageSize;
      return rows.slice(start, start + pageSize);
    }}

    function pageLabel(page, total) {{
      if (!total) return 'Mostrando 0 de 0';
      const start = (page - 1) * pageSize + 1;
      const end = Math.min(page * pageSize, total);
      return `Mostrando ${{formatNumber.format(start)}}-${{formatNumber.format(end)}} de ${{formatNumber.format(total)}}`;
    }}

    function setLoading(isLoading) {{
      document.querySelectorAll('.kpis .card, .grid .card').forEach(element => {{
        element.classList.toggle('loading', isLoading);
      }});
    }}

    function filteredData() {{
      const state = stateFilter.value;
      const party = partyFilter.value;
      const name = nameFilter.value.trim().toLowerCase();

      return DATA.filter(row =>
        (!state || row.siglaUf === state) &&
        (!party || row.siglaPartido === party) &&
        (!name || String(row.nome || '').toLowerCase().includes(name))
      );
    }}

    function filteredPecVotes() {{
      const state = stateFilter.value;
      const party = partyFilter.value;
      const name = nameFilter.value.trim().toLowerCase();
      const term = pecFilter.value.trim().toLowerCase();
      const selectedPec = pecSelect.value;

      return PEC_VOTE_DATA.filter(row => {{
        const haystack = [
          row.proposicao_titulo,
          row.ementa_curta,
          row.nome,
          row.voto_predominante,
          row.siglaPartido,
          row.siglaUf
        ].join(' ').toLowerCase();

        return (!state || row.siglaUf === state) &&
          (!party || row.siglaPartido === party) &&
          (!selectedPec || row.proposicao_titulo === selectedPec) &&
          (!name || String(row.nome || '').toLowerCase().includes(name)) &&
          (!term || haystack.includes(term));
      }});
    }}

    function sum(rows, field) {{
      return rows.reduce((acc, row) => acc + Number(row[field] || 0), 0);
    }}

    function avg(rows, field) {{
      if (!rows.length) return 0;
      return sum(rows, field) / rows.length;
    }}

    function formatSignedPctDiff(value, baseline) {{
      if (!baseline) return 'sem média de referência';
      const diff = (Number(value || 0) - baseline) / baseline * 100;
      const direction = diff >= 0 ? 'acima' : 'abaixo';
      return `${{formatPct.format(Math.abs(diff))}}% ${{direction}}`;
    }}

    function formatSignedPointDiff(value, baseline) {{
      const diff = Number(value || 0) - Number(baseline || 0);
      const direction = diff >= 0 ? 'acima' : 'abaixo';
      return `${{formatPct.format(Math.abs(diff))}} p.p. ${{direction}}`;
    }}

    function partyRowsFor(row) {{
      return DATA.filter(item => item.siglaPartido === row.siglaPartido);
    }}

    function stateRowsFor(row) {{
      return DATA.filter(item => item.siglaUf === row.siglaUf);
    }}

    function getInitials(name) {{
      return String(name || '?').split(/\\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase();
    }}

    function selectedOrFirst(rows) {{
      if (selectedDeputy && rows.some(row => row.idDeputado === selectedDeputy.idDeputado)) return selectedDeputy;
      return rows[0] || DATA[0];
    }}

    function isSingleDeputyView(rows) {{
      return rows.length === 1;
    }}

    function rankPosition(row, field, ascending = false) {{
      const ranked = [...DATA].sort((a, b) =>
        ascending
          ? Number(a[field] || 0) - Number(b[field] || 0)
          : Number(b[field] || 0) - Number(a[field] || 0)
      );
      const index = ranked.findIndex(item => String(item.idDeputado) === String(row.idDeputado));
      return index >= 0 ? index + 1 : null;
    }}

    function positionLabel(position) {{
      if (position) return `${{formatNumber.format(position)}} de ${{formatNumber.format(DATA.length)}}`;
      return 'Sem posicao';
    }}

    function groupedSum(rows, key, value) {{
      const result = new Map();
      rows.forEach(row => result.set(row[key] || 'ND', (result.get(row[key] || 'ND') || 0) + Number(row[value] || 0)));
      return Array.from(result.entries()).sort((a, b) => b[1] - a[1]).slice(0, 12);
    }}

    function groupedAvg(rows, key, value) {{
      const result = new Map();
      rows.forEach(row => {{
        const label = row[key] || 'ND';
        const item = result.get(label) || {{ total: 0, count: 0 }};
        item.total += Number(row[value] || 0);
        item.count += 1;
        result.set(label, item);
      }});
      return Array.from(result.entries())
        .map(([label, item]) => [label, item.count ? item.total / item.count : 0])
        .sort((a, b) => b[1] - a[1])
        .slice(0, 12);
    }}

    function buildPartyRows(rows) {{
      const result = new Map();
      rows.forEach(row => {{
        const label = row.siglaPartido || 'ND';
        const item = result.get(label) || {{
          siglaPartido: label,
          qtd_candidatos: 0,
          gasto_total: 0,
          remuneracao_total: 0,
          custo_total: 0,
          votacoes_pec: 0,
          ids: new Set()
        }};
        item.ids.add(row.idDeputado);
        item.gasto_total += Number(row.valor_liquido_total || 0);
        item.remuneracao_total += Number(row.valor_subsidio_bruto_total || 0);
        item.custo_total += Number(row.custo_total_estimado || 0);
        item.votacoes_pec += Number(row.qtd_votacoes_pec || 0);
        result.set(label, item);
      }});

      const partyRows = Array.from(result.values()).map(item => {{
        item.qtd_candidatos = item.ids.size;
        item.gasto_medio_por_candidato = item.gasto_total / Math.max(item.qtd_candidatos, 1);
        item.custo_por_deputado = item.custo_total / Math.max(item.qtd_candidatos, 1);
        item.pecs_por_deputado = item.votacoes_pec / Math.max(item.qtd_candidatos, 1);
        delete item.ids;
        return item;
      }});

      const totalDeputies = partyRows.reduce((acc, row) => acc + row.qtd_candidatos, 0);
      const totalCost = partyRows.reduce((acc, row) => acc + row.custo_total, 0);
      partyRows.forEach(row => {{
        row.share_deputados_pct = totalDeputies ? row.qtd_candidatos / totalDeputies * 100 : 0;
        row.share_custo_pct = totalCost ? row.custo_total / totalCost * 100 : 0;
      }});
      return partyRows;
    }}

    function metricFormatter(metric) {{
      if (['custo_por_deputado', 'gasto_medio_por_candidato'].includes(metric)) return formatCompactMoneyPrecise;
      if (['custo_total'].includes(metric)) return formatCompactMoney;
      if (['share_custo_pct', 'share_deputados_pct'].includes(metric)) return value => formatPct.format(value) + '%';
      return value => formatNumber.format(Math.round(value));
    }}

    function renderPartyMetricBars(rows) {{
      const metric = partyMetricFilter.value;
      const partyRows = buildPartyRows(rows)
        .sort((a, b) => Number(b[metric] || 0) - Number(a[metric] || 0))
        .slice(0, 12)
        .map(row => [row.siglaPartido, Number(row[metric] || 0)]);
      renderBars('partyBars', partyRows, 'party', metricFormatter(metric));
    }}

    function renderBars(targetId, rows, className, formatter) {{
      const target = document.getElementById(targetId);
      const max = Math.max(...rows.map(row => row[1]), 1);
      target.innerHTML = rows.map(([label, value]) => `
        <div class="bar-row">
          <strong>${{label}}</strong>
          <div class="bar-track"><div class="bar-fill ${{className}}" style="width:${{Math.max((value / max) * 100, 2)}}%"></div></div>
          <span>${{formatter(value)}}</span>
        </div>
      `).join('');
    }}

    function renderStaticBars(targetId, rows, labelField, valueField, className, formatter) {{
      const target = document.getElementById(targetId);
      const values = rows.map(row => Number(row[valueField] || 0));
      const max = Math.max(...values, 1);
      target.innerHTML = rows.slice(0, 12).map(row => {{
        const value = Number(row[valueField] || 0);
        return `
          <div class="bar-row">
            <strong>${{row[labelField] || 'ND'}}</strong>
            <div class="bar-track"><div class="bar-fill ${{className}}" style="width:${{Math.max((value / max) * 100, 2)}}%"></div></div>
            <span>${{formatter(value)}}</span>
          </div>
        `;
      }}).join('');
    }}

    function renderStackedPartyCosts(rows) {{
      const partyRows = buildPartyRows(rows)
        .sort((a, b) => b.custo_total - a.custo_total)
        .slice(0, 10);
      document.getElementById('partyCostStack').innerHTML = partyRows.map(row => {{
        const total = Math.max(row.custo_total, 1);
        const expensePct = row.gasto_total / total * 100;
        const salaryPct = row.remuneracao_total / total * 100;
        return `
          <div class="stack-row">
            <div class="stack-head"><span>${{row.siglaPartido}}</span><span>${{formatCompactMoney(row.custo_total)}}</span></div>
            <div class="stack-track">
              <div class="stack-segment-expense" style="width:${{expensePct}}%"></div>
              <div class="stack-segment-salary" style="width:${{salaryPct}}%"></div>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function renderPartyShareCompare(rows) {{
      const partyRows = buildPartyRows(rows)
        .sort((a, b) => b.share_custo_pct - a.share_custo_pct)
        .slice(0, 10);
      document.getElementById('partyShareCompare').innerHTML = partyRows.map(row => `
        <div class="stack-row">
          <div class="stack-head"><span>${{row.siglaPartido}}</span><span>${{formatPct.format(row.share_custo_pct)}}% custo | ${{formatPct.format(row.share_deputados_pct)}}% bancada</span></div>
          <div class="stack-track">
            <div class="stack-segment-expense" style="width:${{Math.max(row.share_custo_pct, 2)}}%"></div>
          </div>
          <div class="stack-track">
            <div class="stack-segment-salary" style="width:${{Math.max(row.share_deputados_pct, 2)}}%"></div>
          </div>
        </div>
      `).join('');
    }}

    function renderQuickInsights(rows) {{
      const pool = rows.length ? rows : DATA;
      if (isSingleDeputyView(rows)) {{
        const row = rows[0];
        const cleanCards = [
          ['Media da Camara', 'Custo total', formatCompactMoney(avg(DATA, 'custo_total_estimado'))],
          [`Media do ${{row.siglaPartido}}`, 'Custo total', formatCompactMoney(avg(partyRowsFor(row), 'custo_total_estimado'))],
          [`Media de ${{row.siglaUf}}`, 'Custo total', formatCompactMoney(avg(stateRowsFor(row), 'custo_total_estimado'))],
          ['Posicao em custo', row.nome, positionLabel(rankPosition(row, 'custo_total_estimado'))]
        ];
        document.getElementById('quickInsights').innerHTML = cleanCards.map(([label, title, value]) => `
          <div class="quick-card">
            <span>${{escapeHtml(label)}}</span>
            <strong>${{escapeHtml(title)}}</strong>
            <em>${{escapeHtml(value)}}</em>
          </div>
        `).join('');
        return;
      }}
      if (isSingleDeputyView(rows)) {{
        const row = rows[0];
        const cards = [
          ['MÃ©dia da CÃ¢mara', 'Custo total', formatCompactMoney(avg(DATA, 'custo_total_estimado'))],
          [`MÃ©dia do ${{row.siglaPartido}}`, 'Custo total', formatCompactMoney(avg(partyRowsFor(row), 'custo_total_estimado'))],
          [`MÃ©dia de ${{row.siglaUf}}`, 'Custo total', formatCompactMoney(avg(stateRowsFor(row), 'custo_total_estimado'))],
          ['PosiÃ§Ã£o em custo', row.nome, positionLabel(rankPosition(row, 'custo_total_estimado'))]
        ];
        document.getElementById('quickInsights').innerHTML = cards.map(([label, title, value]) => `
          <div class="quick-card">
            <span>${{escapeHtml(label)}}</span>
            <strong>${{escapeHtml(title)}}</strong>
            <em>${{escapeHtml(value)}}</em>
          </div>
        `).join('');
        return;
      }}
      const byCost = [...pool].sort((a, b) => Number(b.custo_total_estimado || 0) - Number(a.custo_total_estimado || 0))[0];
      const byCostPresence = [...pool].sort((a, b) => Number(b.custo_por_presenca || 0) - Number(a.custo_por_presenca || 0))[0];
      const byYoy = [...pool].sort((a, b) => Number(b.diferenca_yoy || 0) - Number(a.diferenca_yoy || 0))[0];
      const byAbsence = [...pool].sort((a, b) => Number(b.pct_ausencia_nao_justificada || 0) - Number(a.pct_ausencia_nao_justificada || 0))[0];
      const spotlight = selectedOrFirst(pool);
      const cards = [
        ['Maior custo total', byCost, formatCompactMoney(byCost?.custo_total_estimado)],
        ['Maior custo por presença', byCostPresence, formatCompactMoney(byCostPresence?.custo_por_presenca)],
        ['Maior aumento no ano', byYoy, formatCompactMoney(byYoy?.diferenca_yoy)],
        ['Mais ausências não justificadas', byAbsence, formatPct.format(Number(byAbsence?.pct_ausencia_nao_justificada || 0)) + '%'],
        ['Deputado em destaque', spotlight, formatCompactMoney(spotlight?.custo_total_estimado)]
      ];
      document.getElementById('quickInsights').innerHTML = cards.map(([label, row, value]) => `
        <div class="quick-card">
          <span>${{label}}</span>
          <strong>${{escapeHtml(row?.nome || 'Sem dados')}}</strong>
          <em>${{escapeHtml(row ? `${{row.siglaPartido}}-${{row.siglaUf}} · ${{value}}` : '')}}</em>
        </div>
      `).join('');
    }}

    function renderDeputyProfile(rows) {{
      const row = selectedOrFirst(rows);
      if (!row) return;
      selectedDeputy = row;
      const partyRows = partyRowsFor(row);
      const stateRows = stateRowsFor(row);
      const chamberAvgCost = avg(DATA, 'custo_total_estimado');
      const partyAvgCost = avg(partyRows, 'custo_total_estimado');
      const stateAvgCost = avg(stateRows, 'custo_total_estimado');
      const chamberPresence = avg(DATA, 'indice_presenca_relativa');
      document.getElementById('deputyProfile').innerHTML = `
        <div class="avatar">${{escapeHtml(getInitials(row.nome))}}</div>
        <div class="profile-main">
          <div>
            <h2>${{escapeHtml(row.nome)}}</h2>
            <div class="profile-meta">${{escapeHtml(row.siglaPartido)}}-${{escapeHtml(row.siglaUf)}}</div>
          </div>
          <div class="profile-grid">
            <div class="profile-stat"><span>Custo total aproximado</span><strong>${{formatCompactMoney(row.custo_total_estimado)}}</strong></div>
            <div class="profile-stat"><span>Gasto parlamentar</span><strong>${{formatCompactMoney(row.valor_liquido_total)}}</strong></div>
            <div class="profile-stat"><span>Salários no período</span><strong>${{formatCompactMoney(row.valor_subsidio_bruto_total)}}</strong></div>
            <div class="profile-stat"><span>Presença comparada</span><strong>${{formatPct.format(Number(row.indice_presenca_relativa || 0))}}%</strong></div>
            <div class="profile-stat"><span>Ausência não just.</span><strong>${{formatPct.format(Number(row.pct_ausencia_nao_justificada || 0))}}%</strong></div>
            <div class="profile-stat"><span>Votos em PECs</span><strong>${{formatNumber.format(Number(row.qtd_votacoes_pec || 0))}}</strong></div>
          </div>
          <div class="comparison-list">
            <span>Custo total: ${{formatSignedPctDiff(row.custo_total_estimado, chamberAvgCost)}} da media da Camara.</span>
            <span>Comparação com partido: ${{formatSignedPctDiff(row.custo_total_estimado, partyAvgCost)}} da média do ${{escapeHtml(row.siglaPartido)}}.</span>
            <span>Comparação com UF: ${{formatSignedPctDiff(row.custo_total_estimado, stateAvgCost)}} da média de ${{escapeHtml(row.siglaUf)}}.</span>
            <span>Presença: ${{formatSignedPointDiff(row.indice_presenca_relativa, chamberPresence)}} da média geral.</span>
          </div>
          <div class="notice">Atencao: maior gasto parlamentar nao significa, sozinho, pior atuacao. O dado deve ser analisado junto com presenca, justificativas, estado de origem, atividade parlamentar e tipo de despesa.</div>
        </div>
      `;
    }}

    function rankContext(row, valueField) {{
      const chamberAvgClean = avg(DATA, valueField);
      const partyAvgClean = avg(partyRowsFor(row), valueField);
      const stateAvgClean = avg(stateRowsFor(row), valueField);
      return `${{formatSignedPctDiff(row[valueField], chamberAvgClean)}} da media da Camara | ${{formatSignedPctDiff(row[valueField], partyAvgClean)}} do partido | ${{formatSignedPctDiff(row[valueField], stateAvgClean)}} da UF`;
      const chamberAvg = avg(DATA, valueField);
      const partyAvg = avg(partyRowsFor(row), valueField);
      const stateAvg = avg(stateRowsFor(row), valueField);
      return `${{formatSignedPctDiff(row[valueField], chamberAvg)}} da média da Câmara · ${{formatSignedPctDiff(row[valueField], partyAvg)}} do partido · ${{formatSignedPctDiff(row[valueField], stateAvg)}} da UF`;
    }}

    function renderRanking(targetId, rows, field, formatter, limit = 10, ascending = false) {{
      const ranked = [...rows]
        .sort((a, b) => ascending ? Number(a[field] || 0) - Number(b[field] || 0) : Number(b[field] || 0) - Number(a[field] || 0))
        .slice(0, limit);
      document.getElementById(targetId).innerHTML = ranked.map((row, index) => `
        <div class="rank-item">
          <div class="rank-head"><span>${{index + 1}}. ${{escapeHtml(row.nome)}} <small>${{escapeHtml(row.siglaPartido)}}-${{escapeHtml(row.siglaUf)}}</small></span><strong>${{formatter(row[field])}}</strong></div>
          <div class="rank-context">${{rankContext(row, field)}} · Variação anual da cota: ${{formatCompactMoney(row.diferenca_yoy)}}</div>
        </div>
      `).join('');
    }}

    function renderRankingPosition(targetId, row, field, formatter, ascending = false) {{
      const position = rankPosition(row, field, ascending);
      document.getElementById(targetId).innerHTML = `
        <div class="rank-item">
          <div class="rank-head"><span>${{positionLabel(position)}}</span><strong>${{formatter(row[field])}}</strong></div>
          <div class="rank-context">${{rankContext(row, field)}} | Variacao anual da cota: ${{formatCompactMoney(row.diferenca_yoy)}}</div>
        </div>
      `;
      return;
      document.getElementById(targetId).innerHTML = `
        <div class="rank-item">
          <div class="rank-head"><span>${{positionLabel(position)}}</span><strong>${{formatter(row[field])}}</strong></div>
          <div class="rank-context">${{rankContext(row, field)}} Â· VariaÃ§Ã£o anual da cota: ${{formatCompactMoney(row.diferenca_yoy)}}</div>
        </div>
      `;
    }}

    function renderRankings(rows) {{
      const pool = rows.length ? rows : DATA;
      if (isSingleDeputyView(rows)) {{
        const row = rows[0];
        renderRankingPosition('rankCost', row, 'custo_total_estimado', formatCompactMoney);
        renderRankingPosition('rankCostPresence', row, 'custo_por_presenca', formatCompactMoney);
        renderRankingPosition('rankYoy', row, 'diferenca_yoy', formatCompactMoney);
        renderRankingPosition('rankAbsence', row, 'pct_ausencia_nao_justificada', value => formatPct.format(Number(value || 0)) + '%');
        return;
      }}
      renderRanking('rankCost', pool, 'custo_total_estimado', formatCompactMoney);
      renderRanking('rankCostPresence', pool, 'custo_por_presenca', formatCompactMoney);
      renderRanking('rankYoy', pool, 'diferenca_yoy', formatCompactMoney);
      renderRanking('rankAbsence', pool, 'pct_ausencia_nao_justificada', value => formatPct.format(Number(value || 0)) + '%');
    }}

    function renderMatrix(rows) {{
      const pool = (rows.length ? rows : DATA).slice(0, window.matchMedia('(max-width: 720px)').matches ? 80 : 160);
      const maxCost = Math.max(...pool.map(row => Number(row.custo_total_estimado || 0)), 1);
      const maxPresence = Math.max(...pool.map(row => Number(row.indice_presenca_relativa || 0)), 1);
      const maxExpense = Math.max(...pool.map(row => Number(row.valor_liquido_total || 0)), 1);
      document.getElementById('attentionMatrix').innerHTML = `
        <div class="matrix-label tl">Baixo custo + alta presença<br>Boa eficiência relativa</div>
        <div class="matrix-label tr">Alto custo + alta presença<br>Custo alto, mas com atividade registrada</div>
        <div class="matrix-label bl">Baixo custo + baixa presença<br>Baixa atividade aparente</div>
        <div class="matrix-label br">Alto custo + baixa presença<br>Ponto de atenção</div>
      ` + pool.map(row => {{
        const x = Number(row.custo_total_estimado || 0) / maxCost * 92 + 4;
        const y = Number(row.indice_presenca_relativa || 0) / maxPresence * 88 + 6;
        const size = Math.max(8, Math.min(24, Number(row.valor_liquido_total || 0) / maxExpense * 22));
        return `<button class="matrix-dot" type="button" data-deputy-id="${{row.idDeputado}}" title="${{escapeHtml(row.nome)}} · ${{escapeHtml(row.siglaPartido)}}-${{escapeHtml(row.siglaUf)}} · custo ${{formatCompactMoney(row.custo_total_estimado)}} · presença ${{formatPct.format(Number(row.indice_presenca_relativa || 0))}}%" style="left:${{x}}%; bottom:${{y}}%; width:${{size}}px; height:${{size}}px;"></button>`;
      }}).join('');
    }}

    function buildVideoScript(row) {{
      const partyAvgCost = avg(partyRowsFor(row), 'custo_total_estimado');
      const stateAvgCost = avg(stateRowsFor(row), 'custo_total_estimado');
      return `Voce sabe quanto custou a atuacao do deputado ${{row.nome}}, do ${{row.siglaPartido}}-${{row.siglaUf}}, no periodo analisado?

Segundo dados publicos organizados neste painel, o custo total aproximado foi de ${{formatCompactMoney(row.custo_total_estimado)}}.

Esse valor fica ${{formatSignedPctDiff(row.custo_total_estimado, partyAvgCost)}} da media dos deputados do mesmo partido e ${{formatSignedPctDiff(row.custo_total_estimado, stateAvgCost)}} da media dos deputados do mesmo estado.

No mesmo periodo, a presenca comparada aos demais foi de ${{formatPct.format(Number(row.indice_presenca_relativa || 0))}}%, e o painel registra ${{formatNumber.format(Number(row.qtd_votacoes_pec || 0))}} votacoes em PECs.

Mas atencao: gasto parlamentar sozinho nao conta a historia toda. Tambem e preciso olhar presenca, ausencias, tipo de despesa, estado de origem e votacoes.

Fontes: Camara dos Deputados, Senado Federal, TSE, ALERJ e DOCIGP/ALERJ. Consulta realizada em {data_updated_label}.`;
    }}

    function renderCreator(rows) {{
      const row = selectedOrFirst(rows);
      if (row) document.getElementById('videoScript').value = buildVideoScript(row);
    }}

    function classForDelta(value) {{
      return Number(value || 0) > 0 ? 'positive' : 'negative';
    }}

    function setYoySubtext(id, value, prefix = 'Dif. YoY do gasto parlamentar') {{
      const target = document.getElementById(id);
      target.textContent = `${{prefix}}: ${{formatCompactMoney(value)}}`;
      target.classList.toggle('positive', Number(value || 0) > 0);
      target.classList.toggle('negative', Number(value || 0) <= 0);
    }}

    function setNeutralSubtext(id, text) {{
      const target = document.getElementById(id);
      target.textContent = text;
      target.classList.remove('positive', 'negative');
    }}

    function setPointDiffSubtext(id, value, invert = false) {{
      const target = document.getElementById(id);
      const sign = value > 0 ? '+' : '';
      target.textContent = `Vs. media Brasil: ${{sign}}${{formatPct.format(value)}} p.p.`;
      target.classList.toggle('positive', invert ? value < 0 : value > 0);
      target.classList.toggle('negative', invert ? value >= 0 : value <= 0);
      return;
      target.textContent = `Vs. média Brasil: ${{sign}}${{formatPct.format(value)}} p.p.`;
      target.classList.toggle('positive', invert ? value < 0 : value > 0);
      target.classList.toggle('negative', invert ? value >= 0 : value <= 0);
    }}

    function setMetricLabel(valueId, label) {{
      const labelEl = document.getElementById(valueId).closest('.card').querySelector('.metric-label');
      if (labelEl && labelEl.childNodes.length) {{
        labelEl.childNodes[0].nodeValue = label + ' ';
      }}
    }}

    function renderAggregateKpis(rows, expenseYoy, costTotal, presenceDiff, absenceDiff, pecAvg) {{
      setMetricLabel('kpiDeputies', 'Deputados');
      setMetricLabel('kpiExpenses', 'Gasto parlamentar');
      setMetricLabel('kpiSalary', 'RemuneraÃ§Ã£o');
      setMetricLabel('kpiCost', 'Custo total');
      setMetricLabel('kpiPresencePct', '% presenÃ§a relativa');
      setMetricLabel('kpiUnjustifiedAbsence', '% ausÃªncia nÃ£o just.');
      setMetricLabel('kpiPecVotes', 'VotaÃ§Ãµes PEC');
      setMetricLabel('kpiSalary', 'Remuneracao estimada');
      setMetricLabel('kpiPresencePct', 'Presenca rel. eventos');
      setMetricLabel('kpiUnjustifiedAbsence', 'Ausencia nao just.');
      setMetricLabel('kpiPecVotes', 'Registros votos PEC');
      document.getElementById('kpiDeputies').textContent = formatNumber.format(rows.length);
      document.getElementById('kpiExpenses').textContent = formatCompactMoney(sum(rows, 'valor_liquido_total'));
      document.getElementById('kpiSalary').textContent = formatCompactMoney(sum(rows, 'valor_subsidio_bruto_total'));
      document.getElementById('kpiCost').textContent = formatCompactMoney(sum(rows, 'custo_total_estimado'));
      document.getElementById('kpiPresencePct').textContent = formatPct.format(avg(rows, 'indice_presenca_relativa')) + '%';
      document.getElementById('kpiUnjustifiedAbsence').textContent = formatPct.format(avg(rows, 'pct_ausencia_nao_justificada')) + '%';
      document.getElementById('kpiPecVotes').textContent = formatNumber.format(sum(rows, 'qtd_votacoes_pec'));
      setYoySubtext('kpiExpensesYoy', expenseYoy, 'YoY do gasto parlamentar');
      setNeutralSubtext('kpiSalaryContext', 'Subsidio estimado, sem serie YoY');
      setYoySubtext('kpiCostYoy', expenseYoy, costTotal ? `YoY do gasto parlamentar (${{formatPct.format(expenseYoy / costTotal * 100)}}% do custo)` : 'YoY do gasto parlamentar');
      setPointDiffSubtext('kpiPresenceContext', presenceDiff);
      setPointDiffSubtext('kpiAbsenceContext', absenceDiff, true);
      setNeutralSubtext('kpiPecContext', `Media por deputado: ${{formatPct.format(pecAvg)}}`);
    }}

    function renderSingleDeputyKpis(row) {{
      setMetricLabel('kpiDeputies', 'Recorte');
      setMetricLabel('kpiExpenses', 'Gasto parlamentar');
      setMetricLabel('kpiSalary', 'Remuneracao estimada');
      setMetricLabel('kpiCost', 'Custo do deputado');
      setMetricLabel('kpiPresencePct', 'Presenca do deputado');
      setMetricLabel('kpiUnjustifiedAbsence', 'Ausencia nao just.');
      setMetricLabel('kpiPecVotes', 'Votacoes PEC');
      document.getElementById('kpiDeputies').textContent = '1 deputado';
      document.getElementById('kpiExpenses').textContent = formatCompactMoney(row.valor_liquido_total);
      document.getElementById('kpiSalary').textContent = formatCompactMoney(row.valor_subsidio_bruto_total);
      document.getElementById('kpiCost').textContent = formatCompactMoney(row.custo_total_estimado);
      document.getElementById('kpiPresencePct').textContent = formatPct.format(Number(row.indice_presenca_relativa || 0)) + '%';
      document.getElementById('kpiUnjustifiedAbsence').textContent = formatPct.format(Number(row.pct_ausencia_nao_justificada || 0)) + '%';
      document.getElementById('kpiPecVotes').textContent = formatNumber.format(Number(row.qtd_votacoes_pec || 0));
      setNeutralSubtext('kpiExpensesYoy', `${{formatSignedPctDiff(row.valor_liquido_total, avg(DATA, 'valor_liquido_total'))}} da media da Camara`);
      setNeutralSubtext('kpiSalaryContext', `${{formatSignedPctDiff(row.valor_subsidio_bruto_total, avg(DATA, 'valor_subsidio_bruto_total'))}} da media da Camara`);
      setNeutralSubtext('kpiCostYoy', `${{formatSignedPctDiff(row.custo_total_estimado, avg(DATA, 'custo_total_estimado'))}} da media da Camara`);
      setNeutralSubtext('kpiPresenceContext', `${{formatSignedPointDiff(row.indice_presenca_relativa, nationalPresenceAvg)}} da media geral`);
      setNeutralSubtext('kpiAbsenceContext', `${{formatSignedPointDiff(row.pct_ausencia_nao_justificada, nationalUnjustifiedAbsenceAvg)}} da media geral`);
      setNeutralSubtext('kpiPecContext', positionLabel(rankPosition(row, 'qtd_votacoes_pec')));
      return;
      setMetricLabel('kpiDeputies', 'Recorte');
      setMetricLabel('kpiExpenses', 'Gasto parlamentar');
      setMetricLabel('kpiSalary', 'RemuneraÃ§Ã£o estimada');
      setMetricLabel('kpiCost', 'Custo do deputado');
      setMetricLabel('kpiPresencePct', 'PresenÃ§a do deputado');
      setMetricLabel('kpiUnjustifiedAbsence', 'AusÃªncia nÃ£o just.');
      setMetricLabel('kpiPecVotes', 'VotaÃ§Ãµes PEC');
      document.getElementById('kpiDeputies').textContent = '1 deputado';
      document.getElementById('kpiExpenses').textContent = formatCompactMoney(row.valor_liquido_total);
      document.getElementById('kpiSalary').textContent = formatCompactMoney(row.valor_subsidio_bruto_total);
      document.getElementById('kpiCost').textContent = formatCompactMoney(row.custo_total_estimado);
      document.getElementById('kpiPresencePct').textContent = formatPct.format(Number(row.indice_presenca_relativa || 0)) + '%';
      document.getElementById('kpiUnjustifiedAbsence').textContent = formatPct.format(Number(row.pct_ausencia_nao_justificada || 0)) + '%';
      document.getElementById('kpiPecVotes').textContent = formatNumber.format(Number(row.qtd_votacoes_pec || 0));
      setNeutralSubtext('kpiExpensesYoy', `${{formatSignedPctDiff(row.valor_liquido_total, avg(DATA, 'valor_liquido_total'))}} da mÃ©dia da CÃ¢mara`);
      setNeutralSubtext('kpiSalaryContext', `${{formatSignedPctDiff(row.valor_subsidio_bruto_total, avg(DATA, 'valor_subsidio_bruto_total'))}} da mÃ©dia da CÃ¢mara`);
      setNeutralSubtext('kpiCostYoy', `${{formatSignedPctDiff(row.custo_total_estimado, avg(DATA, 'custo_total_estimado'))}} da mÃ©dia da CÃ¢mara`);
      setNeutralSubtext('kpiPresenceContext', `${{formatSignedPointDiff(row.indice_presenca_relativa, nationalPresenceAvg)}} da mÃ©dia geral`);
      setNeutralSubtext('kpiAbsenceContext', `${{formatSignedPointDiff(row.pct_ausencia_nao_justificada, nationalUnjustifiedAbsenceAvg)}} da mÃ©dia geral`);
      setNeutralSubtext('kpiPecContext', positionLabel(rankPosition(row, 'qtd_votacoes_pec')));
    }}

    function renderTable(rows) {{
      const sortedRows = sortRows(rows, candidateSort);
      const maxPage = Math.max(Math.ceil(sortedRows.length / pageSize), 1);
      candidatePage = Math.min(candidatePage, maxPage);
      const pageRows = getPageRows(sortedRows, candidatePage);
      document.getElementById('candidateTableStatus').textContent = pageLabel(candidatePage, sortedRows.length) + ' deputados';
      document.getElementById('candidatePageStatus').textContent = `Página ${{formatNumber.format(candidatePage)}} de ${{formatNumber.format(maxPage)}}`;
      document.getElementById('candidatePrevPage').disabled = candidatePage <= 1;
      document.getElementById('candidateNextPage').disabled = candidatePage >= maxPage;
      lastCandidateRows = sortedRows;

      document.getElementById('tableBody').innerHTML = pageRows.map(row => `
        <tr>
          <td>${{escapeHtml(row.nome)}}</td>
          <td>${{escapeHtml(row.siglaPartido)}}</td>
          <td>${{escapeHtml(row.siglaUf)}}</td>
          <td class="num">${{formatMoney.format(Number(row.valor_liquido_total || 0))}}</td>
          <td class="num">${{formatMoney.format(Number(row.valor_subsidio_bruto_total || 0))}}</td>
          <td class="num">${{formatMoney.format(Number(row.custo_total_estimado || 0))}}</td>
          <td class="num">${{formatPct.format(Number(row.indice_presenca_relativa || 0))}}%</td>
          <td class="num">${{formatPct.format(Number(row.pct_ausencia_justificada || 0))}}%</td>
          <td class="num">${{formatPct.format(Number(row.pct_ausencia_nao_justificada || 0))}}%</td>
          <td class="num">${{formatNumber.format(Number(row.qtd_votacoes_pec || 0))}}</td>
          <td class="num ${{classForDelta(row.diferenca_yoy)}}">${{formatMoney.format(Number(row.diferenca_yoy || 0))}}</td>
          <td class="num ${{classForDelta(row.dif_gasto_media_candidato)}}">${{formatMoney.format(Number(row.dif_gasto_media_candidato || 0))}}</td>
          <td class="num">${{formatMoney.format(Number(row.custo_por_presenca || 0))}}</td>
        </tr>
      `).join('');

      document.getElementById('deputyCardList').innerHTML = pageRows.map(row => `
        <article class="mobile-data-card">
          <div class="mobile-card-title">
            <span>${{escapeHtml(row.nome)}}</span>
            <span>${{escapeHtml(row.siglaPartido)}}/${{escapeHtml(row.siglaUf)}}</span>
          </div>
          <div class="mobile-card-grid">
            <span>Gasto parlamentar<b>${{formatCompactMoney(Number(row.valor_liquido_total || 0))}}</b></span>
            <span>Custo total<b>${{formatCompactMoney(Number(row.custo_total_estimado || 0))}}</b></span>
            <span>Presença rel.<b>${{formatPct.format(Number(row.indice_presenca_relativa || 0))}}%</b></span>
            <span>PECs<b>${{formatNumber.format(Number(row.qtd_votacoes_pec || 0))}}</b></span>
            <span>Aus. não just.<b>${{formatPct.format(Number(row.pct_ausencia_nao_justificada || 0))}}%</b></span>
            <span>YoY<b>${{formatCompactMoney(Number(row.diferenca_yoy || 0))}}</b></span>
          </div>
        </article>
      `).join('');
    }}

    function renderPecVotes(rows) {{
      const sortedRows = sortRows(rows, pecSort);
      const maxPage = Math.max(Math.ceil(sortedRows.length / pageSize), 1);
      pecPage = Math.min(pecPage, maxPage);
      const pageRows = getPageRows(sortedRows, pecPage);
      document.getElementById('pecTableStatus').textContent = pageLabel(pecPage, sortedRows.length) + ' votos em PECs';
      document.getElementById('pecPageStatus').textContent = `Página ${{formatNumber.format(pecPage)}} de ${{formatNumber.format(maxPage)}}`;
      document.getElementById('pecPrevPage').disabled = pecPage <= 1;
      document.getElementById('pecNextPage').disabled = pecPage >= maxPage;
      lastPecRows = sortedRows;

      document.getElementById('pecVoteBody').innerHTML = pageRows.map(row => `
        <tr>
          <td>${{escapeHtml(row.data_ultima)}}</td>
          <td>${{escapeHtml(row.nome)}}</td>
          <td>${{escapeHtml(row.siglaPartido)}}</td>
          <td>${{escapeHtml(row.siglaUf)}}</td>
          <td>
            <div class="pec-title">${{escapeHtml(row.proposicao_titulo || 'PEC')}}</div>
            <div class="pec-desc">${{escapeHtml(row.ementa_curta)}}</div>
          </td>
          <td><strong>${{escapeHtml(row.voto_predominante)}}</strong></td>
          <td class="num">${{formatNumber.format(Number(row.votos_sim || 0))}}</td>
          <td class="num">${{formatNumber.format(Number(row.votos_nao || 0))}}</td>
          <td class="num">${{formatNumber.format(Number(row.votos_obstrucao || 0) + Number(row.votos_outros || 0))}}</td>
          <td>${{escapeHtml(row.siglaOrgao)}}</td>
        </tr>
      `).join('');

      document.getElementById('pecVoteCards').innerHTML = pageRows.map(row => `
        <article class="mobile-data-card">
          <div class="mobile-card-title">
            <span>${{escapeHtml(row.proposicao_titulo || 'PEC')}}</span>
            <span>${{escapeHtml(row.voto_predominante)}}</span>
          </div>
          <div class="mobile-card-meta">
            <span>${{escapeHtml(row.data_ultima)}}</span>
            <span>${{escapeHtml(row.nome)}}</span>
            <span>${{escapeHtml(row.siglaPartido)}}/${{escapeHtml(row.siglaUf)}}</span>
          </div>
          <div class="pec-desc">${{escapeHtml(row.ementa_curta)}}</div>
          <div class="mobile-card-grid">
            <span>Sim<b>${{formatNumber.format(Number(row.votos_sim || 0))}}</b></span>
            <span>Não<b>${{formatNumber.format(Number(row.votos_nao || 0))}}</b></span>
            <span>Outros<b>${{formatNumber.format(Number(row.votos_obstrucao || 0) + Number(row.votos_outros || 0))}}</b></span>
            <span>Órgão<b>${{escapeHtml(row.siglaOrgao)}}</b></span>
          </div>
        </article>
      `).join('');
    }}

    function updateActiveFilters() {{
      const chips = [
        {{ label: stateFilter.value || 'Brasil', target: stateFilter, type: 'uf' }},
        {{ label: partyFilter.value || 'Todos os partidos', target: partyFilter, type: 'partido' }},
        {{ label: nameFilter.value.trim() || 'Todos os deputados', target: nameFilter, type: 'deputado' }},
        {{ label: pecSelect.value || 'Todas as PECs', target: pecSelect, type: 'pec' }}
      ];
      document.getElementById('activeFilters').innerHTML = '<strong>Mostrando:</strong>' + chips.map(item => {{
        const canRemove = item.target.value || item.target === nameFilter && nameFilter.value.trim();
        const button = canRemove ? `<button type="button" data-clear-filter="${{item.type}}" aria-label="Remover filtro ${{escapeHtml(item.label)}}">x</button>` : '';
        return `<span class="chip">${{escapeHtml(item.label)}}${{button}}</span>`;
      }}).join('');
      updateClearFiltersVisibility();
    }}

    function hasActiveFilters() {{
      return Boolean(stateFilter.value || partyFilter.value || nameFilter.value.trim() || pecFilter.value.trim() || pecSelect.value || mainSearch.value.trim());
    }}

    function updateClearFiltersVisibility() {{
      document.getElementById('clearAllFilters').classList.toggle('is-hidden', !hasActiveFilters());
    }}

    function updateSortHeaders() {{
      document.querySelectorAll('th[data-sort]').forEach(header => {{
        const state = header.dataset.table === 'pec' ? pecSort : candidateSort;
        header.classList.toggle('sorted-asc', header.dataset.sort === state.field && state.direction === 'asc');
        header.classList.toggle('sorted-desc', header.dataset.sort === state.field && state.direction === 'desc');
      }});
    }}

    function updateUrl() {{
      const params = new URLSearchParams();
      if (stateFilter.value) params.set('uf', stateFilter.value);
      if (partyFilter.value) params.set('partido', partyFilter.value);
      if (nameFilter.value.trim()) params.set('deputado', nameFilter.value.trim());
      if (pecSelect.value) params.set('pec', pecSelect.value);
      const query = params.toString();
      const nextUrl = window.location.pathname + (query ? '?' + query : '') + window.location.hash;
      window.history.replaceState(null, '', nextUrl);
    }}

    function applyUrlFilters() {{
      const params = new URLSearchParams(window.location.search);
      stateFilter.value = params.get('uf') || '';
      partyFilter.value = params.get('partido') || '';
      nameFilter.value = params.get('deputado') || '';
      mainSearch.value = params.get('deputado') || params.get('partido') || params.get('uf') || '';
      pecSelect.value = params.get('pec') || '';
    }}

    function populateMainSearchList() {{
      const deputyOptions = DATA
        .slice()
        .sort((a, b) => String(a.nome || '').localeCompare(String(b.nome || ''), 'pt-BR'))
        .map(row => `<option value="${{escapeHtml(row.nome)}} (${{escapeHtml(row.siglaPartido)}}-${{escapeHtml(row.siglaUf)}})">`);
      const deputyNameOptions = DATA
        .slice()
        .sort((a, b) => String(a.nome || '').localeCompare(String(b.nome || ''), 'pt-BR'))
        .map(row => `<option value="${{escapeHtml(row.nome)}}">`);
      const partyOptions = PARTIES.map(value => `<option value="${{escapeHtml(value)}}">`);
      const stateOptions = STATES.map(value => `<option value="${{escapeHtml(value)}}">`);
      deputySearchList.innerHTML = deputyNameOptions.join('');
      mainSearchList.innerHTML = deputyOptions.concat(partyOptions, stateOptions).join('');
    }}

    function applyMainSearch(value) {{
      const raw = value.trim();
      const upper = raw.toUpperCase();
      const nameOnly = raw.replace(/\\s+\\([^)]+\\)\\s*$/, '');
      if (!raw) {{
        nameFilter.value = '';
        selectedDeputy = null;
        return;
      }}
      if (STATES.includes(upper)) {{
        stateFilter.value = upper;
        nameFilter.value = '';
        selectedDeputy = null;
        return;
      }}
      if (PARTIES.includes(upper)) {{
        partyFilter.value = upper;
        nameFilter.value = '';
        selectedDeputy = null;
        return;
      }}
      nameFilter.value = nameOnly;
      selectedDeputy = DATA.find(row => String(row.nome || '').toLowerCase() === nameOnly.toLowerCase()) ||
        DATA.find(row => String(row.nome || '').toLowerCase().includes(nameOnly.toLowerCase())) ||
        null;
    }}

    function resetPages() {{
      candidatePage = 1;
      pecPage = 1;
    }}

    function scheduleRender({{ reset = true, syncUrl = true }} = {{}}) {{
      if (reset) resetPages();
      setLoading(true);
      window.requestAnimationFrame(() => {{
        render();
        updateSortHeaders();
        updateStickyOffset();
        if (syncUrl) updateUrl();
        setLoading(false);
      }});
    }}

    function csvValue(value) {{
      return '"' + String(value ?? '').replace(/"/g, '""') + '"';
    }}

    function downloadCsv(filename, rows, columns) {{
      const header = columns.map(column => csvValue(column.label)).join(',');
      const body = rows.map(row => columns.map(column => csvValue(row[column.field])).join(',')).join('\\n');
      const blob = new Blob([header + '\\n' + body], {{ type: 'text/csv;charset=utf-8;' }});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
    }}

    function copyText(text) {{
      if (navigator.clipboard) {{
        navigator.clipboard.writeText(text);
        return;
      }}
      const tmp = document.createElement('textarea');
      tmp.value = text;
      document.body.appendChild(tmp);
      tmp.select();
      document.execCommand('copy');
      document.body.removeChild(tmp);
    }}

    function exportStoryCard() {{
      const row = selectedDeputy || selectedOrFirst(filteredData());
      const canvas = document.createElement('canvas');
      canvas.width = 1080;
      canvas.height = 1920;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#f7f9fb';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#1351b4';
      ctx.fillRect(0, 0, canvas.width, 150);
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 46px Arial';
      ctx.fillText('Câmara 2026', 70, 95);
      ctx.fillStyle = '#071d41';
      ctx.font = 'bold 58px Arial';
      ctx.fillText(row.nome, 70, 260);
      ctx.font = 'bold 36px Arial';
      ctx.fillText(`${{row.siglaPartido}}-${{row.siglaUf}}`, 70, 320);
      const items = [
        ['Custo total aproximado', formatCompactMoney(row.custo_total_estimado)],
        ['Gasto parlamentar', formatCompactMoney(row.valor_liquido_total)],
        ['Presença comparada aos demais', formatPct.format(Number(row.indice_presenca_relativa || 0)) + '%'],
        ['Ausência não justificada', formatPct.format(Number(row.pct_ausencia_nao_justificada || 0)) + '%'],
        ['Votos em PECs', formatNumber.format(Number(row.qtd_votacoes_pec || 0))]
      ];
      let y = 460;
      items.forEach(([label, value]) => {{
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(70, y, 940, 160);
        ctx.strokeStyle = '#d6e0ef';
        ctx.strokeRect(70, y, 940, 160);
        ctx.fillStyle = '#56616f';
        ctx.font = 'bold 28px Arial';
        ctx.fillText(label.toUpperCase(), 105, y + 52);
        ctx.fillStyle = '#071d41';
        ctx.font = 'bold 46px Arial';
        ctx.fillText(value, 105, y + 112);
        y += 190;
      }});
      ctx.fillStyle = '#604a00';
      ctx.font = '28px Arial';
      wrapCanvasText(ctx, 'Use estes dados com responsabilidade. O painel aponta padrões e comparações, não comprova irregularidades individualmente.', 70, 1480, 920, 38);
      ctx.fillStyle = '#56616f';
      ctx.font = '24px Arial';
      wrapCanvasText(ctx, sourceText, 70, 1700, 920, 34);
      const link = document.createElement('a');
      link.href = canvas.toDataURL('image/png');
      link.download = `camara-2026-${{String(row.nome || 'deputado').toLowerCase().replace(/[^a-z0-9]+/g, '-')}}.png`;
      link.click();
    }}

    function wrapCanvasText(ctx, text, x, y, maxWidth, lineHeight) {{
      const words = text.split(' ');
      let line = '';
      words.forEach(word => {{
        const testLine = line + word + ' ';
        if (ctx.measureText(testLine).width > maxWidth && line) {{
          ctx.fillText(line, x, y);
          line = word + ' ';
          y += lineHeight;
        }} else {{
          line = testLine;
        }}
      }});
      ctx.fillText(line, x, y);
    }}

    function render() {{
      const rows = filteredData();
      const expenseYoy = sum(rows, 'diferenca_yoy');
      const costTotal = sum(rows, 'custo_total_estimado');
      const presenceDiff = avg(rows, 'indice_presenca_relativa') - nationalPresenceAvg;
      const absenceDiff = avg(rows, 'pct_ausencia_nao_justificada') - nationalUnjustifiedAbsenceAvg;
      const pecAvg = rows.length ? sum(rows, 'qtd_votacoes_pec') / rows.length : 0;
      updateActiveFilters();
      if (isSingleDeputyView(rows)) {{
        renderSingleDeputyKpis(rows[0]);
      }} else {{
        renderAggregateKpis(rows, expenseYoy, costTotal, presenceDiff, absenceDiff, pecAvg);
      }}
      renderPartyMetricBars(rows);
      renderBars('stateBars', groupedSum(rows, 'siglaUf', 'custo_total_estimado'), '', value => formatCompactMoney(value));
      renderBars('partyPresenceBars', groupedAvg(rows, 'siglaPartido', 'indice_presenca_relativa'), 'presence', value => formatPct.format(value) + '%');
      renderBars('statePresenceBars', groupedAvg(rows, 'siglaUf', 'indice_presenca_relativa'), 'presence', value => formatPct.format(value) + '%');
      renderBars('partyAbsenceBars', groupedAvg(rows, 'siglaPartido', 'pct_ausencia_nao_justificada'), 'presence', value => formatPct.format(value) + '%');
      renderBars('partyPecBars', groupedSum(rows, 'siglaPartido', 'qtd_votacoes_pec'), 'party', value => formatNumber.format(value));
      renderBars(
        'partyAverageBars',
        buildPartyRows(rows)
          .sort((a, b) => b.gasto_medio_por_candidato - a.gasto_medio_por_candidato)
          .slice(0, 12)
          .map(row => [row.siglaPartido, row.gasto_medio_por_candidato]),
        'party',
        value => formatCompactMoney(value)
      );
      renderStackedPartyCosts(rows);
      renderPartyShareCompare(rows);
      renderQuickInsights(rows);
      renderDeputyProfile(rows);
      renderRankings(rows);
      renderMatrix(rows);
      renderCreator(rows);
      renderTable(rows);
      renderPecVotes(filteredPecVotes());
      normalizeVisibleText();
      return;
      document.getElementById('kpiDeputies').textContent = formatNumber.format(rows.length);
      document.getElementById('kpiExpenses').textContent = formatCompactMoney(sum(rows, 'valor_liquido_total'));
      document.getElementById('kpiSalary').textContent = formatCompactMoney(sum(rows, 'valor_subsidio_bruto_total'));
      document.getElementById('kpiCost').textContent = formatCompactMoney(sum(rows, 'custo_total_estimado'));
      document.getElementById('kpiPresencePct').textContent = formatPct.format(avg(rows, 'indice_presenca_relativa')) + '%';
      document.getElementById('kpiUnjustifiedAbsence').textContent = formatPct.format(avg(rows, 'pct_ausencia_nao_justificada')) + '%';
      document.getElementById('kpiPecVotes').textContent = formatNumber.format(sum(rows, 'qtd_votacoes_pec'));
      setYoySubtext('kpiExpensesYoy', expenseYoy, 'Dif. YoY');
      setNeutralSubtext('kpiSalaryContext', 'Subsídio estimado, sem série YoY');
      setYoySubtext('kpiCostYoy', expenseYoy, costTotal ? `Impacto YoY no custo (${{formatPct.format(expenseYoy / costTotal * 100)}}%)` : 'Impacto YoY no custo');
      setPointDiffSubtext('kpiPresenceContext', presenceDiff);
      setPointDiffSubtext('kpiAbsenceContext', absenceDiff, true);
      setNeutralSubtext('kpiPecContext', `Média por deputado: ${{formatPct.format(pecAvg)}}`);
      renderPartyMetricBars(rows);
      renderBars('stateBars', groupedSum(rows, 'siglaUf', 'custo_total_estimado'), '', value => formatCompactMoney(value));
      renderBars('partyPresenceBars', groupedAvg(rows, 'siglaPartido', 'indice_presenca_relativa'), 'presence', value => formatPct.format(value) + '%');
      renderBars('statePresenceBars', groupedAvg(rows, 'siglaUf', 'indice_presenca_relativa'), 'presence', value => formatPct.format(value) + '%');
      renderBars('partyAbsenceBars', groupedAvg(rows, 'siglaPartido', 'pct_ausencia_nao_justificada'), 'presence', value => formatPct.format(value) + '%');
      renderBars('partyPecBars', groupedSum(rows, 'siglaPartido', 'qtd_votacoes_pec'), 'party', value => formatNumber.format(value));
      renderBars(
        'partyAverageBars',
        buildPartyRows(rows)
          .sort((a, b) => b.gasto_medio_por_candidato - a.gasto_medio_por_candidato)
          .slice(0, 12)
          .map(row => [row.siglaPartido, row.gasto_medio_por_candidato]),
        'party',
        value => formatCompactMoney(value)
      );
      renderStackedPartyCosts(rows);
      renderPartyShareCompare(rows);
      renderQuickInsights(rows);
      renderDeputyProfile(rows);
      renderRankings(rows);
      renderMatrix(rows);
      renderCreator(rows);
      renderTable(rows);
      renderPecVotes(filteredPecVotes());
    }}

    function uniqueSorted(rows, field) {{
      return [...new Set(rows.map(row => row[field]).filter(Boolean))]
        .sort((a, b) => String(a).localeCompare(String(b), 'pt-BR'));
    }}

    function populateAuxiliaryFilters() {{
      setOptions(document.getElementById('senateStateFilter'), uniqueSorted(SENATE_DATA, 'siglaUf'), 'Todos');
      setOptions(document.getElementById('senatePartyFilter'), uniqueSorted(SENATE_DATA, 'siglaPartido'), 'Todos');
      setOptions(document.getElementById('rjExpensePartyFilter'), uniqueSorted(RJ_EXPENSE_DATA, 'siglaPartido'), 'Todos');
      setOptions(document.getElementById('rjPartyFilter'), uniqueSorted(RJ_ELECTED_DATA, 'siglaPartido'), 'Todos');
      setOptions(document.getElementById('rjGenderFilter'), uniqueSorted(RJ_ELECTED_DATA, 'genero'), 'Todos');
    }}

    function addScopeNavLinks() {{
      const nav = document.querySelector('.section-tabs');
      if (!nav) return;
      nav.innerHTML = '';
      sectionLinks.forEach(([href, label]) => {{
        const link = document.createElement('a');
        link.href = href;
        link.textContent = label;
        link.addEventListener('click', event => {{
          event.preventDefault();
          navigateToSection(href);
        }});
        nav.appendChild(link);
      }});
      const sectionSelect = document.getElementById('sectionSelect');
      sectionSelect.innerHTML = sectionLinks.map(([href, label]) => `<option value="${{href}}">${{label}}</option>`).join('');
      sectionSelect.addEventListener('change', event => navigateToSection(event.target.value));
    }}

    function collapseFiltersForAnchor() {{
      const controls = document.getElementById('visao-geral');
      controls.classList.add('is-filters-collapsed');
      document.getElementById('toggleFilters').textContent = 'Filtros';
      updateStickyOffset();
    }}

    function navigateToSection(hash, replace = false) {{
      const target = document.querySelector(hash);
      if (!target) return;
      collapseFiltersForAnchor();
      window.requestAnimationFrame(() => {{
        target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
        if (replace) window.history.replaceState(null, '', hash);
        else window.history.pushState(null, '', hash);
        updateActiveSection(hash);
      }});
    }}

    function scrollToInitialHash() {{
      if (!window.location.hash) return;
      collapseFiltersForAnchor();
      window.requestAnimationFrame(() => {{
        window.requestAnimationFrame(() => navigateToSection(window.location.hash, true));
      }});
    }}

    function updateActiveSection(hash = window.location.hash || '#visao-geral') {{
      document.querySelectorAll('.section-tabs a').forEach(link => {{
        link.classList.toggle('is-active', link.getAttribute('href') === hash);
      }});
      const sectionSelect = document.getElementById('sectionSelect');
      if (sectionSelect && sectionLinks.some(([href]) => href === hash)) sectionSelect.value = hash;
    }}

    function updateStickyOffset() {{
      const controls = document.getElementById('visao-geral');
      const height = Math.ceil(controls.getBoundingClientRect().height || 0);
      document.documentElement.style.setProperty('--sticky-offset', `${{height + 14}}px`);
    }}

    function sortByField(rows, field, descending = true) {{
      return [...rows].sort((a, b) => {{
        const left = Number(a[field]);
        const right = Number(b[field]);
        if (!Number.isNaN(left) && !Number.isNaN(right)) return descending ? right - left : left - right;
        return String(a[field] || '').localeCompare(String(b[field] || ''), 'pt-BR') * (descending ? -1 : 1);
      }});
    }}

    function renderSenateSection() {{
      const state = document.getElementById('senateStateFilter').value;
      const party = document.getElementById('senatePartyFilter').value;
      const name = document.getElementById('senateNameFilter').value.trim().toLowerCase();
      const sortField = document.getElementById('senateSortFilter').value;
      const rows = sortByField(SENATE_DATA.filter(row =>
        (!state || row.siglaUf === state) &&
        (!party || row.siglaPartido === party) &&
        (!name || String(row.nome || '').toLowerCase().includes(name))
      ), sortField, sortField !== 'nome');
      document.getElementById('senateTableStatus').textContent = `Mostrando ${{formatNumber.format(rows.length)}} senadores`;
      document.getElementById('senateKpiSenators').textContent = formatNumber.format(rows.length);
      document.getElementById('senateKpiCeaps').textContent = formatCompactMoney(sum(rows, 'valor_reembolsado_total'));
      document.getElementById('senateKpiVotes').textContent = formatNumber.format(sum(rows, 'qtd_votos'));
      document.getElementById('senateKpiAvgCeaps').textContent = formatCompactMoney(avg(rows, 'valor_reembolsado_total'));
      document.getElementById('senateCards').innerHTML = rows.slice(0, 30).map(row => `
        <article class="mobile-data-card">
          <div class="mobile-card-title"><span>${{escapeHtml(row.nome)}}</span><span>${{escapeHtml(row.siglaPartido)}}/${{escapeHtml(row.siglaUf)}}</span></div>
          <div class="mobile-card-grid">
            <span>Gasto parlamentar<b>${{formatCompactMoney(row.valor_reembolsado_total)}}</b></span>
            <span>Lancamentos<b>${{formatNumber.format(Number(row.qtd_lancamentos || 0))}}</b></span>
            <span>Votacoes<b>${{formatNumber.format(Number(row.qtd_votacoes || 0))}}</b></span>
            <span>Votos nominais<b>${{formatNumber.format(Number(row.qtd_votos || 0))}}</b></span>
          </div>
        </article>
      `).join('');
      normalizeVisibleText(document.getElementById('senado'));
    }}

    function renderRjSection() {{
      const party = document.getElementById('rjPartyFilter').value;
      const gender = document.getElementById('rjGenderFilter').value;
      const name = document.getElementById('rjNameFilter').value.trim().toLowerCase();
      const sortField = document.getElementById('rjSortFilter').value;
      const rows = sortByField(RJ_ELECTED_DATA.filter(row =>
        (!party || row.siglaPartido === party) &&
        (!gender || row.genero === gender) &&
        (!name || String(row.nomeUrna || row.nomeCompleto || '').toLowerCase().includes(name))
      ), sortField, sortField !== 'nomeUrna');
      document.getElementById('rjTableStatus').textContent = `Mostrando ${{formatNumber.format(rows.length)}} eleitos`;
      document.getElementById('rjKpiElected').textContent = formatNumber.format(rows.length);
      document.getElementById('rjKpiVotes').textContent = formatNumber.format(sum(rows, 'votos_nominais'));
      document.getElementById('rjKpiTopVotes').textContent = formatNumber.format(Math.max(...rows.map(row => Number(row.votos_nominais || 0)), 0));
      document.getElementById('rjKpiParties').textContent = formatNumber.format(uniqueSorted(rows, 'siglaPartido').length);
      document.getElementById('rjCards').innerHTML = rows.slice(0, 30).map(row => `
        <article class="mobile-data-card">
          <div class="mobile-card-title"><span>${{escapeHtml(row.nomeUrna)}}</span><span>${{escapeHtml(row.siglaPartido)}}/${{escapeHtml(row.numeroCandidato)}}</span></div>
          <div class="mobile-card-grid">
            <span>Votos<b>${{formatNumber.format(Number(row.votos_nominais || 0))}}</b></span>
            <span>Municipios<b>${{formatNumber.format(Number(row.municipios_com_voto || 0))}}</b></span>
            <span>Genero<b>${{escapeHtml(row.genero)}}</b></span>
            <span>Cor/raca<b>${{escapeHtml(row.corRaca)}}</b></span>
          </div>
        </article>
      `).join('');
      normalizeVisibleText(document.getElementById('rj-eleitoral'));
    }}

    function renderRjExpenseSection() {{
      const party = document.getElementById('rjExpensePartyFilter').value;
      const name = document.getElementById('rjExpenseNameFilter').value.trim().toLowerCase();
      const sortField = document.getElementById('rjExpenseSortFilter').value;
      const rows = sortByField(RJ_EXPENSE_DATA.filter(row =>
        (!party || row.siglaPartido === party) &&
        (!name || String(row.nomeParlamentar || row.nome || '').toLowerCase().includes(name))
      ), sortField, sortField !== 'nome');
      const categoryRows = sortByField(RJ_EXPENSE_CATEGORY_DATA, 'valorGastoParlamentar');
      document.getElementById('rjExpenseTableStatus').textContent = `Mostrando ${{formatNumber.format(rows.length)}} deputados`;
      document.getElementById('rjExpenseKpiDeputies').textContent = formatNumber.format(rows.length);
      document.getElementById('rjExpenseKpiSpending').textContent = formatCompactMoney(sum(rows, 'valorGastoParlamentar'));
      document.getElementById('rjExpenseKpiEntries').textContent = formatNumber.format(sum(rows, 'qtdLancamentos'));
      document.getElementById('rjExpenseKpiAvg').textContent = formatCompactMoney(avg(rows, 'valorGastoParlamentar'));
      document.getElementById('rjExpenseCards').innerHTML = rows.slice(0, 30).map(row => `
        <article class="mobile-data-card">
          <div class="mobile-card-title"><span>${{escapeHtml(row.nomeParlamentar || row.nome)}}</span><span>${{escapeHtml(row.siglaPartido)}}</span></div>
          <div class="mobile-card-grid">
            <span>Gasto parlamentar<b>${{formatCompactMoney(row.valorGastoParlamentar)}}</b></span>
            <span>Lancamentos<b>${{formatNumber.format(Number(row.qtdLancamentos || 0))}}</b></span>
            <span>Fornecedores<b>${{formatNumber.format(Number(row.qtdFornecedores || 0))}}</b></span>
            <span>Uso do limite<b>${{formatPct.format(Number(row.usoLimitePct || 0))}}%</b></span>
          </div>
        </article>
      `).join('');
      document.getElementById('rjExpenseCategoryCards').innerHTML = categoryRows.slice(0, 12).map(row => `
        <article class="mobile-data-card">
          <div class="mobile-card-title"><span>${{escapeHtml(row.codigoCentroCusto || 'Categoria')}}</span><span>${{formatPct.format(Number(row.shareGastoPct || 0))}}%</span></div>
          <div class="mobile-card-meta">${{escapeHtml(row.centroCusto || '')}}</div>
          <div class="mobile-card-grid">
            <span>Gasto parlamentar<b>${{formatCompactMoney(row.valorGastoParlamentar)}}</b></span>
            <span>Lancamentos<b>${{formatNumber.format(Number(row.qtdLancamentos || 0))}}</b></span>
          </div>
        </article>
      `).join('');
      normalizeVisibleText(document.getElementById('rj-estadual'));
    }}

    function renderAlerjSection() {{
      const term = document.getElementById('alerjSourceFilter').value.trim().toLowerCase();
      document.getElementById('alerjKpiDeputies').textContent = formatNumber.format(ALERJ_DEPUTY_DATA.length);
      document.getElementById('alerjKpiSources').textContent = formatNumber.format(ALERJ_SOURCE_DATA.length);
      document.getElementById('alerjKpiPdfs').textContent = formatNumber.format(ALERJ_PDF_DATA.length);
      document.getElementById('alerjDeputyCards').innerHTML = ALERJ_DEPUTY_DATA.slice(0, 20).map(row => `
        <article class="mobile-data-card">
          <div class="mobile-card-title"><span>${{escapeHtml(row.nome)}}</span><span>${{escapeHtml(row.siglaPartido)}}</span></div>
          <div class="mobile-card-meta"><a href="${{escapeHtml(row.perfilUrl)}}" target="_blank" rel="noopener">Perfil ALERJ</a></div>
        </article>
      `).join('');
      const sources = ALERJ_SOURCE_DATA.filter(row => {{
        const text = [row.tipo, row.formato, row.titulo, row.observacao, row.url].join(' ').toLowerCase();
        return !term || text.includes(term);
      }});
      document.getElementById('alerjSourceCards').innerHTML = sources.slice(0, 25).map(row => `
        <article class="mobile-data-card">
          <div class="mobile-card-title"><span>${{escapeHtml(row.tipo || 'Fonte')}}</span><span>${{escapeHtml(row.formato)}}</span></div>
          <div class="mobile-card-meta"><a href="${{escapeHtml(row.url)}}" target="_blank" rel="noopener">${{escapeHtml(row.titulo || row.url)}}</a></div>
          <div class="pec-desc">${{escapeHtml(row.observacao)}}</div>
        </article>
      `).join('');
      normalizeVisibleText(document.getElementById('fontes-alerj'));
    }}

    setOptions(stateFilter, STATES, 'Todos');
    setOptions(partyFilter, PARTIES, 'Todos');
    setOptions(pecSelect, PEC_OPTIONS, 'Todas');
    addScopeNavLinks();
    populateAuxiliaryFilters();
    populateMainSearchList();
    applyUrlFilters();
    renderStaticBars('categoryShareBars', CATEGORY_DATA, 'categoria_tratada', 'share_gasto_pct', '', value => formatPct.format(value) + '%');
    renderSenateSection();
    renderRjExpenseSection();
    renderRjSection();
    renderAlerjSection();
    document.getElementById('toggleFilters').addEventListener('click', () => {{
      const controls = document.getElementById('visao-geral');
      controls.classList.toggle('is-filters-collapsed');
      document.getElementById('toggleFilters').textContent = controls.classList.contains('is-filters-collapsed')
        ? 'Filtros'
        : 'Ocultar filtros';
      updateStickyOffset();
    }});
    document.getElementById('clearAllFilters').addEventListener('click', () => {{
      stateFilter.value = '';
      partyFilter.value = '';
      nameFilter.value = '';
      mainSearch.value = '';
      pecFilter.value = '';
      pecSelect.value = '';
      selectedDeputy = null;
      document.getElementById('visao-geral').classList.add('is-filters-collapsed');
      document.getElementById('toggleFilters').textContent = 'Filtros';
      scheduleRender({{ reset: true }});
    }});
    document.querySelectorAll('[data-toggle-section]').forEach(button => {{
      button.addEventListener('click', event => {{
        const target = document.getElementById(event.currentTarget.dataset.toggleSection);
        target.classList.toggle('is-expanded');
        event.currentTarget.textContent = target.classList.contains('is-expanded')
          ? 'Mostrar menos'
          : 'Mostrar todos os gráficos';
      }});
    }});
    document.querySelectorAll('[data-toggle-detail]').forEach(button => {{
      button.addEventListener('click', event => {{
        const target = document.getElementById(event.currentTarget.dataset.toggleDetail);
        target.classList.toggle('is-collapsed');
        event.currentTarget.textContent = target.classList.contains('is-collapsed')
          ? event.currentTarget.textContent.replace('Recolher', 'Expandir')
          : event.currentTarget.textContent.replace('Expandir', 'Recolher');
      }});
    }});
    [stateFilter, partyFilter, nameFilter, pecFilter, pecSelect, partyMetricFilter].forEach(element => {{
      element.addEventListener('input', () => scheduleRender({{ reset: true }}));
    }});
    [
      'senateStateFilter',
      'senatePartyFilter',
      'senateNameFilter',
      'senateSortFilter'
    ].forEach(id => document.getElementById(id).addEventListener('input', renderSenateSection));
    [
      'rjExpensePartyFilter',
      'rjExpenseNameFilter',
      'rjExpenseSortFilter'
    ].forEach(id => document.getElementById(id).addEventListener('input', renderRjExpenseSection));
    [
      'rjPartyFilter',
      'rjGenderFilter',
      'rjNameFilter',
      'rjSortFilter'
    ].forEach(id => document.getElementById(id).addEventListener('input', renderRjSection));
    document.getElementById('alerjSourceFilter').addEventListener('input', renderAlerjSection);
    mainSearch.addEventListener('input', () => {{
      applyMainSearch(mainSearch.value);
      scheduleRender({{ reset: true }});
    }});
    nameFilter.addEventListener('input', () => {{
      mainSearch.value = nameFilter.value;
      selectedDeputy = null;
    }});
    sortFilter.addEventListener('input', () => {{
      candidateSort = {{ field: sortFilter.value, direction: 'desc' }};
      scheduleRender({{ reset: true }});
    }});
    document.getElementById('activeFilters').addEventListener('click', event => {{
      const type = event.target.dataset.clearFilter;
      if (!type) return;
      if (type === 'uf') stateFilter.value = '';
      if (type === 'partido') partyFilter.value = '';
      if (type === 'deputado') {{
        nameFilter.value = '';
        mainSearch.value = '';
        selectedDeputy = null;
      }}
      if (type === 'pec') pecSelect.value = '';
      scheduleRender({{ reset: true }});
    }});
    document.getElementById('attentionMatrix').addEventListener('click', event => {{
      const id = event.target.dataset.deputyId;
      if (!id) return;
      selectedDeputy = DATA.find(row => String(row.idDeputado) === String(id)) || null;
      if (selectedDeputy) {{
        nameFilter.value = selectedDeputy.nome;
        mainSearch.value = `${{selectedDeputy.nome}} (${{selectedDeputy.siglaPartido}}-${{selectedDeputy.siglaUf}})`;
        document.getElementById('ficha-deputado').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
      scheduleRender({{ reset: true }});
    }});
    document.querySelectorAll('th[data-sort]').forEach(header => {{
      header.addEventListener('click', () => {{
        const state = header.dataset.table === 'pec' ? pecSort : candidateSort;
        const nextDirection = state.field === header.dataset.sort && state.direction === 'desc' ? 'asc' : 'desc';
        if (header.dataset.table === 'pec') {{
          pecSort = {{ field: header.dataset.sort, direction: nextDirection }};
          pecPage = 1;
        }} else {{
          candidateSort = {{ field: header.dataset.sort, direction: nextDirection }};
          if (Array.from(sortFilter.options).some(option => option.value === header.dataset.sort)) {{
            sortFilter.value = header.dataset.sort;
          }}
          candidatePage = 1;
        }}
        scheduleRender({{ reset: false, syncUrl: false }});
      }});
    }});
    document.getElementById('candidatePrevPage').addEventListener('click', () => {{
      candidatePage = Math.max(candidatePage - 1, 1);
      scheduleRender({{ reset: false, syncUrl: false }});
    }});
    document.getElementById('candidateNextPage').addEventListener('click', () => {{
      candidatePage += 1;
      scheduleRender({{ reset: false, syncUrl: false }});
    }});
    document.getElementById('pecPrevPage').addEventListener('click', () => {{
      pecPage = Math.max(pecPage - 1, 1);
      scheduleRender({{ reset: false, syncUrl: false }});
    }});
    document.getElementById('pecNextPage').addEventListener('click', () => {{
      pecPage += 1;
      scheduleRender({{ reset: false, syncUrl: false }});
    }});
    document.getElementById('exportCandidateCsv').addEventListener('click', () => {{
      downloadCsv('camara_deputados_filtrados.csv', lastCandidateRows, [
        {{ field: 'nome', label: 'Deputado' }},
        {{ field: 'siglaPartido', label: 'Partido' }},
        {{ field: 'siglaUf', label: 'UF' }},
        {{ field: 'valor_liquido_total', label: 'Gasto parlamentar' }},
        {{ field: 'valor_subsidio_bruto_total', label: 'Remuneracao' }},
        {{ field: 'custo_total_estimado', label: 'Custo total' }},
        {{ field: 'indice_presenca_relativa', label: 'Presenca relativa pct' }},
        {{ field: 'pct_ausencia_nao_justificada', label: 'Ausencia nao justificada pct' }},
        {{ field: 'qtd_votacoes_pec', label: 'Votacoes PEC' }},
        {{ field: 'diferenca_yoy', label: 'Diferenca YoY' }}
      ]);
    }});
    document.getElementById('exportPecCsv').addEventListener('click', () => {{
      downloadCsv('camara_votos_pec_filtrados.csv', lastPecRows, [
        {{ field: 'data_ultima', label: 'Ultima votacao' }},
        {{ field: 'nome', label: 'Deputado' }},
        {{ field: 'siglaPartido', label: 'Partido' }},
        {{ field: 'siglaUf', label: 'UF' }},
        {{ field: 'proposicao_titulo', label: 'PEC' }},
        {{ field: 'ementa_curta', label: 'Ementa' }},
        {{ field: 'voto_predominante', label: 'Voto predominante' }},
        {{ field: 'votos_sim', label: 'Sim' }},
        {{ field: 'votos_nao', label: 'Nao' }},
        {{ field: 'votos_obstrucao', label: 'Obstrucao' }},
        {{ field: 'votos_outros', label: 'Outros' }},
        {{ field: 'siglaOrgao', label: 'Orgao' }}
      ]);
    }});
    document.getElementById('copyVideoScript').addEventListener('click', () => copyText(document.getElementById('videoScript').value));
    document.getElementById('copySource').addEventListener('click', () => copyText(sourceText));
    document.getElementById('exportStoryCard').addEventListener('click', exportStoryCard);
    render();
    updateSortHeaders();
    updateStickyOffset();
    updateActiveSection();
    scrollToInitialHash();
    window.addEventListener('resize', updateStickyOffset);
    window.addEventListener('hashchange', () => {{
      updateActiveSection();
      scrollToInitialHash();
    }});
  </script>
</body>
</html>
"""


def save_report(html: str) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORTS_DIR / "camara_dashboard.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    report_df = build_report_dataset()
    output_path = save_report(render_html(report_df))
    print(f"Registros no relatorio: {len(report_df)}")
    print(f"Relatorio gerado: {output_path}")


if __name__ == "__main__":
    main()
