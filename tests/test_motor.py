"""
Fase 5 - Testes de robustez e casos limite.

Executar:
    python -m unittest discover -s tests -v
ou, se o pytest estiver instalado:
    pytest -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor import (  # noqa: E402
    MotorInferencia,
    analisar_gaps,
    carregar_base,
    gerar_plano,
    inferir_niveis,
)

BASE = carregar_base()
MOTOR = MotorInferencia(BASE)


def perfil(padrao: int = 3, **ajustes: int) -> dict[str, int]:
    """Monta um conjunto completo de respostas com um valor padrao."""
    respostas = {dim: padrao for dim in BASE.ids_dimensoes}
    respostas.update(ajustes)
    return respostas


class TestBaseConhecimento(unittest.TestCase):
    def test_base_carrega_sem_inconsistencias(self):
        self.assertEqual(
            BASE.inconsistencias,
            [],
            msg="A base de conhecimento acusou inconsistencias:\n- "
            + "\n- ".join(BASE.inconsistencias),
        )

    def test_dez_trilhas_declaradas(self):
        self.assertEqual(len(BASE.ids_trilhas), 10)

    def test_toda_trilha_tem_detalhamento_completo(self):
        for id_trilha in BASE.ids_trilhas:
            detalhe = BASE.detalhe_trilha(id_trilha)
            with self.subTest(trilha=id_trilha):
                self.assertTrue(detalhe.get("competencias"), "sem competencias")
                self.assertTrue(detalhe.get("roadmap"), "sem roadmap")
                self.assertTrue(detalhe.get("certificacoes"), "sem certificacoes")
                self.assertTrue(detalhe.get("projetos_portfolio"), "sem projetos de portfolio")

    def test_todas_dimensoes_pontuam_todas_trilhas(self):
        for dim in BASE.dimensoes:
            with self.subTest(dimensao=dim["id"]):
                self.assertEqual(set(dim["pesos"]), set(BASE.ids_trilhas))

    def test_conhecimento_nao_esta_hardcoded_no_motor(self):
        """Alterar os pesos do JSON em memoria deve alterar o resultado do motor.

        Prova o requisito de desacoplamento: o pacote ``motor`` nao conhece
        nenhuma trilha nem nenhum peso -- todo o comportamento vem da base.
        """
        import copy

        # documentacao_processos=3 mantem a penalidade P04 desarmada, para que o
        # teste avalie o efeito dos pesos e nao o das regras de penalidade.
        respostas = perfil(
            2,
            infraestrutura_redes=5,
            automacao_scripting=5,
            pressao_plantao=5,
            visao_sistemica=4,
            documentacao_processos=3,
            design_visual=1,
        )
        original = MOTOR.avaliar(respostas)
        vencedora = original.top.id
        self.assertEqual(vencedora, "DEVOPS_SRE")

        # (a) Transplantar os pesos da vencedora para o QA deve elevar o QA ao
        #     mesmo patamar. A igualdade e exata porque as duas parcelas do
        #     modelo (cobertura e cosseno) sao invariantes a escala e dependem
        #     unicamente do vetor de pesos vindo do JSON.
        base_a = copy.deepcopy(BASE)
        for dim in base_a.dimensoes:
            dim["pesos"]["QA"] = dim["pesos"][vencedora]
        resultado_a = MotorInferencia(base_a).avaliar(respostas)
        qa = resultado_a.por_id("QA")
        self.assertGreater(qa.compatibilidade, original.por_id("QA").compatibilidade)
        self.assertAlmostEqual(
            qa.compatibilidade, resultado_a.por_id(vencedora).compatibilidade, places=6
        )
        self.assertIn("QA", [r.id for r in resultado_a.top_n(2)])

        # (b) Zerar os pesos da vencedora deve retira-la do Top 3.
        base_b = copy.deepcopy(BASE)
        for dim in base_b.dimensoes:
            dim["pesos"][vencedora] = 0.0
        resultado_b = MotorInferencia(base_b).avaliar(respostas)
        self.assertNotIn(vencedora, [r.id for r in resultado_b.top_n(3)])


class TestCasosLimite(unittest.TestCase):
    def test_respostas_neutras_nao_quebram_o_motor(self):
        resultado = MOTOR.avaliar(perfil(3))
        self.assertEqual(len(resultado.ranking), 10)
        self.assertTrue(
            any("mesmo valor" in d for d in resultado.diagnosticos),
            msg="esperado diagnostico de respostas sem variacao",
        )

    def test_tudo_cinco_ainda_discrimina_trilhas(self):
        """O caso classico do respondente entusiasmado: nao pode dar 100% em tudo."""
        resultado = MOTOR.avaliar(perfil(5))
        notas = {r.id: r.compatibilidade for r in resultado.ranking}
        self.assertGreater(
            max(notas.values()) - min(notas.values()),
            3.0,
            msg=f"sem discriminacao entre trilhas: {notas}",
        )

    def test_tudo_um_produz_notas_baixas(self):
        resultado = MOTOR.avaliar(perfil(1))
        self.assertLess(resultado.top.compatibilidade, 60.0)

    def test_compatibilidade_sempre_entre_zero_e_cem(self):
        for padrao in (1, 2, 3, 4, 5):
            resultado = MOTOR.avaliar(perfil(padrao))
            for r in resultado.ranking:
                with self.subTest(padrao=padrao, trilha=r.id):
                    self.assertGreaterEqual(r.compatibilidade, 0.0)
                    self.assertLessEqual(r.compatibilidade, 100.0)

    def test_respostas_ausentes_assumem_valor_neutro(self):
        resultado = MOTOR.avaliar({"logica_algoritmos": 5})
        self.assertEqual(len(resultado.respostas), len(BASE.ids_dimensoes))
        ausente = next(d for d in BASE.ids_dimensoes if d != "logica_algoritmos")
        self.assertEqual(resultado.respostas[ausente], 3)

    def test_valores_fora_da_escala_sao_truncados(self):
        resultado = MOTOR.avaliar(perfil(3, logica_algoritmos=99, design_visual=-40))
        self.assertEqual(resultado.respostas["logica_algoritmos"], 5)
        self.assertEqual(resultado.respostas["design_visual"], 1)

    def test_entrada_nao_numerica_nao_quebra(self):
        resultado = MOTOR.avaliar(perfil(3, logica_algoritmos="cinco", design_visual=None))
        self.assertEqual(resultado.respostas["logica_algoritmos"], 3)
        self.assertEqual(resultado.respostas["design_visual"], 3)

    def test_dicionario_vazio_nao_quebra(self):
        resultado = MOTOR.avaliar({})
        self.assertEqual(len(resultado.ranking), 10)

    def test_objetivos_desconhecidos_sao_ignorados(self):
        sem = MOTOR.avaliar(perfil(4), objetivos=[])
        com_lixo = MOTOR.avaliar(perfil(4), objetivos=["objetivo_inexistente"])
        self.assertEqual(
            [r.compatibilidade for r in sem.ranking],
            [r.compatibilidade for r in com_lixo.ranking],
        )


class TestPerfisCaracteristicos(unittest.TestCase):
    """Cada perfil arquetipico deve trazer sua trilha ao Top 3."""

    def _top_ids(self, respostas, n=3, objetivos=None):
        return [r.id for r in MOTOR.avaliar(respostas, objetivos).top_n(n)]

    def test_perfil_devops(self):
        respostas = perfil(
            2,
            infraestrutura_redes=5,
            automacao_scripting=5,
            pressao_plantao=5,
            visao_sistemica=4,
            logica_algoritmos=4,
            logica_servidor_apis=3,
            design_visual=1,
            gestao_lideranca=2,
        )
        self.assertIn("DEVOPS_SRE", self._top_ids(respostas))

    def test_perfil_cientista_de_dados(self):
        respostas = perfil(
            2,
            matematica_estatistica=5,
            pesquisa_experimentacao=5,
            banco_dados_modelagem=4,
            big_data_pipelines=4,
            comunicacao_negocio=4,
            infraestrutura_redes=1,
            design_visual=2,
            dispositivos_moveis=1,
        )
        self.assertIn("DATA_SCIENCE", self._top_ids(respostas))

    def test_perfil_frontend(self):
        respostas = perfil(
            2,
            design_visual=5,
            experiencia_usuario=5,
            dispositivos_moveis=3,
            logica_algoritmos=3,
            infraestrutura_redes=1,
            matematica_estatistica=2,
            logica_servidor_apis=2,
        )
        self.assertIn("FRONTEND_UX", self._top_ids(respostas))

    def test_perfil_backend(self):
        respostas = perfil(
            2,
            logica_servidor_apis=5,
            logica_algoritmos=5,
            banco_dados_modelagem=4,
            visao_sistemica=4,
            design_visual=2,
            gestao_lideranca=1,
            dispositivos_moveis=2,
        )
        self.assertIn("BACKEND", self._top_ids(respostas))

    def test_perfil_ciberseguranca(self):
        respostas = perfil(
            2,
            seguranca_investigacao=5,
            infraestrutura_redes=5,
            atencao_detalhes=5,
            documentacao_processos=4,
            pressao_plantao=4,
            design_visual=1,
            dispositivos_moveis=1,
        )
        self.assertIn("CIBERSEGURANCA", self._top_ids(respostas))

    def test_perfil_qa(self):
        respostas = perfil(
            2,
            atencao_detalhes=5,
            documentacao_processos=5,
            automacao_scripting=4,
            logica_algoritmos=3,
            infraestrutura_redes=2,
            design_visual=2,
            gestao_lideranca=2,
        )
        self.assertIn("QA", self._top_ids(respostas))

    def test_perfil_product_management(self):
        respostas = perfil(
            2,
            gestao_lideranca=5,
            comunicacao_negocio=5,
            experiencia_usuario=4,
            documentacao_processos=4,
            pesquisa_experimentacao=4,
            logica_servidor_apis=1,
            infraestrutura_redes=1,
            banco_dados_modelagem=2,
        )
        self.assertIn("PRODUCT_MGMT", self._top_ids(respostas))

    def test_perfil_engenheiro_de_dados(self):
        respostas = perfil(
            2,
            big_data_pipelines=5,
            banco_dados_modelagem=5,
            automacao_scripting=4,
            infraestrutura_redes=4,
            visao_sistemica=4,
            design_visual=1,
            gestao_lideranca=2,
            matematica_estatistica=3,
        )
        self.assertIn("DATA_ENG", self._top_ids(respostas))

    def test_perfil_mobile(self):
        respostas = perfil(
            2,
            dispositivos_moveis=5,
            experiencia_usuario=4,
            design_visual=4,
            logica_algoritmos=4,
            logica_servidor_apis=3,
            infraestrutura_redes=1,
            gestao_lideranca=1,
        )
        self.assertIn("MOBILE", self._top_ids(respostas))

    def test_perfil_cloud_architecture(self):
        respostas = perfil(
            2,
            visao_sistemica=5,
            infraestrutura_redes=5,
            comunicacao_negocio=4,
            documentacao_processos=4,
            gestao_lideranca=4,
            seguranca_investigacao=4,
            design_visual=1,
            dispositivos_moveis=1,
        )
        self.assertIn("CLOUD_ARCH", self._top_ids(respostas))


class TestAmbiguidadeEEmpates(unittest.TestCase):
    def test_perfil_ambiguo_dados_e_web_e_sinalizado(self):
        """Alguem que gosta igualmente de dados e de web deve receber aviso."""
        respostas = perfil(
            3,
            matematica_estatistica=5,
            banco_dados_modelagem=5,
            big_data_pipelines=4,
            design_visual=5,
            experiencia_usuario=5,
            logica_algoritmos=4,
            logica_servidor_apis=4,
        )
        resultado = MOTOR.avaliar(respostas)
        self.assertTrue(
            resultado.perfil_ambiguo or resultado.empates,
            msg="esperado empate parcial ou sinalizacao de perfil multivalente",
        )
        self.assertTrue(resultado.diagnosticos)

    def test_empate_gera_justificativa_textual(self):
        respostas = perfil(4, design_visual=4, matematica_estatistica=4)
        resultado = MOTOR.avaliar(respostas)
        for a, b, delta in resultado.empates:
            with self.subTest(par=(a, b)):
                self.assertLessEqual(delta, BASE.configuracao["limiar_empate"])
        if resultado.empates:
            self.assertTrue(any("Empate parcial" in d for d in resultado.diagnosticos))

    def test_ranking_ordenado_de_forma_decrescente(self):
        resultado = MOTOR.avaliar(perfil(3, logica_algoritmos=5, design_visual=1))
        notas = [r.compatibilidade for r in resultado.ranking]
        self.assertEqual(notas, sorted(notas, reverse=True))


class TestFatoresDeCerteza(unittest.TestCase):
    def test_regra_positiva_eleva_a_confianca(self):
        respostas = perfil(3, matematica_estatistica=5, pesquisa_experimentacao=5)
        ds = MOTOR.avaliar(respostas).por_id("DATA_SCIENCE")
        self.assertGreater(ds.grau_confianca, 0.5)
        self.assertTrue(any(r.id == "R01" for r in ds.regras))

    def test_contraindicacao_produz_confianca_negativa(self):
        respostas = perfil(3, matematica_estatistica=1, pesquisa_experimentacao=1)
        ds = MOTOR.avaliar(respostas).por_id("DATA_SCIENCE")
        self.assertLess(ds.grau_confianca, 0.0)
        self.assertEqual(ds.rotulo_confianca, "Contraindicado pelas regras")

    def test_cf_permanece_no_intervalo_valido(self):
        for padrao in (1, 2, 3, 4, 5):
            resultado = MOTOR.avaliar(perfil(padrao))
            for r in resultado.ranking:
                with self.subTest(padrao=padrao, trilha=r.id):
                    self.assertGreaterEqual(r.grau_confianca, -1.0)
                    self.assertLessEqual(r.grau_confianca, 1.0)

    def test_combinacao_mycin_de_cfs_positivos(self):
        combinado = MOTOR._combinar_cf(0.6, 0.5)
        self.assertAlmostEqual(combinado, 0.8, places=6)

    def test_combinacao_mycin_de_cfs_negativos(self):
        combinado = MOTOR._combinar_cf(-0.6, -0.5)
        self.assertAlmostEqual(combinado, -0.8, places=6)

    def test_combinacao_mycin_de_sinais_opostos(self):
        combinado = MOTOR._combinar_cf(0.8, -0.5)
        self.assertAlmostEqual(combinado, (0.8 - 0.5) / (1 - 0.5), places=6)

    def test_combinacao_mycin_de_cfs_opostos_e_iguais_se_anula(self):
        self.assertAlmostEqual(MOTOR._combinar_cf(1.0, -1.0), 0.0, places=6)


class TestPenalidades(unittest.TestCase):
    def test_perfil_de_gestao_penaliza_devops(self):
        respostas = perfil(
            3,
            gestao_lideranca=5,
            infraestrutura_redes=1,
            automacao_scripting=1,
        )
        devops = MOTOR.avaliar(respostas).por_id("DEVOPS_SRE")
        self.assertGreater(devops.penalidade_total, 0.0)
        self.assertTrue(any(p.id == "P01" for p in devops.penalidades))

    def test_aversao_a_codigo_penaliza_trilhas_de_engenharia(self):
        respostas = perfil(3, logica_algoritmos=1, logica_servidor_apis=1)
        resultado = MOTOR.avaliar(respostas)
        for id_trilha in ("BACKEND", "DATA_ENG", "MOBILE"):
            with self.subTest(trilha=id_trilha):
                self.assertGreater(resultado.por_id(id_trilha).penalidade_total, 0.0)

    def test_penalidade_respeita_o_teto_configurado(self):
        respostas = perfil(1, gestao_lideranca=5)
        teto = BASE.pesos_modelo["fator_penalidade_max"]
        for r in MOTOR.avaliar(respostas).ranking:
            with self.subTest(trilha=r.id):
                self.assertLessEqual(r.penalidade_total, teto + 1e-9)

    def test_penalidade_reduz_a_nota_final(self):
        base_respostas = perfil(3, dispositivos_moveis=3)
        penalizado = perfil(3, dispositivos_moveis=1)
        sem = MOTOR.avaliar(base_respostas).por_id("MOBILE")
        com = MOTOR.avaliar(penalizado).por_id("MOBILE")
        self.assertGreater(com.penalidade_total, sem.penalidade_total)
        self.assertLess(com.compatibilidade, sem.compatibilidade)


class TestObjetivosDeCarreira(unittest.TestCase):
    def test_objetivo_desloca_o_ranking_na_direcao_esperada(self):
        respostas = perfil(3)
        sem = MOTOR.avaliar(respostas).por_id("QA").compatibilidade
        com = MOTOR.avaliar(respostas, objetivos=["primeira_vaga_rapida"]).por_id("QA").compatibilidade
        self.assertGreater(com, sem)

    def test_ajuste_por_objetivos_tem_influencia_limitada(self):
        respostas = perfil(3)
        sem = MOTOR.avaliar(respostas)
        com = MOTOR.avaliar(respostas, objetivos=["salario_rapido", "estabilidade"])
        for r in com.ranking:
            with self.subTest(trilha=r.id):
                delta = abs(r.compatibilidade - sem.por_id(r.id).compatibilidade)
                self.assertLessEqual(delta, 13.0)

    def test_objetivo_registra_o_ajuste_aplicado(self):
        resultado = MOTOR.avaliar(perfil(3), objetivos=["lideranca_futura"])
        pm = resultado.por_id("PRODUCT_MGMT")
        self.assertNotEqual(pm.ajuste_objetivos, 0.0)


class TestAnaliseDeGaps(unittest.TestCase):
    def test_sem_conhecimento_a_prontidao_e_zero(self):
        analise = analisar_gaps(BASE, "BACKEND", niveis_usuario={})
        self.assertEqual(analise.prontidao, 0.0)
        self.assertEqual(analise.atendidas, [])
        self.assertTrue(analise.gaps)

    def test_conhecimento_total_zera_os_gaps(self):
        detalhe = BASE.detalhe_trilha("QA")
        niveis = {c["id"]: 4 for c in detalhe["competencias"]}
        analise = analisar_gaps(BASE, "QA", niveis_usuario=niveis)
        self.assertEqual(analise.gaps, [])
        self.assertEqual(analise.prontidao, 100.0)
        self.assertEqual(analise.semanas_estimadas, 0.0)
        self.assertIn("Pronto", analise.classificacao)

    def test_prontidao_sempre_entre_zero_e_cem(self):
        for id_trilha in BASE.ids_trilhas:
            for nivel in (0, 1, 2, 3, 4):
                niveis = {c: nivel for c in BASE.catalogo}
                analise = analisar_gaps(BASE, id_trilha, niveis_usuario=niveis)
                with self.subTest(trilha=id_trilha, nivel=nivel):
                    self.assertGreaterEqual(analise.prontidao, 0.0)
                    self.assertLessEqual(analise.prontidao, 100.0)

    def test_gaps_ordenados_por_prioridade(self):
        analise = analisar_gaps(BASE, "DATA_ENG", niveis_usuario={})
        prioridades = [g.prioridade for g in analise.gaps]
        self.assertEqual(prioridades, sorted(prioridades, reverse=True))

    def test_nivel_acima_do_exigido_nao_inflaciona_a_prontidao(self):
        detalhe = BASE.detalhe_trilha("QA")
        exato = {c["id"]: c["nivel_minimo_junior"] for c in detalhe["competencias"]}
        acima = {c["id"]: 4 for c in detalhe["competencias"]}
        self.assertEqual(
            analisar_gaps(BASE, "QA", niveis_usuario=exato).prontidao,
            analisar_gaps(BASE, "QA", niveis_usuario=acima).prontidao,
        )

    def test_maturidade_e_disponibilidade_afetam_o_prazo(self):
        comum = dict(niveis_usuario={}, disponibilidade="11_20h")
        iniciante = analisar_gaps(BASE, "BACKEND", nivel_experiencia="zero", **comum)
        atuando = analisar_gaps(BASE, "BACKEND", nivel_experiencia="junior_atuando", **comum)
        self.assertLess(atuando.semanas_estimadas, iniciante.semanas_estimadas)

        pouco_tempo = analisar_gaps(
            BASE, "BACKEND", niveis_usuario={}, nivel_experiencia="zero", disponibilidade="ate_5h"
        )
        muito_tempo = analisar_gaps(
            BASE, "BACKEND", niveis_usuario={}, nivel_experiencia="zero", disponibilidade="mais_20h"
        )
        self.assertGreater(pouco_tempo.semanas_estimadas, muito_tempo.semanas_estimadas)

    def test_inferir_niveis_traduz_o_inventario(self):
        niveis = inferir_niveis(BASE, dominadas=["sql"], basicas=["git", "docker"])
        self.assertEqual(niveis["sql"], 3)
        self.assertEqual(niveis["git"], 2)
        self.assertEqual(niveis["docker"], 2)
        self.assertEqual(niveis["kubernetes"], 0)

    def test_tabela_de_gaps_cobre_todas_as_competencias(self):
        analise = analisar_gaps(BASE, "CLOUD_ARCH", niveis_usuario={"cloud_basico": 3})
        detalhe = BASE.detalhe_trilha("CLOUD_ARCH")
        self.assertEqual(len(analise.como_tabela()), len(detalhe["competencias"]))


class TestPlanoDeAcao(unittest.TestCase):
    def test_plano_gerado_para_todas_as_trilhas(self):
        for id_trilha in BASE.ids_trilhas:
            analise = analisar_gaps(BASE, id_trilha, niveis_usuario={})
            plano = gerar_plano(BASE, analise)
            with self.subTest(trilha=id_trilha):
                self.assertTrue(plano.fases)
                self.assertTrue(plano.proximos_passos)
                self.assertTrue(plano.certificacoes)
                self.assertTrue(plano.projetos)
                self.assertIn("Plano de acao", plano.como_texto())

    def test_proximos_passos_priorizam_a_primeira_fase(self):
        analise = analisar_gaps(BASE, "BACKEND", niveis_usuario={})
        plano = gerar_plano(BASE, analise)
        itens_fase_1 = {i.competencia_id for i in plano.fases[0].itens}
        self.assertIn(plano.proximos_passos[0].id, itens_fase_1)

    def test_perfil_pronto_nao_recebe_proximos_passos(self):
        detalhe = BASE.detalhe_trilha("QA")
        niveis = {c["id"]: 4 for c in detalhe["competencias"]}
        plano = gerar_plano(BASE, analisar_gaps(BASE, "QA", niveis_usuario=niveis))
        self.assertEqual(plano.proximos_passos, [])
        self.assertTrue(plano.fases[0].concluida)

    def test_fase_marca_itens_ja_atendidos(self):
        analise = analisar_gaps(BASE, "BACKEND", niveis_usuario={"logica_prog": 4, "git": 4, "sql": 4})
        plano = gerar_plano(BASE, analise)
        self.assertTrue(plano.fases[0].concluida)
        self.assertEqual(plano.fase_atual.titulo, plano.fases[1].titulo)

    def test_certificacao_gratuita_vem_primeiro_para_iniciante(self):
        plano = gerar_plano(BASE, analisar_gaps(BASE, "CIBERSEGURANCA", niveis_usuario={}))
        primeira = plano.certificacoes[0]["custo"].lower()
        self.assertTrue(
            "gratuit" in primeira or "freemium" in primeira or "subsidiado" in primeira,
            msg=f"primeira certificacao sugerida foi '{plano.certificacoes[0]['nome']}'",
        )

    def test_plano_incorpora_alertas_do_resultado(self):
        respostas = perfil(3, gestao_lideranca=5, infraestrutura_redes=1, automacao_scripting=1)
        resultado = MOTOR.avaliar(respostas)
        plano = gerar_plano(
            BASE,
            analisar_gaps(BASE, "DEVOPS_SRE", niveis_usuario={}),
            resultado.por_id("DEVOPS_SRE"),
        )
        self.assertTrue(any("Alerta de perfil" in obs for obs in plano.observacoes))


class TestIntegracaoFimAFim(unittest.TestCase):
    def test_jornada_completa_de_um_usuario(self):
        respostas = perfil(
            2,
            infraestrutura_redes=5,
            automacao_scripting=5,
            pressao_plantao=4,
            visao_sistemica=4,
            logica_algoritmos=4,
        )
        resultado = MOTOR.avaliar(respostas, objetivos=["salario_rapido", "remoto_internacional"])
        top = resultado.top

        niveis = inferir_niveis(BASE, dominadas=["linux_cli", "git"], basicas=["docker", "cloud_basico"])
        analise = analisar_gaps(
            BASE,
            top.id,
            niveis_usuario=niveis,
            nivel_experiencia="suporte_infra",
            disponibilidade="11_20h",
        )
        plano = gerar_plano(BASE, analise, top)

        self.assertGreater(top.compatibilidade, 0)
        self.assertGreater(analise.prontidao, 0)
        self.assertLess(analise.prontidao, 100)
        self.assertTrue(plano.proximos_passos)
        texto = plano.como_texto()
        self.assertIn(plano.trilha_nome, texto)
        self.assertIn("Roadmap por fase", texto)
        self.assertIn("portfolio", texto.lower())

    def test_tabelas_de_saida_sao_serializaveis(self):
        resultado = MOTOR.avaliar(perfil(4, design_visual=2))
        tabela = resultado.como_tabela()
        self.assertEqual(len(tabela), 10)
        self.assertEqual(tabela[0]["Posicao"], 1)
        analise = analisar_gaps(BASE, resultado.top.id, niveis_usuario={})
        self.assertTrue(all(isinstance(linha, dict) for linha in analise.como_tabela()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
