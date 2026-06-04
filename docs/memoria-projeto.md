# Memoria do Projeto

Este arquivo registra decisoes e contexto duravel para manter consistencia entre proximas iteracoes.

## Decisoes Iniciais

- O modelo analitico deve seguir Star Schema.
- A primeira extracao implementada e da Camara dos Deputados.
- Os dados brutos extraidos devem ser salvos em `data/raw/`.
- A documentacao deve usar Markdown e Mermaid.
- O projeto deve manter rastreabilidade entre dados modelados e identificadores originais das APIs publicas.
- O primeiro relatorio interativo e um HTML estatico gerado em `reports/camara_dashboard.html`.
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

## Proximas Decisoes Pendentes

- Definir banco analitico alvo: PostgreSQL, DuckDB, SQLite ou carga direta no Power BI.
- Definir periodicidade de atualizacao: diaria, semanal ou mensal.
- Definir se o ETL sera executado localmente, em GitHub Actions ou em outro orquestrador.
- Definir padrao de nomenclatura final das tabelas: portugues, ingles ou hibrido tecnico.
- Definir criterios para selecionar proposicoes prioritarias, como PECs e votacoes nominais relevantes.
- Definir fonte definitiva para beneficios alem do subsidio, como auxilio-moradia e outras verbas indenizatorias.
- Definir se a taxa de presenca deve usar eventos, sessoes de plenario ou ambos como denominador.
- Incluir presenca formal de plenario quando o webservice legado for integrado.

## Padroes de Saida

- CSV bruto: `data/raw/<fonte>/`
- CSV tratado/modelado: `data/processed/<fonte>/`
- Documentacao tecnica: `docs/`
- Codigo de extracao: `src/`
- Relatorios interativos: `reports/`
