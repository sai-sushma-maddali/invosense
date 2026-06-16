"""Standalone invoice extraction module.

Turns an invoice image into an ``ExtractedInvoice`` (Contract 1) JSON object
using a Groq vision LLM routed through the TrueFoundry AI Gateway.
"""

from extraction.contract import ExtractedInvoice
from extraction.extract import run

__all__ = ["ExtractedInvoice", "run"]
