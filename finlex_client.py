"""
finlex_client.py – HTTP client for the Finlex avoin data API v1.

Base URL: https://opendata.finlex.fi/finlex/avoindata/v1
All responses are Akoma Ntoso XML (namespace http://docs.oasis-open.org/legaldocml/ns/akn/3.0).
User-Agent header is MANDATORY on every request.

Valid document types (from API spec):
  act:      statute | statute-consolidated | statute-foreign-language-translation | statute-sami-translation
  judgment: chancellor-of-justice-decision | data-protection-ombudsman-decision
  doc:      government-proposal | collective-agreement-general-applicability-decision |
            legal-literature-references | tax-treaty-consolidated | trade-union-center-agreement |
            treaty-metadata | treaty | authority-regulation
"""

import time
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

BASE_URL = "https://opendata.finlex.fi/finlex/avoindata/v1"

HEADERS = {
    "User-Agent": "finlex-mcp/1.0",
    "Accept-Encoding": "gzip",
}

TIMEOUT = 30.0
CHAR_LIMIT = 25_000

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
FINLEX_NS = "http://data.finlex.fi/schema/finlex"
NS = {"akn": AKN_NS, "finlex": FINLEX_NS}


# ---------------------------------------------------------------------------
# Low-level HTTP
# ---------------------------------------------------------------------------

def _get(url: str, params: dict = None, accept: str = "application/xml") -> httpx.Response:
    """GET with retries on HTTP 429."""
    req_headers = {**HEADERS, "Accept": accept}
    with httpx.Client(timeout=TIMEOUT) as client:
        for attempt in range(3):
            r = client.get(url, headers=req_headers, params=params)
            if r.status_code == 429:
                wait = 2 ** attempt
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError(f"Rate limited after 3 attempts: {url}")


def _get_json(url: str, params: dict = None) -> list | dict:
    """GET JSON list endpoint."""
    if params is None:
        params = {}
    params["format"] = "json"
    r = _get(url, params=params, accept="application/json")
    return r.json()


# ---------------------------------------------------------------------------
# XML text extraction helpers
# ---------------------------------------------------------------------------

def _tag(local: str) -> str:
    """Return Clark-notation tag name."""
    return f"{{{AKN_NS}}}{local}"


def _get_text_recursive(elem: ET.Element) -> str:
    """Recursively extract all text from an XML element."""
    parts = []
    if elem.text and elem.text.strip():
        parts.append(elem.text.strip())
    for child in elem:
        parts.append(_get_text_recursive(child))
        if child.tail and child.tail.strip():
            parts.append(child.tail.strip())
    return " ".join(p for p in parts if p)


def _extract_text_from_element(elem: ET.Element, indent: int = 0) -> list[str]:
    """
    Walk an AKN element tree and return list of human-readable text lines.
    Handles: chapter, section, subsection, paragraph, content, p, heading,
    num, hcontainer, header, judgmentBody, decision, mainBody, introduction, rationale.
    """
    lines = []
    prefix = "  " * indent
    tag = elem.tag.replace(f"{{{AKN_NS}}}", "")

    if tag in ("chapter", "hcontainer"):
        num_el = elem.find(_tag("num"))
        head_el = elem.find(_tag("heading"))
        label = ""
        if num_el is not None and num_el.text:
            label += num_el.text.strip()
        if head_el is not None and head_el.text:
            label += (" – " if label else "") + head_el.text.strip()
        if label:
            lines.append(f"\n{prefix}{'=' * 40}")
            lines.append(f"{prefix}{label.upper()}")
            lines.append(f"{prefix}{'=' * 40}")
        for child in elem:
            lines.extend(_extract_text_from_element(child, indent))

    elif tag == "section":
        num_el = elem.find(_tag("num"))
        head_el = elem.find(_tag("heading"))
        label = ""
        if num_el is not None and num_el.text:
            label += num_el.text.strip()
        if head_el is not None and head_el.text:
            label += ("  " if label else "") + head_el.text.strip()
        if label:
            lines.append(f"\n{prefix}{label}")
        for child in elem:
            if child.tag not in (_tag("num"), _tag("heading")):
                lines.extend(_extract_text_from_element(child, indent + 1))

    elif tag == "subsection":
        for child in elem:
            lines.extend(_extract_text_from_element(child, indent + 1))

    elif tag == "paragraph":
        num_el = elem.find(_tag("num"))
        num = num_el.text.strip() if num_el is not None and num_el.text else ""
        content = ""
        for child in elem:
            if child.tag != _tag("num"):
                content += _get_text_recursive(child) + " "
        text = (num + "  " + content.strip()).strip()
        if text:
            lines.append(f"{prefix}{text}")

    elif tag in ("content", "intro"):
        text = _get_text_recursive(elem).strip()
        if text:
            lines.append(f"{prefix}{text}")

    elif tag == "p":
        text = _get_text_recursive(elem).strip()
        if text:
            lines.append(f"{prefix}{text}")

    elif tag in ("heading",):
        text = _get_text_recursive(elem).strip()
        if text:
            lines.append(f"\n{prefix}--- {text} ---")

    elif tag in ("judgmentBody", "mainBody", "body"):
        for child in elem:
            lines.extend(_extract_text_from_element(child, indent))

    elif tag in ("decision", "introduction", "rationale", "tblock"):
        head_el = elem.find(_tag("heading"))
        if head_el is not None:
            heading_text = _get_text_recursive(head_el).strip()
            if heading_text:
                lines.append(f"\n{prefix}--- {heading_text} ---")
        for child in elem:
            if child.tag != _tag("heading"):
                lines.extend(_extract_text_from_element(child, indent + 1))

    elif tag == "header":
        for child in elem:
            lines.extend(_extract_text_from_element(child, indent))

    elif tag in ("preface", "preamble"):
        for child in elem:
            lines.extend(_extract_text_from_element(child, indent))

    elif tag == "formula":
        text = _get_text_recursive(elem).strip()
        if text:
            lines.append(f"\n{prefix}{text}")

    elif tag == "table":
        lines.append(f"{prefix}[Taulukko – katso alkuperäinen dokumentti]")

    elif tag in ("meta", "references", "identification", "proprietary",
                 "classification", "keyword", "signatures", "conclusions"):
        pass  # skip metadata

    else:
        # Fallback: recurse into unknown containers
        for child in elem:
            lines.extend(_extract_text_from_element(child, indent))

    return lines


