"""
server.py – Finlex MCP -palvelin (FastMCP, SSE-transport).

Käyttö:
    python3 server.py                  → käynnistää palvelimen portissa 8000
    uvicorn server:app --port 8000     → tuotanto-ajotapa

Ympäristömuuttujat (.env):
    MCP_SERVER_JWT_SECRET    – HMAC-allekirjoitusavain (pakollinen tuotannossa)
    MCP_SERVER_JWT_ISSUER    – JWT-myöntäjä (valinnainen)
    MCP_SERVER_JWT_AUDIENCE  – JWT-kohdeyleisö (valinnainen)
"""

import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from mcp.server.fastmcp import Icon
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

load_dotenv()

from tools_finlex import (
    get_decision_text,
    get_government_proposal,
    get_statute_by_citation,
    get_statute_text,
    search_case_law,
    search_statutes,
)

####### API KEY #######

verifier = JWTVerifier(
    public_key=os.getenv("MCP_SERVER_JWT_SECRET"),
    issuer=os.getenv("MCP_SERVER_JWT_ISSUER", ""),
    audience=os.getenv("MCP_SERVER_JWT_AUDIENCE", ""),
    algorithm="HS256",
)

####### CUSTOM MIDDLEWARE #######

class IPAllowlistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_ips: list[str]):
        super().__init__(app)
        self.allowed_ips = set(allowed_ips)
        self.allow_all = "*" in self.allowed_ips

    async def dispatch(self, request, call_next):
        if self.allow_all:
            return await call_next(request)
        client_ip = request.client.host if request.client else None
        if client_ip not in self.allowed_ips:
            return JSONResponse(
                status_code=403,
                content={"error": "Forbidden", "your_ip": client_ip},
            )
        return await call_next(request)


ALLOWED_IPS = os.getenv("MCP_ALLOWED_IPS", "*").split(",")
middleware = [Middleware(IPAllowlistMiddleware, allowed_ips=ALLOWED_IPS)]

####### SERVER METADATA #######

icon = Icon(
    src="https://www.finlex.fi/favicon.ico",
)

INSTRUCTION_STRING = """Olet yhteydessä Finlexiin – Suomen oikeudelliseen tietopankkiin, jota ylläpitää oikeusministeriö.

Voit hakea:
- Säädöksiä: Suomen lait ja asetukset vuosi- ja numerotunnisteen perusteella
- Oikeusratkaisuja: Oikeuskanslerin ratkaisut (OKV) ja Tietosuojavaltuutetun päätökset
- Hallituksen esityksiä: lainvalmistelun perustelut

TÄRKEÄÄ: Kaikki haut ja termit on tehtävä suomeksi tai ruotsiksi. Englanninkieliset hakusanat eivät tuota tuloksia.

Säädösviittaukset ovat muodossa numero/vuosi, esim. "55/2001" (Työsopimuslaki).
Hallituksen esitysten viittausmuoto: "HE numero/vuosi", esim. "HE 215/2024".

HUOMIO SAATAVILLA OLEVISTA RATKAISUTYYPEISTÄ:
Finlexin avoin data -rajapinta ei sisällä KKO:n tai KHO:n ennakkopäätöksiä.
Saatavilla ovat:
- Oikeuskanslerin ratkaisut (OKV) – court="chancellor-of-justice"
- Tietosuojavaltuutetun päätökset – court="data-protection"

Kaikki tiedot ovat peräisin Suomen virallisesta oikeustietopankista (https://opendata.finlex.fi/).
Lisenssi: Creative Commons Attribution 4.0 International (CC BY 4.0)."""

VERSION = "1.0.0"
WEBSITE_URL = "https://opendata.finlex.fi/"

####### SERVER CONFIGURATION #######

mcp = FastMCP(
    name="Finlex",
    instructions=INSTRUCTION_STRING,
    version=VERSION,
    website_url=WEBSITE_URL,
    icons=[icon],
    auth=verifier,
)

####### TOOLS #######

# All tools run automatically without user confirmation
mcp.tool(meta={"requires_permission": False})(search_statutes)
mcp.tool(meta={"requires_permission": False})(get_statute_text)
mcp.tool(meta={"requires_permission": False})(get_statute_by_citation)
mcp.tool(meta={"requires_permission": False})(search_case_law)
mcp.tool(meta={"requires_permission": False})(get_decision_text)
mcp.tool(meta={"requires_permission": False})(get_government_proposal)

####### CUSTOM ROUTES #######

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

####### RUNNING THE SERVER #######
# Run with: uvicorn server:app --host 0.0.0.0 --port 8000
app = mcp.http_app(middleware=middleware)

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("MCP_PORT", "8000"))
    host = os.getenv("MCP_HOST", "0.0.0.0")
    print(f"Käynnistetään Finlex MCP -palvelin osoitteessa {host}:{port}/mcp")
    uvicorn.run(app, host=host, port=port)
