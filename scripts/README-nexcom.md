# Fuente única Nexcom

El workflow `sync-catalogo.yml` consulta únicamente la API pública Store de Nexcom. Usa un User-Agent completo de navegador, paginación de 100 en 100 y valida los totales y la unicidad de SKU/ID antes de modificar archivos. `sku` se cruza con `reference`, sin cambiar el ID existente de Kodex.

## Operación

```bash
python3 scripts/sync_nexcom_catalog.py --dry-run --report-file /tmp/nexcom-revision.json
python3 scripts/sync_nexcom_catalog.py
python3 scripts/generate_product_pages.py
```

El workflow ejecuta los dos últimos pasos, guarda ambos JSON públicos, el registro de vistos y las páginas SEO, y publica en GitHub Pages. Horario: 6 a. m. dominicana, sujeto a retrasos de GitHub. Ya no lee `OMEGA_PRICING_RULES` ni consulta las páginas de Omega para datos nuevos. Los scripts antiguos quedan como histórico y no son invocados por el workflow.

## Altas y registros

- `scripts/nexcom_seen_skus.json`: unión persistente de todos los SKU observados; no se quitan referencias cuando desaparecen. La captura inicial verificada contenía 4,707 SKU. Esa primera captura no da de alta productos históricos.
- `scripts/altas-manuales.json`: referencias como cadenas, por ejemplo `["109613"]`. Se incluyen aunque ya fueran conocidas o no cumplan el filtro de interés. Las ausentes se registran sin inventar productos.
- Las nuevas referencias de interés se incluyen tanto con stock como sin él. Sin stock se marcan `proximamente: true`. Al entrar stock se quita la marca; una pérdida posterior de inventario no vuelve a marcar automáticamente un producto habitual.
- Se respeta la eliminación permanente de la referencia 62635 y la exclusión de refurbished/refurbish en altas automáticas.
- El interés usa las marcas ya vendidas y los departamentos, incluidos los padres extraídos de los enlaces públicos de categorías. Seguridad/Redes exige una marca ya vendida, salvo altas manuales.

## Precios y datos

El precio publicado es el de Nexcom en centavos dividido entre 100, sin márgenes ni redondeos adicionales. La respuesta actual anuncia `currency_code: USD` pero muestra `RD$` tanto en `currency_symbol` como en `currency_prefix`. El adaptador acepta exactamente esa combinación observada o el código `DOP`, siempre con dos decimales de moneda. Rechaza una presentación real en US$; no hace conversiones de divisa.

Las descripciones conservan solamente `p`, `strong` y `br`, sin atributos, scripts ni estilos. Las filas `div` se convierten en párrafos. Se conserva la imagen local existente de Omega; Nexcom se descarga con HTTPS verificado solo como respaldo de una imagen ausente.

Cada SKU deja en el log precio anterior, propuesto, retenido/publicado y fuente. Una diferencia superior a RD$500 retiene el precio anterior para revisión. Si más del 20% de los productos existentes propone un precio diferente, **se detiene toda la publicación**, incluso si se retienen individualmente algunos precios. Los productos nuevos no inflan el denominador de este control.

El propietario aprobó una excepción al límite global únicamente para la migración inicial, conservando el límite de RD$500. El argumento manual `--initial-price-migration` solo funciona sobre el catálogo anterior identificado como Omega y se rechaza una vez que la fuente ya es Nexcom. El workflow no utiliza ese argumento: ambas protecciones siguen activas en todas las corridas diarias.

Una respuesta incompleta, SKU ambiguo, precio inválido o fallo de red deja intacto el catálogo publicado. Tres SKU existentes ausentes se conservan con su precio anterior y sin disponibilidad; ausencias masivas detienen la publicación. El reporte completo también se puede guardar con `--report-file`.

## Costos internos

`scripts/factores-costo.json` es la única tabla activa: factor estándar por defecto y las tres excepciones premium indicadas por el propietario. No se consulta ni cambia el portal VIP. Los resultados son estimados derivados, no costos verificados.

El workflow calcula el archivo interno en `$RUNNER_TEMP`: **no se sube como artefacto público, no se añade al commit ni al sitio**. Para Finanzas se debe ejecutar la utilidad desde su backend privado usando esta misma tabla:

```bash
python3 scripts/costos_estimados.py --catalog js/productos-v2.json --output /ruta/privada/nuevo-estimado.json
```

El destino debe ser nuevo y estar fuera del repositorio público. Tiene permisos de archivo privados. La utilidad consulta el precio actual de Nexcom: si el candado retuvo un precio de venta anterior en Kodex, el costo se estima igualmente desde el precio actual de Nexcom, no desde el precio retenido. Las referencias ausentes quedan sin estimado. La utilidad nunca reemplaza un archivo existente ni un costo VIP. Conectar estos estimados a una aplicación financiera externa requiere su backend; esta migración no presume una conexión que aún no se ha configurado.
