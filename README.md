# Finlex MCP

An MCP server that wraps [Finlex](https://opendata.finlex.fi/) — Finland's official legal databank maintained by the Ministry of Justice. It gives an AI assistant direct access to Finnish statutes, government bills, and legal decisions as structured text, using the Finlex open data REST API. Useful for any task involving Finnish law: finding legislation, reading the reasoning behind a law, or looking up regulatory decisions.

## Tools

| Tool | Description |
|---|---|
| `search_statutes` | List statutes by year range and type (act, decree, decision, etc.) |
| `get_statute_text` | Fetch the full text of a statute by year and number |
| `get_statute_by_citation` | Fetch a statute using the standard Finnish citation format `numero/vuosi` (e.g. `55/2001`) |
| `search_case_law` | List decisions from the Chancellor of Justice or Data Protection Ombudsman |
| `get_decision_text` | Fetch the full text of a specific legal decision by year and number |
| `get_government_proposal` | Fetch the text of a government bill (hallituksen esitys) by year and number |

## How it works

1. **Find** — call `search_statutes` or `search_case_law` to get a list of documents with their year and number.
2. **Fetch** — call `get_statute_text` or `get_decision_text` with the year and number to retrieve the full document.
3. **Shortcut** — if you already have a citation like `55/2001`, call `get_statute_by_citation` directly.
4. **Context** — call `get_government_proposal` with the bill number to read the legislative reasoning behind a statute.

## Quick start

```bash
git clone https://github.com/SimonBerg255/finlex-mcp.git
cd finlex-mcp
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000
```

## API details

- **Base URL:** `https://opendata.finlex.fi/finlex/avoindata/v1`
- **Protocol:** HTTPS REST; `User-Agent` header required on every request
- **Auth:** None — fully public
- **Rate limiting:** HTTP 429 enforced; client retries with exponential backoff (up to 3 attempts)
- **Response format:** Akoma Ntoso XML for documents; JSON for list endpoints
- **License:** [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)

## Domain reference

**Citation format:** Finnish statutes are cited as `numero/vuosi`, e.g. `55/2001` (Työsopimuslaki), `731/1999` (Suomen perustuslaki), `39/1889` (Rikoslaki). Government bills use `HE numero/vuosi`, e.g. `HE 215/2024`.

**Language:** All documents are in Finnish (`fin`) or Swedish (`swe`). Search terms must be in Finnish or Swedish — English returns nothing.

**Statute types** (for `search_statutes`): `act`, `decree`, `decision`, `announcement`, `official-regulation`, `budget`, `rules-of-procedure`, and others.

**Available case law:** Only two judgment types are exposed by the open data API:
- `chancellor-of-justice` — Oikeuskanslerin ratkaisut (OKV)
- `data-protection` — Tietosuojavaltuutetun päätökset

KKO (Supreme Court) and KHO (Supreme Administrative Court) precedents are not available via this API. See [finlex.fi/fi/oikeus/](https://www.finlex.fi/fi/oikeus/) for those.

**Text cap:** All document responses are capped at 25,000 characters. Large statutes include a truncation notice.

## Validation

```bash
python3 test_tools.py
```

Runs 8 live tests against the real Finlex API: fetching Työsopimuslaki (55/2001), listing 2024 statutes, citation parsing, case law search, context overflow safety for Rikoslaki (39/1889), a government proposal (HE 215/2024), Suomen perustuslaki (731/1999), and graceful error handling for KKO queries. All tests must pass before the server is considered ready.

## License

MIT
