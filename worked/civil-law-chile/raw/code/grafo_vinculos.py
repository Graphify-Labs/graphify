"""
Open Legal Chile — Generador de Grafos de Vínculos y Redes Corporativas
Construye redes relacionales entre personas de interés, autoridades, sociedades,
bienes raíces, resoluciones sancionatorias y causas judiciales.
Exporta en código Mermaid (renderizable en Markdown/Chats) y JSON relacional.
"""

import re
from typing import List, Dict, Any, Optional, Union


class LegalGraphBuilder:
    # Paleta de colores institucionales para categorías forenses
    CATEGORY_STYLES = {
        "sociedad": "fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1",
        "empresa": "fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1",
        "persona": "fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20",
        "autoridad": "fill:#fff8e1,stroke:#f57f17,stroke-width:2px,color:#e65100",
        "organismo": "fill:#ede7f6,stroke:#512da8,stroke-width:2px,color:#311b92",
        "causa": "fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c",
        "sancion": "fill:#fbe9e7,stroke:#d84315,stroke-width:2px,color:#bf360c",
        "inmueble": "fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c"
    }

    def __init__(self):
        self.nodes = {}
        self.edges = []

    def _sanitize_id(self, raw_id: Any) -> str:
        """Sanitiza identificadores para compatibilidad estricta con la sintaxis de Mermaid."""
        if raw_id is None:
            raw_id = "node"
        s = str(raw_id).strip()
        # Reemplazar caracteres no alfanuméricos por guión bajo
        clean = re.sub(r'[^a-zA-Z0-9_]', '_', s).strip('_')
        if not clean:
            clean = "nodo"
        # Mermaid falla si el identificador comienza con dígito
        if clean[0].isdigit():
            clean = f"id_{clean}"
        return clean

    def add_node(self, node_id: Any, label: str, category: str = "sociedad", metadata: Optional[Dict[str, Any]] = None) -> str:
        clean_id = self._sanitize_id(node_id)
        lbl = str(label if label is not None else clean_id).strip()
        cat = str(category or "sociedad").lower().strip()
        self.nodes[clean_id] = {
            "id": clean_id,
            "label": lbl,
            "category": cat,
            "metadata": metadata or {}
        }
        return clean_id

    def add_edge(self, source_id: Any, target_id: Any, relation: str = ""):
        src = self._sanitize_id(source_id)
        tgt = self._sanitize_id(target_id)
        rel = str(relation or "").strip()
        self.edges.append({
            "source": src,
            "target": tgt,
            "relation": rel
        })

    def to_mermaid(self, title: str = "Red de Vínculos") -> str:
        """Genera diagrama Mermaid compatible con Markdown, GitHub y Antigravity."""
        lines = [
            "```mermaid",
            "---",
            f"title: {title}",
            "---",
            "graph TD",
            "    %% Estilos por Categoría",
            "    classDef sociedad fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1;",
            "    classDef persona fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20;",
            "    classDef autoridad fill:#fff8e1,stroke:#f57f17,stroke-width:2px,color:#e65100;",
            "    classDef organismo fill:#ede7f6,stroke:#512da8,stroke-width:2px,color:#311b92;",
            "    classDef causa fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c;",
            "    classDef sancion fill:#fbe9e7,stroke:#d84315,stroke-width:2px,color:#bf360c;",
            "    classDef inmueble fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;",
            ""
        ]

        # Declaración de nodos
        for nid, data in self.nodes.items():
            lbl = data["label"].replace('"', "'").replace("\n", "<br/>")
            lines.append(f'    {nid}["{lbl}"]')

        # Aplicar clases a los nodos
        for nid, data in self.nodes.items():
            cat = data.get("category", "sociedad")
            if cat in self.CATEGORY_STYLES:
                lines.append(f"    class {nid} {cat};")

        lines.append("")

        # Declaración de aristas
        for e in self.edges:
            rel = e["relation"].replace('"', "'").replace("\n", " ")
            if rel:
                lines.append(f'    {e["source"]} -->|"{rel}"| {e["target"]}')
            else:
                lines.append(f'    {e["source"]} --> {e["target"]}')

        lines.append("```")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
            "mermaid": self.to_mermaid()
        }


def build_quick_graph(
    nodes_list: Optional[List[Dict[str, Any]]] = None,
    edges_list: Optional[List[Dict[str, Any]]] = None,
    title: str = "Red de Vínculos"
) -> Dict[str, Any]:
    """Construye un grafo relacional de forma tolerante a nombres de campos y tipos."""
    builder = LegalGraphBuilder()

    if isinstance(nodes_list, list):
        for n in nodes_list:
            if not isinstance(n, dict):
                continue
            nid = n.get("id") or n.get("rut") or n.get("nombre") or n.get("label")
            if not nid:
                continue
            label = n.get("label") or n.get("nombre") or str(nid)
            cat = n.get("category") or n.get("tipo") or "sociedad"
            builder.add_node(nid, label, cat, metadata=n.get("metadata"))

    if isinstance(edges_list, list):
        for e in edges_list:
            if not isinstance(e, dict):
                continue
            src = e.get("source") or e.get("origen") or e.get("desde")
            tgt = e.get("target") or e.get("destino") or e.get("hacia")
            if not src or not tgt:
                continue
            rel = e.get("relation") or e.get("relacion") or e.get("vinculo") or ""
            builder.add_edge(src, tgt, rel)

    return builder.to_dict()


if __name__ == "__main__":
    builder = LegalGraphBuilder()
    builder.add_node("ula", "Universidad de Los Lagos", "organismo")
    builder.add_node("kimun", "Corporación Kimün", "sociedad")
    builder.add_node(12345, "Representante Legal", "persona")
    builder.add_edge("ula", "kimun", "Traspaso de Acciones por $130M")
    builder.add_edge(12345, "kimun", "Administrador")
    print(builder.to_mermaid())
