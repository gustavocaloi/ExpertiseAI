from __future__ import annotations

import json
import traceback
import os
import sys
import tempfile
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _extract_markdown(result: object) -> str:
    document = getattr(result, "document", None)
    if document is None:
        raise ValueError("Falha ao converter arquivo com docling: documento não retornado.")
    if hasattr(document, "export_to_markdown"):
        markdown = document.export_to_markdown()
    elif hasattr(document, "to_markdown"):
        markdown = document.to_markdown()
    else:
        raise ValueError("Conversor docling sem método conhecido de exportação.")
    markdown = str(markdown or "")
    if not markdown.strip():
        raise ValueError("Docling retornou conteúdo vazio.")
    return markdown


def _page_count(file_path: Path) -> int | None:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return None

    document = None
    try:
        document = pdfium.PdfDocument(str(file_path))
        return len(document)
    except Exception:
        return None
    finally:
        if document is not None and hasattr(document, "close"):
            document.close()


def _split_pdf_to_chunks(file_path: Path, batch_size: int) -> list[Path]:
    import pypdfium2 as pdfium

    chunks: list[Path] = []
    source = pdfium.PdfDocument(str(file_path))
    try:
        total_pages = len(source)
        temp_root = Path(tempfile.mkdtemp(prefix="docling-pdf-chunks-"))
        for start in range(0, total_pages, batch_size):
            end = min(start + batch_size, total_pages)
            target = pdfium.PdfDocument.new()
            try:
                target.import_pages(source, pages=list(range(start, end)))
                chunk_path = temp_root / f"{file_path.stem}-chunk-{start+1}-{end}.pdf"
                target.save(str(chunk_path))
                chunks.append(chunk_path)
            finally:
                if hasattr(target, "close"):
                    target.close()
    finally:
        if hasattr(source, "close"):
            source.close()
    return chunks


def _build_converter(file_path: Path):
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    pipeline_options = PdfPipelineOptions()
    if hasattr(pipeline_options, "do_ocr"):
        pipeline_options.do_ocr = _bool_env("EXPAI_DOCLING_OCR_ENABLED", True)
    if hasattr(pipeline_options, "do_table_structure"):
        pipeline_options.do_table_structure = _bool_env("EXPAI_DOCLING_TABLE_STRUCTURE_ENABLED", True)
    if hasattr(pipeline_options, "document_timeout"):
        pipeline_options.document_timeout = _int_env("EXPAI_DOCLING_TIMEOUT_SECONDS", 600)
    if hasattr(pipeline_options, "enable_remote_services"):
        pipeline_options.enable_remote_services = False

    if file_path.suffix.lower() == ".pdf":
        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            },
        )
    if file_path.suffix.lower() == ".docx":
        return DocumentConverter(allowed_formats=[InputFormat.DOCX])
    return DocumentConverter()


def _convert(file_path: Path) -> str:
    max_file_size_bytes = _int_env("EXPAI_DOCLING_MAX_FILE_SIZE_BYTES", 50 * 1024 * 1024)
    file_size_bytes = file_path.stat().st_size
    if file_size_bytes > max_file_size_bytes:
        raise ValueError("Arquivo excede o tamanho máximo permitido para conversão.")

    converter = _build_converter(file_path)
    convert_kwargs = {
        "max_file_size": max_file_size_bytes,
    }

    if file_path.suffix.lower() != ".pdf":
        return _extract_markdown(converter.convert(str(file_path), **convert_kwargs))

    max_pages = _int_env("EXPAI_DOCLING_MAX_PAGES", 250)
    batch_size = max(1, _int_env("EXPAI_DOCLING_PDF_PAGE_BATCH_SIZE", 25))
    total_pages = _page_count(file_path)

    if total_pages is not None and total_pages > max_pages:
        raise ValueError(f"PDF com {total_pages} páginas excede o limite configurado de {max_pages} páginas.")

    if total_pages is not None and total_pages > batch_size:
        markdown_parts: list[str] = []
        chunk_paths = _split_pdf_to_chunks(file_path, batch_size)
        try:
            for chunk_path in chunk_paths:
                chunk_result = converter.convert(str(chunk_path), max_file_size=max_file_size_bytes, max_num_pages=batch_size)
                markdown_parts.append(_extract_markdown(chunk_result).strip())
        finally:
            for chunk_path in chunk_paths:
                chunk_path.unlink(missing_ok=True)
            if chunk_paths:
                chunk_root = chunk_paths[0].parent
                chunk_root.rmdir()
        return "\n\n".join(part for part in markdown_parts if part)

    convert_kwargs["max_num_pages"] = max_pages
    return _extract_markdown(converter.convert(str(file_path), **convert_kwargs))

def main() -> int:
    if len(sys.argv) != 4:
        print("Usage: docling_worker.py <input_path> <output_path> <filename>", file=sys.stderr)
        return 2

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    _filename = sys.argv[3]

    try:
        file_size_bytes = input_path.stat().st_size if input_path.exists() else -1
        page_count = _page_count(input_path) if input_path.suffix.lower() == ".pdf" else None
        print(
            json.dumps(
                {
                    "event": "docling_worker_start",
                    "input_path": str(input_path),
                    "filename": _filename,
                    "file_size_bytes": file_size_bytes,
                    "page_count": page_count,
                },
                ensure_ascii=False,
            ),
            file=sys.stdout,
        )
        markdown = _convert(input_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump({"markdown": markdown}, f, ensure_ascii=False)
        print(
            json.dumps(
                {
                    "event": "docling_worker_done",
                    "input_path": str(input_path),
                    "filename": _filename,
                    "markdown_length": len(markdown),
                },
                ensure_ascii=False,
            ),
            file=sys.stdout,
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "event": "docling_worker_error",
                    "input_path": str(input_path),
                    "filename": _filename,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
