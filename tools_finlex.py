"""
tools_finlex.py – Finlex MCP -työkalut (6 kpl).

Kaikki työkalut ovat asynkronisia funktioita, jotka palauttavat merkkijonon.
Finlex API:n User-Agent on pakollinen jokaisessa pyynnössä.

Huomio dokumenttityypeistä:
  Säädökset (act):
    - statute            = lait ja asetukset (Suomen säädöskokoelma)
    - statute-consolidated = konsolidoitu versio (voimassa oleva teksti)
  Ratkaisut (judgment):
    - chancellor-of-justice-decision       = Oikeuskanslerinviraston päätökset
    - data-protection-ombudsman-decision   = Tietosuojavaltuutetun päätökset
  Asiakirjat (doc):
    - government-proposal = Hallituksen esitykset (HE)
"""

import re
from typing import Optional

from finlex_client import (
    CHAR_LIMIT,
    fetch_doc_xml,
    fetch_judgment_xml,
    fetch_statute_xml,
    format_result,
    list_docs,
    list_judgments,
    list_statutes,
    parse_akn_xml,
)


# ---------------------------------------------------------------------------
# Apufunktiot
# ---------------------------------------------------------------------------

def _uri_to_metadata(uri: str) -> dict:
    """
    Pura Finlex-URI:sta vuosi, numero ja kieli.
    Esim: .../akn/fi/act/statute/2024/123/fin@ -> {year:2024, number:123, lang:fin}
    """
    parts = uri.rstrip("/").split("/")
    result = {}
    try:
        # Etsi numeroa edeltävä kohta
        # URI muoto: .../act/{type}/{year}/{number}/{lang}@
        # tai: .../judgment/{type}/{year}/{number}/{lang}@
        lang_ver = parts[-1]
        lang = lang_ver.replace("%40", "").replace("@", "").strip()
        result["lang"] = lang if lang else "fin"
        number = parts[-2]
        year = parts[-3]
        result["number"] = number
        result["year"] = year
        doc_type = parts[-4]
        result["doc_type"] = doc_type
    except IndexError:
        pass
    return result


# ---------------------------------------------------------------------------
# Työkalu 1: Hae säädösluettelo
# ---------------------------------------------------------------------------

async def search_statutes(
    start_year: int,
    end_year: int,
    statute_type: str = "act",
    lang: str = "fin",
    page: int = 1,
) -> str:
    """
    Hae säädösluettelo Finlexistä vuosivälin perusteella.

    Palauttaa listan säädöksistä (URI, vuosi, numero, kieli, tila).
    Käytä tätä työkalua, kun haluat selata tiettynä vuonna annettuja säädöksiä.

    Parametrit:
        start_year: Aloitusvuosi (esim. 2024)
        end_year: Lopetusvu​osi (esim. 2024)
        statute_type: Säädöstyyppi. Tuetut arvot:
            - "act" = laki
            - "decree" = asetus
            - "decision" = päätös
            - "announcement" = ilmoitus
            - "official-regulation" = virallinen asetus
            (Muut: announcement, budget, confirmation, declaration, instructions,
             letter, list, notice, order, rules-of-procedure, statement)
        lang: Kielikoodi. "fin" = suomi (oletus), "swe" = ruotsi
        page: Sivunumero hakutuloksissa (oletus: 1, sivukoko: 10)

    Palauttaa: Merkkijono, jossa luettelo säädöksistä (URI ja tila).

    Esimerkki: search_statutes(start_year=2024, end_year=2024, statute_type="act")
    """
    try:
        items = list_statutes(
            start_year=start_year,
            end_year=end_year,
            statute_type=statute_type,
            lang_and_version=f"{lang}@",
            page=page,
            limit=10,
        )
        if not items:
            return f"Ei tuloksia haulla: vuodet {start_year}–{end_year}, tyyppi '{statute_type}', kieli '{lang}'."

        lines = [f"Säädöshaku: {start_year}–{end_year}, tyyppi={statute_type}, kieli={lang}, sivu={page}",
                 f"Tuloksia: {len(items)} kpl\n"]
        for item in items:
            uri = item.get("akn_uri", "")
            status = item.get("status", "")
            meta = _uri_to_metadata(uri)
            year = meta.get("year", "?")
            number = meta.get("number", "?")
            item_lang = meta.get("lang", "?")
            lines.append(f"  {number}/{year} ({item_lang}) – {status}")
            lines.append(f"    URI: {uri}")

        lines.append(f"\nHae säädöksen teksti: get_statute_text(year=VUOSI, number=NUMERO)")
        return "\n".join(lines)

    except Exception as e:
        return f"Virhe säädöshaossa: {e}"


