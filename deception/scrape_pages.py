#!/usr/bin/env python3
"""
Scraper for product pages from the hosted catalog.
Scrapes all product pages and saves them organized by category.
"""

import json
import os
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# Paths
SCRIPT_DIR = Path(__file__).parent
JSON_DIR = SCRIPT_DIR / "json"
PAGES_DIR = SCRIPT_DIR / "pages"


def load_json(filename: str) -> dict:
    """Load a JSON file from the json directory."""
    with open(JSON_DIR / filename, 'r') as f:
        return json.load(f)


def get_url_id(url: str) -> str:
    """Extract the UUID from the URL to use as filename."""
    # URL format: https://abhin2149.github.io/product-catalog/{category}/{uuid}/
    parts = url.rstrip('/').split('/')
    return parts[-1]


def get_category_from_url(url: str) -> str:
    """Extract category from URL."""
    # URL format: https://abhin2149.github.io/product-catalog/{category}/{uuid}/
    parts = url.rstrip('/').split('/')
    return parts[-2]


def scrape_page(url: str, retries: int = 3, delay: float = 1.0) -> Tuple[str, str]:
    """
    Scrape a single page and return (html_content, text_content).
    
    Args:
        url: URL to scrape
        retries: Number of retry attempts
        delay: Delay between retries
    
    Returns:
        Tuple of (raw HTML, extracted text content)
    """
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            html_content = response.text
            
            # Extract text content using BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text
            text_content = soup.get_text(separator='\n', strip=True)
            
            return html_content, text_content
            
        except requests.RequestException as e:
            print(f"  Attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


def main():
    """Main scraping function."""
    print("=" * 60)
    print("Product Page Scraper")
    print("=" * 60)
    
    # Load JSON data
    print("\n[1] Loading JSON data...")
    products_hosted = load_json("products_hosted.json")
    link_to_label = load_json("link_to_label_map.json")
    link_to_product = load_json("link_to_product_map.json")
    link_to_category = load_json("link_to_category_map.json")
    
    # Collect all unique URLs
    all_urls = set()
    for category, data in products_hosted.items():
        for product in data["products"]:
            all_urls.add(product["link"])
    
    print(f"   Found {len(all_urls)} unique URLs across {len(products_hosted)} categories")
    
    # Create output directories
    print("\n[2] Creating output directories...")
    PAGES_DIR.mkdir(exist_ok=True)
    (PAGES_DIR / "html").mkdir(exist_ok=True)
    (PAGES_DIR / "text").mkdir(exist_ok=True)
    
    # Create category subdirectories
    for category in products_hosted.keys():
        category_slug = category.replace(" ", "_")
        (PAGES_DIR / "html" / category_slug).mkdir(exist_ok=True)
        (PAGES_DIR / "text" / category_slug).mkdir(exist_ok=True)
    
    # Scrape pages
    print("\n[3] Scraping pages...")
    scraped_metadata = []
    
    for i, url in enumerate(sorted(all_urls), 1):
        url_id = get_url_id(url)
        category = link_to_category.get(url, get_category_from_url(url))
        category_slug = category.replace(" ", "_")
        label = link_to_label.get(url, "unknown")
        product_name = link_to_product.get(url, "Unknown Product")
        
        print(f"   [{i}/{len(all_urls)}] {product_name[:50]}...")
        
        # Check if already scraped
        html_path = PAGES_DIR / "html" / category_slug / f"{url_id}.html"
        text_path = PAGES_DIR / "text" / category_slug / f"{url_id}.txt"
        
        if html_path.exists() and text_path.exists():
            print(f"         Already scraped, skipping...")
            # Still add to metadata
            with open(text_path, 'r') as f:
                text_content = f.read()
            scraped_metadata.append({
                "url": url,
                "url_id": url_id,
                "category": category,
                "label": label,
                "product_name": product_name,
                "html_path": str(html_path.relative_to(SCRIPT_DIR)),
                "text_path": str(text_path.relative_to(SCRIPT_DIR)),
                "text_length": len(text_content)
            })
            continue
        
        try:
            html_content, text_content = scrape_page(url)
            
            # Save HTML
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Save text
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            scraped_metadata.append({
                "url": url,
                "url_id": url_id,
                "category": category,
                "label": label,
                "product_name": product_name,
                "html_path": str(html_path.relative_to(SCRIPT_DIR)),
                "text_path": str(text_path.relative_to(SCRIPT_DIR)),
                "text_length": len(text_content)
            })
            
            print(f"         Saved ({len(text_content)} chars)")
            
            # Be nice to the server
            time.sleep(0.5)
            
        except Exception as e:
            print(f"         ERROR: {e}")
            scraped_metadata.append({
                "url": url,
                "url_id": url_id,
                "category": category,
                "label": label,
                "product_name": product_name,
                "error": str(e)
            })
    
    # Save metadata
    print("\n[4] Saving metadata...")
    metadata_path = PAGES_DIR / "scraped_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(scraped_metadata, f, indent=2)
    print(f"   Saved metadata to {metadata_path}")
    
    # Generate summary by category
    print("\n[5] Generating summary...")
    summary = {}
    for item in scraped_metadata:
        cat = item.get("category", "unknown")
        if cat not in summary:
            summary[cat] = {"total": 0, "target": 0, "target_adv": 0, "normal": 0, "errors": 0}
        
        summary[cat]["total"] += 1
        if "error" in item:
            summary[cat]["errors"] += 1
        else:
            label = item.get("label", "unknown")
            if label in summary[cat]:
                summary[cat][label] += 1
    
    print("\n   Category Summary:")
    print("   " + "-" * 55)
    print(f"   {'Category':<20} {'Total':>6} {'Target':>7} {'Adv':>5} {'Normal':>7} {'Err':>5}")
    print("   " + "-" * 55)
    for cat, data in sorted(summary.items()):
        print(f"   {cat:<20} {data['total']:>6} {data['target']:>7} {data['target_adv']:>5} {data['normal']:>7} {data['errors']:>5}")
    print("   " + "-" * 55)
    
    # Save summary
    summary_path = PAGES_DIR / "category_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"\n   Saved summary to {summary_path}")
    
    print("\n" + "=" * 60)
    print("Scraping complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
