"""
Core functionality for fetching web pages and extracting content.
"""

import requests
from typing import Tuple, List, Optional
from urllib.parse import urlparse, unquote
from janito.tools.rich_console import print_info, print_success, print_error, print_warning
from janito.tools.usage_tracker import track_usage
from bs4 import BeautifulSoup

@track_usage('web_requests')
def fetch_webpage(url: str, headers: dict = None, timeout: int = 30, max_size: int = 5000000) -> Tuple[str, bool]:
    """
    Fetch the content of a web page from a given URL.
    
    Args:
        url: The URL of the web page to fetch
        headers: Optional HTTP headers to include in the request (default: None)
        timeout: Request timeout in seconds (default: 30)
        max_size: Maximum size in bytes to download (default: 5MB)
        
    Returns:
        A tuple containing (message, is_error)
    """
    print_info(f"Fetching content from URL: {url}", "Web Fetch")
    
    try:
        # Set default headers if none provided
        if headers is None:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.google.com/',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1'
            }
        
        # Make the HTTP request with streaming enabled
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        
        # Raise an exception for HTTP errors
        response.raise_for_status()
        
        # Check content length before downloading fully
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > max_size:
            warning_msg = f"Web Fetch: Content size ({int(content_length)/1000000:.1f}MB) exceeds max size ({max_size/1000000:.1f}MB). Aborting download."
            print_warning(warning_msg)
            return warning_msg, True
            
        # Download content with size limit
        content_bytes = b''
        for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            content_bytes += chunk
            if len(content_bytes) > max_size:
                warning_msg = f"Web Fetch: Download exceeded max size ({max_size/1000000:.1f}MB). Truncating."
                print_warning(warning_msg)
                break
                
        # Get the content
        content = content_bytes.decode('utf-8', errors='replace')
        
        print_success(f"Successfully fetched content ({len(content)} bytes)", "Web Fetch")
        
        # Return the full content
        return content, False
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching web page: {str(e)}"
        print_error(error_msg, "Web Fetch Error")
        return error_msg, True


@track_usage('web_content')
def fetch_and_extract(url: str, max_length: int = 10000, keywords: List[str] = None) -> Tuple[str, bool]:
    """
    Fetch a webpage and extract its main content using BeautifulSoup.
    
    Args:
        url: The URL to fetch
        max_length: Maximum length of text to return
        keywords: Optional list of URL-encoded keywords to prioritize content containing these terms
        
    Returns:
        A tuple containing (extracted_content, is_error)
    """
    html_content, is_error = fetch_webpage(url)
    
    if is_error:
        return html_content, True
    
    try:
        # Use BeautifulSoup to parse and extract content
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'header', 'footer', 'nav', 'aside']):
            element.decompose()
        
        # URL-decode keywords if provided
        decoded_keywords = []
        if keywords:
            decoded_keywords = [unquote(keyword).lower() for keyword in keywords]
            print_info(f"Prioritizing content with keywords: {', '.join(decoded_keywords)}", "Content Extraction")

        # Extract text from main content elements
        paragraphs = []
        keyword_paragraphs = []
        
        for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'article', 'section', 'div']):
            text = tag.get_text(strip=True)
            if text and len(text) > 20:  # Skip very short pieces that might be UI elements
                # Check if the paragraph contains any of the keywords
                if decoded_keywords and any(keyword in text.lower() for keyword in decoded_keywords):
                    keyword_paragraphs.append(text)
                else:
                    paragraphs.append(text)
        
        # Join paragraphs, prioritizing those with keywords
        if keyword_paragraphs:
            print_info(f"Found {len(keyword_paragraphs)} paragraphs containing keywords", "Content Extraction")
            extracted_text = "\n\n".join(keyword_paragraphs + paragraphs)
        else:
            extracted_text = "\n\n".join(paragraphs)
        
        # If no paragraphs found, fall back to all text
        if not extracted_text or len(extracted_text) < 100:
            extracted_text = soup.get_text(separator='\n\n')
            
        # Clean up extra whitespace
        extracted_text = ' '.join(extracted_text.split())
        extracted_text = extracted_text.replace('. ', '.\n\n')
            
        # Truncate if needed
        if len(extracted_text) > max_length:
            print_info(f"Truncating content from {len(extracted_text)} to {max_length} characters", "Content Extraction")
            extracted_text = extracted_text[:max_length] + "..."
        
        print_success(f"Successfully extracted {len(extracted_text)} characters of content", "Content Extraction")
        return extracted_text, False
    
    except Exception as e:
        error_msg = f"Error extracting content: {str(e)}"
        print_error(error_msg, "Content Extraction Error")
        return error_msg, True


def chunk_content(content: str, chunk_size: int = 2000, overlap: int = 200) -> List[str]:
    """
    Split content into overlapping chunks of a specified size.
    
    Args:
        content: The text content to chunk
        chunk_size: Maximum size of each chunk
        overlap: Number of characters to overlap between chunks
        
    Returns:
        List of text chunks
    """
    if not content:
        return []
        
    chunks = []
    
    # Simple chunking with overlap
    for i in range(0, len(content), chunk_size - overlap):
        chunk_end = min(i + chunk_size, len(content))
        chunks.append(content[i:chunk_end])
        if chunk_end == len(content):
            break
    
    print_success(f"Content successfully chunked into {len(chunks)} parts", "Content Chunking")
    return chunks