# ---------------------------------------------------------------------------
# Työkalu 2: Hae säädöksen teksti
# ---------------------------------------------------------------------------

async def get_statute_text(
    year: int,
    number: int,
    lang: str = "fin",
    section: Optional[str] = None,
) -> str:
    """
    Hae yksittäisen säädöksen koko teksti Finlexistä.

    Hakee säädöksen vuoden ja numeron perusteella (Suomen säädöskokoelman viittausmuoto).
    Palauttaa Akoma Ntoso -muotoisen XML-dokumentin tekstimuodossa.

    Ensin yritetään hakea alkuperäistä säädöstä (statute), sitten konsolidoitua
    versiota (statute-consolidated), jos alkuperäistä ei löydy.

    Parametrit:
        year: Säädöksen antamisvuosi (esim. 2001)
        number: Säädöksen numero (esim. 55)
        lang: Kielikoodi – "fin" = suomi (oletus), "swe" = ruotsi
        section: Valinnainen pykäläfiltteri (esim. "3" → luku/pykälä 3).
                 Tällä hetkellä ei suodateta – palautetaan koko teksti.

    Palauttaa: Säädöksen teksti merkkijonona (max 25 000 merkkiä).
               Jos dokumentti on pitkä, se katkaistaan ja lisätään huomio.

    Esimerkki:
        get_statute_text(year=2001, number=55)   → Työsopimuslaki
        get_statute_text(year=1889, number=39)   → Rikoslaki
        get_statute_text(year=1999, number=731)  → Suomen perustuslaki
    """
    try:
        xml_content = fetch_statute_xml(year, number, lang, "statute")
        parsed = parse_akn_xml(xml_content)
        result = format_result(parsed)
        if len(result) < 50:
            # Yritetään konsolidoitua versiota
            xml_content2 = fetch_statute_xml(year, number, lang, "statute-consolidated")
            parsed2 = parse_akn_xml(xml_content2)
            result2 = format_result(parsed2)
            if len(result2) > len(result):
                return result2
        return result
    except Exception as e:
        # Yritetään konsolidoitua versiota
        try:
            xml_content = fetch_statute_xml(year, number, lang, "statute-consolidated")
            parsed = parse_akn_xml(xml_content)
            return format_result(parsed)
        except Exception as e2:
            return f"Säädöstä {number}/{year} ei löydy. Virhe: {e} | {e2}"


# ---------------------------------------------------------------------------
# Työkalu 3: Hae säädös viittauksen perusteella
# ---------------------------------------------------------------------------

async def get_statute_by_citation(
    citation: str,
    lang: str = "fin",
) -> str:
    """
    Hae säädös suomalaisen säädösviittauksen perusteella (muoto numero/vuosi).

    Tunnistaa automaattisesti "numero/vuosi" -muodon (esim. "55/2001") ja
    hakee kyseisen säädöksen tekstin Finlexistä.

    Parametrit:
        citation: Säädösviittaus muodossa "numero/vuosi" (esim. "55/2001", "731/1999")
        lang: Kielikoodi – "fin" = suomi (oletus), "swe" = ruotsi

    Palauttaa: Säädöksen teksti tai virheilmoitus.

    Esimerkkejä:
        get_statute_by_citation("55/2001")   → Työsopimuslaki
        get_statute_by_citation("731/1999")  → Suomen perustuslaki
        get_statute_by_citation("39/1889")   → Rikoslaki
        get_statute_by_citation("417/2007")  → Lastensuojelulaki
    """
    # Tunnistetaan muoto numero/vuosi tai vuosi/numero
    citation = citation.strip()
    match = re.match(r"^(\d+)[/\-](\d{4})$", citation)
    if match:
        number = int(match.group(1))
        year = int(match.group(2))
    else:
        # Kokeillaan myös muotoa vuosi/numero (harvinaisempi)
        match2 = re.match(r"^(\d{4})[/\-](\d+)$", citation)
        if match2:
            year = int(match2.group(1))
            number = int(match2.group(2))
        else:
            return (
                f"Virheellinen säädösviittaus: '{citation}'. "
                "Käytä muotoa 'numero/vuosi', esim. '55/2001'."
            )

    return await get_statute_text(year=year, number=number, lang=lang)


