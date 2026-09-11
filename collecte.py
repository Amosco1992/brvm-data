#!/usr/bin/env python3
"""Collecte quotidienne des données de la BRVM.

Un seul fichier, volontairement : il se téléverse d'un glisser-déposer dans
un dépôt GitHub sans qu'aucune arborescence puisse se perdre en route.

    pip install requests
    python collecte.py                # avec contrôle croisé Sika Finance
    python collecte.py --sans-sika    # miroir GitHub seul, plus rapide

Produit, à côté de ce fichier :

    data/universe.json          47 titres : référentiel, cours, indicateurs
    data/history/<TICKER>.json  séances quotidiennes sur cinq ans
    data/meta.json              horodatage, état des sources, divergences

Trois règles tenues par le code :

  1. Aucune valeur n'est publiée sans sa source et sa date.
  2. Une donnée périmée est signalée, jamais servie comme fraîche.
  3. Quand deux sources divergent, on publie l'écart au lieu d'arbitrer
     en silence.

Données de marché à titre informatif. Ne constitue pas un conseil en
investissement.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import statistics
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import requests


# ==========================================================================
# RÉFÉRENTIEL DES VALEURS COTÉES
# ==========================================================================

# ticker, symbole Sika, émetteur, pays, secteur
UNIVERS = [
    ("ABJC",  "ABJC.CI",  "Servair Abidjan",                   "CI", "Services"),
    ("BICC",  "BICC.CI",  "BICI Côte d'Ivoire",                "CI", "Finance"),
    ("BNBC",  "BNBC.CI",  "Bernabé Côte d'Ivoire",             "CI", "Distribution"),
    ("BOAC",  "BOAC.CI",  "Bank of Africa Côte d'Ivoire",      "CI", "Finance"),
    ("CABC",  "CABC.CI",  "SICABLE Côte d'Ivoire",             "CI", "Industrie"),
    ("CFAC",  "CFAC.CI",  "CFAO Motors Côte d'Ivoire",         "CI", "Distribution"),
    ("CIEC",  "CIEC.CI",  "CIE Côte d'Ivoire",                 "CI", "Services publics"),
    ("ECOC",  "ECOC.CI",  "Ecobank Côte d'Ivoire",             "CI", "Finance"),
    ("FTSC",  "FTSC.CI",  "Filtisac Côte d'Ivoire",            "CI", "Industrie"),
    ("NEIC",  "NEIC.CI",  "NEI-CEDA Côte d'Ivoire",            "CI", "Industrie"),
    ("NSBC",  "NSBC.CI",  "NSIA Banque Côte d'Ivoire",         "CI", "Finance"),
    ("NTLC",  "NTLC.CI",  "Nestlé Côte d'Ivoire",              "CI", "Agro-industrie"),
    ("ORAC",  "ORAC.CI",  "Orange Côte d'Ivoire",              "CI", "Télécommunications"),
    ("PALC",  "PALC.CI",  "Palm Côte d'Ivoire",                "CI", "Agro-industrie"),
    ("PRSC",  "PRSC.CI",  "Tractafric Motors Côte d'Ivoire",   "CI", "Distribution"),
    ("SAFC",  "SAFC.CI",  "SAFCA Côte d'Ivoire",               "CI", "Finance"),
    ("SCRC",  "SCRC.CI",  "Sucrivoire",                        "CI", "Agro-industrie"),
    ("SDCC",  "SDCC.CI",  "SODECI",                            "CI", "Services publics"),
    ("SDSC",  "SDSC.CI",  "Africa Global Logistics CI",        "CI", "Transport"),
    ("SEMC",  "SEMC.CI",  "Eviosys Packaging Siem CI",         "CI", "Industrie"),
    ("SGBC",  "SGBC.CI",  "Société Générale Côte d'Ivoire",    "CI", "Finance"),
    ("SHEC",  "SHEC.CI",  "Vivo Energy Côte d'Ivoire",         "CI", "Distribution"),
    ("SIBC",  "SIBC.CI",  "Société Ivoirienne de Banque",      "CI", "Finance"),
    ("SICC",  "SICC.CI",  "SICOR Côte d'Ivoire",               "CI", "Agro-industrie"),
    ("SIVC",  "SIVC.CI",  "Erium Côte d'Ivoire",               "CI", "Industrie"),
    ("SLBC",  "SLBC.CI",  "Solibra Côte d'Ivoire",             "CI", "Agro-industrie"),
    ("SMBC",  "SMBC.CI",  "SMB Côte d'Ivoire",                 "CI", "Industrie"),
    ("SOGC",  "SOGC.CI",  "SOGB Côte d'Ivoire",                "CI", "Agro-industrie"),
    ("SPHC",  "SPHC.CI",  "SAPH Côte d'Ivoire",                "CI", "Agro-industrie"),
    ("STAC",  "STAC.CI",  "SETAO Côte d'Ivoire",               "CI", "BTP"),
    ("STBC",  "STBC.CI",  "SITAB Côte d'Ivoire",               "CI", "Industrie"),
    ("TTLC",  "TTLC.CI",  "TotalEnergies Marketing CI",        "CI", "Distribution"),
    ("UNLC",  "UNLC.CI",  "Unilever Côte d'Ivoire",            "CI", "Industrie"),
    ("UNXC",  "UNXC.CI",  "Uniwax Côte d'Ivoire",              "CI", "Industrie"),
    ("BOAS",  "BOAS.SN",  "Bank of Africa Sénégal",            "SN", "Finance"),
    ("SNTS",  "SNTS.SN",  "Sonatel",                           "SN", "Télécommunications"),
    ("TTLS",  "TTLS.SN",  "TotalEnergies Marketing Sénégal",   "SN", "Distribution"),
    ("BOABF", "BOABF.BF", "Bank of Africa Burkina Faso",       "BF", "Finance"),
    ("CBIBF", "CBIBF.BF", "Coris Bank International",          "BF", "Finance"),
    ("ONTBF", "ONTBF.BF", "Onatel Burkina Faso",               "BF", "Télécommunications"),
    ("BOAM",  "BOAM.ML",  "Bank of Africa Mali",               "ML", "Finance"),
    ("ETIT",  "ETIT.TG",  "Ecobank Transnational Inc.",        "TG", "Finance"),
    ("ORGT",  "ORGT.TG",  "Oragroup",                          "TG", "Finance"),
    ("BICB",  "BICB.BJ",  "BIIC Bénin",                        "BJ", "Finance"),
    ("LNBB",  "LNBB.BJ",  "Loterie Nationale du Bénin",        "BJ", "Services"),
    ("BOAB",  "BOAB.BJ",  "Bank of Africa Bénin",              "BJ", "Finance"),
    ("BOAN",  "BOAN.NE",  "Bank of Africa Niger",              "NE", "Finance"),
]

TICKERS = [u[0] for u in UNIVERS]
PAR_TICKER = {u[0]: {"ticker": u[0], "symbole_sika": u[1], "emetteur": u[2],
                     "pays": u[3], "secteur": u[4]} for u in UNIVERS}

PAYS = {"CI": "Côte d'Ivoire", "SN": "Sénégal", "BF": "Burkina Faso",
        "ML": "Mali", "TG": "Togo", "BJ": "Bénin", "NE": "Niger"}


# ==========================================================================
# SOURCE — miroir CSV public sur GitHub (historique OHLCV depuis 1998)
# ==========================================================================

BASE = "https://raw.githubusercontent.com/Fredysessie/brvm-data-public/main/data"
NOM_MIROIR = "miroir-github"


def _en_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        return None


def _en_nombre(s: str) -> float | None:
    try:
        v = float(str(s).replace(" ", "").replace("\u202f", "").replace(",", "."))
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def historique_miroir(ticker: str, session: requests.Session | None = None,
               timeout: int = 30) -> list[dict]:
    """Séries quotidiennes d'un titre, triées par date croissante.

    Renvoie une liste vide si le fichier est absent ou illisible : l'appelant
    décide quoi en faire. On ne lève pas d'exception pour un seul ticker
    manquant, sinon un délistage fait tomber toute la collecte.
    """
    s = session or requests.Session()
    url = f"{BASE}/{ticker}/{ticker}.daily.csv"
    try:
        r = s.get(url, timeout=timeout)
    except requests.RequestException:
        return []
    if r.status_code != 200:
        return []

    lignes: list[dict] = []
    for row in csv.DictReader(io.StringIO(r.text)):
        d = _en_date(row.get("Date", ""))
        cloture = _en_nombre(row.get("Close", ""))
        if d is None or cloture is None:
            continue
        volume = _en_nombre(row.get("Volume", "")) or 0.0
        lignes.append({
            "date": d.isoformat(),
            "ouverture": _en_nombre(row.get("Open", "")),
            "haut": _en_nombre(row.get("High", "")),
            "bas": _en_nombre(row.get("Low", "")),
            "cloture": cloture,
            "volume": int(volume),
        })
    lignes.sort(key=lambda x: x["date"])
    return lignes


def dernier_cours(lignes: list[dict]) -> dict | None:
    return lignes[-1] if lignes else None


# ==========================================================================
# SOURCE — API EOD de Sika Finance (deuxième avis sur le dernier cours)
# ==========================================================================

URL = "https://www.sikafinance.com/api/charting/GetTicksEOD"
NOM_SIKA = "sika"

_UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0",
]


def _entetes_sika() -> dict:
    return {"User-Agent": random.choice(_UA), "Accept": "application/json"}


def historique_sika(symbole_sika: str, jours: int = 365,
               session: requests.Session | None = None,
               timeout: int = 15) -> list[dict]:
    """Historique EOD. `jours` au-delà de 365 fait basculer l'API en hebdomadaire."""
    s = session or requests.Session()
    params = {"symbol": symbole_sika, "length": min(jours, 365),
              "period": "0", "guid": str(uuid.uuid4())}
    try:
        r = s.get(URL, params=params, headers=_entetes_sika(), timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return []

    points = data.get("QuoteTab") or []
    lignes = []
    for p in points:
        brut = p.get("d")
        try:
            d = datetime.fromisoformat(str(brut).replace("Z", "")).date().isoformat()
        except ValueError:
            continue
        cloture = p.get("c")
        if not cloture:
            continue
        lignes.append({
            "date": d,
            "ouverture": p.get("o"),
            "haut": p.get("h"),
            "bas": p.get("l"),
            "cloture": float(cloture),
            "volume": int(p.get("v") or 0),
        })
    lignes.sort(key=lambda x: x["date"])
    return lignes


# ==========================================================================
# SOURCE — brvm.org, cote officielle et rapports (NON TESTÉ)
# ==========================================================================

RACINE = "https://www.brvm.org"
NOM_SITE = "brvm.org"

_ENTETES = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Accept-Language": "fr",
}


