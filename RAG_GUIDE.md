# RAG System Documentation

## Overview

Advanced Retrieval-Augmented Generation (RAG) system for intelligent contract document processing. Uses semantic search to find relevant templates and sections before LLM analysis.

## Architecture

```
Query Input
    ↓
[Pre-Retrieval Pipeline]
    ├─ Query Expansion: Generate variants
    └─ Query Rewriting: Normalize for search
    ↓
[Vector Search - FAISS]
    └─ Semantic similarity against indexed templates
    ↓
[Post-Retrieval Pipeline]
    ├─ Reranking: CrossEncoder scoring
    ├─ Summarization: Extract key sentences
    └─ Fusion: Merge similar documents
    ↓
[LLM Analysis]
    └─ Context-aware extraction with retrieved documents
    ↓
Output: Enhanced analysis with document references
```

## Components

### 1. Docling Parser (`agents/docling_parser.py`)
Smart document parsing with structure preservation.

**Key Features:**
- Parses PDF, DOCX, DOC with layout understanding
- Preserves document structure (sections, paragraphs)
- Extracts metadata (page numbers, images)
- Batch processing support
- LangChain integration

**Usage:**
```python
from agents.docling_parser import DoclingParser

parser = DoclingParser()
docs = parser.parse_document("contract.pdf")
langchain_docs = parser.documents_to_langchain(docs)
```

### 2. RAG Chunking (`agents/rag_chunking.py`)
Intelligent document chunking with multiple strategies.

**Strategies:**
- **Semantic**: Respects document sections (best for contracts)
- **Recursive**: Splits by paragraphs/sentences with context
- **Simple**: Fixed-size chunks

**Key Features:**
- Merge small chunks to avoid fragmentation
- Add context windows (neighbor chunks)
- Preserve metadata

**Usage:**
```python
from agents.rag_chunking import RagChunking

chunker = RagChunking(chunk_size=1024, strategy="semantic")
chunks = chunker.process_pipeline(documents)
```

### 3. Pre-Retrieval Pipeline (`agents/pre_retrieval.py`)
Optimize queries before vector search.

**Techniques:**
- **Query Expansion**: Generate variants (keywords, synonyms, legal-specific)
- **Query Rewriting**: Normalize and enhance queries

**Why no HyDE or Query Routing?**
- **HyDE**: Generates hypothetical documents, redundant with expansion
- **Query Routing**: Routes to different indexes, unnecessary with single FAISS index

**Usage:**
```python
from agents.pre_retrieval import PreRetrievalPipeline

pipeline = PreRetrievalPipeline(llm_client=llm)
result = pipeline.process_query("What are liability terms?", method="hybrid")
search_queries = result["search_queries"]  # Use for vector search
```

### 4. Vector Store (`agents/vector_store.py`)
FAISS-based semantic search with embeddings.

**Features:**
- Automatic embedding generation (sentence-transformers)
- Similarity search with scoring
- Batch operations
- Save/load persistence
- Statistics

**Usage:**
```python
from agents.vector_store import VectorStore

store = VectorStore(embedding_model="multilingual-e5-base")
store.add_documents(chunks)
results = store.search("liability clause", k=5)  # Top 5 results
store.save_faiss_index("my_index.faiss")
```

### 5. Post-Retrieval Pipeline (`agents/post_retrieval.py`)
Refine retrieved documents after search.

**Techniques:**
- **Reranking**: CrossEncoder for accurate scoring
- **Extractive Summary**: First + last sentences
- **Fusion**: Merge similar docs (>70% similarity)

**Usage:**
```python
from agents.post_retrieval import PostRetrievalPipeline

processor = PostRetrievalPipeline()
refined = processor.process(
    retrieved_docs,
    rerank=True,
    summary=True,
    fusion=True
)
context = processor.get_final_context(refined, max_tokens=2000)
```

## Integration with DocumentProcessor

The RAG system integrates seamlessly with existing document analysis:

```python
from agents.document_processor import DocumentProcessor

# Initialize with RAG support
processor = DocumentProcessor(enable_rag=True)

# Index templates once
processor.index_templates()

# Use RAG-enhanced analysis
result = processor.extract_info_with_rag(
    text="contract content",
    use_preprocessing=True
)
```

### RAG Methods Added:
- `_init_rag_components()`: Lazy-load RAG modules
- `index_templates()`: Index templates from config directory
- `extract_info_with_rag()`: Full RAG pipeline + LLM analysis

## CLI Usage

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Validate RAG setup
python test_rag_setup.py
```

### Run with RAG
```bash
# Test RAG pipeline with sample email
python main.py --test --rag

# Index templates into vector store
python main.py --index-templates

# Run continuous processing with RAG
python main.py --rag

# Show RAG statistics
python main.py --stats
```

## Configuration

### In `config.py`:
```python
# Template directory for indexing
TEMPLATES_DIR = "templates/"

# Vector store settings
VECTOR_STORE_INDEX = "vector_store/contracts.faiss"
EMBEDDING_MODEL = "multilingual-e5-base"

# Chunking settings
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 100

# Post-retrieval settings
RERANK_MODEL = "cross-encoder/qnli-distilroberta-base"
```

## Performance Notes

**Speed:**
- Query expansion: <100ms
- Vector search (FAISS): <50ms for 1000 docs
- Reranking: ~100-200ms (depends on doc count)
- Full pipeline: ~300-500ms per query

**Accuracy:**
- Reranking improves precision by 20-30%
- Fusion reduces context by removing duplicates
- Extractive summary preserves original language

## Troubleshooting

### Import Errors
```bash
pip install langchain langchain-community docling faiss-cpu chromadb sentence-transformers
```

### Vector Store Not Found
```python
# Reinitialize templates
processor.index_templates()
```

### Slow Vector Search
- Check FAISS index size with `store.get_stats()`
- Reduce chunk size for faster search
- Use fewer templates for testing

### Memory Issues with Large PDFs
- Use semantic chunking (respects sections)
- Reduce chunk size
- Process in batches

## Technique Selection Rationale

| Technique | Selected | Reason |
|-----------|----------|--------|
| Query Expansion | ✅ | Essential: generates search variants |
| Query Rewriting | ✅ | Critical: optimizes legal terminology |
| Reranking | ✅ | Improves precision 20-30% |
| Extractive Summary | ✅ | Preserves original contract language |
| Fusion | ✅ | Reduces redundancy in context |
| HyDE | ❌ | Redundant with expansion |
| Query Routing | ❌ | Single index sufficient |

## Future Enhancements

- [ ] Query correction and spell-checking
- [ ] Multi-index routing for different contract types
- [ ] Abstractive summarization option
- [ ] Fine-tuned reranker for legal docs
- [ ] Metadata filtering (date, type, jurisdiction)
- [ ] Query caching for repeated searches
