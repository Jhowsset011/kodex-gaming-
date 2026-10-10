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

`js/productos.json` contiene 589 referencias únicas. El lote `nuevos-oct10.zip` añadió 18 a las 571 existentes: nueve monitores, cinco fuentes de poder, dos tarjetas gráficas, un disco externo y un combo de teclado y mouse. Se consultaron sus IDs exactos en Nexcom para incorporar precios, fotografías y características. La importación añade solo los IDs ausentes y conserva las fichas anteriores. El disco duro usado de 80GB (referencia 62635, ID 21890), retirado a petición del propietario, permanece fuera del catálogo y de la selección de sincronización. Los nombres iguales con referencias distintas se mantienen como publicaciones diferentes del suplidor; las tarjetas muestran la referencia para distinguirlas.

Los precios, fotografías y características proceden de Nexcom y del lote seleccionado por el propietario. Esta sincronización no consulta la cuenta privada de Omega ni verifica en vivo la coincidencia con su catálogo. Hay 587 productos con fotografías locales y dos con marcador. La tienda muestra 24 productos por página. Una publicación anterior (ID 21308, Lenovo ThinkPad E16) ya no aparece en la API: conserva su ficha, pero se marca como no disponible.

Todos los productos tienen su categoría principal y **un solo nivel de subcategorías**, guardado en `subcategory`. La navegación lateral sigue la referencia de Nexcom: lista de categorías con cantidades y flechas; la categoría seleccionada despliega debajo sus subcategorías con sangría y cantidades. No hay selectores encadenados. Solo se muestran grupos con productos. En Audio y Video se usan Audífonos, Bocinas, Equipos de sonido, Accesorios de audio, Soportes para TV, Streaming y TV Smart y Televisores, según el catálogo disponible.

La selección de categoría muestra todos sus productos; elegir una subcategoría restringe el listado. Los filtros se pueden quitar por separado y se conservan al volver de una ficha. Cada ficha enlaza a su única subcategoría mediante `categoria` y `subcategoria` en la URL. Los enlaces anteriores con `sub1` se aceptan y las selecciones antiguas se adaptan a los nuevos nombres de grupo; `sub2` y `sub3` se ignoran.

La clasificación prioriza el tipo real del producto sobre la categoría comercial: 86 monitores, 158 componentes, 184 periféricos, 68 productos de almacenamiento, 44 de audio y video, 44 laptops, tres muebles y dos computadoras. Zona Gamer es una selección adicional; sus subcategorías agrupan el tipo de producto, como Monitores, Mouse o Audio. Ofertas también permite esa navegación. ThinkPad y ThinkVision se agrupan bajo Lenovo; las licencias Disney y Marvel de Xtech bajo Xtech. Las marcas sin evidencia se mantienen como Genérico. Las subcategorías proceden del tipo de producto identificado por el nombre y las especificaciones disponibles. Las tecnologías, tamaños y capacidades se consultan en la ficha, sin crear niveles adicionales.

## Actualización automática

Se incorporaron y adaptaron los tres archivos solicitados: `scripts/sync_nexcom.py`, `scripts/omega_ids.txt` y `.github/workflows/sync-catalogo.yml`. El flujo se programa todos los días a las **6:00 a. m. de República Dominicana** (10:00 UTC), puede ejecutarse manualmente desde Actions y se inicia al cambiar sus scripts o configuración en main. El horario de GitHub Actions puede sufrir demoras.

La selección se limita a los 589 IDs de `omega_ids.txt`: nuevos productos del suplidor se incorporan únicamente al añadir sus IDs a esa lista. El script consulta directamente esas referencias, incluyendo laptops; actualiza precios sin margen, disponibilidad, descuentos, imágenes y características; y reaplica las reglas de categoría, marca y la única subcategoría de cada producto. Lee el catálogo del checkout, no la copia publicada, para conservar enriquecimiento y archivos locales. Un fallo de red o validación no sustituye el catálogo. Las publicaciones que desaparecen del origen se conservan como no disponibles; una pérdida extensa de fichas detiene la actualización. No se generan commits cuando los datos son iguales.

El flujo guarda los cambios y, en las ejecuciones programadas o manuales, despliega explícitamente un artefacto mediante GitHub Pages. Esto evita depender de que un commit hecho con GITHUB_TOKEN inicie otro flujo. En los pushes del propietario, la publicación automática de la rama main se encarga del despliegue y el job deploy del catálogo se omite para evitar que dos publicaciones se cancelen entre sí. No requiere contraseñas de Nexcom ni Omega. GitHub debe permitir Actions, la escritura del token en main y el despliegue al entorno github-pages; si una protección lo impide, la ejecución muestra el motivo en Actions. El despliegue mediante artefacto del lote de 481 productos se verificó con resultado correcto. Las ejecuciones posteriores pueden consultarse en Actions.

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

Las fichas se consultan por sus IDs exactos en la API pública de Nexcom. La consulta usa `/wp-json/wc/store/v1/products`, validando IDs y referencias antes de incorporar los datos. Las 18 referencias del lote de octubre se recuperaron completas; en total hay 572 fichas con características estructuradas y 17 con características en texto. El JSON conserva `reference`, `description`, `specifications`, `features`, `specificationSources` y `specificationsUpdated`. Las importaciones conservan las fichas existentes; las sincronizaciones posteriores actualizan precios y disponibilidad desde Nexcom. Dos publicaciones del Dell E2318H discrepan en los puertos: esas conexiones se muestran pendientes de confirmación para la unidad, conservando el valor original en `sourceValue`.

Las fichas todavía no tienen verificación independiente con fabricantes oficiales. Las consultas anteriores a Omega fallaron al validar su certificado en el proxy, y las consultas a MSI y Lenovo fueron bloqueadas por la política de acceso de ese entorno. La importación de este lote consulta Nexcom; no usa credenciales privadas de Omega.

## GitHub Pages

La dirección pública es **https://kodexgaming.com/**, con HTTPS. El archivo `CNAME` conserva ese dominio y también se incluye en el artefacto de las sincronizaciones programadas y manuales.

En Settings → Pages, mantén Deploy from a branch, main y / (root). Los pushes del propietario se publican desde la rama. La sincronización diaria y las ejecuciones manuales publican su artefacto mediante `sync-catalogo.yml`; sus commits hechos con GITHUB_TOKEN no disparan una segunda publicación desde la rama. El despliegue del catálogo se omite en eventos push para evitar duplicarlo. Cambiar el origen a GitHub Actions requiere quitar esa condición y usar el workflow para todos los eventos.

## Pedidos por WhatsApp

Los botones «Hacer pedido» de las tarjetas y los detalles preparan un mensaje al número de negocio +1 809 879 6463, con el producto, código, cantidad y precio. El carrito permite ajustar cantidades (1–99), quitar productos y preparar un pedido conjunto con subtotales y total. Abrir WhatsApp no envía el mensaje automáticamente; el cliente revisa y envía el pedido. Disponibilidad y entrega se confirman por WhatsApp.
