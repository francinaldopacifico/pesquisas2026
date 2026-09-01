import streamlit as st
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

# --- 1. SETUP DO BANCO ---
DB_PATH = Path(__file__).parent / "pesquisas.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS resultados_pesquisas (
        pesquisa_id TEXT PRIMARY KEY,
        instituto TEXT NOT NULL,
        cargo TEXT NOT NULL,
        data_pesquisa TEXT,
        uf TEXT,
        fonte_manual TEXT,
        criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
        atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS candidatos_resultado (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pesquisa_id TEXT NOT NULL,
        candidato TEXT NOT NULL,
        percentual REAL NOT NULL CHECK (percentual >= 0 AND percentual <= 100),
        FOREIGN KEY (pesquisa_id) REFERENCES resultados_pesquisas(pesquisa_id),
        UNIQUE(pesquisa_id, candidato)
    )
    """)
    conn.commit()
    conn.close()

# --- 2. FONTE: SQLite (metadados + resultados) ---

@st.cache_data
def carregar_metadados():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM pesquisas_tse", conn)
    conn.close()
    df["pesquisa_id"] = df["pesquisa_id"].astype(str).str.strip()
    df["amostra"] = df["amostra"].fillna(0).astype(int)
    return df

# --- 3. FUNÇÕES DE RESULTADOS (persistência via GitHub JSON) ---
import storage

def salvar_resultado(pesquisa_id, instituto, cargo, data_pesquisa, uf, fonte, candidatos):
    dados = storage.carregar_resultados_json()
    dados[pesquisa_id] = {
        "instituto": instituto,
        "cargo": cargo,
        "data_pesquisa": data_pesquisa,
        "uf": uf,
        "fonte_manual": fonte or "",
        "candidatos": {cand: float(pct) for cand, pct in candidatos},
    }
    return storage.salvar_resultados_json(dados)

def carregar_resultados(pesquisa_id):
    dados = storage.carregar_resultados_json()
    reg = dados.get(pesquisa_id)
    if not reg:
        return None
    cands = reg.get("candidatos", {})
    df_cand = pd.DataFrame(
        [{"candidato": k, "percentual": v} for k, v in cands.items()]
    ).sort_values("percentual", ascending=False) if cands else pd.DataFrame(columns=["candidato", "percentual"])
    return {
        "metadados": pd.Series({
            "instituto": reg.get("instituto", ""),
            "cargo": reg.get("cargo", ""),
            "data_pesquisa": reg.get("data_pesquisa", ""),
            "uf": reg.get("uf", ""),
            "fonte_manual": reg.get("fonte_manual", ""),
        }),
        "candidatos": df_cand,
    }

def deletar_resultado(pesquisa_id):
    dados = storage.carregar_resultados_json()
    if pesquisa_id in dados:
        del dados[pesquisa_id]
        return storage.salvar_resultados_json(dados)
    return False

def ids_com_resultado():
    return set(storage.carregar_resultados_json().keys())

# --- 4. INTERFACE ---
init_db()

st.set_page_config(layout="wide", page_title="Pesquisas Eleitorais 2026")

df_meta = carregar_metadados()
df_meta["amostra"] = df_meta["amostra"].fillna(0).astype(int)

# --- ADMIN (senha) ---
def _admin_senha():
    try:
        from streamlit import secrets as _s
        if "ADMIN_SENHA" in _s:
            return _s["ADMIN_SENHA"]
    except Exception:
        pass
    import os
    return os.environ.get("ADMIN_SENHA") or "admin123"

st.sidebar.title("🔒 Painel Admin")
senha = st.sidebar.text_input("Senha do admin", type="password")
ADMIN = senha == _admin_senha()

if ADMIN:
    st.sidebar.success("✅ Modo ADMIN ativado")
    st.title("🛠️ Administração de Resultados")
    tab1, tab2, tab3 = st.tabs(["➕ Inserir/Editar Resultado", "🗑️ Deletar Resultado", "📋 Metadados TSE"])

    with tab1:
        st.header("Vincular resultado a uma pesquisa oficial")
        with st.expander("📖 Como usar (guia rápido)"):
            st.markdown("""
1. **Busque** o instituto (ex.: `real time`, `quaest`) ou o protocolo.
2. **Selecione** a pesquisa — os candidatos aparecem preenchidos.
3. **Digite o % real** de cada candidato (soma ≤ 100).
4. Preencha a **fonte** (ex.: g1, site do instituto).
5. Clique **💾 Salvar Resultado** → aparece "✅ Resultado salvo no GitHub!".

