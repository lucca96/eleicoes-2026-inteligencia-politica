# Inteligencia de Dados Politicos - Eleicoes 2026

Projeto para extrair, modelar, cruzar e visualizar dados publicos de deputados federais, senadores e deputados estaduais do RJ, com foco em gastos parlamentares, presenca e historico de votacoes.

## Aviso

Este projeto usa exclusivamente dados publicos oficiais e tem finalidade analitica, educacional e jornalistica. As metricas derivadas devem ser interpretadas conforme a fonte e a metodologia descritas na documentacao.

## Objetivo

Construir uma base analitica em Star Schema para apoiar dashboards em Power BI e ferramentas auxiliares em React, permitindo analises comparativas sobre atuacao parlamentar durante o ciclo eleitoral de 2026.

## Estrutura Inicial

```text
.
|-- README.md
|-- requirements.txt
|-- src/
|   |-- build_camara_remuneracao.py
|   |-- camara_client.py
|   |-- camara_legislatura.py
|   |-- extract_alerj_deputados_rj.py
|   |-- extract_camara_deputados.py
|   |-- extract_camara_mandato.py
|   |-- extract_camara_plenario_presenca.py
|   |-- extract_camara_presenca.py
|   |-- extract_camara_votos_pec.py
|   |-- extract_senado_senadores.py
|   |-- extract_tse_deputados_estaduais_rj.py
|   |-- generate_interactive_report.py
|   |-- project_paths.py
|   `-- senado_client.py
|-- reports/
|   `-- camara_dashboard.html
`-- docs/
    |-- contexto-estendido.md
    |-- memoria-projeto.md
    `-- star-schema.md
```

## Como Executar o ETL Base

1. Crie e ative um ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instale as dependencias:

```powershell
pip install -r requirements.txt
```

3. Execute a extracao da Camara:

```powershell
python .\src\extract_camara_deputados.py
python .\src\extract_camara_mandato.py
python .\src\build_camara_remuneracao.py
python .\src\extract_camara_presenca.py
python .\src\extract_camara_plenario_presenca.py
python .\src\extract_camara_votos_pec.py
python .\src\generate_interactive_report.py
```

O script gera arquivos CSV na pasta `data/raw/camara/`:

- `deputados_em_exercicio.csv`
- `despesas_deputados_mes_atual.csv`
- `resumo_despesas_deputados_mes_atual.csv`
- `despesas_deputados_mandato.csv`
- `resumo_despesas_deputados_mandato.csv`
- `despesas_yoy_deputados_mandato.csv`
- `resumo_gastos_categoria_mandato.csv`
- `remuneracao_deputados_mes_atual.csv`
- `remuneracao_deputados_mandato.csv`
- `presenca_eventos_deputados_mes_atual.csv`
- `resumo_presenca_deputados_mes_atual.csv`
- `presenca_eventos_deputados_mandato.csv`
- `resumo_presenca_deputados_mandato.csv`
- `presenca_plenario_deputados_mandato.csv`
- `resumo_presenca_plenario_deputados_mandato.csv`
- `votos_pec_deputados_mandato.csv`
- `resumo_votos_pec_deputados_mandato.csv`
- `resumo_votacoes_pec_mandato.csv`

O relatorio interativo e gerado em:

- `reports/camara_dashboard.html`

## Como Executar Senado e RJ Estadual

Senado Federal:

```powershell
python .\src\extract_senado_senadores.py
```

Para validar rapidamente apenas cadastro e CEAPS, sem baixar votacoes nominais:

```powershell
python .\src\extract_senado_senadores.py --skip-votes
```

Para testar o parser de votacoes com uma amostra:

```powershell
python .\src\extract_senado_senadores.py --max-senators 2
```

Arquivos gerados em `data/raw/senado/`:

- `senadores_em_exercicio.csv`
- `despesas_ceaps_senadores_mandato.csv`
- `resumo_despesas_ceaps_senadores_mandato.csv`
- `votos_senadores_mandato.csv`
- `resumo_votos_senadores_mandato.csv`

