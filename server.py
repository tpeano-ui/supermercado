"""
Flask server for the Supermarket Price Comparator.
Provides REST API endpoints and serves the frontend.
"""

import os
import time
import hashlib
import secrets
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS

from scrapers.carrefour import CarrefourScraper
from scrapers.disco import DiscoScraper
from scrapers.dinosaurio import DinosaurioScraper
from scrapers.cordiez import CordiezScraper

# ─── Configuration ───────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = secrets.token_hex(32)
CORS(app)

# Access code for sharing — change this to your preferred code
ACCESS_CODE = "cordoba2025"

# Cache configuration
CACHE_TTL = 300  # 5 minutes
price_cache = {}  # {cache_key: {"data": ..., "timestamp": ...}}

# Initialize scrapers
SCRAPERS = {
    "carrefour": CarrefourScraper(),
    "disco": DiscoScraper(),
    "supermami": DinosaurioScraper(),
    "cordiez": CordiezScraper(),
}

# Thread pool for parallel scraping
executor = ThreadPoolExecutor(max_workers=4)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def cache_key(query: str, supermercado: str) -> str:
    """Generate a cache key for a query + supermarket."""
    return hashlib.md5(f"{query}:{supermercado}".encode()).hexdigest()


def get_cached(key: str):
    """Get cached result if still valid."""
    if key in price_cache:
        entry = price_cache[key]
        if time.time() - entry["timestamp"] < CACHE_TTL:
            return entry["data"]
        else:
            del price_cache[key]
    return None


def set_cache(key: str, data):
    """Store result in cache."""
    price_cache[key] = {"data": data, "timestamp": time.time()}


def require_auth(f):
    """Decorator to require access code authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check session
        if session.get("authenticated"):
            return f(*args, **kwargs)
        # Check header
        auth_code = request.headers.get("X-Access-Code", "")
        if auth_code == ACCESS_CODE:
            session["authenticated"] = True
            return f(*args, **kwargs)
        return jsonify({"error": "Acceso no autorizado", "code": 401}), 401
    return decorated


def buscar_en_supermercado(scraper_name: str, query: str, limit: int = 3):
    """Search a single supermarket (used in thread pool)."""
    scraper = SCRAPERS[scraper_name]
    key = cache_key(query, scraper_name)

    # Check cache first
    cached = get_cached(key)
    if cached is not None:
        return scraper_name, cached, True

    try:
        productos = scraper.buscar_producto(query, limit=limit)
        result = [p.to_dict() for p in productos]
        set_cache(key, result)
        return scraper_name, result, False
    except Exception as e:
        print(f"[Server] Error en {scraper_name} buscando '{query}': {e}")
        return scraper_name, [], False


# ─── Routes ──────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    """Serve the main page."""
    return send_from_directory("static", "index.html")


@app.route("/api/auth", methods=["POST"])
def authenticate():
    """Authenticate with access code."""
    data = request.get_json()
    code = data.get("code", "")
    if code == ACCESS_CODE:
        session["authenticated"] = True
        return jsonify({"success": True, "message": "Acceso concedido"})
    return jsonify({"success": False, "message": "Codigo incorrecto"}), 401


@app.route("/api/supermercados")
@require_auth
def get_supermercados():
    """List available supermarkets."""
    supermercados = {}
    for key, scraper in SCRAPERS.items():
        supermercados[key] = scraper.info()
    return jsonify(supermercados)


@app.route("/api/buscar", methods=["POST"])
@require_auth
def buscar():
    """
    Search products across all supermarkets.
    
    Request body:
    {
        "productos": ["leche", "pan lactal", "yerba 1kg"],
        "supermercados": ["carrefour", "disco"]  // optional, default: all
    }
    """
    data = request.get_json()
    lista_productos = data.get("productos", [])
    supermercados_seleccionados = data.get("supermercados", list(SCRAPERS.keys()))
    resultados_por_producto = data.get("resultados_por_producto", 3)

    if not lista_productos:
        return jsonify({"error": "La lista de productos esta vacia"}), 400

    if len(lista_productos) > 30:
        return jsonify({"error": "Maximo 30 productos por consulta"}), 400

    # Filter valid supermarkets
    supermercados_validos = [
        s for s in supermercados_seleccionados if s in SCRAPERS
    ]

    resultados = {}
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

    for producto_query in lista_productos:
        producto_query = producto_query.strip()
        if not producto_query:
            continue

        resultados[producto_query] = {}
        futures = {}

        # Launch parallel searches
        for supermercado in supermercados_validos:
            future = executor.submit(
                buscar_en_supermercado,
                supermercado,
                producto_query,
                resultados_por_producto,
            )
            futures[future] = supermercado

        # Collect results
        for future in as_completed(futures, timeout=30):
            try:
                nombre_super, productos, from_cache = future.result()
                resultados[producto_query][nombre_super] = {
                    "productos": productos,
                    "from_cache": from_cache,
                }
            except Exception as e:
                nombre_super = futures[future]
                print(f"[Server] Timeout/error en {nombre_super}: {e}")
                resultados[producto_query][nombre_super] = {
                    "productos": [],
                    "error": str(e),
                }

    # Calculate summary (cheapest option per product)
    resumen = calcular_resumen(resultados, supermercados_validos)

    return jsonify(
        {
            "resultados": resultados,
            "resumen": resumen,
            "timestamp": timestamp,
            "supermercados_info": {
                k: SCRAPERS[k].info() for k in supermercados_validos
            },
        }
    )


def calcular_resumen(resultados: dict, supermercados: list) -> dict:
    """
    Calculate a summary: for each supermarket, estimate total cost
    using the cheapest matching product for each item.
    """
    totales = {s: {"total": 0, "encontrados": 0, "no_encontrados": []} for s in supermercados}

    for producto_query, por_super in resultados.items():
        for super_name in supermercados:
            data = por_super.get(super_name, {})
            productos = data.get("productos", [])
            if productos:
                # Use the cheapest product found
                mejor_precio = min(p["precio_final"] for p in productos)
                totales[super_name]["total"] += mejor_precio
                totales[super_name]["encontrados"] += 1
            else:
                totales[super_name]["no_encontrados"].append(producto_query)

    # Add supermarket info to summary
    for s in supermercados:
        totales[s]["info"] = SCRAPERS[s].info()
        totales[s]["total"] = round(totales[s]["total"], 2)

    return totales


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  COMPARADOR DE PRECIOS - Supermercados de Cordoba")
    print("=" * 60)
    print(f"  Codigo de acceso: {ACCESS_CODE}")
    print(f"  Supermercados activos: {', '.join(SCRAPERS.keys())}")
    print(f"  Cache TTL: {CACHE_TTL}s")
    print("=" * 60)
    print("  Abrí http://localhost:5000 en tu navegador")
    print("=" * 60 + "\n")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
