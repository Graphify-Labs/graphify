"""Extrai métricas de qualidade com o Radon (CC, MI, Halstead e Raw) do código-fonte
e do código de teste do projeto, e salva os resultados em JSON e CSV.

Uso (sempre a partir da pasta raiz do projeto, com o ambiente virtual ativado):

    python extract_metrics_radon.py --etapa before    # antes da refatoração
    python extract_metrics_radon.py --etapa after     # depois da refatoração
"""

# ======================= CONFIGURAÇÃO =======================
# Altere apenas estas duas linhas, se necessário.

# Pasta com o código-fonte do projeto.
# Exemplos: CODIGO_FONTE = "pytubefix"  ou  CODIGO_FONTE = "src/itsdangerous"
CODIGO_FONTE = "graphify"

# Pasta dos testes. Se ficar como None, o script procura automaticamente.
# Exemplos: TESTES = "tests"  ou  TESTES = "test"
TESTES = None
# ============================================================

import argparse
import csv
import json
import os
import subprocess
import sys

CANDIDATOS_TESTES = ["tests", "test", "src/tests", "src/test"]
SUFIXO = {"before": "antes", "after": "depois"}
HAL_FIELDS = ["h1", "h2", "N1", "N2", "vocabulary", "length", "calculated_length",
              "volume", "difficulty", "effort", "time", "bugs"]
RAW_FIELDS = ["loc", "lloc", "sloc", "comments", "multi", "blank", "single_comments"]


def normalizar(path):
    return path.replace("\\", "/").removeprefix("./")


