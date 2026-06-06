"""
Scraper for Dinosaurio / Super Mami (dinoonline.com.ar / supermami.com.ar).
Dinosaurio S.A. uses Oracle Commerce (ATG) for its online stores.
This scraper searches and parses ATG HTML product catalog results.
"""

import re
import urllib.parse
from typing import List
from bs4 import BeautifulSoup
from .base import SupermarketScraper, Producto


class DinosaurioScraper(SupermarketScraper):
    NOMBRE = "Super Mami"
    BASE_URL = "https://www.supermami.com.ar"
    COLOR = "#F7941D"
    LOGO_EMOJI = "🟠"

    SEARCH_URL = "https://www.supermami.com.ar/super/categoria"

    def __init__(self):
        super().__init__()
        self.session.headers.update(
            {
                "Referer": "https://www.supermami.com.ar/super/home",
                "Origin": "https://www.supermami.com.ar",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            }
        )
        self._initialized = False

    def _ensure_session(self):
        """Pre-visit the home page to get ATG cookies if not initialized yet."""
        if not self._initialized:
            try:
                # Visit the homepage to initialize ATG cookies
                self._get("https://www.supermami.com.ar/super/home", verify=False)
                self._initialized = True
            except Exception as e:
                print(f"[Super Mami] Warning initializing session: {e}")

    def buscar_producto(self, query: str, limit: int = 5) -> List[Producto]:
        """Search products on Super Mami by scraping their ATG search page."""
        self._ensure_session()
        productos = []
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"{self.SEARCH_URL}?Ntt={encoded_query}&Dy=1&Nty=1"
            response = self._get(url, verify=False)

            soup = BeautifulSoup(response.text, "html.parser")
            prod_cards = soup.select(".product")

            for card in prod_cards[:limit]:
                try:
                    producto = self._parse_product_card(card)
                    if producto:
                        productos.append(producto)
                except Exception as e:
                    print(f"[Super Mami] Error parseando producto: {e}")
                    continue

        except Exception as e:
            print(f"[Super Mami] Error buscando '{query}': {e}")

        return productos

    def _parse_product_card(self, card) -> Producto:
        """Parse an ATG product card HTML element."""
        # Extract name
        desc_el = card.select_one(".description")
        nombre = desc_el.text.strip() if desc_el else ""
        if not nombre:
            return None

        # Extract link
        link_el = card.select_one(".image a")
        link = link_el.get("href", "") if link_el else ""
        url_producto = f"{self.BASE_URL}{link}" if link else ""

        # Extract image
        img_el = card.select_one(".image img")
        img_src = img_el.get("src", "") if img_el else ""
        if img_src.startswith("//"):
            imagen_url = f"https:{img_src}"
        else:
            imagen_url = img_src

        # Extract price
        price_div = card.select_one(".precio-unidad")
        if not price_div:
            return None

        current_span = price_div.select_one("span")
        current_price = self._parse_price(current_span.text) if current_span else 0.0

        antes_p = price_div.select_one("p")
        antes_text = antes_p.text if antes_p else ""

        precio = current_price
        precio_promo = None
        promo_desc = ""

        if antes_text and "antes" in antes_text.lower():
            original_price = self._parse_price(antes_text)
            if original_price and original_price > current_price:
                precio = original_price
                precio_promo = current_price
                descuento = round((1 - current_price / original_price) * 100)
                promo_desc = f"{descuento}% OFF"

        return Producto(
            nombre=nombre,
            precio=precio,
            supermercado=self.NOMBRE,
            marca="",
            precio_promo=precio_promo,
            promo_descripcion=promo_desc,
            imagen_url=imagen_url,
            url_producto=url_producto,
            disponible=True,
        )

    @staticmethod
    def _parse_price(text: str) -> float:
        """Parse a price string into a float, supporting both AR and US decimal separator style."""
        if not text:
            return 0.0
        cleaned = re.sub(r"[^\d.,-]", "", text)
        if not cleaned:
            return 0.0

        last_dot = cleaned.rfind(".")
        last_comma = cleaned.rfind(",")

        if last_dot != -1 and last_comma != -1:
            if last_dot > last_comma:
                cleaned = cleaned.replace(",", "")
            else:
                cleaned = cleaned.replace(".", "").replace(",", ".")
        elif last_comma != -1:
            cleaned = cleaned.replace(",", ".")

        try:
            return float(cleaned)
        except ValueError:
            return 0.0
