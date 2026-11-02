"""Etapa 3: métricas del nicho + resumen con un LLM local (Ollama, gratis)."""
import argparse, json, urllib.request

import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--maps", default="data/maps.jsonl")
ap.add_argument("--modelo", default="qwen2.5:7b")
ap.add_argument("--salida", default="data/reporte.md")
a = ap.parse_args()

df = pd.DataFrame(json.loads(l) for l in open(a.maps))
df = df[df["match"]].copy()
df["sin_web"] = df["g_web"].isna()
df["pocas_resenas"] = df["g_n_resenas"].fillna(0) < 50

metricas = {
    "locales_analizados": len(df),
    "rating_medio": round(df["g_rating"].mean(), 2),
    "mediana_resenas": float(df["g_n_resenas"].median()),
    "pct_sin_web": round(100 * df["sin_web"].mean()),
    "pct_con_menos_de_50_resenas": round(100 * df["pocas_resenas"].mean()),
}
tabla = df[["g_nombre", "g_rating", "g_n_resenas", "g_web", "g_direccion"]].fillna("").to_csv(index=False)

prompt = f"""Eres analista de mercado. Tienes datos de Google Maps de restaurantes de un nicho en Alicante.
Métricas agregadas: {json.dumps(metricas, ensure_ascii=False)}
Locales (CSV):
{tabla}
Responde en español, conciso: 1) nivel de competencia, 2) calidad percibida, 3) debilidades digitales
de los competidores, 4) oportunidad para un nuevo negocio (puntuación 1-10 con justificación), 5) riesgos y qué validar."""

req = urllib.request.Request("http://localhost:11434/api/generate",
    data=json.dumps({"model": a.modelo, "prompt": prompt, "stream": False}).encode(),
    headers={"Content-Type": "application/json"})
texto = json.load(urllib.request.urlopen(req, timeout=600))["response"]

out = f"# Análisis del nicho\n\n```\n{json.dumps(metricas, indent=2, ensure_ascii=False)}\n```\n\n{texto}\n"
open(a.salida, "w").write(out)
print(out)
