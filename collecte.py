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
import math
import statistics
import unicodedata
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
# DIVIDENDES — historique officiel publié par la BRVM
# ==========================================================================

MOIS = {"janvier":1,"février":2,"fevrier":2,"mars":3,"avril":4,"mai":5,"juin":6,
        "juillet":7,"août":8,"aout":8,"septembre":9,"octobre":10,"novembre":11,
        "décembre":12,"decembre":12}

URL_ESV = "https://www.brvm.org/fr/esv/paiement-de-dividendes"

# Identifiants trouvés dans le nom de fichier de l'avis -> ticker.
# Les plus spécifiques d'abord : « sib_ci » ne doit pas capter « cbibf ».
SLUGS = [
    ("totalenergies_marketing_senegal","TTLS"),("totalenergies_marketing_ci","TTLC"),
    ("total_senegal","TTLS"),("total_ci","TTLC"),
    ("societe_generale_ci","SGBC"),("nsia_banque_ci","NSBC"),("nei-ceda_ci","NEIC"),
    ("nei_ceda_ci","NEIC"),("cfao_motors_ci","CFAC"),("vivo_energy_ci","SHEC"),
    ("coris_bank","CBIBF"),("cbibf","CBIBF"),("onatel_bf","ONTBF"),("onatel","ONTBF"),
    ("oragroup","ORGT"),("sonatel","SNTS"),("orange_ci","ORAC"),("nestle_ci","NTLC"),
    ("solibra","SLBC"),("unilever_ci","UNLC"),("uniwax","UNXC"),("sitab_ci","STBC"),
    ("sitab","STBC"),("filtisac","FTSC"),("sicable","CABC"),("sicor","SICC"),
    ("air_liquide","SIVC"),("crown_siem","SEMC"),("siem","SEMC"),
    ("saph_ci","SPHC"),("saph","SPHC"),("sogb_ci","SOGC"),("sogb","SOGC"),
    ("palm_ci","PALC"),("palmci","PALC"),("sucrivoire","SCRC"),
    ("smb_ci","SMBC"),("sode_ci","SDCC"),("sodeci","SDCC"),("cie_ci","CIEC"),
    ("setao","STAC"),("servair","ABJC"),("bernabe","BNBC"),("safca","SAFC"),
    ("tractafric","PRSC"),("bollore","SDSC"),("agl_ci","SDSC"),
    ("ecobank_ci","ECOC"),("eti_tg","ETIT"),("eti","ETIT"),
    ("bicici","BICC"),("bici_ci","BICC"),("biic","BICB"),
    ("boa_benin","BOAB"),("boa_bn","BOAB"),("boa_burkina","BOABF"),("boa_bf","BOABF"),
    ("boa_ci","BOAC"),("boa_mali","BOAM"),("boa_ml","BOAM"),("boa_niger","BOAN"),
    ("boa_ne","BOAN"),("boa_senegal","BOAS"),("boa_sn","BOAS"),
    ("sib_ci","SIBC"),("lnb","LNBB"),("loterie","LNBB"),
]

# Libellés affichés -> ticker, utilisés seulement si le nom de fichier ne dit rien.
LIBELLES = {
    "smb":"SMBC","sodeci":"SDCC","sode ci":"SDCC","nei-ceda ci":"NEIC","nei ceda ci":"NEIC",
    "vivo energy ci":"SHEC","saph ci":"SPHC","sgci":"SGBC","sgbci":"SGBC","nestle ci":"NTLC",
    "cfao motors ci":"CFAC","sitab":"STBC","sogb":"SOGC","sib":"SIBC","cie ci":"CIEC",
    "onatel bf":"ONTBF","palm ci":"PALC","nsbc":"NSBC","coris bank international":"CBIBF",
    "sonatel":"SNTS","orange ci":"ORAC","solibra":"SLBC","unilever ci":"UNLC","uniwax":"UNXC",
    "filtisac":"FTSC","sicable":"CABC","sicor":"SICC","sucrivoire":"SCRC","setao":"STAC",
    "servair abidjan":"ABJC","bernabe ci":"BNBC","safca":"SAFC","ecobank ci":"ECOC",
    "eti":"ETIT","eti tg":"ETIT","bicici":"BICC","biic":"BICB","oragroup":"ORGT",
    "boa benin":"BOAB","boa burkina faso":"BOABF","boa ci":"BOAC","boa mali":"BOAM",
    "boa niger":"BOAN","boa senegal":"BOAS","lnb":"LNBB",
    # Libellés effectivement servis par brvm.org, relevés sur une collecte réelle.
    # « NG » désigne ici le Niger : il n'y a pas de filiale nigériane cotée à la BRVM.
    "bank of africa bn":"BOAB","bank of africa benin":"BOAB",
    "bank of africa bf":"BOABF","bank of africa burkina faso":"BOABF",
    "bank of africa ci":"BOAC","bank of africa cote d ivoire":"BOAC",
    "bank of africa ml":"BOAM","bank of africa mali":"BOAM",
    "bank of africa ng":"BOAN","bank of africa niger":"BOAN",
    "bank of africa sn":"BOAS","bank of africa senegal":"BOAS",
    "boa bn":"BOAB","boa bf":"BOABF","boa ml":"BOAM","boa ng":"BOAN","boa sn":"BOAS",
    "bici ci":"BICC","bici":"BICC",
    # Libellés longs employés par les rubriques d'annonces, là où le tableau
    # des dividendes emploie des sigles.
    "societe generale ci":"SGBC","societe generale":"SGBC",
    "societe ivoirienne de banque":"SIBC","safca ci":"SAFC",
    "loterie nationale du benin":"LNBB","loterie nationale":"LNBB",
    "servair abidjan ci":"ABJC","nsia banque cote d ivoire":"NSBC",
    "nsia banque":"NSBC","ecobank cote d ivoire":"ECOC",
    "totalenergies marketing ci":"TTLC","totalenergies marketing senegal":"TTLS",
    "vivo energy ci":"SHEC","crown siem ci":"SEMC","crown siem":"SEMC",
    "air liquide ci":"SIVC","air liquide":"SIVC","sitab ci":"STBC",
    "nestle cote d ivoire":"NTLC","sonatel sn":"SNTS","sonatel senegal":"SNTS",
    "bollore africa logistics ci":"SDSC","bollore transport logistics":"SDSC",
    "coris bank international bf":"CBIBF","oragroup togo":"ORGT",
    "palm ci":"PALC","palmci":"PALC","sogb ci":"SOGC","sucrivoire ci":"SCRC",
    "filtisac ci":"FTSC","uniwax ci":"UNXC","unilever ci":"UNLC",
    "solibra ci":"SLBC","setao ci":"STAC","bernabe":"BNBC",
    "cfao motors":"CFAC","tractafric motors ci":"PRSC","smb ci":"SMBC",
    "sodeci ci":"SDCC","sode ci":"SDCC","cie cote d ivoire":"CIEC",
    "nei ceda":"NEIC","nei ceda ci":"NEIC","saph":"SPHC","sogb":"SOGC",
}


