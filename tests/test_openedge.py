"""OpenEdge ABL (.p/.w/.i/.cls) + DF schema (.df) extractors.

The tree-sitter-abl / tree-sitter-df parsers are optional (not on PyPI), so each
test skips cleanly when its parser is not installed.
"""
import tempfile
import textwrap
import unittest
from pathlib import Path

from graphify.extract import extract_abl, extract_df, _make_id

try:
    import tree_sitter_abl  # noqa: F401
    _HAS_ABL = True
except ImportError:
    _HAS_ABL = False

try:
    import tree_sitter_df  # noqa: F401
    _HAS_DF = True
except ImportError:
    _HAS_DF = False


class TestOpenEdge(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write(self, name: str, content: str) -> Path:
        p = self.temp_path / name
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    @unittest.skipUnless(_HAS_DF, "tree-sitter-df not installed")
    def test_df_extracts_tables_and_sequences(self):
        p = self._write("schema.df", '''
            ADD SEQUENCE "seq_cli"
              INITIAL 0

            ADD TABLE "client"
              AREA "Tables"
              DUMP-NAME "client"

            ADD FIELD "cod_cli" OF "client" AS integer
              ORDER 10

            ADD FIELD "nom_cli" OF "client" AS character
              ORDER 20

            ADD INDEX "pk" ON "client"
              UNIQUE PRIMARY
              INDEX-FIELD "cod_cli" ASCENDING
        ''')
        result = extract_df(p)
        self.assertIsNone(result.get("error"))
        labels = {n["label"] for n in result["nodes"]}
        self.assertIn("client", labels)
        self.assertIn("seq_cli", labels)

        table = next(n for n in result["nodes"] if n["label"] == "client")
        # Global, file-independent id so ABL `uses` edges resolve onto it.
        self.assertEqual(table["id"], _make_id("client"))
        # Fields/indexes are counts on the table, not separate nodes.
        self.assertEqual(table["field_count"], 2)
        self.assertEqual(table["index_count"], 1)
        # type=module exempts it from graphify's path-based id disambiguation, so
        # duplicate `.df` dumps of one database collapse to a single table node.
        self.assertEqual(table.get("type"), "module")

    @unittest.skipUnless(_HAS_ABL, "tree-sitter-abl not installed")
    def test_abl_emits_uses_edges_to_tables(self):
        p = self._write("traitement.p", '''
            DEFINE TEMP-TABLE tt-tmp NO-UNDO FIELD x AS INTEGER.

            PROCEDURE maj:
              FIND FIRST client NO-LOCK NO-ERROR.
              FOR EACH commande WHERE commande.no_cde > 0:
                DISPLAY commande.no_cde.
              END.
              CREATE tt-tmp.
            END PROCEDURE.
        ''')
        result = extract_abl(p)
        self.assertIsNone(result.get("error"))
        uses = {
            (e["source"], e["target"])
            for e in result["edges"]
            if e.get("relation") == "uses"
        }
        # `client` and `commande` are referenced; targets carry the global table id.
        targets = {t for _, t in uses}
        self.assertIn(_make_id("client"), targets)
        self.assertIn(_make_id("commande"), targets)
        # The temp-table defined in-file is NOT treated as a DB table.
        self.assertNotIn(_make_id("tt-tmp"), targets)

    @unittest.skipUnless(_HAS_ABL, "tree-sitter-abl not installed")
    def test_abl_uses_target_matches_df_table_id(self):
        """The ABL `uses` edge target id equals the DF table node id — the contract
        that lets code link onto schema at corpus-assembly time."""
        pp = self._write("prog.p", '''
            PROCEDURE r:
              FIND FIRST facture NO-LOCK NO-ERROR.
            END PROCEDURE.
        ''')
        abl = extract_abl(pp)
        use_targets = {e["target"] for e in abl["edges"] if e.get("relation") == "uses"}
        self.assertIn(_make_id("facture"), use_targets)


if __name__ == "__main__":
    unittest.main()
