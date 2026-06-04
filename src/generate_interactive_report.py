from __future__ import annotations

import json
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
    return read_csv_if_exists(RAW_CAMARA_DIR / "resumo_gastos_categoria_mandato.csv")


def build_party_dataset(report_df: pd.DataFrame) -> pd.DataFrame:
    return (
        report_df.groupby("siglaPartido", as_index=False)
        .agg(
            qtd_candidatos=("idDeputado", "nunique"),
            gasto_total=("valor_liquido_total", "sum"),
            custo_total=("custo_total_estimado", "sum"),
            presenca_media=("indice_presenca_relativa", "mean"),
        )
        .assign(
            gasto_medio_por_candidato=lambda df: df["gasto_total"]
            / df["qtd_candidatos"].replace(0, 1)
        )
        .sort_values("gasto_medio_por_candidato", ascending=False)
    )


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
    pec_vote_records = build_pec_vote_detail_dataset().to_dict(orient="records")
    states = sorted(report_df["siglaUf"].dropna().unique().tolist())
    parties = sorted(report_df["siglaPartido"].dropna().unique().tolist())

    data_json = json.dumps(records, ensure_ascii=False)
    categories_json = json.dumps(category_records, ensure_ascii=False)
    party_json = json.dumps(party_records, ensure_ascii=False)
    pec_vote_json = json.dumps(pec_vote_records, ensure_ascii=False)
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
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Rawline, Raleway, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
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
    .hero {{
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
    main {{
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
    .metric-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      font-weight: 740;
    }}
    .metric-value {{
      margin-top: 10px;
      color: var(--gov-blue-dark);
      font-size: 24px;
      font-weight: 780;
      white-space: nowrap;
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
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      background: #fff;
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
    tr:nth-child(even) td {{ background: #fbfcff; }}
    td.num, th.num {{ text-align: right; }}
    .positive {{ color: var(--red); }}
    .negative {{ color: var(--gov-green); }}
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
      .gov-logo {{ width: 96px; }}
      .hero, main {{
        padding-left: 14px;
        padding-right: 14px;
      }}
      h1 {{ font-size: 24px; }}
      .subtitle {{ font-size: 14px; }}
      .filters, .kpis, .insight-row, .grid {{ grid-template-columns: 1fr; }}
      .pec-tools {{ grid-template-columns: 1fr; }}
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
        <div class="brand-meta">Portal único do Governo Federal</div>
      </div>
      <div class="eyebrow">Painel de inteligência política</div>
      <h1>Relatório Interativo da Câmara</h1>
      <div class="subtitle">Gastos do mandato, remuneração acumulada, presença em eventos e plenário, ausências, votos em PECs e comparativos YoY.</div>
      <nav class="section-tabs" aria-label="Seções do relatório">
        <a href="#visao-geral">Visão geral</a>
        <a href="#gastos">Gastos</a>
        <a href="#presenca">Presença</a>
        <a href="#pecs">PECs</a>
        <a href="#detalhes">Detalhes</a>
      </nav>
    </div>
  </header>
  <main>
    <section class="section-block" id="visao-geral">
      <div class="block-heading">
        <h2>Visão geral</h2>
        <span>Filtros e indicadores consolidados</span>
      </div>
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
      <div class="insight-row">
        <div class="insight"><strong>Mandato atual</strong><span>Dados acumulados da legislatura vigente até a data de referência.</span></div>
        <div class="insight"><strong>Presença formal</strong><span>Ausências justificadas e não justificadas vêm das sessões de plenário.</span></div>
        <div class="insight"><strong>PECs</strong><span>Votos nominais vinculados a proposições do tipo PEC.</span></div>
        <div class="insight"><strong>YoY</strong><span>Comparação do ano atual contra o mesmo período do ano anterior.</span></div>
      </div>
    </section>

    <section class="kpis" aria-label="Indicadores principais">
      <div class="card accent-blue"><div class="metric-label">Deputados</div><div class="metric-value" id="kpiDeputies">0</div></div>
      <div class="card accent-green"><div class="metric-label">Gasto mandato</div><div class="metric-value" id="kpiExpenses">R$ 0</div></div>
      <div class="card accent-yellow"><div class="metric-label">Remuneração</div><div class="metric-value" id="kpiSalary">R$ 0</div></div>
      <div class="card accent-blue"><div class="metric-label">Custo total</div><div class="metric-value" id="kpiCost">R$ 0</div></div>
      <div class="card accent-green"><div class="metric-label">% presença relativa</div><div class="metric-value" id="kpiPresencePct">0%</div></div>
      <div class="card accent-yellow"><div class="metric-label">Dif. YoY</div><div class="metric-value" id="kpiYoy">R$ 0</div></div>
      <div class="card accent-blue"><div class="metric-label">% ausência não just.</div><div class="metric-value" id="kpiUnjustifiedAbsence">0%</div></div>
      <div class="card accent-green"><div class="metric-label">Votações PEC</div><div class="metric-value" id="kpiPecVotes">0</div></div>
    </section>

    <section class="section-block" id="gastos">
      <div class="block-heading">
        <h2>Gastos</h2>
        <span>Cota parlamentar, categorias e média por partido</span>
      </div>
      <div class="grid">
      <div class="card">
        <h2 class="section-title">Custo total por partido</h2>
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
      </div>
    </section>

    <section class="section-block" id="presenca">
      <div class="block-heading">
        <h2>Presença e ausências</h2>
        <span>Eventos legislativos e sessões de plenário</span>
      </div>
      <div class="grid">
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
          <label>Buscar PEC<input id="pecFilter" type="search" placeholder="PEC, deputado, voto ou trecho da ementa"></label>
          <div class="pec-note">A tabela abaixo acompanha os filtros de estado, partido e deputado aplicados no topo.</div>
        </div>
        <div class="table-wrap">
          <table class="pec-table">
            <thead>
              <tr>
                <th>Última votação</th>
                <th>Deputado</th>
                <th>Partido</th>
                <th>UF</th>
                <th>PEC</th>
                <th>Voto predominante</th>
                <th class="num">Sim</th>
                <th class="num">Não</th>
                <th class="num">Outros</th>
                <th>Órgão</th>
              </tr>
            </thead>
            <tbody id="pecVoteBody"></tbody>
          </table>
        </div>
      </div>
      </div>
    </section>

    <section class="section-block" id="detalhes">
      <div class="block-heading">
        <h2>Detalhamento por deputado</h2>
        <span>Até 120 registros conforme os filtros atuais</span>
      </div>
      <div class="table-wrap">
        <table>
        <thead>
          <tr>
            <th>Deputado</th>
            <th>Partido</th>
            <th>UF</th>
            <th class="num">Gasto</th>
            <th class="num">Remun.</th>
            <th class="num">Custo</th>
            <th class="num">% pres. rel.</th>
            <th class="num">Aus. just.</th>
            <th class="num">Aus. nao just.</th>
            <th class="num">PECs</th>
            <th class="num">YoY</th>
            <th class="num">Dif. media candidato</th>
            <th class="num">Custo/pres.</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
      </div>
    </section>
  </main>
  <script>
    const DATA = {data_json};
    const CATEGORY_DATA = {categories_json};
    const PARTY_DATA = {party_json};
    const PEC_VOTE_DATA = {pec_vote_json};
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

    function setOptions(select, values, allLabel) {{
      select.innerHTML = '<option value="">' + allLabel + '</option>' +
        values.map(value => '<option value="' + value + '">' + value + '</option>').join('');
    }}

    function filteredData() {{
      const state = stateFilter.value;
      const party = partyFilter.value;
      const name = nameFilter.value.trim().toLowerCase();

      return DATA.filter(row =>
        (!state || row.siglaUf === state) &&
        (!party || row.siglaPartido === party) &&
        (!name || String(row.nome || '').toLowerCase().includes(name))
      ).sort((a, b) => Number(b[sortFilter.value] || 0) - Number(a[sortFilter.value] || 0));
    }}

    function filteredPecVotes() {{
      const state = stateFilter.value;
      const party = partyFilter.value;
      const name = nameFilter.value.trim().toLowerCase();
      const term = pecFilter.value.trim().toLowerCase();

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
          (!name || String(row.nome || '').toLowerCase().includes(name)) &&
          (!term || haystack.includes(term));
      }}).slice(0, 300);
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

    function classForDelta(value) {{
      return Number(value || 0) > 0 ? 'positive' : 'negative';
    }}

    function renderTable(rows) {{
      document.getElementById('tableBody').innerHTML = rows.slice(0, 120).map(row => `
        <tr>
          <td>${{row.nome || ''}}</td>
          <td>${{row.siglaPartido || ''}}</td>
          <td>${{row.siglaUf || ''}}</td>
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
    }}

    function renderPecVotes(rows) {{
      document.getElementById('pecVoteBody').innerHTML = rows.map(row => `
        <tr>
          <td>${{row.data_ultima || ''}}</td>
          <td>${{row.nome || ''}}</td>
          <td>${{row.siglaPartido || ''}}</td>
          <td>${{row.siglaUf || ''}}</td>
          <td>
            <div class="pec-title">${{row.proposicao_titulo || 'PEC'}}</div>
            <div class="pec-desc">${{row.ementa_curta || ''}}</div>
          </td>
          <td><strong>${{row.voto_predominante || ''}}</strong></td>
          <td class="num">${{formatNumber.format(Number(row.votos_sim || 0))}}</td>
          <td class="num">${{formatNumber.format(Number(row.votos_nao || 0))}}</td>
          <td class="num">${{formatNumber.format(Number(row.votos_obstrucao || 0) + Number(row.votos_outros || 0))}}</td>
          <td>${{row.siglaOrgao || ''}}</td>
        </tr>
      `).join('');
    }}

    function render() {{
      const rows = filteredData();
      document.getElementById('kpiDeputies').textContent = formatNumber.format(rows.length);
      document.getElementById('kpiExpenses').textContent = formatMoney.format(sum(rows, 'valor_liquido_total'));
      document.getElementById('kpiSalary').textContent = formatMoney.format(sum(rows, 'valor_subsidio_bruto_total'));
      document.getElementById('kpiCost').textContent = formatMoney.format(sum(rows, 'custo_total_estimado'));
      document.getElementById('kpiPresencePct').textContent = formatPct.format(avg(rows, 'indice_presenca_relativa')) + '%';
      document.getElementById('kpiYoy').textContent = formatMoney.format(sum(rows, 'diferenca_yoy'));
      document.getElementById('kpiUnjustifiedAbsence').textContent = formatPct.format(avg(rows, 'pct_ausencia_nao_justificada')) + '%';
      document.getElementById('kpiPecVotes').textContent = formatNumber.format(sum(rows, 'qtd_votacoes_pec'));
      renderBars('partyBars', groupedSum(rows, 'siglaPartido', 'custo_total_estimado'), 'party', value => formatMoney.format(value));
      renderBars('stateBars', groupedSum(rows, 'siglaUf', 'custo_total_estimado'), '', value => formatMoney.format(value));
      renderBars('partyPresenceBars', groupedAvg(rows, 'siglaPartido', 'indice_presenca_relativa'), 'presence', value => formatPct.format(value) + '%');
      renderBars('statePresenceBars', groupedAvg(rows, 'siglaUf', 'indice_presenca_relativa'), 'presence', value => formatPct.format(value) + '%');
      renderBars('partyAbsenceBars', groupedAvg(rows, 'siglaPartido', 'pct_ausencia_nao_justificada'), 'presence', value => formatPct.format(value) + '%');
      renderBars('partyPecBars', groupedSum(rows, 'siglaPartido', 'qtd_votacoes_pec'), 'party', value => formatNumber.format(value));
      renderTable(rows);
      renderPecVotes(filteredPecVotes());
    }}

    setOptions(stateFilter, STATES, 'Todos');
    setOptions(partyFilter, PARTIES, 'Todos');
    renderStaticBars('categoryShareBars', CATEGORY_DATA, 'tipoDespesa', 'share_gasto_pct', '', value => formatPct.format(value) + '%');
    renderStaticBars('partyAverageBars', PARTY_DATA, 'siglaPartido', 'gasto_medio_por_candidato', 'party', value => formatMoney.format(value));
    [stateFilter, partyFilter, nameFilter, sortFilter, pecFilter].forEach(element => element.addEventListener('input', render));
    render();
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
