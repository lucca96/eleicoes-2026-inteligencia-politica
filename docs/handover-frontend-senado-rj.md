# Handover Front-end - Senado e Deputados Estaduais RJ

## Contexto

O projeto tinha dashboard HTML focado em deputados federais/Camara. Foram adicionadas novas coletas para:

- Senadores: cadastro, gastos CEAPS e votacoes nominais.
- Deputados estaduais do RJ via TSE: candidatos, eleitos e votos nominais da eleicao de 2022.
- ALERJ: deputados em exercicio e catalogo de fontes oficiais para transparencia, presenca e atividade legislativa.

Os dados ja foram integrados ao front-end estatico em `reports/`. O arquivo `src/generate_interactive_report.py` e a fonte de verdade para regenerar as paginas; nao editar os HTMLs gerados manualmente.

## Arquivos de Codigo Novos

- `src/senado_client.py`
  - Cliente XML para os Dados Abertos do Senado.
- `src/extract_senado_senadores.py`
  - Extrai senadores em exercicio, CEAPS e votacoes nominais.
  - Flags uteis:
    - `--skip-votes`: valida cadastro e CEAPS sem baixar votacoes.
    - `--max-senators 2`: testa votacoes com amostra.
- `src/extract_tse_deputados_estaduais_rj.py`
  - Extrai candidatos e eleitos a deputado estadual do RJ em 2022 via TSE.
- `src/extract_alerj_deputados_rj.py`
  - Extrai deputados estaduais em exercicio na ALERJ e cataloga fontes oficiais.
- `src/project_paths.py`
  - Adicionou:
    - `RAW_SENADO_DIR`
    - `RAW_TSE_DIR`
    - `RAW_ALERJ_DIR`

## Dados Gerados e Validados

### Senado

Pasta: `data/raw/senado/`

Arquivos:

- `senadores_em_exercicio.csv`
  - 81 registros.
  - Campos principais:
    - `codigoParlamentar`
    - `nome`
    - `nomeCompleto`
    - `siglaPartido`
    - `siglaUf`
    - `email`
    - `urlFoto`
    - `urlPagina`
    - `codigoMandato`
    - `descricaoParticipacao`
    - `inicioPrimeiraLegislatura`
    - `fimSegundaLegislatura`
- `despesas_ceaps_senadores_mandato.csv`
  - 71.339 lancamentos.
  - Campos principais:
    - `ano`
    - `mes`
    - `nome`
    - `tipoDespesa`
    - `cnpjCpfFornecedor`
    - `nomeFornecedor`
    - `numDocumento`
    - `dataDocumento`
    - `detalhamento`
    - `valorReembolsado`
    - `codDocumento`
- `resumo_despesas_ceaps_senadores_mandato.csv`
  - Base mais simples para cards/tabela.
  - Campos principais:
    - dados de `senadores_em_exercicio.csv`
    - `qtd_lancamentos`
    - `valor_reembolsado_total`
- `votos_senadores_mandato.csv`
  - 30.954 votos nominais.
  - Campos principais:
    - `codigoParlamentar`
    - `nome`
    - `siglaPartido`
    - `siglaUf`
    - `dataSessao`
    - `descricaoMateria`
    - `siglaMateria`
    - `numeroMateria`
    - `anoMateria`
    - `ementaMateria`
    - `codigoSessaoVotacao`
    - `descricaoVotacao`
    - `descricaoResultado`
    - `voto`
- `resumo_votos_senadores_mandato.csv`
  - Base agregada para ranking e cards.
  - Campos principais:
    - dados de `senadores_em_exercicio.csv`
    - `qtd_votos`
    - `qtd_votacoes`
    - `votos_sim`
    - `votos_nao`
    - `votos_outros`

### TSE - Deputados Estaduais RJ

Pasta: `data/raw/tse/`

Arquivos:

- `deputados_estaduais_rj_candidatos_2022.csv`
  - 1.639 candidatos.
  - Campos principais:
    - `anoEleicao`
    - `sequencialCandidato`
    - `numeroCandidato`
    - `nomeUrna`
    - `nomeCompleto`
    - `siglaPartido`
    - `nomePartido`
    - `siglaUf`
    - `cargo`
    - `situacaoTotalTurno`
    - `situacaoCandidatura`
    - `genero`
    - `corRaca`
    - `grauInstrucao`
    - `ocupacao`
    - `eleito`
    - `votos_nominais`
    - `municipios_com_voto`
    - `zonas_com_voto`
- `deputados_estaduais_rj_eleitos_2022.csv`
  - 70 eleitos.
  - Mesmos campos do arquivo de candidatos.
  - Importante: a regra de eleito foi corrigida para nao classificar `NAO ELEITO` como eleito. Valores aceitos:
    - `ELEITO`
    - `ELEITO POR QP`
    - `ELEITO POR MEDIA`
    - `ELEITO POR MÉDIA`

### ALERJ

Pasta: `data/raw/alerj/`

Arquivos:

- `deputados_estaduais_rj_alerj_em_exercicio.csv`
  - 70 deputados em exercicio.
  - Campos principais:
    - `idAlerj`
    - `legislaturaAlerj`
    - `nome`
    - `siglaPartido`
    - `perfilUrl`
    - `lideranca`
    - `casaLegislativa`
    - `siglaUf`
- `alerj_fontes_transparencia_e_legislativo.csv`
  - 598 recursos oficiais catalogados.
  - Campos principais:
    - `tipo`
    - `formato`
    - `titulo`
    - `url`
    - `observacao`
