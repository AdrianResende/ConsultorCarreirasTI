"""
Testes da interface Streamlit usando o AppTest oficial.

Percorre as quatro etapas do wizard sem navegador, garantindo que nenhuma
tela levante excecao e que o resultado final seja efetivamente renderizado.

Executar:
    python -m unittest tests.test_app -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from streamlit.testing.v1 import AppTest  # noqa: E402

from motor import carregar_base  # noqa: E402

BASE = carregar_base()
APP = str(RAIZ / "app.py")
TIMEOUT = 120


def respostas_devops() -> dict[str, int]:
    respostas = {d: 2 for d in BASE.ids_dimensoes}
    respostas.update(
        infraestrutura_redes=5,
        automacao_scripting=5,
        pressao_plantao=4,
        visao_sistemica=4,
        logica_algoritmos=4,
        design_visual=1,
    )
    return respostas


def app_na_etapa(etapa: int, **estado) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state["etapa"] = etapa
    for chave, valor in estado.items():
        at.session_state[chave] = valor
    at.run()
    return at


class TestWizard(unittest.TestCase):
    def test_etapa_1_perfil_renderiza(self):
        at = app_na_etapa(0)
        self.assertFalse(at.exception, msg=str(at.exception))
        self.assertIn("Perfil pessoal", at.subheader[0].value)
        self.assertTrue(at.radio)       # situacao profissional
        self.assertTrue(at.selectbox)   # formacao

    def test_etapa_2_tem_um_slider_por_dimensao(self):
        at = app_na_etapa(1)
        self.assertFalse(at.exception, msg=str(at.exception))
        self.assertEqual(len(at.slider), len(BASE.dimensoes))

    def test_etapa_2_avisa_quando_nao_ha_variacao(self):
        at = app_na_etapa(1, respostas={d: 4 for d in BASE.ids_dimensoes})
        self.assertFalse(at.exception, msg=str(at.exception))
        self.assertTrue(
            any("mesmo valor" in w.value for w in at.warning),
            msg="esperado aviso de respostas sem variacao",
        )

    def test_etapa_3_lista_objetivos_e_inventario(self):
        at = app_na_etapa(2)
        self.assertFalse(at.exception, msg=str(at.exception))
        self.assertEqual(len(at.checkbox), len(BASE.objetivos["opcoes"]))
        self.assertEqual(len(at.multiselect), 2)

    def test_etapa_4_renderiza_o_resultado_completo(self):
        at = app_na_etapa(
            3,
            respostas=respostas_devops(),
            objetivos=["salario_rapido"],
            dominadas=["linux_cli", "git"],
            basicas=["docker", "cloud_basico"],
            nivel_experiencia="suporte_infra",
            disponibilidade="11_20h",
        )
        self.assertFalse(at.exception, msg=str(at.exception))

        # Tres metricas do Top 3 + metricas das abas de gaps e plano.
        rotulos = [m.label for m in at.metric]
        self.assertTrue(any("DevOps" in r for r in rotulos), msg=f"metricas: {rotulos}")
        self.assertTrue(any(r.startswith("1.") for r in rotulos))

        # Graficos de barras, radar e decomposicao. O AppTest nao tem wrapper
        # tipado para st.plotly_chart: ele aparece na arvore como UnknownElement.
        graficos = [e for e in at.main if type(e).__name__ == "UnknownElement"]
        self.assertGreaterEqual(len(graficos), 3, msg=f"graficos encontrados: {len(graficos)}")

        # Tabelas de matriz, gaps, resumo por criticidade e respostas registradas.
        self.assertGreaterEqual(len(at.dataframe), 3)

        # Downloads: CSV da matriz e plano em Markdown.
        self.assertGreaterEqual(len(at.get("download_button")), 2)

        # As seis abas da tela de resultado.
        self.assertEqual(len([e for e in at.main if type(e).__name__ == "Tab"]), 6)

    def test_etapa_4_funciona_sem_nenhum_conhecimento_declarado(self):
        at = app_na_etapa(3, respostas=respostas_devops(), objetivos=[], dominadas=[], basicas=[])
        self.assertFalse(at.exception, msg=str(at.exception))
        prontidao = next((m for m in at.metric if "Prontidao" in m.label), None)
        self.assertIsNotNone(prontidao)
        self.assertEqual(prontidao.value, "0%")

    def test_etapa_4_com_perfil_neutro_nao_quebra(self):
        at = app_na_etapa(3, respostas={d: 3 for d in BASE.ids_dimensoes})
        self.assertFalse(at.exception, msg=str(at.exception))
        self.assertTrue(at.info, msg="esperado diagnostico informativo na tela")

    def test_etapa_4_com_perfil_ambiguo_exibe_alerta(self):
        respostas = {d: 3 for d in BASE.ids_dimensoes}
        respostas.update(
            matematica_estatistica=5,
            banco_dados_modelagem=5,
            big_data_pipelines=4,
            design_visual=5,
            experiencia_usuario=5,
            logica_algoritmos=4,
            logica_servidor_apis=4,
        )
        at = app_na_etapa(3, respostas=respostas)
        self.assertFalse(at.exception, msg=str(at.exception))
        self.assertTrue(at.warning or at.info)

    def test_barra_lateral_mostra_o_resumo_da_base(self):
        at = app_na_etapa(0)
        texto = " ".join(m.value for m in at.sidebar.markdown)
        self.assertIn("Base de conhecimento", texto)
        self.assertIn(BASE.regras["metadados"]["versao"], texto)

    def test_navegacao_avanca_de_etapa(self):
        at = app_na_etapa(0)
        at.button(key=next(b.key for b in at.button if b.label == "Avancar")).click().run()
        self.assertFalse(at.exception, msg=str(at.exception))
        self.assertEqual(at.session_state["etapa"], 1)

    def test_slider_alterado_persiste_na_sessao(self):
        at = app_na_etapa(1)
        at.slider(key="slider_design_visual").set_value(5).run()
        self.assertFalse(at.exception, msg=str(at.exception))
        self.assertEqual(at.session_state["respostas"]["design_visual"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
