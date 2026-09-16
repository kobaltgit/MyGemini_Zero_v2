"""
Media Processing Service for MyGemini Zero v2.
Converts images, voice notes, and documents (PDF, DOCX, TXT) into Gemini SDK multimodal parts.
"""

from io import BytesIO
from typing import Tuple
from google.genai import types
from pypdf import PdfReader
from docx import Document

from core.logger import get_logger

logger = get_logger("user_messages")


def format_image_part(image_bytes: bytes, mime_type: str = "image/jpeg") -> types.Part:
    """Wraps raw image bytes into a google-genai Part object."""
    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)


def format_audio_part(audio_bytes: bytes, mime_type: str = "audio/ogg") -> types.Part:
    """Wraps voice/audio bytes into a google-genai Part object."""
    return types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)


def parse_document_text(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """
    Extracts text from uploaded document files based on extension.
    Returns tuple of (extracted_text, document_type).
    Supported formats: PDF, DOCX, TXT, MD, PY, JSON, CSV.
    """
    lower_name = filename.lower()

    if lower_name.endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(file_bytes))
            pages_text = []
            for i, page in enumerate(reader.pages):
                txt = page.extract_text() or ""
                if txt.strip():
                    pages_text.append(f"--- Страница {i + 1} ---\n{txt}")
            extracted = "\n\n".join(pages_text)
            return extracted or "[Документ PDF пуст или содержит только изображения]", "pdf"
        except Exception as e:
            logger.error(f"Error reading PDF {filename}: {e}")
            return f"[Ошибка при чтении PDF: {e}]", "pdf"

    elif lower_name.endswith(".docx"):
        try:
            doc = Document(BytesIO(file_bytes))
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            extracted = "\n".join(paras)
            return extracted or "[Документ DOCX пуст]", "docx"
        except Exception as e:
            logger.error(f"Error reading DOCX {filename}: {e}")
            return f"[Ошибка при чтении DOCX: {e}]", "docx"

    else:
        # Plain text formats (txt, md, json, csv, py, etc.)
        for encoding in ["utf-8", "cp1251", "latin-1"]:
            try:
                decoded = file_bytes.decode(encoding)
                return decoded, "text"
            except UnicodeDecodeError:
                continue

        return "[Не удалось распознать кодировку текстового файла]", "text"
