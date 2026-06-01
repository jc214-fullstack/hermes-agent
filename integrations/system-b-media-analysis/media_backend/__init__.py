"""System B media backend.

Native Linux/WSL package for identifying media URL sources, downloading media,
and preparing local audio/frame artifacts for later analysis.
"""

__version__ = "0.2.0"

from .detector import SourceInfo, detect
from .downloader import DownloadError, download
from .extractor import ExtractionError, extract_audio, extract_frames
from .manifest import build_manifest_data, write_manifest

__all__ = [
    "SourceInfo",
    "detect",
    "DownloadError",
    "download",
    "ExtractionError",
    "extract_audio",
    "extract_frames",
    "build_manifest_data",
    "write_manifest",
]
