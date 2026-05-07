"""
rag_query.py — RAG retrieval and generation pipeline.
"""

import logging

from store.qdrant_store import COLLECTION_NAME, EMBEDDING_MODEL

logger = logging.getLogger(__name__)

SEARCH_TOP_K = 15
ANSWER_MODEL = "gpt-4o"

SYSTEM_PROMPT = """
You are a document assistant with access to file metadata.
Answer questions using only the provided document context below.

Each context block contains a header with metadata:
- File: the filename
- Source: "drive" (Google Drive) or "dropbox" (Dropbox)
- Path: the full path of the file in Drive or Dropbox
- Folder: the parent folder the file is stored in
- Page: the page number or sheet name
- Owner: the email of the file owner
- Modified: when the file was last modified

Rules:
- If asked which storage service (Drive or Dropbox) → use Source field
- If asked about file location or folder → use Path and Folder fields
- If asked about file ownership → use Owner field
- If asked about modification date → use Modified field
- Always cite the filename and page/sheet when relevant
- If the answer cannot be found in the context, say so clearly
- Do not hallucinate any information not present in the context
"""


def build_context_string(payloads: list[dict]) -> str:
    """
    Format retrieved chunk payloads into a context string for GPT-4o.
    Includes ALL metadata fields so location, source type, ownership,
    and date questions can be answered from any matching chunk.
    """
    formatted_chunks = []
    
    for chunk in payloads:
        filename = chunk.get("filename") or "Unknown File"
        source_type = chunk.get("source_type") or "unknown"
        file_path = chunk.get("file_path") or "not available"
        parent_folder = chunk.get("parent_folder") or "not available"
        page = chunk.get("page_or_sheet") or "unknown"
        owner_email = chunk.get("owner_email") or "not available"
        modified_at = chunk.get("modified_at") or "not available"
        content = chunk.get("content", "")
        
        chunk_str = f"[File: {filename} | Source: {source_type} | Path: {file_path} | Folder: {parent_folder} | Page: {page} | Owner: {owner_email} | Modified: {modified_at}]\n{content}"
        formatted_chunks.append(chunk_str)
        
    return "\n\n---\n\n".join(formatted_chunks)


def run_query(question: str, openai_client, qdrant_client) -> dict:
    """
    Execute the full RAG query pipeline.

    Returns
    -------
    dict
        A dictionary containing "answer" (str), "sources" (list[dict]),
        and "retrieved_contexts" (list[str]) — one string per chunk.
    """
    try:
        logger.info(f"[run_query] Processing question (len={len(question)})")
        
        # 1. Embed the question
        response = openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[question]
        )
        query_vector = response.data[0].embedding
        
        # 2. Search Qdrant
        search_results = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=SEARCH_TOP_K,
            with_payload=True
        )
        
        # 3. Extract payloads
        payloads = [hit.payload for hit in search_results.points if hit.payload]
        
        # 4. Build context
        context = build_context_string(payloads)
        
        # 5. Call GPT-4o
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}
        ]
        
        chat_response = openai_client.chat.completions.create(
            model=ANSWER_MODEL,
            messages=messages,
            temperature=0.0
        )
        answer = chat_response.choices[0].message.content or ""
        
        # 6. Build sources list
        sources = []
        # Keep track of chunk_ids to avoid duplicate sources if same chunk is somehow returned multiple times
        seen_chunk_ids = set() 
        for chunk in payloads:
            chunk_id = chunk.get("chunk_id")
            if chunk_id in seen_chunk_ids:
                continue
                
            seen_chunk_ids.add(chunk_id)
            sources.append({
                "chunk_id": chunk_id,
                "filename": chunk.get("filename"),
                "page_or_sheet": chunk.get("page_or_sheet"),
                "file_path": chunk.get("file_path"),
                "web_url": chunk.get("web_url")
            })

        # Build retrieved_contexts: actual text content of every retrieved chunk.
        # Required for RAGAS context_precision, context_recall, and faithfulness metrics.
        retrieved_contexts = [
            chunk.get("content", "")
            for chunk in payloads
            if chunk.get("content", "").strip()
        ]

        logger.info(
            f"[run_query] Generated answer (len={len(answer)}) "
            f"with {len(sources)} sources, "
            f"{len(retrieved_contexts)} context chunks"
        )

        return {
            "answer":             answer,
            "sources":            sources,
            "retrieved_contexts": retrieved_contexts,
        }
        
    except Exception as e:
        logger.error(f"[run_query] Query failed: {e}")
        raise
