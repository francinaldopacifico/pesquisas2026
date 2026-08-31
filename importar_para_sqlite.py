import sqlite3
import pandas as pd
import glob
import re
from pathlib import Path
from datetime import datetime

"""
Importador dos metadados oficiais do PesqEle TSE 2026 para SQLite.
Fonte: ZIP oficial (um CSV por UF), colunas reais do TSE.
Gera pesquisas.db -> tabela pesquisas_tse, usando NR_PROTOCOLO_REGISTRO como chave unica.
"""

ZIP_DIR = Path(__file__).parent / "pesquisas_2026"
DB_PATH = Path(__file__).parent / "pesquisas.db"

# Colunas reais do CSV do TSE
COLS = [
    "NR_PROTOCOLO_REGISTRO", "SG_UF", "NM_UE", "NM_EMPRESA",
    "DS_CARGO", "DT_REGISTRO", "DT_INICIO_PESQUISA", "DT_FIM_PESQUISA",
    "QT_ENTREVISTADO", "NM_ESTATISTICO_RESP",
]


def normalizar_cargo(c):
    if not c or (isinstance(c, float) and pd.isna(c)):
        return ""
    c = str(c).strip().lower()
    for k, v in {
        "presidente": "Presidente",
        "governador": "Governador",
        "vice-governador": "Vice-Governador",
        "senador": "Senador",
        "deputado federal": "Deputado Federal",
        "deputado estadual": "Deputado Estadual",
        "deputado distrital": "Deputado Distrital",
        "prefeito": "Prefeito",
        "vice-prefeito": "Vice-Prefeito",
        "vereador": "Vereador",
    }.items():
        if k in c:
            return v
    return str(c).title()


def data_br(v):
    if not v or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip().split(" ")[0]
    m = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})", s)
    if m:
        return f"{m.group(3)}/{m.group(2)}/{m.group(1)}"
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"
    return s


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pesquisas_tse (
        pesquisa_id TEXT PRIMARY KEY,
        instituto TEXT,
        cargo TEXT,
        municipio TEXT,
        datas TEXT,
        amostra INTEGER,
        uf TEXT,
        protocolo TEXT,
        data_importacao DATETIME
    )
    """)
    conn.commit()
    conn.close()


def importar():
    csvs = sorted(glob.glob(str(ZIP_DIR / "pesquisa_eleitoral_2026_*.csv")))
    csvs = [c for c in csvs if "_BRASIL" not in c]
    if not csvs:
        raise FileNotFoundError(
            f"Nenhum CSV oficial encontrado em {ZIP_DIR}. "
            "Coloque os arquivos pesquisa_eleitoral_2026_UF.csv nesta pasta."
        )
    print(f"✅ Encontrados {len(csvs)} arquivos CSV do TSE.")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = 0

    for f in csvs:
        df = pd.read_csv(f, sep=";", encoding="latin-1", usecols=lambda c: c in COLS,
                         dtype={"NR_PROTOCOLO_REGISTRO": str}, low_memory=False)
        rows = []
        for _, r in df.iterrows():
            proto = str(r["NR_PROTOCOLO_REGISTRO"]).strip()
            if not proto:
                continue
            inst = str(r["NM_EMPRESA"]).strip() if pd.notna(r.get("NM_EMPRESA")) else ""
            cargo = normalizar_cargo(r.get("DS_CARGO"))
            mun = str(r["NM_UE"]).strip() if pd.notna(r.get("NM_UE")) else ""
            qtd = r["QT_ENTREVISTADO"] if pd.notna(r.get("QT_ENTREVISTADO")) else 0
            try:
                qtd = int(float(qtd))
            except Exception:
                qtd = 0
            uf = str(r["SG_UF"]).strip().upper()
            data = data_br(r.get("DT_INICIO_PESQUISA")) or data_br(r.get("DT_REGISTRO"))
            rows.append((proto, inst, cargo, mun, data, qtd, uf, proto, now))

        cur.executemany("""
        INSERT INTO pesquisas_tse
            (pesquisa_id, instituto, cargo, municipio, datas, amostra, uf, protocolo, data_importacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pesquisa_id) DO UPDATE SET
            instituto=excluded.instituto, cargo=excluded.cargo, municipio=excluded.municipio,
            datas=excluded.datas, amostra=excluded.amostra, uf=excluded.uf
        """, rows)
        conn.commit()
        total += len(rows)
        print(f"   {Path(f).name}: {len(rows)}")

    conn.close()
    print(f"\n✅ IMPORTADO! Total: {total} pesquisas em {DB_PATH}")


if __name__ == "__main__":
    init_db()
    importar()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT COUNT(*) n, COUNT(DISTINCT uf) ufs FROM pesquisas_tse", conn)
    conn.close()
    print(df.to_string(index=False))