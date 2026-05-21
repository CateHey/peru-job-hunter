# Peru Job Hunter

Herramienta automatizada para buscar trabajos de TI, Robotica y Electronica en Peru.
Scrapea multiples portales y paginas de empresas, usa Claude API para analizar relevancia,
y genera un dashboard HTML interactivo.

## Dos Clientes / Dos Programas

| Programa | Perfil | Que busca |
|----------|--------|-----------|
| `mechatronics_hunter` | Estudiante 9no ciclo Ing. Mecatronica | Practicas en AI, ML, BI, Robotica, Electronica |
| `infra_hunter` | Junior IT Infrastructure | Sysadmin, Redes, Cloud, DevOps, Soporte |

Ambos programas comparten la misma libreria base (`shared/`) y la misma API key de Claude.

---

## Requisitos Previos

- **Python 3.10+** (recomendado 3.11 o 3.12)
- **Google Chrome** instalado (necesario para los scrapers que usan Selenium: Bumeran, Gobierno, algunas career pages)
- **Una cuenta en Anthropic** para obtener tu API key de Claude (https://console.anthropic.com/)

---

## Instalacion Paso a Paso

### 1. Abrir terminal en la carpeta del proyecto

```powershell
cd C:\Users\lucer\Downloads\peru_job_hunter
```

### 2. Crear entorno virtual (venv)

```powershell
python -m venv .venv
```

### 3. Activar el entorno virtual

```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1

# Si te da error de politica de ejecucion, ejecuta primero:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Cuando el venv esta activo, veras `(.venv)` al inicio de tu terminal.

### 4. Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 5. Configurar la API Key de Claude

Crea un archivo `.env` en la raiz del proyecto:

```powershell
copy .env.example .env
```

Luego abre `.env` con cualquier editor y reemplaza con tu key real:

```
ANTHROPIC_API_KEY=sk-ant-api03-TU-KEY-AQUI
```

**Donde obtener la key:**
1. Ve a https://console.anthropic.com/
2. Inicia sesion o crea una cuenta
3. Ve a "API Keys" en el menu lateral
4. Click en "Create Key"
5. Copia la key y pegala en tu `.env`

**IMPORTANTE:** Una sola API key funciona para ambos programas (mechatronics_hunter e infra_hunter).
No necesitas keys separadas. La key es de tu cuenta de Anthropic, no del cliente.

**Costo estimado:** Cada ejecucion analiza ~100-200 trabajos con Claude Haiku 4.5.
Costo aproximado: $0.05 - $0.15 USD por ejecucion.

---

## Uso

### Busqueda para el estudiante de Mecatronica

```powershell
# Busqueda completa (scraping + analisis Claude)
python -m mechatronics_hunter.run

# Solo scraping, sin gastar API (para probar que los scrapers funcionan)
python -m mechatronics_hunter.run --no-claude

# Con Claude pero sin batch API (mas lento, resultados inmediatos)
python -m mechatronics_hunter.run --no-batch
```

### Busqueda para el Junior de Infraestructura TI

```powershell
# Busqueda completa
python -m infra_hunter.run

# Solo scraping
python -m infra_hunter.run --no-claude

# Sin batch
python -m infra_hunter.run --no-batch
```

### Que hace cada flag

| Flag | Efecto |
|------|--------|
| (sin flags) | Busqueda completa: scraping + analisis con Claude Batch API |
| `--no-claude` | Solo scraping. No usa API. Genera dashboard sin scores de relevancia |
| `--no-batch` | Usa Claude pero con llamadas una por una (mas lento, no necesita esperar batch) |

---

## Resultado

Cada ejecucion genera un archivo HTML en:

- `mechatronics_hunter/output/dashboard_YYYY-MM-DD_HHMM.html`
- `infra_hunter/output/dashboard_YYYY-MM-DD_HHMM.html`

El dashboard se abre automaticamente en tu navegador. Incluye:

- Trabajos ordenados por relevancia (score 0-100)
- Filtros por fuente, recomendacion y texto
- Color: verde (APPLY_NOW), amarillo (CONSIDER), rojo (SKIP)
- Links directos para postular a cada oferta
- Modo claro/oscuro

---

## Fuentes de Datos

| Fuente | Habilitada | Metodo | Notas |
|--------|-----------|--------|-------|
| CompuTrabajo | Si | HTTP + BS4 | Principal. 133K+ ofertas Peru |
| LinkedIn | Si | Guest API | Sin login requerido |
| Indeed | Si | python-jobspy | Wrapper automatico |
| Bumeran | No (opcional) | Selenium | Necesita Chrome. Habilitar en config.yaml |
| Gobierno Peru | Si | Selenium | Best-effort, puede fallar |
| Career Pages | Si | HTTP/Selenium | Configurable por empresa |

### Empresas configuradas

**Mecatronica:** Siemens, ABB, Schneider Electric, Rockwell, IBM, Microsoft, J&J Peru

**Infra TI:** Claro, Movistar/Telefonica, Entel, IBM, HP, Cisco, AWS, BBVA, BCP

---

## Personalizar Busquedas

Edita los archivos de configuracion YAML:

- `mechatronics_hunter/config.yaml` - terminos de busqueda, empresas, skills del perfil
- `infra_hunter/config.yaml` - idem para infraestructura

Puedes agregar/quitar terminos de busqueda, habilitar/deshabilitar fuentes,
y modificar las empresas en cuyas career pages buscar.

Para agregar una nueva empresa, crea un YAML en `scrapers/company_configs/` siguiendo
el formato de los existentes (ver `siemens.yaml` como ejemplo).

---

## Estructura del Proyecto

```
peru_job_hunter/
├── .env                        # Tu API key (NO subir a git)
├── .env.example                # Plantilla del .env
├── .gitignore
├── requirements.txt
├── README.md
│
├── shared/                     # Libreria compartida
│   ├── models.py               # Modelos de datos (Job, AnalysisResult, etc.)
│   ├── config_loader.py        # Carga configs YAML
│   ├── scraper_base.py         # Clase base para scrapers
│   ├── rate_limiter.py         # Rate limiting + robots.txt
│   ├── deduplicator.py         # Elimina trabajos duplicados entre fuentes
│   ├── claude_analyzer.py      # Analisis con Claude API (batch + secuencial)
│   ├── dashboard_generator.py  # Genera el HTML
│   ├── utils.py                # Utilidades (logging, parseo fechas, etc.)
│   └── templates/
│       └── dashboard.html      # Template del dashboard
│
├── scrapers/                   # Un scraper por fuente
│   ├── computrabajo.py
│   ├── linkedin_guest.py
│   ├── indeed_jobspy.py
│   ├── bumeran.py
│   ├── gobierno_peru.py
│   ├── company_careers.py
│   └── company_configs/        # Config YAML por empresa
│       ├── siemens.yaml
│       ├── ibm.yaml
│       └── ... (15 empresas)
│
├── mechatronics_hunter/        # Programa Cliente 1
│   ├── config.yaml
│   ├── run.py
│   └── output/                 # Dashboards generados
│
└── infra_hunter/               # Programa Cliente 2
    ├── config.yaml
    ├── run.py
    └── output/                 # Dashboards generados
```

---

## Troubleshooting

**"No module named 'shared'"**
- Asegurate de ejecutar desde la raiz del proyecto: `python -m mechatronics_hunter.run`
- NO hagas `cd mechatronics_hunter && python run.py`

**"selenium no instalado" o Chrome no encontrado**
- Instala Chrome desde https://www.google.com/chrome/
- `pip install selenium webdriver-manager`

**"ANTHROPIC_API_KEY not set"**
- Verifica que el archivo `.env` existe y tiene tu key
- Verifica que el venv esta activo (debe decir `(.venv)` en el terminal)

**Pocos resultados o ningun resultado**
- Algunos portales bloquean scraping agresivo. Espera unos minutos y reintenta
- Prueba con `--no-claude` primero para verificar que los scrapers funcionan
- Revisa los terminos de busqueda en `config.yaml`

**Error de rate limit de Claude**
- El programa espera automaticamente 30s y reintenta
- Si persiste, usa `--no-batch` para llamadas mas lentas pero estables
