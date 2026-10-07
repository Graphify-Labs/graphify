"""PHP cross-file resolution.

The config-driven PHP *extractor* (``extract_php`` → ``_extract_generic``) still
lives in ``graphify/extract.py``; per ``extractors/MIGRATION.md`` the
config-driven languages cannot be ported one-by-one until the shared
``_extract_generic`` core moves as its own coordinated batch. This module is the
PHP home for the parts that *are* cleanly separable — today, the name-resolution
side of the member-call pass: matching a written class name against a definition
node, and the ``use``-import-aware receiver typing built on top of it.
"""
from __future__ import annotations

from graphify.extractors.resolution import _php_fqn_from_raw

# Mirrors `_PHP_RESOLVER_SUFFIXES` in graphify/extract.py. Kept local, like
# `_is_cs_file` in csharp.py, so this module imports nothing from the facade.
_PHP_SOURCE_SUFFIXES = (
    ".php", ".phtml", ".php3", ".php4", ".php5", ".php7", ".phps",
)


def _is_php_file(value: object) -> bool:
    return isinstance(value, str) and value.lower().endswith(_PHP_SOURCE_SUFFIXES)


def _metadata(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _php_key(name: object) -> str:
    """Fold a PHP class name: the language matches them case-insensitively."""
    return str(name).strip().casefold()


def _php_qualified_corroborates(
    qualified: str | None,
    type_node: dict | None,
    declared_fqn: str | None = None,
) -> bool:
    """True when a source-written class name corroborates the resolved node (#1682).

    ``(new \\App\\Services\\Svc())`` names the class outright, but the short-name
    lookup that found the node ignored the namespace — so the namespace is
    independent evidence, and only a match makes the edge EXTRACTED.

    ``declared_fqn`` is the name the DEFINING FILE declares for that class,
    read from its ``namespace`` statement at extraction time (#14). When it is
    known the comparison is whole-name: `\\App\\Services\\Client` corroborates
    `App\\Services\\Client` and nothing else. Two things that used to promote
    now do not — a file whose declared namespace disagrees with its PSR-4 path
    (the written name then denotes a class that exists nowhere in the corpus),
    and a truncated qualifier like `\\Services\\Client`, which is a DIFFERENT
    class from `App\\Services\\Client` but matched as a path tail.

    Without a declaration — the file declares no namespace at all, or the node
    came from a prior graph on an incremental run — the node's path is the only
    corroborating fact left, and PSR-4 maps ``App\\Services\\Svc`` onto
    ``app/Services/Svc.php``; every written segment must line up with the tail
    of that path, case-insensitively.

    A BARE name (no namespace segment) corroborates nothing and stays INFERRED;
    a namespace that does not line up downgrades rather than refusing, since the
    class name itself still resolved unambiguously.
    """
    if not qualified or not type_node:
        return False
    want = [seg.casefold() for seg in str(qualified).split("\\") if seg]
    if len(want) < 2:
        return False  # bare `new Svc()`: no namespace written, no evidence
    if declared_fqn:
        have = [seg.casefold() for seg in str(declared_fqn).split("\\") if seg]
        return want == have  # whole name, not a suffix of one
    source_file = str(type_node.get("source_file") or "")
    parts = [p for p in source_file.replace("\\", "/").split("/")
             if p and p not in (".", "..")]
    if not parts:
        return False
    parts[-1] = parts[-1].rsplit(".", 1)[0]  # drop the file extension
    parts = [p.casefold() for p in parts]
    return len(parts) >= len(want) and parts[-len(want):] == want


def _php_fqn_names_another_class(
    fqn: str,
    type_node: dict | None,
    declared_fqn: str | None,
) -> bool:
    """True when ``fqn`` provably names something OTHER than ``type_node`` (#21).

    The contrapositive of ``_php_qualified_corroborates``, with one deliberate
    difference: *absent* evidence is not a contradiction. Otherwise the same
    comparison the inline-`new` promotion already makes — the declared name when
    the defining file was dispatched this run, its PSR-4 path when it was not.

    Two shapes carry no evidence either way and so keep the edge:
      * a name with no namespace segment (`use Client;` imports from the global
        namespace and writes nothing to compare);
      * a path with fewer segments than the written name, once the declaration
        is unavailable — composer maps a namespace PREFIX onto a directory
        (`App\\Domain\\` -> `src/`), and a stripped prefix is indistinguishable
        from a different class. Refusing there would delete true edges on
        incremental rebuilds only, where the declaration is what is missing;
        persisting it for unchanged files is #23.

    That second branch is why every bindable declaration KIND has to reach the
    declared-FQN map: an `interface`/`enum`/`trait` left out of it was judged by
    path alone, and a replayed context node's relativized path has fewer
    segments than a 4-segment vendor FQN — so `use Illuminate\\Contracts\\…\\
    Notifier;` read as "no evidence" and kept an edge onto the in-corpus
    `App\\Contracts\\Notifier` it provably does not name (#53).
    """
    if type_node is None:
        return False
    want = [seg for seg in str(fqn).split("\\") if seg]
    if len(want) < 2:
        return False
    if not declared_fqn:
        parts = [
            part
            for part in str(type_node.get("source_file") or "").replace("\\", "/").split("/")
            if part and part not in (".", "..")
        ]
        if len(parts) < len(want):
            return False
    return not _php_qualified_corroborates(fqn, type_node, declared_fqn)


class PhpNameResolver:
    """``use``-import/namespace-aware PHP receiver-type resolution (#21).

    The PHP twin of ``CsharpNameResolver`` (``extractors/csharp.py``), built for
    the same reason: ``_resolve_php_member_calls`` bound a receiver's short type
    name through a corpus-wide index whose only refusal rule was "more than one
    candidate", so a file that writes ``use Vendor\\Sdk\\Client;`` — CLAIMING the
    name ``Client`` for a class outside the corpus — still bound the lone
    unrelated ``App\\Local\\Client`` and minted a wrong ``INFERRED 0.8`` edge
    (#16). Consulted in front of that fallback, this resolver makes the claim
    decisive: it refuses instead of guessing.

    Built from graph-stamped facts only — the ``imports`` edges' ``use``
    metadata (#19), the declared-FQN payload of the files dispatched this run
    (#14), and the same type-definition index the fallback uses. Nothing is
    re-parsed, and no new persisted marker is needed: the ``use`` map belongs to
    the CALLING file, which an incremental rebuild always re-dispatches.

    The refusal (#21) is strictly subtractive; the declared-FQN index layered on
    top (#22) is its additive counterpart. When the claimed FQN matches the name
    some in-corpus type's own file DECLARES (#14), that match outranks the
    short-name census: it picks the imported one of several same-short-named
    types, and follows a renaming alias (``use App\\X as Y;``) to a type the
    written short name never would have found. The index only knows types whose
    declared FQNs are available — for a file left undispatched by an incremental
    rebuild that is the persisted ``_php_class_fqns`` marker (#23); a graph
    written before that marker simply yields no match and the verdict falls back
    to the #21 rules, adding no edge rather than a wrong one. ``interface``,
    ``enum`` and ``trait`` declarations are in the index since #53 made them
    bindable receiver types; without their FQNs the #21 rules judged them by
    PSR-4 path alone, which is weaker and, on replayed context nodes, wrong.
    """

    def __init__(
        self,
        all_nodes: list[dict],
        all_edges: list[dict],
        type_def_nids: dict[str, list[str]],
        class_fqn_by_file: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.type_def_nids = type_def_nids
        self.class_fqn_by_file = class_fqn_by_file or {}
        self.node_by_id: dict[str, dict] = {
            node["id"]: node
            for node in all_nodes
            if isinstance(node.get("id"), str) and node.get("id")
        }

        # Per file: claimed short name -> imported FQN. Read off the edge
        # METADATA, never the target node's label — `_resolve_php_type_references`
        # re-points import targets (onto an FQN stub, or onto the in-corpus class
        # the unique-label rewire finds), and only the metadata still spells what
        # the file actually wrote (#19).
        self.uses_by_file: dict[str, dict[str, str]] = {}
        for edge in all_edges:
            if edge.get("relation") != "imports":
                continue
            source_file = edge.get("source_file")
            if not _is_php_file(source_file):
                continue
            metadata = _metadata(edge.get("metadata"))
            # `use function` / `use const` import no class name, in either
            # spelling — the shared parser reports the declaration-level keyword
            # of the group form too (#26).
            if metadata.get("use_kind") != "class":
                continue
            target_fqn = metadata.get("target_fqn")
            if not isinstance(target_fqn, str) or not target_fqn:
                continue
            alias = metadata.get("alias")
            claimed = _php_key(
                alias if isinstance(alias, str) and alias
                else target_fqn.rsplit("\\", 1)[-1]
            )
            if claimed:
                # Two `use`s claiming one name is a PHP fatal error; first wins.
                self.uses_by_file.setdefault(source_file, {}).setdefault(
                    claimed, target_fqn
                )

        # Declared FQN -> definition node, over the same node universe as the
        # short-name index — every binding this enables is one the fallback
        # could have made if only it could tell the namesakes apart (#22). An
        # FQN declared by two nodes (copied fixtures, vendored duplicates) is
        # poisoned rather than answered with either.
        self.fqn_def_nid: dict[str, str | None] = {}
        for nids in type_def_nids.values():
            for nid in nids:
                node = self.node_by_id.get(nid)
                declared = self._declared_fqn(node)
                if not declared:
                    continue
                fqn_key = _php_key(declared)
                if self.fqn_def_nid.setdefault(fqn_key, nid) != nid:
                    self.fqn_def_nid[fqn_key] = None

        # Per file: the namespace its declarations sit in, needed to resolve a
        # namespace-RELATIVE annotation (`Local\Client`). Derived from the
        # declared-FQN payload, which covers every file dispatched this run —
        # and the file that writes the annotation always is one. A file that
        # declares two namespaces (a PSR-1 violation) is left out rather than
        # answered with one of them.
        self.namespace_by_file: dict[str, str] = {}
        for path, classes in self.class_fqn_by_file.items():
            namespaces = {
                fqn.rsplit("\\", 1)[0] if "\\" in fqn else ""
                for fqn in classes.values()
            }
            if len(namespaces) == 1:
                self.namespace_by_file[path] = next(iter(namespaces))

    def _declared_fqn(self, type_node: dict | None) -> str | None:
        """The name the DEFINING file declares for ``type_node``'s class (#14).

        Absent for a global-namespace class, and for a class whose file was not
        dispatched this run — an incremental rebuild then falls back to the
        PSR-4 path comparison, which is why the refusal needs no new marker.
        """
        if not type_node:
            return None
        by_name = self.class_fqn_by_file.get(str(type_node.get("source_file") or ""))
        if not by_name:
            return None
        return by_name.get(_php_key(type_node.get("label", "")))

    def _written_fqn(self, written: str, source_file: str) -> str | None:
        """The FQN a QUALIFIED written annotation denotes, or None if unknowable.

        PHP resolves `\\A\\B` absolutely, `A\\B` through the `use` map's
        group-prefix semantics and otherwise relative to the current namespace —
        never against the global namespace. A leading backslash is therefore not
        something to assume nor to strip blindly (#20).
        """
        raw = written.strip()
        if raw.startswith("\\"):
            return raw.lstrip("\\")
        uses = self.uses_by_file.get(source_file, {})
        if _php_key(raw.split("\\", 1)[0]) in uses:
            return _php_fqn_from_raw(raw, "", uses)
        namespace = self.namespace_by_file.get(source_file)
        if namespace is not None:
            return _php_fqn_from_raw(raw, namespace, uses)
        if source_file in self.class_fqn_by_file:
            return None  # two namespaces in one file: refuse to pick one
        return _php_fqn_from_raw(raw, "", uses)  # the file is global-namespace

    def resolve_type_name(
        self, type_name: str, qualified: object, source_file: str
    ) -> tuple[str | None, bool]:
        """Resolve a receiver's declared type to a definition node, with a verdict.

        Returns ``(node_id, decisive)``:
          * ``(nid, True)``  — the file's own naming lands on that definition.
          * ``(None, True)`` — the file CLAIMS the name (a `use` import, or a
            qualified form written at the annotation) and the claim does not
            land on an in-corpus class: refuse, and do NOT let the caller fall
            back to the looser corpus-wide bare-name match. This is #16.
          * ``(None, False)`` — nothing in the file claims the name; the
            caller's existing fallback runs unchanged.
        """
        short = _php_key(type_name)
        if not short:
            return None, False
        written = qualified.strip() if isinstance(qualified, str) else ""
        if "\\" in written:
            fqn = self._written_fqn(written, source_file)
        else:
            fqn = self.uses_by_file.get(source_file, {}).get(short)
        if not fqn:
            return None, False

        # The claimed FQN against the names the defining files DECLARE (#22):
        # a unique match is the strongest verdict there is — the calling file
        # names the class in full and some file declares exactly that class —
        # so it outranks the short-name census below, selecting the imported
        # one of several namesakes and following a renaming alias to a class
        # the written short name would never census. Absent a match (the
        # defining file declares no namespace, or was not dispatched and left
        # no #23 marker) nothing is asserted either way: fall through, where
        # the #21 rules refuse or bind exactly as they did before this index.
        declared_nid = self.fqn_def_nid.get(_php_key(fqn))
        if declared_nid is not None:
            return declared_nid, True

        candidates = self.type_def_nids.get(short, [])
        if len(candidates) != 1:
            # Nothing in the corpus answers to the written name, or several
            # things do — and no declared FQN above told them apart. There
            # is no edge the fallback could keep either way: refuse.
            return None, True
        node = self.node_by_id.get(candidates[0])
        if _php_fqn_names_another_class(fqn, node, self._declared_fqn(node)):
            return None, True
        return candidates[0], True
