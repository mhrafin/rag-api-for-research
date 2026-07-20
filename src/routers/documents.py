import os
import shutil
import uuid

import tiktoken
from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, logger
from fastapi.responses import Response
from kreuzberg import ExtractionConfig, extract_file
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
)
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import verify_api_key
from src.config import get_settings
from src.database import get_db
from src.models import Chunk, Document

settings = get_settings()

router = APIRouter(dependencies=[Depends(verify_api_key)])


class DocumentResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    id: int
    source_type: str
    source_reference: str
    status: str


@router.post("/documents", response_model=DocumentResponse)
async def documents(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Currently only focusing on file, Later I will integrate URL that return accurate media type.
    # if file and url:
    #     return Response(
    #         status_code=400, content="Either upload a valid format file or an url."
    #     )

    # print(file.content_type)

    MAX_FILE_SIZE = 50 * 1024 * 1024

    if file.size and file.size > MAX_FILE_SIZE:
        return Response(status_code=413, content="File too large")

    if not is_file_valid_format(file_content_type=file.content_type):
        return Response(
            status_code=415,
            content="Unsupported file format. Supported formats are: pdf, md, and txt.",
        )

    os.makedirs(settings.temp_dir, exist_ok=True)

    # To stop traversal attacks
    file_path = (
        settings.temp_dir + str(uuid.uuid4()) + "." + file.content_type.split("/")[-1]
    )

    # We need to save the file. Background tasks can't continue with the file from UploadFile when the request life-cycle ends, because UploadFile is temporary.
    with open(f"{file_path}", "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    new_doc = Document(
        source_type="FILE",
        source_reference=file.filename,
        status="QUEUED",
    )

    db.add(new_doc)
    await db.commit()
    await db.refresh(new_doc)

    background_tasks.add_task(
        embedding_pipeline, file_path=file_path, doc_id=new_doc.id
    )
    return new_doc


def is_file_valid_format(file_content_type: str):
    valid_formats = ["application/pdf", "text/plain", "text/markdown"]

    if file_content_type not in valid_formats:
        print("Invalid")
        return False

    print("valid")
    return True


async def embedding_pipeline(file_path: str, doc_id: int):
    FILE_PATH = file_path

    from src.database import AsyncSession

    db = AsyncSession()

    stmt = (
        select(Document)
        .where(Document.id == doc_id)
        .options(selectinload(Document.chunks))
    )
    doc = await db.scalar(stmt)

    content = await extract_content(file_path=FILE_PATH)

    doc.content = content

    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", chunk_size=500, chunk_overlap=50
    )

    splitted_chunks = text_splitter.split_text(content)

    # print(chunks[0])
    # print(chunks[1])

    # We need this so that we can find the token count of a given text, It the same thing we used for splitting.
    encoding = tiktoken.get_encoding("cl100k_base")

    doc_total_token = 0

    try:
        for index, chunk in enumerate(splitted_chunks):
            token_count = len(encoding.encode(chunk))
            doc_total_token += token_count
            new_chunk = Chunk(
                document_id=doc.id,
                chunk_uuid=uuid.uuid4(),
                chunk_index=index + 1,
                content=chunk,
                token_count=token_count,
            )

            db.add(new_chunk)

        doc.total_token = doc_total_token

        # Add estimated cost of the total operation
        current_est_cost_doc = 0.0 if doc.estimated_cost is None else doc.estimated_cost
        new_est_cost_doc = (
            (settings.cost_per_million / 1000000) * doc_total_token
        ) + current_est_cost_doc
        doc.estimated_cost = new_est_cost_doc

        doc.status = "CHUNKED"

        # db commit outside of the loop
        await db.commit()
        await db.refresh(doc)

        # Embedding starts from here
        chunks = [c for c in doc.chunks if c.embedding is None]

        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small", api_key=settings.openai_api_key
        )
        chunk_contents = []
        vectors = []

        for i, chunk in enumerate(chunks):
            chunk_contents.append(chunk.content)

        vectors = embeddings.embed_documents(chunk_contents)

        for vector, chunk in zip(vectors, chunks):
            chunk.embedding = vector

        doc.status = "PROCESSED"
        await db.commit()
    except Exception:
        await db.rollback()
        doc.status = "FAILED"
        await db.commit()
        raise
    finally:
        await db.aclose()
        os.remove(file_path)


async def extract_content(file_path: str):
    try:
        config = ExtractionConfig()
        result = await extract_file(file_path, config=config)
        return result.content
    except Exception as e:
        logger.error("extract_content failed for %s: %s", file_path, e)
        raise
