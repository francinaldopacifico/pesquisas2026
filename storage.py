import json
import os
import urllib.request
import urllib.error
from pathlib import Path

"""
Persistência de resultados via GitHub API.
Guarda os resultados inseridos no admin em um arquivo 'resultados.json'
commitado no próprio repositório (Streamlit Cloud não tem disco persistente).

Config (Streamlit Secrets):
    GITHUB_TOKEN = token com acesso 'repo' (Fine-grained: contents write)
    GITHUB_REPO  = 'usuario/repositorio'  (ex: francinaldopacifico/pesquisas2026)
    GITHUB_FILE  = 'resultados.json' (opcional)

Fallback: se não houver secrets, usa 'resultados.json' local (só-voo, não persiste no Cloud).
"""

FILE = "resultados.json"


def _secrets():
    """Lê secrets do Streamlit se disponível (sem import em ambiente sem streamlit)."""
    try:
        import streamlit as st
        return st.secrets
    except Exception:
        return {}


def _repo():
    try:
        from streamlit import secrets as _s
        if "GITHUB_REPO" in _s:
            return _s["GITHUB_REPO"]
    except Exception:
        pass
    return os.environ.get("GITHUB_REPO") or "francinaldopacifico/pesquisas2026"


def _token():
    try:
        from streamlit import secrets as _s
        if "GITHUB_TOKEN" in _s:
            return _s["GITHUB_TOKEN"]
    except Exception:
        pass
    return os.environ.get("GITHUB_TOKEN") or ""


def _base_url():
    return f"https://api.github.com/repos/{_repo()}/contents/{FILE}"


def carregar_resultados_json():
    """Retorna dict {pesquisa_id: {candidato: pct, ...}}."""
    # 1) Tenta o arquivo local (copiado do repo pelo Streamlit) — mais confiável
    p = Path(__file__).parent / FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 2) Fallback: GitHub (persistente)
    token = _token()
    if token:
        try:
            req = urllib.request.Request(_base_url())
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("User-Agent", "Pindora2026")
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.load(r)
            content = data.get("content", "")
            import base64
            raw = base64.b64decode(content).decode("utf-8")
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            print("[gh] erro ao ler:", e.code)
        except Exception as e:
            print("[gh] erro ao ler:", e)
    return {}


def salvar_resultados_json(dados):
    """Grava 'dados' no GitHub (commit) e também local."""
    # Grava local (fallback/bkp)
    Path(__file__).parent.joinpath(FILE).write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    token = _token()
    if not token:
        print("[gh] sem token — apenas gravação local (não persiste no Cloud).")
        return False

    import base64
    body = json.dumps(dados, ensure_ascii=False, indent=2)

    # Tentar obter SHA do arquivo existente
    sha = None
    try:
        req = urllib.request.Request(_base_url())
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("User-Agent", "Pindora2026")
        with urllib.request.urlopen(req, timeout=15) as r:
            sha = json.load(r).get("sha")
    except Exception:
        pass

    payload = {
        "message": "Atualiza resultados pesquisas (admin)",
        "content": base64.b64encode(body.encode("utf-8")).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha

    try:
        req = urllib.request.Request(
            _base_url(),
            data=json.dumps(payload).encode("utf-8"),
            method="PUT",
        )
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("User-Agent", "Pindora2026")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 201)
    except Exception as e:
        print("[gh] erro ao salvar:", e)
        return False