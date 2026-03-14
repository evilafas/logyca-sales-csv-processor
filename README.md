# LOGYCA - Sales CSV Processor

Sistema de procesamiento asíncrono de archivos CSV de ventas con FastAPI, Azure Blob/Queue Storage, PostgreSQL y N8N.

---

## Tabla de contenidos

1. [Arquitectura](#arquitectura)
2. [Prerrequisitos](#prerrequisitos)
3. [Instalacion paso a paso](#instalación-paso-a-paso)
4. [Guia de uso completa](#guía-de-uso-completa)
5. [Importar workflow en N8N](#importar-workflow-en-n8n)
6. [Pruebas unitarias](#pruebas-unitarias)
7. [Pruebas de carga (CSV grande)](#pruebas-de-carga-csv-grande)
8. [Endpoints API](#endpoints-api)
9. [Base de datos](#base-de-datos)
10. [Decisiones tecnicas](#decisiones-técnicas)
11. [Estructura del proyecto](#estructura-del-proyecto)
12. [Solucion de problemas](#solución-de-problemas)

---

## Arquitectura

El sistema tiene 5 componentes que se comunican entre sí:

```
                    ┌──────────────┐
  CSV ──────────>   │  POST /upload │
                    │   (FastAPI)   │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              v                         v
    ┌──────────────┐          ┌──────────────┐
    │  Azure Blob  │          │ Azure Queue  │
    │   Storage    │          │  (mensaje)   │
    │  (Azurite)   │          │  (Azurite)   │
    └──────────────┘          └──────┬───────┘
                                     │
                                     v
                            ┌──────────────┐
                            │    Worker    │
                            │  (consumer)  │
                            └──────┬───────┘
                                   │ streaming + COPY
                                   v
                            ┌──────────────┐
                            │  PostgreSQL  │
                            │  (sales)     │
                            └──────┬───────┘
                                   │
                                   v
                            ┌──────────────┐
                            │     N8N      │
                            │  (cron 5min) │
                            │  summary     │
                            └──────────────┘
```

### Flujo paso a paso

1. El usuario sube un archivo CSV al endpoint `POST /upload`
2. La API guarda el archivo en **Azure Blob Storage** (Azurite en local)
3. La API envía un mensaje a **Azure Queue** indicando que hay un archivo por procesar
4. La API responde inmediatamente con un `job_id` (no espera a que se procese)
5. El **Worker** (proceso independiente) escucha la cola cada 5 segundos
6. Cuando recibe un mensaje, descarga el CSV desde Blob Storage
7. Procesa el CSV **línea por línea** (sin cargarlo completo en memoria)
8. Inserta los datos en PostgreSQL usando `COPY` en batches de 5,000 filas
9. Actualiza el estado del job a `COMPLETED` (o `FAILED` si hay error)
10. El usuario consulta el estado con `GET /job/{job_id}`
11. **N8N** ejecuta un workflow cada 5 minutos que calcula el resumen diario de ventas

---

## Prerrequisitos

Solo necesitas tener instalado **Docker Desktop**. Todo lo demás corre dentro de contenedores.

### Verificar que Docker está instalado

Abre una terminal (CMD, PowerShell, o Git Bash) y ejecuta:

```bash
docker --version
```

Deberías ver algo como:
```
Docker version 29.0.1, build ...
```

Si no tienes Docker, descárgalo de: https://www.docker.com/products/docker-desktop/

**Importante:** Asegúrate de que Docker Desktop esté **abierto y corriendo** (el icono de la ballena en la barra de tareas debe estar activo, sin animación de carga).

---

## Instalación paso a paso

### Paso 1: Clonar o descargar el proyecto

Si tienes el código en un repositorio:
```bash
git clone <url-del-repositorio>
cd RetoTecnicoLogyca
```

Si lo descargaste como ZIP, descomprimirlo y abrir una terminal en esa carpeta:
```bash
cd ruta/a/RetoTecnicoLogyca
```

### Paso 2: Verificar que los archivos existan

Ejecuta este comando para ver la estructura:
```bash
ls -la
```

Debes ver al menos estos archivos:
```
docker-compose.yml
Dockerfile
.env
requirements.txt
```

Si no existe el archivo `.env`, créalo copiando el ejemplo:
```bash
cp .env.example .env
```

### Paso 3: Levantar todos los servicios

Este es el comando principal. Construye las imágenes Docker y levanta los 5 servicios:

```bash
docker-compose up --build -d
```

**¿Qué significa cada flag?**
- `--build`: reconstruye las imágenes (necesario la primera vez o cuando cambias código)
- `-d`: ejecuta en segundo plano (detached), para que la terminal quede libre

**La primera vez tarda entre 2-5 minutos** porque descarga las imágenes de Docker (PostgreSQL, Azurite, N8N, Python). Las siguientes veces tarda segundos.

### Paso 4: Verificar que todo está corriendo

```bash
docker-compose ps
```

Debes ver 5 servicios con estado "Up":

```
NAME                           STATUS          PORTS
retotecnicologyca-api-1        Up              0.0.0.0:8000->8000/tcp
retotecnicologyca-azurite-1    Up              0.0.0.0:10000-10002->10000-10002/tcp
retotecnicologyca-n8n-1        Up              0.0.0.0:5678->5678/tcp
retotecnicologyca-postgres-1   Up (healthy)    0.0.0.0:5432->5432/tcp
retotecnicologyca-worker-1     Up
```

### Paso 5: Verificar que la API responde

```bash
curl http://localhost:8000/health
```

Respuesta esperada:
```json
{"status":"ok"}
```

**Alternativa sin curl:** Abre tu navegador y ve a http://localhost:8000/health

Si ves `{"status":"ok"}`, todo está funcionando correctamente.

---

## Guía de uso completa

### 1. Subir un archivo CSV

El proyecto incluye un archivo CSV de ejemplo en `data/sample.csv`. Para subirlo:

```bash
curl -X POST http://localhost:8000/upload -F "file=@data/sample.csv"
```

**Respuesta:**
```json
{
  "job_id": "08252cbd-4d3e-4316-884a-8487769c3fea",
  "message": "File uploaded. Processing started."
}
```

**Copia el `job_id`**, lo necesitarás en el siguiente paso.

**¿Qué pasó internamente?**
1. El CSV se subió a Azure Blob Storage (Azurite)
2. Se creó un registro en la tabla `jobs` con estado `PENDING`
3. Se envió un mensaje a la cola para que el Worker lo procese
4. La API respondió inmediatamente (no esperó al procesamiento)

### 2. Consultar el estado del procesamiento

Reemplaza `{job_id}` con el ID que recibiste:

```bash
curl http://localhost:8000/job/08252cbd-4d3e-4316-884a-8487769c3fea
```

**Posibles respuestas:**

| Estado | Significado |
|--------|-------------|
| `PENDING` | El archivo está en la cola, esperando ser procesado |
| `PROCESSING` | El Worker está procesando el archivo ahora |
| `COMPLETED` | Procesamiento exitoso, datos insertados en la BD |
| `FAILED` | Ocurrió un error (ver logs del worker) |

Normalmente el archivo de ejemplo se procesa en menos de 2 segundos:
```json
{"job_id": "08252cbd-4d3e-4316-884a-8487769c3fea", "status": "COMPLETED"}
```

### 3. Ver los datos en la base de datos

**Ver los registros de ventas insertados:**
```bash
docker exec retotecnicologyca-postgres-1 psql -U logyca -d logyca -c "SELECT * FROM sales;"
```

Salida esperada (10 filas del CSV de ejemplo):
```
 id |    date    | product_id | quantity | price  | total
----+------------+------------+----------+--------+--------
  1 | 2026-01-01 |       1001 |        2 |  10.50 |  21.00
  2 | 2026-01-01 |       1002 |        1 |   5.20 |   5.20
  3 | 2026-01-01 |       1003 |        5 |   3.75 |  18.75
  ...
```

**Ver el estado de los jobs:**
```bash
docker exec retotecnicologyca-postgres-1 psql -U logyca -d logyca -c "SELECT id, status, filename, records_processed FROM jobs;"
```

**Ver el resumen diario (se llena después de ejecutar el workflow de N8N):**
```bash
docker exec retotecnicologyca-postgres-1 psql -U logyca -d logyca -c "SELECT * FROM sales_daily_summary ORDER BY date;"
```

### 4. Usar el Swagger UI (interfaz visual)

Si prefieres no usar curl, abre en tu navegador:

**http://localhost:8000/docs**

Esto muestra una interfaz interactiva donde puedes:
1. Click en el endpoint que quieras probar (ej: `POST /upload`)
2. Click en **"Try it out"**
3. Seleccionar un archivo CSV en el campo `file`
4. Click en **"Execute"**
5. Ver la respuesta abajo

### 5. Calcular el resumen diario manualmente

Si no quieres esperar a que N8N lo haga automáticamente:

```bash
curl -X POST http://localhost:8000/summary/calculate
```

Respuesta:
```json
[
  {"date": "2026-01-01", "total_sales": 44.95, "record_count": 3},
  {"date": "2026-01-02", "total_sales": 72.30, "record_count": 3},
  {"date": "2026-01-03", "total_sales": 329.40, "record_count": 4}
]
```

---

## Importar workflow en N8N

N8N es una herramienta de automatización visual. Nuestro workflow consulta periódicamente los jobs completados y calcula el resumen diario de ventas.

### Paso 1: Abrir N8N

Abre en tu navegador: **http://localhost:5678**

La primera vez te pedirá crear una cuenta. Es una cuenta local (solo vive en tu Docker), puedes usar cualquier email/contraseña.

### Paso 2: Crear un nuevo workflow

1. Click en el icono **"+"** (arriba a la izquierda, al lado del logo de n8n)
2. Selecciona **"Workflow"**

### Paso 3: Importar el archivo

1. Click en el menú **"..."** (tres puntos, arriba a la derecha)
2. Click en **"Import from file..."**
3. Navega hasta la carpeta del proyecto y selecciona: `n8n/workflow.json`

**Alternativa (copiar y pegar):** También puedes abrir `n8n/workflow.json` en un editor de texto, copiar todo el contenido (Ctrl+A, Ctrl+C), ir al canvas vacío de N8N y pegar (Ctrl+V).

### Paso 4: Verificar el workflow

Debes ver 3 nodos conectados:
```
Every 5 Minutes → Check Completed Jobs → Calculate Daily Summary
```

### Paso 5: Ejecutar manualmente

Click en el botón rojo **"Execute workflow"** (abajo al centro).

Si todo funciona, verás los nodos en verde con la cantidad de items procesados:
- Every 5 Minutes: 1 item
- Check Completed Jobs: 1 item (el job del CSV que subimos)
- Calculate Daily Summary: 3 items (3 días de resumen)

### Paso 6 (opcional): Activar ejecución automática

Si quieres que se ejecute automáticamente cada 5 minutos:
1. Click en **"Publish"** (arriba a la derecha)
2. El workflow quedará activo y se ejecutará según el schedule

---

## Pruebas unitarias

El proyecto incluye **49 pruebas unitarias** que no requieren conexion a la base de datos (usan mocks).

### Ejecutar todos los tests

```bash
docker exec retotecnicologyca-api-1 python -m pytest tests/ -v
```

**Alternativa** (si el contenedor no esta corriendo):
```bash
docker compose run --rm --no-deps api python -m pytest tests/ -v
```

### Resultado esperado

```
tests/test_api.py        ... 10 passed
tests/test_processor.py  ... 31 passed
tests/test_services.py   ...  8 passed

======================== 49 passed in ~1s =========================
```

### Que cubre cada archivo de tests

| Archivo | Tests | Que verifica |
|---------|-------|-------------|
| `test_processor.py` | 31 | Validacion de filas CSV (`validate_row`): campos requeridos, formato de fecha, product_id positivo, quantity/price no negativos. Parsing de filas, calculo de `total = quantity * price`, redondeo decimal. Que el parser es un generador (memoria eficiente). Que acepta streams (no solo strings). Escape de caracteres especiales en el buffer COPY. Tamano de batch razonable. |
| `test_api.py` | 10 | Upload exitoso de CSV, rechazo de archivos no-CSV, error al no enviar archivo, consulta de job existente/inexistente/UUID invalido, diferentes estados de job (PENDING/COMPLETED/FAILED), listado de jobs completados |
| `test_services.py` | 8 | Creacion de job con status PENDING y UUID, consulta de job existente y no existente, actualizacion de status con y sin campos opcionales (error_message, records_processed) |

---

## Pruebas de carga (CSV grande)

El proyecto incluye un script para generar CSVs de cualquier tamaño.

### Generar un CSV de 1 millón de filas

```bash
docker exec retotecnicologyca-api-1 python data/generate_csv.py 1000000 data/large_sample.csv
```

Esto genera un archivo de ~45 MB con 1 millón de filas de datos aleatorios.

### Subir el CSV grande

```bash
curl -X POST http://localhost:8000/upload -F "file=@data/large_sample.csv"
```

### Monitorear el procesamiento

```bash
# Ver logs del worker en tiempo real
docker logs -f retotecnicologyca-worker-1

# Consultar el estado del job
curl http://localhost:8000/job/{job_id}

# Ver cuántos registros hay en la tabla sales
docker exec retotecnicologyca-postgres-1 psql -U logyca -d logyca -c "SELECT COUNT(*) FROM sales;"
```

---

## Endpoints API

| Método | Ruta | Descripción | Ejemplo de respuesta |
|--------|------|-------------|---------------------|
| `POST` | `/upload` | Sube CSV, lo almacena en Blob Storage, encola procesamiento | `{"job_id": "uuid", "message": "File uploaded..."}` |
| `GET` | `/job/{job_id}` | Estado del procesamiento del job | `{"job_id": "uuid", "status": "COMPLETED"}` |
| `GET` | `/jobs/completed` | Lista todos los jobs completados (usado por N8N) | `[{"job_id": "uuid", "status": "COMPLETED", ...}]` |
| `POST` | `/summary/calculate` | Calcula resumen diario de ventas (usado por N8N) | `[{"date": "2026-01-01", "total_sales": 44.95, ...}]` |
| `GET` | `/health` | Health check del servicio | `{"status": "ok"}` |

### Formato del CSV esperado

```csv
date,product_id,quantity,price
2026-01-01,1001,2,10.50
2026-01-01,1002,1,5.20
```

| Campo | Tipo | Restricciones |
|-------|------|---------------|
| `date` | `YYYY-MM-DD` | Formato estricto, requerido |
| `product_id` | entero | Mayor que 0, requerido |
| `quantity` | entero | Mayor o igual a 0, requerido |
| `price` | decimal | Mayor o igual a 0, requerido |

El campo `total` se calcula automaticamente: `total = quantity * price`

### Validaciones al subir un archivo

El endpoint `POST /upload` valida **antes** de aceptar el archivo:

| Validacion | Error si falla |
|------------|----------------|
| Extension `.csv` | `400: Only CSV files are allowed` |
| Content-type `text/csv` o `application/octet-stream` | `400: Invalid content type` |
| Tamano maximo: 500 MB | `400: File too large` |
| Archivo no vacio | `400: File is empty` |
| Columnas requeridas en el header | `400: CSV missing required columns: ...` |

Adicionalmente, durante el procesamiento el Worker valida **cada fila** del CSV:
- Formato de fecha (`YYYY-MM-DD`)
- `product_id` sea un entero positivo
- `quantity` sea un entero no negativo
- `price` sea un decimal no negativo
- Si alguna fila es invalida, el job queda en estado `FAILED` con el mensaje de error

---

## Base de datos

Se usa PostgreSQL 15. Las tablas se crean automáticamente al iniciar el contenedor (via `sql/init.sql`).

### Tabla `jobs`

Registra cada archivo CSV subido y su estado de procesamiento.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | UUID | Identificador único del job |
| `status` | VARCHAR | PENDING, PROCESSING, COMPLETED, FAILED |
| `filename` | VARCHAR | Nombre original del archivo |
| `blob_url` | TEXT | URL del archivo en Blob Storage |
| `created_at` | TIMESTAMP | Fecha de creación |
| `updated_at` | TIMESTAMP | Última actualización |
| `error_message` | TEXT | Mensaje de error (si falló) |
| `records_processed` | INTEGER | Cantidad de filas insertadas |

### Tabla `sales`

Cada fila representa una venta individual.

| Campo | Tipo | Restriccion | Descripcion |
|-------|------|-------------|-------------|
| `id` | BIGSERIAL | PK | ID autoincremental |
| `date` | DATE | NOT NULL | Fecha de la venta |
| `product_id` | INTEGER | CHECK > 0 | ID del producto |
| `quantity` | INTEGER | CHECK >= 0 | Cantidad vendida |
| `price` | NUMERIC(12,2) | CHECK >= 0 | Precio unitario |
| `total` | NUMERIC(14,2) | CHECK >= 0 | Total = quantity * price |

Indices: `date`, `product_id`

### Tabla `sales_daily_summary`

Resumen diario calculado por el workflow de N8N.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | SERIAL | ID autoincremental |
| `date` | DATE | Fecha (UNIQUE) |
| `total_sales` | NUMERIC(16,2) | Suma de ventas del día |
| `record_count` | INTEGER | Cantidad de registros del día |
| `updated_at` | TIMESTAMP | Última actualización |

### Conectarse a PostgreSQL directamente

```bash
docker exec -it retotecnicologyca-postgres-1 psql -U logyca -d logyca
```

Esto abre una consola interactiva. Comandos útiles:
- `\dt` - ver todas las tablas
- `\d sales` - ver estructura de la tabla sales
- `SELECT COUNT(*) FROM sales;` - contar registros
- `\q` - salir

---

## Decisiones técnicas

### 1. No cargar el CSV completo en memoria

El CSV se procesa como un **generador** Python (`parse_csv_rows` en `app/worker/processor.py`). Esto significa que:
- Se lee una fila a la vez del archivo
- Las filas se acumulan en un batch de 5,000
- Cuando el batch está lleno, se inserta en la BD y se limpia de memoria
- Uso de memoria constante: **O(batch_size)**, sin importar si el archivo tiene 10 filas o 10 millones

### 2. Estrategia de inserción masiva (PostgreSQL COPY)

En vez de hacer `INSERT INTO sales VALUES (...)` por cada fila, se usa `COPY FROM` de PostgreSQL via `psycopg2.copy_from()`. Esto es **10-100x más rápido** porque:
- Envía todas las filas del batch en una sola operación de red
- PostgreSQL las procesa en bulk sin ejecutar el query planner por cada fila
- Minimiza el overhead transaccional

### 3. Como se evita saturar PostgreSQL

| Mecanismo | Como funciona |
|-----------|---------------|
| Batches de 5,000 filas | Cada batch hace COMMIT, liberando locks y permitiendo que PostgreSQL haga VACUUM |
| Pool de conexiones | SQLAlchemy limita a 10 conexiones simultaneas + 20 overflow |
| `pool_pre_ping=True` | Detecta conexiones muertas antes de usarlas, evitando errores en runtime |
| `pool_recycle=1800` | Recicla conexiones cada 30 min para evitar timeouts por inactividad |
| Un worker por mensaje | El visibility timeout (600s) de la cola previene que dos workers procesen el mismo archivo |
| COPY vs INSERT | Reduce la carga de CPU y I/O en el servidor de BD |
| CHECK constraints en SQL | `product_id > 0`, `quantity >= 0`, `price >= 0`, `total >= 0` como defensa a nivel de BD |

Para escalar: se pueden agregar mas workers (replicas del servicio `worker` en Docker Compose) y PostgreSQL distribuira la carga naturalmente via la cola.

### 4. Azure local con Azurite

**Azurite** es el emulador oficial de Microsoft para Azure Storage. Permite desarrollar y probar sin necesidad de una cuenta de Azure real. Los mismos SDKs de Python (`azure-storage-blob`, `azure-storage-queue`) funcionan de manera idéntica. Para producción, solo se cambia la `AZURE_STORAGE_CONNECTION_STRING` en el archivo `.env`.

### 5. Seguridad del contenedor

El `Dockerfile` crea un usuario no-root (`appuser`) para ejecutar la aplicacion. Esto sigue el principio de minimo privilegio: si un atacante compromete el proceso, no tendria permisos de root dentro del contenedor.

### 6. Descarga streaming desde Blob Storage

El metodo `download_blob_as_stream()` descarga el archivo de Blob Storage como un stream de texto (`TextIOWrapper`). Esto evita cargar el archivo completo en memoria antes de procesarlo. El Worker recibe el stream y lo pasa directamente al parser CSV.

### 7. Validacion en multiples capas

La validacion de datos se hace en 3 niveles:

| Capa | Que valida |
|------|-----------|
| **API** (upload) | Extension, content-type, tamano, headers CSV |
| **Worker** (procesamiento) | Formato de fecha, tipos numericos, valores positivos |
| **PostgreSQL** (CHECK constraints) | Restricciones a nivel de BD como ultima linea de defensa |

### 8. Diseno de capas

```
API (routes.py) → Services (blob, queue, job) → DB (SQLAlchemy / psycopg2)
                                                   ↑
Worker (consumer.py) → Processor (processor.py) ───┘
```

- **API layer** (`app/api/`): validación HTTP, coordinación de servicios
- **Service layer** (`app/services/`): lógica de negocio, interacción con Azure y BD
- **Worker layer** (`app/worker/`): procesamiento asíncrono, desacoplado de la API
- **DB layer** (`app/db/`): modelos ORM y sesiones de base de datos

---

## Estructura del proyecto

```
RetoTecnicoLogyca/
├── docker-compose.yml          # Define los 5 servicios Docker
├── Dockerfile                  # Imagen Python para api y worker
├── .env                        # Variables de entorno (no subir a git)
├── .env.example                # Ejemplo de variables de entorno
├── .dockerignore               # Archivos que Docker ignora al copiar
├── requirements.txt            # Dependencias de Python
│
├── app/                        # Código fuente principal
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, health check, incluye router
│   ├── config.py               # Configuración con pydantic-settings
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py           # Endpoints: /upload, /job/{id}, /jobs/completed, /summary/calculate
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py         # Engine SQLAlchemy y session factory
│   │   └── models.py           # Modelos ORM: Job, Sale, SalesDailySummary
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic schemas para request/response
│   ├── services/
│   │   ├── __init__.py
│   │   ├── blob_service.py     # Upload/download de archivos en Azure Blob
│   │   ├── queue_service.py    # Enviar/recibir mensajes de Azure Queue
│   │   └── job_service.py      # CRUD de jobs en la BD
│   └── worker/
│       ├── __init__.py
│       ├── consumer.py         # Loop principal: escucha cola → procesa → actualiza job
│       └── processor.py        # Parsing CSV + bulk insert con COPY
│
├── tests/                      # 49 pruebas unitarias
│   ├── __init__.py
│   ├── conftest.py             # Fixtures compartidos (TestClient)
│   ├── test_api.py             # Tests de endpoints (10 tests)
│   ├── test_processor.py       # Tests de procesamiento y validacion CSV (31 tests)
│   └── test_services.py        # Tests de servicios (8 tests)
│
├── sql/
│   └── init.sql                # DDL: CREATE TABLE jobs, sales, sales_daily_summary
│
├── n8n/
│   └── workflow.json           # Workflow exportable de N8N
│
└── data/
    ├── sample.csv              # CSV de ejemplo con 10 filas
    └── generate_csv.py         # Script para generar CSVs grandes
```

---

## Solución de problemas

### "Docker no está corriendo"

```
error during connect: ... open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

**Solución:** Abre Docker Desktop y espera a que el icono de la ballena esté estable (sin animación de carga). Luego vuelve a ejecutar el comando.

### "El puerto 8000 ya está en uso"

```
Bind for 0.0.0.0:8000 failed: port is already allocated
```

**Solución:** Otro programa usa el puerto 8000. Opciones:
1. Cierra el otro programa
2. O cambia el puerto en `docker-compose.yml`: `"8001:8000"` (usa 8001 en vez de 8000)

### "El job queda en PENDING y nunca pasa a COMPLETED"

Revisa los logs del worker:
```bash
docker logs retotecnicologyca-worker-1
```

Si ves errores de conexión a Azurite o PostgreSQL, reinicia los servicios:
```bash
docker-compose down && docker-compose up --build -d
```

### "Los tests no corren"

Asegúrate de ejecutarlos dentro del contenedor Docker:
```bash
docker exec retotecnicologyca-api-1 python -m pytest tests/ -v
```

No correrán directamente en tu máquina porque necesitan las dependencias instaladas dentro del contenedor.

### Reiniciar todo desde cero

Si quieres empezar limpio (borra todos los datos):
```bash
docker-compose down -v
docker-compose up --build -d
```

El flag `-v` borra los volúmenes (datos de PostgreSQL, Azurite y N8N).

### Ver logs de cualquier servicio

```bash
# API
docker logs retotecnicologyca-api-1

# Worker
docker logs retotecnicologyca-worker-1

# PostgreSQL
docker logs retotecnicologyca-postgres-1

# Seguir logs en tiempo real (Ctrl+C para salir)
docker logs -f retotecnicologyca-worker-1
```
