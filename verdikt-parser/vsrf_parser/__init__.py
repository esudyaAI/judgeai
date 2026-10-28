"""Парсер судебных актов Верховного Суда РФ (vsrf.ru)."""

from .client import VSRFClient
from .crawler import Crawler
from .http_client import HttpClient
from .listing import parse_listing
from .models import ClaimDetails, ParsedActText
from .pdf import download_pdf, extract_text
from .sudact import SudActClient
from .text_parser import parse_act_file, parse_act_text

__version__ = "1.0.0"

__all__ = [
    "VSRFClient",
    "Crawler",
    "HttpClient",
    "SudActClient",
    "parse_listing",
    "parse_act_text",
    "parse_act_file",
    "ClaimDetails",
    "ParsedActText",
    "download_pdf",
    "extract_text",
]
