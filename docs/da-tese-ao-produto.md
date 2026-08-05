# Da tese ao produto: testes empíricos e ecossistema de business case

> Documento de trabalho. Objetivo: (1) resumir os testes/resultados empíricos da dissertação de forma auto-contida e (2) usar essas conclusões — incluindo a conclusão *negativa* — como base honesta para desenhar um sistema e sub-ecossistema de negócio.

---

## Parte 1 — O que a tese testou (resumo técnico)

### 1.1 Pergunta de investigação

A tese testa se modelos de machine learning conseguem prever **retornos horários do Bitcoin** de forma mais eficaz do que benchmarks *naive* fortes, quando o desenho experimental é reprodutível, **livre de leakage** (fuga de informação do futuro) e avaliado em múltiplos horizontes.

### 1.2 Desenho experimental (o "teste" propriamente dito)

| Elemento | Configuração |
|---|---|
| Alvo | Retorno direto (forward return), não preço em nível |
| Horizontes | 1h, 6h, 24h |
| Janela out-of-sample | 9 jan 2024 → 8 jan 2025 (inclui aprovação dos ETFs spot BTC nos EUA e o halving de abril 2024 — regime de alta volatilidade) |
| Validação | Walk-forward de origem rolante (*rolling-origin*), com **gap de purga de 24h** entre treino e teste |
| Pré-processamento | Restrito ao bloco de treino em cada split (sem fuga estatística treino→teste); variáveis quase-constantes removidas; imputação apenas com estatísticas de treino |
| Modelos comparados (núcleo defendido) | **Naive0**, **NaiveLast**, **OLS**, **Random Forest**, **ARIMA** |
| Modelo auxiliar (não pertence ao ranking principal) | **LSTM** (52 splits válidos vs. 53 dos restantes; caminho de exportação separado) |
| Métricas | MAE, RMSE, sMAPE, MASE, Directional Accuracy (DA), F1, R² fora da amostra |
| Teste estatístico comparativo | **Diebold–Mariano (DM)** por split, contra Naive0 (melhor/pior a p<0,05) |
| Features exógenas conceptuais | Sentimento (notícias/redes) e hash-rate — cobertura real limitada (sentimento parcial, hash-rate horário praticamente ausente) |

### 1.3 Resultados por horizonte

**1 hora** (a configuração mais exigente/ruidosa):

| Modelo | MAE | RMSE | DA (%) | F1 | DM vs N0 (B/W) |
|---|---|---|---|---|---|
| Naive0 | 0.003627 | 0.005321 | — | — | — |
| OLS | 0.003683 (+1.55%) | 0.005367 | 51.33 | 0.528 | 0/4 |
| RF | 0.004033 | 0.005692 | 51.12 | 0.427 | 0/13 |
| ARIMA | 0.045971 | 0.051331 | 50.27 | 0.488 | 0/53 |
| LSTM (auxiliar) | 0.012067 | 0.013381 | 48.30 | 0.169 | 0/47 |

**6 horas**:

| Modelo | MAE | DA (%) | F1 | DM vs N0 (B/W) |
|---|---|---|---|---|
| Naive0 | 0.009110 | — | — | — |
| OLS | 0.009533 (+4.64%) | 52.51 | 0.526 | 4/18 |
| RF | 0.010936 | 50.33 | 0.480 | 0/30 |

**24 horas**:

| Modelo | MAE | DA (%) | F1 | DM vs N0 (B/W) |
|---|---|---|---|---|
| Naive0 | 0.019720 | — | — | — |
| OLS | 0.020895 (+5.96%) | 50.80 | 0.524 | 14/22 |
| RF | 0.029491 | 49.48 | 0.462 | 7/34 |

### 1.4 As quatro conclusões centrais do capítulo de resultados

1. **Naive0 venceu em MAE/RMSE médios nos três horizontes.** Nenhum modelo não-naive foi consistentemente melhor.
2. **OLS foi o melhor desafiante não-naive**, mas ficou sempre acima do Naive0 (+1.55% a 1h, +4.64% a 6h, +5.96% a 24h).
3. **Desempenho direcional fraco**: melhor DA observada = 52.51% (OLS, 6h) — marginal acima do acaso (50%).
4. **Evidência Diebold–Mariano mista e limitada**: mesmo o OLS teve mais splits "pior" do que "melhor" que o Naive0 em quase todos os horizontes; ARIMA e LSTM tiveram desempenho materialmente pior.

