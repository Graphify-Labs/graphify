"""Issue-triage automation for the Graphify repository.

``taxonomy`` is the single source of truth for the labels, ``classify`` turns one
issue into ``area/`` + ``kind/`` labels with a single model call, and
``sync_labels`` creates those labels on the repository. See ``README.md``.
"""