def parse_akn_xml(xml_content: str) -> dict:
    """
    Parse Akoma Ntoso XML and return a dict with:
      - title: str
      - number: str
      - year: str
      - date_issued: str
      - language: str
      - doc_type: str  (act / judgment / doc)
      - text: str  (full text, capped at CHAR_LIMIT)
      - truncated: bool
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}", "text": ""}

    # Determine document element type
    act_el = root.find(_tag("act"))
    judgment_el = root.find(_tag("judgment"))
    doc_el = root.find(_tag("doc"))

    doc_elem = act_el or judgment_el or doc_el
    if doc_elem is None:
        # Try direct root
        doc_elem = root

    doc_type = "act" if act_el is not None else ("judgment" if judgment_el is not None else "doc")

    # Extract metadata
    meta = {}
    identification = doc_elem.find(f".//{_tag('identification')}")
    if identification:
        frbrwork = identification.find(_tag("FRBRWork"))
        if frbrwork:
            frbrdate = frbrwork.find(_tag("FRBRdate"))
            meta["date_issued"] = frbrdate.get("date", "") if frbrdate is not None else ""
            frbrnumber = frbrwork.find(_tag("FRBRnumber"))
            meta["number"] = frbrnumber.get("value", "") if frbrnumber is not None else ""
            frbryear = frbrwork.find(f"{_tag('FRBRdate')}")
            # Extract year from date_issued
            meta["year"] = meta["date_issued"][:4] if meta.get("date_issued") else ""

        frbrexpr = identification.find(_tag("FRBRExpression"))
        if frbrexpr:
            lang_el = frbrexpr.find(_tag("FRBRlanguage"))
            meta["language"] = lang_el.get("language", "") if lang_el is not None else ""
            for d in frbrexpr.findall(_tag("FRBRdate")):
                if d.get("name") == "dateIssued":
                    meta["date_issued"] = d.get("date", "")
                    meta["year"] = meta["date_issued"][:4] if meta["date_issued"] else ""

    # Extract title and document number from preface / header
    title = ""
    doc_number = ""

    preface = doc_elem.find(_tag("preface"))
    if preface is not None:
        docnum_el = preface.find(f".//{_tag('docNumber')}")
        if docnum_el is not None:
            doc_number = (docnum_el.text or "").strip()
        doctitle_el = preface.find(f".//{_tag('docTitle')}")
        if doctitle_el is not None:
            title = (doctitle_el.text or "").strip()

    header = doc_elem.find(_tag("header"))
    if header is not None and not title:
        doctitle_el = header.find(f".//{_tag('docTitle')}")
        if doctitle_el is not None:
            title = (doctitle_el.text or "").strip()

    # Build header text
    header_lines = []
    if doc_number:
        header_lines.append(f"Säädösnumero: {doc_number}")
    if title:
        header_lines.append(f"Otsikko: {title}")
    if meta.get("date_issued"):
        header_lines.append(f"Annettu: {meta['date_issued']}")
    if meta.get("language"):
        lang_map = {"fin": "suomi", "swe": "ruotsi"}
        header_lines.append(f"Kieli: {lang_map.get(meta['language'], meta['language'])}")

    # Extract body text
    text_lines = []
    body_el = doc_elem.find(_tag("body"))
    judgment_body_el = doc_elem.find(_tag("judgmentBody"))
    main_body_el = doc_elem.find(_tag("mainBody"))

    for container in [preface, body_el, judgment_body_el, main_body_el]:
        if container is not None:
            text_lines.extend(_extract_text_from_element(container))

    full_text = "\n".join(header_lines) + "\n\n" + "\n".join(text_lines)
    full_text = full_text.strip()

    truncated = False
    if len(full_text) > CHAR_LIMIT:
        full_text = full_text[:CHAR_LIMIT]
        truncated = True

    return {
        "title": title,
        "number": doc_number or meta.get("number", ""),
        "year": meta.get("year", ""),
        "date_issued": meta.get("date_issued", ""),
        "language": meta.get("language", ""),
        "doc_type": doc_type,
        "text": full_text,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

def list_statutes(
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    statute_type: Optional[str] = None,
    lang_and_version: Optional[str] = None,
    page: int = 1,
    limit: int = 10,
    doc_type: str = "statute",
) -> list[dict]:
    """
    Return a list of statute URIs from the /act/{doc_type}/list endpoint.
    Each item: {"akn_uri": str, "status": str}
    """
    url = f"{BASE_URL}/akn/fi/act/{doc_type}/list"
    params: dict = {"page": page, "limit": min(limit, 10)}
    if start_year:
        params["startYear"] = start_year
    if end_year:
        params["endYear"] = end_year
    if statute_type:
        params["typeStatute"] = statute_type
    if lang_and_version:
        params["langAndVersion"] = lang_and_version
    return _get_json(url, params)


def fetch_statute_xml(
    year: int,
    number: int | str,
    lang: str = "fin",
    doc_type: str = "statute",
) -> str:
    """
    Fetch full statute XML as string.
    Some old statutes have hyphenated numbers (e.g. 39-001 for Rikoslaki 39/1889).
    Tries plain number first, then number-001 format if 404.
    """
    lang_ver = f"{lang}%40"
    url = f"{BASE_URL}/akn/fi/act/{doc_type}/{year}/{number}/{lang_ver}"
    try:
        r = _get(url)
        return r.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Try with -001 suffix for old statutes
            url2 = f"{BASE_URL}/akn/fi/act/{doc_type}/{year}/{number}-001/{lang_ver}"
            try:
                r2 = _get(url2)
                return r2.text
            except httpx.HTTPStatusError:
                pass
        raise


def list_judgments(
    judgment_type: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    page: int = 1,
    limit: int = 10,
) -> list[dict]:
    """
    Return a list of judgment URIs.
    Valid judgment_type values:
      - chancellor-of-justice-decision
      - data-protection-ombudsman-decision
    """
    url = f"{BASE_URL}/akn/fi/judgment/{judgment_type}/list"
    params: dict = {"page": page, "limit": min(limit, 10)}
    if start_year:
        params["startYear"] = start_year
    if end_year:
        params["endYear"] = end_year
    return _get_json(url, params)


def fetch_judgment_xml(
    judgment_type: str,
    year: int,
    number: int,
    lang: str = "fin",
) -> str:
    """Fetch full judgment XML as string."""
    lang_ver = f"{lang}%40"
    url = f"{BASE_URL}/akn/fi/judgment/{judgment_type}/{year}/{number}/{lang_ver}"
    r = _get(url)
    return r.text


def list_docs(
    doc_type: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    page: int = 1,
    limit: int = 10,
) -> list[dict]:
    """
    Return a list of document URIs.
    Valid doc_type values: government-proposal, collective-agreement-general-applicability-decision,
    legal-literature-references, tax-treaty-consolidated, trade-union-center-agreement,
    treaty-metadata, treaty, authority-regulation
    """
    url = f"{BASE_URL}/akn/fi/doc/{doc_type}/list"
    params: dict = {"page": page, "limit": min(limit, 10)}
    if start_year:
        params["startYear"] = start_year
    if end_year:
        params["endYear"] = end_year
    return _get_json(url, params)


def fetch_doc_xml(
    doc_type: str,
    year: int,
    number: int,
    lang: str = "fin",
) -> str:
    """Fetch full document XML as string."""
    lang_ver = f"{lang}%40"
    url = f"{BASE_URL}/akn/fi/doc/{doc_type}/{year}/{number}/{lang_ver}"
    r = _get(url)
    return r.text


def format_result(parsed: dict) -> str:
    """Format a parsed AKN result into a clean string for the MCP tool response."""
    if "error" in parsed:
        return f"Virhe: {parsed['error']}"
    text = parsed.get("text", "")
    if parsed.get("truncated"):
        text += f"\n\n[HUOM: Dokumentti on katkaistu. Alkuperäinen dokumentti on pidempi. Näytetään ensimmäiset {CHAR_LIMIT} merkkiä.]"
    return text
