import asyncio
from scraper.browser_crawler import RelevantBrowserCrawler

if __name__ == "__main__":
    asyncio.run(RelevantBrowserCrawler("config.json").crawl())
