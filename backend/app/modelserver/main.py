"""Model server: embeddings and reranking over HTTP.

Runs wherever the GPU is. On a Windows laptop that is the host, not Docker:
    .\\make.ps1 models
Without a GPU, the `models` compose profile runs the same code on CPU.

Isolating torch here keeps the api and worker images small and lets several processes
share one copy of the weights. The api/worker talk to it through app.services.embedding.http.
"""

import logging
import os
import threading
import time
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import CrossEncoder, SentenceTransformer

log = logging.getLogger("mindgrep.models")
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
EMBED_MAX_TOKENS = int(os.environ.get("EMBED_MAX_TOKENS", "2048"))
RERANK_MAX_TOKENS = int(os.environ.get("RERANK_MAX_TOKENS", "512"))
BATCH_SIZE = int(os.environ.get("MODEL_BATCH_SIZE", "16"))

# Qwen3-Embedding is instruction-tuned: queries carry a task description, documents do not.
QUERY_PROMPT = (
    "Instruct: Given a developer's search query, retrieve the code, notes, or document "
    "passages that answer it\nQuery: "
)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DTYPE = torch.float16 if DEVICE == "cuda" else torch.float32

# One GPU, one request at a time: interleaved batches only thrash memory.
_lock = threading.Lock()
_models: dict[str, object] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    started = time.perf_counter()
    embedder = SentenceTransformer(
        EMBEDDING_MODEL, device=DEVICE, model_kwargs={"torch_dtype": DTYPE}
    )
    embedder.max_seq_length = EMBED_MAX_TOKENS
    reranker = CrossEncoder(
        RERANKER_MODEL,
        device=DEVICE,
        max_length=RERANK_MAX_TOKENS,
        model_kwargs={"torch_dtype": DTYPE},
    )
    _models["embedder"], _models["reranker"] = embedder, reranker
    log.info(
        "loaded %s (%d dims) and %s on %s in %.1fs",
        EMBEDDING_MODEL,
        embedder.get_sentence_embedding_dimension(),
        RERANKER_MODEL,
        DEVICE,
        time.perf_counter() - started,
    )
    yield
    _models.clear()


app = FastAPI(title="Mindgrep model server", lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str] = Field(max_length=512)
    input_type: str = Field(pattern="^(query|document)$")


class RerankRequest(BaseModel):
    query: str
    documents: list[str] = Field(max_length=300)


@app.get("/info")
def info() -> dict:
    embedder: SentenceTransformer = _models["embedder"]  # type: ignore[assignment]
    return {
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": embedder.get_sentence_embedding_dimension(),
        "reranker_model": RERANKER_MODEL,
        "device": DEVICE,
        "gpu": torch.cuda.get_device_name(0) if DEVICE == "cuda" else None,
    }


@app.post("/embed")
def embed(request: EmbedRequest) -> dict:
    embedder: SentenceTransformer = _models["embedder"]  # type: ignore[assignment]
    prompt = QUERY_PROMPT if request.input_type == "query" else None
    with _lock:
        try:
            vectors = embedder.encode(
                request.texts,
                prompt=prompt,
                batch_size=BATCH_SIZE,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except torch.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            raise HTTPException(503, "GPU out of memory; retry with a smaller batch") from exc
    return {"model": EMBEDDING_MODEL, "vectors": vectors.astype("float32").tolist()}


@app.post("/rerank")
def rerank(request: RerankRequest) -> dict:
    reranker: CrossEncoder = _models["reranker"]  # type: ignore[assignment]
    pairs = [(request.query, doc) for doc in request.documents]
    with _lock:
        try:
            # Sigmoid puts scores in [0, 1], which makes an abstention threshold meaningful.
            scores = reranker.predict(
                pairs,
                batch_size=BATCH_SIZE * 2,
                activation_fn=torch.nn.Sigmoid(),
                convert_to_numpy=True,
            )
        except torch.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            raise HTTPException(503, "GPU out of memory; retry with fewer documents") from exc
    return {"model": RERANKER_MODEL, "scores": [float(s) for s in scores]}
