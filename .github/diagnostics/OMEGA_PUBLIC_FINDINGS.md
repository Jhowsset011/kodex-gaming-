# Lectura pública de Omega: resultado del 10 de octubre de 2026

La prueba en la rama `codex/probar-omega-publico` obtiene páginas de Omega sin cuenta, cookies de sesión ni credenciales. No cambia `main`, el catálogo publicado ni el flujo Nexcom.

Ejecución verificada: https://github.com/Jhowsset011/kodex-gaming-/actions/runs/38090950521

## HTTPS

El servidor presenta solo la hoja, emitida por Let's Encrypt YE2 y válida para `tienda.omega.com.do` y `sis.omega.com.do`. Python falla inicialmente con `unable to get local issuer certificate` tanto en el entorno de desarrollo como en GitHub Actions.

La cadena se completa con los certificados oficiales disponibles en https://letsencrypt.org/certificates/:

- https://letsencrypt.org/certs/gen-y/int-ye2.pem
- https://letsencrypt.org/certs/gen-y/root-ye-by-x2.pem
- https://letsencrypt.org/certs/gen-y/root-x2-by-x1.pem

Antes de consultar páginas, `openssl verify` comprueba el hostname y la cadena hasta una raíz del sistema existente, usando los certificados descargados como intermediarios. Python mantiene comprobación de hostname y certificado obligatorio, y desactiva `VERIFY_X509_PARTIAL_CHAIN`. No se confía directamente en la hoja ni se incorpora una nueva raíz de confianza. Los certificados y la comprobación se guardan en el artefacto de diagnóstico. Esta configuración debe revisarse si Omega cambia de emisor; un fallo debe conservar el último catálogo válido.

## Datos comprobados

Las fichas públicas siguen la ruta `/es/product/consul/REFERENCIA`. Se descargaron y analizaron cuatro referencias presentes en Kodex:

| Referencia | Producto | Precio público DOP |
| --- | --- | ---: |
| 111698 | MSI MAG 346CQDF E20, 34 pulgadas | 23,099.83 |
| 110069 | MSI MAG 272F X24, 27 pulgadas | 13,124.90 |
| 109640 | MSI MAG A750GLS PCIE5, 750 W | 6,929.95 |
| 106019 | Xtech Fireshot XTS-131 | 786.95 |

Se verificaron URL canónica, referencia de producto, nombre, número de parte, precio, selector DOP, descripción e inventario numérico por sucursal. Las dos fotografías de monitores se descargaron de `https://sis.omega.com.do/ProductImages/`, verificando HTTPS, tipo de contenido y firma PNG.

El HTML ofrece categoría en la ruta de navegación. Las descripciones de estas muestras contienen características principales, pero no todas las fichas tienen una tabla técnica completa. No se comprobó una API oficial. `/robots.txt` permite estas rutas y solo declara `Disallow: /private_file.html`. `/sitemap.xml` devuelve una página de error con HTTP 200; no es un sitemap válido.

## Validaciones necesarias antes de migrar

- Un HTTP 200 no prueba que exista el producto: validar la URL canónica, botón de producto dentro de su resumen, referencia, modelo/número de parte y moneda.
- Las cuatro referencias coinciden, pero no se han comprobado las 589. Mantener los IDs de Kodex y verificar cada correspondencia; los IDs de Nexcom no son IDs de Omega.
- Omega 109640 muestra `MAG A750BN PCIE5` en el título, mientras su número de parte y descripción indican `MAG A750GLS PCIE5`. Conservar esta discrepancia para revisión y evitar reemplazar automáticamente el nombre correcto de Kodex.
- Leer la moneda en `#select-currency`: el símbolo `$` por sí solo no acredita DOP. En estas muestras está seleccionado `RD (DOP)`.
- El HTML examinado no confirma si el precio incluye impuestos. No afirmar condiciones tributarias ni transformar la garantía del proveedor en una oferta propia de Kodex.
- Separar el precio público del costo privado y del precio final de venta. No publicar descuento de cuenta, costos privados o credenciales en JSON, logs, artefactos o repositorio.
- Adaptar clasificación, dominios de fotografías y metadatos de origen; los actuales contienen reglas específicas de Nexcom. Mantener una sola subcategoría y el retiro de ID 21890 / referencia 62635.

La conexión pública está demostrada mediante HTML. La activación de una sincronización Omega en producción requiere validar la selección completa y definir el precio de venta.
