# Handover Front-end - Senado e Deputados Estaduais RJ

## Contexto

O projeto tinha dashboard HTML focado em deputados federais/Camara. Foram adicionadas novas coletas para:

- Senadores: cadastro, gastos CEAPS e votacoes nominais.
- Deputados estaduais do RJ via TSE: candidatos, eleitos e votos nominais da eleicao de 2022.
- ALERJ: deputados em exercicio e catalogo de fontes oficiais para transparencia, presenca e atividade legislativa.

Os dados foram gerados, mas ainda nao foram integrados ao front-end. Os arquivos `reports/camara_dashboard.html` e `src/generate_interactive_report.py` ja tinham alteracoes locais de front-end antes desta expansao; preservar essas alteracoes ao integrar.

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

## Sugestao de Integracao no Dashboard

Evitar misturar tudo na tela atual da Camara. A melhor estrutura para o front-end e:

- Tab ou seletor de casa/escopo:
  - `Camara`
  - `Senado`
  - `RJ Estadual`
  - `Fontes ALERJ`

### Senado

Usar como base principal:

- `resumo_despesas_ceaps_senadores_mandato.csv`
- `resumo_votos_senadores_mandato.csv`

Possiveis cards:

- Senadores em exercicio: contagem de `codigoParlamentar`.
- Total CEAPS: soma de `valor_reembolsado_total`.
- Total de votos nominais: soma de `qtd_votos`.
- Media CEAPS por senador.

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

### RJ Estadual - TSE

Usar como base principal:

- `deputados_estaduais_rj_eleitos_2022.csv`

Possiveis cards:

- Eleitos: 70.
- Total de votos nominais.
- Maior votacao.
- Partidos com eleitos.

Tabela sugerida:

- Nome de urna
- Partido
- Numero
- Votos nominais
- Municipios com voto
- Genero
- Cor/raca
- Grau de instrucao
- Ocupacao

Filtros:

- Partido
- Situacao total turno
- Genero
- Cor/raca
- Ordenacao por votos nominais ou municipios com voto.

### RJ Estadual - ALERJ

Usar como base principal:

- `deputados_estaduais_rj_alerj_em_exercicio.csv`
- `alerj_fontes_transparencia_e_legislativo.csv`

Possiveis cards:

- Deputados em exercicio: 70.
- Recursos oficiais catalogados: 598.
- PDFs de atividade legislativa: 522.

Tabela de deputados:

- Nome
- Partido
- Perfil ALERJ
- Lideranca

Tabela de fontes:

- Tipo
- Formato
- Titulo
- URL
- Observacao

Importante: por enquanto, ALERJ e uma camada de rastreabilidade oficial, nao uma fato-table completa de presenca/votacoes. As paginas de transparencia testadas nao tinham tabelas HTML diretas; muita coisa esta em PDFs ou sistemas legados.

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

Integrar primeiro os CSVs agregados no dashboard:

1. Senado por `resumo_despesas_ceaps_senadores_mandato.csv` + `resumo_votos_senadores_mandato.csv`.
2. RJ estadual TSE por `deputados_estaduais_rj_eleitos_2022.csv`.
3. ALERJ por `deputados_estaduais_rj_alerj_em_exercicio.csv` + `alerj_fontes_transparencia_e_legislativo.csv`.

Depois, criar uma etapa separada para parsing dos PDFs/portais legados da ALERJ em fatos estruturados de presenca, votacoes e atividade legislativa.