- `alerj_anuario_atividade_legislativa_pdfs.csv`
  - 522 PDFs catalogados.
  - Campos principais:
    - `tipo`
    - `formato`
    - `nomeDeputadoOuRelatorio`
    - `url`
    - `observacao`

## Estado Atual do Front-end

O front-end foi reorganizado como site estatico multi-pagina em `reports/`, em vez de uma pagina unica longa:

- `index.html`: landing page, com visao geral, agregados por partido/UF e cards de cortes prontos.
- `deputados-federais.html`: gasto parlamentar, presenca, ausencias e PECs da Camara.
- `senadores.html`: CEAPS e votacoes nominais do Senado.
- `deputados-estaduais-rj.html`: gasto parlamentar DOCIGP/ALERJ por deputado e categoria.
- `metodologia.html`: fontes, metodologia e limites.
- `camara_dashboard.html`: redirecionamento de compatibilidade.

O produto deve manter foco em gasto parlamentar e sinais de comprometimento com o trabalho. Catalogos extensos de fontes nao devem aparecer como pagina analitica.

### Senado

Usar como base principal:

- `resumo_despesas_ceaps_senadores_mandato.csv`
- `resumo_votos_senadores_mandato.csv`

Possiveis cards:

- Senadores em exercicio: contagem de `codigoParlamentar`.
- Total CEAPS: soma de `valor_reembolsado_total`.
- Total de votos nominais: soma de `qtd_votos`.
- Media CEAPS por senador.
- Observacao de integracao: se `resumo_despesas_ceaps_senadores_mandato.csv` vier com `valor_reembolsado_total` zerado, o gerador consolida CEAPS por nome normalizado a partir de `despesas_ceaps_senadores_mandato.csv`.

Tabela sugerida:

- Nome
- UF
- Partido
- Valor CEAPS
- Qtd lancamentos
- Qtd votacoes
- Votos sim
- Votos nao
- Votos outros

Filtros:

- UF
- Partido
- Senador
- Ordenacao por CEAPS, qtd votacoes ou votos.

### RJ Estadual - DOCIGP/ALERJ

Usar como base principal:

- `docigp_resumo_gastos_deputados_estaduais_rj.csv`
- `docigp_lancamentos_deputados_estaduais_rj.csv`

Possiveis cards:

- Gasto parlamentar DOCIGP.
- Lancamentos.
- Fornecedores.
- Uso do limite.

Tabela/cards:

- Nome
- Partido
- Gasto parlamentar
- Lancamentos
- Fornecedores
- Uso do limite

Importante: categorias de gasto devem reagir ao filtro de deputado, senador, partido ou UF. Presenca e votacoes estaduais ainda dependem de extracao estruturada adicional; nao exibir proxy sem fonte confiavel.

## Ajustes Mobile e UX

- Topo mobile deve mostrar apenas menu sanduiche e titulo curto; autoria/LinkedIn ficam no drawer e rodape.
- Filtros das paginas de detalhe ficam colapsaveis no mobile e abertos no desktop.
- KPIs principais devem aparecer antes dos filtros em deputados federais, senadores e deputados estaduais RJ.
- A landing deve priorizar gasto parlamentar e sinais de trabalho; evitar secoes de fontes como bloco analitico principal.
- A landing deve transformar dados em narrativa responsavel: titulo, numero principal, tese, contraponto e fonte.
- A pagina federal inclui rankings editoriais e seletor de tom de roteiro. Manter sempre ressalvas para rankings sensiveis como ausencia nao justificada, custo por presenca e divulgacao parlamentar.

## Cuidados de Front-end

- Nao sobrescrever manualmente `reports/camara_dashboard.html` sem regenerar pelo script, se o fluxo atual do projeto continuar sendo HTML gerado.
- Conferir as alteracoes existentes em `src/generate_interactive_report.py` antes de editar; havia mudancas locais anteriores.
- CSVs estao em `utf-8-sig`; no browser, usar parser que respeite BOM.
- Numericos relevantes:
  - `valor_reembolsado_total`
  - `valorReembolsado`
  - `votos_nominais`
  - `qtd_votos`
  - `qtd_votacoes`
- Nomes TSE e ALERJ podem nao bater 1:1 por nome parlamentar, suplentes e mudancas de mandato. Evitar join automatico por nome sem uma etapa de conciliacao.

## Comandos de Validacao

```powershell
python -B src\extract_senado_senadores.py --skip-votes
python -B src\extract_senado_senadores.py --max-senators 2
python -B src\extract_senado_senadores.py
python -B src\extract_tse_deputados_estaduais_rj.py
python -B src\extract_alerj_deputados_rj.py
```

Validacao de sintaxe usada:

```powershell
python -B -c "from pathlib import Path; files=['src/senado_client.py','src/extract_senado_senadores.py','src/extract_tse_deputados_estaduais_rj.py','src/extract_alerj_deputados_rj.py']; [compile(Path(f).read_text(encoding='utf-8'), f, 'exec') for f in files]; print('syntax ok')"
```

## Documentacao Atualizada

- `README.md`
- `docs/contexto-estendido.md`
- `docs/memoria-projeto.md`
- `docs/star-schema.md`

## Proxima Etapa Recomendada

Criar etapa separada para parsing dos PDFs/portais legados da ALERJ em fatos estruturados de presenca, votacoes e atividade legislativa.
