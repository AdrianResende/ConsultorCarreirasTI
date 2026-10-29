"""
Modulo de recomendacao: roadmap de estudos, certificacoes e portfolio.

Combina a trilha vencedora (motor de inferencia) com a analise de gaps para
produzir um plano de acao individualizado: o que estudar primeiro, em que
ordem, quais certificacoes buscar em cada momento e quais projetos colocar
no GitHub.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .base_conhecimento import BaseConhecimento
from .gaps import AnaliseGaps, GapCompetencia

PESO_ORDEM = {"essencial": 3.0, "importante": 2.0, "diferencial": 1.0}


@dataclass
class ItemRoadmap:
    competencia_id: str
    nome: str
    status: str                  # "Atendido" | "Reforcar" | "Comecar do zero" | "Nao avaliado"
    criticidade: str
    nivel_atual: int
    nivel_requerido: int
    semanas: float

    @property
    def concluido(self) -> bool:
        return self.status == "Atendido"


@dataclass
class FaseRoadmap:
    titulo: str
    itens: List[ItemRoadmap] = field(default_factory=list)

    @property
    def concluida(self) -> bool:
        avaliados = [i for i in self.itens if i.status != "Nao avaliado"]
        return bool(avaliados) and all(i.concluido for i in avaliados)

    @property
    def percentual(self) -> float:
        avaliados = [i for i in self.itens if i.status != "Nao avaliado"]
        if not avaliados:
            return 0.0
        return round(sum(1 for i in avaliados if i.concluido) / len(avaliados) * 100, 1)

    @property
    def semanas(self) -> float:
        return round(sum(i.semanas for i in self.itens if not i.concluido), 1)

    @property
    def pendentes(self) -> List[ItemRoadmap]:
        return [i for i in self.itens if not i.concluido]


@dataclass
class PlanoAcao:
    trilha_id: str
    trilha_nome: str
    resumo: str
    dia_a_dia: str
    prontidao: float
    classificacao: str
    fases: List[FaseRoadmap] = field(default_factory=list)
    proximos_passos: List[GapCompetencia] = field(default_factory=list)
    certificacoes: List[Dict[str, Any]] = field(default_factory=list)
    projetos: List[Dict[str, Any]] = field(default_factory=list)
    armadilhas: List[str] = field(default_factory=list)
    faixa_salarial: Dict[str, str] = field(default_factory=dict)
    maturidade_mercado: str = ""
    semanas_estimadas: float = 0.0
    meses_estimados: float = 0.0
    horas_estimadas: float = 0.0
    nota_maturidade: str = ""
    observacoes: List[str] = field(default_factory=list)

    @property
    def fase_atual(self) -> FaseRoadmap | None:
        for fase in self.fases:
            if not fase.concluida:
                return fase
        return self.fases[-1] if self.fases else None

    def como_texto(self) -> str:
        """Plano em Markdown, para download ou impressao."""
        linhas: List[str] = [
            f"# Plano de acao - {self.trilha_nome}",
            "",
            f"**O que e a trilha:** {self.resumo}",
            "",
            f"**Dia a dia:** {self.dia_a_dia}",
            "",
            f"**Prontidao atual para Junior:** {self.prontidao}% - {self.classificacao}",
            f"**Esforco restante estimado:** {self.semanas_estimadas} semanas "
            f"(~{self.meses_estimados} meses, ~{int(self.horas_estimadas)} horas de estudo)",
            "",
        ]
        if self.nota_maturidade:
            linhas += [f"> {self.nota_maturidade}", ""]

        linhas.append("## Proximos passos (comece por aqui)")
        linhas.append("")
        if self.proximos_passos:
            for i, gap in enumerate(self.proximos_passos, start=1):
                linhas.append(
                    f"{i}. **{gap.nome}** - nivel {gap.nivel_atual} de {gap.nivel_requerido} "
                    f"({gap.criticidade}, ~{gap.esforco_semanas} semanas)"
                )
        else:
            linhas.append("Todos os requisitos de nivel Junior estao atendidos. "
                          "Direcione o esforco para os diferenciais de nivel Pleno.")
        linhas.append("")

        linhas.append("## Roadmap por fase")
        linhas.append("")
        for fase in self.fases:
            marca = "[OK]" if fase.concluida else f"[{fase.percentual:.0f}%]"
            linhas.append(f"### {marca} {fase.titulo}")
            for item in fase.itens:
                caixa = "x" if item.concluido else " "
                extra = "" if item.concluido else f" - {item.status}"
                linhas.append(f"- [{caixa}] {item.nome}{extra}")
            linhas.append("")

        linhas.append("## Certificacoes recomendadas")
        linhas.append("")
        for cert in self.certificacoes:
            linhas.append(
                f"- **{cert['nome']}** ({cert['emissor']}, {cert['custo']}) - {cert['quando']}"
            )
        linhas.append("")

        linhas.append("## Projetos para o portfolio no GitHub")
        linhas.append("")
        for i, proj in enumerate(self.projetos, start=1):
            linhas.append(f"{i}. **{proj['titulo']}**")
            linhas.append(f"   - {proj['descricao']}")
            linhas.append(f"   - Diferencial: {proj['diferencial']}")
        linhas.append("")

        if self.armadilhas:
            linhas.append("## Armadilhas a evitar")
            linhas.append("")
            for item in self.armadilhas:
                linhas.append(f"- {item}")
            linhas.append("")

        if self.faixa_salarial:
            linhas.append("## Faixa salarial de referencia")
            linhas.append("")
            for nivel, faixa in self.faixa_salarial.items():
                linhas.append(f"- {nivel.capitalize()}: {faixa}")
            linhas.append("")

        if self.maturidade_mercado:
            linhas += ["## Mercado", "", self.maturidade_mercado, ""]

        if self.observacoes:
            linhas.append("## Observacoes do sistema especialista")
            linhas.append("")
            for obs in self.observacoes:
                linhas.append(f"- {obs}")
            linhas.append("")

        return "\n".join(linhas)


def _ordenar_certificacoes(certificacoes: List[Dict[str, Any]], prontidao: float) -> List[Dict[str, Any]]:
    """Para quem esta comecando, certificacao gratuita vem primeiro."""
    def chave(cert: Dict[str, Any]) -> tuple[int, str]:
        custo = str(cert.get("custo", "")).lower()
        gratuita = "gratuit" in custo or "freemium" in custo or "auditavel" in custo
        if prontidao < 50:
            return (0 if gratuita else 1, cert.get("nome", ""))
        return (1 if gratuita else 0, cert.get("nome", ""))

    return sorted(certificacoes, key=chave)


def gerar_plano(
    base: BaseConhecimento,
    analise: AnaliseGaps,
    resultado_trilha: Any | None = None,
    max_passos: int = 5,
) -> PlanoAcao:
    """Monta o plano de acao individualizado para a trilha analisada."""
    detalhe = base.detalhe_trilha(analise.trilha_id)
    por_id = {g.id: g for g in analise.todas}

    fases: List[FaseRoadmap] = []
    for fase_bruta in detalhe.get("roadmap", []):
        fase = FaseRoadmap(titulo=fase_bruta.get("fase", "Fase"))
        for comp_id in fase_bruta.get("itens", []):
            gap = por_id.get(comp_id)
            if gap is not None:
                fase.itens.append(
                    ItemRoadmap(
                        competencia_id=comp_id,
                        nome=gap.nome,
                        status=gap.status,
                        criticidade=gap.criticidade,
                        nivel_atual=gap.nivel_atual,
                        nivel_requerido=gap.nivel_requerido,
                        semanas=gap.esforco_semanas,
                    )
                )
            else:
                # Item de roadmap que nao e requisito Junior (diferencial de Pleno).
                fase.itens.append(
                    ItemRoadmap(
                        competencia_id=comp_id,
                        nome=base.nome_competencia(comp_id),
                        status="Nao avaliado",
                        criticidade="diferencial",
                        nivel_atual=0,
                        nivel_requerido=0,
                        semanas=0.0,
                    )
                )
        fases.append(fase)

    # Proximos passos: respeita a ordem das fases e, dentro delas, a prioridade.
    proximos: List[GapCompetencia] = []
    for fase in fases:
        pendentes = [por_id[i.competencia_id] for i in fase.pendentes if i.competencia_id in por_id]
        pendentes = [g for g in pendentes if not g.atendida]
        pendentes.sort(key=lambda g: (-g.prioridade, -PESO_ORDEM.get(g.criticidade, 1.0)))
        for gap in pendentes:
            if gap not in proximos:
                proximos.append(gap)
            if len(proximos) >= max_passos:
                break
        if len(proximos) >= max_passos:
            break

    # Gaps essenciais fora do roadmap explicito nao podem ficar de fora.
    if len(proximos) < max_passos:
        for gap in analise.gaps:
            if gap not in proximos and gap.criticidade == "essencial":
                proximos.append(gap)
            if len(proximos) >= max_passos:
                break

    observacoes: List[str] = list(analise.avisos)
    if resultado_trilha is not None:
        for penalidade in getattr(resultado_trilha, "penalidades", []):
            observacoes.append(f"Alerta de perfil ({penalidade.id}): {penalidade.motivo}")
        contrarias = getattr(resultado_trilha, "fatores_contrarios", lambda: [])()
        for fator in contrarias:
            if fator.peso >= 0.5 and fator.resposta <= 2:
                observacoes.append(
                    f"A trilha exige bastante '{fator.dimensao.replace('_', ' ')}', "
                    f"onde voce se avaliou com {fator.resposta} de 5. "
                    "Valide esse ponto antes de se comprometer com a trilha."
                )
        if getattr(resultado_trilha, "grau_confianca", 0) < 0:
            observacoes.append(
                "As regras de certeza contraindicam esta trilha para o seu perfil. "
                "Ela aparece no ranking pela pontuacao ponderada, mas considere as alternativas do Top 3."
            )

    return PlanoAcao(
        trilha_id=analise.trilha_id,
        trilha_nome=analise.trilha_nome,
        resumo=detalhe.get("resumo", ""),
        dia_a_dia=detalhe.get("dia_a_dia", ""),
        prontidao=analise.prontidao,
        classificacao=analise.classificacao,
        fases=fases,
        proximos_passos=proximos[:max_passos],
        certificacoes=_ordenar_certificacoes(detalhe.get("certificacoes", []), analise.prontidao),
        projetos=detalhe.get("projetos_portfolio", []),
        armadilhas=detalhe.get("armadilhas", []),
        faixa_salarial=detalhe.get("faixa_salarial", {}),
        maturidade_mercado=detalhe.get("maturidade_mercado", ""),
        semanas_estimadas=analise.semanas_estimadas,
        meses_estimados=analise.meses_estimados,
        horas_estimadas=analise.horas_estimadas,
        nota_maturidade=analise.nota_maturidade,
        observacoes=observacoes,
    )
