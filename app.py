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

# --- 2. DATASET REAL DO TSE ---
@st.cache_data
def carregar_metadados():
    p = Path(__file__).parent / "pesquisas.csv"
    df = pd.read_csv(p, dtype={"protocolo": str})
    df["pesquisa_id"] = df["protocolo"].astype(str).str.strip()
    df = df.rename(columns={
        "uf": "uf",
        "instituto": "instituto",
        "cargo": "cargo",
        "data_inicio": "datas",
        "entrevistados": "amostra",
        "municipio": "municipio",
    })
    # datas vem como DD/MM/AAAA já (no csv gerado). Mantém.
    return df

# --- 3. FUNÇÕES DE BANCO ---
def salvar_resultado(pesquisa_id, instituto, cargo, data_pesquisa, uf, fonte, candidatos):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
    INSERT INTO resultados_pesquisas
        (pesquisa_id, instituto, cargo, data_pesquisa, uf, fonte_manual, criado_em, atualizado_em)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(pesquisa_id) DO UPDATE SET
        instituto=excluded.instituto,
        cargo=excluded.cargo,
        data_pesquisa=excluded.data_pesquisa,
        uf=excluded.uf,
        fonte_manual=excluded.fonte_manual,
        atualizado_em=excluded.atualizado_em
    """, (pesquisa_id, instituto, cargo, data_pesquisa, uf, fonte, now, now))
    cur.execute("DELETE FROM candidatos_resultado WHERE pesquisa_id = ?", (pesquisa_id,))
    for cand, pct in candidatos:
        cur.execute("""
        INSERT INTO candidatos_resultado (pesquisa_id, candidato, percentual)
        VALUES (?, ?, ?)
        """, (pesquisa_id, cand, pct))
    conn.commit()
    conn.close()

def carregar_resultados(pesquisa_id):
    conn = sqlite3.connect(DB_PATH)
    df_main = pd.read_sql("SELECT * FROM resultados_pesquisas WHERE pesquisa_id = ?",
                          conn, params=(pesquisa_id,))
    if df_main.empty:
        conn.close()
        return None
    df_cand = pd.read_sql("""
        SELECT candidato, percentual FROM candidatos_resultado
        WHERE pesquisa_id = ? ORDER BY percentual DESC
    """, conn, params=(pesquisa_id,))
    conn.close()
    return {'metadados': df_main.iloc[0], 'candidatos': df_cand}

def deletar_resultado(pesquisa_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM resultados_pesquisas WHERE pesquisa_id = ?", (pesquisa_id,))
    cur.execute("DELETE FROM candidatos_resultado WHERE pesquisa_id = ?", (pesquisa_id,))
    conn.commit()
    conn.close()

# --- 4. INTERFACE ---
init_db()

st.set_page_config(layout="wide", page_title="Pesquisas Eleitorais 2026")

df_meta = carregar_metadados()
df_meta["amostra"] = df_meta["amostra"].fillna(0).astype(int)

# --- ADMIN (senha) ---
st.sidebar.title("🔒 Painel Admin")
senha = st.sidebar.text_input("Senha do admin", type="password")
ADMIN = senha == "admin123"  # Troque por senha segura

if ADMIN:
    st.sidebar.success("✅ Modo ADMIN ativado")
    st.title("🛠️ Administração de Resultados")
    tab1, tab2 = st.tabs(["➕ Inserir/Editar Resultado", "🗑️ Deletar Resultado", "📋 Metadados TSE"])

    with tab1:
        st.header("Vincular resultado a uma pesquisa oficial")
        busca = st.text_input("Buscar pesquisa (instituto/protocolo/UF/cargo):")
        df_busca = df_meta
        if busca.strip():
            b = busca.strip().lower()
            mask = (
                df_meta["instituto"].astype(str).str.lower().str.contains(b)
                | df_meta["protocolo"].astype(str).str.lower().str.contains(b)
                | df_meta["uf"].astype(str).str.lower().str.contains(b)
                | df_meta["cargo"].astype(str).str.lower().str.contains(b)
                | df_meta["municipio"].astype(str).str.lower().str.contains(b)
            )
            df_busca = df_meta[mask]
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
            n = st.number_input("Nº de candidatos", min_value=1, max_value=15,
                                value=(len(dados_existentes['candidatos']) if dados_existentes else 4),
                                step=1)
            candidatos = []
            total = 0.0
            pre = (dados_existentes['candidatos']['candidato'].tolist(),
                   dados_existentes['candidatos']['percentual'].tolist()) if dados_existentes else (["", "", "", ""], [0.0, 0.0, 0.0, 0.0])
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
            if total > 100.1:
                st.error(f"⚠️ Soma {total:.1f}% — deve ser ≤ 100%")
            else:
                fonte = st.text_input("Fonte manual (ex: Folha de S.Paulo, g1)",
                                      value=(dados_existentes['metadados']['fonte_manual'] or "")
                                      if dados_existentes else "")
                if st.button("💾 Salvar Resultado"):
                    salvar_resultado(opcao, meta['instituto'], meta['cargo'], meta['datas'],
                                     meta['uf'], fonte, candidatos)
                    st.success("✅ Resultado salvo!")
                    st.rerun()

    with tab2:
        st.header("Deletar resultado vinculado")
        _conn = sqlite3.connect(DB_PATH)
        ids = [r[0] for r in _conn.execute("SELECT pesquisa_id FROM resultados_pesquisas")]
        _conn.close()
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
    # --- MODO PÚBLICO ---
    st.title("🗳️ Pesquisas Eleitorais → TSE 2026")
    st.markdown("Pesquisas registradas no PesqEle (TSE). Quando o resultado por candidato estiver "
                "disponível, ele é exibido. Caso contrário, apenas os metadados oficiais.")

    c1, c2, c3 = st.columns(3)
    with c1:
        uf_f = st.selectbox("UF:", ["Todas"] + sorted(df_meta["uf"].dropna().unique().tolist()))
    with c2:
        cargo_f = st.selectbox("Cargo:", ["Todos"] + sorted(df_meta["cargo"].dropna().unique().tolist()))
    with c3:
        termo = st.text_input("Busca (instituto/candidato/protocolo):")

    df_f = df_meta
    if uf_f != "Todas":
        df_f = df_f[df_f["uf"] == uf_f]
    if cargo_f != "Todos":
        df_f = df_f[df_f["cargo"] == cargo_f]
    if termo.strip():
        t = termo.strip().lower()
        mask = (df_f["instituto"].astype(str).str.lower().str.contains(t)
                | df_f["protocolo"].astype(str).str.lower().str.contains(t)
                | df_f["cargo"].astype(str).str.lower().str.contains(t)
                | df_f["municipio"].astype(str).str.lower().str.contains(t))
        df_f = df_f[mask]

    # Filtra também por candidato nos resultados salvos
    conn = sqlite3.connect(DB_PATH)
    all_ids = [r[0] for r in conn.execute("SELECT pesquisa_id FROM resultados_pesquisas")]
    cand_ids = set()
    if termo.strip():
        t = termo.strip().lower()
        cand_ids = {r[0] for r in conn.execute(
            "SELECT pesquisa_id FROM candidatos_resultado WHERE lower(candidato) LIKE ?", (f"%{t}%",))}
    conn.close()
    if cand_ids:
        df_f = pd.concat([df_f, df_meta[df_meta['pesquisa_id'].isin(cand_ids)]]).drop_duplicates('pesquisa_id')

    st.write(f"Mostrando **{len(df_f)}** pesquisas.")

    for _, row in df_f.iterrows():
        pid = row["pesquisa_id"]
        res = carregar_resultados(pid)
        with st.expander(f"📋 {row['instituto']} | {row['cargo']} | UF {row['uf']} | coleta até {row['datas']}"):
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Instituto", row["instituto"])
            with col2: st.metric("Cargo", row["cargo"])
            with col3: st.metric("Término coleta", row["datas"])
            with col4: st.metric("Amostra", f"{row['amostra']:,}".replace(",", "."))
            if res is not None:
                st.success("📊 Resultado disponível")
                st.dataframe(res["candidatos"], use_container_width=True, hide_index=True)
                fig, ax = plt.subplots(figsize=(6, max(2, 0.4 * len(res['candidatos']))))
                ax.barh(res["candidatos"]["candidato"], res["candidatos"]["percentual"], color="#4C78A8")
                ax.set_xlabel("Percentual (%)")
                ax.set_xlim(0, 100)
                ax.invert_yaxis()
                st.pyplot(fig)
                fonte = res["metadados"]["fonte_manual"]
                if fonte:
                    st.caption(f"Fonte dos resultados: {fonte}")
            else:
                st.warning("⚠️ Apenas metadados oficiais do TSE — resultado não inserido ainda.")

st.sidebar.divider()
st.sidebar.caption("🔒 Admin: senha 'admin123' (troque por segura)")
st.sidebar.caption("Metadados: PesqEle TSE 2026 (oficiais)")