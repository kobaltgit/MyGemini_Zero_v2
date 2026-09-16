"""
ChromaDB Vector Store Service for Long-Term Memory (RAG) in MyGemini Zero v2.
Handles chunking, Google Generative AI embeddings, semantic search,
and document management (viewing uploaded files and targeted deletion).
"""

import os
import time
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
import chromadb
from chromadb.config import Settings as ChromaSettings
from google import genai

from core.config import settings
from core.logger import get_logger

logger = get_logger("database")


class TextSplitter:
    """Lightweight recursive character text splitter."""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            if end < text_len:
                # Find suitable break point
                split_at = text.rfind("\n\n", start, end)
                if split_at == -1 or split_at < start + self.chunk_size // 2:
                    split_at = text.rfind("\n", start, end)
                if split_at == -1 or split_at < start + self.chunk_size // 2:
                    split_at = text.rfind(" ", start, end)
                if split_at != -1 and split_at > start:
                    end = split_at

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = max(end - self.chunk_overlap, start + 1)
            if end >= text_len:
                break

        return chunks


class VectorStoreManager:
    """
    Manages isolated long-term vector memory per dialog using ChromaDB.
    Supports operation with or without an API key (management operations).
    """

    def __init__(self, api_key: Optional[str] = None):
        os.makedirs(settings.VECTOR_STORE_PATH, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=settings.VECTOR_STORE_PATH,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.api_key = api_key
        self.genai_client = genai.Client(api_key=api_key) if api_key else None
        self.splitter = TextSplitter(chunk_size=500, chunk_overlap=50)

    def _get_collection(self, dialog_id: int):
        """Retrieves or creates ChromaDB collection for the dialog."""
        return self.client.get_or_create_collection(name=f"dialog_{dialog_id}")

    async def _embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings using official google-genai SDK."""
        if not self.genai_client:
            raise ValueError("Google API key is required to create embeddings.")

        embeddings = []
        for text in texts:
            resp = await self.genai_client.aio.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
            )
            # Handle Matryoshka truncation or standard 768 vector
            raw_vals = resp.embedding.values if hasattr(resp, "embedding") else resp.embeddings[0].values
            embeddings.append(list(raw_vals[:768]))
        return embeddings

    async def add_document(
        self,
        dialog_id: int,
        text_content: str,
        filename: str,
        file_size: Optional[int] = None,
    ) -> int:
        """
        Splits uploaded document into chunks, generates embeddings,
        and saves into dialog collection with document metadata.
        Returns the number of chunks added.
        """
        if not text_content.strip():
            return 0

        chunks = self.splitter.split_text(text_content)
        if not chunks:
            return 0

        collection = self._get_collection(dialog_id)
        now_ts = int(time.time())
        now_iso = datetime.now().isoformat()
        name_hash = hashlib.md5(filename.encode("utf-8", errors="ignore")).hexdigest()[:16]

        chunk_ids = [f"doc_{name_hash}_{now_ts}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "content_type": "document",
                "file_name": filename,
                "file_hash": name_hash,
                "file_size": file_size or len(text_content.encode("utf-8")),
                "timestamp": now_iso,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        embeddings = await self._embed_texts(chunks)

        collection.add(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )

        logger.info(f"Added document '{filename}' ({len(chunks)} chunks) to dialog {dialog_id}")
        return len(chunks)

    def get_dialog_documents(self, dialog_id: int) -> List[Dict[str, Any]]:
        """
        Aggregates all document chunks stored in dialog into unique document summaries.
        Returns list of {file_name, file_hash, chunks_count, timestamp, file_size}.
        """
        collection_name = f"dialog_{dialog_id}"
        try:
            collection = self.client.get_collection(name=collection_name)
        except Exception:
            return []

        results = collection.get(
            where={"content_type": "document"},
            include=["metadatas"],
        )

        metas = results.get("metadatas") or []
        docs_map: Dict[str, Dict[str, Any]] = {}

        for meta in metas:
            if not isinstance(meta, dict):
                continue
            fname = meta.get("file_name", "Без имени")
            fhash = meta.get("file_hash", hashlib.md5(fname.encode("utf-8")).hexdigest()[:16])

            if fhash not in docs_map:
                docs_map[fhash] = {
                    "file_name": fname,
                    "file_hash": fhash,
                    "chunks_count": 0,
                    "timestamp": meta.get("timestamp", ""),
                    "file_size": meta.get("file_size", 0),
                }
            docs_map[fhash]["chunks_count"] += 1

        return list(docs_map.values())

    def delete_document(self, dialog_id: int, file_identifier: str) -> bool:
        """
        Deletes all chunks belonging to a specific document by file_name or file_hash.
        """
        collection_name = f"dialog_{dialog_id}"
        try:
            collection = self.client.get_collection(name=collection_name)
        except Exception:
            return False

        try:
            # 1. Direct match by file_name
            res = collection.get(where={"file_name": file_identifier})
            if res and res.get("ids"):
                collection.delete(where={"file_name": file_identifier})
                logger.info(f"Deleted document '{file_identifier}' from dialog {dialog_id}")
                return True

            # 2. Match by file_hash
            all_docs = collection.get(where={"content_type": "document"}, include=["metadatas"])
            ids = all_docs.get("ids") or []
            metadatas = all_docs.get("metadatas") or []
            target_ids = []

            for i, m in enumerate(metadatas):
                if isinstance(m, dict):
                    f_hash = m.get("file_hash", "")
                    f_name = m.get("file_name", "")
                    if f_hash == file_identifier or f_name == file_identifier:
                        target_ids.append(ids[i])

            if target_ids:
                collection.delete(ids=target_ids)
                logger.info(f"Deleted {len(target_ids)} chunks for identifier '{file_identifier}'")
                return True

            return False
        except Exception as e:
            logger.error(f"Error deleting document '{file_identifier}': {e}")
            return False

    def delete_dialog_memory(self, dialog_id: int) -> bool:
        """Completely purges ChromaDB collection when a dialog is deleted."""
        collection_name = f"dialog_{dialog_id}"
        try:
            self.client.delete_collection(name=collection_name)
            logger.info(f"Purged vector memory for dialog {dialog_id}")
            return True
        except Exception:
            return False

    async def search_context(self, dialog_id: int, query: str, n_results: int = 4) -> str:
        """
        Performs semantic RAG retrieval of relevant chunks for a user query.
        """
        collection_name = f"dialog_{dialog_id}"
        try:
            collection = self.client.get_collection(name=collection_name)
        except Exception:
            return ""

        count = collection.count()
        if count == 0:
            return ""

        try:
            query_embeddings = await self._embed_texts([query])
            results = collection.query(
                query_embeddings=query_embeddings,
                n_results=min(n_results, count),
            )
            docs = results.get("documents", [[]])[0]
            if not docs:
                return ""
            context_blocks = [f"--- Контекст из документов ---\n" + "\n---\n".join(docs)]
            return "\n\n".join(context_blocks)
        except Exception as e:
            logger.error(f"Error searching vector context: {e}")
            return ""
