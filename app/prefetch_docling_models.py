from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path


def _minimal_pdf_bytes() -> bytes:
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 36 120 Td (Docling prefetch) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000241 00000 n 
0000000335 00000 n 
trailer
<< /Root 1 0 R /Size 6 >>
startxref
405
%%EOF
"""


def _configure_cache(cache_root: Path) -> None:
    hf_cache = cache_root / "huggingface"
    cache_root.mkdir(parents=True, exist_ok=True)
    hf_cache.mkdir(parents=True, exist_ok=True)
    os.environ["DOCLING_CACHE_DIR"] = str(cache_root)
    os.environ["XDG_CACHE_HOME"] = str(cache_root)
    os.environ["HF_HOME"] = str(hf_cache)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_cache)
    os.environ.pop("TRANSFORMERS_CACHE", None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", required=True)
    args = parser.parse_args()

    cache_root = Path(args.cache_dir).resolve()
    _configure_cache(cache_root)

    from app.docling_worker import _convert

    temp_root = Path(tempfile.mkdtemp(prefix="docling-prefetch-"))
    pdf_path = temp_root / "prefetch.pdf"
    try:
        pdf_path.write_bytes(_minimal_pdf_bytes())
        _convert(pdf_path)
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
