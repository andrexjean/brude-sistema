"""
BRUDE - Pipeline
Orquestra: Parser → Normalizer → Classifier → Database → Report
Interface simples: você aponta o arquivo, o pipeline faz o resto.
"""
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

from database import (
    get_connection, get_categorias, get_membro_id,
    inserir_transacoes, consolidado_mensal, parcelas_projetadas, DB_PATH
)
from normalizer import Normalizer
from classifier import Classifier


class Pipeline:
    """
    Orquestrador principal. Instancie uma vez e use para processar
    múltiplos arquivos.
    """

    def __init__(self):
        self.normalizer = Normalizer(str(DB_PATH))
        self.categorias = get_categorias()
        self.classifier = Classifier(self.categorias)

    # ── CONTRATO PÚBLICO (usado pelo app.py) ──────────────────
    def processar_fatura(self, file_path: str, membro: str, banco: str = "nubank") -> dict:
        """
        Função principal para uso pela interface.

        Retorna contrato padronizado:
        {
            "transacoes": [
                {
                    "data": str,
                    "descricao_original": str,
                    "descricao_norm": str,
                    "valor": float,
                    "categoria": str,
                    "confianca": float,
                    "parcela_atual": int | None,
                    "parcela_total": int | None
                }
            ],
            "resumo": {
                "NomeCategoria": {
                    "total": float,
                    "meta": float,
                    "status": "ok" | "atencao" | "critico",
                    "pct_meta": float | None
                }
            },
            "totais": {
                "geral": float,
                "inseridas": int,
                "duplicatas": int,
                "baixa_confianca": int
            },
            "erros": [str],
            "mes": str
        }
        """
        erros = []

        # 1. Parse
        try:
            resultado_interno = self.processar(file_path, membro, banco)
        except Exception as e:
            return {
                "transacoes": [], "resumo": {},
                "totais": {"geral": 0, "inseridas": 0, "duplicatas": 0, "baixa_confianca": 0},
                "erros": [f"Erro ao ler o arquivo: {str(e)}"],
                "mes": None
            }

        if resultado_interno.get("status") == "erro":
            return {
                "transacoes": [], "resumo": {},
                "totais": {"geral": 0, "inseridas": 0, "duplicatas": 0, "baixa_confianca": 0},
                "erros": [resultado_interno.get("msg", "Nenhuma transação encontrada")],
                "mes": None
            }

        # 2. Mapeia para contrato padronizado
        raw = resultado_interno.get("transacoes", [])
        cat_id_to_nome = {v: k for k, v in self.categorias.items()}

        transacoes_contrato = []
        for t in raw:
            cat_nome = cat_id_to_nome.get(t.get("categoria_id"), "Outros")
            transacoes_contrato.append({
                "data":               t.get("data", ""),
                "descricao_original": t.get("descricao_original", ""),
                "descricao_norm":     t.get("descricao_norm") or t.get("descricao_original", ""),
                "valor":              round(float(t.get("valor", 0)), 2),
                "categoria":          cat_nome,
                "confianca":          round(float(t.get("confianca", 0)), 2),
                "parcela_atual":      t.get("parcela_atual"),
                "parcela_total":      t.get("parcela_total"),
            })

        # 3. Mês de referência
        mes = next(
            (t.get("mes_referencia") for t in raw if t.get("mes_referencia")),
            None
        )

        # 4. Resumo por categoria (do banco, pós-inserção)
        resumo = {}
        if mes:
            try:
                consolidado = consolidado_mensal(mes)
                resumo = {
                    cat: {
                        "total":    round(v["total"], 2),
                        "meta":     v.get("meta", 0),
                        "status":   v.get("status", "ok"),
                        "pct_meta": round(v["pct_meta"], 1) if v.get("pct_meta") else None,
                        "por_membro": v.get("por_membro", {}),
                    }
                    for cat, v in consolidado.items()
                }
            except Exception as e:
                erros.append(f"Erro ao gerar resumo: {str(e)}")

        return {
            "transacoes": sorted(transacoes_contrato,
                                 key=lambda x: x["data"], reverse=True),
            "resumo":     resumo,
            "totais": {
                "geral":           round(sum(t["valor"] for t in transacoes_contrato), 2),
                "inseridas":       resultado_interno.get("inseridas", 0),
                "duplicatas":      resultado_interno.get("duplicatas", 0),
                "baixa_confianca": resultado_interno.get("baixa_conf", 0),
            },
            "erros": erros,
            "mes":   mes,
        }

    def processar(
        self,
        filepath: str,
        membro: str,
        banco: str,
        mes_referencia: Optional[str] = None
    ) -> dict:
        """
        Processa um arquivo (PDF ou CSV) do início ao fim.
        Método interno — use processar_fatura() na interface.
        """

        # 1. PARSE
        transacoes = self._parse(filepath, membro, banco, mes_referencia)
        if not transacoes:
            return {'status': 'erro', 'msg': 'Nenhuma transação encontrada'}

        # 2. RESOLVE membro_id
        membro_id = get_membro_id(membro)
        if not membro_id:
            print(f"⚠️  Membro '{membro}' não encontrado no banco")
            membro_id = 1  # fallback

        # 3. NORMALIZAÇÃO + CLASSIFICAÇÃO (em lote)
        print(f"🔄 Normalizando e classificando {len(transacoes)} transações...")
        for t in transacoes:
            t['membro_id'] = membro_id

            # Normaliza descrição
            desc_norm, cat_sug, conf_norm = self.normalizer.normalizar(
                t['descricao_original']
            )
            t['descricao_norm']     = desc_norm
            t['categoria_sugerida'] = cat_sug
            t['confianca_norm']     = conf_norm

        # Classifica lote
        transacoes = self.classifier.classificar_lote(transacoes)

        # 4. ARMAZENA
        inseridas, duplicatas = inserir_transacoes(transacoes)
        print(f"💾 Inseridas: {inseridas} | Duplicatas ignoradas: {duplicatas}")

        # 5. IDENTIFICA baixa confiança para revisão
        baixa_conf = self.classifier.itens_baixa_confianca(transacoes, threshold=0.5)
        if baixa_conf:
            print(f"⚠️  {len(baixa_conf)} itens com classificação incerta (revisar):")
            for t in baixa_conf[:5]:
                print(f"   → '{t['descricao_original']}' "
                      f"→ conf: {t['confianca']:.0%}")
            if len(baixa_conf) > 5:
                print(f"   ... e mais {len(baixa_conf)-5}")

        return {
            'status':      'ok',
            'arquivo':     Path(filepath).name,
            'inseridas':   inseridas,
            'duplicatas':  duplicatas,
            'baixa_conf':  len(baixa_conf),
            'transacoes':  transacoes,
        }

    def _parse(
        self,
        filepath: str,
        membro: str,
        banco: str,
        mes_referencia: Optional[str]
    ) -> list[dict]:
        banco = banco.lower()
        if banco == 'nubank':
            from nubank import parse_nubank
            return parse_nubank(filepath, membro, mes_referencia)
        elif banco == 'xp':
            from xp import parse_xp
            return parse_xp(filepath, membro, mes_referencia)
        else:
            raise ValueError(f"Banco não suportado: {banco}")

    def gerar_relatorio(self, mes: str) -> dict:
        """
        Gera relatório consolidado de um mês.
        mes: '2026-04'
        """
        print(f"\n📊 Gerando relatório — {mes}")

        consolidado = consolidado_mensal(mes)

        # Ordena por total decrescente
        cats_ordenadas = sorted(
            consolidado.items(),
            key=lambda x: x[1]['total'],
            reverse=True
        )

        # Totais
        total_geral = sum(v['total'] for v in consolidado.values())
        total_essencial = sum(
            v['total'] for v in consolidado.values()
            if v['tipo'] == 'essencial'
        )
        total_nao_essencial = total_geral - total_essencial

        # Parcelas projetadas próximo mês
        from datetime import date
        dt = datetime.strptime(mes, '%Y-%m')
        mes_prox = f"{dt.year}-{dt.month+1:02d}" if dt.month < 12 else f"{dt.year+1}-01"
        parcelas = parcelas_projetadas(mes_prox)
        total_parcelas = sum(p['valor'] for p in parcelas)

        # Score simples (0-100)
        # Componentes: taxa poupança, % essencial, uso de metas
        conn = get_connection()
        receita_row = conn.execute(
            "SELECT SUM(valor) as total FROM receitas WHERE mes = ?", (mes,)
        ).fetchone()
        conn.close()
        receita = receita_row['total'] if receita_row and receita_row['total'] else 15000

        taxa_poupanca = max(0, (receita - total_geral) / receita) if receita > 0 else 0
        pct_essencial = total_essencial / total_geral if total_geral > 0 else 1
        cats_acima_meta = sum(1 for v in consolidado.values()
                              if v['status'] == 'critico')
        score = self._calcular_score(taxa_poupanca, pct_essencial, cats_acima_meta)

        relatorio = {
            'mes':                 mes,
            'total_geral':         round(total_geral, 2),
            'total_essencial':     round(total_essencial, 2),
            'total_nao_essencial': round(total_nao_essencial, 2),
            'receita_estimada':    receita,
            'taxa_poupanca':       round(taxa_poupanca * 100, 1),
            'pct_essencial':       round(pct_essencial * 100, 1),
            'score':               score,
            'parcelas_mes_prox':   round(total_parcelas, 2),
            'categorias':          cats_ordenadas,
            'alertas':             self._gerar_alertas(consolidado, taxa_poupanca),
        }

        return relatorio

    def _calcular_score(
        self,
        taxa_poupanca: float,
        pct_essencial: float,
        cats_acima_meta: int
    ) -> int:
        """
        Score financeiro 0-100.

        Componentes e pesos:
        - Taxa de poupança (40pts): >30% = 40pts, >15% = 25pts, >0% = 10pts
        - % gasto essencial (30pts): <60% = 30pts, <75% = 20pts, <90% = 10pts
        - Categorias acima da meta (30pts): 0 = 30pts, penaliza 5pts cada

        Justificativa: taxa de poupança é o indicador mais crítico de saúde
        financeira, por isso tem maior peso.
        """
        score = 0

        # Taxa de poupança (40 pts)
        if taxa_poupanca >= 0.30:
            score += 40
        elif taxa_poupanca >= 0.20:
            score += 30
        elif taxa_poupanca >= 0.10:
            score += 20
        elif taxa_poupanca >= 0.0:
            score += 10

        # % essencial (30 pts)
        if pct_essencial <= 0.55:
            score += 30
        elif pct_essencial <= 0.70:
            score += 20
        elif pct_essencial <= 0.85:
            score += 10

        # Categorias acima da meta (30 pts)
        penalidade = min(cats_acima_meta * 5, 30)
        score += max(0, 30 - penalidade)

        return min(100, max(0, score))

    def _gerar_alertas(self, consolidado: dict, taxa_poupanca: float) -> list[str]:
        """Gera alertas acionáveis baseados nos dados do mês."""
        alertas = []

        # Categorias críticas
        criticos = [
            (cat, v) for cat, v in consolidado.items()
            if v['status'] == 'critico'
        ]
        for cat, v in sorted(criticos, key=lambda x: -x[1]['total'])[:3]:
            excesso = v['total'] - v['meta']
            pct = (v['total'] / v['meta'] - 1) * 100
            alertas.append(
                f"🔴 {cat}: R$ {v['total']:,.0f} "
                f"({pct:.0f}% acima da meta de R$ {v['meta']:,.0f}) "
                f"— cortar R$ {excesso:,.0f}/mês libera essa diferença"
            )

        # Taxa de poupança baixa
        if taxa_poupanca < 0.10:
            alertas.append(
                f"⚠️  Taxa de poupança: {taxa_poupanca*100:.1f}% "
                f"— abaixo do mínimo recomendado (10%)"
            )
        elif taxa_poupanca < 0:
            alertas.append(
                "🔴 Gastos superaram receitas este mês — "
                "comissão/reserva sendo consumida"
            )

        return alertas

    def imprimir_relatorio(self, relatorio: dict):
        """Imprime relatório formatado no terminal."""
        mes = relatorio['mes']
        print(f"\n{'═'*55}")
        print(f"  BRUDE FINANÇAS — {mes}")
        print(f"{'═'*55}")

        print(f"\n  SCORE FINANCEIRO: {relatorio['score']}/100")
        print(f"  Taxa de poupança: {relatorio['taxa_poupanca']}%")
        print(f"  % Gasto essencial: {relatorio['pct_essencial']}%")

        print(f"\n  TOTAIS")
        print(f"  Total gastos:       R$ {relatorio['total_geral']:>10,.2f}")
        print(f"  Essencial:          R$ {relatorio['total_essencial']:>10,.2f}")
        print(f"  Não essencial:      R$ {relatorio['total_nao_essencial']:>10,.2f}")
        print(f"  Parcelas prox. mês: R$ {relatorio['parcelas_mes_prox']:>10,.2f}")

        print(f"\n  GASTOS POR CATEGORIA")
        print(f"  {'Categoria':<22} {'Total':>10} {'Meta':>8} {'Status'}")
        print(f"  {'-'*52}")
        for cat, v in relatorio['categorias']:
            status = {'ok': '🟢', 'atencao': '🟡', 'critico': '🔴'}.get(v['status'], '—')
            meta_str = f"{v['meta']:>8,.0f}" if v['meta'] else '       —'
            print(f"  {cat:<22} {v['total']:>10,.2f} {meta_str} {status}")

        if relatorio['alertas']:
            print(f"\n  ALERTAS")
            for alerta in relatorio['alertas']:
                print(f"  {alerta}")

        print(f"\n{'═'*55}\n")

    def exportar_csv(self, relatorio: dict, output_dir: str = "output"):
        """Exporta consolidado do mês em CSV."""
        from pathlib import Path
        import csv

        output = Path(output_dir)
        output.mkdir(exist_ok=True)
        mes_safe = relatorio['mes'].replace('/', '-')
        filepath = output / f"consolidado_{mes_safe}.csv"

        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['Categoria', 'Total', 'Meta', 'Status',
                             'André', 'Bruna'])
            for cat, v in relatorio['categorias']:
                writer.writerow([
                    cat,
                    f"{v['total']:.2f}",
                    f"{v['meta']:.2f}" if v['meta'] else '',
                    v['status'],
                    f"{v['por_membro'].get('André', 0):.2f}",
                    f"{v['por_membro'].get('Bruna', 0):.2f}",
                ])

        print(f"📤 Exportado: {filepath}")
        return str(filepath)
