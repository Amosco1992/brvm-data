#!/usr/bin/env python3
"""Contrôle statique de collecte.py avant de le pousser.

Le fichier unique regroupe cinq collecteurs qui vivaient dans des modules
séparés. À chaque fusion, des fonctions ont été renommées pour éviter les
collisions — et à deux reprises un appel est resté sur l'ancien nom, qui
existait encore ailleurs dans le fichier. Python ne s'en plaint qu'à
l'exécution, une fois la collecte lancée.

Ce script rejoue ce contrôle en une seconde :

    python verif.py
"""
import ast
import sys
from pathlib import Path

SRC = Path(__file__).with_name("collecte.py")


def controler(chemin: Path) -> list[str]:
    arbre = ast.parse(chemin.read_text())
    fonctions = {n.name: n for n in ast.walk(arbre) if isinstance(n, ast.FunctionDef)}
    globaux = {n.targets[0].id for n in arbre.body
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    importes = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            importes |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            importes |= {a.asname or a.name for a in n.names}
    locaux = set()
    for fn in fonctions.values():
        locaux |= {a.arg for a in fn.args.args + fn.args.kwonlyargs}
        locaux |= {n.id for n in ast.walk(fn)
                   if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    connus = set(fonctions) | globaux | importes | locaux | set(dir(__builtins__))

    ennuis = []
    for n in ast.walk(arbre):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)):
            continue
        nom = n.func.id
        if nom not in connus:
            ennuis.append(f"ligne {n.lineno} : appel à {nom}(), qui n'existe pas")
            continue
        fn = fonctions.get(nom)
        if fn and not fn.args.vararg:
            maxi = len(fn.args.args)
            mini = maxi - len(fn.args.defaults)
            if len(n.args) > maxi or len(n.args) + len(n.keywords) < mini:
                ennuis.append(
                    f"ligne {n.lineno} : {nom}() reçoit {len(n.args)} arguments "
                    f"positionnels, la définition en attend {mini} à {maxi}")
    return ennuis


if __name__ == "__main__":
    problemes = controler(SRC)
    for p in problemes:
        print("  " + p)
    print(f"{len(problemes)} problème(s)" if problemes else "Aucun problème détecté.")
    sys.exit(1 if problemes else 0)
