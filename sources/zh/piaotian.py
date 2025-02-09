# -*- coding: utf-8 -*-
import logging
import time
import random
from lncrawl.core.crawler import Crawler
import urllib.parse
from requests.adapters import HTTPAdapter
from urllib3.util import Retry  # Corrigido o import

headers = {
    "Cache-Control": "no-cache",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.piaotia.com",
    "Referer": "https://www.piaotia.com/modules/article/search.php",
}

logger = logging.getLogger(__name__)

novel_search_url = "%smodules/article/search.php"
cover_image_url = "%sfiles/article/image/%s/%s/%ss.jpg"


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

    def _retry_strategy(self):
        return Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]  # Para versões mais recentes do urllib3
            # Se estiver usando uma versão mais antiga do urllib3, use:
            # method_whitelist=["GET", "POST"]
        )

    def _random_delay(self):
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self.min_delay:
            delay = random.uniform(self.min_delay, self.max_delay)
            time.sleep(delay)
        self._last_request_time = time.time()

    def search_novel(self, query):
        self._random_delay()  # Add delay before request
        
        query = urllib.parse.quote(query.encode("gbk"))
        search = urllib.parse.quote(" 搜 索 ".encode("gbk"))
        data = f"searchtype=articlename&searchkey={query}&Submit={search}"
        headers["Origin"] = self.home_url
        headers["Referer"] = novel_search_url % self.home_url

        response = self.post_response(
            novel_search_url % self.home_url,
            headers=headers,
            data=data,
        )
        soup = self.make_soup(response, "gbk")

        results = []

        # if there is only one result, the search page redirects to bookinfo page of that result
        if response.url.startswith("%sbookinfo/" % self.home_url):
            author = soup.select('div#content table tr td[width]')[2].get_text()
            author = author.replace(u'\xa0', "").replace("作 者：", "")
            results.append(
                {
                    "title": soup.select_one("div#content table table table h1").get_text(),
                    "url": response.url,
                    "info": f"Author: {author}",
                }
            )

        else:
            for data in soup.select("div#content table tr")[1:]:
                title = data.select_one("td a").get_text()
                author = data.select("td")[2].get_text()
                url = data.select_one("td a")["href"]

                results.append(
                    {
                        "title": title,
                        "url": url,
                        "info": f"Author: {author}",
                    }
                )
        return results

    def read_novel_info(self):
        self._random_delay()  # Add delay before request

        # Transform bookinfo page into chapter list page
        # https://www.piaotia.com/bookinfo/8/8866.html -> https://www.piaotia.com/html/8/8866/
        if self.novel_url.startswith("%sbookinfo/" % self.home_url):
            self.novel_url = self.novel_url.replace("/bookinfo/", "/html/").replace(".html", "/")

        if self.novel_url.endswith("index.html"):
            self.novel_url = self.novel_url.replace("/index.html", "/")

        soup = self.get_soup(self.novel_url, encoding="gbk")

        self.novel_title = soup.select_one("div.title").text.replace("最新章节", "").strip()
        logger.info("Novel title: %s", self.novel_title)

        author = soup.select_one("div.list")
        author.select_one("a").decompose()
        self.novel_author = author.text.replace("作者：", "").strip()
        logger.info("Novel author: %s", self.novel_author)

        ids = self.novel_url.replace("%shtml/" % self.home_url, "").split("/")
        logger.debug(self.home_url)
        self.novel_cover = cover_image_url % (self.home_url, ids[0], ids[1], ids[1])
        logger.info("Novel cover: %s", self.novel_cover)

        for a in soup.select("div.centent ul li a"):
            chap_id = len(self.chapters) + 1
            vol_id = 1 + len(self.chapters) // 100
            if chap_id % 100 == 1:
                self.volumes.append({"id": vol_id})
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "title": a.text,
                    "url": self.novel_url + a["href"],
                }
            )

    def download_chapter_body(self, chapter):
        self._random_delay()  # Add delay before request
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                headers_chapter = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                    **headers  # Maintain original headers
                }
                raw_html = self.get_response(chapter.url, headers=headers_chapter)
                if not raw_html:
                    logger.warning(f"Empty response received for {chapter.url}")
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
                    logger.warning(f"Content div not found in {chapter.url}")
                    raise Exception("Content div not found")

                for elem in body.select("h1, script, div, table"):
                    elem.decompose()

                text = self.cleaner.extract_contents(body)
                return text

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {chapter.url}: {str(e)}")
                if attempt < max_retries - 1:
                    sleep_time = retry_delay * (attempt + 1)
                    logger.info(f"Waiting {sleep_time} seconds before retry...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"Failed to download chapter after {max_retries} attempts: {chapter.url}")
                    raise