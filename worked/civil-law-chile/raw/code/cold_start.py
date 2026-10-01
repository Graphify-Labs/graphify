"""
Open Legal Chile — Entrevista de Arranque (Cold-Start Interview)
Permite a cualquier abogado o estudio jurídico configurar su perfil de práctica,
tono de litigación y preferencias dogmáticas para que los modelos de IA
redacten con la identidad y el estilo propio del despacho.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

PROFILE_FILE = "practice_profile.json"

DEFAULT_QUESTIONS: List[Dict[str, Any]] = [
    {
        "id": "firm_name",
        "pregunta": "¿Cuál es el nombre de su estudio jurídico o su nombre como abogado/a?",
        "default": "Abogado Independiente"
    },
    {
        "id": "jurisdiction",
        "pregunta": "¿En qué jurisdicción y tribunales litiga principalmente? (Ej. Santiago - Civil y Laboral, Concepción, etc.)",
        "default": "Santiago — Tribunales Civiles, Laborales y Cortes de Apelaciones"
    },
    {
        "id": "tone",
        "pregunta": "¿Cuál es su tono preferido de redacción en escritos y demandas? (1: Formal tradicional, 2: Combativo y riguroso, 3: Conciliador)",
        "opciones": {
            "1": "Formal tradicional (estilo judicial sobrio con fórmulas sacramentales)",
            "2": "Combativo y riguroso (énfasis en tipicidad, causalidad y jurisprudencia dura)",
            "3": "Conciliador y propositivo (enfoque en resolución rápida de controversias)"
        },
        "default": "1"
    },
    {
        "id": "doctrina_preference",
        "pregunta": "En responsabilidad civil extracontractual, ¿qué criterio doctrinario prefiere citar? (1: Barros Bourie, 2: Alessandri Rodríguez, 3: Ambos)",
        "opciones": {
            "1": "Enrique Barros Bourie (Tratado contemporáneo y estándares de conducta)",
            "2": "Arturo Alessandri Rodríguez (Doctrina clásica)",
            "3": "Ambos en complementación armónica"
        },
        "default": "1"
    }
]

class ColdStartInterviewEngine:
    """Motor interactivo para calibrar el perfil de práctica del estudio."""

    @staticmethod
    def run_interactive(base_dir: str = ".") -> Dict[str, Any]:
        """
        Ejecuta la entrevista interactiva por terminal.
        """
        print("\n" + "="*70)
        print("🏛️ OPEN LEGAL CHILE — ENTREVISTA DE ARRANQUE (COLD-START INTERVIEW)")
        print("Personalice en 60 segundos el tono, jurisdicción y dogmática de sus agentes.")
        print("="*70 + "\n")

        respuestas = {}
        for q in DEFAULT_QUESTIONS:
            print(f"👉 {q['pregunta']}")
            if "opciones" in q:
                for k, v in q["opciones"].items():
                    print(f"   [{k}] {v}")
            val = input(f"Respuesta (Enter para '{q['default']}'): ").strip()
            if not val:
                val = q["default"]

            # Si es opción numérica, resolver
            if "opciones" in q and val in q["opciones"]:
                respuestas[q["id"]] = q["opciones"][val]
            else:
                respuestas[q["id"]] = val
            print()

        return ColdStartInterviewEngine.save_profile(respuestas, base_dir=base_dir)

    @staticmethod
    def save_profile(respuestas: Dict[str, Any], base_dir: str = ".") -> Dict[str, Any]:
        """
        Guarda el perfil de práctica en practice_profile.json y actualiza directrices.
        """
        out_path = os.path.join(base_dir, PROFILE_FILE)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(respuestas, f, indent=2, ensure_ascii=False)

        # Actualizar sección en CLAUDE.md si existe
        claude_md = os.path.join(base_dir, "CLAUDE.md")
        if os.path.exists(claude_md):
            try:
                with open(claude_md, "r", encoding="utf-8") as f:
                    content = f.read()

                profile_snippet = (
                    f"\n\n<!-- PRACTICE_PROFILE_START -->\n"
                    f"## 🏛️ Perfil de Práctica del Despacho ({respuestas.get('firm_name')})\n"
                    f"- **Jurisdicción:** {respuestas.get('jurisdiction')}\n"
                    f"- **Tono procesal:** {respuestas.get('tone')}\n"
                    f"- **Criterio doctrinal civil:** {respuestas.get('doctrina_preference')}\n"
                    f"<!-- PRACTICE_PROFILE_END -->\n"
                )

                if "<!-- PRACTICE_PROFILE_START -->" in content:
                    start = content.find("<!-- PRACTICE_PROFILE_START -->")
                    end = content.find("<!-- PRACTICE_PROFILE_END -->") + len("<!-- PRACTICE_PROFILE_END -->")
                    content = content[:start] + profile_snippet.strip() + content[end:]
                else:
                    content += profile_snippet

                with open(claude_md, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                sys.stderr.write(f"No se pudo actualizar CLAUDE.md: {e}\n")

        print("="*70)
        print("✅ PERFIL DE PRÁCTICA REGISTRADO EXITOSAMENTE")
        print(f"Archivo generado: {out_path}")
        print("Los agentes redactarán automáticamente con la identidad de su firma.")
        print("="*70 + "\n")
        return respuestas

    @staticmethod
    def load_profile(base_dir: str = ".") -> Optional[Dict[str, Any]]:
        out_path = os.path.join(base_dir, PROFILE_FILE)
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
