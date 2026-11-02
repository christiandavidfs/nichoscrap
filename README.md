# nichoscrap

Pipeline gratuito para detectar nichos de negocio en una zona concreta (ejemplo: restaurantes en Alicante).

1. **Etapa 1 – Overture Maps:** descarga masiva de POIs (gratis, sin API key) con DuckDB.
2. **Etapa 2 – Google Maps:** scraper con Playwright que extrae la ficha de cada local (rating, nº de reseñas, web, teléfono, dirección).
3. **Etapa 3 – Análisis:** métricas del nicho + resumen con un LLM local (Ollama).

> Las reseñas están desactivadas por defecto: Maps sirve una "vista limitada" a navegadores automatizados y oculta la pestaña de reseñas.
> Scrapear Google Maps va contra sus términos de servicio; úsalo solo para análisis personal y con volúmenes pequeños.

## Requisitos
- Python 3.12+ y [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com) con un modelo descargado (por ejemplo `ollama pull qwen2.5:7b`)

## Uso paso a paso

**0. Preparación (una sola vez)**
```bash
uv sync
uv run playwright install chromium
```

**1. Comprobar que Ollama está activo**
```bash
ollama list        # debe aparecer qwen2.5:7b; si falla, ejecuta `ollama serve`
```

**2. Descargar POIs de Overture**
```bash
uv run python etapa1_overture.py --categoria restaurant
# otro nicho o zona:
uv run python etapa1_overture.py --categoria sushi --out data/overture_sushi.parquet
# bbox personalizado: --bbox OESTE SUR ESTE NORTE
```

**3. Scrapear las fichas de Google Maps**
```bash
rm -f data/maps.jsonl
uv run python etapa2_maps.py --categoria mexican_restaurant --limite 30
```
- ~5 s por local, con pausas aleatorias.
- Reanudable: si lo interrumpes y lo relanzas, salta los locales ya hechos.
- Con otra entrada: `--entrada data/overture_sushi.parquet`.
- Prueba primero con `--limite 5`.

**4. Analizar con el modelo local**
```bash
uv run python etapa3_analisis.py                    # genera data/reporte.md
uv run python etapa3_analisis.py --modelo gemma4:12b  # modelo más potente, más lento
```

## Notas
- Fíate de las **métricas agregadas** del reporte; el texto del LLM local puede interpretarlas mal con pocos datos.
- Si Maps devuelve muchos `match=False`, reduce `--limite` y reintenta más tarde. No hay proxies ni evasión de bloqueos.
- Overture usa licencias abiertas (atribución obligatoria); no mezcles datos de Google en bases que publiques o revendas.
