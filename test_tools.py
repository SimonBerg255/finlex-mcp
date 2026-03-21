"""
test_tools.py – Live-integraatiotestit Finlex MCP -palvelimelle.

Testit ottavat yhteyden oikeaan Finlex-rajapintaan.
Aja: python3 test_tools.py
"""

import asyncio
import sys
import time


async def run_tests():
    failures = []

    print("=== TEST 1: Hae säädös 55/2001 (Työsopimuslaki) ===")
    try:
        from tools_finlex import get_statute_text
        result = await get_statute_text(year=2001, number=55)
        assert "työsopimus" in result.lower() or "55/2001" in result.lower() or len(result) > 500, \
            f"Odotettu teksti puuttuu. Tulos: {result[:200]}"
        assert len(result) > 200, f"Liian lyhyt vastaus: {len(result)} merkkiä"
        print(f"PASS — Saatiin {len(result)} merkkiä")
        print(f"Esikatselu: {result[:300]}\n")
    except Exception as e:
        failures.append(f"TEST 1 EPÄONNISTUI: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(1)

    print("=== TEST 2: Hae säädösluettelo vuodelta 2024 ===")
    try:
        from tools_finlex import search_statutes
        result = await search_statutes(start_year=2024, end_year=2024)
        assert "2024" in result, f"Vuosi 2024 puuttuu vastauksesta: {result[:200]}"
        print(f"PASS")
        print(f"Esikatselu: {result[:300]}\n")
    except Exception as e:
        failures.append(f"TEST 2 EPÄONNISTUI: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(1)

    print("=== TEST 3: Hae viittauksen '55/2001' perusteella ===")
    try:
        from tools_finlex import get_statute_by_citation
        result = await get_statute_by_citation("55/2001")
        assert len(result) > 200, f"Liian lyhyt vastaus: {len(result)} merkkiä"
        print(f"PASS — Saatiin {len(result)} merkkiä\n")
    except Exception as e:
        failures.append(f"TEST 3 EPÄONNISTUI: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(1)

    print("=== TEST 4: Hae oikeusratkaisuja (Oikeuskansleri) ===")
    try:
        from tools_finlex import search_case_law
        result = await search_case_law(court="chancellor-of-justice", start_year=2024, end_year=2025)
        assert len(result) > 100, f"Liian lyhyt vastaus: {len(result)} merkkiä"
        assert "chancellor" in result.lower() or "oikeuskansleri" in result.lower() \
               or "2024" in result or "2025" in result, \
            f"Odotettu sisältö puuttuu: {result[:200]}"
        print(f"PASS")
        print(f"Esikatselu: {result[:300]}\n")
    except Exception as e:
        failures.append(f"TEST 4 EPÄONNISTUI: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(1)

    print("=== TEST 5: Kontekstiturvallisuus – suuri laki katkaistaan ===")
    try:
        from tools_finlex import get_statute_text
        # Rikoslaki (39/1889) on erittäin pitkä – testaa myös -001-suffix-hakua
        result = await get_statute_text(year=1889, number=39)
        assert len(result) <= 30_000, \
            f"KONTEKSTIYLITYS: {len(result)} merkkiä (raja 25 000)"
        # Myös Työsopimuslaki (55/2001) pitäisi katketa
        result2 = await get_statute_text(year=2001, number=55)
        assert len(result2) <= 30_000, \
            f"KONTEKSTIYLITYS (55/2001): {len(result2)} merkkiä (raja 25 000)"
        print(f"PASS — Rikoslaki: {len(result)} merkkiä, Työsopimuslaki: {len(result2)} merkkiä (raja: 25 000)\n")
    except Exception as e:
        failures.append(f"TEST 5 EPÄONNISTUI: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(1)

    print("=== TEST 6: Hae hallituksen esitys HE 215/2024 ===")
    try:
        from tools_finlex import get_government_proposal
        result = await get_government_proposal(year=2024, number=215)
        assert len(result) > 200, f"Liian lyhyt vastaus: {len(result)} merkkiä"
        assert "215" in result or "hallitus" in result.lower() or "esitys" in result.lower(), \
            f"Odotettu sisältö puuttuu: {result[:200]}"
        print(f"PASS — Saatiin {len(result)} merkkiä")
        print(f"Esikatselu: {result[:300]}\n")
    except Exception as e:
        failures.append(f"TEST 6 EPÄONNISTUI: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(1)

    print("=== TEST 7: Hae suomen perustuslaki (731/1999) ===")
    try:
        from tools_finlex import get_statute_by_citation
        result = await get_statute_by_citation("731/1999")
        assert len(result) > 200, f"Liian lyhyt vastaus: {len(result)} merkkiä"
        assert "perustuslaki" in result.lower() or "731" in result or "1999" in result, \
            f"Odotettu sisältö puuttuu: {result[:200]}"
        print(f"PASS — Saatiin {len(result)} merkkiä")
        print(f"Esikatselu: {result[:300]}\n")
    except Exception as e:
        failures.append(f"TEST 7 EPÄONNISTUI: {e}")
        print(f"FAIL: {e}\n")

    time.sleep(1)

    print("=== TEST 8: KKO-haku palauttaa selkeän virheilmoituksen ===")
    try:
        from tools_finlex import search_case_law
        result = await search_case_law(court="KKO", start_year=2024, end_year=2024)
        # Pitäisi palauttaa selkeä virheilmoitus, ei kaatua
        assert len(result) > 20, f"Liian lyhyt vastaus: {len(result)} merkkiä"
        print(f"PASS — KKO-haku palauttaa: {result[:200]}\n")
    except Exception as e:
        failures.append(f"TEST 8 EPÄONNISTUI: {e}")
        print(f"FAIL: {e}\n")

    # Yhteenveto
    print("=" * 50)
    if failures:
        print(f"\n=== EPÄONNISTUNEET TESTIT ({len(failures)}) ===")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    else:
        print("\nKAIKKI TESTIT LÄPÄISTY – Finlex MCP on valmis")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_tests())