Deputados estaduais do RJ via TSE:

```powershell
python .\src\extract_tse_deputados_estaduais_rj.py
```

Arquivos gerados em `data/raw/tse/`:

- `deputados_estaduais_rj_candidatos_2022.csv`
- `deputados_estaduais_rj_eleitos_2022.csv`

ALERJ:

```powershell
python .\src\extract_alerj_deputados_rj.py
```

Arquivos gerados em `data/raw/alerj/`:

- `deputados_estaduais_rj_alerj_em_exercicio.csv`
- `alerj_fontes_transparencia_e_legislativo.csv`
- `alerj_anuario_atividade_legislativa_pdfs.csv`

Observacao: o TSE cobre a dimensao eleitoral dos deputados estaduais do RJ. A ALERJ cobre a lista em exercicio e cataloga fontes oficiais de transparencia, presenca e atividade legislativa; parte dos dados de presenca/votacoes estaduais e publicada em paginas legadas ou PDFs, entao o primeiro passo estadual preserva URLs oficiais rastreaveis antes da extracao semiestruturada.

Abra esse arquivo no navegador para usar filtros por estado, partido, deputado e ordenacao por custo, gasto do mandato, percentual de presenca, YoY ou custo por presenca.

## Metricas do Relatorio

- Gasto do mandato: soma de `valorLiquido` da Cota Parlamentar no periodo da legislatura atual ate a data de referencia.
- Remuneracao: estimativa acumulada do subsidio bruto parlamentar mensal no mesmo periodo.
- Custo total estimado: gasto do mandato + remuneracao acumulada.
- Percentual de presenca relativa: eventos distintos com presenca do deputado / maior volume de eventos com presenca registrado por um deputado no periodo.
- Percentual bruto de eventos: eventos distintos com presenca do deputado / total de eventos distintos registrados no periodo. Este campo fica no CSV, mas nao e o principal do dashboard porque nem todo deputado e esperado em todo evento.
- Diferenca YoY: comparacao do gasto acumulado no ano atual ate o mes corrente contra o mesmo intervalo do ano anterior.
- Diferenca contra media: quanto o deputado esta acima ou abaixo da media de gasto/presenca do partido ou UF.
- Ausencias de plenario: presenca formal em sessoes de plenario pelo webservice legado `ListarPresencasParlamentar`, separando justificadas e nao justificadas.
- Share por categoria: percentual do gasto liquido total do mandato por tipo de despesa, apresentado em barras horizontais.
- Votos em PECs: votos nominais vinculados a proposicoes do tipo `PEC` nos arquivos anuais de votacoes da Camara.
- Votos por PEC no dashboard: resumo por deputado e PEC, com voto predominante e contagens de Sim, Nao, Obstrucao/Outros, porque uma mesma PEC pode ter varias votacoes nominais.
- Gasto medio por candidato do partido: gasto total do partido dividido pela quantidade de deputados atuais do partido.
- Senadores: gastos usam CEAPS anual do Senado; votacoes usam votacoes nominais por senador nos Dados Abertos do Senado.
- Deputados estaduais RJ: cadastro eleitoral e votos nominais usam TSE 2022; dados de mandato usam fontes oficiais da ALERJ, com catalogo inicial para presenca, beneficios/subsidio e anuarios de atividade legislativa.

## Documentacao

- [Contexto estendido](docs/contexto-estendido.md)
- [Memoria do projeto](docs/memoria-projeto.md)
- [Star Schema inicial](docs/star-schema.md)

## Fontes Publicas

- Camara dos Deputados: https://dadosabertos.camara.leg.br/api/v2/
- Senado Federal: https://legis.senado.leg.br/dadosabertos/docs/
- CEAPS Senado: https://www.senado.gov.br/transparencia/LAI/verba/
- TSE Dados Abertos: https://dadosabertos.tse.jus.br/
- ALERJ: https://www.alerj.rj.gov.br/
- Portal da Transparencia da ALERJ: https://transparencia.alerj.rj.gov.br/