### 1.5 Interpretação assumida na tese (importante para o business case)

- R² fora da amostra **negativo em todos os modelos e horizontes** → os modelos treinados pioraram o erro quadrático relativo ao benchmark, não apenas "explicaram pouco".
- A tese **não testa lucro de negociação**: sem custos de transação, slippage, execução ou dimensionamento de posição. Precisão estatística ≠ valor económico.
- Cobertura exógena real (sentimento, hash-rate) ficou muito abaixo do desenho conceptual — não é um teste multimodal "cheio".
- Conclusão-chave: **sob validação rigorosa e livre de leakage, a previsibilidade de curto prazo do Bitcoin é fraca e instável**, e isso deve ser tratado como resultado científico válido, não como falha do estudo.

### 1.6 Prioridades de investigação futura (tabela da tese)

| Direção futura | Motivação | Requisito metodológico |
|---|---|---|
| Modelos sensíveis a regime (HMM, híbridos) | Estrutura preditiva pode depender do estado do mercado | Testar sob o mesmo protocolo purgado, contra naive forte |
| Dados exógenos de maior frequência | Sentimento diário/hash-rate ausente limitou o ganho multimodal | Sentimento intradiário, news, order-flow, on-chain alinhados causalmente |
| Explicabilidade consistente por split | Arquivo não guarda feature importance/SHAP por split | Persistir artefactos de explicabilidade junto às métricas |
| Comparação alargada de modelos | Boosting, GRU, Transformer ainda não testados nas mesmas condições | Mesmo pré-processamento, splits e regras de report |
| Avaliação económica pós-validação estatística | Precisão estatística ≠ lucro | Custos de transação, slippage, turnover, execução, portfólio |

---

## Parte 2 — Sistema e sub-ecossistema de business case

### 2.1 Princípio orientador

A tese **não** prova que é possível prever o Bitcoin e ganhar dinheiro com isso. Prova o oposto: modelos sofisticados **não bateram de forma estável** um benchmark naive, sob validação rigorosa. Um business case honesto **não deve vender "sinal de trading"** — deve vender exatamente aquilo que a tese demonstrou ter valor: **o protocolo de validação em si** (deteção de leakage, benchmarking naive-first, teste DM, transparência de instabilidade).

Isto define o posicionamento: não é uma fintech de "previsão de preço", é uma **infraestrutura de validação e auditoria de modelos preditivos em mercados cripto/financeiros** — "o TÜV/auditor independente dos modelos de forecasting", não "mais um modelo que promete alpha".

### 2.2 Proposta de valor

> "Antes de confiar num modelo de trading ou de research quantitativo, prove que ele bate um benchmark naive, sob um protocolo sem fuga de informação, com significância estatística documentada — ou saiba, de forma auditável, que não bate."

Público que precisa disto: fundos cripto, desks de research, exchanges, reguladores/compliance, fintechs que vendem "sinais", investidores de retalho a avaliar produtos algorítmicos.

### 2.3 Arquitetura do ecossistema (subsistemas)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ECOSSISTEMA "NAIVE-FIRST"                     │
│      Auditoria e validação de modelos preditivos em cripto       │
└─────────────────────────────────────────────────────────────────┘
        │
        ├── 1. Motor de Validação Leakage-Aware (core IP)
        │     • Walk-forward de origem rolante + gap de purga configurável
        │     • Pré-processamento restrito a treino, por split
        │     • Benchmarks naive obrigatórios (Naive0 / NaiveLast) como baseline
        │     • Teste Diebold–Mariano por split, com correção de variância
        │       de longo prazo para horizontes sobrepostos (Harvey et al. 1997)
        │     → Distribuível como SDK/biblioteca (Python) + serviço API
        │
        ├── 2. Pipeline de Dados Multimodal Causal
        │     • Preço/mercado (OHLCV multi-horizonte)
        │     • Sentimento (notícias, redes sociais) com alinhamento causal
        │       explícito (lag documentado, sem look-ahead)
        │     • On-chain / hash-rate e outras proxies de rede
        │     • Contratos de qualidade de dados: cobertura, gaps, timestamps
        │     → Resolve a limitação #2 da tese (cobertura exógena fraca)
        │
        ├── 3. Dashboard de Benchmark Contínuo (produto SaaS)
        │     • Monitorização em produção: o modelo do cliente continua a
        │       bater o naive, split a split, mês a mês?
        │     • Alertas de degradação / mudança de regime
        │     • Relatórios DA, MAE, RMSE, MASE, R² fora da amostra, DM
        │     → Ligado à Parte 1.3–1.5 (mesmas métricas da tese)
        │
        ├── 4. Camada de "Reality Check" / Auditoria de Terceiros
        │     • Devida diligência quantitativa: um fundo/fintech submete
        │       o seu modelo (ou apenas as suas previsões) e recebe um
        │       relatório de auditoria independente naive-first
        │     • Certificação/selo "validado sob protocolo sem leakage"
        │     → Modelo de receita B2B (compliance, due diligence, M&A)
        │
        ├── 5. Módulo Económico (fase 2, explicitamente fora do escopo
        │     da tese e por isso diferenciador de roadmap)
        │     • Custos de transação, slippage, execução, turnover
        │     • Simulação de portfólio realista pós-validação estatística
        │     → Só ativado depois de um modelo passar o subsistema 1
        │
        └── 6. API / SDK para terceiros
              • Integração em plataformas de research, exchanges, fintechs
              • Modelo "bring your own model": clientes trazem previsões,
                o sistema devolve veredicto estatístico honesto
