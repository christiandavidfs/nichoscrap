"""Etapa 1: descarga POIs de Overture Maps para un bbox y categoría (gratis, sin API key)."""
import argparse
import duckdb

RELEASE = "2026-10-21.0"
# Alicante ciudad (aprox.): oeste, sur, este, norte
BBOX = (-0.56, 38.29, -0.42, 38.42)

p = argparse.ArgumentParser()
p.add_argument("--categoria", default="restaurant", help="categoria taxonomy (substring o nodo de jerarquía)")
p.add_argument("--bbox", type=float, nargs=4, default=BBOX, metavar=("W", "S", "E", "N"))
p.add_argument("--out", default="data/overture_alicante.parquet")
a = p.parse_args()
w, s, e, n = a.bbox

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
con.execute(f"""
COPY (
  SELECT
    id,
    names.primary                         AS nombre,
    taxonomy.primary                      AS categoria,
    confidence,
    websites[1]                           AS web,
    phones[1]                             AS telefono,
    socials[1]                            AS social,
    addresses[1].freeform                 AS direccion,
    addresses[1].locality                 AS ciudad,
    ST_Y(geometry)                        AS lat,
    ST_X(geometry)                        AS lon
  FROM read_parquet('s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*', hive_partitioning=1)
  WHERE bbox.xmin BETWEEN {w} AND {e}
    AND bbox.ymin BETWEEN {s} AND {n}
    AND (taxonomy.primary ILIKE '%{a.categoria}%' OR list_contains(taxonomy.hierarchy, '{a.categoria}'))
    AND coalesce(operating_status,'open') = 'open'
) TO '{a.out}' (FORMAT parquet)
""")
print(con.execute(f"""
  SELECT categoria, count(*) n, round(avg(confidence),2) conf,
         round(100*avg((web IS NULL)::int)) pct_sin_web
  FROM '{a.out}' GROUP BY 1 ORDER BY n DESC LIMIT 15""").df().to_string(index=False))
print("total:", con.execute(f"SELECT count(*) FROM '{a.out}'").fetchone()[0])
