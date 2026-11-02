"""Etapa 2: para cada POI de Overture, busca el local en Google Maps (Playwright, sin API)
y extrae ficha + reseñas. Salida JSONL reanudable."""
import argparse, asyncio, json, random, re, sys, urllib.parse
from pathlib import Path

import duckdb
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from rapidfuzz import fuzz

NUM = re.compile(r"[\d.,]+")


def num(s):
    m = NUM.search(s or "")
    return float(m.group().replace(".", "").replace(",", ".")) if m else None


async def aceptar_cookies(pg):
    for t in ("Aceptar todo", "Accept all"):
        b = pg.get_by_role("button", name=t)
        if await b.count():
            await b.first.click()
            await pg.wait_for_timeout(2500)
            return


async def txt(pg, sel):
    el = pg.locator(sel).first
    return (await el.inner_text()).strip() if await el.count() else None


async def attr(pg, sel, name):
    el = pg.locator(sel).first
    return await el.get_attribute(name) if await el.count() else None


async def abrir_ficha(pg, poi):
    q = urllib.parse.quote(f"{poi['nombre']} {poi['ciudad'] or 'Alicante'}")
    await pg.goto(f"https://www.google.com/maps/search/{q}/@{poi['lat']},{poi['lon']},18z?hl=es",
                  wait_until="domcontentloaded")
    await pg.wait_for_timeout(2500)
    if "consent.google" in pg.url:
        await aceptar_cookies(pg)
    # Lista de resultados: elegir el que mejor coincide por nombre; si no, ya se abrió la ficha
    try:
        await pg.wait_for_selector('h1, div[role="feed"]', timeout=12000)
    except PWTimeout:
        return False
    if await pg.locator('div[role="feed"]').count():
        links = pg.locator('div[role="feed"] a.hfpxzc')
        n = await links.count()
        mejor, mejor_s = None, 0
        for i in range(min(n, 6)):
            lab = await links.nth(i).get_attribute("aria-label") or ""
            s = fuzz.token_set_ratio(lab.lower(), poi["nombre"].lower())
            if s > mejor_s:
                mejor, mejor_s = i, s
        if mejor is None or mejor_s < 80:
            return False
        await links.nth(mejor).click()
        await pg.wait_for_selector("h1.DUwDvf", timeout=10000)
    return True


async def ficha(pg):
    rating_el = pg.locator("div.F7nice").first
    rating_txt = await rating_el.inner_text() if await rating_el.count() else ""
    m = re.search(r"([\d,]+)\s*\(?([\d.]+)\)?", rating_txt.replace("\n", " "))
    return {
        "g_nombre": await txt(pg, "h1.DUwDvf"),
        "g_rating": float(m.group(1).replace(",", ".")) if m else None,
        "g_n_resenas": int(m.group(2).replace(".", "")) if m else None,
        "g_categoria": await txt(pg, "button.DkEaL"),
        "g_direccion": await attr(pg, 'button[data-item-id="address"]', "aria-label"),
        "g_web": await attr(pg, 'a[data-item-id="authority"]', "href"),
        "g_telefono": await attr(pg, 'button[data-item-id^="phone"]', "aria-label"),
        "g_precio": await attr(pg, 'span[aria-label^="Precio"]', "aria-label"),
    }


async def resenas(pg, maximo):
    if maximo <= 0:
        return []
    tab = pg.get_by_role("tab", name=re.compile("Reseñas"))
    if not await tab.count():
        return []
    await tab.first.click()
    await pg.wait_for_selector("div.jftiEf", timeout=8000)
    # ordenar por "Más recientes"/"Menos relevantes" no es necesario; scroll para cargar más
    panel = pg.locator("div.m6QErb.DxyBCb").first
    prev = 0
    for _ in range(40):
        cnt = await pg.locator("div.jftiEf").count()
        if cnt >= maximo or (cnt == prev and _ > 2):
            break
        prev = cnt
        await panel.evaluate("e => e.scrollBy(0, 4000)")
        await pg.wait_for_timeout(random.randint(700, 1300))
    out = []
    for r in await pg.locator("div.jftiEf").all():
        mas = r.locator("button.w8nwRe")
        if await mas.count():
            await mas.first.click()
        estrellas = await r.locator("span.kvMYJc").first.get_attribute("aria-label") if await r.locator("span.kvMYJc").count() else None
        texto = await r.locator("span.wiI7pd").first.inner_text() if await r.locator("span.wiI7pd").count() else ""
        fecha = await r.locator("span.rsqaWe").first.inner_text() if await r.locator("span.rsqaWe").count() else None
        out.append({"estrellas": num(estrellas), "fecha": fecha, "texto": texto.strip()})
        if len(out) >= maximo:
            break
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="data/overture_alicante.parquet")
    ap.add_argument("--categoria", default="mexican_restaurant")
    ap.add_argument("--limite", type=int, default=30)
    ap.add_argument("--resenas", type=int, default=0, help="reseñas por local (0 = omitir; Maps las oculta a navegadores automatizados)")
    ap.add_argument("--salida", default="data/maps.jsonl")
    ap.add_argument("--visible", action="store_true", help="mostrar navegador")
    a = ap.parse_args()

    pois = duckdb.sql(f"SELECT * FROM '{a.entrada}' WHERE categoria ILIKE '%{a.categoria}%' AND nombre IS NOT NULL ORDER BY confidence DESC LIMIT {a.limite}").df().to_dict("records")
    salida = Path(a.salida)
    hechos = {json.loads(l)["id"] for l in salida.read_text().splitlines()} if salida.exists() else set()

    async with async_playwright() as p:
        b = await p.chromium.launch(headless=not a.visible)
        ctx = await b.new_context(locale="es-ES", viewport={"width": 1280, "height": 900})
        pg = await ctx.new_page()
        for i, poi in enumerate(pois, 1):
            if poi["id"] in hechos:
                continue
            reg = {"id": poi["id"], "nombre": poi["nombre"], "categoria": poi["categoria"], "lat": poi["lat"], "lon": poi["lon"]}
            try:
                if await abrir_ficha(pg, poi):
                    reg.update(await ficha(pg))
                    reg["resenas"] = await resenas(pg, a.resenas)
                    reg["match"] = True
                else:
                    reg["match"] = False
            except Exception as e:
                reg.update(match=False, error=repr(e)[:200])
            with salida.open("a") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
            print(f"[{i}/{len(pois)}] {poi['nombre']}: match={reg['match']} rating={reg.get('g_rating')} n={reg.get('g_n_resenas')} res={len(reg.get('resenas', []))}", flush=True)
            await pg.wait_for_timeout(random.randint(2500, 6000))
        await b.close()

asyncio.run(main())
