from io import BytesIO
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from pypdf import PdfReader


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".log", ".json"}


async def parse_upload_to_document(
    file: UploadFile,
    source_type: str,
    equipment_id: Optional[str],
    title: Optional[str],
) -> dict[str, Union[str, None]]:
    content = await file.read()
    filename = file.filename or "uploaded-document"
    text = _extract_text(filename, file.content_type, content)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Uploaded document did not contain extractable text")
    return {
        "id": f"DOC-UPLOAD-{uuid4().hex[:10]}",
        "source_type": source_type,
        "equipment_id": equipment_id,
        "title": title or Path(filename).stem.replace("_", " ").replace("-", " ").strip() or filename,
        "content": text.strip(),
    }


def _extract_text(filename: str, content_type: Optional[str], content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" or content_type == "application/pdf":
        return _extract_pdf_text(content)
    if suffix in TEXT_EXTENSIONS or (content_type and content_type.startswith("text/")):
        return _decode_text(content)
    raise HTTPException(status_code=400, detail=f"Unsupported document type for {filename}")


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="Uploaded text file could not be decoded")


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Uploaded PDF could not be parsed: {exc}") from exc
