from __future__ import annotations

from typing import Any

import chromadb
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore
from ollama import Client

from config import CHROMA_DIR, COLLECTION_NAME, OLLAMA_EMBED_MODEL, OLLAMA_MODEL, PAGES_PATH
from utils import load_json


def _available_ollama_models() -> list[str]:
    client = Client()
    response = client.list()
    models = response.get("models", []) if isinstance(response, dict) else getattr(response, "models", [])
    names: list[str] = []
    for model in models:
        if isinstance(model, dict):
            name = model.get("name") or model.get("model")
        else:
            name = getattr(model, "model", None) or getattr(model, "name", None)
        if name:
            names.append(name)
    return names


def _resolve_model(preferred: str, available: list[str]) -> str:
    exact = next((name for name in available if name == preferred), None)
    if exact:
        return exact
    base = preferred.split(":", 1)[0]
    partial = next((name for name in available if name.startswith(f"{base}:") or name == base), None)
    if partial:
        return partial
    return available[0] if available else preferred


def _resolve_completion_model(preferred: str, available: list[str]) -> str:
    resolved = _resolve_model(preferred, available)
    if resolved in available and "embed" not in resolved.lower():
        return resolved
    preferred_fallbacks = ["gemma3:1b", "gemma3", "llama3.1", "llama3", "mistral"]
    for candidate in preferred_fallbacks:
        matched = next((name for name in available if name == candidate or name.startswith(f"{candidate}:")), None)
        if matched:
            return matched
    fallback = next((name for name in available if "embed" not in name.lower()), None)
    return fallback or resolved


def _build_documents() -> list[Document]:
    pages = load_json(PAGES_PATH, [])
    splitter = SentenceSplitter(chunk_size=800, chunk_overlap=120)
    documents: list[Document] = []

    for page in pages:
        content = page.get("markdown") or page.get("text") or ""
        if not content.strip():
            continue
        chunks = splitter.split_text(content)
        for index, chunk in enumerate(chunks):
            documents.append(
                Document(
                    text=chunk,
                    metadata={
                        "url": page.get("url", "unknown"),
                        "title": page.get("title", "unknown"),
                        "page_type": page.get("page_type", "unknown"),
                        "chunk_id": f"{page.get('title', 'page')}::{index}",
                    },
                )
            )
    return documents


def build_knowledge_base() -> dict[str, Any]:
    available_models = _available_ollama_models()
    llm_model = _resolve_completion_model(OLLAMA_MODEL, available_models)
    embed_model = _resolve_model(OLLAMA_EMBED_MODEL, available_models)

    Settings.embed_model = OllamaEmbedding(model_name=embed_model)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    documents = _build_documents()
    VectorStoreIndex.from_documents(documents, storage_context=storage_context, show_progress=True)

    result = {
        "documents_indexed": len(documents),
        "llm_model": llm_model,
        "embedding_model": embed_model,
        "collection": COLLECTION_NAME,
    }
    print(
        f"Built knowledge base with {result['documents_indexed']} chunks using "
        f"LLM={result['llm_model']} EMBED={result['embedding_model']}"
    )
    return result


def get_runtime_models() -> dict[str, str]:
    available_models = _available_ollama_models()
    return {
        "llm_model": _resolve_completion_model(OLLAMA_MODEL, available_models),
        "embedding_model": _resolve_model(OLLAMA_EMBED_MODEL, available_models),
    }


def load_vector_index() -> VectorStoreIndex:
    models = get_runtime_models()
    Settings.embed_model = OllamaEmbedding(model_name=models["embedding_model"])
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=collection)
    return VectorStoreIndex.from_vector_store(vector_store=vector_store)
