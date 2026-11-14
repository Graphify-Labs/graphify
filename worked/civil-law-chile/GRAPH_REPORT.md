# Graph Report - worked-civil-law-chile  (2026-09-18)

## Corpus Check
- 8 files · ~3,010 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 72 nodes · 91 edges · 9 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- stats_tracker.py
- LegalGraphBuilder
- cold_start.py
- ColdStartInterviewEngine
- config.py
- Canon Doctrinal Jurídico Chileno — Open Legal Chile
- Guía de Audiencia de Conciliación Laboral
- Guía de Buenas Prácticas Judiciales en Temas Éticos
- Guía para la Audiencia de Juicio Oral Laboral

## God Nodes (most connected - your core abstractions)
1. `LegalGraphBuilder` - 8 edges
2. `safe_urlopen()` - 6 edges
3. `ColdStartInterviewEngine` - 5 edges
4. `get_pypi_download_stats()` - 5 edges
5. `get_github_community_stats()` - 5 edges
6. `get_suite_adoption_metrics()` - 5 edges
7. `Canon Doctrinal Jurídico Chileno — Open Legal Chile` - 5 edges
8. `build_quick_graph()` - 4 edges
9. `Guía de Audiencia de Conciliación Laboral` - 4 edges
10. `Guía de Buenas Prácticas Judiciales en Temas Éticos` - 4 edges

## Surprising Connections (you probably didn't know these)
- `get_github_community_stats()` --calls--> `safe_urlopen()`  [EXTRACTED]
  raw/code/stats_tracker.py → raw/code/config.py
- `get_pypi_download_stats()` --calls--> `safe_urlopen()`  [EXTRACTED]
  raw/code/stats_tracker.py → raw/code/config.py
- `send_anonymous_telemetry_ping()` --calls--> `safe_urlopen()`  [EXTRACTED]
  raw/code/stats_tracker.py → raw/code/config.py

## Import Cycles
- None detected.

## Communities (9 total, 0 thin omitted)

### Community 0 - "stats_tracker.py"
Cohesion: 0.20
Nodes (14): Ejecuta una petición HTTP/HTTPS segura validando que el esquema no sea file://…, safe_urlopen(), get_github_community_stats(), get_pypi_download_stats(), get_suite_adoption_metrics(), Any, Open Legal Chile — Rastreador de Estadísticas de Adopción y Telemetría Ética…, Envía un ping anónimo no invasivo para cuantificar instalaciones activas.… (+6 more)

### Community 1 - "LegalGraphBuilder"
Cohesion: 0.27
Nodes (6): build_quick_graph(), LegalGraphBuilder, Any, Construye un grafo relacional de forma tolerante a nombres de campos y tipos., Sanitiza identificadores para compatibilidad estricta con la sintaxis de…, Genera diagrama Mermaid compatible con Markdown, GitHub y Antigravity.

### Community 2 - "cold_start.py"
Cohesion: 0.22
Nodes (7): json, pathlib, Open Legal Chile — Entrevista de Arranque (Cold-Start Interview) Permite a…, Open Legal Chile — Generador de Grafos de Vínculos y Redes Corporativas…, re, sys, typing

### Community 3 - "ColdStartInterviewEngine"
Cohesion: 0.36
Nodes (5): ColdStartInterviewEngine, Any, Motor interactivo para calibrar el perfil de práctica del estudio., Ejecuta la entrevista interactiva por terminal., Guarda el perfil de práctica en practice_profile.json y actualiza directrices.

### Community 4 - "config.py"
Cohesion: 0.29
Nodes (6): os, check_configuration(), load_env_file(), Open Legal Chile — Gestor Centralizado de Configuración y Claves de API Carga…, Carga pares clave=valor desde un archivo .env si existe., Verifica el estado del sistema, conectores abiertos y motores de IA.

### Community 5 - "Canon Doctrinal Jurídico Chileno — Open Legal Chile"
Cohesion: 0.33
Nodes (5): 🏛️ 1. Obras y Tratados Canónicos Digitalizados por Capítulos, ⚖️ 2. Cumplimiento Estricto de Propiedad Intelectual (Ley N° 17.336), ⚡ 3. Estándar de Optimización de Tokens, 🔍 4. Uso del Motor FTS5 y Herramientas MCP, Canon Doctrinal Jurídico Chileno — Open Legal Chile

### Community 6 - "Guía de Audiencia de Conciliación Laboral"
Cohesion: 0.40
Nodes (4): Consulta y Descarga del Documento Original, Guía de Audiencia de Conciliación Laboral, Materia: Laboral | Fecha: 2025-02-15, Resumen Ejecutivo de Práctica Judicial

### Community 7 - "Guía de Buenas Prácticas Judiciales en Temas Éticos"
Cohesion: 0.40
Nodes (4): Consulta y Descarga del Documento Original, Guía de Buenas Prácticas Judiciales en Temas Éticos, Materia: Ética Judicial | Fecha: 2026-07-10, Resumen Ejecutivo de Práctica Judicial

### Community 8 - "Guía para la Audiencia de Juicio Oral Laboral"
Cohesion: 0.40
Nodes (4): Consulta y Descarga del Documento Original, Guía para la Audiencia de Juicio Oral Laboral, Materia: Laboral | Fecha: 2025-02-15, Resumen Ejecutivo de Práctica Judicial

## Knowledge Gaps
- **13 isolated node(s):** `🏛️ 1. Obras y Tratados Canónicos Digitalizados por Capítulos`, `⚖️ 2. Cumplimiento Estricto de Propiedad Intelectual (Ley N° 17.336)`, `⚡ 3. Estándar de Optimización de Tokens`, `🔍 4. Uso del Motor FTS5 y Herramientas MCP`, `Materia: Laboral | Fecha: 2025-02-15` (+8 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 39 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `LegalGraphBuilder` connect `LegalGraphBuilder` to `cold_start.py`?**
  _High betweenness centrality (0.137) - this node is a cross-community bridge._
- **Why does `ColdStartInterviewEngine` connect `ColdStartInterviewEngine` to `cold_start.py`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `build_quick_graph()` connect `LegalGraphBuilder` to `cold_start.py`?**
  _High betweenness centrality (0.036) - this node is a cross-community bridge._
- **What connects `🏛️ 1. Obras y Tratados Canónicos Digitalizados por Capítulos`, `⚖️ 2. Cumplimiento Estricto de Propiedad Intelectual (Ley N° 17.336)`, `⚡ 3. Estándar de Optimización de Tokens` to the rest of the system?**
  _13 weakly-connected nodes found - possible documentation gaps or missing edges._