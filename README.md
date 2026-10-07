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

`js/productos.json` contiene 481 referencias únicas: las 408 existentes y 73 nuevas de `kodex-tienda-omega-481.zip`. La importación conserva los precios y la disponibilidad anteriores y añade solo los IDs ausentes. Todos los productos tienen una referencia de suplidor distinta; los nombres iguales con referencias distintas se mantienen como publicaciones diferentes del suplidor.

El archivo declara que son productos comunes a Nexcom y Omega. Los precios, fotografías y características proceden de Nexcom; esta sincronización no consulta la cuenta privada de Omega ni verifica en vivo esa coincidencia. Hay 480 productos con fotografías locales y uno con marcador. La tienda muestra 24 productos por página, con categorías, marcas y ofertas generadas desde el JSON.

Se revisaron las 481 fichas: 136 categorías y 37 marcas se corrigieron respecto al lote recibido. El tipo de producto tiene prioridad sobre la categoría comercial del suplidor: todos los monitores están en Monitores; los SSD en Almacenamiento; las televisiones en Audio y Video; y las computadoras, laptops y sillas en sus categorías correspondientes. ThinkPad y ThinkVision se agrupan bajo Lenovo, y las licencias Disney/Marvel de productos Xtech bajo Xtech. Seis referencias sin fabricante identificable quedan como Genérico. Zona Gamer es una selección adicional, de modo que sus productos también aparecen en su categoría real. Las tarjetas muestran la referencia para distinguir publicaciones con nombres parecidos.

## Actualización automática

Se incorporaron y adaptaron los tres archivos solicitados: `scripts/sync_nexcom.py`, `scripts/omega_ids.txt` y `.github/workflows/sync-catalogo.yml`. El flujo se programa todos los días a las **6:00 a. m. de República Dominicana** (10:00 UTC), puede ejecutarse manualmente desde Actions y se inicia al cambiar sus scripts o configuración en main. El horario de GitHub Actions puede sufrir demoras.

La selección se limita a los 481 IDs de `omega_ids.txt`: nuevos productos del suplidor se incorporan únicamente al añadir sus IDs a esa lista. El script consulta directamente esas referencias, incluyendo laptops; actualiza precios sin margen, disponibilidad, descuentos, imágenes y características; y reaplica las reglas de categoría y marca. Lee el catálogo del checkout, no la copia publicada, para conservar enriquecimiento y archivos locales. Un fallo de red o validación no sustituye el catálogo. Las publicaciones que desaparecen del origen se conservan como no disponibles; una pérdida extensa de fichas detiene la actualización. No se generan commits cuando los datos son iguales.

El flujo guarda los cambios y despliega explícitamente un artefacto de la web mediante GitHub Pages. Esto evita depender de que un commit hecho con GITHUB_TOKEN inicie otro flujo. No requiere contraseñas de Nexcom ni Omega. GitHub debe permitir Actions, la escritura del token en main y el despliegue al entorno github-pages; si una protección lo impide, la ejecución muestra el motivo en Actions. La primera ejecución remota no se puede comprobar desde este entorno porque el acceso a la API de GitHub está bloqueado.

Para verificar sin escribir:

```sh
python3 scripts/sync_nexcom.py --dry-run
python3 -m unittest discover -s tests -v
```

Para sincronizar manualmente desde un checkout con conexión:

```sh
python3 scripts/sync_nexcom.py
```

## Páginas de producto

La imagen y el nombre de cada tarjeta enlazan a `producto.html?id=ID`. Cada ficha tiene una URL que se puede compartir, fotografía, referencia, descripción completa, características, pedido por WhatsApp y productos de la misma categoría. El carrito se conserva entre páginas; al volver al catálogo se recuperan búsqueda, filtros, orden y página.

Las características de los 481 productos se recuperaron por sus IDs exactos de la API pública de Nexcom (`/wp-json/wc/store/v1/products`), comprobando el nombre de cada producto antes de incorporarlas. Hay 468 fichas con características estructuradas y 13 con características en texto. El JSON conserva `reference`, `description`, `specifications`, `features`, `specificationSources` y `specificationsUpdated`. La importación inicial conserva precios y disponibilidad; las sincronizaciones posteriores actualizan ambos desde Nexcom. Dos publicaciones del Dell E2318H discrepan en los puertos: esas conexiones se muestran pendientes de confirmación para la unidad, conservando el valor original en `sourceValue`.

Omega no se pudo consultar por un fallo de validación del certificado en el proxy del entorno. Las consultas de especificaciones a MSI y Lenovo fueron bloqueadas por la política de acceso; por tanto, estas fichas todavía no tienen verificación independiente con fabricantes oficiales. Se añadieron `www.msi.com`, `psref.lenovo.com` y `www.samsung.com` al borrador de configuración de red, conservando los dominios existentes. Ese borrador requiere revisar, guardar y publicar la configuración del entorno para aplicarse; no cambia el acceso de esta sesión.

## GitHub Pages

En Settings → Pages, selecciona Deploy from a branch, main y / (root).

## Pedidos por WhatsApp

Los botones «Hacer pedido» de las tarjetas y los detalles preparan un mensaje al número de negocio +1 809 879 6463, con el producto, código, cantidad y precio. El carrito permite ajustar cantidades (1–99), quitar productos y preparar un pedido conjunto con subtotales y total. Abrir WhatsApp no envía el mensaje automáticamente; el cliente revisa y envía el pedido. Disponibilidad y entrega se confirman por WhatsApp.
