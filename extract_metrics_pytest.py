"""Executa os testes do projeto com o pytest e salva os relatórios de testes e de cobertura.

Uso (sempre a partir da pasta raiz do projeto, com o ambiente virtual ativado):

    python extract_metrics_pytest.py --etapa before    # antes da refatoração
    python extract_metrics_pytest.py --etapa after     # depois da refatoração
"""

# ======================= CONFIGURAÇÃO =======================
# Altere apenas estas duas linhas, se necessário.

# Pasta com o código-fonte do projeto (a cobertura é medida sobre ela).
# Exemplos: CODIGO_FONTE = "pytubefix"  ou  CODIGO_FONTE = "src/itsdangerous"
CODIGO_FONTE = "graphify"

# Pasta dos testes. Se ficar como None, o script procura automaticamente.
# Exemplos: TESTES = "tests"  ou  TESTES = "test"
TESTES = None
# ============================================================

import argparse
import os
import subprocess
import sys

CANDIDATOS_TESTES = ["tests", "test", "src/tests", "src/test"]
SUFIXO = {"before": "antes", "after": "depois"}


def main():
    p = argparse.ArgumentParser(description="Extrai métricas de testes com o pytest.")
    p.add_argument("--etapa", choices=("before", "after"), required=True,
                   help="before = antes da refatoração; after = depois da refatoração")
    args = p.parse_args()

    if not CODIGO_FONTE:
        sys.exit("[erro] defina CODIGO_FONTE no início do script com a pasta do código-fonte do projeto.")
    if not os.path.isdir(CODIGO_FONTE):
        sys.exit(f"[erro] a pasta de código-fonte '{CODIGO_FONTE}' não existe. "
                 f"Execute o script na pasta raiz do projeto e confira CODIGO_FONTE.")

    testes = TESTES or next((c for c in CANDIDATOS_TESTES if os.path.isdir(c)), None)
    if not testes or not os.path.isdir(testes):
        sys.exit(f"[erro] pasta de testes não encontrada (procurado em: {CANDIDATOS_TESTES}). "
                 f"Defina TESTES no início do script.")

    pasta = f"metrics-{args.etapa}-pytest"
    sufixo = SUFIXO[args.etapa]
    if os.path.exists(pasta):
        sys.exit(f"[erro] a pasta {pasta}/ já existe. Os resultados não serão sobrescritos.\n"
                 f"       Se precisar refazer a medição, fale com o monitor antes de apagar a pasta.")
    os.makedirs(pasta)

    def saida(nome):
        return os.path.join(pasta, nome.format(s=sufixo))

    print(f"Etapa         : {args.etapa}")
    print(f"Código-fonte  : {CODIGO_FONTE}")
    print(f"Testes        : {testes}")
    print(f"Relatórios em : {pasta}/\n")

    resultado = subprocess.run([
        sys.executable, "-m", "pytest", testes,
        "-v",
        "-p", "no:cacheprovider",                      # não cria a pasta .pytest_cache
        f"--junit-xml={saida('pytest_{s}.xml')}",
        f"--html={saida('pytest_{s}.html')}",
        "--self-contained-html",
        f"--cov={CODIGO_FONTE}",
        "--cov-branch",
        f"--cov-report=xml:{saida('coverage_{s}.xml')}",
        f"--cov-report=json:{saida('coverage_{s}.json')}",
        f"--cov-report=html:{saida('coverage_{s}_html')}",
        "--cov-report=term",
    ])

    # Códigos do pytest: 0 = todos passaram, 1 = algum teste falhou (resultado válido),
    # 2 = interrompido, 3 = erro interno, 4 = erro de uso, 5 = nenhum teste coletado.
    if resultado.returncode not in (0, 1):
        print(f"\n[aviso] o pytest terminou com código {resultado.returncode}: os testes não foram "
              f"executados corretamente (geralmente falta alguma dependência do projeto).\n"
              f"        Corrija o problema, apague a pasta {pasta}/ e execute o script novamente.")
        sys.exit(resultado.returncode)

    print(f"\nArquivos gerados em {pasta}/:")
    print(f"  pytest_{sufixo}.xml       resultados dos testes em XML")
    print(f"  pytest_{sufixo}.html      relatório visual dos testes")
    print(f"  coverage_{sufixo}.xml     cobertura de código em XML")
    print(f"  coverage_{sufixo}.json    cobertura de código em JSON")
    print(f"  coverage_{sufixo}_html/   relatório visual de cobertura")
    print("\nConcluído.")


if __name__ == "__main__":
    main()