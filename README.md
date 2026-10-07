# Kodex Gaming

Tienda gaming estática con catálogo, búsqueda, filtros y carrito local.

## Desarrollo

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

No requiere instalación ni compilación. Los pedidos se preparan en WhatsApp; la web no procesa pagos.

## Catálogo

`js/productos.json` contiene 408 productos del archivo `kodex-tienda-omega-408.zip` proporcionado por el propietario. El archivo declara que son productos comunes a Nexcom y Omega; sus precios, imágenes, descripciones y disponibilidad provienen de Nexcom. Esta coincidencia no se ha verificado en vivo contra Omega y no representa los precios especiales de una cuenta de Omega.

Se conservan los precios del archivo sin margen adicional. Las 407 referencias a fotografías usan los archivos locales ya descargados en `img/catalogo`; el producto sin fotografía usa un marcador. La tienda muestra 24 productos por página, con categorías, marcas y ofertas generadas desde el JSON. Al cambiar el catálogo se eliminan del carrito los artículos que ya no aparecen en él.

La importación es una copia del archivo, sin conexión ni actualización automática con Omega o Nexcom. Las instrucciones y el flujo de sincronización incluidos en el ZIP no se activaron; ese flujo consulta la API de Nexcom con una lista fija de IDs y no una API de Omega. Para actualizar el catálogo se debe importar un archivo nuevo y validar sus imágenes y precios.

## GitHub Pages

En Settings → Pages, selecciona Deploy from a branch, main y / (root).

## Pedidos por WhatsApp

Los botones «Hacer pedido» de las tarjetas y los detalles preparan un mensaje al número de negocio +1 809 879 6463, con el producto, código, cantidad y precio. El carrito permite ajustar cantidades (1–99), quitar productos y preparar un pedido conjunto con subtotales y total. Abrir WhatsApp no envía el mensaje automáticamente; el cliente revisa y envía el pedido. Disponibilidad y entrega se confirman por WhatsApp.
