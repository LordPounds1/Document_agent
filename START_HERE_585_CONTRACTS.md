# 585 Contracts - Getting Started Now

## 📊 Your Database

**Just Added:** 585 real contracts to `templates/` folder
- 292 .docx files
- 291 .doc files  
- 2 .pdf files
- Total: 28.5 MB
- Date range: 2012-2019

**Contract Types Found:**
- Generic/Other: 428 (73.2%)
- Acts: 37
- Powers of Attorney: 24
- Construction: 20
- Amendments: 18
- Rental: 15
- Letters: 14
- Services: 13
- Purchase/Supply: 9
- Orders: 7

**Key Parties:**
- Aktobe (27 contracts)
- СДС (26 contracts)
- Koptyeuov (20 contracts)
- Amanat (14 contracts)
- ТКА (13 contracts)
- And 2+ more major parties

## 🚀 Do This Now (3 Simple Steps)

### Step 1: Understand What You Have (30 seconds)
```bash
python analyze_contracts.py
```
Shows statistics, generates CSV with all contract details.

### Step 2: Index for Search (10-15 minutes)
```bash
python main.py --index-templates
```
Makes all 585 contracts searchable using AI. Run once, then use forever.

### Step 3: Search Interactively (Instant)
```bash
python search_contracts.py
```
Try these searches:
- `договоры об аренде` - Find all rental contracts
- `контракты с Аманатом` - Find contracts with Amanat
- `строительство` - Find construction contracts
- `услуги` - Find service contracts
- `доверенность` - Find powers of attorney

## 💡 What This Enables

### Before (Manual):
❌ Flip through 585 documents manually
❌ Use Ctrl+F for text search only
❌ Can't find contracts by meaning
❌ Have to read each one to understand

### After (Smart RAG):
✅ Semantic search across all 585
✅ Find by meaning, not just keywords
✅ Get relevant contracts ranked by score
✅ <1 second per search

## 🎯 5 Key Use Cases

1. **Before Signing New Contract:**
   ```bash
   python search_contracts.py "договор строительства"
   ```
   See similar past contracts, copy proven terms

2. **Extract Standard Terms:**
   ```bash
   python search_contracts.py "условия оплаты"
   ```
   Understand your typical payment terms

3. **Find All Contracts with Company:**
   ```bash
   python search_contracts.py "контракты с СДС"
   ```
   See all deals with specific party

4. **Analyze Patterns:**
   - See most common contract types
   - Identify key service providers
   - Track payment term patterns
   - Find outdated templates

5. **Email Processing:**
   ```bash
   python main.py --test --rag
   ```
   New contract arrives → System finds 5 similar past contracts → Shows what terms you typically use

## 📁 Files Generated

After running `python analyze_contracts.py`:

1. **contract_analysis.csv** - Excel-ready file
   - All 585 contracts with metadata
   - Party names, years, types
   - Easy to sort/filter in Excel

2. **contract_analysis.json** - Program-friendly data
   - Statistics in machine-readable format
   - Can use for further analysis

3. **contracts_by_type.json** - Organized by type
   - All rental contracts together
   - All construction contracts together
   - All amendments together
   - Etc.

## 🔍 Search Examples

```bash
# Rental contracts
python search_contracts.py "аренда помещения"

# Construction work
python search_contracts.py "строительные работы"

# Service agreements
python search_contracts.py "оказание услуг"

# Specific company
python search_contracts.py "ТОО СДС 2012"

# Specific person
python search_contracts.py "Махатов"

# Contract amounts
python search_contracts.py "договор на сумму"

# Power of attorney
python search_contracts.py "доверенность"
```

## ⏱️ Time Required

1. Analysis: 30 seconds
2. Indexing: 10-15 minutes (one-time)
3. Search: <1 second per query
4. Total setup: ~15 minutes

## 💾 Disk Space

- Vector index: ~50-100 MB
- Analysis files: ~10 MB
- Total: <200 MB (minimal impact)

## ✅ Verification

To verify everything is set up:
```bash
python test_rag_setup.py
```

Should show:
- ✓ All RAG modules ready
- ✓ DocumentProcessor integration OK
- ✓ main.py integration OK
- ✓ Dependencies listed
- ✓ Technique selection verified

## 🎓 Learning from Your Contracts

Your 585 contracts are valuable data:

1. **Templates**: Find most common structures
2. **Language**: See typical contract language
3. **Terms**: Learn standard payment/delivery terms
4. **Parties**: Identify key business partners
5. **Risk**: Spot problematic contract patterns

## 🚨 Important Notes

- **One-time Indexing**: `python main.py --index-templates` only needs to run once
- **Add New Contracts**: Put new files in `templates/`, run indexing again
- **Search in Russian**: Contracts are mostly in Russian, search in Russian for best results
- **Reranking**: Uses CrossEncoder for accurate relevance scoring

## 📈 Next Steps (Optional)

1. Extract structured data (parties, dates, amounts)
2. Build risk detection (missing clauses, unusual terms)
3. Create contract amendment tracker
4. Integrate with email alerts for expiring contracts
5. Build contract recommendations for new deals

## 🎯 Recommended Order

**Right Now:**
1. `python analyze_contracts.py` ← Start here (30 sec)
2. `python main.py --index-templates` ← Then do this (15 min)
3. `python search_contracts.py` ← Then try searching (instant)

**Then Try:**
1. `python main.py --test --rag` ← Test RAG pipeline
2. `python main.py --stats` ← See vector store stats
3. Look at `contract_analysis.csv` in Excel

**Advanced:**
- Modify search_contracts.py to export results
- Create contract risk analyzer
- Build amendment tracking system
- Integrate with your email system

## 📞 Quick Commands Reference

```bash
# Analyze database
python analyze_contracts.py

# Index all contracts (one-time)
python main.py --index-templates

# Interactive search
python search_contracts.py

# Search from command line
python search_contracts.py "договоры об аренде"

# Test RAG system
python main.py --test --rag

# Show statistics
python main.py --stats

# Validate setup
python test_rag_setup.py
```

## ✨ Summary

You have **585 real contracts** that are now:
- ✅ Analyzed (see stats in contract_analysis.csv)
- ✅ Categorized (by type, party, year)
- ✅ Ready to index (run 1 command)
- ✅ Ready to search (like Google for contracts!)
- ✅ Ready to use for learning patterns

**Start now:** `python analyze_contracts.py`

---

For detailed information, see:
- `CONTRACT_SEARCH_GUIDE.md` - How to use search
- `CONTRACT_DATABASE_PLAN.md` - Full feature roadmap
- `RAG_GUIDE.md` - How RAG system works
