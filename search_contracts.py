#!/usr/bin/env python3
"""
Contract Search Tool - Search through 585 indexed contracts using RAG
Interactive semantic search with results ranking and filtering
"""
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.vector_store import VectorStore
from agents.pre_retrieval import PreRetrievalPipeline
from agents.post_retrieval import PostRetrievalPipeline

def load_vector_store():
    """Load pre-indexed vector store"""
    store = VectorStore()
    try:
        store.load_faiss_index("vector_store/contracts.faiss")
        print("✓ Loaded indexed contracts")
        return store
    except FileNotFoundError:
        print("❌ Vector store index not found!")
        print("   Run: python main.py --index-templates")
        sys.exit(1)

def search_contracts(query, k=10, use_reranking=True):
    """Search contracts using RAG pipeline"""
    
    print("\n" + "=" * 70)
    print(f"SEARCHING: {query}")
    print("=" * 70)
    
    # Load store
    store = load_vector_store()
    
    # Pre-retrieval: expand query
    pre_processor = PreRetrievalPipeline()
    query_result = pre_processor.process_query(query, method="expansion")
    search_queries = query_result["search_queries"]
    
    print(f"\n🔍 Search variants generated ({len(search_queries)}):")
    for i, sq in enumerate(search_queries[:5], 1):
        print(f"   {i}. {sq}")
    if len(search_queries) > 5:
        print(f"   ... and {len(search_queries) - 5} more")
    
    # Vector search with all variants
    print(f"\n📊 Searching vector store...")
    all_results = []
    for sq in search_queries[:3]:  # Use top 3 variants to avoid duplicates
        results = store.search(sq, k=k)
        all_results.extend(results)
    
    # Remove duplicates and keep best score
    seen = {}
    for doc, score in all_results:
        doc_text = doc.metadata.get("source", "")
        if doc_text not in seen or score > seen[doc_text][1]:
            seen[doc_text] = (doc, score)
    
    unique_results = list(seen.values())
    unique_results.sort(key=lambda x: x[1], reverse=True)
    unique_results = unique_results[:k]
    
    print(f"✓ Found {len(unique_results)} relevant contracts")
    
    # Post-retrieval: rerank
    if use_reranking and len(unique_results) > 1:
        print(f"\n📈 Reranking results...")
        post_processor = PostRetrievalPipeline()
        unique_results = post_processor._rerank(unique_results, query)
        print(f"✓ Reranked for better relevance")
    
    # Display results
    print(f"\n{'Rank':<5} {'Score':<8} {'Contract':<50}")
    print("-" * 70)
    
    for i, (doc, score) in enumerate(unique_results, 1):
        source = doc.metadata.get("source", "Unknown")
        # Shorten long names
        if len(source) > 48:
            source = source[:45] + "..."
        print(f"{i:<5} {score:>6.3f} {source:<50}")
    
    print("\n" + "=" * 70)
    print(f"RESULTS: {len(unique_results)} contracts found")
    print("=" * 70)
    
    # Show details for top 3
    if unique_results:
        print(f"\n📋 DETAILS (Top 3):\n")
        for i, (doc, score) in enumerate(unique_results[:3], 1):
            print(f"{i}. {doc.metadata.get('source', 'Unknown')}")
            print(f"   Score: {score:.3f}")
            # Show first 100 chars of content
            content = doc.page_content[:150].replace("\n", " ")
            if len(content) > 140:
                content = content[:140] + "..."
            print(f"   Preview: {content}")
            print()

def interactive_search():
    """Run interactive search loop"""
    print("=" * 70)
    print("CONTRACT SEARCH - Interactive Mode")
    print("=" * 70)
    print("\nSearch through 585 indexed contracts with RAG")
    print("Examples:")
    print("  - договоры об аренде")
    print("  - контракты с Аманатом")
    print("  - услуги строительства")
    print("  - договоры поставки")
    print("  - доверенности")
    print("\nType 'exit' to quit, 'help' for options\n")
    
    while True:
        try:
            query = input("\n🔍 Search query: ").strip()
            
            if not query:
                continue
            
            if query.lower() == "exit":
                print("\n👋 Goodbye!")
                break
            
            if query.lower() == "help":
                print("""
Commands:
  exit          - Exit search
  help          - Show this help
  stats         - Show database statistics
  
Examples of good queries:
  - договоры об аренде (rental contracts)
  - контракты с [компанией] ([Company] contracts)
  - услуги [вид] ([Service type] services)
  - договор [тип] ([Contract type])
  - строительство (construction)
  - поставка (supply contracts)
  - доверенность (powers of attorney)
                """)
                continue
            
            if query.lower() == "stats":
                import json
                try:
                    with open("contract_analysis.json", "r", encoding="utf-8") as f:
                        stats = json.load(f)
                    print(f"""
Contract Database Statistics:
  Total: {stats['total_contracts']} contracts
  Size: {stats['total_size_mb']} MB
  Unique parties: {stats['unique_parties']}
  File types: .docx, .doc, .pdf
  
Top parties:
  {', '.join([f"{k} ({v})" for k, v in list(stats['top_parties'].items())[:5]])}
                    """)
                except FileNotFoundError:
                    print("Run 'analyze_contracts.py' first to generate statistics")
                continue
            
            # Perform search
            search_contracts(query, k=10, use_reranking=True)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            print("   Make sure to run: python main.py --index-templates")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line search
        query = " ".join(sys.argv[1:])
        search_contracts(query)
    else:
        # Interactive mode
        interactive_search()
