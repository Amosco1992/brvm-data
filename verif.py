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
import builtins
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
    # dir(__builtins__) renvoie les méthodes d'un dict quand ce module est
    # importé plutôt qu'exécuté : on vise le module builtins explicitement.
    connus = set(fonctions) | globaux | importes | locaux | set(dir(builtins))

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


# ---------------------------------------------------------------------------
# Contrôle croisé collecteur / application
# ---------------------------------------------------------------------------

def champs_ecrits(chemin: Path) -> set[str]:
    """Clés du dictionnaire produit par ecrire_app()."""
    import re
    src = chemin.read_text()
    debut = src.index("def ecrire_app")
    bloc = src[debut:src.index("\ndef ", debut + 10)]
    return set(re.findall(r'"([a-z0-9_]{1,8})":', bloc))


def champs_lus(chemin: Path) -> set[str]:
    """Champs que l'application lit sur un titre (x.champ ou x?.champ)."""
    import re
    if not chemin.exists():
        return set()
    return set(re.findall(r"\bx\??\.([a-z0-9_]{1,8})\b", chemin.read_text()))


def controler_contrat(col: Path, app: Path) -> list[str]:
    """L'application lit-elle des champs que le collecteur n'écrit pas ?

    C'est le défaut le plus silencieux du lot : rien ne casse, la page
    s'affiche, et une case indique « NaN % » ou « — » sans que personne
    sache d'où vient le trou.
    """
    lus, ecrits = champs_lus(app), champs_ecrits(col)
    ignorer = {"map", "filter", "length", "sort", "find", "some", "every", "t"}
    manquants = sorted(lus - ecrits - ignorer)
    return [f"l'application lit x.{c} que ecrire_app() n'écrit pas" for c in manquants]