def _texte(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _date_fr(s: str) -> str | None:
    """« 18 septembre 2026 » -> « 2026-09-18 »."""
    m = re.search(r"(\d{1,2})\s+([A-Za-zéûôàè]+)\s+(\d{4})", s or "")
    if not m:
        return None
    mois = MOIS.get(m.group(2).lower())
    if not mois:
        return None
    try:
        return date(int(m.group(3)), mois, int(m.group(1))).isoformat()
    except ValueError:
        return None


def _montant(s: str) -> float | None:
    """« 1 707,2 FCFA » -> 1707.2 ; « 266,44625 FCFA » -> 266.44625."""
    m = re.search(r"([\d][\d\s\u00a0\u202f]*(?:,\d+)?)", s or "")
    if not m:
        return None
    try:
        return float(re.sub(r"[\s\u00a0\u202f]", "", m.group(1)).replace(",", "."))
    except ValueError:
        return None


def _plier_accents(s: str) -> str:
    """« SOCIÉTÉ » et « SOCIETE » doivent tomber au même endroit."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def ticker_de(libelle: str, url_avis: str) -> str | None:
    """Le nom de fichier de l'avis prime sur le libellé affiché.

    Le libellé varie d'une rubrique à l'autre : le tableau des dividendes
    écrit « SGCI » là où les annonces écrivent « SOCIETE GENERALE CI ».
    D'où le repli par inclusion, qui évite de recenser chaque variante.
    """
    u = (url_avis or "").lower()
    for slug, t in SLUGS:
        if slug in u:
            return t

    n = re.sub(r"[^a-z0-9 ]", " ", _plier_accents(libelle or "").lower())
    n = re.sub(r"\s+", " ", n).strip()
    if not n:
        return None
    if n in LIBELLES:
        return LIBELLES[n]

    # Repli : la clé connue la plus longue contenue dans le libellé. On exige
    # au moins quatre caractères pour éviter qu'un fragment comme « sib »
    # n'accroche « bicici » au passage.
    candidats = [(k, v) for k, v in LIBELLES.items()
                 if len(k) >= 4 and (f" {k} " in f" {n} " or n.startswith(k + " "))]
    if candidats:
        return max(candidats, key=lambda kv: len(kv[0]))[1]
    return None


def parser_page(html: str) -> tuple[list[dict], list[str]]:
    """Extrait les paiements d'une page. Renvoie (lignes, libellés non rapprochés)."""
    lignes, orphelins = [], []
    for bloc in re.split(r"<tr[^>]*>", html, flags=re.I)[1:]:
        cells = [_texte(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", bloc,
                                               re.I | re.S)]
        if len(cells) < 7:
            continue
        libelle, exercice = cells[0], cells[3]
        if not re.fullmatch(r"(19|20)\d{2}", exercice.strip()):
            continue
        lien = re.search(r'href="([^"]+\.pdf)"', bloc, re.I)
        url = lien.group(1) if lien else ""
        if url.startswith("/"):
            url = "https://www.brvm.org" + url

        t = ticker_de(libelle, url)
        if not t:
            # une cellule émetteur vide n'est pas un libellé qu'on n'a pas su lire :
            # c'est une ligne inexploitable, on la compte sans la nommer.
            orphelins.append(libelle.strip() or "(émetteur absent)")
            continue
        montant = _montant(cells[6])
        if montant is None:
            continue
        lignes.append({
            "ticker": t, "libelle_source": libelle, "exercice": int(exercice),
            "date_paiement": _date_fr(cells[4]), "date_ex": _date_fr(cells[5]),
            "montant_net": montant, "avis": url, "source": "brvm.org",
        })
    return lignes, orphelins


def collecter_dividendes(session, pages: int = 44, timeout: int = 30) -> tuple[list[dict], list[str]]:
    """Parcourt le tableau paginé. Les pages en échec sont sautées, pas fatales."""
    tout, orphelins = [], []
    for p in range(pages):
        url = URL_ESV if p == 0 else f"{URL_ESV}?page={p}"
        try:
            r = session.get(url, timeout=timeout,
                            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "fr"})
            r.raise_for_status()
        except Exception:                       # noqa: BLE001
            continue
        lignes, orph = parser_page(r.text)
        if not lignes and p > 0:
            break                               # fin de pagination
        tout.extend(lignes)
        orphelins.extend(orph)
    # dédoublonnage : un même exercice peut être republié (avis rectificatif)
    vus, net = set(), []
    for l in sorted(tout, key=lambda x: (x["ticker"], x["exercice"],
                                         x["date_paiement"] or "")):
        cle = (l["ticker"], l["exercice"])
        if cle in vus:
            net[-1] = l                         # on garde la publication la plus récente
            continue
        vus.add(cle)
        net.append(l)
    return net, sorted(set(orphelins))


