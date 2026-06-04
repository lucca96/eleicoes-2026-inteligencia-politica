from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from project_paths import RAW_CAMARA_DIR, REPORTS_DIR


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

    def compact_money(value: float) -> str:
        abs_value = abs(value)
        if abs_value >= 1_000_000_000:
            return f"R$ {round(value / 1_000_000_000):,.0f} bi".replace(",", ".")
        if abs_value >= 1_000_000:
            return f"R$ {round(value / 1_000_000):,.0f} mi".replace(",", ".")
        if abs_value >= 1_000:
            return f"R$ {round(value / 1_000):,.0f} mil".replace(",", ".")
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
    }

    data_json = json.dumps(records, ensure_ascii=False)
    categories_json = json.dumps(category_records, ensure_ascii=False)
    party_json = json.dumps(party_records, ensure_ascii=False)
    pec_vote_json = json.dumps(pec_vote_records, ensure_ascii=False)
    pec_options_json = json.dumps(pec_options, ensure_ascii=False)
    states_json = json.dumps(states, ensure_ascii=False)
    parties_json = json.dumps(parties, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Relatorio Politico Interativo</title>
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
      overflow-x: hidden;
      scroll-behavior: smooth;
      -webkit-text-size-adjust: 100%;
    }}
    body {{
      width: 100%;
      min-width: 0;
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Rawline, Raleway, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow-x: hidden;
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
      max-width: 860px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.5;
    }}
    .section-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 18px;
    }}
    .section-tabs a {{
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
    .sticky-controls {{
      position: sticky;
      top: 0;
      z-index: 20;
      background: rgba(247, 249, 251, 0.96);
      backdrop-filter: blur(10px);
      border-bottom: 1px solid var(--line);
      padding: 10px 0 12px;
    }}
    .sticky-controls .section-tabs {{
      margin-top: 0;
      margin-bottom: 10px;
    }}
    main {{
      width: 100%;
      max-width: 1380px;
      margin: 0 auto;
      padding: 18px 28px 34px;
      display: grid;
      gap: 18px;
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
      grid-template-columns: repeat(4, minmax(170px, 1fr));
      gap: 12px;
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
      font-size: 30px;
      font-weight: 780;
      white-space: nowrap;
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
    .mobile-data-card {{
      display: grid;
      gap: 8px;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      box-shadow: var(--shadow);
      padding: 13px;
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
      .kpis, .insight-row, .grid {{ grid-template-columns: 1fr 1fr; }}
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
      h1 {{ font-size: 24px; }}
      .subtitle {{ font-size: 14px; }}
      .section-tabs {{
        flex-wrap: nowrap;
        overflow-x: auto;
        padding-bottom: 4px;
      }}
      .section-tabs a {{ flex: 0 0 auto; }}
      .sticky-controls {{
        top: 0;
        padding: 8px 0 10px;
      }}
      .sticky-controls .section-tabs {{ margin-bottom: 8px; }}
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
      }}
      .filters, .grid {{ grid-template-columns: 1fr; }}
      .kpis {{
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }}
      .kpis .card {{
        min-height: 78px;
        padding: 12px;
      }}
      .kpis .card:nth-child(n+5) {{ display: none; }}
      body.show-all-kpis .kpis .card {{ display: block; }}
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
      }}
      .metric-value {{ font-size: 21px; white-space: normal; }}
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
      footer {{ padding-left: 14px; padding-right: 14px; }}
      th, td {{ padding: 9px; }}
    }}
  </style>
