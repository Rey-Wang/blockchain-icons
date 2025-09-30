#!/usr/bin/env python3
"""
Cryptologos.cc SVG Icon Scraper using MCP Playwright

This script uses the MCP Playwright browser to search for token icons 
on cryptologos.cc and coordinate SVG downloads for tokens marked with 🚀 
in the README.TODO.md file.
"""

import re
import os
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional
import argparse
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CryptologosBrowserScraper:
    def __init__(self, base_dir: str = None):
        """
        Initialize the scraper
        
        Args:
            base_dir: Base directory for the project
        """
        if base_dir is None:
            self.base_dir = Path(__file__).parent
        else:
            self.base_dir = Path(base_dir)
        
        self.todolist_path = self.base_dir / "ERC20-tokens" / "TODOLIST.md"
        self.output_dir = self.base_dir / "pyAdvanceSVG"
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Cryptologos browser scraper initialized")
        logger.info(f"TODO list path: {self.todolist_path}")
        logger.info(f"Output directory: {self.output_dir}")
    
    def parse_todolist(self) -> List[Dict[str, str]]:
        """
        Parse the README.TODO.md file to extract token information
        
        Returns:
            List of token information dictionaries
        """
        if not self.todolist_path.exists():
            logger.error(f"TODO list file not found: {self.todolist_path}")
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
    
    def generate_browser_script(self, tokens: List[Dict[str, str]]) -> str:
        """
        Generate instructions for manual browser interaction
        
        Args:
            tokens: List of token information dictionaries
            
        Returns:
            Instructions for browser automation
        """
        script_content = f"""
# Cryptologos.cc SVG 下载指南

这个指南将帮助您手动或半自动下载代币的 SVG 图标。

## 需要搜索和下载的代币 ({len(tokens)} 个):

"""
        
        for i, token in enumerate(tokens, 1):
            script_content += f"""
### {i}. {token['symbol']} - {token['name']}

- **代币符号**: {token['symbol']}
- **代币名称**: {token['name']}
- **搜索 URL**: https://www.cryptologos.cc/search?q={token['symbol']}
- **下载文件名**: {token['symbol'].lower()}.svg

**步骤**:
1. 访问搜索 URL
2. 查找包含 "{token['symbol']}" 的结果
3. 点击进入代币页面
4. 找到并下载 SVG 格式的图标
5. 将文件重命名为 `{token['symbol'].lower()}.svg`
6. 保存到 `pyAdvanceSVG/` 目录

---
"""
        
        script_content += f"""
## 批量下载建议

由于 cryptologos.cc 有反爬虫保护，建议按以下方式进行：

### 方法 1: 手动下载
1. 打开浏览器访问 https://www.cryptologos.cc/
2. 逐个搜索上面列出的代币符号
3. 下载 SVG 格式的图标

### 方法 2: 浏览器扩展
考虑使用浏览器扩展来辅助批量下载：
1. Tampermonkey/Greasemonkey 脚本
2. 浏览器开发者工具的 Console

### 方法 3: 其他图标源
如果 cryptologos.cc 无法访问，可以尝试其他源：
- https://github.com/spothq/cryptocurrency-icons
- https://github.com/ErikThiart/cryptocurrency-icons
- https://www.coingecko.com/ (API)

## 完成状态跟踪

请在下载完成后，在对应的代币行后面添加 ✅ 标记：

"""
        
        for token in tokens:
            script_content += f"- [ ] {token['symbol']} - {token['name']}\n"
        
        return script_content
    
    def save_download_guide(self, tokens: List[Dict[str, str]]) -> None:
        """
        Save a download guide for manual processing
        
        Args:
            tokens: List of token information dictionaries
        """
        guide_content = self.generate_browser_script(tokens)
        
        guide_file = self.output_dir / "cryptologos_download_guide.md"
        
        try:
            with open(guide_file, 'w', encoding='utf-8') as f:
                f.write(guide_content)
            logger.info(f"Download guide saved to: {guide_file}")
        except Exception as e:
            logger.error(f"Failed to save download guide: {e}")
    
    def generate_browser_automation_script(self, tokens: List[Dict[str, str]]) -> str:
        """
        Generate a browser console script for automation
        
        Args:
            tokens: List of token information dictionaries
            
        Returns:
            JavaScript code for browser console
        """
        js_tokens = json.dumps([{'symbol': t['symbol'], 'name': t['name']} for t in tokens])
        
        js_script = f"""
// Cryptologos.cc 自动化下载脚本
// 在浏览器控制台中运行此脚本

const tokens = {js_tokens};
let currentIndex = 0;

async function downloadToken(token) {{
    console.log(`正在处理: ${{token.symbol}} - ${{token.name}}`);
    
    // 搜索代币
    const searchUrl = `https://www.cryptologos.cc/search?q=${{token.symbol}}`;
    window.open(searchUrl, '_blank');
    
    // 等待用户手动选择和下载
    return new Promise((resolve) => {{
        setTimeout(() => {{
            resolve();
        }}, 5000); // 5秒后继续下一个
    }});
}}

async function downloadAll() {{
    for (let i = 0; i < tokens.length; i++) {{
        await downloadToken(tokens[i]);
        console.log(`完成 ${{i + 1}}/${{tokens.length}}: ${{tokens[i].symbol}}`);
    }}
    console.log('所有代币处理完成！');
}}

// 开始下载
console.log('开始批量下载...');
downloadAll();

// 使用方法：
// 1. 访问 https://www.cryptologos.cc/
// 2. 打开浏览器开发者工具 (F12)
// 3. 切换到 Console 标签
// 4. 复制粘贴上面的代码并回车执行
// 5. 脚本会自动打开搜索页面，您需要手动点击下载
"""
        return js_script
    
    def save_automation_script(self, tokens: List[Dict[str, str]]) -> None:
        """
        Save JavaScript automation script
        
        Args:
            tokens: List of token information dictionaries
        """
        js_content = self.generate_browser_automation_script(tokens)
        
        js_file = self.output_dir / "cryptologos_automation.js"
        
        try:
            with open(js_file, 'w', encoding='utf-8') as f:
                f.write(js_content)
            logger.info(f"Automation script saved to: {js_file}")
        except Exception as e:
            logger.error(f"Failed to save automation script: {e}")
    
    def save_url_list(self, tokens: List[Dict[str, str]]) -> None:
        """
        Save a simple list of URLs for easy copying
        
        Args:
            tokens: List of token information dictionaries
        """
        urls = []
        for token in tokens:
            urls.append(f"https://www.cryptologos.cc/search?q={token['symbol']}")
        
        url_content = "# Cryptologos.cc 搜索 URLs\n\n"
        url_content += "以下是所有需要搜索的代币 URL，可以批量在浏览器中打开：\n\n"
        
        for i, (token, url) in enumerate(zip(tokens, urls), 1):
            url_content += f"{i}. {token['symbol']} - {url}\n"
        
        url_content += f"\n总计: {len(urls)} 个代币需要下载\n"
        
        url_file = self.output_dir / "search_urls.txt"
        
        try:
            with open(url_file, 'w', encoding='utf-8') as f:
                f.write(url_content)
            logger.info(f"URL list saved to: {url_file}")
        except Exception as e:
            logger.error(f"Failed to save URL list: {e}")
    
    def run(self) -> None:
        """
        Main execution function
        """
        logger.info("Starting Cryptologos.cc browser scraper...")
        
        # Parse tokens from TODO list
        tokens = self.parse_todolist()
        
        if not tokens:
            logger.error("No tokens found in TODO list")
            return
        
        logger.info(f"Found {len(tokens)} tokens to process")
        
        # Generate helper files
        self.save_download_guide(tokens)
        self.save_automation_script(tokens)
        self.save_url_list(tokens)
        
        logger.info(f"""
=== Cryptologos.cc 下载辅助文件已生成 ===

由于 cryptologos.cc 有反爬虫保护，我们创建了以下辅助文件：

1. 📋 pyAdvanceSVG/cryptologos_download_guide.md
   - 详细的手动下载指南
   - 包含所有代币的搜索链接和下载步骤

2. 🤖 pyAdvanceSVG/cryptologos_automation.js  
   - 浏览器控制台自动化脚本
   - 可以辅助批量打开搜索页面

3. 🔗 pyAdvanceSVG/search_urls.txt
   - 所有搜索 URL 的简单列表
   - 方便批量复制到浏览器

建议使用步骤：
1. 打开 cryptologos_download_guide.md 查看详细指南
2. 访问 https://www.cryptologos.cc/ 
3. 使用自动化脚本或手动逐个搜索下载
4. 将下载的 SVG 文件保存到 pyAdvanceSVG/ 目录

总共需要下载 {len(tokens)} 个代币的 SVG 图标。
""")

def main():
    parser = argparse.ArgumentParser(description='Cryptologos.cc Browser-based SVG Icon Scraper')
    parser.add_argument('--base-dir', type=str, help='Base directory for the project')
    
    args = parser.parse_args()
    
    scraper = CryptologosBrowserScraper(base_dir=args.base_dir)
    scraper.run()

if __name__ == "__main__":
    main()
