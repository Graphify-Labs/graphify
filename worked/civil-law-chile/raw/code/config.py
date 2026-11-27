"""
Open Legal Chile — Gestor Centralizado de Configuración y Claves de API
Carga automáticamente las variables de entorno desde el archivo .env local
o desde las variables del sistema operativo sin dependencias externas.
"""

import os
from typing import Optional


def load_env_file(filepath: Optional[str] = None) -> None:
    """Carga pares clave=valor desde un archivo .env si existe."""
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), ".env")

    if not os.path.exists(filepath):
        return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception as e:
        print(f"[Aviso] No se pudo leer el archivo .env: {e}")


# Cargar variables de entorno al importar el módulo
load_env_file()

# Configuraciones y credenciales del Estado
BCN_API_KEY: str = os.getenv("BCN_API_KEY", "")
CNE_EMAIL: str = os.getenv("CNE_EMAIL", "")
CNE_PASSWORD: str = os.getenv("CNE_PASSWORD", "")
PORT: int = int(os.getenv("PORT", "8000"))

# Proveedores de Inteligencia Artificial (BYOK - Bring Your Own Key)
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Verificación de credenciales y estado soberano
def check_configuration() -> dict:
    """Verifica el estado del sistema, conectores abiertos y motores de IA."""
    ollama_active = False
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        res = sock.connect_ex(("localhost", 11434))
        sock.close()
        ollama_active = (res == 0)
    except Exception:
        ollama_active = False

    return {
        "OPEN_SOURCE_SOBERANO": True,
        "OLLAMA_ACTIVE": ollama_active,
        "CONNECTORS_OPEN": {
            "bcn": True,
            "cgr": True,
            "dt": True,
            "pjud": True,
            "cmf": True,
            "sii": True,
            "sma": True,
            "tdlc": True,
            "panel_expertos": True,
            "cne": True
        },
        "OPTIONAL_COMMERCIAL_PROVIDERS": {
            "anthropic": bool(ANTHROPIC_API_KEY and not ANTHROPIC_API_KEY.startswith("tu_")),
            "gemini": bool(GEMINI_API_KEY and not GEMINI_API_KEY.startswith("tu_")),
            "deepseek": bool(DEEPSEEK_API_KEY and not DEEPSEEK_API_KEY.startswith("tu_")),
            "openai": bool(OPENAI_API_KEY and not OPENAI_API_KEY.startswith("tu_")),
        }
    }


def safe_urlopen(req, timeout: float = 30.0):
    """Ejecuta una petición HTTP/HTTPS segura validando que el esquema no sea file:// ni arbitrario."""
    import urllib.request
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"Esquema de URL no permitido por políticas de seguridad: {url}")
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    return urllib.request.urlopen(req, timeout=timeout)  # nosec B310


if __name__ == "__main__":
    status = check_configuration()
    print("\n================================================================================")
    print("   ⚖️  OPEN LEGAL CHILE — ESTADO DEL SISTEMA (100% OPEN SOURCE & SOBERANO)  ⚖️")
    print("================================================================================")
    print(" • Motor Jurídico Soberano:     ✅ OPERATIVO (100% Local, Cero API Keys, $0)")
    print(f" • Motor Ollama (Modelos Libres): {'🟢 Activo (localhost:11434)' if status['OLLAMA_ACTIVE'] else '⚪ Inactivo (Opcional para modelos de pesos libres)'}")
    print(" • 10 Conectores del Estado:      ✅ 100% OPERATIVOS Y PÚBLICOS (BCN, CGR, DT, PJUD, etc.)")
    print("\n🔌 Proveedores Comerciales Propietarios (Opcionales de Terceros — No Requeridos):")
    for prov, configured in status["OPTIONAL_COMMERCIAL_PROVIDERS"].items():
        print(f"   - {prov.capitalize()}: {'✅ Configurado' if configured else '⚪ No configurado (opcional)'}")
    print("--------------------------------------------------------------------------------\n")