def metriques_dividendes(paiements: list[dict], cours: float | None,
              aujourdhui: date | None = None) -> dict:
    """Régularité et rendement, à partir des seuls exercices effectivement payés.

    Le rendement est calculé sur le *dividende net* publié par la BRVM :
    c'est ce que l'actionnaire touche, pas le dividende brut voté.
    """
    if not paiements:
        return {"exercices_connus": 0}
    aujourdhui = aujourdhui or date.today()
    par_ex = {p["exercice"]: p for p in paiements}
    annees = sorted(par_ex)
    dernier = par_ex[annees[-1]]

    # exercices consécutifs payés en remontant depuis le plus récent
    consec, a = 1, annees[-1]
    while a - 1 in par_ex:
        consec += 1
        a -= 1

    # baisses d'un exercice au suivant, sur les exercices contigus
    baisses = [{"exercice": y, "de": par_ex[y-1]["montant_net"],
                "a": par_ex[y]["montant_net"]}
               for y in annees[1:]
               if y - 1 in par_ex and par_ex[y]["montant_net"] < par_ex[y-1]["montant_net"]]

    fenetre = [y for y in annees if y >= aujourdhui.year - 10]
    return {
        "exercices_connus": len(annees),
        "premier_exercice": annees[0],
        "dernier_exercice": annees[-1],
        "dernier_montant_net": dernier["montant_net"],
        "derniere_date_paiement": dernier["date_paiement"],
        "prochaine_date_ex": (dernier["date_ex"]
                              if dernier["date_ex"] and dernier["date_ex"] >= aujourdhui.isoformat()
                              else None),
        "exercices_payes_10a": len(fenetre),
        "exercices_consecutifs": consec,
        "baisses": baisses,
        "nb_baisses": len(baisses),
        "rendement_net_pct": (round(dernier["montant_net"] / cours * 100, 2)
                              if cours else None),
        "historique": [{"exercice": y, "montant_net": par_ex[y]["montant_net"],
                        "date_paiement": par_ex[y]["date_paiement"],
                        "avis": par_ex[y]["avis"]} for y in annees],
    }


# ==========================================================================
# VALORISATION — PER, capitalisation, taux de distribution
# ==========================================================================

RACINE_BRVM = "https://www.brvm.org"
ENTETES_VAL = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
           "Accept-Language": "fr"}

MOIS_FR = {"janvier":1,"février":2,"fevrier":2,"mars":3,"avril":4,"mai":5,"juin":6,
           "juillet":7,"août":8,"aout":8,"septembre":9,"octobre":10,"novembre":11,
           "décembre":12,"decembre":12}

AGE_PERIME = 400   # jours au-delà desquels la fiche est signalée comme ancienne


def _nb_val(s: str) -> float | None:
    if s is None:
        return None
    t = re.sub(r"[\s\u00a0\u202f]", "", str(s))
    t = t.replace(",", ".") if t.count(",") and not t.count(".") else t.replace(",", "")
    try:
        v = float(t)
        return v if v > 0 else None
    except ValueError:
        return None


def _champ_val(texte: str, etiquette: str) -> str | None:
    """Les fiches sont des paires « Étiquette: valeur » séparées par des balises."""
    m = re.search(re.escape(etiquette) + r"\s*:?\s*([^\n<]{1,60})", texte, re.I)
    return m.group(1).strip() if m else None


def _date_fiche(s: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+([A-Za-zéûôàè]+),?\s+(\d{4})", s or "")
    if not m:
        return None
    mois = MOIS_FR.get(m.group(2).lower())
    if not mois:
        return None
    try:
        return date(int(m.group(3)), mois, int(m.group(1))).isoformat()
    except ValueError:
        return None


def urls_symboles(html: str) -> dict[str, str]:
    """Relève, dans le bandeau de cotation, le lien de chaque ticker.

    Évite de deviner 47 alias Drupal, et suit automatiquement le site s'il
    republie une fiche sous un nouvel alias.
    """
    out = {}
    for href, libelle in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>\s*([A-Z]{3,5})\s*<',
                                    html):
        if re.fullmatch(r"[A-Z]{3,5}", libelle) and "/fr/" in href:
            out.setdefault(libelle, href if href.startswith("http") else RACINE_BRVM + href)
    return out


def parser_fiche(html: str) -> dict | None:
    """Extrait les quatre champs utiles d'une fiche symbole."""
    # Les sauts de ligne sont ce qui borne chaque valeur : on remplace les
    # balises par des retours et on ne compacte que les espaces horizontaux.
    # Tout aplatir ferait déborder la capture sur le champ suivant.
    txt = re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"<[^>]+>", "\n", html))
    per = _nb_val(_champ_val(txt, "PER"))
    capi = _nb_val(_champ_val(txt, "Capitalisation Boursière"))
    cours = _nb_val(_champ_val(txt, "Cours Clôture"))
    if not (per and cours):
        return None
    return {
        "per_fiche": per,
        "cours_fiche": cours,
        "capitalisation": capi,
        "date_fiche": _date_fiche(_champ_val(txt, "Trading Date") or ""),
        "symbole": (_champ_val(txt, "Code Symbole") or "").strip() or None,
    }


def derive_valorisation(fiche: dict, cours_actuel: float | None,
           dividende_net: float | None = None,
           aujourdhui: date | None = None) -> dict:
    """Calcule ce qui reste valable quand la fiche a vieilli.

    Le BPA implicite tient tant que les comptes publiés n'ont pas changé ;
    le PER de la fiche, lui, est périmé dès que le cours bouge.
    """
    aujourdhui = aujourdhui or date.today()
    bpa = fiche["cours_fiche"] / fiche["per_fiche"]
    actions = (fiche["capitalisation"] / fiche["cours_fiche"]
               if fiche.get("capitalisation") else None)

    age = None
    if fiche.get("date_fiche"):
        age = (aujourdhui - date.fromisoformat(fiche["date_fiche"])).days

    out = {
        "bpa_implicite": round(bpa, 2),
        "per_fiche": fiche["per_fiche"],
        "per_actuel": round(cours_actuel / bpa, 2) if cours_actuel and bpa else None,
        "actions_estimees": round(actions) if actions else None,
        "resultat_net_estime": (round(fiche["capitalisation"] / fiche["per_fiche"])
                                if fiche.get("capitalisation") else None),
        "date_comptes": fiche.get("date_fiche"),
        "age_jours": age,
        "fiche_ancienne": age is not None and age > AGE_PERIME,
    }
    if dividende_net and bpa:
        taux = dividende_net / bpa * 100
        out["taux_distribution_pct"] = round(taux, 1)
        # Le dividende publié est net de retenue, le BPA est brut : le taux
        # est donc minoré. On ne tranche que sur des écarts francs.
        out["distribution"] = ("superieure_aux_benefices" if taux > 100
                               else "elevee" if taux > 80
                               else "confortable" if taux > 0 else None)
    return out


