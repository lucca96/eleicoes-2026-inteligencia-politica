# Contexto Estendido

## Visao Geral

Este projeto organiza uma solucao de inteligencia de dados politicos para as eleicoes de 2026. O foco inicial esta em parlamentares federais, com dados publicos da Camara dos Deputados e do Senado Federal.

## Escopo Analitico

As primeiras trilhas de analise sao:

- Gastos parlamentares: despesas detalhadas da Cota Parlamentar, fornecedores, tipos de despesa, valores liquidos e documentos fiscais.
- Remuneracao parlamentar: subsidio mensal usado como referencia de custo fixo do mandato.
- Presenca parlamentar: presencas, ausencias e ausencias justificadas em plenario e comissoes.
- Votacoes: votos nominais, proposicoes, orientacao partidaria e resultado de votacoes relevantes.
- Comparativos temporais: diferencas YoY e comparacoes contra medias de partido e estado.
- Ausencias formais em plenario: percentual de ausencias justificadas e nao justificadas por deputado, partido e UF.
- Votacoes em PECs: historico de votos nominais relacionados a proposicoes do tipo PEC.

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
- Separar metrica oficial de presenca em plenario de proxy de presenca em eventos quando as fontes forem diferentes.
- Usar barras horizontais para share de categorias de gasto, evitando grafico de pizza ou donut.

## Fontes de Dados

- Dados Abertos da Camara: `https://dadosabertos.camara.leg.br/api/v2/`
- Arquivos de presenca da Camara: `https://dadosabertos.camara.leg.br/arquivos/eventosPresencaDeputados/csv/`
- Dados Abertos do Senado: `https://legis.senado.leg.br/dadosabertos/docs/`
