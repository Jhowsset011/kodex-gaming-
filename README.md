# Kodex Gaming

Tienda gaming estática con catálogo, búsqueda, filtros y carrito local.

## Desarrollo

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

No requiere instalación ni compilación. Los pedidos se preparan en WhatsApp; la web no procesa pagos.

## Apariencia

El interruptor de sol/luna cambia entre modo claro y oscuro en la tienda y las fichas de producto. En el inicio y en las fichas aparece en la barra superior, junto a «Asesoría por WhatsApp». El modo oscuro es el inicial y conserva la paleta existente. El modo claro tiene fondos suaves, texto oscuro y un logo preparado para fondo claro. La elección se guarda en `localStorage` (`kodex-theme`), se aplica antes de cargar los estilos y se sincroniza entre pestañas. Si el navegador bloquea el almacenamiento, el interruptor sigue funcionando durante la visita. Los estilos del tema claro están en `css/tema.css`; `js/tema.js` controla la selección. Las referencias a estilos y scripts llevan una versión para invalidar copias antiguas al publicar cambios.

## Catálogo

`js/productos.json` contiene 408 productos del archivo `kodex-tienda-omega-408.zip` proporcionado por el propietario. El archivo declara que son productos comunes a Nexcom y Omega; sus precios, imágenes, descripciones y disponibilidad provienen de Nexcom. Esta coincidencia no se ha verificado en vivo contra Omega y no representa los precios especiales de una cuenta de Omega.

Se conservan los precios del archivo sin margen adicional. Las 407 referencias a fotografías usan los archivos locales ya descargados en `img/catalogo`; el producto sin fotografía usa un marcador. La tienda muestra 24 productos por página, con categorías, marcas y ofertas generadas desde el JSON. Al cambiar el catálogo se eliminan del carrito los artículos que ya no aparecen en él.

La importación es una copia del archivo, sin conexión ni actualización automática con Omega o Nexcom. Las instrucciones y el flujo de sincronización incluidos en el ZIP no se activaron; ese flujo consulta la API de Nexcom con una lista fija de IDs y no una API de Omega. Para actualizar el catálogo se debe importar un archivo nuevo y validar sus imágenes y precios.

## Páginas de producto

La imagen y el nombre de cada tarjeta enlazan a `producto.html?id=ID`. Cada ficha tiene una URL que se puede compartir, fotografía, referencia, descripción completa, características, pedido por WhatsApp y productos de la misma categoría. El carrito se conserva entre páginas; al volver al catálogo se recuperan búsqueda, filtros, orden y página.

Las características de los 408 productos se recuperaron por sus IDs exactos de la API pública de Nexcom (`/wp-json/wc/store/v1/products`), comprobando el nombre de cada producto antes de incorporarlas. Hay 397 fichas con características estructuradas y 11 con características en texto. El JSON conserva `reference`, `description`, `specifications`, `features`, `specificationSources` y `specificationsUpdated`. Esta consulta no modifica precios ni disponibilidad del archivo original. Dos publicaciones del Dell E2318H discrepan en los puertos: esas conexiones se muestran pendientes de confirmación para la unidad, conservando el valor original en `sourceValue`.

Omega no se pudo consultar por un fallo de validación del certificado en el proxy del entorno. Las consultas de especificaciones a MSI y Lenovo fueron bloqueadas por la política de acceso; por tanto, estas fichas todavía no tienen verificación independiente con fabricantes oficiales. Se añadieron `www.msi.com`, `psref.lenovo.com` y `www.samsung.com` al borrador de configuración de red, conservando los dominios existentes. Ese borrador requiere revisar, guardar y publicar la configuración del entorno para aplicarse; no cambia el acceso de esta sesión.

## GitHub Pages

En Settings → Pages, selecciona Deploy from a branch, main y / (root).

## Pedidos por WhatsApp

Los botones «Hacer pedido» de las tarjetas y los detalles preparan un mensaje al número de negocio +1 809 879 6463, con el producto, código, cantidad y precio. El carrito permite ajustar cantidades (1–99), quitar productos y preparar un pedido conjunto con subtotales y total. Abrir WhatsApp no envía el mensaje automáticamente; el cliente revisa y envía el pedido. Disponibilidad y entrega se confirman por WhatsApp.