```

### 2.4 Modelos de receita possíveis

| Linha de negócio | Cliente-alvo | Formato |
|---|---|---|
| SDK/licença do motor de validação | Quant desks, investigadores, fintechs | Licenciamento + suporte |
| SaaS de monitorização contínua | Fundos, gestores de algoritmos | Subscrição mensal por modelo monitorizado |
| Auditoria/certificação sob pedido | Investidores, compliance, reguladores | Serviço pontual/relatório pago |
| Dados exógenos causais (feed) | Equipas de research | Data-as-a-service |
| Consultoria de desenho experimental | Equipas académicas/industriais | Projeto |

### 2.5 Diferenciação face ao mercado

A maioria dos produtos de "sinais" ou "IA para cripto" vende a promessa de alpha. Este ecossistema vende o oposto — **honestidade estatística verificável** — apoiada num resultado empírico documentado (a própria tese) que mostra exatamente como é fácil enganar-se com validação fraca (splits aleatórios, pré-processamento global, ausência de benchmark naive). Isso é o argumento de vendas: "nós sabemos como os modelos parecem bons sem ser — porque testámos isso."

### 2.6 Roadmap faseado (alinhado às prioridades de investigação futura da tese)

1. **Fase 0 (MVP)**: motor de validação (subsistema 1) como biblioteca open-core + relatório de auditoria manual.
2. **Fase 1**: dashboard de benchmark contínuo (subsistema 3) para clientes piloto (fundos pequenos/médios).
3. **Fase 2**: pipeline de dados causal (subsistema 2) — sentimento e on-chain intradiário, resolvendo a limitação de cobertura da tese.
4. **Fase 3**: modelos sensíveis a regime (HMM/híbridos) como oferta de research aplicada, testados sob o mesmo protocolo.
5. **Fase 4**: módulo económico (subsistema 5) — só depois de um modelo cliente demonstrar superioridade estável sobre o naive.
6. **Fase 5**: certificação/selo de terceiros (subsistema 4) como produto de confiança/compliance.

### 2.7 Riscos e limites éticos a respeitar

- **Não prometer o que a tese não provou**: não posicionar como "sistema de previsão do Bitcoin". O produto é validação, não geração de sinal.
- Deixar claro nos relatórios de cliente a distinção **precisão estatística vs. lucro económico** (secção 1.5).
- Evitar reivindicar significância estatística em horizontes sobrepostos sem a correção de variância adequada (limitação explícita da tese, secção "Comparative statistical testing").
- Qualquer extensão para sinais de trading exige o módulo económico (custos, slippage) antes de qualquer alegação de rentabilidade.

---

## Parte 3 — Próximos passos sugeridos

- [ ] Validar com stakeholders qual subsistema tem procura mais imediata (provável: 3 — dashboard de benchmark contínuo, é o mais vendável a fundos existentes)
- [ ] Extrair o motor de validação (`walk-forward + purge + DM test`) dos scripts (`run_arima_returns.py`, `run_rf_noleak.py`, `run_sarima_only.py`) para uma biblioteca reutilizável e desacoplada do dataset do Bitcoin
- [ ] Definir formato do "relatório de auditoria" (subsistema 4) como artefacto vendável, inspirado nas tabelas da secção 1.3 desta síntese
- [ ] Mapear requisitos de dados causais (subsistema 2) para expandir além de sentimento/hash-rate (ex.: order-flow, derivados)
