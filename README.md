# Sistema Especialista Inteligente para Mapeamento, Compatibilidade e Trilha de Carreira em TI

Sistema Especialista Baseado em Regras com **Tratamento de Incerteza** e **Pontuação Ponderada**,
desenvolvido em Python. Atua como *Consultor Avançado de Carreiras e Desenvolvimento Profissional*:
analisa o perfil multifacetado do usuário a partir de respostas graduais, calcula uma **matriz de
compatibilidade percentual** para 10 trilhas de TI, identifica **lacunas de competências (skill gaps)**
e gera um **plano de ação individualizado** (roadmap, certificações e portfólio).

> Centro Universitário Presidente Antônio Carlos — UNIPAC Barbacena
> Disciplina: Sistemas Especialistas

---

## 1. Por que não usar regras SE-ENTÃO rígidas

O mundo real raramente é preto no branco. Um motor puramente booleano responderia
"*você é DevOps*" ou "*você não é DevOps*", e quebraria diante de respostas do tipo
"*gosto moderadamente de infraestrutura*".

Este projeto resolve isso com três mecanismos combinados, todos parametrizados por arquivo externo:

| Mecanismo | O que mede | Faixa |
|---|---|---|
| **Cobertura ponderada** | Quanto o usuário possui daquilo que a trilha exige (inclui pesos negativos, que contraindicam) | 0 – 1 |
| **Forma do perfil** | Similaridade de cosseno entre o perfil centrado na média do próprio usuário e o vetor de pesos da trilha | 0 – 1 |
| **Fatores de Certeza (MYCIN)** | Grau de confiança das conclusões, combinando regras SE-ENTÃO com CF em `[-1, +1]` | -1 – +1 |

Sobre o resultado incidem ainda **regras de penalidade** para perfis logicamente conflitantes
e um ajuste leve pelos **objetivos de carreira** declarados.

### A fórmula

```
score      = (w_forma · forma + w_cobertura · cobertura) · (1 − f_obj) + f_obj · bônus_objetivos
compatib.  = score · (1 − penalidade_total) · 100
```

Todos os coeficientes (`w_forma`, `w_cobertura`, `f_obj`, teto de penalidade) vivem em
`dados/regras_carreiras.json → configuracao.pesos_modelo`. **Nada disso está hardcoded no Python.**

### Por que a parcela de "forma" existe

É a solução para o caso-limite clássico: o respondente que marca **5 em tudo**.
A cobertura sozinha o aprovaria em todas as 10 trilhas com nota quase idêntica.
A similaridade de cosseno sobre o vetor **centrado na média do usuário** mede o *contraste relativo*
entre as afinidades dele, e continua discriminando as trilhas.
Quando não há contraste nenhum (todas as respostas iguais), a forma assume valor neutro `0,5`
e o sistema **avisa explicitamente** que o ranking perdeu confiabilidade — ele não finge precisão que não tem.

---

## 2. Arquitetura

```
EspecialistaTI/
├── app.py                        Interface web (Streamlit) em 4 etapas — wizard
├── requirements.txt
├── README.md
├── dados/                        BASE DE CONHECIMENTO (desacoplada do código)
│   ├── regras_carreiras.json     Dimensões, matriz de pesos, regras de certeza,
│   │                             regras de penalidade, objetivos, configuração do modelo
│   └── trilhas_carreiras.json    Catálogo de competências, requisitos de nível Júnior,
│                                 roadmaps por fase, certificações, projetos de portfólio
├── motor/                        MOTOR DE INFERÊNCIA (não contém conhecimento de domínio)
│   ├── base_conhecimento.py      Carga, validação e fachada de acesso aos JSONs
│   ├── inferencia.py             Pontuação ponderada + fatores de certeza + diagnósticos
│   ├── gaps.py                   Skill Gap Analysis e estimativa de esforço
│   └── roadmap.py                Geração do plano de ação individualizado
└── tests/
    ├── test_motor.py             Testes de robustez e casos limite (Fase 5)
    └── test_app.py               Testes da interface, via AppTest oficial do Streamlit
```

