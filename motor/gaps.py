"""
Modulo de Skill Gap Analysis.

Cruza o nivel declarado pelo usuario em cada competencia (escala 0-4) com o
nivel minimo exigido pela trilha para uma vaga Junior, produzindo:

* a lista de lacunas ordenada por prioridade;
* um indice de prontidao ponderado pela criticidade de cada competencia;
* a estimativa de esforco restante em semanas e horas, ajustada pela
  disponibilidade de estudo e pela maturidade profissional declarada.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping

from .base_conhecimento import BaseConhecimento

# Peso de cada criticidade no indice de prontidao.
PESO_CRITICIDADE: Dict[str, float] = {
    "essencial": 3.0,
    "importante": 2.0,
    "diferencial": 1.0,
}

NIVEL_MAXIMO = 4


@dataclass
class GapCompetencia:
    id: str
    nome: str
    area: str
    criticidade: str
    nivel_atual: int
    nivel_requerido: int
    semanas_estudo: int

    @property
    def gap(self) -> int:
        return max(0, self.nivel_requerido - self.nivel_atual)

    @property
    def atendida(self) -> bool:
        return self.gap == 0

    @property
    def fracao_faltante(self) -> float:
        if self.nivel_requerido <= 0:
            return 0.0
        return self.gap / self.nivel_requerido

    @property
    def esforco_semanas(self) -> float:
        """Semanas de estudo proporcionais ao tamanho da lacuna."""
        return round(self.semanas_estudo * self.fracao_faltante, 1)

    @property
    def prioridade(self) -> float:
        """Criticidade x tamanho da lacuna. Define a ordem de estudo."""
        return PESO_CRITICIDADE.get(self.criticidade, 1.0) * self.gap

    @property
    def status(self) -> str:
        if self.atendida:
            return "Atendido"
        if self.nivel_atual == 0:
            return "Comecar do zero"
        return "Reforcar"


@dataclass
class AnaliseGaps:
    trilha_id: str
    trilha_nome: str
    prontidao: float                 # 0-100
    gaps: List[GapCompetencia] = field(default_factory=list)
    atendidas: List[GapCompetencia] = field(default_factory=list)
    semanas_estimadas: float = 0.0
    horas_estimadas: float = 0.0
    meses_estimados: float = 0.0
    nota_maturidade: str = ""
    avisos: List[str] = field(default_factory=list)

    @property
    def todas(self) -> List[GapCompetencia]:
        return self.atendidas + self.gaps

    @property
    def gaps_essenciais(self) -> List[GapCompetencia]:
        return [g for g in self.gaps if g.criticidade == "essencial"]

    @property
    def classificacao(self) -> str:
        if self.prontidao >= 85:
            return "Pronto para se candidatar a vagas Junior"
        if self.prontidao >= 65:
            return "Quase pronto: foque nos gaps essenciais restantes"
        if self.prontidao >= 40:
            return "Em formacao: base parcial construida"
        if self.prontidao >= 15:
            return "Inicio de jornada: fundamentos em andamento"
        return "Ponto de partida: comece pela fase 1 do roadmap"

    def como_tabela(self) -> List[Dict[str, Any]]:
        return [
            {
                "Competencia": g.nome,
                "Area": g.area,
                "Criticidade": g.criticidade.capitalize(),
                "Seu nivel": g.nivel_atual,
                "Exigido (Junior)": g.nivel_requerido,
                "Gap": g.gap,
                "Status": g.status,
                "Esforco (semanas)": g.esforco_semanas,
            }
            for g in sorted(
                self.todas,
                key=lambda g: (-g.prioridade, -PESO_CRITICIDADE.get(g.criticidade, 1.0), g.nome),
            )
        ]

    def resumo_por_criticidade(self) -> List[Dict[str, Any]]:
        linhas = []
        for crit in ("essencial", "importante", "diferencial"):
            do_grupo = [g for g in self.todas if g.criticidade == crit]
            if not do_grupo:
                continue
            abertos = [g for g in do_grupo if not g.atendida]
            linhas.append(
                {
                    "Criticidade": crit.capitalize(),
                    "Total": len(do_grupo),
                    "Atendidas": len(do_grupo) - len(abertos),
                    "Em aberto": len(abertos),
                }
            )
        return linhas


def _fator_maturidade(base: BaseConhecimento, nivel_experiencia: str | None) -> tuple[float, str]:
    for nivel in base.niveis_experiencia:
        if nivel["id"] == nivel_experiencia:
            return float(nivel.get("fator_maturidade", 0.0)), nivel.get("nota", "")
    return 0.0, ""


def _disponibilidade(base: BaseConhecimento, id_disponibilidade: str | None) -> tuple[float, float]:
    """Retorna (horas_semanais, multiplicador_de_prazo)."""
    for disp in base.disponibilidades:
        if disp["id"] == id_disponibilidade:
            return float(disp.get("horas", 10)), float(disp.get("multiplicador_prazo", 1.0))
    return 10.0, 1.0


def analisar_gaps(
    base: BaseConhecimento,
    id_trilha: str,
    niveis_usuario: Mapping[str, int] | None = None,
    nivel_experiencia: str | None = None,
    disponibilidade: str | None = None,
) -> AnaliseGaps:
    """Executa a analise de lacunas de uma trilha para o perfil informado."""
    detalhe = base.detalhe_trilha(id_trilha)
    niveis_usuario = dict(niveis_usuario or {})

    gaps: List[GapCompetencia] = []
    atendidas: List[GapCompetencia] = []
    avisos: List[str] = []

    numerador = 0.0
    denominador = 0.0

    for comp in detalhe.get("competencias", []):
        comp_id = comp["id"]
        requerido = int(comp.get("nivel_minimo_junior", 2))
        atual = int(niveis_usuario.get(comp_id, 0))
        atual = max(0, min(NIVEL_MAXIMO, atual))

        item = GapCompetencia(
            id=comp_id,
            nome=comp.get("nome_alternativo") or base.nome_competencia(comp_id),
            area=base.area_competencia(comp_id),
            criticidade=comp.get("criticidade", "importante"),
            nivel_atual=atual,
            nivel_requerido=requerido,
            semanas_estudo=int(comp.get("semanas_estudo", 4)),
        )

        peso = PESO_CRITICIDADE.get(item.criticidade, 1.0)
        numerador += peso * min(atual, requerido)
        denominador += peso * requerido

        (atendidas if item.atendida else gaps).append(item)

    prontidao = (numerador / denominador * 100) if denominador > 0 else 0.0

    gaps.sort(key=lambda g: (-g.prioridade, -PESO_CRITICIDADE.get(g.criticidade, 1.0), g.nome))

    # ------------------------------------------------------- estimativa de prazo
    fator_mat, nota = _fator_maturidade(base, nivel_experiencia)
    horas_semana, multiplicador = _disponibilidade(base, disponibilidade)

    semanas_brutas = sum(g.esforco_semanas for g in gaps)
    # Quem ja atua em TI aproveita parte do caminho andado (ate 30% menos esforco).
    semanas = semanas_brutas * (1 - 0.30 * fator_mat) * multiplicador
    horas = semanas * horas_semana
    meses = semanas / 4.345 if semanas else 0.0

    if not detalhe.get("competencias"):
        avisos.append(f"A trilha {id_trilha} nao possui competencias cadastradas na base.")
    if prontidao >= 85 and gaps:
        avisos.append(
            "Prontidao alta com lacunas remanescentes: candidate-se em paralelo ao estudo, "
            "pois processos seletivos levam semanas."
        )
    if any(g.nivel_atual == 0 and g.criticidade == "essencial" for g in gaps):
        avisos.append(
            "Existem competencias essenciais em nivel zero. Elas sao bloqueantes: "
            "nenhuma certificacao compensa a ausencia delas."
        )

    return AnaliseGaps(
        trilha_id=id_trilha,
        trilha_nome=detalhe.get("nome", base.nome_trilha(id_trilha)),
        prontidao=round(prontidao, 1),
        gaps=gaps,
        atendidas=atendidas,
        semanas_estimadas=round(semanas, 1),
        horas_estimadas=round(horas, 0),
        meses_estimados=round(meses, 1),
        nota_maturidade=nota,
        avisos=avisos,
    )


def inferir_niveis(
    base: BaseConhecimento,
    dominadas: List[str] | None = None,
    basicas: List[str] | None = None,
) -> Dict[str, int]:
    """Converte as duas selecoes do formulario em niveis na escala 0-4.

    'Domino e uso em projetos' -> 3; 'Conheco o basico' -> 2; o restante -> 0.
    """
    niveis = {comp_id: 0 for comp_id in base.catalogo}
    for comp_id in basicas or []:
        niveis[comp_id] = 2
    for comp_id in dominadas or []:
        niveis[comp_id] = 3
    return niveis
