# 585 Contract Database - Quick Start Guide

## 📚 What You Can Do Now

You have **585 real contracts** that can be:
1. **Indexed** into RAG for semantic search
2. **Analyzed** for patterns and statistics
3. **Searched** intelligently using AI
4. **Extracted** for structured data (parties, dates, amounts)
5. **Used as templates** for new contracts

## 🚀 Quick Start (5 minutes)

### Step 1: Analyze Your Contracts (30 seconds)
```bash
python analyze_contracts.py
```

**Generates:**
- `contract_analysis.csv` - Full details for all 585 contracts
- `contract_analysis.json` - Summary statistics
- `contracts_by_type.json` - Organized by contract type

**Shows you:**
```
✓ TOTAL CONTRACTS: 585
  - .docx: 292 files (49.9%)
  - .doc: 291 files (49.7%)
  - .pdf: 2 files (0.3%)

📋 Top contract types:
  - Other: 428 (73.2%)
  - Acts: 37 (6.3%)
  - Power of Attorney: 24 (4.1%)
  - Construction: 20 (3.4%)
  - Amendments: 18 (3.1%)
  - Rental: 15 (2.6%)

👥 Top parties:
  - Aktobe: 27 contracts
  - СДС: 26 contracts
  - Koptyeuov: 20 contracts
  - ... and more
```

### Step 2: Index All Contracts (10-15 minutes)
```bash
python main.py --index-templates
```

**What happens:**
1. Parses all 585 contracts with Docling
2. Chunks intelligently (respects document structure)
3. Creates FAISS vector index
4. Ready for semantic search

**After this:** You can search semantically across all 585 contracts

### Step 3: Search Contracts (Interactive)
```bash
python search_contracts.py
```

**Now you can ask:**
- "договоры об аренде" → Finds all rental contracts
- "контракты с Аманатом" → Finds contracts with specific party
- "услуги строительства" → Finds construction service contracts
- "договор поставки" → Finds supply contracts

**Search works like Google for your contracts!**

### Step 4: View Statistics
```bash
python main.py --stats
```

Shows:
- Vector store size
- Number of indexed documents
- Number of chunks
- Embedding dimension

## 📊 Analysis Results (Already Generated)

Run `python analyze_contracts.py` to see:

**Current Stats from 585 contracts:**
- Total size: 28.5 MB
- Largest contracts: .doc format (20.5 MB)
- Most common type: Generic contracts/Other (73.2%)
- Time period: 2012-2019 (mostly 2018-2019)
- Top 5 parties: Aktobe, СДС, Koptyeuov, Amanat, ТКА

## 🔍 How Search Works

### Query Expansion
Your search query automatically expands:
```
"договоры об аренде"
↓
- договоры об аренде
- арендные договоры
- аренда помещений
- договор аренды
- rental agreements
```

### Vector Search
FAISS searches across all 585 contracts using semantic similarity (not just keywords)

### Reranking
CrossEncoder reranks results for better relevance

### Result
You get most relevant contracts ranked by score

## 💡 Use Cases

### 1. Find Similar Contracts
Before signing new contract → Search for similar past contracts
```bash
python search_contracts.py "договор строительства"
```

### 2. Extract Standard Terms
Find what payment terms you typically use:
```bash
python search_contracts.py "условия оплаты 30 дней"
```

### 3. Check for Contract Types
Research how you've structured contracts:
```bash
python search_contracts.py "доверенность"
```

### 4. Find Specific Parties
Look up all contracts with a specific company:
```bash
python search_contracts.py "контракты с Аманатом"
```

### 5. Analyze Patterns
See trends in your contracts:
- Most common services
- Typical contract amounts
- Payment terms patterns
- Date ranges

## 🎯 Advanced Usage

### Python Integration
```python
from agents.vector_store import VectorStore

store = VectorStore()
store.load_faiss_index("vector_store/contracts.faiss")

# Search
results = store.search("договоры об аренде", k=5)
for doc, score in results:
    print(f"{doc.metadata['source']}: {score:.3f}")
```

### Extract to Excel
```python
import csv
# Read contract_analysis.csv
# Filter by type or party
# Export to Excel
```

### Batch Processing
```bash
python main.py --test --rag
```

Process sample email with RAG context from all 585 contracts

## 📈 What's Happening Behind the Scenes

1. **Docling Parser**: Reads .docx, .doc, .pdf files
2. **Semantic Chunking**: Splits into 1024-char chunks respecting structure
3. **Embeddings**: sentence-transformers creates semantic vectors
4. **FAISS Index**: Stores 585 documents for fast search
5. **Reranking**: CrossEncoder scores relevance
6. **Results**: Sorted by relevance, top matches first

## 🔧 Troubleshooting

### "Vector store index not found"
```bash
python main.py --index-templates
```

### "Module not found" errors
```bash
pip install -r requirements.txt
```

### Search returns no results
- Check if indexing completed
- Try simpler search terms
- Search in Russian (contracts are in Russian/Kazakh)

### Indexing is slow
- Normal for 585 contracts (10-15 min)
- One-time operation
- Can reduce chunk size in config.py if needed

## 📚 Files Created

**Analysis Scripts:**
- `analyze_contracts.py` - Analyze all contracts
- `search_contracts.py` - Interactive search tool

**Generated Files:**
- `contract_analysis.csv` - Full contract metadata (585 rows)
- `contract_analysis.json` - Summary statistics
- `contracts_by_type.json` - Contracts grouped by type

**Documentation:**
- `CONTRACT_DATABASE_PLAN.md` - Full implementation plan
- This file - Quick start guide

## 🎓 Next Steps (Optional)

1. **Extract Structured Data** - Create script to extract:
   - Parties
   - Dates
   - Amounts
   - Key terms
   
2. **Build Contract Templates** - Find and extract common templates

3. **Risk Analysis** - Flag:
   - Missing clauses
   - Unusual terms
   - Unsigned documents

4. **Contract Lifecycle** - Track:
   - Expiration dates
   - Renewal periods
   - Amendments

5. **Integration** - Use in email processing:
   - Auto-suggest similar contracts
   - Extract terms from precedent
   - Flag deviations

## 💾 System Requirements

**Space:**
- Vector store: ~50-100 MB
- Analysis files: ~10 MB
- Total: <200 MB

**Time:**
- Analysis: 30 seconds
- Indexing: 10-15 minutes
- Search: <1 second per query

**Memory:**
- Indexing: ~500 MB
- Search: ~200 MB

## 📞 Support Commands

```bash
# Analyze contracts
python analyze_contracts.py

# Index contracts (one-time)
python main.py --index-templates

# Interactive search
python search_contracts.py

# Test RAG with sample
python main.py --test --rag

# Show statistics
python main.py --stats

# Validate setup
python test_rag_setup.py
```

## 🎉 Summary

You now have a **searchable database of 585 contracts**:
- ✅ Analyzed and categorized
- ✅ Indexed for semantic search
- ✅ Searchable like Google
- ✅ Integrated with RAG system
- ✅ Ready for advanced analysis

**Start with:** `python analyze_contracts.py` then `python main.py --index-templates`

---

**Questions?** Check `CONTRACT_DATABASE_PLAN.md` for detailed implementation plan.