**Desacoplamento do conhecimento** é o requisito arquitetural central: o pacote `motor/` não
conhece nenhuma trilha, nenhum peso e nenhuma regra. Trocar `dados/*.json` muda o comportamento
do sistema sem tocar em uma linha de Python — há um teste automatizado que prova exatamente isso
(`test_conhecimento_nao_esta_hardcoded_no_motor`).

---

## 3. Escopo: 10 trilhas

Back-end · Front-end/UX · Cientista de Dados · Engenheiro de Dados · Cibersegurança ·
DevOps/SRE · Cloud Architecture · Mobile · QA · Product Management

Cada trilha traz, na base de conhecimento:

- **18 dimensões de afinidade** ponderadas em `[-1, +1]` (pesos negativos contraindicam);
- **competências com nível mínimo exigido para Júnior** (escala 0 – 4) e criticidade
  (`essencial` / `importante` / `diferencial`);
- **roadmap em 4 fases**, dos fundamentos aos diferenciais de nível Pleno;
- **certificações** com emissor, custo e o momento certo de buscá-las;
- **projetos de portfólio** com o diferencial que cada um demonstra ao recrutador;
- **armadilhas** típicas da trilha e faixas salariais de referência.

---

## 4. Como executar

Requisito: **Python 3.10 ou superior**.

```bash
# 1. ambiente virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# 2. dependências
pip install -r requirements.txt

# 3. interface web
streamlit run app.py
```

A aplicação abre em `http://localhost:8501`.

### Testes

```bash
python -m unittest discover -s tests -v     # 68 testes
# ou, se tiver pytest:
pytest -v
```

São duas suítes:

- `tests/test_motor.py` — 57 testes do motor de inferência, gaps e roadmap;
- `tests/test_app.py` — 11 testes que percorrem o wizard com o `AppTest` oficial do
  Streamlit, sem navegador, garantindo que nenhuma das quatro etapas levante exceção
  e que a tela de resultado renderize métricas, gráficos, tabelas e downloads.

> **Nota sobre Windows 11 com Smart App Control:** o `requirements.txt` fixa `pandas` na
> série 2.2 de propósito. Os binários recém-publicados do pandas 3.x são bloqueados pela
> política de Controle de Aplicativo do Windows (`DLL load failed while importing conversion`)
> por ainda não terem reputação estabelecida. A série 2.2 carrega sem exigir nenhuma
> alteração nas configurações de segurança da máquina.

---

## 5. O fluxo da interface (wizard)

| Etapa | Conteúdo |
|---|---|
| **1. Perfil pessoal** | Formação, situação profissional e disponibilidade de estudo. Não altera a afinidade: calibra o **prazo** e o ponto de partida do roadmap. |
| **2. Afinidades técnicas** | 18 perguntas em **escala Likert 1–5**, agrupadas por categoria, com texto de ajuda. |
| **3. Objetivos e conhecimento** | Objetivos de carreira (múltipla escolha) e inventário de competências já dominadas. |
| **4. Resultado** | Ranking Top 3, matriz completa, justificativas, gaps, plano de ação e aba de transparência. |

A tela de resultado é dividida em seis abas:

1. **Visão geral** — gráfico de barras da compatibilidade e **gráfico de radar** sobrepondo
   o perfil do usuário à exigência das trilhas do Top 3.
2. **Matriz completa** — as 10 trilhas com compatibilidade, cobertura, aderência de perfil,
   CF e penalidade; exportável em CSV.
3. **Justificativas** — para cada trilha do Top 3: regras de certeza satisfeitas com seus CFs,
   o que pesou a favor, pontos de atenção e penalidades aplicadas.
4. **Análise de gaps** — prontidão para Júnior, gaps essenciais, prazo estimado e tabela
   competência por competência; permite **ajustar o nível individualmente** e recalcular.
5. **Plano de ação** — próximos passos ordenados, roadmap por fase com percentual concluído,
   certificações priorizadas, projetos de portfólio e download em Markdown.