def collecter_valorisation(session, tickers: list[str], cours: dict[str, float],
              dividendes: dict[str, float] | None = None,
              timeout: int = 30) -> tuple[dict[str, dict], list[str]]:
    """Renvoie ({ticker: valorisation}, tickers non résolus)."""
    dividendes = dividendes or {}
    try:
        r = session.get(f"{RACINE}/fr/indice-prestige", headers=ENTETES, timeout=timeout)
        r.raise_for_status()
        carte = urls_symboles(r.text)
    except Exception:                                    # noqa: BLE001
        carte = {}

    out, manquants = {}, []
    for t in tickers:
        url = carte.get(t)
        if not url:
            manquants.append(t)
            continue
        try:
            rr = session.get(url, headers=ENTETES, timeout=timeout)
            rr.raise_for_status()
            fiche = parser_fiche(rr.text)
        except Exception:                                # noqa: BLE001
            fiche = None
        if not fiche:
            manquants.append(t)
            continue
        out[t] = derive_valorisation(fiche, cours.get(t), dividendes.get(t))
        out[t]["url_fiche"] = url
    return out, manquants


# ==========================================================================
# ANNONCES DES ÉMETTEURS
# ==========================================================================

RUBRIQUES_ANN = {
    "communique": "/fr/emetteurs/type-annonces/communiques",
    "notation": "/fr/emetteurs/type-annonces/notations-financieres",
    "dirigeant": "/fr/emetteurs/type-annonces/changements-de-dirigeants",
    "seuil": "/fr/emetteurs/type-annonces/franchissements-de-seuil",
    "assemblee": "/fr/emetteurs/type-annonces/convocations-assemblees-generales",
    "resolution": "/fr/emetteurs/type-annonces/projets-de-resolution",
    "permanente": "/fr/informations-permanentes",
}

# Ordre significatif : le premier motif qui accroche l'emporte, donc les
# libellés les plus spécifiques d'abord.
TYPES_ANN = [
    (r"paiement de dividende", "dividende"),
    (r"états? financiers?|etats? financiers?", "etats_financiers"),
    (r"rapport d.?activit", "rapport_activite"),
    (r"notation", "notation"),
    (r"augmentation de capital|admission à la cote", "capital"),
    (r"assemblée|assemblee|convocation", "assemblee"),
    (r"résolution|resolution", "resolution"),
    (r"dirigeant|nomination|démission|demission", "dirigeant"),
    (r"franchissement|seuil", "seuil"),
    (r"contrat de liquidité|contrat de liquidite", "liquidite"),
]

# Ce qui mérite qu'on le remonte à un porteur de long terme, et ce qui relève
# de la formalité administrative.
IMPORTANTS_ANN = {"etats_financiers", "rapport_activite", "notation", "dividende",
              "capital", "seuil", "dirigeant"}


def _texte_ann(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h)).strip()


def _date_ann(s):
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def classer_annonce(titre):
    t = (titre or "").lower()
    for motif, nom in TYPES_ANN:
        if re.search(motif, t):
            return nom
    return "autre"


def emetteur_de(titre, resolveur):
    """Les titres s'écrivent « ÉMETTEUR : libellé du document ».

    On tente d'abord le segment avant le deux-points, puis le titre entier :
    certaines rubriques ne respectent pas la convention.
    """
    if not titre:
        return None
    avant = titre.split(":", 1)[0] if ":" in titre else titre
    return resolveur(avant, "") or resolveur(titre, "")


