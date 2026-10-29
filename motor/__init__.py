"""
Sistema Especialista Inteligente para Mapeamento, Compatibilidade e
Trilha de Carreira em TI.

Pacote do motor de inferencia. A base de conhecimento (regras, pesos,
trilhas, roadmaps) e externa e vive em ``dados/*.json``.
"""
from .base_conhecimento import (
    BaseConhecimento,
    ErroBaseConhecimento,
    carregar_base,
)
from .gaps import AnaliseGaps, GapCompetencia, analisar_gaps, inferir_niveis
from .inferencia import (
    ContribuicaoDimensao,
    MotorInferencia,
    PenalidadeAplicada,
    RegraDisparada,
    ResultadoInferencia,
    ResultadoTrilha,
)
from .roadmap import FaseRoadmap, ItemRoadmap, PlanoAcao, gerar_plano

__version__ = "1.3.0"

__all__ = [
    "BaseConhecimento",
    "ErroBaseConhecimento",
    "carregar_base",
    "MotorInferencia",
    "ResultadoInferencia",
    "ResultadoTrilha",
    "ContribuicaoDimensao",
    "RegraDisparada",
    "PenalidadeAplicada",
    "AnaliseGaps",
    "GapCompetencia",
    "analisar_gaps",
    "inferir_niveis",
    "PlanoAcao",
    "FaseRoadmap",
    "ItemRoadmap",
    "gerar_plano",
    "__version__",
]
