import re

from fastapi import APIRouter, Depends
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import verify_api_key
from src.config import get_settings
from src.database import get_db
from src.models import Chunk, Document
from src.utils.embeddings import embed_text
from src.utils.tokens import get_token_count

settings = get_settings()

router = APIRouter(dependencies=[Depends(verify_api_key)])


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(ge=1, le=15, default=10)


class Ref(BaseModel):
    reference: str
    document_name: str
    chunk_index: int
    excerpt: str


class QueryResponse(BaseModel):
    response: str
    references: list[Ref]


@router.post("/query")
async def queries(
    query: QueryRequest,
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    query_vectors = await embed_text(text=query.query, settings=settings)

    distance = Chunk.embedding.cosine_distance(query_vectors)

    stmt = (
        select(
            Chunk.id,
            # Chunk.document_id,
            Chunk.chunk_index,
            Chunk.content,
            Document.source_reference.label("document_name"),
            (1 - distance).label("similarity"),
        )
        .join(Document)
        .where(Document.status == "PROCESSED")
        .order_by(distance)
        .limit(query.top_k)
    )

    result = await db.execute(stmt)

    rows = result.mappings().all()

    context_refs: dict[str, dict] = {}
    context_string = ""
    context_string_token_count = 0
    for i, row in enumerate(rows):
        context_label = f"[Ref {i + 1}]"
        new_context = f"\n\n{context_label}\n{row.content}\n\n"
        new_token_count = get_token_count(new_context)
        if (
            context_string_token_count + new_token_count
            > settings.max_context_string_token
        ):
            break
        context_string_token_count += new_token_count

        context_refs[context_label] = {
            "document_name": row.document_name,
            "chunk_index": row.chunk_index,
            "content": row.content,
        }

        context_string += new_context

    # print(context_string)

    system_instructions = """You are a precise, evidence-based research assistant. You must base your answer ONLY on the provided context. Provide a thorough, multi-paragraph answer. Do not be concise. If the context does not contain the answer, say so.

    CRITICAL CITATION RULES:
    1. INLINE PLACEMENT: You must cite the specific Reference identifier immediately after the fact, number, or claim it supports.
    2. NO AGGREGATION: DO NOT dump or group citations at the end of a sentence or paragraph.
    3. EXACT MATCH: Use the exact identifier provided in the context (e.g., [Ref 1], [Ref 2]).
    4. PUNCTUATION: Place the citation BEFORE commas or periods.

    EXAMPLE OF BAD OUTPUT (DO NOT DO THIS):
    RAG combines a retriever and a generator to answer questions. [Ref 1][Ref 2]

    EXAMPLE OF GOOD OUTPUT (DO THIS):
    RAG combines a retriever [Ref 1] and a generator [Ref 2] to answer questions.
    """

    # 2. Define the Human input (where the untrusted chunks and user query go)
    human_template = """Contexts:
    {context}

    Question: {question}"""

    prompt = ChatPromptTemplate.from_messages(
        [("system", system_instructions), ("human", human_template)]
    )

    from langchain_core.output_parsers import StrOutputParser
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model="gpt-5-nano",
        temperature=0.5,
        max_completion_tokens=4096,
        reasoning_effort="minimal",
        api_key=settings.openai_api_key,
    )

    parser = StrOutputParser()

    basic_chain = prompt | llm | parser

    result = basic_chain.invoke({"context": context_string, "question": query.query})

    used_refs = dict.fromkeys(re.findall(r"\[Ref \d+]", result))

    refs: list[Ref] = []
    for ref_match in used_refs:
        data = context_refs.get(ref_match)
        if data:
            excerpt = data["content"][:500]
            refs.append(
                Ref(
                    reference=ref_match,
                    document_name=data["document_name"],
                    chunk_index=data["chunk_index"],
                    excerpt=excerpt,
                )
            )

    return QueryResponse(response=result, references=refs)
