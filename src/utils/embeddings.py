from typing import overload

from langchain_openai import OpenAIEmbeddings

from src.config import Settings


@overload
async def embed_text(text: str, settings: Settings) -> list[float]: ...


@overload
async def embed_text(text: list[str], settings: Settings) -> list[list[float]]: ...


async def embed_text(
    text: str | list[str],
    settings: Settings,
) -> list[float] | list[list[float]]:
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small", api_key=settings.openai_api_key
    )
    if isinstance(text, str):
        return await embeddings.aembed_query(text)
    return await embeddings.aembed_documents(text)
