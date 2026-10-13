"""
Atlas Vector Search (RAG Engine)
Executes sub-millisecond nearest-neighbor retrievals using MongoDB Atlas $vectorSearch.
Falls back gracefully to semantic keyword matching if vector index or Atlas cluster is offline.
"""

import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

from db import knowledge_chunks_collection
from models import KnowledgeChunk

# Fallback in-memory knowledge in case Atlas is unreachable
FALLBACK_KNOWLEDGE = [
    {
        "title": "Aanandi TechnoSoft Overview & Core Capabilities",
        "category": "capabilities",
        "content": (
            "Aanandi TechnoSoft designs, engineers, and deploys high-availability Autonomous AI Agents, "
            "multimodal sales widgets, and workflow automation. Our stack features FastAPI, LangGraph, "
            "Pipecat AI, Web Audio/WebRTC, MongoDB Atlas Vector Search, and sub-100ms TTS/STT pipelines."
        )
    },
    {
        "title": "Healthcare & Telemedicine AI Solutions",
        "category": "case_studies",
        "content": (
            "Case Study: Automated patient intake and voice triage assistant integrated with EHR systems. "
            "Achieved 99.9% uptime, reduced appointment booking friction by 74%, and handled HIPAA-compliant "
            "pre-consultation symptoms collection with real-time human agent handoff."
        )
    },
    {
        "title": "FinTech Lead Qualification & KYC Automation",
        "category": "case_studies",
        "content": (
            "Case Study: Real-time fraud detection and KYC intake bot. Provided instant BANT qualification, "
            "verified identities with automated OTP SMS/email flows, and routed high-net-worth prospects "
            "directly to certified wealth management advisors within 90 seconds."
        )
    },
    {
        "title": "Enterprise CRM & Custom Workflow Orchestration",
        "category": "case_studies",
        "content": (
            "Case Study: Bi-directional synchronization agents connecting sales chats with Salesforce, "
            "HubSpot, and Zoho CRM. Features automated calendar scheduling via Cal.com API v2 and upfront "
            "escrow/deposit commitment payments via Razorpay QR codes."
        )
    }
]

async def get_embedding(text: str) -> List[float]:
    """Generates 1536-dimensional float embedding using OpenAI or fallback."""
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key and not openai_key.startswith("sk-dummy"):
        try:
            from langchain_openai import OpenAIEmbeddings
            embedder = OpenAIEmbeddings(model="text-embedding-3-small", api_key=openai_key)
            return await embedder.aembed_query(text)
        except Exception as e:
            print(f"[RAG NOTICE] OpenAI embedding error: {e}")
    # Return 1536-dim zero vector if offline
    return [0.0] * 1536

async def vector_search_knowledge(
    query_text: str,
    limit: int = 3,
    num_candidates: int = 50,
    category_filter: Optional[str] = None
) -> str:
    """
    Executes $vectorSearch against knowledge_chunks in MongoDB Atlas.
    Formats top results for the LangGraph sales agent context.
    """
    try:
        query_vector = await get_embedding(query_text)
        
        # Only run true $vectorSearch if we have a non-zero embedding
        if any(v != 0.0 for v in query_vector[:10]):
            pipeline: List[Dict[str, Any]] = [
                {
                    "$vectorSearch": {
                        "index": "vector_index",
                        "path": "embedding",
                        "queryVector": query_vector,
                        "numCandidates": num_candidates,
                        "limit": limit
                    }
                }
            ]
            if category_filter:
                pipeline[0]["$vectorSearch"]["filter"] = {"category": category_filter}
                
            pipeline.append({
                "$project": {
                    "_id": 0,
                    "title": 1,
                    "content": 1,
                    "category": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            })

            cursor = knowledge_chunks_collection.aggregate(pipeline)
            results = await cursor.to_list(length=limit)
            if results:
                formatted = []
                for doc in results:
                    score = doc.get("score", 0.0)
                    formatted.append(f"### {doc.get('title')} (Relevance: {score:.2f})\n{doc.get('content')}")
                return "\n\n".join(formatted)

    except Exception as e:
        print(f"[RAG NOTICE] MongoDB Atlas $vectorSearch query bypassed ({e}), using semantic fallback.")

    # Semantic Keyword Fallback
    q_lower = query_text.lower()
    matches = []
    for item in FALLBACK_KNOWLEDGE:
        title = item["title"].lower()
        content = item["content"].lower()
        if any(word in title or word in content for word in q_lower.split() if len(word) > 3):
            matches.append(f"### {item['title']}\n{item['content']}")

    if matches:
        return "\n\n".join(matches[:limit])

    # Default overview
    return (
        "### Aanandi TechnoSoft Overview & Core Capabilities\n"
        "Aanandi TechnoSoft designs, engineers, and deploys high-availability Autonomous AI Agents, "
        "multimodal sales widgets, and workflow automation. Stack features FastAPI, LangGraph, "
        "Pipecat AI, Web Audio/WebRTC, MongoDB Atlas Vector Search, and sub-100ms TTS/STT pipelines."
    )
