"""Detecta os test smells do projeto usando o motor de detecção do TEMPY,
sem a interface gráfica, e salva os resultados em um formato padronizado.

Uso (sempre a partir da pasta raiz do projeto):

    python extract_smells_tempy.py --etapa before          # antes da refatoração (salva)
    python extract_smells_tempy.py --etapa after           # depois da refatoração (salva)
    python extract_smells_tempy.py                         # conferência rápida (não salva nada)
    python extract_smells_tempy.py --arquivo tests/test_x.py   # conferência de um arquivo (não salva)
"""

# ======================= CONFIGURAÇÃO =======================
# Altere apenas esta linha, se necessário: caminho da pasta onde o TEMPY foi clonado.
TEMPY_DIR = "../TEMPY"
# ============================================================

import argparse
import contextlib
import csv
import functools
import html
import io
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime

SCRIPT_NAME = os.path.basename(__file__)
IGNORED_DIRS = {"venv", "env", "node_modules", "build", "dist", "site-packages", "__pycache__"}


def load_tempy(tempy_dir):
    """Importa o parser do TEMPY a partir da pasta clonada."""
    assets = os.path.join(os.path.abspath(tempy_dir), "assets")
    if not os.path.isfile(os.path.join(assets, "python_parser.py")):
        sys.exit(f"[erro] TEMPY não encontrado em: {os.path.abspath(tempy_dir)}\n"
                 f"       Ajuste TEMPY_DIR no início do script ou use --tempy <caminho>.")
    sys.path.insert(0, assets)
    import python_parser
    # O TEMPY abre os arquivos sem definir a codificação, o que quebra no Windows
    # com arquivos UTF-8 acentuados. Forçamos UTF-8 apenas dentro do parser.
    python_parser.open = functools.partial(open, encoding="utf-8", errors="ignore")
    return python_parser.PythonParser


def is_ignored_dir(name):
    return name.startswith(".") or name.startswith("metrics-") or name in IGNORED_DIRS


def is_test_file(path):
    """Mesmo critério do TEMPY: o arquivo importa unittest/pytest ou tem linha começando com assert."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.find("assert") == 0:
                return True
            if any(t in line for t in ("import unittest", "import pytest", "from unittest", "from pytest")):
                return True
    return False


def find_test_files(root):
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not is_ignored_dir(d))
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if name.endswith(".py") and name != SCRIPT_NAME and is_test_file(path):
                files.append(path)
    return files


def analyze(parser_cls, path):
    """Executa a detecção do TEMPY em um arquivo. Retorna (ocorrências, erro)."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):  # o TEMPY imprime muita coisa
            parser = parser_cls(path)
            occurrences = parser.start() if parser.ast_parser else parser.start2()
        return occurrences, None
    except Exception as e:  # arquivo que o TEMPY não conseguiu analisar
        return [], f"{type(e).__name__}: {e}"


def git_commit(path):
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True)
        return r.stdout.strip() or None
    except OSError:
        return None


def run(parser_cls, root, files):
    rows, errors, seen = [], [], set()
    for path in files:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        occurrences, error = analyze(parser_cls, path)
        if error:
            errors.append({"arquivo": rel, "erro": error})
        for occ in occurrences:
            lines = ";".join(str(n) for n in occ.lines)
            key = (rel, occ.test_smell_type, occ.method_name, lines)
            if key in seen:  # descarta ocorrências idênticas repetidas
                continue
            seen.add(key)
            rows.append({"arquivo": rel, "smell": occ.test_smell_type,
                         "metodo": occ.method_name or "(nível do módulo)", "linhas": lines})
    return rows, errors


def print_summary(rows, n_files, errors):
    print(f"\n{len(rows)} test smells encontrados em {n_files} arquivos de teste analisados.\n")
    for smell, n in Counter(r["smell"] for r in rows).most_common():
        print(f"  {n:5d}  {smell}")
    if errors:
        print(f"\n[aviso] {len(errors)} arquivo(s) não puderam ser analisados pelo TEMPY.")


