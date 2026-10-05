# AskQuery Extension

A Chrome popup that sends the active webpage URL and a question to a local FastAPI/LangChain backend.

## Setup

From the project root, install dependencies into the workspace virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
```

Create `backend/.env` and set a Hugging Face token (do not commit the file):

```text
HF_TOKEN=your_hugging_face_token
```

The server also accepts `HUGGINGFACEHUB_API_TOKEN`.

## Run the backend

```sh
cd backend
../.venv/bin/python -m uvicorn server:app --reload --port 8000
```

The first start may download the sentence-transformer model. Keep the server terminal running.

## Load the Chrome extension

1. Open `chrome://extensions` and enable **Developer mode**.
2. Choose **Load unpacked** and select this project's `extension/` directory.
3. Open an HTTP/HTTPS webpage, open the extension popup, enter a question, and submit it.

The extension talks to `http://localhost:8000`. The backend only allows requests from Chrome extension origins and rejects non-HTTP(S), localhost, and literal non-public IP URLs.

# WorkFlow
[ Browser / Extension UI ] 
       │
       │ 1. POST /ask  { "url": "https://...", "question": "Who is...?" }
       ▼
[ FastAPI Server (server.py) ] ──► 2. SSRF & URL Security Check (validate_page_url)
       │
       ├─► Is URL in retriever_cache?
       │     ├── NO (First Question on Page):
       │     │     ├─► 3. Scrape HTML via LangChain WebBaseLoader
       │     │     ├─► 4. Split text into 1000-char chunks (RecursiveCharacterTextSplitter)
       │     │     ├─► 5. Convert chunks to 384-D vectors (all-MiniLM-L6-v2)
       │     │     └─► 6. Store in FAISS Vector Index & save in retriever_cache[url]
       │     │
       │     └── YES (Follow-up Question):
       │           └─► Skip scraping! Load cached FAISS index instantly from RAM
       │
       ├─► 7. Semantic Search: Embed user's question & fetch Top 4 matching chunks (k=4)
       ├─► 8. Prompt Assembly: Inject Top 4 chunks + Question into PromptTemplate
       └─► 9. LLM Inference: Qwen/Qwen2.5-7B-Instruct generates grounded answer
              │
              ▼
[ JSON Response {"answer": "..."} rendered in Extension UI ]