6. **Transparência** — a fórmula, os parâmetros carregados do JSON e a **decomposição da nota
   dimensão por dimensão**, mostrando a contribuição de cada resposta.

---

## 6. Tratamento de casos limite (Fase 5)

O sistema foi testado contra os cenários que normalmente quebram sistemas especialistas:

| Caso limite | Comportamento |
|---|---|
| Todas as respostas iguais | Calcula o ranking, mas **sinaliza** que a parcela de forma ficou neutra e o resultado perdeu confiabilidade. |
| Tudo 5 (respondente entusiasmado) | Continua discriminando as trilhas pelo contraste relativo, em vez de dar ~100% para todas. |
| Tudo 1 | Compatibilidades absolutas baixas e recomendação de explorar a área antes de escolher. |
| **Perfil ambíguo** (gosta igualmente de dados e de web) | Detecta **empates parciais** dentro do limiar configurado, não força escolha única e apresenta justificativas de ambas as trilhas. |
| Dimensão não respondida | Assume o ponto médio da escala (equivale a "indiferente") sem quebrar o cálculo. |
| Valor fora da escala / não numérico | Truncado para a faixa válida ou substituído pelo valor neutro. |
| Perfil conflitante (quer gestão, rejeita infraestrutura) | **Penalidade** aplicada com motivo textual explícito, limitada pelo teto configurado. |
| Contraindicação forte | **CF negativo** resulta no rótulo "Contraindicado pelas regras", mesmo que a trilha pontue bem. |
| Usuário já pronto para Júnior | Zero próximos passos; o plano redireciona para os diferenciais de nível Pleno. |

Cobertura dos testes: integridade da base, casos limite de entrada, os 10 perfis arquetípicos,
ambiguidade e empates, álgebra de combinação de CFs (MYCIN), penalidades, objetivos,
análise de gaps, geração de plano e um teste de jornada completa fim a fim.

---

## 7. Fases do desenvolvimento

| Fase | Entrega | Onde está |
|---|---|---|
| 1 | Engenharia do conhecimento e modelagem JSON | `dados/*.json` |
| 2 | Motor de inferência com pontuação ponderada | `motor/inferencia.py` |
| 3 | Módulo de gaps e roadmap | `motor/gaps.py`, `motor/roadmap.py` |
| 4 | Interface web em etapas | `app.py` |
| 5 | Testes de robustez e casos limite | `tests/test_motor.py` |

---

## 8. Como estender a base de conhecimento

**Adicionar uma dimensão (pergunta):** acrescente um objeto em `dimensoes` com `id`, `pergunta`,
`categoria` e um peso em `[-1, +1]` para **cada** uma das 10 trilhas. O validador avisa se
alguma trilha ficar sem peso.

**Adicionar uma trilha:** declare-a em `regras_carreiras.json → trilhas`, acrescente o peso dela
em todas as dimensões e crie a entrada correspondente em `trilhas_carreiras.json → trilhas`
com competências, roadmap, certificações e projetos.

**Ajustar a sensibilidade do modelo:** edite `configuracao.pesos_modelo`. Aumentar `peso_forma`
privilegia o contraste do perfil; aumentar `peso_cobertura` privilegia o volume absoluto de
afinidade. `limiar_empate` controla quando duas trilhas são declaradas equivalentes.

O carregador valida a base no startup e exibe eventuais inconsistências na barra lateral
(pesos fora da faixa, trilhas sem detalhamento, competências fora do catálogo, regras
apontando para dimensões inexistentes).

---

## 9. Limitações declaradas

- As faixas salariais são referências de mercado brasileiro e envelhecem: devem ser revisadas
  periodicamente na base de conhecimento.
- Os pesos de correlação resultam de engenharia do conhecimento (elicitação com base em
  descrições de vaga e literatura de carreira), não de ajuste estatístico sobre dados reais
  de profissionais empregados.
- O resultado é **indicativo**. É uma ferramenta de apoio à reflexão, não um substituto de
  orientação profissional de carreira.