def rodar_radon(metrica, caminhos):
    r = subprocess.run([sys.executable, "-m", "radon", metrica, *caminhos, "-j"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(f"[erro] falha ao executar 'radon {metrica}'. O Radon está instalado no ambiente "
                 f"virtual ativo?\n{r.stderr}")
    return json.loads(r.stdout)


def salvar_csv(pasta, nome, linhas, ordenar_por=None):
    if not linhas:
        print(f"  (sem dados para {nome})")
        return
    if ordenar_por:
        linhas = sorted(linhas, key=lambda x: (x[ordenar_por] == "", x[ordenar_por]))
    caminho = os.path.join(pasta, nome)
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=linhas[0].keys())
        writer.writeheader()
        writer.writerows(linhas)
    print(f"  {len(linhas):>5} linhas -> {caminho}")


def extrair_funcoes(blocos, arquivo, origem):
    resultado = []
    for bloco in blocos:
        if bloco["type"] != "class":
            resultado.append({
                "arquivo": arquivo, "origem": origem, "tipo": bloco["type"],
                "classe": bloco.get("classname") or "", "nome": bloco["name"],
                "rank_cc": bloco["rank"], "complexity": bloco["complexity"],
                "linha_ini": bloco["lineno"], "linha_fim": bloco["endline"],
            })
        if bloco.get("closures"):
            resultado += extrair_funcoes(bloco["closures"], arquivo, origem)
    return resultado


def main():
    p = argparse.ArgumentParser(description="Extrai métricas de qualidade com o Radon.")
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

    fonte_n, testes_n = normalizar(CODIGO_FONTE).rstrip("/"), normalizar(testes).rstrip("/")

    def origem(arquivo):
        # Se a pasta de testes estiver dentro do código-fonte, ela tem prioridade.
        return "teste" if arquivo == testes_n or arquivo.startswith(testes_n + "/") else "fonte"

    caminhos = [CODIGO_FONTE] if testes_n.startswith(fonte_n + "/") else [CODIGO_FONTE, testes]

    pasta = f"metrics-{args.etapa}-radon"
    s = SUFIXO[args.etapa]
    if os.path.exists(pasta):
        sys.exit(f"[erro] a pasta {pasta}/ já existe. Os resultados não serão sobrescritos.\n"
                 f"       Se precisar refazer a medição, fale com o monitor antes de apagar a pasta.")

    print(f"Etapa: {args.etapa} | código-fonte: {CODIGO_FONTE} | testes: {testes}")
    dados = {}
    for metrica in ("cc", "mi", "hal", "raw"):
        print(f"Rodando radon {metrica}...")
        bruto = rodar_radon(metrica, caminhos)
        dados[metrica] = {normalizar(k): v for k, v in bruto.items()}

    os.makedirs(pasta)
    for metrica, conteudo in dados.items():
        with open(os.path.join(pasta, f"{metrica}_{s}.json"), "w", encoding="utf-8") as f:
            json.dump(conteudo, f, indent=2, ensure_ascii=False)

    # Arquivos que o Radon não conseguiu analisar (ex.: erro de sintaxe) ficam registrados à parte.
    erros = {}
    for metrica, conteudo in dados.items():
        for arquivo, d in conteudo.items():
            if isinstance(d, dict) and "error" in d:
                erros.setdefault(arquivo, {})[metrica] = d["error"]

    def validos(metrica):
        return [(a, d) for a, d in dados[metrica].items() if a not in erros]

    rows_mi = [{"arquivo": a, "origem": origem(a), "mi": round(d["mi"], 4), "rank_mi": d["rank"]}
               for a, d in validos("mi")]

    rows_cc, rows_cc_arquivo, vistas = [], [], set()
    for arquivo, blocos in validos("cc"):
        funcoes = []
        for f in extrair_funcoes(blocos, arquivo, origem(arquivo)):
            chave = (f["arquivo"], f["classe"], f["nome"], f["linha_ini"])
            if chave not in vistas:
                vistas.add(chave)
                funcoes.append(f)
        rows_cc += funcoes
        linha = {"arquivo": arquivo, "origem": origem(arquivo), "funcoes": len(funcoes),
                 "cc_media": "", "cc_max": "", "cc_soma": "", "pior_rank": "",
                 "pior_classe": "", "pior_funcao": "", "pior_linha_ini": ""}
        if funcoes:
            cs = [f["complexity"] for f in funcoes]
            pior = max(funcoes, key=lambda x: x["complexity"])
            linha.update(cc_media=round(sum(cs) / len(cs), 2), cc_max=max(cs), cc_soma=sum(cs),
                         pior_rank=pior["rank_cc"], pior_classe=pior["classe"],
                         pior_funcao=pior["nome"], pior_linha_ini=pior["linha_ini"])
        rows_cc_arquivo.append(linha)

    rows_hal_arquivo, rows_hal_funcao = [], []
    for arquivo, d in validos("hal"):
        base = {"arquivo": arquivo, "origem": origem(arquivo)}
        rows_hal_arquivo.append({**base, "escopo": "arquivo", "nome": "",
                                 **{k: round(d["total"].get(k) or 0, 4) for k in HAL_FIELDS}})
        for nome, fh in d.get("functions", {}).items():
            rows_hal_funcao.append({**base, "escopo": "funcao", "nome": nome,
                                    **{k: round(fh.get(k) or 0, 4) for k in HAL_FIELDS}})

    rows_raw = []
    totais = {o: {k: 0 for k in RAW_FIELDS} for o in ("fonte", "teste")}
    for arquivo, d in validos("raw"):
        o = origem(arquivo)
        linha = {"arquivo": arquivo, "origem": o, **{k: d.get(k) or 0 for k in RAW_FIELDS}}
        rows_raw.append(linha)
        for k in RAW_FIELDS:
            totais[o][k] += linha[k]
    rows_raw.sort(key=lambda x: x["sloc"])
    rows_raw.append({"arquivo": "TOTAL", "origem": "fonte", **totais["fonte"]})
    rows_raw.append({"arquivo": "TOTAL", "origem": "teste", **totais["teste"]})

    print("Salvando CSVs:")
    salvar_csv(pasta, f"mi_por_arquivo_{s}.csv", rows_mi, ordenar_por="mi")
    salvar_csv(pasta, f"cc_por_funcao_{s}.csv", rows_cc, ordenar_por="complexity")
    salvar_csv(pasta, f"cc_por_arquivo_{s}.csv", rows_cc_arquivo, ordenar_por="cc_media")
    salvar_csv(pasta, f"hal_por_arquivo_{s}.csv", rows_hal_arquivo, ordenar_por="effort")
    salvar_csv(pasta, f"hal_por_funcao_{s}.csv", rows_hal_funcao)
    salvar_csv(pasta, f"raw_por_arquivo_e_total_{s}.csv", rows_raw)
    if erros:
        salvar_csv(pasta, f"arquivos_com_erro_{s}.csv",
                   [{"arquivo": a, "origem": origem(a), "erro": "; ".join(sorted(set(e.values())))}
                    for a, e in sorted(erros.items())])
        print(f"\n[aviso] {len(erros)} arquivo(s) não puderam ser analisados pelo Radon "
              f"(veja arquivos_com_erro_{s}.csv).")
    print("\nConcluído.")


if __name__ == "__main__":
    main()