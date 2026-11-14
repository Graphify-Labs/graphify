# Canon Doctrinal Jurídico Chileno — Open Legal Chile

Repositorio canónico de dogmática jurídica de la República de Chile estructurado en **Markdown de Alta Densidad (Token-Optimized)** para agentes de inteligencia artificial y profesionales del derecho.

---

## 🏛️ 1. Obras y Tratados Canónicos Digitalizados por Capítulos

El corpus abarca las obras más citadas por la **Corte Suprema**, el **Tribunal Constitucional**, la **Contraloría General de la República** y la **Dirección del Trabajo**:

| Área | Tratadista | Obra Canónica | Capítulos Digitalizados | Ubicación |
| :--- | :--- | :--- | :--- | :--- |
| **Civil (Obligaciones)** | René Ramos Pazos | *De las Obligaciones* | 4 Capítulos (Estructura, Efectos, Acciones auxiliares, Extinción y prelación) | [`civil/ramos_pazos_obligaciones/`](civil/ramos_pazos_obligaciones/) |
| **Civil (Responsabilidad)** | Enrique Barros Bourie | *Tratado de Responsabilidad Extracontractual* | 4 Capítulos (Modelos, Antijuridicidad y culpa, Presunciones Arts. 2320/2329, Daño e imputación) | [`civil/barros_bourie_responsabilidad/`](civil/barros_bourie_responsabilidad/) |
| **Civil (Bienes)** | Daniel Peñailillo Arévalo | *Los Bienes y Derechos Reales* | 4 Capítulos (Bienes, Dominio y tradición CBR, Posesión inscrita, Reivindicatoria y precario) | [`civil/penailillo_bienes/`](civil/penailillo_bienes/) |
| **Procesal** | Mario Mosquera y Cristián Maturana | *Los Recursos Procesales* | 3 Capítulos (Impugnación y reposición, Apelación, Casación forma/fondo y queja) | [`procesal/maturana_mosquera_recursos/`](procesal/maturana_mosquera_recursos/) |
| **Administrativo** | Jorge Bermúdez Soto | *Derecho Administrativo General* | 3 Capítulos (Bases y probidad, Acto Ley 19.880 e invalidez, Falta de servicio y sancionador) | [`administrativo/bermudez_derecho_administrativo/`](administrativo/bermudez_derecho_administrativo/) |
| **Laboral** | Sergio Gamonal Contreras | *Derecho del Trabajo y Tutela Laboral* | 3 Capítulos (Principios protectores, Contrato y despido Art. 161 CT, Tutela y Ley Karin) | [`laboral/gamonal_derecho_del_trabajo/`](laboral/gamonal_derecho_del_trabajo/) |
| **Penal** | Enrique Cury Urzúa | *Derecho Penal: Parte General* | 3 Capítulos (Legalidad y conducta, Antijuridicidad y justificación, Culpabilidad y autoría) | [`penal/cury_parte_general/`](penal/cury_parte_general/) |
| **Constitucional** | José Luis Cea Egaña | *Derecho Constitucional Chileno* | 3 Capítulos (Bases e institucionalidad, Derechos y orden económico, Recurso de protección y TC) | [`constitucional/cea_derecho_constitucional/`](constitucional/cea_derecho_constitucional/) |

---

## ⚖️ 2. Cumplimiento Estricto de Propiedad Intelectual (Ley N° 17.336)

Para conciliar la publicidad del código abierto en GitHub con el régimen de propiedad intelectual chileno e internacional:

1. **Derecho de Cita y Análisis Doctrinal (Art. 71B Ley N° 17.336):**  
   "Es lícita la inclusión en una obra de fragmentos breves de otras obras ajenas, con fines de crítica, ilustración, enseñanza o investigación, indicando su fuente y el nombre del autor."  
   Todas las fichas en `.md` atribuyen de forma rigurosa la autoría, el tratado y el año, sintetizando y extrayendo los conceptos dogmáticos sustanciales sin reproducir maquetas editoriales comerciales.
2. **Minería de Textos y Datos para Investigación Tecnológica e IA (Art. 71C Ley N° 17.336):**  
   Se autoriza el procesamiento automatizado y vectorización de contenidos para investigación sin perjuicio injustificado a la explotación normal de la obra.
3. **Aislamiento de Archivos Crudos (`doctrina_raw/`):**  
   Cualquier PDF escaneado completo de consulta personal o privada permanece confinado en `doctrina_raw/`, el cual se encuentra expresamente excluido de control de versiones en el archivo [`.gitignore`](../.gitignore) para no ser publicado en repositorios públicos.

---

## ⚡ 3. Estándar de Optimización de Tokens

Los capítulos siguen una arquitectura diseñada para consumir **menos del 12% de los tokens** que demandaría un escaneo tradicional:
* **Cero Ruido:** Sin encabezados de página repetitivos, números de fojas descontextualizados ni avisos legales editoriales.
* **Estructura Atómica:** Secciones claramente delimitadas mediante `## 🏛️ <Nombre de Institución>`.
* **Metadatos Vinculantes:**
  * `**Definición Canónica:**` Síntesis exacta del concepto dogmático.
  * `**Requisitos Copulativos:**` Listados numerados de procedencia jurídica.
  * `**Concordancias Legales:**` Enlaces oficiales normalizados `[BCN - Código ..., Art. X]`.
  * `**Criterio Jurisprudencial Rector:**` Citas de casaciones y unificaciones de doctrina de la Corte Suprema (`[CS - Rol N° ...]`) y del Tribunal Constitucional (`[STC - Rol N° ...]`).

---

## 🔍 4. Uso del Motor FTS5 y Herramientas MCP

El motor [`doctrina_connector.py`](../doctrina_connector.py) indexa automáticamente todos los capítulos en una base SQLite virtual FTS5 (`doctrina.db`):

* **Búsqueda desde CLI:**
  ```bash
  python doctrina_connector.py search "presuncion culpa 2329"
  python doctrina_connector.py institucion "Recurso de Protección"
  python doctrina_connector.py list
  ```
* **Herramientas MCP:**
  * `doctrina_search`: Búsqueda con relevancia BM25 y filtrado por área.
  * `doctrina_get_institucion`: Recuperación de ficha completa.
  * `doctrina_list_obras`: Listado de tratados y estadísticas de tokens.
