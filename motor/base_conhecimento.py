"""
Camada de acesso a Base de Conhecimento.

O conhecimento do dominio (perguntas, pesos, regras, trilhas, roadmaps) vive
exclusivamente nos arquivos JSON de ``dados/``. Este modulo apenas carrega,
valida e expoe esse conteudo -- nenhuma regra de carreira e escrita aqui.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ_PROJETO / "dados"

ARQUIVO_REGRAS = "regras_carreiras.json"
ARQUIVO_TRILHAS = "trilhas_carreiras.json"


class ErroBaseConhecimento(Exception):
    """Base de conhecimento ausente, mal formada ou inconsistente."""


@dataclass
class BaseConhecimento:
    """Fachada imutavel sobre os dois arquivos JSON da base."""

    regras: Dict[str, Any]
    detalhes: Dict[str, Any]
    inconsistencias: List[str] = field(default_factory=list)

    # ---------------------------------------------------------------- acesso
    @property
    def configuracao(self) -> Dict[str, Any]:
        return self.regras["configuracao"]

    @property
    def pesos_modelo(self) -> Dict[str, float]:
        return self.configuracao["pesos_modelo"]

    @property
    def escala(self) -> tuple[int, int]:
        return self.configuracao["escala_min"], self.configuracao["escala_max"]

    @property
    def dimensoes(self) -> List[Dict[str, Any]]:
        return self.regras["dimensoes"]

    @property
    def ids_dimensoes(self) -> List[str]:
        return [d["id"] for d in self.dimensoes]

    @property
    def trilhas(self) -> Dict[str, Dict[str, Any]]:
        return self.regras["trilhas"]

    @property
    def ids_trilhas(self) -> List[str]:
        return list(self.trilhas.keys())

    @property
    def regras_certeza(self) -> List[Dict[str, Any]]:
        return self.regras.get("regras_certeza", [])

    @property
    def regras_penalidade(self) -> List[Dict[str, Any]]:
        return self.regras.get("regras_penalidade", [])

    @property
    def objetivos(self) -> Dict[str, Any]:
        return self.regras.get("objetivos_carreira", {"opcoes": []})

    @property
    def niveis_experiencia(self) -> List[Dict[str, Any]]:
        return self.detalhes.get("niveis_experiencia", [])

    @property
    def disponibilidades(self) -> List[Dict[str, Any]]:
        return self.detalhes.get("disponibilidade_estudo", [])

    @property
    def catalogo(self) -> Dict[str, Dict[str, Any]]:
        """Catalogo principal somado as competencias auxiliares de roadmap."""
        unificado: Dict[str, Dict[str, Any]] = {}
        unificado.update(self.detalhes.get("catalogo_competencias", {}))
        unificado.update(self.detalhes.get("competencias_extra", {}))
        return unificado

    @property
    def niveis_rotulos(self) -> Dict[str, str]:
        return self.detalhes.get("metadados", {}).get("escala_nivel", {})

    def nome_trilha(self, id_trilha: str) -> str:
        return self.trilhas.get(id_trilha, {}).get("nome", id_trilha)

    def detalhe_trilha(self, id_trilha: str) -> Dict[str, Any]:
        detalhe = self.detalhes.get("trilhas", {}).get(id_trilha)
        if detalhe is None:
            raise ErroBaseConhecimento(
                f"Trilha '{id_trilha}' nao possui detalhamento em {ARQUIVO_TRILHAS}."
            )
        return detalhe

    def nome_competencia(self, id_comp: str) -> str:
        entrada = self.catalogo.get(id_comp)
        if entrada:
            return entrada["nome"]
        # Ultimo recurso: transforma o id em texto legivel.
        return id_comp.replace("_", " ").capitalize()

    def area_competencia(self, id_comp: str) -> str:
        return self.catalogo.get(id_comp, {}).get("area", "Outros")

    def competencias_por_area(self) -> Dict[str, List[tuple[str, str]]]:
        """Agrupa o catalogo por area, para montar o inventario na interface."""
        agrupado: Dict[str, List[tuple[str, str]]] = {}
        for id_comp, dados in self.detalhes.get("catalogo_competencias", {}).items():
            agrupado.setdefault(dados.get("area", "Outros"), []).append(
                (id_comp, dados["nome"])
            )
        for itens in agrupado.values():
            itens.sort(key=lambda par: par[1])
        return dict(sorted(agrupado.items()))


# -------------------------------------------------------------------- loader
def _ler_json(caminho: Path) -> Dict[str, Any]:
    if not caminho.exists():
        raise ErroBaseConhecimento(f"Arquivo da base de conhecimento nao encontrado: {caminho}")
    try:
        with caminho.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ErroBaseConhecimento(f"JSON invalido em {caminho.name}: {exc}") from exc


def _validar(regras: Dict[str, Any], detalhes: Dict[str, Any]) -> List[str]:
    """Verificacoes de integridade. Falhas estruturais levantam excecao;
    divergencias toleraveis sao devolvidas como avisos."""
    for chave in ("configuracao", "trilhas", "dimensoes"):
        if chave not in regras:
            raise ErroBaseConhecimento(f"Chave obrigatoria ausente em {ARQUIVO_REGRAS}: '{chave}'")

    ids_trilhas = set(regras["trilhas"])
    if not ids_trilhas:
        raise ErroBaseConhecimento("Nenhuma trilha declarada na base de conhecimento.")

    avisos: List[str] = []
    vistos: set[str] = set()

    for dim in regras["dimensoes"]:
        if "id" not in dim or "pesos" not in dim:
            raise ErroBaseConhecimento("Dimensao sem 'id' ou sem 'pesos' na base de regras.")
        if dim["id"] in vistos:
            raise ErroBaseConhecimento(f"Dimensao duplicada: {dim['id']}")
        vistos.add(dim["id"])

        faltantes = ids_trilhas - set(dim["pesos"])
        if faltantes:
            avisos.append(
                f"Dimensao '{dim['id']}' nao pontua as trilhas: {', '.join(sorted(faltantes))} (assumido 0.0)."
            )
        for trilha, peso in dim["pesos"].items():
            if trilha not in ids_trilhas:
                avisos.append(f"Dimensao '{dim['id']}' referencia trilha inexistente '{trilha}'.")
            if not -1.0 <= float(peso) <= 1.0:
                avisos.append(
                    f"Peso fora da faixa [-1, 1] em '{dim['id']}' -> '{trilha}': {peso}."
                )

    for regra in regras.get("regras_certeza", []):
        if regra.get("trilha") not in ids_trilhas:
            avisos.append(f"Regra de certeza {regra.get('id')} aponta trilha desconhecida.")
        for cond in regra.get("condicoes", []):
            if cond.get("dimensao") not in vistos:
                avisos.append(
                    f"Regra {regra.get('id')} usa dimensao inexistente '{cond.get('dimensao')}'."
                )

    for regra in regras.get("regras_penalidade", []):
        for trilha in regra.get("trilhas", []):
            if trilha not in ids_trilhas:
                avisos.append(f"Penalidade {regra.get('id')} aponta trilha desconhecida '{trilha}'.")

    detalhadas = set(detalhes.get("trilhas", {}))
    sem_detalhe = ids_trilhas - detalhadas
    if sem_detalhe:
        avisos.append(
            f"Trilhas sem detalhamento de roadmap: {', '.join(sorted(sem_detalhe))}."
        )

    catalogo = set(detalhes.get("catalogo_competencias", {})) | set(
        detalhes.get("competencias_extra", {})
    )
    for id_trilha, detalhe in detalhes.get("trilhas", {}).items():
        for comp in detalhe.get("competencias", []):
            if comp["id"] not in catalogo and "nome_alternativo" not in comp:
                avisos.append(
                    f"Competencia '{comp['id']}' da trilha {id_trilha} nao esta no catalogo."
                )
    return avisos


def carregar_base(dir_dados: Path | str | None = None) -> BaseConhecimento:
    """Carrega e valida a base de conhecimento a partir dos arquivos JSON."""
    base_dir = Path(dir_dados) if dir_dados else DIR_DADOS
    regras = _ler_json(base_dir / ARQUIVO_REGRAS)
    detalhes = _ler_json(base_dir / ARQUIVO_TRILHAS)

    # Competencias declaradas com nome alternativo entram no catalogo em tempo de carga.
    extra = detalhes.setdefault("competencias_extra", {})
    for detalhe in detalhes.get("trilhas", {}).values():
        for comp in detalhe.get("competencias", []):
            if "nome_alternativo" in comp and comp["id"] not in extra:
                extra[comp["id"]] = {"nome": comp["nome_alternativo"], "area": "Especifico"}

    avisos = _validar(regras, detalhes)
    return BaseConhecimento(regras=regras, detalhes=detalhes, inconsistencias=avisos)
