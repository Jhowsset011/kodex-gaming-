# Kodex Gaming

Tienda gaming estática con catálogo, búsqueda, filtros y carrito local.

## Desarrollo

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

No requiere instalación ni compilación. No procesa pedidos o pagos.

## Catálogo

El catálogo de `js/productos.json` contiene 1,025 productos importados del archivo proporcionado por el propietario, cuya fuente declarada es Nexcom. Se conservan los precios del archivo sin margen adicional y la disponibilidad es la indicada en esa exportación. No son precios de una cuenta de Omega.

Las imágenes descargadas se guardan en `img/catalogo`; los productos sin fotografía usan un marcador. La tienda muestra 24 productos por página y genera sus categorías, marcas y ofertas desde el JSON.

Esta importación es una copia del catálogo, no una conexión o actualización automática con Nexcom. Para actualizarlo se debe importar un catálogo nuevo y validar sus imágenes y precios.

## GitHub Pages

En Settings → Pages, selecciona Deploy from a branch, main y / (root).
