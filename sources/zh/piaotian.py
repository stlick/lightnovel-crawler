import logging
import time
import random
from typing import Optional
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

class PiaoTian(Crawler):
    base_url = [
        "https://www.piaotian.com",
        "https://www.ptwxz.com",
        "https://www.piaotia.com",
    ]
    
    def __init__(self):
        super().__init__()
        self.session.mount('https://', HTTPAdapter(max_retries=self._retry_strategy()))
        self._last_request_time = 0
        self.min_delay = 3  # Minimum delay between requests in seconds
        self.max_delay = 5  # Maximum delay between requests in seconds

    def _retry_strategy(self) -> Retry:
        """Configure retry strategy for failed requests"""
        return Retry(
            total=5,  # Maximum number of retries
            backoff_factor=1,  # Factor to apply between retries
            status_forcelist=[429, 500, 502, 503, 504],  # Status codes to retry on
            allowed_methods=["GET", "POST"]  # Methods to apply retry on
        )

    def _random_delay(self) -> None:
        """Implement random delay between requests"""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self.min_delay:
            delay = random.uniform(self.min_delay, self.max_delay)
            time.sleep(delay)
        self._last_request_time = time.time()

    def get_response(self, url: str, **kwargs) -> Optional[str]:
        """Override get_response to implement rate limiting"""
        self._random_delay()
        headers = kwargs.get('headers', {})
        # Add random User-Agent
        if 'User-Agent' not in headers:
            headers['User-Agent'] = self._get_random_user_agent()
        kwargs['headers'] = headers
        return super().get_response(url, **kwargs)

    def post_response(self, url: str, **kwargs) -> Optional[str]:
        """Override post_response to implement rate limiting"""
        self._random_delay()
        headers = kwargs.get('headers', {})
        if 'User-Agent' not in headers:
            headers['User-Agent'] = self._get_random_user_agent()
        kwargs['headers'] = headers
        return super().post_response(url, **kwargs)

    def _get_random_user_agent(self) -> str:
        """Return a random User-Agent string"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        ]
        return random.choice(user_agents)

    def download_chapter_body(self, chapter):
        """Override download_chapter_body with improved error handling"""
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                    "User-Agent": self._get_random_user_agent()
                }
                raw_html = self.get_response(chapter.url, headers=headers)
                if not raw_html:
                    raise Exception("Empty response received")
                
                raw_html.encoding = "gbk"
                raw_text = raw_html.text.replace(
                    '<script language="javascript">GetFont();</script>', 
                    '<div id="content">'
                )
                self.last_soup_url = chapter.url
                soup = self.make_soup(raw_text)

                body = soup.select_one("div#content")
                if not body:
                    raise Exception("Content div not found")

                for elem in body.select("h1, script, div, table"):
                    elem.decompose()

                text = self.cleaner.extract_contents(body)
                return text

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {chapter.url}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"Failed to download chapter after {max_retries} attempts: {chapter.url}")
                    raise