</head>
<body>
  <div class="govbar">
    <span>Dados públicos legislativos</span>
    <span>Câmara dos Deputados | Mandato atual</span>
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
      <h1>Relatório Interativo da Câmara</h1>
      <div class="subtitle">Gastos do mandato, remuneração acumulada, presença em eventos e plenário, ausências, votos em PECs e comparativos YoY.</div>
    </div>
  </header>
  <main>
    <section class="section-block sticky-controls" id="visao-geral">
      <nav class="section-tabs" aria-label="Seções do relatório">
        <a href="#visao-geral">Visão geral</a>
        <a href="#gastos">Gastos</a>
        <a href="#presenca">Presença</a>
        <a href="#pecs">PECs</a>
        <a href="#detalhes">Detalhes</a>
      </nav>
      <div class="filters">
        <label>Estado<select id="stateFilter"></select></label>
        <label>Partido<select id="partyFilter"></select></label>
        <label>Deputado<input id="nameFilter" type="search" placeholder="Filtrar por nome"></label>
        <label>Ordenar<select id="sortFilter">
          <option value="custo_total_estimado">Custo total</option>
          <option value="valor_liquido_total">Gasto do mandato</option>
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

    <section class="kpis" aria-label="Indicadores principais">
      <div class="card accent-blue"><div class="metric-label">Deputados</div><div class="metric-value" id="kpiDeputies">{initial_kpis["deputies"]}</div></div>
      <div class="card accent-green"><div class="metric-label">Gasto mandato</div><div class="metric-value" id="kpiExpenses">{initial_kpis["expenses"]}</div></div>
      <div class="card accent-yellow"><div class="metric-label">Remuneração</div><div class="metric-value" id="kpiSalary">{initial_kpis["salary"]}</div></div>
      <div class="card accent-blue"><div class="metric-label">Custo total <i class="info-tip" tabindex="0" data-tip="Custo total = cota parlamentar acumulada no mandato + remuneração bruta estimada no mandato.">i</i></div><div class="metric-value" id="kpiCost">{initial_kpis["cost"]}</div></div>
      <div class="card accent-green"><div class="metric-label">% presença relativa <i class="info-tip" tabindex="0" data-tip="Média do índice de presença relativa dos deputados filtrados, calculada a partir dos registros de presença disponíveis.">i</i></div><div class="metric-value" id="kpiPresencePct">{initial_kpis["presence"]}</div></div>
      <div class="card accent-yellow"><div class="metric-label">Dif. YoY <i class="info-tip" tabindex="0" data-tip="Diferença YoY = gasto no ano atual até o período disponível menos o mesmo período do ano anterior.">i</i></div><div class="metric-value" id="kpiYoy">{initial_kpis["yoy"]}</div></div>
      <div class="card accent-blue"><div class="metric-label">% ausência não just. <i class="info-tip" tabindex="0" data-tip="Média percentual das ausências não justificadas em sessões de plenário para os deputados filtrados.">i</i></div><div class="metric-value" id="kpiUnjustifiedAbsence">{initial_kpis["unjustified_absence"]}</div></div>
      <div class="card accent-green"><div class="metric-label">Votações PEC <i class="info-tip" tabindex="0" data-tip="Total de registros nominais de votação em proposições classificadas como PEC no mandato.">i</i></div><div class="metric-value" id="kpiPecVotes">{initial_kpis["pec_votes"]}</div></div>
    </section>
    <button class="mobile-toggle" type="button" data-toggle-kpis>Mostrar todos os indicadores</button>

    <section class="section-block" id="gastos">
      <div class="block-heading">
        <h2>Gastos</h2>
        <span>Cota parlamentar, categorias e média por partido</span>
      </div>
      <button class="mobile-toggle" type="button" data-toggle-section="gastosGrid">Mostrar todos os gráficos de gastos</button>
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
        <h2 class="section-title">Share dos gastos por categoria</h2>
        <div id="categoryShareBars"></div>
      </div>
      <div class="card">
        <h2 class="section-title">Gasto médio por candidato do partido</h2>
        <div id="partyAverageBars"></div>
      </div>
      <div class="card">
        <h2 class="section-title">Custo: cota parlamentar x remuneração</h2>
        <div class="legend"><span><i style="background: var(--gov-green)"></i>Cota</span><span><i style="background: var(--gov-blue)"></i>Remuneração</span></div>
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
            <th class="num" data-sort="valor_liquido_total" data-table="candidate">Gasto</th>
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
  </main>
  <footer>
    Dados atualizados em: <strong>{data_updated_label}</strong> · Fonte:
    <a href="https://dadosabertos.camara.leg.br" target="_blank" rel="noopener">Dados Abertos da Câmara</a>
  </footer>
  <script>
    const DATA = {data_json};
    const CATEGORY_DATA = {categories_json};
    const PARTY_DATA = {party_json};
    const PEC_VOTE_DATA = {pec_vote_json};
    const PEC_OPTIONS = {pec_options_json};
    const STATES = {states_json};
    const PARTIES = {parties_json};

    const formatMoney = new Intl.NumberFormat('pt-BR', {{ style: 'currency', currency: 'BRL' }});
    const formatNumber = new Intl.NumberFormat('pt-BR');
    const formatPct = new Intl.NumberFormat('pt-BR', {{ maximumFractionDigits: 1 }});

    const stateFilter = document.getElementById('stateFilter');
    const partyFilter = document.getElementById('partyFilter');
    const nameFilter = document.getElementById('nameFilter');
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

    function setOptions(select, values, allLabel) {{
      select.innerHTML = '<option value="">' + allLabel + '</option>' +
        values.map(value => '<option value="' + value + '">' + value + '</option>').join('');
    }}

    function formatCompactMoney(value) {{
      const number = Number(value || 0);
      const abs = Math.abs(number);
      if (abs >= 1_000_000_000) return 'R$ ' + formatNumber.format(Math.round(number / 1_000_000_000)) + ' bi';
      if (abs >= 1_000_000) return 'R$ ' + formatNumber.format(Math.round(number / 1_000_000)) + ' mi';
      if (abs >= 1_000) return 'R$ ' + formatNumber.format(Math.round(number / 1_000)) + ' mil';
      return formatMoney.format(number);
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
      if (['custo_total', 'custo_por_deputado', 'gasto_medio_por_candidato'].includes(metric)) return formatCompactMoney;
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

    function classForDelta(value) {{
      return Number(value || 0) > 0 ? 'positive' : 'negative';
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
            <span>Gasto<b>${{formatCompactMoney(Number(row.valor_liquido_total || 0))}}</b></span>
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
      pecSelect.value = params.get('pec') || '';
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

    function render() {{
      const rows = filteredData();
      updateActiveFilters();
      document.getElementById('kpiDeputies').textContent = formatNumber.format(rows.length);
      document.getElementById('kpiExpenses').textContent = formatCompactMoney(sum(rows, 'valor_liquido_total'));
      document.getElementById('kpiSalary').textContent = formatCompactMoney(sum(rows, 'valor_subsidio_bruto_total'));
      document.getElementById('kpiCost').textContent = formatCompactMoney(sum(rows, 'custo_total_estimado'));
      document.getElementById('kpiPresencePct').textContent = formatPct.format(avg(rows, 'indice_presenca_relativa')) + '%';
      document.getElementById('kpiYoy').textContent = formatCompactMoney(sum(rows, 'diferenca_yoy'));
      document.getElementById('kpiUnjustifiedAbsence').textContent = formatPct.format(avg(rows, 'pct_ausencia_nao_justificada')) + '%';
      document.getElementById('kpiPecVotes').textContent = formatNumber.format(sum(rows, 'qtd_votacoes_pec'));
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
      renderTable(rows);
      renderPecVotes(filteredPecVotes());
    }}

    setOptions(stateFilter, STATES, 'Todos');
    setOptions(partyFilter, PARTIES, 'Todos');
    setOptions(pecSelect, PEC_OPTIONS, 'Todas');
    applyUrlFilters();
    renderStaticBars('categoryShareBars', CATEGORY_DATA, 'categoria_tratada', 'share_gasto_pct', '', value => formatPct.format(value) + '%');
    document.querySelector('[data-toggle-kpis]').addEventListener('click', event => {{
      document.body.classList.toggle('show-all-kpis');
      event.currentTarget.textContent = document.body.classList.contains('show-all-kpis')
        ? 'Mostrar menos indicadores'
        : 'Mostrar todos os indicadores';
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
    sortFilter.addEventListener('input', () => {{
      candidateSort = {{ field: sortFilter.value, direction: 'desc' }};
      scheduleRender({{ reset: true }});
    }});
    document.getElementById('activeFilters').addEventListener('click', event => {{
      const type = event.target.dataset.clearFilter;
      if (!type) return;
      if (type === 'uf') stateFilter.value = '';
      if (type === 'partido') partyFilter.value = '';
      if (type === 'deputado') nameFilter.value = '';
      if (type === 'pec') pecSelect.value = '';
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
        {{ field: 'valor_liquido_total', label: 'Gasto mandato' }},
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
    render();
    updateSortHeaders();
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
