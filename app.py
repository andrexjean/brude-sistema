"""
BRUDE Financas — versão flat (todos os arquivos na raiz)
Como rodar: streamlit run app.py
"""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd

st.set_page_config(page_title="BRUDE Financas", page_icon="💰", layout="centered")

st.markdown("""
<style>
.block-container{max-width:800px;padding-top:2rem}
.stButton>button{width:100%;padding:14px;font-size:16px;font-weight:700;
  background:#6366f1;color:white;border:none;border-radius:8px;margin-top:8px}
.stButton>button:hover{background:#4f46e5}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def iniciar():
    from database import init_db
    init_db()
    from pipeline import Pipeline
    return Pipeline()

pipeline = iniciar()

def brl(v):
    try: return f"R$ {float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
    except: return "—"

def icon(s): return {"ok":"🟢","atencao":"🟡","critico":"🔴"}.get(s,"⚪")

# ── FORMULÁRIO ────────────────────────────────────────────────
st.markdown("## 💰 BRUDE Finanças")
st.markdown("Selecione o titular, faça upload da fatura e clique em **Processar**.")
st.markdown("---")

c1, c2 = st.columns(2)
with c1:
    membro = st.selectbox("👤 Titular", ["André", "Bruna"])
with c2:
    banco = st.selectbox("💳 Cartão", ["nubank","xp"],
                         format_func=lambda x: "Nubank" if x=="nubank" else "XP")

arquivo = st.file_uploader("📄 Fatura (PDF ou CSV)", type=["pdf","csv"],
    help="No app Nubank: Cartão → Fatura → Exportar → CSV")

if arquivo:
    st.caption(f"✅ {arquivo.name} · {arquivo.size/1024:.1f} KB")

st.markdown("&nbsp;")
processar = st.button("⚡  PROCESSAR", type="primary")

# ── PROCESSAMENTO ─────────────────────────────────────────────
if processar:
    if not arquivo:
        st.error("❌ Selecione um arquivo antes de processar.")
        st.stop()

    sufixo = Path(arquivo.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
        tmp.write(arquivo.read())
        tmp_path = tmp.name

    try:
        with st.spinner("⏳ Processando fatura..."):
            resultado = pipeline.processar_fatura(tmp_path, membro, banco)
    except Exception as e:
        st.error(f"❌ Erro inesperado: {e}")
        st.stop()
    finally:
        try: os.unlink(tmp_path)
        except: pass

    for err in resultado.get("erros", []):
        st.error(f"❌ {err}")

    trans  = resultado["transacoes"]
    resumo = resultado["resumo"]
    totais = resultado["totais"]

    if not trans:
        st.warning(
            "⚠️ Nenhuma transação encontrada.\n\n"
            "**Verifique:**\n"
            "- É a fatura do cartão (não extrato de conta)\n"
            "- No app Nubank: Cartão → Fatura → Exportar → **CSV**\n"
            "- O arquivo não está protegido por senha"
        )
        st.stop()

    st.success(
        f"✅ **{totais['inseridas']}** importadas · "
        f"{totais['duplicatas']} duplicatas ignoradas"
        + (f" · ⚠️ {totais['baixa_confianca']} revisar"
           if totais["baixa_confianca"] else "")
    )

    # ── TABELA ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(f"### 📋 Transações ({len(trans)})")

    df = pd.DataFrame([{
        "Data":       t["data"],
        "Descrição":  t["descricao_norm"][:45],
        "Categoria":  t["categoria"],
        "Valor":      t["valor"],
        "Parcela":    (f"{t['parcela_atual']}/{t['parcela_total']}"
                       if t["parcela_atual"] else "—"),
        "Confiança":  t["confianca"],
    } for t in trans])

    def fmt_conf(val):
        if val >= 0.8: return "color:#10b981"
        if val >= 0.5: return "color:#f59e0b"
        return "color:#ef4444"

    st.dataframe(
        df.style
          .applymap(fmt_conf, subset=["Confiança"])
          .format({"Valor": lambda x: brl(x),
                   "Confiança": lambda x: f"{x*100:.0f}%"}),
        use_container_width=True, hide_index=True,
        height=min(400, 36 + len(df)*35),
    )

    # ── RESUMO ────────────────────────────────────────────────
    if resumo:
        st.markdown("---")
        st.markdown("### 📊 Resumo por Categoria")

        cats = sorted(resumo.items(), key=lambda x: -x[1]["total"])

        for cat, v in cats:
            total  = v["total"]
            meta   = v.get("meta", 0)
            status = v.get("status", "ok")
            pct    = min(int(v.get("pct_meta") or 0), 100)
            cor    = ("#ef4444" if status=="critico"
                      else "#f59e0b" if status=="atencao"
                      else "#10b981")

            ca, cb = st.columns([3,1])
            with ca:
                meta_txt = (f" <span style='color:#64748b;font-size:11px'>"
                            f"meta {brl(meta)}</span>" if meta else "")
                st.markdown(f"**{icon(status)} {cat}**{meta_txt}",
                            unsafe_allow_html=True)
                st.markdown(
                    f"<div style='background:#1e293b;border-radius:4px;height:6px;"
                    f"margin-top:2px'><div style='background:{cor};width:{pct}%;"
                    f"height:100%;border-radius:4px'></div></div>",
                    unsafe_allow_html=True)
            with cb:
                st.markdown(
                    f"<div style='text-align:right;font-size:16px;font-weight:700;"
                    f"color:{cor};padding-top:4px'>{brl(total)}</div>",
                    unsafe_allow_html=True)
            st.markdown("<div style='margin-bottom:6px'></div>",
                        unsafe_allow_html=True)

        st.markdown("---")
        ca2, cb2 = st.columns([3,1])
        ca2.markdown("**TOTAL GERAL**")
        cb2.markdown(
            f"<div style='text-align:right;font-size:18px;font-weight:800;"
            f"color:#ef4444'>{brl(totais['geral'])}</div>",
            unsafe_allow_html=True)

        df_chart = pd.DataFrame(
            [{"Categoria": cat, "Valor (R$)": v["total"]} for cat,v in cats]
        ).set_index("Categoria")
        st.bar_chart(df_chart, use_container_width=True, height=260)

        criticos = [(c,v) for c,v in cats if v["status"]=="critico" and v.get("meta")]
        if criticos:
            st.markdown("---")
            st.markdown("### ⚠️ Categorias acima da meta")
            for cat, v in criticos:
                eco = v["total"] - v["meta"]
                st.error(
                    f"**{cat}**: {brl(v['total'])} vs meta {brl(v['meta'])} "
                    f"— excesso de **{brl(eco)}/mês** · {brl(eco*12)}/ano"
                )
