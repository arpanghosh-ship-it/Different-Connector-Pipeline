"""
qdrant_store.py — Interface with Qdrant Cloud for vector storage.

All embedding and upsert operations happen here.
Uses direct qdrant-client, NO LangChain wrappers.
"""

import logging
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams, Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)

COLLECTION_NAME = "documents"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 3072
EMBED_BATCH_SIZE = 100
UPSERT_BATCH_SIZE = 100


def init_collection(qdrant_client: QdrantClient) -> None:
    """
    Initialize the Qdrant Cloud collection at startup.
    
    If it exists, do nothing.
    If it doesn't exist, create it with 3072 dims and Cosine distance.
    """
    try:
        collections = qdrant_client.get_collections().collections
        exists = any(c.name == COLLECTION_NAME for c in collections)
        
        if exists:
            logger.info(f"[init_collection] Collection '{COLLECTION_NAME}' already exists")
        else:
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE)
            )
            logger.info(f"[init_collection] Created collection '{COLLECTION_NAME}'")
            
    except Exception as e:
        logger.error(f"[init_collection] Failed to initialize Qdrant collection: {e}")
        raise


def embed_texts(texts: list[str], openai_client) -> list[list[float]]:
    """
    Embed a list of text strings using OpenAI text-embedding-3-large.
    
    Batches texts into groups of EMBED_BATCH_SIZE (100).
    
    Parameters
    ----------
    texts : list[str]
        List of chunks to embed.
    openai_client : openai.OpenAI
        Initialized OpenAI client.
        
    Returns
    -------
    list[list[float]]
        Flat list of embedding vectors (each 3072 dims) in the same order as texts.
    """
    logger.info(f"[embed_texts] Embedding {len(texts)} chunks")
    all_embeddings = []
    
    try:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            
            response = openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch
            )
            
            # OpenAI returns embeddings in the 'data' array, maintaining order
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
            
        batches_count = (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE
        logger.info(f"[embed_texts] Completed embedding {len(texts)} chunks across {batches_count} batch(es)")
        return all_embeddings
        
    except Exception as e:
        logger.error(f"[embed_texts] Failed to embed chunks: {e}")
        raise


def delete_by_source_id(source_id: str, qdrant_client: QdrantClient) -> None:
    """
    Delete all Qdrant points for a given source_id.
    
    Called before re-ingesting a file to prevent duplicate points.
    """
    try:
        logger.info(f"[delete_by_source_id] Deleting existing points for source_id={source_id!r}")
        
        response = qdrant_client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="source_id",
                        match=MatchValue(value=source_id)
                    )
                ]
            )
        )
        # It's hard to get the exact count deleted without a separate scroll/count call,
        # so we just log success.
        logger.info(f"[delete_by_source_id] Deletion successful for source_id={source_id!r}")
        
    except Exception as e:
        # We don't re-raise here. If deletion fails (e.g. transient network issue), 
        # it shouldn't completely crash ingestion, just logs an error.
        logger.error(f"[delete_by_source_id] Deletion failed for source_id={source_id!r}: {e}")


def upsert_chunks(chunks: list, embeddings: list[list[float]], qdrant_client: QdrantClient) -> None:
    """
    Upsert chunk payloads and their embeddings into Qdrant Cloud.
    
    Upserts in batches of UPSERT_BATCH_SIZE (100).
    """
    try:
        if len(chunks) != len(embeddings):
            raise ValueError(f"Length mismatch: {len(chunks)} chunks vs {len(embeddings)} embeddings")
            
        logger.info(f"[upsert_chunks] Upserting {len(chunks)} points to Qdrant")
        
        for i in range(0, len(chunks), UPSERT_BATCH_SIZE):
            chunk_batch = chunks[i : i + UPSERT_BATCH_SIZE]
            embed_batch = embeddings[i : i + UPSERT_BATCH_SIZE]
            
            points = []
            for chunk, embed in zip(chunk_batch, embed_batch):
                points.append(
                    PointStruct(
                        id=chunk["chunk_id"],
                        vector=embed,
                        payload=chunk
                    )
                )
                
            qdrant_client.upsert(
                collection_name=COLLECTION_NAME,
                points=points
            )
            
        logger.info(f"[upsert_chunks] Successfully upserted {len(chunks)} points")
        
    except Exception as e:
        logger.error(f"[upsert_chunks] Failed to upsert chunks: {e}")
        raise
