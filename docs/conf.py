"""Sphinx configuration for wbi-birds."""

import os
import sys

sys.path.insert(0, os.path.abspath("../src"))

project = "wbi-birds"
copyright = "2026, UBC FRESH Lab"
author = "UBC FRESH Lab"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

# The workflow layer is optional (the `workflow` extra); mock it for API docs.
autodoc_mock_imports = ["freshforge"]
autodoc_typehints = "description"

templates_path: list[str] = []
exclude_patterns = ["_build"]

html_theme = "sphinx_rtd_theme"
html_static_path: list[str] = []