# ---------------------------------------------------------------------------
# Työkalu 4: Hae oikeusratkaisuja
# ---------------------------------------------------------------------------

async def search_case_law(
    court: str = "chancellor-of-justice",
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    page: int = 1,
) -> str:
    """
    Hae oikeusratkaisuja Finlexistä.

    HUOM: Finlexin avoin data -rajapinta sisältää tällä hetkellä seuraavat ratkaisutyypit:
      - "chancellor-of-justice" = Oikeuskanslerin ratkaisut (OKV)
      - "data-protection"       = Tietosuojavaltuutetun päätökset

    KKO:n (Korkein oikeus) ja KHO:n (Korkein hallinto-oikeus) ennakkopäätökset
    EIVÄT ole saatavilla tämän rajapinnan kautta.

    Parametrit:
        court: Tuomioistuimen/viranomaisen lyhenne:
            - "chancellor-of-justice" = Oikeuskansleri (oletus)
            - "data-protection"       = Tietosuojavaltuutettu
        start_year: Aloitusvuosi (valinnainen)
        end_year: Lopetus​vuosi (valinnainen)
        page: Sivunumero (oletus: 1)

    Palauttaa: Lista ratkaisuista URI:neen ja metatietoineen.

    Esimerkki:
        search_case_law(court="chancellor-of-justice", start_year=2024, end_year=2024)
        search_case_law(court="data-protection", start_year=2023, end_year=2024)
    """
    court_map = {
        "chancellor-of-justice": "chancellor-of-justice-decision",
        "okv": "chancellor-of-justice-decision",
        "oikeuskansleri": "chancellor-of-justice-decision",
        "chancellor": "chancellor-of-justice-decision",
        "data-protection": "data-protection-ombudsman-decision",
        "tietosuoja": "data-protection-ombudsman-decision",
        "tso": "data-protection-ombudsman-decision",
        "ombudsman": "data-protection-ombudsman-decision",
        # Nämä eivät ole saatavilla, mutta annetaan selkeä virheilmoitus
        "kko": None,
        "kho": None,
        "ho": None,
        "hao": None,
    }

    judgment_type = court_map.get(court.lower())
    if judgment_type is None:
        if court.lower() in ("kko", "kho", "ho", "hao"):
            return (
                f"Tuomioistuimen '{court}' ratkaisut eivät ole saatavilla Finlexin avoin data -rajapinnan kautta.\n"
                "Saatavilla olevat ratkaisutyypit:\n"
                "  - 'chancellor-of-justice' = Oikeuskanslerin ratkaisut\n"
                "  - 'data-protection' = Tietosuojavaltuutetun päätökset\n\n"
                "KKO:n ja KHO:n ennakkopäätökset löytyvät osoitteesta: https://www.finlex.fi/fi/oikeus/"
            )
        # Yritetään suoraan dokumenttityyppinä
        judgment_type = court

    try:
        items = list_judgments(
            judgment_type=judgment_type,
            start_year=start_year,
            end_year=end_year,
            page=page,
            limit=10,
        )
        if not items:
            return (
                f"Ei ratkaisuja haulla: tuomioistuin='{court}', "
                f"vuodet={start_year}–{end_year}, sivu={page}."
            )

        lines = [
            f"Ratkaisuhaku: {judgment_type}",
            f"Vuodet: {start_year or '(kaikki)'}–{end_year or '(kaikki)'}",
            f"Tuloksia: {len(items)} kpl\n",
        ]
        for item in items:
            uri = item.get("akn_uri", "")
            status = item.get("status", "")
            meta = _uri_to_metadata(uri)
            year = meta.get("year", "?")
            number = meta.get("number", "?")
            lines.append(f"  Ratkaisu {year}/{number} – {status}")
            lines.append(f"    URI: {uri}")

        lines.append(
            f"\nHae ratkaisun teksti: get_decision_text(year=VUOSI, number=NUMERO, court='{court}')"
        )
        return "\n".join(lines)

    except Exception as e:
        return f"Virhe ratkaisuhaussa: {e}"


