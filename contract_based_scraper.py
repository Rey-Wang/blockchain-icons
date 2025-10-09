#!/usr/bin/env python3
"""
Blockchair Token Icon Scraper - Contract Address Based
"""

import re
import time
from pathlib import Path
import logging
from typing import List, Dict, Optional
import asyncio
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ContractBasedTokenScraper:
    def __init__(self, base_dir: str = None):
        if base_dir is None:
            self.base_dir = Path(__file__).parent
        else:
            self.base_dir = Path(base_dir)
        
        self.todolist_path = self.base_dir / "README.TODO.md"
        self.output_dir = self.base_dir / "pyAdvanceIcon"
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.browser = None
        self.page = None
    
    def parse_todolist(self) -> List[Dict[str, str]]:
        """Parse README.TODO.md to extract token information"""
        if not self.todolist_path.exists():
            logger.error(f"README.TODO.md not found at {self.todolist_path}")
            return []
        
        tokens = []
        
        with open(self.todolist_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        # Pattern to match: SYMBOL("0x...", "Name", "SYMBOL", ...)
        pattern = r'(\w+)\("(0x[a-fA-F0-9]{40}|[TR][a-zA-Z0-9]{33})", "([^"]+)", "([^"]+)"'
        
        for line_num, line in enumerate(lines):
            match = re.search(pattern, line)
            if match:
                symbol_var, address, name, symbol = match.groups()
                
                # Skip if already added
                if any(t['address'].lower() == address.lower() for t in tokens):
                    continue
                
                tokens.append({
                    'symbol': symbol,
                    'address': address.lower() if address.startswith('0x') else address,
                    'name': name,
                    'symbol_var': symbol_var,
                    'original_line': line.strip(),
                    'line_number': line_num + 1
                })
                logger.info(f"Found token: {symbol} ({name}) - {address}")
        
        logger.info(f"Total tokens found: {len(tokens)}")
        return tokens
    
    async def init_browser(self):
        """Initialize Playwright browser"""
        logger.info("Initializing browser...")
        self.playwright = await async_playwright().start()
        
        # Launch browser in headless mode for batch processing
        self.browser = await self.playwright.chromium.launch(
            headless=True,  # Set to True for headless mode
            args=['--no-sandbox', '--disable-dev-shm-usage']  # Additional args for stability
        )
        
        self.page = await self.browser.new_page(
            viewport={'width': 1280, 'height': 720}
        )
        
        logger.info("Browser initialized successfully")
    
    async def close_browser(self):
        """Close the browser"""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed")
    
    async def search_token_by_contract(self, address: str, symbol: str) -> Optional[str]:
        """
        Search for token using contract address and extract icon
        
        Args:
            address: Token contract address
            symbol: Token symbol
            
        Returns:
            Icon URL if found, None otherwise
        """
        try:
            # Navigate to Blockchair search page with contract address
            search_url = f"https://blockchair.com/search?q={address}"
            logger.info(f"🔍 Searching contract: {search_url}")
            
            await self.page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
            await self.page.wait_for_timeout(3000)
            
            # Look for token links in search results
            # These links lead to token detail pages
            token_links = await self.page.query_selector_all('a[href*="/tokens/"]')
            
            if token_links and len(token_links) > 0:
                logger.info(f"✓ Found {len(token_links)} token links in search results")
                
                # Click on the first token link to go to details page
                first_link = token_links[0]
                href = await first_link.get_attribute('href')
                logger.info(f"📄 Opening token details: {href}")
                
                await first_link.click()
                await self.page.wait_for_timeout(3000)
                
                # Extract icon from the token details page
                icon_url = await self.extract_icon_from_token_page()
                if icon_url:
                    logger.info(f"🎯 Found icon: {icon_url}")
                    return icon_url
                else:
                    logger.warning(f"❌ No icon found on token details page")
            else:
                logger.warning(f"❌ No token links found for contract {address}")
            
        except Exception as e:
            logger.error(f"❌ Error searching contract {address}: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return None
    
    async def extract_icon_from_token_page(self) -> Optional[str]:
        """
        Extract token icon from the token details page
        Looking for: loutre.blockchair.io/contract-enricher/token/{name}/large.{png|jpg}
        """
        try:
            logger.info("🔍 Looking for token icon with class 'illustration-regular'...")
            
            # Strategy 1: Find images with class 'illustration-regular'
            illustration_imgs = await self.page.query_selector_all('img.illustration-regular')
            
            if illustration_imgs:
                logger.info(f"Found {len(illustration_imgs)} images with class 'illustration-regular'")
                
                for img in illustration_imgs:
                    src = await img.get_attribute('src')
                    width = await img.get_attribute('width')
                    height = await img.get_attribute('height')
                    
                    # Check if this is the main token icon from contract-enricher
                    if src and 'loutre.blockchair.io/contract-enricher/token/' in src:
                        if width == '250' or height == '250':
                            return self._normalize_url(src)
            
            # Strategy 2: Look for contract-enricher URLs directly
            logger.info("🔍 Searching for contract-enricher URLs...")
            all_images = await self.page.query_selector_all('img')
            
            for img in all_images:
                src = await img.get_attribute('src')
                if src and 'loutre.blockchair.io/contract-enricher/token/' in src and '/large.' in src:
                    return self._normalize_url(src)
            
        except Exception as e:
            logger.error(f"Error extracting icon: {e}")
        
        return None
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL to absolute URL"""
        if url.startswith('//'):
            return 'https:' + url
        elif url.startswith('/'):
            return 'https://blockchair.com' + url
        return url
    
    async def download_icon(self, url: str, token_info: Dict[str, str]) -> bool:
        """Download icon from URL"""
        try:
            import aiohttp
            
            # Determine file extension
            if url.endswith('.svg') or 'svg' in url.lower():
                ext = '.svg'
            elif url.endswith('.png') or 'png' in url.lower():
                ext = '.png'
            elif url.endswith('.jpg') or url.endswith('.jpeg'):
                ext = '.jpg'
            else:
                ext = '.png'  # Default
            
            # Use symbol as filename
            filename = f"{token_info['symbol'].lower()}{ext}"
            filepath = self.output_dir / filename
            
            # Download the file
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        # Check minimum file size
                        if len(content) < 100:
                            logger.warning(f"⚠️  Icon too small ({len(content)} bytes), skipping")
                            return False
                        
                        with open(filepath, 'wb') as f:
                            f.write(content)
                        
                        logger.info(f"✅ Downloaded: {filename} ({len(content)} bytes)")
                        return True
                    else:
                        logger.warning(f"❌ Failed to download: HTTP {response.status}")
                        return False
        
        except Exception as e:
            logger.error(f"❌ Error downloading icon: {e}")
            return False
    
    async def process_token(self, token: Dict[str, str]) -> Dict[str, str]:
        """Process a single token"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🪙 Processing: {token['symbol']} ({token['name']})")
        logger.info(f"📍 Contract: {token['address']}")
        logger.info(f"{'='*60}")
        
        # Check if icon already exists
        possible_files = [
            self.output_dir / f"{token['symbol'].lower()}.svg",
            self.output_dir / f"{token['symbol'].lower()}.png",
            self.output_dir / f"{token['symbol'].lower()}.jpg"
        ]
        
        if any(f.exists() for f in possible_files):
            logger.info(f"✅ Icon for {token['symbol']} already exists, skipping")
            return {'token': token, 'status': 'already_exists'}
        
        # Search for icon using contract address
        icon_url = await self.search_token_by_contract(token['address'], token['symbol'])
        
        if icon_url:
            # Try to download
            success = await self.download_icon(icon_url, token)
            if success:
                return {'token': token, 'status': 'success', 'icon_url': icon_url}
            else:
                return {'token': token, 'status': 'download_failed', 'icon_url': icon_url}
        else:
            logger.warning(f"❌ No icon found for {token['symbol']}")
            return {'token': token, 'status': 'not_found'}
    
    async def scrape_tokens(self, tokens: List[Dict[str, str]], limit: int = None) -> List[Dict]:
        """Scrape icons for tokens"""
        if limit:
            tokens = tokens[:limit]
            
        results = []
        failed_tokens = []
        
        for i, token in enumerate(tokens, 1):
            logger.info(f"\n\n>>> Processing token {i}/{len(tokens)}")
            
            result = await self.process_token(token)
            results.append(result)
            
            if result['status'] in ['not_found', 'download_failed']:
                failed_tokens.append(token)
            
            # Small delay between tokens to avoid overwhelming the server
            await asyncio.sleep(0.5)
        
        # Save failed tokens to noResult.txt
        if failed_tokens:
            self.save_failed_tokens(failed_tokens)
        
        return results
    
    def save_failed_tokens(self, failed_tokens: List[Dict[str, str]]) -> None:
        """Save failed tokens to noResult.txt"""
        no_result_file = self.output_dir / "noResult.txt"
        
        content = f"""# Token Icons Not Found
# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
# Total: {len(failed_tokens)} tokens

"""
        
        for token in failed_tokens:
            if token['original_line']:
                content += f"{token['original_line']}\n"
        
        try:
            with open(no_result_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"\n✅ Failed tokens saved to: {no_result_file}")
        except Exception as e:
            logger.error(f"❌ Failed to save noResult.txt: {e}")
    
    def generate_report(self, results: List[Dict]) -> None:
        """Generate summary report"""
        total = len(results)
        success_count = sum(1 for r in results if r['status'] == 'success')
        already_exists_count = sum(1 for r in results if r['status'] == 'already_exists')
        not_found_count = sum(1 for r in results if r['status'] == 'not_found')
        failed_count = sum(1 for r in results if r['status'] == 'download_failed')
        
        report = f"""
{'='*80}
📊 TOKEN ICON SCRAPING REPORT
{'='*80}

📋 Total processed: {total}
✅ Successfully downloaded: {success_count}
📁 Already existed: {already_exists_count}
❌ Not found: {not_found_count}
💥 Download failed: {failed_count}
📈 Success rate: {(success_count / total * 100):.1f}% (new downloads)
📊 Coverage rate: {((success_count + already_exists_count) / total * 100):.1f}% (total)

{'='*80}

📝 Detailed Results:

"""
        
        for result in results:
            token = result['token']
            status = result['status']
            status_icon = '✅' if status in ['success', 'already_exists'] else '❌'
            
            report += f"{status_icon} {token['symbol']:15} | {status:20} | {token['address']}\n"
        
        # Save report
        report_path = self.output_dir / "scraping_report.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        logger.info(report)
        logger.info(f"\n✅ Report saved to: {report_path}")
    
    async def run(self, limit: int = None):
        """Main execution method"""
        logger.info("🚀 Starting contract-based token icon scraping...")
        logger.info(f"📁 Output directory: {self.output_dir}")
        
        # Parse README.TODO.md
        tokens = self.parse_todolist()
        
        if not tokens:
            logger.error("❌ No tokens found to process")
            return
        
        if limit:
            logger.info(f"🎯 Processing first {limit} tokens")
        
        try:
            # Initialize browser
            await self.init_browser()
            
            # Scrape icons
            results = await self.scrape_tokens(tokens, limit)
            
            # Generate report
            self.generate_report(results)
            
            logger.info("\n🎉 Scraping completed!")
            
        finally:
            # Close browser immediately after completion
            await self.close_browser()

async def main():
    """Entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Contract-based Token Icon Scraper')
    parser.add_argument('--limit', type=int, help='Limit number of tokens to process')
    
    args = parser.parse_args()
    
    scraper = ContractBasedTokenScraper()
    await scraper.run(limit=args.limit)

if __name__ == "__main__":
    asyncio.run(main())
