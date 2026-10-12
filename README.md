# Kodex Gaming

Tienda gaming estática con búsqueda, filtros, fichas de producto y carrito local.

## Desarrollo

```sh
python3 -m http.server 8000 --bind 127.0.0.1
python3 -m unittest discover -s tests -v
```

Python 3, OpenSSL y el navegador son suficientes. No requiere paquetes, instalación ni compilación. La tienda prepara pedidos por WhatsApp y no procesa pagos. No enviar mensajes durante las pruebas.

## Catálogo y fuente

La selección completa del propietario está en `data/omega-selection.json`; conserva identidades y clasificación incluso de los productos excluidos de la tienda. `js/productos-v2.json` contiene el catálogo visible tras aplicar las reglas de inventario y condición. Cada producto conserva su ID y la dirección `producto.html?id=ID`; `reference` identifica su ficha pública exacta de Omega Tech en `/es/product/consul/REFERENCIA`. `scripts/omega_ids.txt` conserva los **IDs internos de Kodex**, no las referencias de las rutas de Omega. Ambos conjuntos se validan antes de sincronizar. El producto retirado (ID 21890, referencia 62635) sigue excluido.

La web actual solicita ese catálogo visible sin guardarlo en la caché del navegador. El sincronizador también genera `js/productos.json` con los productos visibles que tienen precio positivo confirmado. Este archivo mantiene funcionando las versiones anteriores de la web que no admiten precios nulos. No se asignan precios ficticios a referencias retiradas ni se eliminan sus identidades de la selección completa. Ambos archivos y la selección se publican en el mismo commit.

La sincronización de precios e inventario consulta exclusivamente el catálogo público de **tienda.omega.com.do**: precio en DOP, inventario publicado por sucursal, número de parte, título, descripción, características y fotografía. Las fichas técnicas pueden completarse con páginas oficiales del fabricante, vinculadas al mismo número de parte. No inicia sesión ni consulta precios especiales de una cuenta. Los archivos anteriores de Nexcom se conservan como herramientas históricas; el workflow activo no los ejecuta ni consulta su API.

La clasificación usa el tipo de producto y la información de Omega, con categoría principal y **un solo nivel de subcategorías**. Zona Gamer es una selección adicional. Los filtros conservan su estado al volver de una ficha. La marca procede del fabricante informado por Omega, no de una marca de procesador encontrada dentro del nombre de una laptop.

Las fotografías se descargan con HTTPS verificado desde Omega, se comprueba el formato y se guardan en `img/catalogo` con nombres derivados del contenido. El manifiesto relaciona únicamente URLs públicas y archivos locales. Fotografías idénticas se comparten. Una fotografía inexistente muestra el marcador de imagen pendiente.

El catálogo visible exige al menos **dos unidades sumando únicamente PRINCIPAL SD y La Nave**. No cuenta las demás sucursales. Se excluye cualquier ficha cuyo título original, marca, descripción, número de parte o características incluyan `refurbish` o `refurbished`, sin distinguir mayúsculas. Los filtros se aplican a todas las marcas de la tienda. Una referencia confirmada retirada también se excluye. Las identidades se conservan en la selección: si un producto vuelve a tener inventario suficiente y cumple la condición, recupera el mismo enlace al sincronizar. La referencia 62635 continúa excluida permanentemente.

Una respuesta incompleta, un fallo de red, la ausencia de las sucursales requeridas o un problema de TLS detiene la actualización y conserva el último catálogo válido; no se interpreta como inventario cero. Un modelo contradictorio sigue pendiente de confirmación y no permite pedidos. Un precio explícito cero o a consultar también impide pedidos; cuando hay inventario suficiente, la web muestra «Consultar precio» y «No disponible».

## Precios de venta y configuración privada

`scripts/omega_pricing.py` calcula el costo descontado, selecciona el tramo sobre ese costo y aplica el incremento correspondiente. El costo se redondea a centavos antes de elegir el tramo; el precio final se redondea a centavos con HALF_UP. Por encima del último tramo puede conservarse el precio público del suplidor. Se trata de un incremento sobre costo, no de margen bruto sobre la venta.