Para **atualizar**: selecione a mesma pesquisa, ajuste os % e salve de novo (substitui).
Para **ver no público**: apague a senha no menu lateral — a pesquisa com resultado abre expandida com tabela + gráfico.
""")
        busca = st.text_input("Buscar pesquisa (instituto/protocolo/cargo):")
        df_busca = df_meta[df_meta["uf"] == "CE"].copy()
        if busca.strip():
            b = busca.strip().lower()
            mask = (
                df_busca["instituto"].astype(str).str.lower().str.contains(b, regex=False)
                | df_busca["protocolo"].astype(str).str.lower().str.contains(b, regex=False)
                | df_busca["uf"].astype(str).str.lower().str.contains(b, regex=False)
                | df_busca["cargo"].astype(str).str.lower().str.contains(b, regex=False)
                | df_busca["municipio"].astype(str).str.lower().str.contains(b, regex=False)
            )
            df_busca = df_busca[mask]
        if df_busca.empty:
            st.info("Nenhuma pesquisa encontrada.")
        else:
            st.caption(f"{len(df_busca)} pesquisas encontradas.")
            opcao = st.selectbox(
                "Selecione a pesquisa (mostra: protocolo | UF | instituto | cargo | término da coleta):",
                df_busca["pesquisa_id"].tolist(),
                format_func=lambda pid: next(
                    (f"{r['protocolo']} | {r['uf']} | {r['instituto']} | {r['cargo']} | {r['datas']}"
                     for _, r in df_busca[df_busca['pesquisa_id'] == pid].iterrows()), pid)
            )
            meta = df_busca[df_busca['pesquisa_id'] == opcao].iloc[0]
            st.info(f"**{meta['instituto']}** — {meta['cargo']} — UF {meta['uf']} — coleta até {meta['datas']} — amostra {meta['amostra']}")

            dados_existentes = carregar_resultados(opcao)
            st.subheader("Resultados por candidato")
            if dados_existentes:
                n_default = len(dados_existentes['candidatos'])
                pre = (dados_existentes['candidatos']['candidato'].tolist(),
                       dados_existentes['candidatos']['percentual'].tolist())
            else:
                import candidatos_ce
                sugestoes = candidatos_ce.sugerir_candidatos(meta['cargo'])
                if sugestoes:
                    n_default = len(sugestoes)
                    pre = (sugestoes, [0.0] * len(sugestoes))
                else:
                    n_default = 4
                    pre = (["", "", "", ""], [0.0, 0.0, 0.0, 0.0])
            n_default = max(1, min(15, n_default))
            n = st.number_input("Nº de candidatos", min_value=1, max_value=15,
                                value=n_default, step=1, key=f"n_cand_{opcao}")
            candidatos = []
            total = 0.0
            for i in range(int(n)):
                c1, c2 = st.columns([3, 1])
                nome_default = pre[0][i] if i < len(pre[0]) else ""
                pct_default = float(pre[1][i]) if i < len(pre[1]) else 0.0
                cand = c1.text_input(f"Candidato {i+1}", value=nome_default, key=f"c_{opcao}_{i}")
                pct = c2.number_input(f"%", min_value=0.0, max_value=100.0, value=pct_default,
                                      step=0.1, key=f"p_{opcao}_{i}")
                if cand.strip():
                    candidatos.append((cand.strip(), pct))
                    total += pct
            if not candidatos:
                st.warning("⚠️ Preencha ao menos um candidato com nome para poder salvar.")
            elif total > 100.1:
                st.error(f"⚠️ Soma {total:.1f}% — deve ser ≤ 100%")
            else:
                fonte = st.text_input("Fonte manual (ex: Folha de S.Paulo, g1)",
                                      value=(dados_existentes['metadados']['fonte_manual'] or "")
                                      if dados_existentes else "")
                if st.button("💾 Salvar Resultado"):
                    try:
                        ok = salvar_resultado(opcao, meta['instituto'], meta['cargo'], meta['datas'],
                                              meta['uf'], fonte, candidatos)
                        if ok:
                            st.success("✅ Resultado salvo no GitHub!")
                            st.toast("Salvo com sucesso!")
                            dados_existentes = carregar_resultados(opcao)
                        else:
                            st.error("❌ Não foi possível gravar no GitHub. Tente novamente.")
                    except Exception as ex:
                        st.error(f"❌ Erro ao salvar: {ex}")

    with tab2:
        st.header("Deletar resultado vinculado")
        ids = sorted(ids_com_resultado())
        if not ids:
            st.info("Nenhum resultado salvo ainda.")
        else:
            del_id = st.selectbox("Resultado a deletar:", ids)
            if st.button("🗑️ Deletar"):
                deletar_resultado(del_id)
                st.success(f"✅ {del_id} deletado.")
                st.rerun()

    with tab3:
        st.header("Metadados oficiais TSE (somente leitura)")
        st.dataframe(df_meta[["protocolo", "uf", "municipio", "instituto", "cargo", "datas", "amostra"]],
                     use_container_width=True, hide_index=True)

else:
    # --- MODO PÚBLICO (foco Ceará) ---
    st.title("🗳️ Pesquisas Eleitorais — Ceará · 2026")
    st.markdown(
        "Pesquisas registradas no PesqEle (TSE) para o Estado do Ceará — "
        "todos os cargos das Eleições 2026. Quando o resultado por candidato "
        "estiver disponível, ele é exibido; caso contrário, apenas os metadados oficiais."
    )

    # Foco no Ceará
    df_ce = df_meta[df_meta["uf"] == "CE"].copy()

    cargos_foco = ["Presidente", "Governador", "Senador", "Deputado Federal", "Deputado Estadual"]
    aba = st.radio("Cargo:", ["Todos"] + cargos_foco, horizontal=True)

    c1, c2 = st.columns([2, 3])
    filtro_inst = c1.selectbox("Instituto:", ["Todos"] + sorted(df_ce["instituto"].dropna().unique().tolist()))
    termo = c2.text_input("Busca (instituto/candidato/protocolo):")

    df_f = df_ce
    if aba != "Todos":
        df_f = df_f[df_f["cargo"].astype(str).str.contains(aba, case=False, na=False)]
    if filtro_inst != "Todos":
        df_f = df_f[df_f["instituto"] == filtro_inst]

    # Busca também por candidato nos resultados salvos
    cand_ids = set()
    if termo.strip():
        t = termo.strip().lower()
        mask = (df_f["instituto"].astype(str).str.lower().str.contains(t, regex=False)
                | df_f["protocolo"].astype(str).str.lower().str.contains(t, regex=False)
                | df_f["cargo"].astype(str).str.lower().str.contains(t, regex=False)
                | df_f["municipio"].astype(str).str.lower().str.contains(t, regex=False))
        df_f = df_f[mask]
        for pid, reg in storage.carregar_resultados_json().items():
            for cand in (reg.get("candidatos") or {}):
                if t in str(cand).lower():
                    cand_ids.add(pid)
    if cand_ids:
        df_f = pd.concat([df_f, df_ce[df_ce['pesquisa_id'].isin(cand_ids)]]).drop_duplicates('pesquisa_id')

    df_f = df_f.copy()
    df_f["_dt"] = pd.to_datetime(df_f["datas"], format="%d/%m/%Y", errors="coerce")
    df_f = df_f.sort_values("_dt", ascending=False).drop(columns=["_dt"])
    st.write(f"Mostrando **{len(df_f)}** pesquisa(s) no Ceará.")

    for _, row in df_f.iterrows():
        pid = row["pesquisa_id"]
        res = carregar_resultados(pid)
        tem_res = res is not None
        titulo = f"📋 {row['instituto']} | {row['cargo']} | coleta até {row['datas']}"
        if tem_res:
            titulo = "📊 " + titulo
        with st.expander(titulo, expanded=tem_res):
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Instituto", row["instituto"])
            with col2: st.metric("Cargo", row["cargo"])
            with col3: st.metric("Término coleta", row["datas"])
            with col4: st.metric("Amostra", f"{row['amostra']:,}".replace(",", "."))
            if res is not None:
                st.success("📊 Resultado disponível")
                cand = res["candidatos"]
                if cand.empty:
                    st.warning("Sem candidatos salvos.")
                else:
                    df_tab = cand.copy()
                    df_tab = df_tab.reset_index(drop=True)
                    df_tab.columns = ["Candidato", "%"]
                    df_tab["%"] = df_tab["%"].astype(float).map(lambda v: f"{v:.1f}".replace(".", ","))
                    st.table(df_tab.style.hide(axis="index"))
                fonte = res["metadados"]["fonte_manual"]
                if fonte:
                    st.caption(f"Fonte dos resultados: {fonte}")
            else:
                st.warning("⚠️ Apenas metadados oficiais do TSE — resultado não inserido ainda.")

st.sidebar.divider()
st.sidebar.caption("🔒 Admin: senha configurada (secret; padrão admin123)")
st.sidebar.caption("Metadados: PesqEle TSE 2026 (oficiais)")
try:
    _nres = len(ids_com_resultado())
    _tok = "✅" if storage._token() else "❌ sem token"
    st.sidebar.caption(f"Resultados salvos: {_nres} | GitHub: {_tok}")
except Exception as _e:
    st.sidebar.caption(f"Status: {_e}")