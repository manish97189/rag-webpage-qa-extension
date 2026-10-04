import os
import ipaddress
import logging
from pathlib import Path
from urllib.parse import urlsplit

os.environ.setdefault("USER_AGENT", "AskQueryExtension/1.0")

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace, HuggingFaceEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).with_name(".env"))

hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
if not hf_token:
    raise RuntimeError("Set HF_TOKEN or HUGGINGFACEHUB_API_TOKEN in your .env file.")

app = FastAPI()

# Allow the Chrome Extension to call our local FastAPI server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

# Initialize LLM & Embeddings once at startup
llm = HuggingFaceEndpoint(
    repo_id="Qwen/Qwen2.5-7B-Instruct",
    task="text-generation",
    provider="featherless-ai",
    huggingfacehub_api_token=hf_token,
)
model = ChatHuggingFace(llm=llm)
parser = StrOutputParser()
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

prompt = PromptTemplate(
    template=(
        "Answer the following question based ONLY on the given context.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}"
    ),
    input_variables=["question", "context"],
)

chain = prompt | model | parser

# Cache retrievers by URL so we don't re-run WebBaseLoader on every question
retriever_cache = {}

class QueryRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    question: str = Field(min_length=1, max_length=4000)


def validate_page_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        _ = parsed.port  # Validate that an explicitly supplied port is in range.
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="URL is malformed.") from exc

    if parsed.scheme not in {"http", "https"} or not hostname:
        raise HTTPException(status_code=400, detail="URL must use http or https.")
    if parsed.username is not None or parsed.password is not None:
        raise HTTPException(status_code=400, detail="URLs containing credentials are not supported.")

    normalized_host = hostname.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith((".localhost", ".local")):
        raise HTTPException(status_code=400, detail="Local network URLs are not supported.")

    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        return
    if not address.is_global:
        raise HTTPException(status_code=400, detail="Private or reserved IP addresses are not supported.")

def get_context_for_url(url: str, question: str) -> str:
    if url not in retriever_cache:
        loader = WebBaseLoader(url, requests_kwargs={"timeout": 15})
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        chunks = splitter.split_documents(docs)

        vectorstore = FAISS.from_documents(chunks, embeddings)
        retriever_cache[url] = vectorstore.as_retriever(search_kwargs={"k": 4})

    retriever = retriever_cache[url]
    relevant_docs = retriever.invoke(question)
    return "\n\n".join(doc.page_content for doc in relevant_docs)

def answer_question(url: str, question: str) -> str:
    context = get_context_for_url(url, question)
    if not context.strip():
        raise HTTPException(status_code=422, detail="No readable page content was found.")
    return chain.invoke({"question": question, "context": context})


@app.post("/ask")
async def ask_question(req: QueryRequest):
    validate_page_url(req.url)
    try:
        result = await run_in_threadpool(answer_question, req.url, req.question)
        return {"answer": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to answer a page question")
        raise HTTPException(status_code=500, detail="Unable to answer the question right now.") from e