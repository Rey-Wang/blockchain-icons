#!/usr/bin/env python3
"""
Advanced Blockchair Token Icon Scraper

This script scrapes token icons from blockchair.com and other sources for tokens marked with 🚀 in the TODOLIST.md file.
It includes multiple fallback strategies and better error handling.
"""

import re
import os
import requests
import time
from urllib.parse import urljoin, urlparse
from pathlib import Path
import logging
from typing import List, Dict, Optional, Tuple
import json
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdvancedTokenIconScraper:
    def __init__(self, base_dir: str = None):
        """
        Initialize the scraper
        
        Args:
            base_dir: Base directory for the project (defaults to current script directory)
        """
        if base_dir is None:
            self.base_dir = Path(__file__).parent
        else:
            self.base_dir = Path(base_dir)
        
        self.todolist_path = self.base_dir / "ERC20-tokens" / "TODOLIST.md"
        self.output_dir = self.base_dir / "pyAdvanceIcon"
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Session for requests with better headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Rate limiting
        self.request_delay = 2  # seconds between requests
        self.max_retries = 3
    
    def parse_todolist(self) -> List[Dict[str, str]]:
        """
        Parse the TODOLIST.md file to extract token information marked with 🚀
        
        Returns:
            List of dictionaries containing token info (address, symbol, name)
        """
        if not self.todolist_path.exists():
            logger.error(f"TODOLIST.md not found at {self.todolist_path}")
            return []
        
        tokens = []
        
        with open(self.todolist_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Store the original lines for later reference
        lines = content.split('\n')
        
        # Pattern to match TODOLIST.md format: SYMBOL("0x...", "Name", "SYMBOL", 18, number),
        pattern = r'(\w+)\("(0x[a-fA-F0-9]{40}|[TR][a-zA-Z0-9]{33})", "([^"]+)", "([^"]+)"'
        
        for line_num, line in enumerate(lines):
            match = re.search(pattern, line)
            if match:
                symbol_var, address, name, symbol = match.groups()
                
                # Skip if already added
                if any(t['address'].lower() == address.lower() for t in tokens):
                    continue
                
                tokens.append({
                    'symbol': symbol,  # This is the fourth parameter (token symbol)
                    'address': address.lower() if address.startswith('0x') else address,
                    'name': name,
                    'symbol_var': symbol_var,
                    'original_line': line.strip(),
                    'line_number': line_num + 1
                })
                logger.info(f"Found token: {symbol} ({address})")
        
        logger.info(f"Total tokens found in TODOLIST.md: {len(tokens)}")
        return tokens
    
    def get_blockchair_token_page(self, address: str) -> Optional[str]:
        """
        Get the blockchair token page URL and check if it exists
        
        Args:
            address: Token contract address
            
        Returns:
            Token page URL if exists, None otherwise
        """
        if address.startswith('0x'):
            # Ethereum address - try multiple blockchair URL formats
            possible_urls = [
                f"https://blockchair.com/ethereum/erc-20/token/{address}",
                f"https://blockchair.com/ethereum/token/{address}",
                f"https://blockchair.com/token/ethereum/{address}"
            ]
        elif address.startswith('T'):
            # TRON address
            possible_urls = [
                f"https://blockchair.com/tron/token/{address}",
                f"https://blockchair.com/token/tron/{address}"
            ]
        else:
            return None
        
        for token_page_url in possible_urls:
            try:
                response = self.session.head(token_page_url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Found token page: {token_page_url}")
                    return token_page_url
            except requests.RequestException as e:
                logger.debug(f"Token page {token_page_url} failed: {e}")
                continue
        
        return None
    
    def extract_icon_from_page(self, page_url: str) -> Optional[str]:
        """
        Extract icon URL from blockchair token page
        
        Args:
            page_url: Token page URL
            
        Returns:
            Icon URL if found, None otherwise
        """
        logger.info(f"Extracting icon from page: {page_url}")
        try:
            response = self.session.get(page_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # First, look for the specific token icon on blockchair
            # Blockchair typically has the icon near the token name/header
            possible_selectors = [
                # Look for img elements with token name in alt text
                lambda token_name: soup.find('img', alt=lambda x: x and token_name.lower() in x.lower()),
                # Look for img elements near headings containing token info
                lambda token_name: self._find_icon_near_heading(soup, token_name),
                # Look for the first meaningful img in the main content area
                lambda token_name: self._find_main_content_icon(soup),
            ]
            
            # Extract potential token name from URL
            token_address = page_url.split('/')[-1]
            
            # Try each selector strategy
            for selector_func in possible_selectors:
                try:
                    icon_element = selector_func(token_address)
                    if icon_element and icon_element.get('src'):
                        icon_url = icon_element['src']
                        
                        # Skip obvious non-token icons
                        if self._is_valid_token_icon_url(icon_url):
                            # Convert relative URLs to absolute
                            if icon_url.startswith('//'):
                                icon_url = 'https:' + icon_url
                            elif icon_url.startswith('/'):
                                icon_url = urljoin(page_url, icon_url)
                            
                            logger.info(f"Found valid icon URL from page: {icon_url}")
                            return icon_url
                except Exception as e:
                    logger.debug(f"Selector failed: {e}")
                    continue
            
            # Fallback: check meta tags
            meta_icon = soup.find('meta', property='og:image')
            if meta_icon and meta_icon.get('content'):
                icon_url = meta_icon['content']
                if self._is_valid_token_icon_url(icon_url):
                    if icon_url.startswith('//'):
                        icon_url = 'https:' + icon_url
                    elif icon_url.startswith('/'):
                        icon_url = urljoin(page_url, icon_url)
                    logger.info(f"Found icon URL from meta: {icon_url}")
                    return icon_url
                
        except Exception as e:
            logger.error(f"Error extracting icon from page {page_url}: {e}")
        
        logger.warning(f"No valid icon found on page: {page_url}")
        return None
    
    def _find_icon_near_heading(self, soup, token_address):
        """Find icon element near token heading"""
        # Look for headings that might contain token info
        headings = soup.find_all(['h1', 'h2', 'h3'], string=lambda text: text and ('token' in text.lower() or 'api' in text.lower()))
        
        for heading in headings:
            # Look for img elements near this heading
            parent = heading.parent
            if parent:
                imgs = parent.find_all('img', limit=3)
                for img in imgs:
                    if img.get('src') and self._looks_like_token_icon(img):
                        return img
        return None
    
    def _find_main_content_icon(self, soup):
        """Find the main token icon in the content area"""
        # Look for images that are likely to be token icons
        # Skip obvious UI elements like logos, buttons, etc.
        imgs = soup.find_all('img')
        
        for img in imgs:
            if img.get('src') and self._looks_like_token_icon(img):
                # Additional checks to ensure it's likely a token icon
                alt_text = img.get('alt', '').lower()
                src = img.get('src', '').lower()
                
                # Skip obvious non-token images
                skip_keywords = ['logo', 'button', 'icon', 'footer', 'header', 'nav', 'menu', 'ad', 'sponsor']
                if any(keyword in alt_text or keyword in src for keyword in skip_keywords):
                    continue
                
                # Prefer images that look like they're in content area
                return img
                
        return None
    
    def _looks_like_token_icon(self, img_element):
        """Check if an img element looks like a token icon"""
        src = img_element.get('src', '')
        alt = img_element.get('alt', '')
        
        # Skip empty or invalid sources
        if not src or src.startswith('data:'):
            return False
            
        # Skip very small images (likely UI elements)
        width = img_element.get('width')
        height = img_element.get('height')
        if width and height:
            try:
                w, h = int(width), int(height)
                if w < 20 or h < 20:  # Too small to be a token icon
                    return False
            except ValueError:
                pass
        
        return True
    
    def _is_valid_token_icon_url(self, url):
        """Check if URL looks like a valid token icon"""
        if not url:
            return False
            
        url_lower = url.lower()
        
        # Skip obvious non-token URLs
        invalid_patterns = [
            'logo', 'button', 'favicon', 'banner', 'ad', 'sponsor',
            'header', 'footer', 'menu', 'nav', 'ui', 'interface'
        ]
        
        if any(pattern in url_lower for pattern in invalid_patterns):
            return False
            
        # Accept URLs that look like token icons
        valid_patterns = [
            'token', 'coin', 'crypto', 'currency', '.svg', '.png', '.jpg', '.jpeg'
        ]
        
        return any(pattern in url_lower for pattern in valid_patterns)
    
    def get_fallback_icon_urls(self, address: str, symbol: str) -> List[str]:
        """
        Generate fallback icon URLs from various sources
        
        Args:
            address: Token contract address
            symbol: Token symbol
            
        Returns:
            List of possible icon URLs
        """
        urls = []
        
        if address.startswith('0x'):
            # Use proper checksum address for better compatibility
            checksum_address = address
            
            # Ethereum-based URLs with correct formats
            urls.extend([
                # TrustWallet assets (most reliable)
                f"https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/ethereum/assets/{checksum_address}/logo.png",
                
                # 1inch token logos
                f"https://tokens.1inch.io/{checksum_address.lower()}.png",
                
                # Uniswap token logos
                f"https://raw.githubusercontent.com/Uniswap/assets/master/blockchains/ethereum/assets/{checksum_address}/logo.png",
                
                # Sushiswap token logos  
                f"https://raw.githubusercontent.com/sushiswap/assets/master/blockchains/ethereum/assets/{checksum_address}/logo.png",
                
                # Polygon/Matic network assets
                f"https://wallet-asset.matic.network/img/tokens/{checksum_address.lower()}.svg",
                
                # Alternative sources
                f"https://tokens-data.1inch.io/images/{checksum_address.lower()}.png",
                f"https://assets.spooky.fi/tokens/{checksum_address.lower()}.png"
            ])
        
        return urls
    
    def find_icon_url(self, token_info: Dict[str, str]) -> Optional[str]:
        """
        Find icon URL using multiple strategies, but only return real token icons
        
        Args:
            token_info: Token information dictionary
            
        Returns:
            Icon URL if found, None otherwise
        """
        address = token_info['address']
        symbol = token_info['symbol']
        
        logger.info(f"Finding icon for {symbol} ({address})")
        
        # Strategy 1: Try reliable fallback URLs first (more likely to work)
        fallback_urls = self.get_fallback_icon_urls(address, symbol)
        
        for i, url in enumerate(fallback_urls):
            try:
                logger.debug(f"Trying fallback URL {i+1}/{len(fallback_urls)}: {url}")
                response = self.session.head(url, timeout=10)
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '')
                    if any(img_type in content_type for img_type in ['image', 'svg']):
                        # Additional validation: make sure it's a real token icon, not a generic placeholder
                        if self._is_real_token_icon(url, symbol):
                            logger.info(f"✅ Found valid token icon: {url}")
                            return url
                        else:
                            logger.debug(f"Skipping generic/placeholder icon: {url}")
                    else:
                        logger.debug(f"Wrong content type: {content_type}")
                else:
                    logger.debug(f"Status code: {response.status_code}")
            except requests.RequestException as e:
                logger.debug(f"Request failed: {e}")
                continue
        
        # Strategy 2: Try blockchair page as last resort (seems to have issues)
        logger.info("Fallback URLs failed, trying blockchair page...")
        page_url = self.get_blockchair_token_page(address)
        if page_url:
            icon_url = self.extract_icon_from_page(page_url)
            if icon_url and not 'tether-usdt' in icon_url and self._is_real_token_icon(icon_url, symbol):
                logger.info(f"Found valid icon from blockchair page: {icon_url}")
                return icon_url
            else:
                logger.warning(f"Blockchair returned default/invalid icon: {icon_url}")
        
        logger.warning(f"No valid icon found for {symbol}")
        return None
    
    def _is_real_token_icon(self, url: str, symbol: str) -> bool:
        """
        Check if the URL points to a real token icon, not a generic placeholder
        
        Args:
            url: Icon URL
            symbol: Token symbol
            
        Returns:
            True if it's likely a real token icon
        """
        if not url:
            return False
            
        url_lower = url.lower()
        symbol_lower = symbol.lower()
        
        # Skip obvious generic/placeholder patterns
        generic_patterns = [
            'default', 'placeholder', 'generic', 'unknown', 'missing',
            'error', '404', 'not-found', 'no-image'
        ]
        
        if any(pattern in url_lower for pattern in generic_patterns):
            return False
        
        # For known reliable sources, accept if address-based URL works
        reliable_sources = [
            'tokens-data.1inch.io',
            'raw.githubusercontent.com/trustwallet',
            'tokens.1inch.io'
        ]
        
        if any(source in url_lower for source in reliable_sources):
            return True
        
        # For other sources, prefer URLs that contain the token symbol
        if symbol_lower in url_lower:
            return True
            
        # Default: be conservative, only accept URLs from known good sources
        return False
    
    def download_icon(self, url: str, token_info: Dict[str, str]) -> bool:
        """
        Download an icon from the given URL with retry logic
        
        Args:
            url: Icon URL
            token_info: Token information dictionary
            
        Returns:
            True if successful, False otherwise
        """
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # Check if response contains actual image data
                content_type = response.headers.get('content-type', '')
                if not any(img_type in content_type for img_type in ['image', 'svg']):
                    logger.warning(f"URL {url} doesn't return image content: {content_type}")
                    return False
                
                # Determine file extension
                if 'svg' in content_type or url.endswith('.svg'):
                    ext = '.svg'
                elif 'png' in content_type or url.endswith('.png'):
                    ext = '.png'
                elif 'jpeg' in content_type or 'jpg' in content_type:
                    ext = '.jpg'
                else:
                    ext = '.png'  # Default
                
                # Use symbol as filename
                filename = f"{token_info['symbol'].lower()}{ext}"
                filepath = self.output_dir / filename
                
                # Check minimum file size to avoid placeholder images
                if len(response.content) < 100:  # Less than 100 bytes is likely not a real icon
                    logger.warning(f"Icon too small ({len(response.content)} bytes), skipping")
                    return False
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"Successfully downloaded: {filename} ({len(response.content)} bytes)")
                return True
                
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                continue
            except Exception as e:
                logger.error(f"Unexpected error downloading {url}: {e}")
                break
        
        return False
    
    def scrape_tokens(self, tokens: List[Dict[str, str]]) -> Dict[str, str]:
        """
        Scrape icons for all provided tokens
        
        Args:
            tokens: List of token information dictionaries
            
        Returns:
            Dictionary mapping token symbols to download status
        """
        results = {}
        failed_tokens = []  # Store tokens that couldn't be found
        
        for i, token in enumerate(tokens, 1):
            logger.info(f"Processing token {i}/{len(tokens)}: {token['symbol']} ({token['address']})")
            
            # Check if icon already exists
            possible_files = [
                self.output_dir / f"{token['symbol'].lower()}.svg",
                self.output_dir / f"{token['symbol'].lower()}.png",
                self.output_dir / f"{token['symbol'].lower()}.jpg"
            ]
            
            if any(f.exists() for f in possible_files):
                logger.info(f"Icon for {token['symbol']} already exists, skipping")
                results[token['symbol']] = "already_exists"
                continue
            
            # Try to find and download icon
            icon_url = self.find_icon_url(token)
            
            if icon_url:
                success = self.download_icon(icon_url, token)
                results[token['symbol']] = "success" if success else "download_failed"
            else:
                logger.warning(f"No icon found for {token['symbol']} ({token['address']})")
                results[token['symbol']] = "not_found"
                # Record failed token info
                failed_tokens.append({
                    'symbol': token['symbol'],
                    'address': token['address'],
                    'name': token['name'],
                    'original_line': token.get('original_line', ''),
                    'line_number': token.get('line_number', 0)
                })
            
            # Rate limiting
            time.sleep(self.request_delay)
        
        # Save failed tokens to noResult.md
        if failed_tokens:
            self.save_failed_tokens(failed_tokens)
        
        return results
    
    def save_failed_tokens(self, failed_tokens: List[Dict[str, str]]) -> None:
        """
        Save information about tokens that couldn't be found to noResult.md
        
        Args:
            failed_tokens: List of token information for failed downloads
        """
        no_result_file = self.output_dir / "noResult.md"
        
        content = f"""# 找不到图标的代币列表

生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
总共找不到图标的代币数量: {len(failed_tokens)}

## 详细列表

以下代币无法找到对应的图标，请手动处理：

"""
        
        for i, token in enumerate(failed_tokens, 1):
            content += f"""### {i}. {token['symbol']} - {token['name']}

- **代币符号**: {token['symbol']}
- **合约地址**: {token['address']}
- **代币名称**: {token['name']}
- **原始行**: {token['original_line']}
- **行号**: {token['line_number']}

---

"""
        
        # Also add a summary section for easy copy-paste
        content += """## 原始代码行（便于复制）

```
"""
        for token in failed_tokens:
            if token['original_line']:
                content += f"{token['original_line']}\n"
        
        content += """```

## 说明

这些代币在以下图标源中都未找到对应的图标：
1. TrustWallet Assets
2. 1inch Token Logos  
3. Uniswap Assets
4. Sushiswap Assets
5. Blockchair Pages

建议手动搜索这些代币的官方网站获取图标，或联系项目方获取高质量图标文件。
"""
        
        try:
            with open(no_result_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Saved failed tokens info to: {no_result_file}")
        except Exception as e:
            logger.error(f"Failed to save noResult.md: {e}")
    
    def generate_report(self, results: Dict[str, str]) -> None:
        """
        Generate a summary report of the scraping results
        
        Args:
            results: Dictionary mapping token symbols to download status
        """
        total = len(results)
        success_count = sum(1 for status in results.values() if status == "success")
        already_exists_count = sum(1 for status in results.values() if status == "already_exists")
        not_found_count = sum(1 for status in results.values() if status == "not_found")
        failed_count = sum(1 for status in results.values() if status == "download_failed")
        
        report = f"""
=== Advanced Token Icon Scraping Report ===
Total tokens processed: {total}
Successfully downloaded: {success_count}
Already existed: {already_exists_count}
Not found: {not_found_count}
Download failed: {failed_count}
Success rate: {(success_count / total * 100):.1f}%

Detailed results:
"""
        
        for symbol, status in sorted(results.items()):
            report += f"  {symbol}: {status}\n"
        
        # Save report to file
        report_path = self.output_dir / "advanced_scraping_report.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # Also save as JSON for programmatic access
        json_report = {
            "summary": {
                "total": total,
                "success": success_count,
                "already_exists": already_exists_count,
                "not_found": not_found_count,
                "failed": failed_count,
                "success_rate": round(success_count / total * 100, 1) if total > 0 else 0
            },
            "results": results
        }
        
        json_path = self.output_dir / "scraping_results.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_report, f, indent=2)
        
        logger.info(report)
        logger.info(f"Report saved to: {report_path}")
        logger.info(f"JSON results saved to: {json_path}")
    
    def run(self) -> None:
        """
        Main execution method
        """
        logger.info("Starting advanced token icon scraping...")
        logger.info(f"Base directory: {self.base_dir}")
        logger.info(f"Output directory: {self.output_dir}")
        
        # Parse TODOLIST.md
        tokens = self.parse_todolist()
        
        if not tokens:
            logger.error("No tokens found to process")
            return
        
        # Scrape icons
        results = self.scrape_tokens(tokens)
        
        # Generate report
        self.generate_report(results)
        
        logger.info("Advanced scraping completed!")

def main():
    """
    Entry point for the script
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Advanced Token Icon Scraper for Blockchair')
    parser.add_argument('--base-dir', help='Base directory for the project')
    parser.add_argument('--delay', type=float, default=2, help='Delay between requests in seconds')
    parser.add_argument('--retries', type=int, default=3, help='Maximum number of retries per download')
    
    args = parser.parse_args()
    
    scraper = AdvancedTokenIconScraper(args.base_dir)
    scraper.request_delay = args.delay
    scraper.max_retries = args.retries
    scraper.run()

if __name__ == "__main__":
    main()
