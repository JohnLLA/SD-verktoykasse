"""Prepare tables from Excel and CSV for Datawrapper."""

import os

# openpyxl reads every XML part with the standard library through defusedxml
# only when lxml is switched off; otherwise most parts go through lxml, which
# expands internal entities. Must be set before openpyxl is imported.
os.environ["OPENPYXL_LXML"] = "False"
os.environ["OPENPYXL_DEFUSEDXML"] = "True"

__version__ = "0.1.0"
