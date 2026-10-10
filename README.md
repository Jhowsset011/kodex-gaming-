# Kodex Gaming

Tienda gaming estática con búsqueda, filtros, fichas de producto y carrito local.

## Desarrollo

```sh
python3 -m http.server 8000 --bind 127.0.0.1
python3 -m unittest discover -s tests -v
```

Python 3, OpenSSL y el navegador son suficientes. No requiere paquetes, instalación ni compilación. La tienda prepara pedidos por WhatsApp y no procesa pagos. No enviar mensajes durante las pruebas.

## Catálogo y fuente

La selección del propietario está en `js/productos.json`: 589 referencias únicas. La migración del 10 de octubre verificó 533 fichas públicas de Omega y 56 referencias retiradas. Se conservaron todos los enlaces; 526 productos permiten pedidos, cuatro presentan inventario cero y tres quedaron con modelo pendiente de confirmación por contradicciones internas del suplidor. Cada producto conserva su ID y la dirección `producto.html?id=ID`; `reference` identifica su ficha pública exacta de Omega Tech en `/es/product/consul/REFERENCIA`. `scripts/omega_ids.txt` conserva los **IDs internos de Kodex**, no las referencias de las rutas de Omega. Ambos conjuntos se validan antes de sincronizar. El producto retirado (ID 21890, referencia 62635) sigue excluido.

La sincronización activa consulta exclusivamente el catálogo público de **tienda.omega.com.do**: precio en DOP, inventario publicado por sucursal, número de parte, título, descripción, características y fotografía. No inicia sesión ni consulta precios especiales de una cuenta. Los archivos anteriores de Nexcom se conservan como herramientas históricas; el workflow activo no los ejecuta ni consulta su API.

La clasificación usa el tipo de producto y la información de Omega, con categoría principal y **un solo nivel de subcategorías**. Zona Gamer es una selección adicional. Los filtros conservan su estado al volver de una ficha. La marca procede del fabricante informado por Omega, no de una marca de procesador encontrada dentro del nombre de una laptop.

Las fotografías se descargan con HTTPS verificado desde Omega, se comprueba el formato y se guardan en `img/catalogo` con nombres derivados del contenido. El manifiesto relaciona únicamente URLs públicas y archivos locales. Fotografías idénticas se comparten. Una fotografía inexistente muestra el marcador de imagen pendiente.

Una referencia que Omega confirma retirada conserva su enlace y clasificación, pero queda sin precio ni características antiguas y no permite pedidos. Un precio explícito cero o a consultar también impide pedidos. La web muestra «Consultar precio» y «No disponible». Una respuesta incompleta, un fallo de red, una referencia contradictoria o un problema de TLS detiene la actualización y conserva el último catálogo válido; no se interpreta como agotamiento.

## Precios de venta y configuración privada

`scripts/omega_pricing.py` calcula el costo descontado, selecciona el tramo sobre ese costo y aplica el incremento correspondiente. El costo se redondea a centavos antes de elegir el tramo; el precio final se redondea a centavos con HALF_UP. Por encima del último tramo puede conservarse el precio público del suplidor. Se trata de un incremento sobre costo, no de margen bruto sobre la venta.

Los porcentajes y límites se suministran mediante **OMEGA_PRICING_RULES**, un objeto JSON con `discountPercent`, `bands` (objetos `maxCost` y `markupPercent`) y `aboveMax: "public"`. Los límites deben crecer, sin huecos; cada banda incluye su límite superior. El JSON público contiene solamente el precio final de venta. No contiene el costo descontado, las reglas privadas ni el precio base usado para calcularlo. No guardar el archivo privado en este repositorio, artefactos públicos, instrucciones de configuración o logs.

Para ejecutar en GitHub, añadir **OMEGA_PRICING_RULES** en **Settings → Secrets and variables → Actions → New repository secret**. Los valores se introducen en GitHub, no en el chat. Sin ese secret, el workflow conserva y publica el catálogo existente, informa que la actualización está pendiente y no vuelve a Nexcom. Un secret inválido detiene el flujo antes de consultar al suplidor.

Para validar localmente con un archivo de reglas fuera del checkout:

```sh
python3 scripts/sync_omega.py --policy-file /ruta/privada/reglas.json --dry-run
```

Para sincronizar, quitar `--dry-run`. También puede usarse la variable de entorno, pero no simultáneamente con el archivo. La captura pública revisada de una migración puntual puede suministrarse con `--source-file`; las fotografías verificadas de esa captura, con `--image-cache`. Las ejecuciones diarias siempre consultan fichas actuales. Una captura inicial con muchas referencias ya retiradas exige `--accept-missing-baseline`; este parámetro solo funciona con `--source-file`, tras revisar sus ausencias confirmadas. El control diario de desapariciones extensas cuenta nuevas ausencias respecto al último catálogo válido.

## Actualización automática

`.github/workflows/sync-catalogo.yml` consulta la selección a las **6:00 a. m. de República Dominicana** (10:00 UTC), manualmente desde Actions y tras cambios relevantes en main. GitHub puede demorar las ejecuciones programadas. La actualización automática requiere el secret privado de precios.

El flujo prueba lector, reglas, clasificación, imágenes y escritura. Limita la consulta a dos conexiones simultáneas y dos inicios de petición por segundo. Valida la moneda y la referencia dentro de la ficha; suma el inventario publicado de todas las sucursales. Una desaparición extensa de fichas detiene el proceso para su revisión. No se añaden productos ajenos a la selección ni se duplican referencias.

La escritura del catálogo es atómica y solo se generan commits cuando cambia el contenido. Las ejecuciones programadas o manuales preparan y despliegan un artefacto completo mediante Pages, incluyendo `CNAME`. Los pushes a main también mantienen la publicación habitual desde la rama. Se requieren permisos de escritura del token en main y de despliegue al entorno github-pages.

Omega actualmente omite certificados intermedios en su conexión. El lector obtiene la cadena oficial de Let's Encrypt, la verifica contra las raíces del sistema, con caducidad, propósito y nombre del servidor, y completa la cadena sin desactivar TLS ni confiar en certificados hoja.

## Apariencia y pedidos

El interruptor junto a «Asesoría por WhatsApp» cambia entre modo claro y oscuro en el inicio y las fichas. La elección persiste en `localStorage` (`kodex-theme`); el modo oscuro es el inicial. El carrito (`kodex-cart`) conserva cantidades de 1 a 99 y elimina productos que dejan de estar disponibles o carecen de precio confirmado.

Los botones «Hacer pedido» preparan un mensaje al negocio **+1 809 879 6463** con referencia, cantidad, precio, subtotales y total. Abrir WhatsApp no envía el mensaje: el cliente revisa y confirma disponibilidad y entrega.

## Publicación

La dirección pública es **https://kodexgaming.com/**. Conservar `CNAME`, DNS y Settings → Pages → Deploy from a branch → main → / (root). Comprobar el catálogo realmente servido después de cada publicación; un push o un artefacto creado no demuestra que el dominio haya recibido la nueva versión.
