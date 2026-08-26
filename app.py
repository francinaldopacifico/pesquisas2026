import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(layout="wide", page_title="Pesquisas Eleitorais 2026 - TSE")

st.title("🗳️ Pesquisas Eleitorais Registradas — TSE 2026")
st.markdown(
    "Pesquisas registradas no PesqEle (TSE) para as Eleições 2026. "
    "Fonte oficial: [TSE](https://www.tse.jus.br/)."
)

@st.cache_data
def carregar():
    p = Path(__file__).parent / "pesquisas.csv"
    df = pd.read_csv(p, dtype={"protocolo": str})
    return df

df = carregar()

# Filtros
c1, c2, _ = st.columns([1, 1, 2])
uf = c1.selectbox("UF:", ["Todas"] + sorted(df["uf"].dropna().unique()))
termo = c2.text_input("Busca (instituto, município ou cargo):", "")

filtrado = df.copy()
if uf != "Todas":
    filtrado = filtrado[filtrado["uf"] == uf]
if termo.strip():
    t = termo.strip().lower()
    mask = (
        filtrado["instituto"].astype(str).str.lower().str.contains(t)
        | filtrado["municipio"].astype(str).str.lower().str.contains(t)
        | filtrado["cargo"].astype(str).str.lower().str.contains(t)
    )
    filtrado = filtrado[mask]

st.metric("Pesquisas encontradas", f"{len(filtrado):,}".replace(",", "."))

if not filtrado.empty:
    show = filtrado[["protocolo", "uf", "municipio", "instituto", "cargo",
                     "data_inicio", "entrevistados"]].copy()
    show["entrevistados"] = show["entrevistados"].fillna(0).astype(int)
    show.columns = ["Protocolo", "UF", "Município", "Instituto", "Cargo",
                    "Término da coleta", "Entrevistados"]
    st.dataframe(show, use_container_width=True, hide_index=True)
else:
    st.info("Nenhuma pesquisa encontrada com os filtros atuais.")

st.divider()
st.caption("Observação: este dataset do TSE contém os metadados das pesquisas registradas "
          "(protocolo, instituto, amostra, datas). Os percentuais por candidato "
          "serão exibidos quando o mapeamento de questionários for integrado (Etapa 2).")