def parser_annonces(html, rubrique, resolveur):
    lignes = []
    for bloc in re.split(r"<tr[^>]*>", html, flags=re.I)[1:]:
        cells = [_texte_ann(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", bloc, re.I | re.S)]
        if not cells:
            continue
        d = next((_date_ann(c) for c in cells if _date_ann(c)), None)
        titre = max((c for c in cells if len(c) > 12 and not _date_ann(c)),
                    key=len, default="")
        if not titre or not d:
            continue
        lien = re.search(r'href="([^"]+\.pdf)"', bloc, re.I)
        url = lien.group(1) if lien else ""
        if url.startswith("/"):
            url = "https://www.brvm.org" + url
        typ = classer_annonce(titre)
        lignes.append({
            "date": d, "titre": titre, "rubrique": rubrique, "type": typ,
            "important": typ in IMPORTANTS_ANN, "url": url,
            "ticker": emetteur_de(titre, resolveur),
        })
    return lignes


def collecter_annonces(session, resolveur, pages=3, timeout=30):
    """Parcourt chaque rubrique sur ses premières pages : on veut le récent,
    pas l'archive. L'échec d'une rubrique n'interrompt pas les autres."""
    tout, echecs = [], []
    for nom, chemin in RUBRIQUES_ANN.items():
        obtenues = 0
        for p in range(pages):
            url = f"https://www.brvm.org{chemin}" + ("" if p == 0 else f"?page={p}")
            try:
                r = session.get(url, timeout=timeout,
                                headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "fr"})
                r.raise_for_status()
            except Exception:                       # noqa: BLE001
                break
            l = parser_annonces(r.text, nom, resolveur)
            if not l:
                break
            tout.extend(l)
            obtenues += len(l)
        if not obtenues:
            echecs.append(nom)
    vus, net = set(), []
    for a in sorted(tout, key=lambda x: x["date"], reverse=True):
        cle = (a["date"], a["titre"][:80])
        if cle not in vus:
            vus.add(cle)
            net.append(a)
    return net, echecs


# ==========================================================================
# ÉTATS FINANCIERS — extraction des PDF publiés
# ==========================================================================

# Multiplicateurs déclarés dans les en-têtes de section.
ECHELLES = [
    (r"en\s+milliards?\s+(?:de\s+)?", 1_000_000_000),
    (r"en\s+millions?\s+(?:de\s+)?", 1_000_000),
    (r"en\s+milliers?\s+(?:de\s+)?", 1_000),
]
DEVISES = [
    (r"f\s?cfa|francs?\s+cfa|xof", "XOF"),
    (r"dollars?\s*(?:eu|us|américains?)?|\$\s?eu|usd", "USD"),
    (r"euros?|€|eur", "EUR"),
]

# Ordre significatif : le libellé le plus spécifique doit gagner.
POSTES = [
    ("resultat_net", [
        r"r[ée]sultat\s+net\s+consolid[ée]",
        r"r[ée]sultat\s+net\s+de\s+l.exercice",
        r"r[ée]sultat\s+net(?!\s+par\s+action)(?!\s*,\s*part)",
        r"b[ée]n[ée]fice\s+net",
    ]),
    ("produit_exploitation", [
        r"produit\s+net\s+bancaire",
        r"chiffre\s+d.affaires\s+net",
        r"chiffre\s+d.affaires",
        r"produits?\s+d.exploitation",
    ]),
    ("capitaux_propres", [
        r"total\s+(?:des\s+)?capitaux\s+propres(?!\s*,\s*part)",
        r"capitaux\s+propres(?!\s*,\s*part)(?!\s+part)",
        r"total\s+fonds\s+propres",
    ]),
    ("total_bilan", [
        r"total\s+(?:de\s+l.)?actif",
        r"total\s+du\s+bilan",
        r"total\s+bilan",
    ]),
]

# En français le séparateur de milliers est l'espace — le même caractère qui
# sépare deux colonnes. « 406 923 366 691 » est donc illisible hors contexte :
# 406 milliards, ou bien 406 923 et 366 691 côte à côte ? On découpe d'abord
# en groupes, puis on tranche sur la forme (voir _colonnes).
_GROUPE = re.compile(r"\(?-?\d{1,3}(?:[\s\u00a0\u202f]\d{3})*(?:[.,]\d+)?\)?")


def _groupes(txt: str) -> list[str]:
    return re.split(r"[\s\u00a0\u202f]", re.sub(r"[()]", "", txt).strip())


def _colonnes(reste: str) -> list[float]:
    """Les nombres d'une ligne comptable, colonnes séparées.

    Quand un candidat compte un nombre pair de groupes de trois chiffres, il
    s'agit presque toujours de deux colonnes accolées (exercice N et N-1). On
    ne coupe que si les deux moitiés sont du même ordre de grandeur : deux
    exercices consécutifs se ressemblent, un vrai nombre coupé en deux non.
    """
    out = []
    for m in _GROUPE.finditer(reste):
        brut = m.group()
        neg = brut.strip().startswith("(")
        gr = _groupes(brut)
        coupe = None
        if len(gr) >= 4 and len(gr) % 2 == 0 and all(len(g) == 3 for g in gr[1:]):
            moitie = len(gr) // 2
            if len(gr[moitie]) == 3:
                a, b = _valeur_fin(" ".join(gr[:moitie])), _valeur_fin(" ".join(gr[moitie:]))
                if a and b and 0.2 <= a / b <= 5:
                    coupe = [a, b]
        vals = coupe if coupe else [_valeur_fin(brut)]
        for v in vals:
            if v is not None:
                out.append(-abs(v) if neg else v)
    return out


def _valeur_fin(txt: str) -> float | None:
    neg = txt.strip().startswith("(")
    t = re.sub(r"[()\s\u00a0\u202f]", "", txt)
    t = t.replace(",", ".") if re.search(r",\d{1,2}$", t) else t.replace(",", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def unite_financiere(ligne: str) -> tuple[int | None, str | None]:
    """Lit « (Montants en milliers de Dollars EU) » -> (1000, 'USD')."""
    l = ligne.lower()
    echelle = next((m for motif, m in ECHELLES if re.search(motif, l)), None)
    devise = next((d for motif, d in DEVISES if re.search(motif, l)), None)
    return echelle, devise


def extraire_etats(texte: str, devise_attendue: str = "XOF") -> dict:
    """Renvoie {poste: {...}} pour ce que le document permet d'affirmer.

    Un poste n'est retenu que si la section qui le porte déclare une échelle
    et une devise. Les candidats contradictoires sont conservés et signalés
    plutôt qu'arbitrés.
    """
    echelle = devise = None
    candidats: dict[str, list] = {}

    for brute in texte.splitlines():
        ligne = re.sub(r"[ \t\u00a0\u202f]+", " ", brute).strip()
        if not ligne:
            continue

        # Une déclaration d'unité vaut pour tout ce qui suit, jusqu'à la suivante.
        if re.search(r"montants?\s+en|exprim[ée]s?\s+en|\(en\s+", ligne, re.I):
            e, d = unite_financiere(ligne)
            if e or d:
                echelle, devise = e or echelle, d or devise
                continue

        bas = ligne.lower()
        for poste, motifs in POSTES:
            motif = next((m for m in motifs if re.search(r"^\s*" + m, bas)), None)
            if not motif:
                continue
            reste = ligne[re.search(motif, bas).end():]
            nombres = [v for v in _colonnes(reste) if abs(v) > 0]
            if not nombres:
                continue
            if echelle is None or devise is None:
                candidats.setdefault(poste, []).append(
                    {"valeur": None, "motif_rejet": "unite_non_declaree", "ligne": ligne[:120]})
                continue
            candidats.setdefault(poste, []).append({
                "valeur": nombres[0] * echelle, "devise": devise,
                "echelle": echelle, "ligne": ligne[:120],
                "nb_colonnes": len(nombres),
            })
            break

    out = {}
    for poste, liste in candidats.items():
        valides = [c for c in liste if c.get("valeur") is not None]
        if not valides:
            out[poste] = {"valeur": None, "confiance": "aucune",
                          "raison": liste[0].get("motif_rejet", "illisible")}
            continue
        # Une ligne à deux colonnes est un compte de résultat (exercice N et
        # N-1) ; au-delà, c'est un tableau de synthèse mêlant les devises, donc
        # moins sûr.
        valides.sort(key=lambda c: (c["nb_colonnes"] != 2, -abs(c["valeur"])))
        retenu = valides[0]
        ecarts = {round(c["valeur"], 2) for c in valides if c["devise"] == retenu["devise"]}
        confiance = ("elevee" if len(ecarts) == 1 and retenu["nb_colonnes"] == 2
                     else "moyenne" if len(ecarts) <= 2 else "faible")
        if retenu["devise"] != devise_attendue:
            confiance = "a_convertir"
        out[poste] = {
            "valeur": retenu["valeur"], "devise": retenu["devise"],
            "confiance": confiance, "candidats": len(valides),
            "source_ligne": retenu["ligne"],
        }
    return out


def ratios_etats(postes: dict, dividende_net: float | None = None,
           actions: float | None = None) -> dict:
    """Taux de distribution et marge, uniquement si les bases sont fiables."""
    out = {}
    rn = postes.get("resultat_net") or {}
    ca = postes.get("produit_exploitation") or {}
    cp = postes.get("capitaux_propres") or {}

    fiable = lambda p: p.get("valeur") and p.get("confiance") in ("elevee", "moyenne")

    if fiable(rn) and fiable(ca) and ca["valeur"]:
        out["marge_nette_pct"] = round(rn["valeur"] / ca["valeur"] * 100, 1)
    if fiable(rn) and fiable(cp) and cp["valeur"]:
        out["rentabilite_fonds_propres_pct"] = round(rn["valeur"] / cp["valeur"] * 100, 1)
    if fiable(rn) and dividende_net and actions:
        total_verse = dividende_net * actions
        out["taux_distribution_pct"] = round(total_verse / rn["valeur"] * 100, 1)
        out["base_taux"] = "etats_financiers"
    return out


# ---------------------------------------------------------------------------
# Récupération des PDF sur brvm.org
# ---------------------------------------------------------------------------


RACINE_SITE = "https://www.brvm.org"
TID_ETATS = 57          # filtre « Etats Financiers » de la vue Drupal
ENTETES_PDF = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
               "Accept-Language": "fr"}


def slugs_emetteurs(session, timeout: int = 30) -> dict[str, str]:
    """Relève les slugs des pages « rapports société » depuis l'index.

    Les slugs (« sonatel », « onatel-bf ») ne se déduisent pas du ticker ;
    l'index les publie tous, autant les lire que les deviner.
    """
    try:
        r = session.get(f"{RACINE_SITE}/fr/rapports-societes-cotees",
                        headers=ENTETES_PDF, timeout=timeout)
        r.raise_for_status()
    except Exception:                                       # noqa: BLE001
        return {}
    out = {}
    for href, libelle in re.findall(
            r'href="(/fr/rapports-societe-cotes/[^"]+)"[^>]*>([^<]{2,80})<', r.text):
        out[re.sub(r"\s+", " ", libelle).strip()] = RACINE_SITE + href
    return out


def dernier_etat_financier(session, url_societe: str, timeout: int = 30) -> dict | None:
    """Le PDF d'états financiers le plus récent publié par un émetteur."""
    try:
        r = session.get(f"{url_societe}?field_type_rapport_tid={TID_ETATS}",
                        headers=ENTETES_PDF, timeout=timeout)
        r.raise_for_status()
    except Exception:                                       # noqa: BLE001
        return None
    liens = re.findall(r'href="([^"]+\.pdf)"', r.text, re.I)
    if not liens:
        return None
    url = liens[0]
    if url.startswith("/"):
        url = RACINE_SITE + url
    # Le nom de fichier commence par la date de publication : AAAAMMJJ_-_…
    m = re.search(r"/(\d{8})_", url)
    return {"url": url,
            "publie_le": (f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
                          if m else None)}


def texte_du_pdf(session, url: str, timeout: int = 60, pages_max: int = 12) -> tuple[str, str]:
    """Texte d'un PDF distant. Renvoie (texte, état).

    Un état financier scanné n'a pas de couche texte : pdfplumber renvoie du
    vide. On le signale comme « scanne » plutôt que de le traiter comme un
    document sans chiffres — c'est une limite connue, pas une absence de
    données.
    """
    try:
        import pdfplumber
    except ImportError:
        return "", "pdfplumber_absent"
    try:
        r = session.get(url, headers=ENTETES_PDF, timeout=timeout)
        r.raise_for_status()
    except Exception:                                       # noqa: BLE001
        return "", "telechargement_echoue"
    try:
        morceaux = []
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for page in pdf.pages[:pages_max]:
                morceaux.append(page.extract_text() or "")
        texte = "\n".join(morceaux)
    except Exception:                                       # noqa: BLE001
        return "", "pdf_illisible"
    if len(texte.strip()) < 200:
        return texte, "scanne"
    return texte, "ok"


# ==========================================================================
# COLLECTE ET INDICATEURS
# ==========================================================================

_HISTOIRES: dict = {}
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


def collecter(verifier_sika: bool = True, avec_dividendes: bool = True,
              avec_valorisation: bool = True, avec_annonces: bool = True,
              avec_etats: bool = True) -> tuple[list[dict], dict]:
    session = requests.Session()
    univers, journal, divergences, echecs_sika = [], {}, [], []
    ok_miroir = 0

    # passe 1 : tout télécharger, puis établir le calendrier de marché
    global _HISTOIRES
    histoires = _HISTOIRES = {t: historique_miroir(t, session=session) for t in TICKERS}
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

    if avec_dividendes:
        paiements, orphelins = collecter_dividendes(session)
        par_ticker: dict[str, list] = {}
        for p in paiements:
            par_ticker.setdefault(p["ticker"], []).append(p)
        for u in univers:
            u["dividendes"] = metriques_dividendes(
                par_ticker.get(u["ticker"], []), u.get("cours"))
        couverts = sum(1 for u in univers if u["dividendes"]["exercices_connus"])
        journal["dividendes"] = {
            "paiements": len(paiements),
            "titres_couverts": couverts,
            "titres_sans_historique": [u["ticker"] for u in univers
                                       if not u["dividendes"]["exercices_connus"]],
            "libelles_non_rapproches": orphelins,
            "etat": "ok" if couverts >= 20 else "degrade",
        }
        (DOSSIER / "dividends.json").write_text(
            json.dumps(paiements, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        journal["dividendes"] = {"etat": "ignore"}

    if avec_valorisation:
        cours_map = {u["ticker"]: u["cours"] for u in univers if u["cours"]}
        div_map = {u["ticker"]: (u.get("dividendes") or {}).get("dernier_montant_net")
                   for u in univers}
        div_map = {k: v for k, v in div_map.items() if v}
        vals, manquants = collecter_valorisation(session, TICKERS, cours_map, div_map)
        for u in univers:
            u["valorisation"] = vals.get(u["ticker"])
        anciennes = sum(1 for v in vals.values() if v.get("fiche_ancienne"))
        journal["valorisation"] = {
            "titres_resolus": len(vals), "titres_manquants": manquants,
            "fiches_anciennes": anciennes,
            "etat": "ok" if len(vals) >= 30 else "degrade",
        }
    else:
        journal["valorisation"] = {"etat": "ignore"}

    if avec_annonces:
        annonces, echecs = collecter_annonces(session, ticker_de)
        par_t: dict[str, list] = {}
        for a in annonces:
            if a["ticker"]:
                par_t.setdefault(a["ticker"], []).append(a)
        for u in univers:
            u["annonces"] = par_t.get(u["ticker"], [])[:12]
        journal["annonces"] = {
            "total": len(annonces),
            "rattachees": sum(1 for a in annonces if a["ticker"]),
            "rubriques_en_echec": echecs,
            "etat": "ok" if len(annonces) > 20 else "degrade",
        }
        (DOSSIER / "annonces.json").write_text(
            json.dumps(annonces, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        journal["annonces"] = {"etat": "ignore"}

    if avec_etats:
        slugs = slugs_emetteurs(session)
        res_ok = scannes = 0
        for u in univers:
            cible = next((v for k, v in slugs.items()
                          if ticker_de(k, "") == u["ticker"]), None)
            if not cible:
                continue
            doc = dernier_etat_financier(session, cible)
            if not doc:
                continue
            texte, etat = texte_du_pdf(session, doc["url"])
            if etat != "ok":
                u["etats"] = {"etat": etat, "url": doc["url"],
                              "publie_le": doc["publie_le"]}
                scannes += etat == "scanne"
                continue
            postes = extraire_etats(texte)
            val = u.get("valorisation") or {}
            div = (u.get("dividendes") or {}).get("dernier_montant_net")
            u["etats"] = {"etat": "ok", "url": doc["url"],
                          "publie_le": doc["publie_le"], "postes": postes,
                          "ratios": ratios_etats(postes, div,
                                                 val.get("actions_estimees"))}
            res_ok += 1
        journal["etats_financiers"] = {
            "titres_extraits": res_ok, "documents_scannes": scannes,
            "etat": "ok" if res_ok >= 15 else "degrade",
        }
    else:
        journal["etats_financiers"] = {"etat": "ignore"}

    journal["calendrier"] = {"seances_retenues": len(calendrier),
                            "de": calendrier[0], "a": calendrier[-1]}

    meta = {
        "genere_le": _maintenant(),
        "sources": journal,
        "divergences": divergences,
        "perimes": [u["ticker"] for u in univers if u.get("perime")],
        "devise": "XOF",
        "parite_eur_fixe": 655.957,
        "date_seance": max((u["date_cours"] for u in univers if u["date_cours"]),
                           default=None),
        "avertissement": "Données de marché à titre informatif. "
                         "Ne constitue pas un conseil en investissement.",
    }
    return univers, meta


def hebdomadaire(lignes: list[dict], n: int = 260) -> list[int]:
    """Une clôture par semaine ISO : de quoi tracer cinq ans sans transporter
    1 300 points par titre jusqu'au téléphone."""
    vu, out = set(), []
    for s in lignes:
        d = date.fromisoformat(s["date"])
        cle = d.isocalendar()[:2]
        if cle not in vu:
            vu.add(cle)
            out.append(round(s["cloture"]))
    return out[-n:]


def volatilite(hebdo: list[int]) -> float | None:
    """Volatilité annualisée, à partir des variations hebdomadaires."""
    if len(hebdo) < 10:
        return None
    rets = [math.log(hebdo[i] / hebdo[i - 1])
            for i in range(1, len(hebdo)) if hebdo[i - 1] > 0]
    if len(rets) < 8:
        return None
    return round(statistics.pstdev(rets) * math.sqrt(52) * 100, 1)


def ecrire_app(univers: list[dict], histoires: dict, meta: dict) -> None:
    """Écrit data/app.json : exactement ce que lit l'application, et rien de plus.

    Sans ce fichier l'application devrait charger universe.json plus 47
    fichiers d'historique pour afficher une fiche. Ici elle fait une requête.
    """
    titres = []
    for u in univers:
        i = u.get("indicateurs") or {}
        w = hebdomadaire(histoires.get(u["ticker"], []))
        d = u.get("dividendes") or {}
        v = u.get("valorisation") or {}
        ann = u.get("annonces") or []
        ef = u.get("etats") or {}
        titres.append({
            "t": u["ticker"], "n": u["emetteur"], "p": u["pays_libelle"],
            "s": u["secteur"], "c": u["cours"], "d": u["date_cours"],
            "l": u["liquidite"], "pe": u.get("perime"),
            "v": i.get("valeur_mediane_par_seance"), "o": i.get("ordre_confortable"),
            "h": i.get("plus_haut_52s"), "b": i.get("plus_bas_52s"),
            "va": i.get("variation_52s_pct"), "r": i.get("position_dans_range_52s"),
            "h5": max(w) if w else None, "b5": min(w) if w else None,
            # Calculés ici et non dans l'application : elle ne reçoit que les
            # clôtures hebdomadaires, pas de quoi les recalculer fidèlement.
            "vol": volatilite(w),
            "dd": (round(min(0.0, (u["cours"] - max(w)) / max(w) * 100), 1)
                   if w and u.get("cours") else None),
            "w": w,
            "div": {
                "n": d.get("exercices_connus", 0),
                "consec": d.get("exercices_consecutifs"),
                "dix": d.get("exercices_payes_10a"),
                "baisses": d.get("nb_baisses"),
                "montant": d.get("dernier_montant_net"),
                "exercice": d.get("dernier_exercice"),
                "rdt": d.get("rendement_net_pct"),
                "ex": d.get("prochaine_date_ex"),
                "hist": [[x["exercice"], x["montant_net"]]
                         for x in d.get("historique", [])],
            } if d.get("exercices_connus") else None,
            "val": {
                "per": v.get("per_actuel"), "bpa": v.get("bpa_implicite"),
                "payout": v.get("taux_distribution_pct"),
                "niveau": v.get("distribution"),
                "comptes": v.get("date_comptes"), "vieux": v.get("fiche_ancienne"),
            } if v.get("bpa_implicite") else None,
            "fin": {
                "ok": ef.get("etat") == "ok",
                "etat": ef.get("etat"), "publie_le": ef.get("publie_le"),
                "url": ef.get("url"),
                "rn": (ef.get("postes", {}).get("resultat_net") or {}).get("valeur"),
                "rn_conf": (ef.get("postes", {}).get("resultat_net") or {}).get("confiance"),
                "cp": (ef.get("postes", {}).get("capitaux_propres") or {}).get("valeur"),
                "ca": (ef.get("postes", {}).get("produit_exploitation") or {}).get("valeur"),
                "marge": ef.get("ratios", {}).get("marge_nette_pct"),
                "roe": ef.get("ratios", {}).get("rentabilite_fonds_propres_pct"),
                "payout": ef.get("ratios", {}).get("taux_distribution_pct"),
            } if ef else None,
            "ann": [{"d": a["date"], "t": a["type"], "i": a["important"],
                     "x": a["titre"][:140], "u": a["url"]} for a in ann[:8]] or None,
        })
    (DOSSIER / "app.json").write_text(
        json.dumps({"titres": titres, "date_seance": meta["date_seance"],
                    "genere_le": meta["genere_le"],
                    "dividendes_etat": meta["sources"].get("dividendes", {})},
                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Collecte des données BRVM")
    ap.add_argument("--sans-etats", action="store_true",
                    help="ne pas extraire les états financiers PDF")
    ap.add_argument("--sans-annonces", action="store_true",
                    help="ne pas collecter les annonces des émetteurs")
    ap.add_argument("--sans-valorisation", action="store_true",
                    help="ne pas collecter PER et capitalisation")
    ap.add_argument("--sans-dividendes", action="store_true",
                    help="ne pas collecter l'historique des dividendes")
    ap.add_argument("--sans-sika", action="store_true",
                    help="ne pas croiser avec Sika Finance")
    args = ap.parse_args()

    DOSSIER.mkdir(parents=True, exist_ok=True)
    univers, meta = collecter(verifier_sika=not args.sans_sika,
                              avec_dividendes=not args.sans_dividendes,
                              avec_valorisation=not args.sans_valorisation,
                              avec_annonces=not args.sans_annonces,
                              avec_etats=not args.sans_etats)

    (DOSSIER / "universe.json").write_text(
        json.dumps(univers, ensure_ascii=False, indent=1), encoding="utf-8")
    (DOSSIER / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    ecrire_app(univers, _HISTOIRES, meta)

    cotes = sum(1 for u in univers if u["cours"])
    print(f"{cotes}/{len(univers)} titres cotés")
    d = meta["sources"].get("dividendes", {})
    if d.get("etat") not in (None, "ignore"):
        print(f"dividendes : {d['paiements']} paiements, "
              f"{d['titres_couverts']}/{len(univers)} titres couverts")
        if d["libelles_non_rapproches"]:
            print("  libellés non rapprochés :", ", ".join(d["libelles_non_rapproches"][:8]))
    vv = meta["sources"].get("valorisation", {})
    if vv.get("etat") not in (None, "ignore"):
        print(f"valorisation : {vv['titres_resolus']}/{len(univers)} fiches, "
              f"{vv['fiches_anciennes']} anciennes")
        if vv["titres_manquants"]:
            print("  sans fiche :", ", ".join(vv["titres_manquants"][:10]))
    aa = meta["sources"].get("annonces", {})
    if aa.get("etat") not in (None, "ignore"):
        print(f"annonces : {aa['total']} relevées, {aa['rattachees']} rattachées à un titre")
        if aa["rubriques_en_echec"]:
            print("  rubriques en échec :", ", ".join(aa["rubriques_en_echec"]))
    ef = meta["sources"].get("etats_financiers", {})
    if ef.get("etat") not in (None, "ignore"):
        print(f"états financiers : {ef['titres_extraits']} extraits, "
              f"{ef['documents_scannes']} scannés (illisibles sans OCR)")
    print(f"périmés : {len(meta['perimes'])}  divergences : {len(meta['divergences'])}")
    for d in meta["divergences"][:10]:
        print(f"  {d['ticker']}: miroir {d['miroir']} / sika {d['sika']} "
              f"({d['ecart_pct']} %)")
    # collecte dégradée = échec visible dans l'Action, pas silence
    return 0 if meta["sources"]["miroir-github"]["etat"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
