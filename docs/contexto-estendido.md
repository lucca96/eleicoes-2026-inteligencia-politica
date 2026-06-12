# Contexto Estendido

## Visao Geral

Este projeto organiza uma solucao de inteligencia de dados politicos para as eleicoes de 2026. O foco inicial esta em parlamentares federais, com dados publicos da Camara dos Deputados e do Senado Federal, e foi expandido para deputados estaduais do RJ com dados eleitorais do TSE e fontes oficiais da ALERJ.

## Escopo Analitico

As primeiras trilhas de analise sao:

- Gastos parlamentares: despesas detalhadas da Cota Parlamentar, fornecedores, tipos de despesa, valores liquidos e documentos fiscais.
- Remuneracao parlamentar: subsidio mensal usado como referencia de custo fixo do mandato.
- Presenca parlamentar: presencas, ausencias e ausencias justificadas em plenario e comissoes.
- Votacoes: votos nominais, proposicoes, orientacao partidaria e resultado de votacoes relevantes.
- Comparativos temporais: diferencas YoY e comparacoes contra medias de partido e estado.
- Ausencias formais em plenario: percentual de ausencias justificadas e nao justificadas por deputado, partido e UF.
- Votacoes em PECs: historico de votos nominais relacionados a proposicoes do tipo PEC.
- Senadores: cadastro em exercicio, CEAPS e votacoes nominais.
- Deputados estaduais do RJ: candidatos/eleitos e votacao nominal via TSE; deputados em exercicio e fontes de presenca/atividade legislativa via ALERJ.

## Stack Tecnico

- ETL: Python com `requests`, `pandas`, tratamento de paginacao, retries e limites de requisicao.
- Modelagem: Star Schema como padrao obrigatorio para performance e clareza analitica.
- BI: Power BI, Power Query M e medidas DAX.
- Interface web: React com Tailwind CSS para ferramentas auxiliares.
- Documentacao: Markdown limpo e diagramas Mermaid.

## Principios de Modelagem

- Separar dimensoes conformadas de fatos transacionais.
- Manter chaves substitutas nas tabelas dimensionais.
- Preservar identificadores originais das APIs para rastreabilidade.
- Evitar tabelas fato com atributos textuais extensos, salvo quando necessario para auditoria.
- Preparar o modelo para expansao incremental: primeiro Camara, depois Senado.
- Separar casas legislativas em `casa_legislativa`, permitindo Camara, Senado e ALERJ sem misturar chaves naturais.
- Tratar dados estaduais em duas camadas: eleitoral nacional padronizada via TSE e mandato estadual com fonte propria da Assembleia Legislativa.
- Separar metrica oficial de presenca em plenario de proxy de presenca em eventos quando as fontes forem diferentes.
- Usar barras horizontais para share de categorias de gasto, evitando grafico de pizza ou donut.

## Fontes de Dados

- Dados Abertos da Camara: `https://dadosabertos.camara.leg.br/api/v2/`
- Arquivos de presenca da Camara: `https://dadosabertos.camara.leg.br/arquivos/eventosPresencaDeputados/csv/`
- Dados Abertos do Senado: `https://legis.senado.leg.br/dadosabertos/docs/`
- CEAPS Senado: `https://www.senado.gov.br/transparencia/LAI/verba/`
- Dados Abertos do TSE: `https://dadosabertos.tse.jus.br/`
- CDN de estatistica eleitoral do TSE: `https://cdn.tse.jus.br/estatistica/sead/odsele/`
- ALERJ: `https://www.alerj.rj.gov.br/`
- Portal da Transparencia da ALERJ: `https://transparencia.alerj.rj.gov.br/`

## Limites Atuais da Camada Estadual

- O TSE e a fonte estruturada para resultado eleitoral de deputados estaduais do RJ.
- A ALERJ publica parte dos dados de mandato em paginas HTML, paginas legadas e PDFs. Por isso, o primeiro extrator estadual cataloga fontes oficiais e gera a lista de deputados em exercicio.
- Presenca, votacoes e atividade legislativa estadual devem ser transformadas em fatos estruturados em uma etapa posterior de parsing dos recursos catalogados.
