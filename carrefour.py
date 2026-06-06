"""
Scraper for Carrefour Argentina (VTEX platform).
Uses the VTEX Intelligent Search API for product queries.
"""

from typing import List
from .base import SupermarketScraper, Producto


class CarrefourScraper(SupermarketScraper):
    NOMBRE = "Carrefour"
    BASE_URL = "https://www.carrefour.com.ar"
    COLOR = "#004E9A"
    LOGO_EMOJI = "🔵"

    # VTEX Intelligent Search endpoint
    SEARCH_URL = (
        "https://www.carrefour.com.ar/api/catalog_system/pub/products/search"
    )

    def __init__(self):
        super().__init__()
        self.session.headers.update(
            {
                "Referer": "https://www.carrefour.com.ar/",
                "Origin": "https://www.carrefour.com.ar",
            }
        )

    def buscar_producto(self, query: str, limit: int = 5) -> List[Producto]:
        """Search products on Carrefour using VTEX catalog API."""
        productos = []
        try:
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            url = f"{self.SEARCH_URL}?ft={encoded_query}&_from=0&_to={min(limit - 1, 49)}"
            response = self._get(url)
            data = response.json()

            for item in data[:limit]:
                try:
                    producto = self._parse_vtex_product(item)
                    if producto:
                        productos.append(producto)
                except Exception as e:
                    print(f"[Carrefour] Error parseando producto: {e}")
                    continue

        except Exception as e:
            print(f"[Carrefour] Error buscando '{query}': {e}")

        return productos

    def _parse_vtex_product(self, item: dict) -> Producto:
        """Parse a VTEX product JSON into a Producto object."""
        nombre = item.get("productName", item.get("productTitle", ""))
        marca = item.get("brand", "")
        link = item.get("link", "")
        url_producto = f"{self.BASE_URL}{link}" if link else ""

        # Get the first available SKU
        items = item.get("items", [])
        if not items:
            return None

        sku = items[0]
        imagen_url = ""
        images = sku.get("images", [])
        if images:
            imagen_url = images[0].get("imageUrl", "")

        unidad = sku.get("measurementUnit", "")
        unit_mult = sku.get("unitMultiplier", 1)

        # Get pricing from sellers
        sellers = sku.get("sellers", [])
        if not sellers:
            return None

        seller = sellers[0]
        commertial_offer = seller.get("commertialOffer", {})
        precio = commertial_offer.get("ListPrice", 0)
        precio_venta = commertial_offer.get("Price", 0)
        disponible = commertial_offer.get("IsAvailable", True)

        # If ListPrice == Price, no promo
        precio_promo = None
        promo_desc = ""
        if precio_venta and precio and precio_venta < precio:
            precio_promo = precio_venta
            descuento = round((1 - precio_venta / precio) * 100)
            promo_desc = f"{descuento}% OFF"
        elif precio_venta:
            precio = precio_venta

        # Check teasers/promotions
        teasers = commertial_offer.get("Teasers", [])
        if teasers and not promo_desc:
            teaser = teasers[0]
            promo_desc = teaser.get("name", "")

        return Producto(
            nombre=nombre,
            precio=precio,
            supermercado=self.NOMBRE,
            marca=marca,
            precio_promo=precio_promo,
            promo_descripcion=promo_desc,
            imagen_url=imagen_url,
            url_producto=url_producto,
            unidad=unidad,
            disponible=disponible,
        )