El objeto privado admite `rounding`, con `step` y `downThrough`, para redondear el precio final después del descuento, la selección de tramo y la ganancia. El remanente menor o igual al límite baja al múltiplo anterior; un remanente mayor sube al siguiente. También se aplica al precio público usado por encima del último tramo. La ausencia de `rounding` conserva el cálculo anterior. Un precio positivo que acabaría en cero detiene la sincronización para su revisión.

El workflow exige que las reglas privadas incluyan ese redondeo. Si el secret sigue usando el formato anterior, conserva los precios publicados e informa que requiere actualización. El CLI ofrece `--require-rounding` para aplicar la misma protección localmente.

Los porcentajes y límites se suministran mediante **OMEGA_PRICING_RULES**, un objeto JSON con `discountPercent`, `bands` (objetos `maxCost` y `markupPercent`) y `aboveMax: "public"`. Los límites deben crecer, sin huecos; cada banda incluye su límite superior. El JSON público contiene solamente el precio final de venta. No contiene el costo descontado, las reglas privadas ni el precio base usado para calcularlo. No guardar el archivo privado en este repositorio, artefactos públicos, instrucciones de configuración o logs.

Para ejecutar en GitHub, añadir **OMEGA_PRICING_RULES** en **Settings → Secrets and variables → Actions → New repository secret**. Los valores se introducen en GitHub, no en el chat. Sin ese secret, el workflow conserva y publica el catálogo existente, informa que la actualización está pendiente y no vuelve a Nexcom. Un secret inválido detiene el flujo antes de consultar al suplidor.

Para validar localmente con un archivo de reglas fuera del checkout:

```sh
python3 scripts/sync_omega.py --policy-file /ruta/privada/reglas.json --dry-run
```

Para sincronizar, quitar `--dry-run`. También puede usarse la variable de entorno, pero no simultáneamente con el archivo. La captura pública revisada de una migración puntual puede suministrarse con `--source-file`; las fotografías verificadas de esa captura, con `--image-cache`. Las ejecuciones diarias siempre consultan fichas actuales. Una captura inicial con muchas referencias ya retiradas exige `--accept-missing-baseline`; este parámetro solo funciona con `--source-file`, tras revisar sus ausencias confirmadas. El control diario de desapariciones extensas cuenta nuevas ausencias respecto al último catálogo válido.

## Actualización automática

`.github/workflows/sync-catalogo.yml` consulta la selección a las **6:00 a. m. de República Dominicana** (10:00 UTC), manualmente desde Actions y tras cambios relevantes en main. GitHub puede demorar las ejecuciones programadas. La actualización automática requiere el secret privado de precios.

El flujo prueba lector, reglas, clasificación, selección, imágenes y escritura. Limita la consulta a dos conexiones simultáneas y dos inicios de petición por segundo. Valida la moneda y la referencia dentro de la ficha y aplica el filtro de Principal SD + La Nave. Una desaparición extensa de fichas detiene el proceso para su revisión. No se añaden productos ajenos a la selección ni se duplican referencias.

`scripts/collect_omega_brands.py` y el workflow `auditar-marcas-omega.yml` permiten auditar MSI, AOC, Antec, Samsung, Primus, Corsair, JBL y Logitech desde las búsquedas públicas de Omega. El lector obtiene el filtro exacto de fabricante de las etiquetas publicadas por Omega y recorre todas las páginas en orden por nombre. `data/omega-brand-audit-request.json` indica las marcas de la auditoría; cambiar ese archivo en main inicia una consulta, que también puede ejecutarse manualmente en Actions. La auditoría consulta el inventario actual de la selección existente y recopila fotografías verificadas. No lee reglas privadas ni publica productos por sí sola. `omega_selection.extend_selection` añade una referencia nueva una sola vez y conserva los IDs existentes. Las nuevas referencias usan un espacio de IDs numéricos separado, validado contra colisiones.

Para importar las referencias nuevas desde una auditoría completa revisada:

