#!/usr/bin/env python3
"""
WhatsApp Monitor Worker - runs in separate subprocess.
Monitors WhatsApp for new documents and saves results to JSON file.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


async def monitor_whatsapp(
    session_dir: str,
    downloads_dir: str,
    results_file: str,
    chat_limit: int,
    check_interval: int,
    timeout: int
):
    """Run WhatsApp monitoring loop."""

    from whatsapp import WhatsAppPipeline
    results_path = Path(results_file)
    processed_files = set()

    # Load already processed files
    if results_path.exists():
        try:
            data = json.loads(results_path.read_text(encoding='utf-8'))
            for doc in data.get('documents', []):
                if doc.get('file_path'):
                    processed_files.add(doc['file_path'])
            logger.info(f"Loaded {len(processed_files)} previously processed files")
        except Exception as e:
            logger.debug(f'Failed to load processed files: {e}')

    pipeline = WhatsAppPipeline(
        session_dir=session_dir,
        downloads_dir=downloads_dir,
        headless=False
    )

    documents: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        'status': 'connecting',
        'checks': 0,
        'last_check': None,
        'errors': 0
    }

    def save_results():
        """Save current results to file."""
        results_path.write_text(json.dumps({
            'status': stats['status'],
            'stats': stats,
            'documents': documents,
            'count': len(documents),
            'timestamp': datetime.now().isoformat()
        }, ensure_ascii=False, indent=2), encoding='utf-8')

    try:
        logger.info("Connecting to WhatsApp...")
        stats['status'] = 'connecting'
        save_results()

        if not await pipeline.connect(timeout=timeout):
            logger.error("Failed to connect to WhatsApp")
            stats['status'] = 'error'
            stats['error'] = 'Failed to connect'
            save_results()
            return

        logger.info("Connected! Starting monitoring...")
        stats['status'] = 'monitoring'
        save_results()

        # Main monitoring loop
        while True:
            try:
                stats['checks'] += 1
                stats['last_check'] = datetime.now().isoformat()
                logger.info(f"Check #{stats['checks']} - scanning {chat_limit} chats...")

                new_docs = 0
                async for doc in pipeline.extract_documents(
                    chat_limit=chat_limit,
                    scroll_history=False,
                    contracts_only=False
                ):
                    # Skip already processed
                    if doc.file_path and doc.file_path in processed_files:
                        continue

                    new_docs += 1
                    if doc.file_path:
                        processed_files.add(doc.file_path)

                    documents.append({
                        'id': doc.id,
                        'filename': doc.filename,
                        'file_path': doc.file_path,
                        'sender': doc.sender,
                        'chat_name': doc.subject,
                        'text': doc.text[:5000] if doc.text else None,
                        'is_contract': doc.is_contract,
                        'received_at': doc.received_at.isoformat() if doc.received_at else None,
                        'found_at': datetime.now().isoformat()
                    })

                    logger.info(f"NEW: {doc.filename} from {doc.subject}")

                if new_docs > 0:
                    logger.info(f"Found {new_docs} new document(s)")
                else:
                    logger.info("No new documents")

                save_results()

            except Exception as e:
                logger.error(f"Check error: {e}")
                stats['errors'] += 1
                stats['status'] = 'error'
                stats['last_error'] = str(e)
                save_results()

            # Wait for next check
            logger.info(f"Waiting {check_interval}s until next check...")
            await asyncio.sleep(check_interval)

    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
        stats['status'] = 'stopped'
        save_results()

    except Exception as e:
        logger.error(f"Monitor error: {e}")
        stats['status'] = 'error'
        stats['error'] = str(e)
        save_results()

    finally:
        await pipeline.disconnect()
        logger.info("Monitor disconnected")


def main():
    parser = argparse.ArgumentParser(description='WhatsApp Monitor Worker')
    parser.add_argument('--results', '-r', default='whatsapp_monitor_results.json',
                       help='Results JSON file')
    parser.add_argument('--chats', '-c', type=int, default=10,
                       help='Number of chats to check')
    parser.add_argument('--interval', '-i', type=int, default=60,
                       help='Check interval in seconds')
    parser.add_argument('--timeout', '-t', type=int, default=120,
                       help='Login timeout in seconds')
    parser.add_argument('--session', '-s', default='.whatsapp_session_playwright',
                       help='Session directory')
    parser.add_argument('--downloads', '-d', default='whatsapp_downloads',
                       help='Downloads directory')

    args = parser.parse_args()

    logger.info(f"Starting WhatsApp monitor: {args.chats} chats, {args.interval}s interval")

    asyncio.run(monitor_whatsapp(
        session_dir=args.session,
        downloads_dir=args.downloads,
        results_file=args.results,
        chat_limit=args.chats,
        check_interval=args.interval,
        timeout=args.timeout
    ))


if __name__ == '__main__':
    main()
