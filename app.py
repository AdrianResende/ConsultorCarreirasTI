"""
Interface web do Sistema Especialista de Carreiras em TI.

Fluxo em quatro etapas (wizard):
    1. Perfil pessoal
    2. Afinidades tecnicas (escala Likert 1-5)
    3. Objetivos de carreira e inventario de conhecimento
    4. Resultado: ranking, gaps e plano de acao

Execucao:  streamlit run app.py
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from motor import (
    ErroBaseConhecimento,
    MotorInferencia,
    analisar_gaps,
    carregar_base,
    gerar_plano,
    inferir_niveis,
)

TOTAL_ETAPAS = 4
NOMES_ETAPAS = [
    "1. Perfil pessoal",
    "2. Afinidades tecnicas",
    "3. Objetivos e conhecimento",
    "4. Resultado e plano de acao",
]

CORES = ["#2563eb", "#7c3aed", "#0891b2", "#64748b", "#94a3b8"]

st.set_page_config(
    page_title="Consultor de Carreiras em TI",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------------ recursos
@st.cache_resource(show_spinner="Carregando base de conhecimento...")
def obter_base():
    return carregar_base()


@st.cache_resource
def obter_motor(_versao: str):
    return MotorInferencia(obter_base())


def iniciar_estado(base) -> None:
    padroes = {
        "etapa": 0,
        "nome": "",
        "formacao": "Graduacao em andamento (area de TI)",
        "nivel_experiencia": base.niveis_experiencia[0]["id"] if base.niveis_experiencia else None,
        "disponibilidade": base.disponibilidades[1]["id"] if len(base.disponibilidades) > 1 else None,
        "respostas": {d["id"]: 3 for d in base.dimensoes},
        "objetivos": [],
        "dominadas": [],
        "basicas": [],
        "niveis_ajustados": {},
        "trilha_escolhida": None,
        "processado": False,
    }
    for chave, valor in padroes.items():
        st.session_state.setdefault(chave, valor)


def ir_para(etapa: int) -> None:
    st.session_state.etapa = max(0, min(TOTAL_ETAPAS - 1, etapa))
    st.rerun()


# -------------------------------------------------------------------- graficos
def grafico_radar(ranking, base) -> go.Figure:
    """Radar das dimensoes: perfil do usuario x exigencia das trilhas do Top 3."""
    dimensoes = base.dimensoes
    rotulos = [d["id"].replace("_", " ").title() for d in dimensoes]
    fig = go.Figure()

    for cor, resultado in zip(CORES, ranking):
        exigencia = [
            max(0.0, float(d["pesos"].get(resultado.id, 0.0))) * 100 for d in dimensoes
        ]
        fig.add_trace(
            go.Scatterpolar(
                r=exigencia + exigencia[:1],
                theta=rotulos + rotulos[:1],
                name=f"Exige: {resultado.nome}",
                line=dict(color=cor, width=2),
                fill="toself",
                opacity=0.28,
                hovertemplate="%{theta}<br>Exigencia: %{r:.0f}%<extra></extra>",
            )
        )

    respostas = st.session_state.respostas
    minimo, maximo = base.escala
    perfil = [
        (respostas.get(d["id"], 3) - minimo) / max(1, (maximo - minimo)) * 100 for d in dimensoes
    ]
    fig.add_trace(
        go.Scatterpolar(
            r=perfil + perfil[:1],
            theta=rotulos + rotulos[:1],
            name="Seu perfil",
            line=dict(color="#111827", width=3, dash="dot"),
            hovertemplate="%{theta}<br>Sua afinidade: %{r:.0f}%<extra></extra>",
        )
    )

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%")),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0),
        height=560,
        margin=dict(l=60, r=60, t=40, b=90),
    )
    return fig


def grafico_barras(ranking) -> go.Figure:
    dados = list(reversed(ranking))
    nomes = [r.nome for r in dados]
    valores = [r.compatibilidade for r in dados]
    cores = ["#2563eb" if v >= 70 else "#0891b2" if v >= 55 else "#94a3b8" for v in valores]

    fig = go.Figure(
        go.Bar(
            x=valores,
            y=nomes,
            orientation="h",
            marker=dict(color=cores),
            text=[f"{v:.1f}%" for v in valores],
            textposition="outside",
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        xaxis=dict(title="Compatibilidade (%)", range=[0, 105]),
        yaxis=dict(title=""),
        height=460,
        margin=dict(l=10, r=40, t=20, b=40),
        showlegend=False,
    )
    return fig


def grafico_decomposicao(resultado) -> go.Figure:
    """Mostra como a nota final foi formada, dimensao por dimensao."""
    contribuicoes = sorted(
        [c for c in resultado.contribuicoes if abs(c.contribuicao) > 0.001],
        key=lambda c: c.contribuicao,
    )
    rotulos = [c.dimensao.replace("_", " ").title() for c in contribuicoes]
    valores = [c.contribuicao for c in contribuicoes]
    cores = ["#dc2626" if v < 0 else "#2563eb" for v in valores]

    fig = go.Figure(
        go.Bar(
            x=valores,
            y=rotulos,
            orientation="h",
            marker=dict(color=cores),
            customdata=[(c.resposta, c.peso) for c in contribuicoes],
            hovertemplate=(
                "%{y}<br>Sua resposta: %{customdata[0]}/5"
                "<br>Peso da trilha: %{customdata[1]:.2f}"
                "<br>Contribuicao: %{x:.3f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        xaxis=dict(title="Contribuicao (peso x resposta normalizada)"),
        height=max(380, 26 * len(contribuicoes)),
        margin=dict(l=10, r=20, t=20, b=40),
        showlegend=False,
    )
    return fig


# --------------------------------------------------------------------- etapas
def etapa_perfil(base) -> None:
    st.subheader("Etapa 1 - Perfil pessoal")
    st.caption(
        "Estes dados nao alteram a afinidade de perfil: eles calibram a estimativa de "
        "prazo e o ponto de partida do roadmap."
    )

    col1, col2 = st.columns(2)
    with col1:
        st.session_state.nome = st.text_input(
            "Como voce quer ser chamado?", value=st.session_state.nome, placeholder="Opcional"
        )
        st.session_state.formacao = st.selectbox(
            "Formacao atual",
            [
                "Ensino medio completo",
                "Curso tecnico em TI",
                "Graduacao em andamento (area de TI)",
                "Graduacao em andamento (outra area)",
                "Graduacao concluida (area de TI)",
                "Graduacao concluida (outra area)",
                "Pos-graduacao",
            ],
            index=[
                "Ensino medio completo",
                "Curso tecnico em TI",
                "Graduacao em andamento (area de TI)",
                "Graduacao em andamento (outra area)",
                "Graduacao concluida (area de TI)",
                "Graduacao concluida (outra area)",
                "Pos-graduacao",
            ].index(st.session_state.formacao),
        )

    with col2:
        niveis = base.niveis_experiencia
        rotulos_nivel = {n["id"]: n["rotulo"] for n in niveis}
        ids_nivel = list(rotulos_nivel)
        st.session_state.nivel_experiencia = st.radio(
            "Qual sua situacao profissional hoje?",
            ids_nivel,
            index=ids_nivel.index(st.session_state.nivel_experiencia)
            if st.session_state.nivel_experiencia in ids_nivel
            else 0,
            format_func=lambda i: rotulos_nivel[i],
        )

        disp = base.disponibilidades
        rotulos_disp = {d["id"]: d["rotulo"] for d in disp}
        ids_disp = list(rotulos_disp)
        st.session_state.disponibilidade = st.select_slider(
            "Quanto tempo voce consegue estudar por semana?",
            options=ids_disp,
            value=st.session_state.disponibilidade
            if st.session_state.disponibilidade in ids_disp
            else ids_disp[0],
            format_func=lambda i: rotulos_disp[i],
        )

    nota = next(
        (n.get("nota", "") for n in base.niveis_experiencia if n["id"] == st.session_state.nivel_experiencia),
        "",
    )
    if nota:
        st.info(nota)

    _navegacao(proxima_habilitada=True)


def etapa_afinidades(base) -> None:
    st.subheader("Etapa 2 - Afinidades tecnicas")
    st.caption(
        "Responda em escala de 1 a 5. **Diferencie as notas**: o motor usa o contraste "
        "entre suas respostas para separar as trilhas. Marcar 5 em tudo reduz a precisao."
    )

    rotulos = base.configuracao.get("rotulos_likert", {})
    legenda = " | ".join(f"**{k}** {v}" for k, v in sorted(rotulos.items()))
    st.markdown(f"<small>{legenda}</small>", unsafe_allow_html=True)
    st.divider()

    por_categoria: Dict[str, List[dict]] = {}
    for dim in base.dimensoes:
        por_categoria.setdefault(dim.get("categoria", "Geral"), []).append(dim)

    minimo, maximo = base.escala
    for categoria, dims in por_categoria.items():
        st.markdown(f"##### {categoria}")
        for dim in dims:
            st.session_state.respostas[dim["id"]] = st.slider(
                dim["pergunta"],
                min_value=minimo,
                max_value=maximo,
                value=int(st.session_state.respostas.get(dim["id"], 3)),
                step=1,
                help=dim.get("ajuda", ""),
                key=f"slider_{dim['id']}",
            )
        st.write("")

    valores = list(st.session_state.respostas.values())
    if len(set(valores)) == 1:
        st.warning(
            "Todas as respostas tem o mesmo valor. O ranking sera calculado, mas as "
            "diferencas entre trilhas ficarao pouco confiaveis."
        )

    _navegacao(proxima_habilitada=True)


def etapa_objetivos(base) -> None:
    st.subheader("Etapa 3 - Objetivos de carreira e inventario de conhecimento")

    objetivos = base.objetivos
    st.markdown(f"##### {objetivos.get('pergunta', 'Objetivos de carreira')}")
    st.caption(objetivos.get("ajuda", ""))

    opcoes = {o["id"]: o["rotulo"] for o in objetivos.get("opcoes", [])}
    selecionados = []
    colunas = st.columns(2)
    for i, (obj_id, rotulo) in enumerate(opcoes.items()):
        with colunas[i % 2]:
            if st.checkbox(rotulo, value=obj_id in st.session_state.objetivos, key=f"obj_{obj_id}"):
                selecionados.append(obj_id)
    st.session_state.objetivos = selecionados

    st.divider()
    st.markdown("##### Inventario de competencias")
    st.caption(
        "Marque o que voce ja conhece. Isso alimenta a analise de gaps: o sistema compara "
        "seu nivel atual com o exigido para uma vaga Junior na trilha recomendada. "
        "Voce podera ajustar nivel por nivel na tela de resultado."
    )

    agrupado = base.competencias_por_area()
    opcoes_flat = [(cid, nome) for itens in agrupado.values() for cid, nome in itens]
    rotulo_por_id = {cid: nome for cid, nome in opcoes_flat}
    rotulo_por_id_com_area = {
        cid: f"{nome}  ({base.area_competencia(cid)})" for cid, nome in opcoes_flat
    }

    st.session_state.dominadas = st.multiselect(
        "Domino e uso em projetos reais (nivel 3)",
        options=list(rotulo_por_id),
        default=[c for c in st.session_state.dominadas if c in rotulo_por_id],
        format_func=lambda c: rotulo_por_id_com_area.get(c, c),
        placeholder="Selecione as competencias que voce domina",
    )

    restantes = [c for c in rotulo_por_id if c not in st.session_state.dominadas]
    st.session_state.basicas = st.multiselect(
        "Estudei o basico (nivel 2)",
        options=restantes,
        default=[c for c in st.session_state.basicas if c in restantes],
        format_func=lambda c: rotulo_por_id_com_area.get(c, c),
        placeholder="Selecione as competencias que voce conhece superficialmente",
    )

    total = len(st.session_state.dominadas) + len(st.session_state.basicas)
    st.caption(f"{total} de {len(rotulo_por_id)} competencias do catalogo marcadas.")

    _navegacao(proxima_habilitada=True, rotulo_proxima="Calcular compatibilidade")


def etapa_resultado(base) -> None:
    motor = obter_motor(base.regras["metadados"]["versao"])
    resultado = motor.avaliar(st.session_state.respostas, st.session_state.objetivos)
    top_n = int(base.configuracao.get("top_n", 3))
    top = resultado.top_n(top_n)

    saudacao = f", {st.session_state.nome}" if st.session_state.nome else ""
    st.subheader(f"Etapa 4 - Resultado{saudacao}")

    # ------------------------------------------------------------ Top N
    st.markdown("#### Ranking de compatibilidade")
    colunas = st.columns(top_n)
    for col, pos, r in zip(colunas, range(1, top_n + 1), top):
        with col:
            delta = f"CF {r.grau_confianca:+.2f} - {r.rotulo_confianca}"
            st.metric(label=f"{pos}. {r.nome}", value=f"{r.compatibilidade:.1f}%", delta=delta, delta_color="off")
            if r.penalidade_total > 0:
                st.caption(f"Penalidade aplicada: -{r.penalidade_total * 100:.0f}%")

    if resultado.perfil_ambiguo:
        st.warning(
            "**Perfil multivalente detectado.** As trilhas do topo ficaram muito proximas. "
            "O sistema nao vai forcar uma escolha unica: compare as justificativas abaixo."
        )

    abas = st.tabs(
        ["Visao geral", "Matriz completa", "Justificativas", "Analise de gaps", "Plano de acao", "Transparencia"]
    )

    # ------------------------------------------------------- aba visao geral
    with abas[0]:
        col_a, col_b = st.columns([1.15, 1])
        with col_a:
            st.markdown("##### Compatibilidade por trilha")
            st.plotly_chart(grafico_barras(resultado.ranking), width="stretch")
        with col_b:
            st.markdown("##### Seu perfil x exigencia das trilhas do Top 3")
            st.plotly_chart(grafico_radar(top, base), width="stretch")

        if resultado.diagnosticos:
            st.markdown("##### Diagnosticos do sistema")
            for diag in resultado.diagnosticos:
                st.info(diag)

    # ---------------------------------------------------- aba matriz completa
    with abas[1]:
        st.markdown("##### Matriz de compatibilidade (todas as 10 trilhas)")
        df = pd.DataFrame(resultado.como_tabela())
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "Compatibilidade (%)": st.column_config.ProgressColumn(
                    "Compatibilidade", format="%.1f%%", min_value=0, max_value=100
                ),
                "Cobertura (%)": st.column_config.NumberColumn(format="%.1f%%"),
                "Aderencia de perfil (%)": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
        st.download_button(
            "Baixar matriz em CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name="matriz_compatibilidade.csv",
            mime="text/csv",
        )
        with st.expander("O que significa cada coluna"):
            st.markdown(
                "- **Compatibilidade**: nota final, apos objetivos e penalidades.\n"
                "- **Cobertura**: quanto voce possui daquilo que a trilha exige.\n"
                "- **Aderencia de perfil**: similaridade entre a *forma* do seu perfil e a da trilha "
                "(resolve o caso de quem responde alto em tudo).\n"
                "- **Confianca (CF)**: fator de certeza combinado das regras SE-ENTAO disparadas, "
                "de -1 (contraindicado) a +1 (fortemente indicado).\n"
                "- **Penalidade**: reducao por conflito logico de perfil."
            )

    # ----------------------------------------------------- aba justificativas
    with abas[2]:
        for pos, r in enumerate(top, start=1):
            with st.expander(f"{pos}. {r.nome} - {r.compatibilidade:.1f}%", expanded=pos == 1):
                c1, c2, c3 = st.columns(3)
                c1.metric("Cobertura", f"{r.cobertura * 100:.0f}%")
                c2.metric("Aderencia de perfil", f"{r.forma * 100:.0f}%")
                c3.metric("Fator de certeza", f"{r.grau_confianca:+.2f}", r.rotulo_confianca, delta_color="off")

                detalhe = base.detalhe_trilha(r.id)
                st.write(detalhe.get("resumo", ""))

                if r.regras:
                    st.markdown("**Regras de certeza satisfeitas**")
                    for regra in r.regras:
                        sinal = "+" if regra.cf >= 0 else "-"
                        st.markdown(
                            f"- `{regra.id}` **CF {regra.cf:+.2f}** ({sinal}) {regra.justificativa}"
                        )
                else:
                    st.caption("Nenhuma regra de certeza foi satisfeita para esta trilha.")

                fatores = r.principais_fatores()
                if fatores:
                    st.markdown("**O que mais pesou a favor**")
                    for f in fatores:
                        st.markdown(
                            f"- {f.dimensao.replace('_', ' ').capitalize()}: sua nota {f.resposta}/5 "
                            f"com peso {f.peso:.2f} na trilha."
                        )

                contrarios = r.fatores_contrarios()
                if contrarios:
                    st.markdown("**Pontos de atencao**")
                    for f in contrarios:
                        st.markdown(
                            f"- {f.dimensao.replace('_', ' ').capitalize()}: nota {f.resposta}/5 "
                            f"para um requisito de peso {f.peso:.2f}."
                        )

                if r.penalidades:
                    st.markdown("**Penalidades por conflito de perfil**")
                    for p in r.penalidades:
                        st.markdown(f"- `{p.id}` **-{p.valor * 100:.0f}%**: {p.motivo}")

                if r.ajuste_objetivos:
                    st.caption(
                        f"Ajuste pelos seus objetivos de carreira: {r.ajuste_objetivos:+.1f} pontos."
                    )

    # -------------------------------------------------------- gaps e roadmap
    ids_top = [r.id for r in top]
    if st.session_state.trilha_escolhida not in ids_top:
        st.session_state.trilha_escolhida = ids_top[0]

    with abas[3]:
        st.markdown("##### Skill Gap Analysis")
        escolhida = st.radio(
            "Para qual trilha deseja analisar as lacunas?",
            ids_top,
            index=ids_top.index(st.session_state.trilha_escolhida),
            format_func=lambda i: f"{base.nome_trilha(i)} ({resultado.por_id(i).compatibilidade:.1f}%)",
            horizontal=True,
            key="radio_trilha_gap",
        )
        st.session_state.trilha_escolhida = escolhida

        niveis = _niveis_efetivos(base, escolhida)
        analise = analisar_gaps(
            base,
            escolhida,
            niveis_usuario=niveis,
            nivel_experiencia=st.session_state.nivel_experiencia,
            disponibilidade=st.session_state.disponibilidade,
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Prontidao para Junior", f"{analise.prontidao:.0f}%")
        c2.metric("Gaps em aberto", len(analise.gaps))
        c3.metric("Gaps essenciais", len(analise.gaps_essenciais))
        c4.metric("Prazo estimado", f"{analise.meses_estimados:.1f} meses")

        st.progress(min(1.0, analise.prontidao / 100), text=analise.classificacao)

        with st.expander("Ajustar meu nivel competencia por competencia", expanded=False):
            st.caption(
                "Escala 0 a 4: " + " | ".join(f"**{k}** {v}" for k, v in sorted(base.niveis_rotulos.items()))
            )
            for comp in base.detalhe_trilha(escolhida).get("competencias", []):
                comp_id = comp["id"]
                chave = f"nivel_{escolhida}_{comp_id}"
                atual = int(niveis.get(comp_id, 0))
                novo = st.slider(
                    f"{comp.get('nome_alternativo') or base.nome_competencia(comp_id)} "
                    f"(exigido: {comp.get('nivel_minimo_junior', 2)})",
                    0,
                    4,
                    value=atual,
                    key=chave,
                )
                st.session_state.niveis_ajustados[f"{escolhida}|{comp_id}"] = novo
            st.caption("Os valores acima substituem o inventario da etapa 3 apenas para esta trilha.")

        st.dataframe(
            pd.DataFrame(analise.como_tabela()),
            width="stretch",
            hide_index=True,
            column_config={
                "Seu nivel": st.column_config.ProgressColumn(
                    "Seu nivel", format="%d", min_value=0, max_value=4
                ),
                "Exigido (Junior)": st.column_config.NumberColumn(format="%d"),
            },
        )

        resumo = analise.resumo_por_criticidade()
        if resumo:
            st.markdown("##### Resumo por criticidade")
            st.dataframe(pd.DataFrame(resumo), width="stretch", hide_index=True)

        for aviso in analise.avisos:
            st.warning(aviso)

    # ------------------------------------------------------- aba plano de acao
    with abas[4]:
        escolhida = st.session_state.trilha_escolhida
        niveis = _niveis_efetivos(base, escolhida)
        analise = analisar_gaps(
            base,
            escolhida,
            niveis_usuario=niveis,
            nivel_experiencia=st.session_state.nivel_experiencia,
            disponibilidade=st.session_state.disponibilidade,
        )
        plano = gerar_plano(base, analise, resultado.por_id(escolhida))

        st.markdown(f"#### Plano de acao - {plano.trilha_nome}")
        st.write(plano.resumo)
        st.caption(f"**Dia a dia:** {plano.dia_a_dia}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Esforco restante", f"{plano.semanas_estimadas:.0f} semanas")
        c2.metric("Equivalente", f"{plano.meses_estimados:.1f} meses")
        c3.metric("Horas de estudo", f"{plano.horas_estimadas:.0f} h")

        if plano.nota_maturidade:
            st.info(plano.nota_maturidade)

        st.markdown("##### Comece por aqui")
        if plano.proximos_passos:
            for i, gap in enumerate(plano.proximos_passos, start=1):
                st.markdown(
                    f"**{i}. {gap.nome}** - do nivel {gap.nivel_atual} ao {gap.nivel_requerido} "
                    f"({gap.criticidade}, ~{gap.esforco_semanas} semanas)"
                )
        else:
            st.success(
                "Todos os requisitos de nivel Junior estao atendidos. "
                "Direcione o esforco para os diferenciais de nivel Pleno."
            )

        st.markdown("##### Roadmap por fase")
        for fase in plano.fases:
            titulo = f"{fase.titulo} - {fase.percentual:.0f}% concluido"
            with st.expander(titulo, expanded=not fase.concluida):
                for item in fase.itens:
                    if item.status == "Nao avaliado":
                        st.markdown(f"- {item.nome} *(diferencial de nivel Pleno)*")
                    elif item.concluido:
                        st.markdown(f"- ~~{item.nome}~~ (atendido)")
                    else:
                        st.markdown(
                            f"- **{item.nome}** - {item.status} "
                            f"(nivel {item.nivel_atual}/{item.nivel_requerido}, ~{item.semanas} semanas)"
                        )
                if fase.semanas:
                    st.caption(f"Esforco pendente nesta fase: ~{fase.semanas} semanas.")

        col_cert, col_proj = st.columns(2)
        with col_cert:
            st.markdown("##### Certificacoes recomendadas")
            for cert in plano.certificacoes:
                st.markdown(
                    f"- **{cert['nome']}**  \n"
                    f"<small>{cert['emissor']} - {cert['custo']} - {cert['quando']}</small>",
                    unsafe_allow_html=True,
                )
        with col_proj:
            st.markdown("##### Projetos para o portfolio no GitHub")
            for i, proj in enumerate(plano.projetos, start=1):
                st.markdown(
                    f"**{i}. {proj['titulo']}**  \n{proj['descricao']}  \n"
                    f"<small>*Diferencial:* {proj['diferencial']}</small>",
                    unsafe_allow_html=True,
                )

        if plano.armadilhas:
            st.markdown("##### Armadilhas a evitar")
            for item in plano.armadilhas:
                st.markdown(f"- {item}")

        if plano.faixa_salarial:
            st.markdown("##### Faixa salarial de referencia")
            st.dataframe(
                pd.DataFrame(
                    [{"Nivel": k.capitalize(), "Faixa": v} for k, v in plano.faixa_salarial.items()]
                ),
                width="stretch",
                hide_index=True,
            )
        if plano.maturidade_mercado:
            st.caption(f"**Mercado:** {plano.maturidade_mercado}")

        if plano.observacoes:
            st.markdown("##### Observacoes do sistema especialista")
            for obs in plano.observacoes:
                st.warning(obs)

        st.download_button(
            "Baixar plano de acao (Markdown)",
            data=plano.como_texto().encode("utf-8"),
            file_name=f"plano_acao_{plano.trilha_id.lower()}.md",
            mime="text/markdown",
            type="primary",
        )

    # ------------------------------------------------------ aba transparencia
    with abas[5]:
        st.markdown("##### Como a nota foi calculada")
        st.latex(
            r"\text{score} = \big(w_f \cdot \text{forma} + w_c \cdot \text{cobertura}\big)"
            r"\cdot (1 - f_o) + f_o \cdot \text{objetivos}"
        )
        st.latex(r"\text{compatibilidade} = \text{score} \cdot (1 - \text{penalidade}) \cdot 100")
        pesos = base.pesos_modelo
        st.caption(
            f"Parametros carregados do JSON: peso_forma={pesos.get('peso_forma')}, "
            f"peso_cobertura={pesos.get('peso_cobertura')}, "
            f"fator_objetivos={pesos.get('fator_objetivos')}, "
            f"penalidade_maxima={pesos.get('fator_penalidade_max')}."
        )

        alvo = st.selectbox(
            "Decompor a pontuacao de qual trilha?",
            [r.id for r in resultado.ranking],
            format_func=base.nome_trilha,
        )
        st.plotly_chart(grafico_decomposicao(resultado.por_id(alvo)), width="stretch")

        st.markdown("##### Respostas registradas")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Dimensao": d["id"],
                        "Pergunta": d["pergunta"],
                        "Sua resposta": resultado.respostas[d["id"]],
                        "Peso nesta trilha": d["pesos"].get(alvo, 0.0),
                    }
                    for d in base.dimensoes
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    st.divider()
    col_voltar, col_reiniciar = st.columns([1, 1])
    with col_voltar:
        if st.button("Voltar e revisar respostas", width="stretch"):
            ir_para(1)
    with col_reiniciar:
        if st.button("Comecar nova consulta", width="stretch"):
            for chave in list(st.session_state.keys()):
                del st.session_state[chave]
            st.rerun()


def _niveis_efetivos(base, id_trilha: str) -> Dict[str, int]:
    """Niveis do inventario da etapa 3, sobrepostos pelos ajustes manuais."""
    niveis = inferir_niveis(base, st.session_state.dominadas, st.session_state.basicas)
    prefixo = f"{id_trilha}|"
    for chave, valor in st.session_state.niveis_ajustados.items():
        if chave.startswith(prefixo):
            niveis[chave[len(prefixo):]] = int(valor)
    return niveis


# ----------------------------------------------------------------- navegacao
def _navegacao(proxima_habilitada: bool = True, rotulo_proxima: str = "Avancar") -> None:
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.session_state.etapa > 0:
            if st.button("Voltar", width="stretch"):
                ir_para(st.session_state.etapa - 1)
    with col3:
        if st.button(
            rotulo_proxima,
            width="stretch",
            type="primary",
            disabled=not proxima_habilitada,
        ):
            ir_para(st.session_state.etapa + 1)


def barra_lateral(base) -> None:
    with st.sidebar:
        st.markdown("### Sistema Especialista")
        st.caption("Consultor Avancado de Carreiras e Desenvolvimento Profissional em TI")
        st.markdown(
            f"**Base de conhecimento:** v{base.regras['metadados']['versao']}  \n"
            f"**Trilhas:** {len(base.ids_trilhas)}  \n"
            f"**Dimensoes avaliadas:** {len(base.dimensoes)}  \n"
            f"**Regras de certeza:** {len(base.regras_certeza)}  \n"
            f"**Regras de penalidade:** {len(base.regras_penalidade)}"
        )
        st.divider()

        st.markdown("#### Progresso")
        for i, nome in enumerate(NOMES_ETAPAS):
            atual = i == st.session_state.etapa
            concluida = i < st.session_state.etapa
            marca = "->" if atual else ("ok" if concluida else "  ")
            estilo = "**" if atual else ""
            st.markdown(f"`{marca}` {estilo}{nome}{estilo}")

        st.progress((st.session_state.etapa + 1) / TOTAL_ETAPAS)
        st.divider()

        if st.button("Reiniciar consulta", width="stretch"):
            for chave in list(st.session_state.keys()):
                del st.session_state[chave]
            st.rerun()

        if base.inconsistencias:
            with st.expander(f"Avisos da base ({len(base.inconsistencias)})"):
                for aviso in base.inconsistencias:
                    st.caption(f"- {aviso}")

        st.divider()
        st.caption(
            "UNIPAC Barbacena - Sistemas Especialistas.  \n"
            "Resultado indicativo, baseado em regras ponderadas e fatores de certeza. "
            "Nao substitui orientacao profissional de carreira."
        )


def main() -> None:
    try:
        base = obter_base()
    except ErroBaseConhecimento as exc:
        st.error(f"Falha ao carregar a base de conhecimento: {exc}")
        st.info("Verifique os arquivos em `dados/regras_carreiras.json` e `dados/trilhas_carreiras.json`.")
        st.stop()

    iniciar_estado(base)
    barra_lateral(base)

    st.title("Consultor Avancado de Carreiras em TI")
    st.caption(
        "Sistema especialista baseado em regras com pontuacao ponderada e tratamento de incerteza. "
        "Analisa seu perfil em 10 trilhas, calcula a compatibilidade percentual, identifica lacunas "
        "de competencias e gera um plano de acao individualizado."
    )

    etapas = [etapa_perfil, etapa_afinidades, etapa_objetivos, etapa_resultado]
    etapas[st.session_state.etapa](base)


if __name__ == "__main__":
    main()
