#!/usr/bin/env python3
"""
Simple standalone script to scan WhatsApp for documents.
Uses the working async code from demo_whatsapp_playwright.py
Outputs results to JSON file.

Usage: python -m whatsapp.run_scan --output results.json --chats 10 --docs 50
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
import sys
# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


async def scan_whatsapp(
    session_dir: str = '.whatsapp_session_playwright',
    downloads_dir: str = 'whatsapp_downloads',
    chat_limit: int = 10,
    doc_limit: int = 50,
    timeout: int = 120
) -> list:
    """Scan WhatsApp for documents using the working async pipeline."""

    from whatsapp import WhatsAppPipeline
    pipeline = WhatsAppPipeline(
        session_dir=session_dir,
        downloads_dir=downloads_dir,
        headless=False
    )

    documents = []

    try:
        logger.info("Connecting to WhatsApp...")

        if not await pipeline.connect(timeout=timeout):
            logger.error("Failed to connect to WhatsApp")
            return []

        logger.info("Connected! Scanning for documents...")

        # Set progress callback
        pipeline.on_chat_processed = lambda name, count: logger.info(f"Chat: {name} - {count} docs")
        pipeline.on_document_found = lambda msg: logger.info(f"Found: {msg.document_name}")

        doc_count = 0
        async for doc in pipeline.extract_documents(
            chat_limit=chat_limit,
            scroll_history=True,
            contracts_only=False  # Get all documents
        ):
            doc_count += 1
            if doc_count > doc_limit:
                break

            documents.append({
                'id': doc.id,
                'filename': doc.filename,
                'file_path': doc.file_path,
                'sender': doc.sender,
                'chat_name': doc.subject,
                'text': doc.text[:5000] if doc.text else None,
                'is_contract': doc.is_contract,
                'received_at': doc.received_at.isoformat() if doc.received_at else None,
                'metadata': doc.metadata
            })

            logger.info(f"[{doc_count}] {doc.filename} from {doc.subject}")

        logger.info(f"Scan complete: {len(documents)} documents found")

    except Exception as e:
        logger.error(f"Error during scan: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await pipeline.disconnect()

    return documents


def main():
    parser = argparse.ArgumentParser(description='Scan WhatsApp for documents')
    parser.add_argument('--output', '-o', default='whatsapp_scan_results.json',
                       help='Output JSON file')
    parser.add_argument('--chats', '-c', type=int, default=10,
                       help='Number of chats to scan')
    parser.add_argument('--docs', '-d', type=int, default=50,
                       help='Maximum documents to extract')
    parser.add_argument('--timeout', '-t', type=int, default=120,
                       help='Login timeout in seconds')
    parser.add_argument('--session', '-s', default='.whatsapp_session_playwright',
                       help='Session directory')
    parser.add_argument('--downloads', default='whatsapp_downloads',
                       help='Downloads directory')

    args = parser.parse_args()

    logger.info(f"Starting WhatsApp scan: {args.chats} chats, max {args.docs} docs")

    # Run async scan
    documents = asyncio.run(scan_whatsapp(
        session_dir=args.session,
        downloads_dir=args.downloads,
        chat_limit=args.chats,
        doc_limit=args.docs,
        timeout=args.timeout
    ))

    # Save results
    output_path = Path(args.output)
    result = {
        'status': 'complete',
        'timestamp': datetime.now().isoformat(),
        'documents': documents,
        'count': len(documents)
    }

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info(f"Results saved to {output_path}")

    return len(documents)


if __name__ == '__main__':
    sys.exit(0 if main() > 0 else 1)
