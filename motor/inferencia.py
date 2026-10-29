"""
Motor de Inferencia com pontuacao ponderada e tratamento de incerteza.

O calculo de compatibilidade combina tres mecanismos complementares:

1. COBERTURA ponderada -- quanto o usuario possui daquilo que a trilha exige.
   Soma ``peso * resposta_normalizada`` e reescala para [0, 1] considerando
   tambem os pesos negativos (afinidades que contraindicam a trilha).

2. FORMA do perfil -- similaridade de cosseno entre o vetor de respostas
   centrado na media do proprio usuario e o vetor de pesos da trilha. Esta
   parcela resolve o problema classico do respondente que marca 5 em tudo:
   a cobertura sozinha o aprovaria em todas as trilhas, enquanto a forma
   mede o *contraste relativo* entre suas afinidades.

3. FATORES DE CERTEZA (estilo MYCIN) -- regras SE-ENTAO com CF em [-1, 1],
   combinadas de forma incremental. Produzem o grau de confianca e as
   justificativas textuais, inclusive contraindicacoes (CF negativo).

Sobre esse resultado incidem ainda as regras de penalidade para perfis
conflitantes e um ajuste leve pelos objetivos de carreira declarados.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from .base_conhecimento import BaseConhecimento

OPERADORES = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


# ----------------------------------------------------------------- resultados
@dataclass
class ContribuicaoDimensao:
    dimensao: str
    pergunta: str
    resposta: int
    peso: float
    contribuicao: float

    @property
    def sentido(self) -> str:
        if self.contribuicao > 0.01:
            return "favorece"
        if self.contribuicao < -0.01:
            return "contraindica"
        return "neutro"


@dataclass
class RegraDisparada:
    id: str
    trilha: str
    cf: float
    justificativa: str
    descricao: str = ""


@dataclass
class PenalidadeAplicada:
    id: str
    valor: float
    motivo: str
    descricao: str = ""


@dataclass
class ResultadoTrilha:
    id: str
    nome: str
    compatibilidade: float            # 0-100, valor final exibido
    score_bruto: float                # 0-1, antes de objetivos e penalidades
    cobertura: float                  # 0-1
    forma: float                      # 0-1 (cosseno reescalado)
    grau_confianca: float             # -1..1, combinacao MYCIN dos CFs
    ajuste_objetivos: float           # delta aplicado em pontos percentuais
    penalidade_total: float           # 0-1
    regras: List[RegraDisparada] = field(default_factory=list)
    penalidades: List[PenalidadeAplicada] = field(default_factory=list)
    contribuicoes: List[ContribuicaoDimensao] = field(default_factory=list)

    @property
    def rotulo_confianca(self) -> str:
        cf = self.grau_confianca
        if cf >= 0.75:
            return "Muito alta"
        if cf >= 0.5:
            return "Alta"
        if cf >= 0.2:
            return "Moderada"
        if cf > -0.2:
            return "Baixa / inconclusiva"
        return "Contraindicado pelas regras"

    def principais_fatores(self, n: int = 4) -> List[ContribuicaoDimensao]:
        favoraveis = [c for c in self.contribuicoes if c.contribuicao > 0]
        return sorted(favoraveis, key=lambda c: c.contribuicao, reverse=True)[:n]

    def fatores_contrarios(self, n: int = 3) -> List[ContribuicaoDimensao]:
        """Dimensoes que pesam contra: peso negativo ou exigencia nao atendida."""
        contrarios = [
            c for c in self.contribuicoes if c.contribuicao < 0 or (c.peso >= 0.5 and c.resposta <= 2)
        ]
        return sorted(contrarios, key=lambda c: (c.contribuicao, -c.peso))[:n]


@dataclass
class ResultadoInferencia:
    ranking: List[ResultadoTrilha]
    diagnosticos: List[str] = field(default_factory=list)
    empates: List[tuple[str, str, float]] = field(default_factory=list)
    perfil_ambiguo: bool = False
    respostas: Dict[str, int] = field(default_factory=dict)

    @property
    def top(self) -> ResultadoTrilha:
        return self.ranking[0]

    def top_n(self, n: int = 3) -> List[ResultadoTrilha]:
        return self.ranking[:n]

    def por_id(self, id_trilha: str) -> ResultadoTrilha | None:
        return next((r for r in self.ranking if r.id == id_trilha), None)

    def como_tabela(self) -> List[Dict[str, Any]]:
        """Formato plano, pronto para Pandas/Streamlit."""
        return [
            {
                "Posicao": pos,
                "Trilha": r.nome,
                "Compatibilidade (%)": r.compatibilidade,
                "Cobertura (%)": round(r.cobertura * 100, 1),
                "Aderencia de perfil (%)": round(r.forma * 100, 1),
                "Confianca (CF)": round(r.grau_confianca, 2),
                "Confianca": r.rotulo_confianca,
                "Penalidade (%)": round(r.penalidade_total * 100, 1),
                "Regras disparadas": len(r.regras),
            }
            for pos, r in enumerate(self.ranking, start=1)
        ]


# ------------------------------------------------------------------- motor
class MotorInferencia:
    """Avalia um conjunto de respostas graduais contra a base de conhecimento."""

    def __init__(self, base: BaseConhecimento) -> None:
        self.base = base
        self.minimo, self.maximo = base.escala
        pesos = base.pesos_modelo
        self.peso_forma = float(pesos.get("peso_forma", 0.55))
        self.peso_cobertura = float(pesos.get("peso_cobertura", 0.45))
        self.penalidade_max = float(pesos.get("fator_penalidade_max", 0.3))
        self.fator_objetivos = float(pesos.get("fator_objetivos", 0.12))

        soma = self.peso_forma + self.peso_cobertura
        if soma <= 0:
            raise ValueError("peso_forma + peso_cobertura deve ser positivo.")
        self.peso_forma /= soma
        self.peso_cobertura /= soma

    # ------------------------------------------------------------ utilidades
    def _normalizar(self, resposta: float) -> float:
        amplitude = self.maximo - self.minimo
        if amplitude == 0:
            return 0.0
        return (float(resposta) - self.minimo) / amplitude

    def _sanear(self, respostas: Dict[str, Any]) -> Dict[str, int]:
        """Garante uma resposta valida para toda dimensao da base.

        Dimensoes ausentes recebem o ponto medio da escala (resposta neutra),
        o que equivale a dizer 'nao sei / indiferente' sem quebrar o calculo.
        """
        neutro = (self.minimo + self.maximo) / 2
        saneadas: Dict[str, int] = {}
        for dim_id in self.base.ids_dimensoes:
            bruto = respostas.get(dim_id, neutro)
            try:
                valor = float(bruto)
            except (TypeError, ValueError):
                valor = neutro
            valor = max(self.minimo, min(self.maximo, valor))
            saneadas[dim_id] = int(round(valor))
        return saneadas

    @staticmethod
    def _combinar_cf(atual: float, novo: float) -> float:
        """Combinacao incremental de fatores de certeza (MYCIN)."""
        if atual >= 0 and novo >= 0:
            return atual + novo * (1 - atual)
        if atual < 0 and novo < 0:
            return atual + novo * (1 + atual)
        denominador = 1 - min(abs(atual), abs(novo))
        if denominador <= 1e-9:
            return 0.0
        return (atual + novo) / denominador

    def _condicoes_satisfeitas(self, condicoes: Sequence[Dict[str, Any]], respostas: Dict[str, int]) -> bool:
        for cond in condicoes:
            dim = cond.get("dimensao")
            if dim not in respostas:
                return False
            operador = OPERADORES.get(cond.get("op", ">="))
            if operador is None:
                return False
            if not operador(respostas[dim], cond.get("valor", 0)):
                return False
        return True

    # ------------------------------------------------------------- avaliacao
    def avaliar(
        self,
        respostas: Dict[str, Any],
        objetivos: Sequence[str] | None = None,
    ) -> ResultadoInferencia:
        respostas = self._sanear(respostas)
        objetivos = list(objetivos or [])

        valores = [respostas[d] for d in self.base.ids_dimensoes]
        media = statistics.fmean(valores)
        centrados = {d: respostas[d] - media for d in self.base.ids_dimensoes}
        norma_usuario = math.sqrt(sum(v * v for v in centrados.values()))

        bonus_objetivos = self._bonus_objetivos(objetivos)

        resultados: List[ResultadoTrilha] = []
        for id_trilha in self.base.ids_trilhas:
            resultados.append(
                self._avaliar_trilha(
                    id_trilha=id_trilha,
                    respostas=respostas,
                    centrados=centrados,
                    norma_usuario=norma_usuario,
                    bonus_objetivos=bonus_objetivos,
                )
            )

        resultados.sort(key=lambda r: (r.compatibilidade, r.grau_confianca), reverse=True)

        diagnosticos, empates, ambiguo = self._diagnosticar(resultados, valores, respostas)
        return ResultadoInferencia(
            ranking=resultados,
            diagnosticos=diagnosticos,
            empates=empates,
            perfil_ambiguo=ambiguo,
            respostas=respostas,
        )

    def _bonus_objetivos(self, objetivos: Sequence[str]) -> Dict[str, float]:
        """Media dos bonus declarados para cada trilha, em [0, 1]."""
        if not objetivos:
            return {}
        opcoes = {o["id"]: o for o in self.base.objetivos.get("opcoes", [])}
        acumulado: Dict[str, List[float]] = {t: [] for t in self.base.ids_trilhas}
        encontrados = 0
        for obj_id in objetivos:
            opcao = opcoes.get(obj_id)
            if not opcao:
                continue
            encontrados += 1
            for trilha in self.base.ids_trilhas:
                acumulado[trilha].append(float(opcao.get("bonus", {}).get(trilha, 0.0)))
        if not encontrados:
            return {}
        return {t: statistics.fmean(v) if v else 0.0 for t, v in acumulado.items()}

    def _avaliar_trilha(
        self,
        id_trilha: str,
        respostas: Dict[str, int],
        centrados: Dict[str, float],
        norma_usuario: float,
        bonus_objetivos: Dict[str, float],
    ) -> ResultadoTrilha:
        soma_ponderada = 0.0
        max_possivel = 0.0
        min_possivel = 0.0
        produto_interno = 0.0
        norma_pesos = 0.0
        contribuicoes: List[ContribuicaoDimensao] = []

        for dim in self.base.dimensoes:
            dim_id = dim["id"]
            peso = float(dim["pesos"].get(id_trilha, 0.0))
            normalizada = self._normalizar(respostas[dim_id])

            contribuicao = peso * normalizada
            soma_ponderada += contribuicao
            max_possivel += max(peso, 0.0)
            min_possivel += min(peso, 0.0)

            produto_interno += peso * centrados[dim_id]
            norma_pesos += peso * peso

            contribuicoes.append(
                ContribuicaoDimensao(
                    dimensao=dim_id,
                    pergunta=dim["pergunta"],
                    resposta=respostas[dim_id],
                    peso=peso,
                    contribuicao=round(contribuicao, 4),
                )
            )

        amplitude = max_possivel - min_possivel
        cobertura = (soma_ponderada - min_possivel) / amplitude if amplitude > 1e-9 else 0.0
        cobertura = min(1.0, max(0.0, cobertura))

        norma_pesos = math.sqrt(norma_pesos)
        if norma_usuario < 1e-9 or norma_pesos < 1e-9:
            # Perfil sem variacao (ex.: tudo 3 ou tudo 5): a forma e inconclusiva.
            forma = 0.5
        else:
            cosseno = produto_interno / (norma_usuario * norma_pesos)
            forma = (max(-1.0, min(1.0, cosseno)) + 1.0) / 2.0

        score_bruto = self.peso_forma * forma + self.peso_cobertura * cobertura

        # Ajuste pelos objetivos de carreira (influencia limitada por projeto).
        score = score_bruto
        ajuste_objetivos = 0.0
        if bonus_objetivos:
            bonus = bonus_objetivos.get(id_trilha, 0.0)
            score = score_bruto * (1 - self.fator_objetivos) + self.fator_objetivos * bonus
            ajuste_objetivos = round((score - score_bruto) * 100, 1)

        regras = self._disparar_regras_certeza(id_trilha, respostas)
        confianca = 0.0
        for regra in regras:
            confianca = self._combinar_cf(confianca, regra.cf)

        penalidades = self._aplicar_penalidades(id_trilha, respostas)
        total_pen = min(self.penalidade_max, sum(p.valor for p in penalidades))
        score *= 1 - total_pen

        return ResultadoTrilha(
            id=id_trilha,
            nome=self.base.nome_trilha(id_trilha),
            compatibilidade=round(min(100.0, max(0.0, score * 100)), 1),
            score_bruto=round(score_bruto, 4),
            cobertura=round(cobertura, 4),
            forma=round(forma, 4),
            grau_confianca=round(confianca, 3),
            ajuste_objetivos=ajuste_objetivos,
            penalidade_total=round(total_pen, 4),
            regras=regras,
            penalidades=penalidades,
            contribuicoes=contribuicoes,
        )

    def _disparar_regras_certeza(self, id_trilha: str, respostas: Dict[str, int]) -> List[RegraDisparada]:
        disparadas: List[RegraDisparada] = []
        for regra in self.base.regras_certeza:
            if regra.get("trilha") != id_trilha:
                continue
            if self._condicoes_satisfeitas(regra.get("condicoes", []), respostas):
                disparadas.append(
                    RegraDisparada(
                        id=regra.get("id", "?"),
                        trilha=id_trilha,
                        cf=float(regra.get("cf", 0.0)),
                        justificativa=regra.get("justificativa", ""),
                        descricao=regra.get("descricao", ""),
                    )
                )
        # CFs mais fortes primeiro, para a interface mostrar o argumento principal.
        disparadas.sort(key=lambda r: abs(r.cf), reverse=True)
        return disparadas

    def _aplicar_penalidades(self, id_trilha: str, respostas: Dict[str, int]) -> List[PenalidadeAplicada]:
        aplicadas: List[PenalidadeAplicada] = []
        for regra in self.base.regras_penalidade:
            if id_trilha not in regra.get("trilhas", []):
                continue
            if self._condicoes_satisfeitas(regra.get("condicoes", []), respostas):
                aplicadas.append(
                    PenalidadeAplicada(
                        id=regra.get("id", "?"),
                        valor=float(regra.get("penalidade", 0.0)),
                        motivo=regra.get("motivo", ""),
                        descricao=regra.get("descricao", ""),
                    )
                )
        aplicadas.sort(key=lambda p: p.valor, reverse=True)
        return aplicadas

    # ---------------------------------------------------------- diagnosticos
    def _diagnosticar(
        self,
        ranking: List[ResultadoTrilha],
        valores: List[int],
        respostas: Dict[str, int],
    ) -> tuple[List[str], List[tuple[str, str, float]], bool]:
        cfg = self.base.configuracao
        limiar_empate = float(cfg.get("limiar_empate", 4.0))
        limiar_ambiguidade = float(cfg.get("limiar_ambiguidade_global", 6.0))
        top_n = int(cfg.get("top_n", 3))

        diagnosticos: List[str] = []
        empates: List[tuple[str, str, float]] = []

        janela = ranking[: top_n + 1]
        for i in range(len(janela)):
            for j in range(i + 1, len(janela)):
                delta = abs(janela[i].compatibilidade - janela[j].compatibilidade)
                if delta <= limiar_empate:
                    empates.append((janela[i].nome, janela[j].nome, round(delta, 1)))

        ambiguo = False
        if len(ranking) >= top_n:
            dispersao = ranking[0].compatibilidade - ranking[top_n - 1].compatibilidade
            ambiguo = dispersao < limiar_ambiguidade
            if ambiguo:
                diagnosticos.append(
                    f"Perfil multivalente: as {top_n} primeiras trilhas ficaram dentro de "
                    f"{dispersao:.1f} pontos. Ha mais de um caminho viavel, e a escolha deve "
                    "considerar seus objetivos e o mercado da sua regiao, nao apenas a pontuacao."
                )

        for a, b, delta in empates:
            diagnosticos.append(
                f"Empate parcial entre {a} e {b} (diferenca de {delta} pontos): trate as duas "
                "como equivalentes e use os fatores de confianca e as penalidades como criterio de desempate."
            )

        if len(set(valores)) == 1:
            diagnosticos.append(
                "Todas as respostas receberam o mesmo valor. Sem contraste entre as afinidades, "
                "a parcela de forma do modelo fica neutra e o ranking reflete apenas a cobertura "
                "bruta. Recomenda-se refazer o questionario diferenciando as notas."
            )
        else:
            desvio = statistics.pstdev(valores)
            if desvio < 0.6:
                diagnosticos.append(
                    f"Respostas pouco diferenciadas (desvio-padrao {desvio:.2f}). O ranking existe, "
                    "mas as diferencas entre trilhas sao pouco confiaveis."
                )
            if statistics.fmean(valores) >= 4.5:
                diagnosticos.append(
                    "Notas altas em quase todas as dimensoes. O modelo usou o contraste relativo "
                    "entre elas para discriminar as trilhas."
                )
            elif statistics.fmean(valores) <= 1.8:
                diagnosticos.append(
                    "Notas baixas em quase todas as dimensoes. As compatibilidades absolutas ficam "
                    "reduzidas; considere explorar a area antes de escolher uma trilha."
                )

        if ranking and ranking[0].grau_confianca <= 0.2:
            diagnosticos.append(
                "Nenhuma regra de certeza forte foi satisfeita para a trilha lider: o resultado vem "
                "da pontuacao ponderada e deve ser lido como indicativo, nao como conclusao."
            )

        penalizadas = [r.nome for r in ranking[:top_n] if r.penalidade_total > 0]
        if penalizadas:
            diagnosticos.append(
                "Trilhas do Top "
                f"{top_n} que receberam penalidade por conflito de perfil: {', '.join(penalizadas)}."
            )

        return diagnosticos, empates, ambiguo
