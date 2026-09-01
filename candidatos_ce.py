# -*- coding: utf-8 -*-
"""
Sugestões de candidatos para pré-preencher o painel admin.
Nomes de candidatos conhecidos (CE 2026) por cargo.
Eles aparecem automaticamente no formulário para edição de percentual.
"""

SUGESTOES_CE = {
    "Governador": [
        "Elmano de Freitas",
        "Capitão Wagner",
        "Eugênio Ronaldo",
        "Suname do Belém",
        "Roberto Cláudio",
        "Chico Lopes",
    ],
    "Senador": [
        "Cid Gomes",
        "Camilo Santana",
        "Roberto Pessoa",
        "Eugênio Ronaldo",
    ],
    "Presidente": [
        "Candidato 1",
        "Candidato 2",
        "Candidato 3",
    ],
}


def sugerir_candidatos(cargo_texto):
    """Retorna lista de candidatos sugeridos para um cargo."""
    if not cargo_texto:
        return []
    cargos = [c.strip() for c in str(cargo_texto).split(",")]
    nomes = []
    for c in cargos:
        base = SUGESTOES_CE.get(c, [])
        for n in base:
            if n not in nomes:
                nomes.append(n)
    return nomes