def _nombre(s: str) -> float | None:
    """« 38 500 » ou « 1 745,50 » -> float. Les cours BRVM sont en FCFA."""
    if s is None:
        return None
    t = re.sub(r"[\s\u00a0\u202f]", "", str(s)).replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def cote_du_jour(tickers: list[str], session: requests.Session | None = None,
                 timeout: int = 30) -> dict[str, dict]:
    """Derniers cours et variation du jour, lus dans le bandeau de cotation.

    Le bandeau apparaît sur toutes les pages du site ; on prend une page
    légère plutôt que l'accueil.
    """
    s = session or requests.Session()
    try:
        r = s.get(f"{RACINE}/fr/node/312", headers=_ENTETES, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException:
        return {}

    texte = re.sub(r"<[^>]+>", " ", r.text)
    texte = re.sub(r"[\u00a0\u202f]", " ", texte)

    resultat: dict[str, dict] = {}
    connus = set(tickers)
    motif = re.compile(
        r"\b(" + "|".join(sorted(connus, key=len, reverse=True)) + r")\b"
        r"\s+([0-9][0-9 ]*(?:[.,][0-9]+)?)"
        r"\s+(-?[0-9]+(?:[.,][0-9]+)?)\s*%"
    )
    for m in motif.finditer(texte):
        ticker, cours, var = m.group(1), _nombre(m.group(2)), _nombre(m.group(3))
        if cours is None:
            continue
        resultat[ticker] = {
            "cloture": cours,
            "variation_pct": var,
            "source": NOM_SITE,
            "recupere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    return resultat


_MOTIF_RAPPORT = re.compile(
    r'href="([^"]+\.pdf)"[^>]*>\s*([^<]{5,300}?)\s*<', re.IGNORECASE)


def rapports(slug_societe: str, session: requests.Session | None = None,
             timeout: int = 30) -> list[dict]:
    """Index des documents publiés par un émetteur.

    `slug_societe` est le segment d'URL de brvm.org, par exemple « sonatel »
    pour /fr/rapports-societe-cotes/sonatel. Ces slugs ne se déduisent pas du
    ticker : il faut les relever une fois depuis
    /fr/rapports-societes-cotees et les figer dans le référentiel.
    """
    s = session or requests.Session()
    url = f"{RACINE}/fr/rapports-societe-cotes/{slug_societe}"
    try:
        r = s.get(url, headers=_ENTETES, timeout=timeout)
        r.raise_for_status()
    except requests.RequestException:
        return []

    vus, docs = set(), []
    for lien, titre in _MOTIF_RAPPORT.findall(r.text):
        if lien.startswith("/"):
            lien = RACINE + lien
        if lien in vus:
            continue
        vus.add(lien)
        docs.append({
            "titre": re.sub(r"\s+", " ", titre).strip(),
            "url": lien,
            "source": NOM_SITE,
            "repere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    return docs


# ==========================================================================
# COLLECTE ET INDICATEURS
# ==========================================================================

RACINE = Path(__file__).resolve().parent
DOSSIER = RACINE / "data"

SEUIL_PERIME = 5          # séances sans mise à jour avant de marquer périmé
SEUIL_DIVERGENCE = 0.01   # 1 % d'écart entre sources -> on signale
SEANCES_PUBLIEES = 1300   # ~5 ans : ce dont l'application a besoin


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _seances_ecoulees(derniere: str) -> int:
    """Jours ouvrés écoulés depuis la dernière cotation (approximation :
    la BRVM cote du lundi au vendredi, hors jours fériés régionaux)."""
    try:
        d = date.fromisoformat(derniere)
    except ValueError:
        return 999
    n, curseur = 0, d
    while curseur < date.today():
        curseur = date.fromordinal(curseur.toordinal() + 1)
        if curseur.weekday() < 5:
            n += 1
    return n


def calendrier_marche(histoires: dict[str, list[dict]], n: int = 90) -> list[str]:
    """Les n dernières séances de bourse, tous titres confondus.

    Indispensable : les fichiers sources ne contiennent que les séances où le
    titre s'est effectivement échangé. Mesurer la liquidité d'un titre sur ses
    propres lignes donne 100 % pour tout le monde, y compris pour celui qui n'a
    coté que trois fois dans le trimestre. Le dénominateur doit venir du marché.
    """
    toutes = set()
    for lignes in histoires.values():
        toutes.update(l["date"] for l in lignes)
    return sorted(toutes)[-n:]


def indicateurs(lignes: list[dict], calendrier: list[str]) -> dict:
    """Indicateurs de liquidité et d'amplitude.

    La liquidité est le filtre qui compte le plus sur ce marché : un titre qui
    ne s'échange qu'une séance sur dix ne se revend pas à la demande, quelle
    que soit la qualité de ses comptes.
    """
    if not lignes or not calendrier:
        return {}
    debut = calendrier[0]
    jours = set(calendrier)
    fenetre = [l for l in lignes if l["date"] in jours]
    cloture = [l["cloture"] for l in lignes if l["date"] >= debut] or \
              [lignes[-1]["cloture"]]
    volumes = [l["volume"] for l in fenetre]
    valeurs = [l["cloture"] * l["volume"] for l in fenetre if l["volume"] > 0]

    an = lignes[-260:]
    cloture_an = [l["cloture"] for l in an]

    return {
        "seances_marche": len(calendrier),
        "seances_echangees": len(fenetre),
        "part_seances_echangees": round(len(fenetre) / len(calendrier), 3),
        "volume_median": int(statistics.median(volumes)) if volumes else 0,
        "valeur_mediane_par_seance": int(statistics.median(valeurs)) if valeurs else 0,
        "ordre_confortable": int(
            (statistics.median(valeurs) if valeurs else 0) * 0.10),
        "plus_haut_52s": max(cloture_an) if cloture_an else None,
        "plus_bas_52s": min(cloture_an) if cloture_an else None,
        "variation_52s_pct": (
            round((cloture_an[-1] / cloture_an[0] - 1) * 100, 2)
            if len(cloture_an) > 1 and cloture_an[0] else None
        ),
        "position_dans_range_52s": (
            round((cloture[-1] - min(cloture_an)) / (max(cloture_an) - min(cloture_an)), 3)
            if cloture_an and max(cloture_an) > min(cloture_an) else None
        ),
    }


def tranche_liquidite(ind: dict) -> str:
    """Palier de négociabilité, fondé sur les capitaux échangés.

    La fréquence de cotation ne discrimine plus rien : dans le marché actuel
    les 47 valeurs cotent quasiment toutes les séances. Ce qui varie, et d'un
    facteur plusieurs centaines, c'est le montant échangé. C'est lui qui
    détermine si un ordre passe sans déplacer le cours.
    """
    part = ind.get("part_seances_echangees")
    valeur = ind.get("valeur_mediane_par_seance", 0)
    if part is None:
        return "inconnue"
    if part < 0.50:
        return "illiquide"
    if valeur >= 20_000_000:
        return "liquide"
    if valeur >= 5_000_000:
        return "correcte"
    if valeur >= 1_000_000:
        return "etroite"
    return "illiquide"


def collecter(verifier_sika: bool = True) -> tuple[list[dict], dict]:
    session = requests.Session()
    univers, journal, divergences, echecs_sika = [], {}, [], []
    ok_miroir = 0

    # passe 1 : tout télécharger, puis établir le calendrier de marché
    histoires = {t: historique_miroir(t, session=session) for t in TICKERS}
    calendrier = calendrier_marche(histoires)

    # passe 2 : dériver les indicateurs sur ce calendrier commun
    for ticker in TICKERS:
        ref = dict(PAR_TICKER[ticker])
        ref["pays_libelle"] = PAYS.get(ref["pays"], ref["pays"])

        lignes = histoires[ticker]
        dernier = dernier_cours(lignes)

        if dernier:
            ok_miroir += 1
            ecoulees = _seances_ecoulees(dernier["date"])
            ref.update({
                "cours": dernier["cloture"],
                "date_cours": dernier["date"],
                "source_cours": NOM_MIROIR,
                "seances_ecoulees": ecoulees,
                "perime": ecoulees > SEUIL_PERIME,
                "profondeur_historique": len(lignes),
                "premiere_seance": lignes[0]["date"],
            })
            ref["indicateurs"] = indicateurs(lignes, calendrier)
            ref["liquidite"] = tranche_liquidite(ref["indicateurs"])
            (DOSSIER / "history").mkdir(parents=True, exist_ok=True)
            (DOSSIER / "history" / f"{ticker}.json").write_text(
                json.dumps({"ticker": ticker, "source": NOM_MIROIR,
                            "recupere_le": _maintenant(),
                            "seances": lignes[-SEANCES_PUBLIEES:]},
                           ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8")
        else:
            ref.update({"cours": None, "date_cours": None, "source_cours": None,
                        "seances_ecoulees": None, "perime": True,
                        "indicateurs": {}, "liquidite": "inconnue"})

        # Deuxième avis : on ne remplace rien, on compare.
        # Isolé dans un try : un contrôle qui échoue doit dégrader la
        # collecte, jamais l'interrompre. Les cours viennent du miroir ; si
        # Sika est injoignable ou change son API, on perd la vérification,
        # pas les données.
        if verifier_sika and dernier:
            try:
                autre = historique_sika(ref["symbole_sika"], jours=10,
                                        session=session)
            except Exception as e:          # noqa: BLE001 - dégradation voulue
                autre = []
                echecs_sika.append(f"{ticker}: {type(e).__name__}")
            if autre:
                ecart = abs(autre[-1]["cloture"] - dernier["cloture"]) / dernier["cloture"]
                ref["controle_sika"] = {
                    "cours": autre[-1]["cloture"],
                    "date": autre[-1]["date"],
                    "ecart_pct": round(ecart * 100, 2),
                }
                if ecart > SEUIL_DIVERGENCE:
                    divergences.append({
                        "ticker": ticker,
                        "miroir": dernier["cloture"], "sika": autre[-1]["cloture"],
                        "ecart_pct": round(ecart * 100, 2),
                    })

        univers.append(ref)

    journal["miroir-github"] = {
        "tickers_attendus": len(TICKERS), "tickers_obtenus": ok_miroir,
        "etat": "ok" if ok_miroir >= len(TICKERS) * 0.9 else "degrade",
    }
    if verifier_sika:
        controles = sum(1 for u in univers if "controle_sika" in u)
        journal["sika"] = {
            "tickers_controles": controles,
            "echecs": len(echecs_sika),
            "detail_echecs": echecs_sika[:5],
            # « injoignable » n'est pas un échec de collecte : le contrôle
            # croisé est un confort, le miroir est la source.
            "etat": "ok" if controles else "injoignable",
        }

    journal["calendrier"] = {"seances_retenues": len(calendrier),
                            "de": calendrier[0], "a": calendrier[-1]}

    meta = {
        "genere_le": _maintenant(),
        "sources": journal,
        "divergences": divergences,
        "perimes": [u["ticker"] for u in univers if u.get("perime")],
        "devise": "XOF",
        "parite_eur_fixe": 655.957,
        "avertissement": "Données de marché à titre informatif. "
                         "Ne constitue pas un conseil en investissement.",
    }
    return univers, meta


def main() -> int:
    ap = argparse.ArgumentParser(description="Collecte des données BRVM")
    ap.add_argument("--sans-sika", action="store_true",
                    help="ne pas croiser avec Sika Finance")
    args = ap.parse_args()

    DOSSIER.mkdir(parents=True, exist_ok=True)
    univers, meta = collecter(verifier_sika=not args.sans_sika)

    (DOSSIER / "universe.json").write_text(
        json.dumps(univers, ensure_ascii=False, indent=1), encoding="utf-8")
    (DOSSIER / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    cotes = sum(1 for u in univers if u["cours"])
    print(f"{cotes}/{len(univers)} titres cotés")
    print(f"périmés : {len(meta['perimes'])}  divergences : {len(meta['divergences'])}")
    for d in meta["divergences"][:10]:
        print(f"  {d['ticker']}: miroir {d['miroir']} / sika {d['sika']} "
              f"({d['ecart_pct']} %)")
    # collecte dégradée = échec visible dans l'Action, pas silence
    return 0 if meta["sources"]["miroir-github"]["etat"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

