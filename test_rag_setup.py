#!/usr/bin/env python3
"""
Quick test to verify RAG system is properly integrated
"""
import sys
from pathlib import Path

def test_rag_modules():
    """Test RAG module structure and integration points"""
    
    print("=" * 60)
    print("RAG SYSTEM VALIDATION")
    print("=" * 60)
    
    # Test 1: Check all RAG modules exist
    print("\n1. Checking RAG module files...")
    rag_modules = [
        "agents/docling_parser.py",
        "agents/rag_chunking.py",
        "agents/pre_retrieval.py",
        "agents/vector_store.py",
        "agents/post_retrieval.py",
    ]
    
    for module in rag_modules:
        path = Path(module)
        if path.exists():
            size = path.stat().st_size
            print(f"   ✓ {module:<40} ({size:>6} bytes)")
        else:
            print(f"   ✗ {module:<40} NOT FOUND")
            return False
    
    # Test 2: Check DocumentProcessor has RAG methods
    print("\n2. Checking DocumentProcessor RAG integration...")
    with open("agents/document_processor.py", "r", encoding="utf-8") as f:
        content = f.read()
        
    rag_methods = [
        "_init_rag_components",
        "index_templates",
        "extract_info_with_rag"
    ]
    
    for method in rag_methods:
        if f"def {method}" in content:
            print(f"   ✓ {method}() implemented")
        else:
            print(f"   ✗ {method}() NOT FOUND")
            return False
    
    # Test 3: Check main.py has RAG support
    print("\n3. Checking main.py RAG integration...")
    with open("main.py", "r", encoding="utf-8") as f:
        main_content = f.read()
    
    main_checks = [
        ("enable_rag parameter", "enable_rag"),
        ("--rag CLI flag", "--rag"),
        ("_index_templates method", "def _index_templates"),
        ("use_rag parameter in process_test_email", "use_rag"),
    ]
    
    for check_name, check_str in main_checks:
        if check_str in main_content:
            print(f"   ✓ {check_name}")
        else:
            print(f"   ✗ {check_name} NOT FOUND")
            return False
    
    # Test 4: Check requirements.txt
    print("\n4. Checking RAG dependencies in requirements.txt...")
    with open("requirements.txt", "r", encoding="utf-8") as f:
        reqs = f.read()
    
    required_packages = [
        "langchain",
        "docling",
        "faiss",
        "chromadb",
        "sentence-transformers",
    ]
    
    for pkg in required_packages:
        if pkg.lower() in reqs.lower():
            print(f"   ✓ {pkg}")
        else:
            print(f"   ✗ {pkg} NOT IN requirements.txt")
            return False
    
    # Test 5: Verify technique selection (NO HyDE or Query Routing)
    print("\n5. Verifying correct technique selection...")
    
    pre_ret_file = "agents/pre_retrieval.py"
    with open(pre_ret_file, "r", encoding="utf-8") as f:
        pre_ret = f.read()
    
    # Check what's implemented
    techniques_implemented = {
        "Query Expansion": "_query_expansion" in pre_ret,
        "Query Rewriting": "_query_rewriting" in pre_ret,
    }
    
    techniques_excluded = {
        "HyDE": "hyde" in pre_ret.lower(),
        "Query Routing": "routing" in pre_ret.lower(),
    }
    
    print("   Implemented:")
    for tech, found in techniques_implemented.items():
        status = "✓" if found else "✗"
        print(f"      {status} {tech}")
    
    print("   Excluded:")
    for tech, found in techniques_excluded.items():
        status = "✓" if not found else "✗ (STILL PRESENT!)"
        print(f"      {status} {tech}")
        if found:
            return False
    
    print("\n" + "=" * 60)
    print("✓ RAG SYSTEM READY")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Install dependencies: pip install -r requirements.txt")
    print("  2. Run with RAG: python main.py --test --rag")
    print("  3. Index templates: python main.py --index-templates")
    return True

if __name__ == "__main__":
    success = test_rag_modules()
    sys.exit(0 if success else 1)
