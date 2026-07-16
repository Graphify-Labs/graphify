from __future__ import annotations

import subprocess

from PyInstaller import __main__ as pyi_main


# Test out the package by importing it, then running functions from it.
def test_pyi_hooksample(tmp_path):
    app_name = "userapp"
    workpath = tmp_path / "build"
    distpath = tmp_path / "dist"
    app = tmp_path / (app_name + ".py")
    app.write_text(
        "\n".join(
            [
                "import rapidfuzz",
                "from rapidfuzz.distance import metrics_py",
                "from rapidfuzz.distance import metrics_cpp",
                "rapidfuzz.distance.Levenshtein.distance('test', 'teste')",
                "metrics_py.levenshtein_distance('test', 'teste')",
                "metrics_cpp.levenshtein_distance('test', 'teste')",
            ]
        )
    )
    args = [
        # Place all generated files in ``tmp_path``.
        "--workpath",
        str(workpath),
        "--distpath",
        str(distpath),
        "--specpath",
        str(tmp_path),
        str(app),
    ]
    pyi_main.run(args)
    subprocess.run([str(distpath / app_name / app_name)], check=True)
