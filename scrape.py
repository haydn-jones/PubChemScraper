import asyncio
import json
import logging
from collections.abc import Sequence
from itertools import cycle
from pathlib import Path
from urllib.parse import quote

import aiofiles
import aiohttp

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ProxyRotator:
    def __init__(self, proxies: Sequence[str]):
        self.proxy_cycle = cycle(proxies)

    def get_next(self) -> str:
        return next(self.proxy_cycle)


async def download_page(
    session: aiohttp.ClientSession,
    url: str,
    heading: str,
    page: int,
    proxy_rotator: ProxyRotator,
    semaphore: asyncio.Semaphore,
) -> str | None:
    """Downloads a single page using the next proxy in rotation with concurrency control"""
    opath = Path(f"./data/scraped/{heading}/{page}.json")
    opath.parent.mkdir(parents=True, exist_ok=True)

    if opath.exists():
        logger.info(f"Skipping {heading} page {page} as it already exists")
        async with aiofiles.open(opath) as f:
            return await f.read()

    async with semaphore:  # Control concurrency
        try:
            proxy = proxy_rotator.get_next()
            async with session.get(url, proxy=proxy) as response:
                if response.status != 200:
                    logger.error(f"Error {response.status} for {url} using proxy {proxy}")
                    return None

                text = await response.text()
                opath.parent.mkdir(parents=True, exist_ok=True)
                opath.write_text(text)

                logger.info(f"Downloaded {heading} page {page}")
                await asyncio.sleep(4.0)  # Keep existing delay
                return text

        except Exception as e:
            logger.error(f"Error downloading {url}: {str(e)}")
            return None


async def download_pubchem_heading(
    heading: str, session: aiohttp.ClientSession, proxy_rotator: ProxyRotator, semaphore: asyncio.Semaphore
) -> None:
    """Downloads all pages for a given PubChem heading asynchronously"""
    base_url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/annotations/heading"
    encoded_heading = quote(heading, safe="")

    # Get first page and total pages
    url = f"{base_url}/{encoded_heading}/JSON?heading_type=Compound"
    text = await download_page(session, url, heading, 1, proxy_rotator, semaphore)

    if not text:
        logger.error(f"Failed to get first page for {heading}")
        return

    try:
        data = json.loads(text)
        total_pages = data["Annotations"]["TotalPages"]
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Error parsing response for {heading}: {str(e)}")
        return

    # Create tasks for remaining pages
    tasks = []
    for page in range(2, total_pages + 1):
        url = f"{base_url}/{encoded_heading}/JSON?page={page}&heading_type=Compound"
        tasks.append(download_page(session, url, heading, page, proxy_rotator, semaphore))

    # Wait for all pages to download
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Log any exceptions that occurred
    for i, result in enumerate(results, start=2):
        if isinstance(result, Exception):
            logger.error(f"Error downloading page {i} of {heading}: {str(result)}")


async def main(headings: list[str], proxies: list[str], max_concurrent: int = 10) -> None:
    """Downloads multiple headings in parallel using rotating proxies with concurrency limit"""
    proxy_rotator = ProxyRotator(proxies)
    semaphore = asyncio.Semaphore(max_concurrent)

    timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout
    connector = aiohttp.TCPConnector(limit_per_host=30)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [download_pubchem_heading(heading, session, proxy_rotator, semaphore) for heading in headings]
        await asyncio.gather(*tasks)


def read_proxies(file_path: str) -> list[str]:
    with open(file_path) as f:
        return [
            f"http://{user}:{password}@{ip}:{port}"
            for ip, port, user, password in (line.strip().split(":") for line in f if line.strip())
        ]


if __name__ == "__main__":
    with open("./data/headings.json") as f:
        headings = json.load(f)

    proxies = read_proxies("data/proxies.txt")

    # Run with max 10 concurrent downloads
    asyncio.run(main(headings, proxies, max_concurrent=30))
