# Memoria do Projeto

Este arquivo registra decisoes e contexto duravel para manter consistencia entre proximas iteracoes.

## Decisoes Iniciais

- O modelo analitico deve seguir Star Schema.
- A primeira extracao implementada e da Camara dos Deputados.
- Os dados brutos extraidos devem ser salvos em `data/raw/`.
- A documentacao deve usar Markdown e Mermaid.
- O projeto deve manter rastreabilidade entre dados modelados e identificadores originais das APIs publicas.
- O front-end publicado passou a ser um site estatico multi-pagina em `reports/`, com `index.html` como landing page e paginas separadas para deputados federais, senadores, deputados estaduais RJ e metodologia.
- A landing page deve trazer analises menos granulares antes do detalhe individual, incluindo gasto parlamentar federal por partido e por UF.
- A landing tambem deve trazer "cortes prontos" com titulo, numero principal, tese, contraponto e fonte para transformar dado em narrativa responsavel.
- A remuneracao inicial usa o subsidio bruto parlamentar como referencia mensal fixa e deve ser revisada quando a fonte oficial mudar.
- A presenca inicial vem do arquivo anual `eventosPresencaDeputados-{ano}.csv`, filtrado para o mes atual.
- A versao de mandato usa a legislatura atual identificada em `deputados_em_exercicio.csv` e consulta `/legislaturas/{id}` para obter inicio e fim do periodo.
- A diferenca YoY compara o acumulado do ano atual ate o mes corrente com o mesmo intervalo do ano anterior.
- O percentual de presenca atual e um proxy baseado em eventos distintos registrados, nao uma taxa oficial de presenca em plenario.
- O dashboard usa `indice_presenca_relativa` como percentual principal, comparando cada deputado ao maior volume de presencas em eventos entre deputados no periodo.
- Ausencias justificadas e nao justificadas usam o webservice legado `ListarPresencasParlamentar`, que exige `matricula`; a matricula e obtida em `ObterDeputados` e cruzada por `ideCadastro`.
- Votos em PECs usam arquivos anuais `votacoesProposicoes`, `votacoesVotos` e `votacoes`, filtrando `proposicao_siglaTipo = PEC`.
- A secao "Votos por PEC" do dashboard agrega por deputado e PEC, exibindo voto predominante e contagens, para reduzir peso do HTML e evitar listar todas as votacoes nominais repetidas.
- A diferenca de media exibida na tabela passou a ser contra a media geral por candidato, nao contra a media do partido.
- A expansao para o Senado usa `data/raw/senado/`, com lista de senadores em exercicio via Dados Abertos do Senado, CEAPS anual via CSV de transparencia e votacoes nominais por senador.
- No front-end, CEAPS do Senado deve ser consolidada a partir do arquivo granular de despesas quando o resumo por senador vier zerado, cruzando nomes normalizados.
- A expansao para deputados estaduais do RJ usa DOCIGP/ALERJ como fonte analitica de gasto parlamentar por deputado e categoria. TSE 2022 e fontes documentais da ALERJ ficam como contexto/rastreabilidade, nao como pagina principal.
- Fontes ALERJ nao devem aparecer como secao analitica propria no produto final; ficam resumidas em metodologia/fontes. O foco da experiencia e gasto parlamentar x sinais de comprometimento com o trabalho.
- Em paginas de parlamentares, categorias de gasto devem responder ao filtro de deputado, senador, partido ou UF. Para Camara isso vem do CSV granular de despesas; para Senado vem do granular CEAPS; para RJ vem dos lancamentos DOCIGP.

## Entidades Prioritarias

- Politicos
- Calendario
- Proposicoes
- Orgaos legislativos
- Fornecedores
- Tipos de despesa
- Gastos parlamentares
- Remuneracao parlamentar
- Votos
- Presenca parlamentar
- Candidaturas eleitorais
- Fontes documentais estaduais

## Proximas Decisoes Pendentes

- Definir banco analitico alvo: PostgreSQL, DuckDB, SQLite ou carga direta no Power BI.
- Definir periodicidade de atualizacao: diaria, semanal ou mensal.
- Definir se o ETL sera executado localmente, em GitHub Actions ou em outro orquestrador.
- Definir padrao de nomenclatura final das tabelas: portugues, ingles ou hibrido tecnico.
- Definir criterios para selecionar proposicoes prioritarias, como PECs e votacoes nominais relevantes.
- Definir fonte definitiva para beneficios alem do subsidio, como auxilio-moradia e outras verbas indenizatorias.
- Definir se a taxa de presenca deve usar eventos, sessoes de plenario ou ambos como denominador.
- Incluir presenca formal de plenario quando o webservice legado for integrado.
- Definir parser de PDFs/Notes da ALERJ para transformar anuarios e listas de presenca em fatos estruturados.
- Definir criterio de conciliacao entre nomes TSE 2022, nomes parlamentares atuais da ALERJ e eventuais suplentes em exercicio.
- Integrar presenca e votacoes estaduais da ALERJ apenas quando houver fatos estruturados confiaveis; nao inferir comprometimento estadual sem fonte propria.

## Padroes de Saida

- CSV bruto: `data/raw/<fonte>/`
- CSV tratado/modelado: `data/processed/<fonte>/`
- Documentacao tecnica: `docs/`
- Codigo de extracao: `src/`
- Relatorios interativos: `reports/`

## Novos Scripts

- `src/extract_senado_senadores.py`: gera senadores em exercicio, CEAPS de mandato, resumo de gastos, votos nominais e resumo de votos.
- `src/extract_tse_deputados_estaduais_rj.py`: gera candidatos e eleitos a deputado estadual do RJ em 2022 com votos nominais agregados.
- `src/extract_alerj_deputados_rj.py`: gera deputados estaduais em exercicio na ALERJ e catalogo de fontes oficiais de transparencia/atividade legislativa.
- `src/extract_alerj_docigp.py`: gera deputados, orcamentos, lancamentos e resumos DOCIGP de gasto parlamentar estadual.

## Front-end Atual

- `src/generate_interactive_report.py` gera:
  - `reports/index.html`
  - `reports/deputados-federais.html`
  - `reports/senadores.html`
  - `reports/deputados-estaduais-rj.html`
  - `reports/metodologia.html`
  - `reports/camara_dashboard.html` como redirecionamento de compatibilidade.
- O site e mobile-first, com menu sanduiche lateral em todas as paginas.
- No mobile, o topo deve ficar enxuto: menu sanduiche e titulo curto. Autoria e LinkedIn ficam no menu lateral e no rodape para evitar overflow.
- Em paginas de detalhe, os KPIs aparecem antes dos filtros; os filtros ficam colapsaveis no mobile e abertos no desktop.
- A pagina de deputados federais inclui rankings editoriais prontos e seletor de tom do roteiro: neutro/fact-check, critica e elogio. Esses textos devem manter ressalvas juridicas e metodologicas.
- Nome e LinkedIn de Lucca Lanzellotti devem permanecer visiveis em todas as paginas.