def write_html(path, summary, rows):
    by_type = "".join(f"<tr><td>{html.escape(s)}</td><td>{n}</td></tr>"
                      for s, n in summary["por_tipo"].items())
    body = "".join(
        f"<tr><td>{i}</td><td>{html.escape(r['arquivo'])}</td><td>{html.escape(r['smell'])}</td>"
        f"<td>{html.escape(r['metodo'])}</td><td>{html.escape(r['linhas'].replace(';', ', '))}</td></tr>"
        for i, r in enumerate(rows, 1))
    page = f"""<!DOCTYPE html>
<html lang="pt-br"><head><meta charset="utf-8"><title>Test smells ({summary['etapa']})</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; margin-bottom: 2rem; }}
th, td {{ border: 1px solid #999; padding: 4px 8px; text-align: left; }}
th {{ background: #eee; }}
</style></head><body>
<h1>Test smells detectados pelo TEMPY ({summary['etapa']})</h1>
<p>Data: {summary['data']}<br>Commit do projeto: {summary['commit_projeto']}<br>
Arquivos de teste analisados: {summary['arquivos_analisados']}<br>
Total de test smells: <strong>{summary['total_smells']}</strong></p>
<h2>Por tipo</h2><table><tr><th>Test smell</th><th>Ocorrências</th></tr>{by_type}</table>
<h2>Ocorrências</h2>
<table><tr><th>#</th><th>Arquivo</th><th>Test smell</th><th>Método</th><th>Linhas</th></tr>{body}</table>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def main():
    p = argparse.ArgumentParser(description="Detecta test smells com o TEMPY.")
    p.add_argument("--etapa", choices=("before", "after"),
                   help="salva os resultados em metrics-<etapa>-tempy/. Sem esta opção, nada é salvo.")
    p.add_argument("--arquivo", help="analisa apenas este arquivo de teste (conferência; não salva)")
    p.add_argument("--tempy", default=TEMPY_DIR, help="pasta onde o TEMPY foi clonado")
    args = p.parse_args()

    if args.etapa and args.arquivo:
        p.error("--arquivo serve só para conferência e não pode ser usado com --etapa")

    root = os.getcwd()
    parser_cls = load_tempy(args.tempy)

    if args.arquivo:
        if not os.path.isfile(args.arquivo):
            sys.exit(f"[erro] arquivo não encontrado: {args.arquivo}")
        rows, errors = run(parser_cls, root, [args.arquivo])
        for r in rows:
            print(f"  {r['smell']:<30} {r['metodo']:<40} linhas {r['linhas'].replace(';', ', ')}")
        print_summary(rows, 1, errors)
        for e in errors:
            print(f"  {e['arquivo']}: {e['erro']}")
        return

    out_dir = f"metrics-{args.etapa}-tempy" if args.etapa else None
    if out_dir and os.path.exists(out_dir):
        sys.exit(f"[erro] a pasta {out_dir}/ já existe. Os resultados não serão sobrescritos.\n"
                 f"       Se precisar refazer a medição, fale com o monitor antes de apagar a pasta.")

    files = find_test_files(root)
    if not files:
        sys.exit("[erro] nenhum arquivo de teste encontrado. Execute o script na pasta raiz do projeto.")
    rows, errors = run(parser_cls, root, files)
    print_summary(rows, len(files), errors)

    if not out_dir:
        print("\n(modo conferência: nenhum arquivo foi salvo)")
        return

    os.makedirs(out_dir)
    summary = {
        "etapa": args.etapa,
        "data": datetime.now().isoformat(timespec="seconds"),
        "commit_projeto": git_commit(root),
        "commit_tempy": git_commit(os.path.abspath(args.tempy)),
        "arquivos_analisados": len(files),
        "arquivos_com_erro": len(errors),
        "total_smells": len(rows),
        "por_tipo": dict(Counter(r["smell"] for r in rows).most_common()),
        "por_arquivo": dict(Counter(r["arquivo"] for r in rows).most_common()),
        "erros": errors,
    }
    with open(os.path.join(out_dir, "smells.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["arquivo", "smell", "metodo", "linhas"])
        writer.writeheader()
        writer.writerows(rows)
    with open(os.path.join(out_dir, "resumo.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    write_html(os.path.join(out_dir, "relatorio.html"), summary, rows)
    print(f"\nResultados salvos em {out_dir}/ (smells.csv, resumo.json, relatorio.html)")


if __name__ == "__main__":
    main()