# ---------------------------------------------------------------------------
# Työkalu 5: Hae oikeuspäätös
# ---------------------------------------------------------------------------

async def get_decision_text(
    year: int,
    number: int,
    court: str = "chancellor-of-justice",
) -> str:
    """
    Hae yksittäisen oikeuspäätöksen tai viranomaispäätöksen teksti Finlexistä.

    Hakee päätöksen vuoden ja numeron perusteella.

    Parametrit:
        year: Päätöksen vuosi (esim. 2025)
        number: Päätöksen numero (esim. 11017)
        court: Tuomioistuin/viranomainen:
            - "chancellor-of-justice" = Oikeuskansleri (oletus)
            - "data-protection"       = Tietosuojavaltuutettu

    Palauttaa: Päätöksen teksti merkkijonona (max 25 000 merkkiä).

    Esimerkki:
        get_decision_text(year=2025, number=11017, court="chancellor-of-justice")
        get_decision_text(year=2025, number=2464, court="data-protection")

    HUOM: KKO:n ja KHO:n päätökset eivät ole saatavilla tässä rajapinnassa.
    """
    court_map = {
        "chancellor-of-justice": "chancellor-of-justice-decision",
        "okv": "chancellor-of-justice-decision",
        "oikeuskansleri": "chancellor-of-justice-decision",
        "chancellor": "chancellor-of-justice-decision",
        "data-protection": "data-protection-ombudsman-decision",
        "tietosuoja": "data-protection-ombudsman-decision",
        "tso": "data-protection-ombudsman-decision",
        "ombudsman": "data-protection-ombudsman-decision",
    }

    judgment_type = court_map.get(court.lower(), court)

    try:
        xml_content = fetch_judgment_xml(judgment_type, year, number, "fin")
        parsed = parse_akn_xml(xml_content)
        return format_result(parsed)
    except Exception as e:
        return f"Päätöstä {year}/{number} (tyyppi: {judgment_type}) ei löydy. Virhe: {e}"


# ---------------------------------------------------------------------------
# Työkalu 6: Hae hallituksen esitys
# ---------------------------------------------------------------------------

async def get_government_proposal(
    year: int,
    number: int,
    lang: str = "fin",
) -> str:
    """
    Hae hallituksen esityksen (HE) teksti Finlexistä.

    Hallituksen esitykset ovat lainvalmistelun perusteluasiakirjoja, joissa
    selitetään lain tarkoitus, vaikutukset ja yksityiskohtaiset perustelut.

    Parametrit:
        year: Hallituksen esityksen vuosi (esim. 2024)
        number: Hallituksen esityksen numero ilman "HE"-etuliitettä (esim. 215)
        lang: Kielikoodi – "fin" = suomi (oletus), "swe" = ruotsi

    Palauttaa: Hallituksen esityksen teksti merkkijonona (max 25 000 merkkiä).
               Pitkät asiakirjat katkaistaan ja huomio lisätään.

    Esimerkkejä:
        get_government_proposal(year=2024, number=215)  → HE 215/2024
        get_government_proposal(year=2024, number=1)    → HE 1/2024

    Viittausmuoto: "HE numero/vuosi" esim. "HE 215/2024"
    """
    try:
        xml_content = fetch_doc_xml("government-proposal", year, number, lang)
        parsed = parse_akn_xml(xml_content)
        return format_result(parsed)
    except Exception as e:
        return f"Hallituksen esitystä HE {number}/{year} ei löydy. Virhe: {e}"
