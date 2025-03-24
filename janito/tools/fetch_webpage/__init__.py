"""
Webpage Content Extractor Package

A simplified tool for extracting clean, relevant content from web pages
for processing with LLMs. Features include:
- Streamlined content extraction using BeautifulSoup
- Clean HTML text extraction
- Efficient content chunking

Dependencies:
- requests
- beautifulsoup4

Author: Claude (Anthropic)
"""

from janito.tools.fetch_webpage.core import fetch_webpage, fetch_and_extract, chunk_content

__all__ = [
    'fetch_webpage',
    'fetch_and_extract',
    'chunk_content'
]