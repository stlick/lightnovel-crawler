# -*- coding: utf-8 -*-
import logging
import time
import random
from lncrawl.core.crawler import Crawler
import urllib.parse

headers = {
    "Cache-Control": "no-cache",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.piaotia.com",
    "Referer": "https://www.piaotia.com/modules/article/search.php",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

logger = logging.getLogger(__name__)

novel_search_url = "%smodules/article/search.php"
cover_image_url = "%sfiles/article/image/%s/%s/%ss.jpg"


class PiaoTian(Crawler):
    base_url = [
        "https://www.piaotia.com",
        "https://www.ptwxz.com",
        "https://www.piaotia.com",
    ]

    def __init__(self):
        super().__init__()
        self._last_request_time = 0
        self.min_delay = 10  # Aumentado para 10 segundos
        self.max_delay = 15  # Aumentado para 15 segundos

    def _wait_between_requests(self):
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        
        # Se passou menos tempo que o delay mínimo
        if elapsed < self.min_delay:
            delay = random.uniform(self.min_delay, self.max_delay)
            time.sleep(delay)
        
        self._last_request_time = time.time()

    def search_novel(self, query):
        self._wait_between_requests()
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
        self._wait_between_requests()
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
        max_retries = 5  # Aumentado número de tentativas
        base_delay = 15  # Delay base aumentado para 15 segundos
        
        for attempt in range(max_retries):
            try:
                self._wait_between_requests()
                headers_chapter = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                    "User-Agent": headers["User-Agent"]
                }
                raw_html = self.get_response(chapter.url, headers=headers_chapter)
                raw_html.encoding = "gbk"
                raw_text = raw_html.text.replace('<script language="javascript">GetFont();</script>', '<div id="content">')
                self.last_soup_url = chapter.url
                soup = self.make_soup(raw_text)

                body = soup.select_one("div#content")
                for elem in body.select("h1, script, div, table"):
                    elem.decompose()

                text = self.cleaner.extract_contents(body)
                return text

            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {chapter.url}: {str(e)}")
                if attempt < max_retries - 1:
                    # Exponential backoff com jitter
                    sleep_time = (base_delay * (2 ** attempt)) + random.uniform(1, 5)
                    logger.info(f"Waiting {sleep_time:.2f} seconds before retry...")
                    time.sleep(sleep_time)
                else:
                    raise