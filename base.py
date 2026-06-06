"""
Base class for all supermarket scrapers.
Provides common interface and utility methods.
"""

import time
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class Producto:
    """Represents a product found in a supermarket."""

    def __init__(
        self,
        nombre: str,
        precio: float,
        supermercado: str,
        marca: str = "",
        precio_promo: Optional[float] = None,
        promo_descripcion: str = "",
        imagen_url: str = "",
        url_producto: str = "",
        unidad: str = "",
        disponible: bool = True,
    ):
        self.nombre = nombre
        self.precio = precio
        self.supermercado = supermercado
        self.marca = marca
        self.precio_promo = precio_promo
        self.promo_descripcion = promo_descripcion
        self.imagen_url = imagen_url
        self.url_producto = url_producto
        self.unidad = unidad
        self.disponible = disponible

    @property
    def precio_final(self) -> float:
        """Returns the best price (promo if available, otherwise regular)."""
        if self.precio_promo and self.precio_promo < self.precio:
            return self.precio_promo
        return self.precio

    @property
    def tiene_promo(self) -> bool:
        return (
            self.precio_promo is not None
            and self.precio_promo > 0
            and self.precio_promo < self.precio
        )

    def to_dict(self) -> Dict:
        return {
            "nombre": self.nombre,
            "precio": self.precio,
            "precio_final": self.precio_final,
            "supermercado": self.supermercado,
            "marca": self.marca,
            "tiene_promo": self.tiene_promo,
            "precio_promo": self.precio_promo,
            "promo_descripcion": self.promo_descripcion,
            "imagen_url": self.imagen_url,
            "url_producto": self.url_producto,
            "unidad": self.unidad,
            "disponible": self.disponible,
        }


class SupermarketScraper(ABC):
    """Abstract base class for supermarket scrapers."""

    # Subclasses must define these
    NOMBRE: str = ""
    BASE_URL: str = ""
    COLOR: str = "#333333"  # Brand color for UI
    LOGO_EMOJI: str = "🛒"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
            }
        )
        self._last_request_time = 0
        self._min_delay = 0.5  # Minimum seconds between requests

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Make a rate-limited GET request with error handling."""
        self._rate_limit()
        try:
            kwargs.setdefault("timeout", 15)
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            print(f"[{self.NOMBRE}] Timeout al conectar con {url}")
            raise
        except requests.exceptions.HTTPError as e:
            print(f"[{self.NOMBRE}] Error HTTP {e.response.status_code}: {url}")
            raise
        except requests.exceptions.ConnectionError:
            print(f"[{self.NOMBRE}] Error de conexion con {url}")
            raise

    @abstractmethod
    def buscar_producto(self, query: str, limit: int = 5) -> List[Producto]:
        """
        Search for products matching the query.
        Returns a list of Producto objects, up to `limit` results.
        """
        pass

    def info(self) -> Dict:
        """Return scraper metadata for the frontend."""
        return {
            "nombre": self.NOMBRE,
            "base_url": self.BASE_URL,
            "color": self.COLOR,
            "logo_emoji": self.LOGO_EMOJI,
        }