```sh
python3 scripts/sync_omega.py --policy-file /ruta/privada/reglas.json --require-rounding --source-file /ruta/auditoria/sources.json --image-cache /ruta/auditoria/images --import-brands --brands PRIMUS CORSAIR JBL LOGITECH --dry-run
```

Quitar `--dry-run` después de revisar la captura. `--brands` limita las referencias nuevas a las marcas solicitadas; no quita marcas ya seleccionadas. Sin ese argumento, la importación conserva el grupo original MSI, AOC, Antec y Samsung. Aplica los mismos precios y filtros a toda la selección y escribe catálogo visible, compatibilidad, selección completa e IDs juntos para su publicación. Repetir la misma auditoría no duplica productos. El filtro de inventario y condición se repite en las sincronizaciones diarias; la búsqueda de referencias nuevas de marca requiere una nueva auditoría.

La escritura del catálogo es atómica y solo se generan commits cuando cambia el contenido. Las ejecuciones programadas o manuales preparan y despliegan un artefacto completo mediante Pages, incluyendo `CNAME`. Los pushes a main también mantienen la publicación habitual desde la rama. Se requieren permisos de escritura del token en main y de despliegue al entorno github-pages.

Omega actualmente omite certificados intermedios en su conexión. El lector obtiene la cadena oficial de Let's Encrypt, la verifica contra las raíces del sistema, con caducidad, propósito y nombre del servidor, y completa la cadena sin desactivar TLS ni confiar en certificados hoja.

## Fichas técnicas

`scripts/product_details.py` organiza los datos explícitos de Omega en características por tipo de producto y genera una descripción legible. Las fichas existentes cuentan con 316 entradas revisadas del fabricante; la selección visible cambia según inventario y condición. No completa datos técnicos a partir de modelos parecidos. Las referencias retiradas y los modelos contradictorios siguen pendientes, sin características inventadas.

`data/product-details.json` conserva características revisadas en fuentes oficiales. Cada entrada se vincula por ID, referencia de Omega, marca y número de parte exacto. La limpieza del identificador solo elimina anotaciones del distribuidor; conserva variantes, códigos de región y sufijos de fabricante. Una discrepancia de identidad detiene la publicación. Los enlaces técnicos se validan contra los dominios oficiales de la marca.

Cada sincronización reconstruye los precios e inventario desde Omega y vuelve a aplicar esas fichas, conservando las características verificadas. Las páginas públicas del fabricante están enlazadas desde la ficha de producto; los enlaces a servicios de datos se conservan en el catálogo técnico. La fecha técnica solo cambia cuando cambian los datos de la ficha. La actualización de una fuente oficial requiere revisar y actualizar su entrada; el flujo diario no realiza búsquedas generales en la web.

`data/product-conflicts.json` mantiene las contradicciones de identidad detectadas al contrastar fuentes. Mientras Omega siga usando el modelo contradictorio, el producto conserva su enlace y precio, pero queda pendiente y no permite pedidos. Una corrección del nombre y descripción de Omega permite retirar automáticamente ese bloqueo; un cambio de número de parte requiere revisión.

## Apariencia y pedidos

El interruptor junto a «Asesoría por WhatsApp» cambia entre modo claro y oscuro en el inicio y las fichas. La elección persiste en `localStorage` (`kodex-theme`); el modo oscuro es el inicial. El carrito (`kodex-cart`) conserva cantidades de 1 a 99 y elimina productos que dejan de estar disponibles o carecen de precio confirmado.

Los botones «Hacer pedido» preparan un mensaje al negocio **+1 809 879 6463** con referencia, cantidad, precio, subtotales y total. Abrir WhatsApp no envía el mensaje: el cliente revisa y confirma disponibilidad y entrega.

## Publicación

La dirección pública es **https://kodexgaming.com/**. Conservar `CNAME`, DNS y Settings → Pages → Deploy from a branch → main → / (root). Comprobar el catálogo realmente servido después de cada publicación; un push o un artefacto creado no demuestra que el dominio haya recibido la nueva versión.
