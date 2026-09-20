# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from email.utils import parsedate_to_datetime
from time import time

from scrapy import signals
from twisted.internet import reactor

# useful for handling different item types with a single interface
from itemadapter import is_item, ItemAdapter


class DegreeprogramsSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    def process_start_requests(self, start_requests, spider):
        # Called with the start requests of the spider, and works
        # similarly to the process_spider_output() method, except
        # that it doesn’t have a response associated.

        # Must return only requests (not items).
        for r in start_requests:
            yield r

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class TooManyRequestsRetryMiddleware:
    """Backs off on HTTP 429 by pausing the whole crawl engine.

    Honors Retry-After when the site sends one; otherwise backs off
    exponentially. Scrapy's AutoThrottle only reacts to response latency,
    not to 429 status codes, so this fills that gap.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        settings = crawler.settings
        self.base_delay = settings.getfloat("TOOMANYREQUESTS_BASE_DELAY", 10)
        self.max_delay = settings.getfloat("TOOMANYREQUESTS_MAX_DELAY", 900)
        self.max_retries = settings.getint("TOOMANYREQUESTS_MAX_RETRIES", 10)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_response(self, request, response, spider):
        if response.status != 429:
            return response

        retries = request.meta.get("retry_times", 0) + 1
        if retries > self.max_retries:
            spider.logger.error(
                "Giving up on %s after %d 429 retries", request.url, retries - 1
            )
            return response

        delay = self._retry_after_seconds(response.headers.get("Retry-After"))
        if delay is None:
            delay = min(self.base_delay * (2 ** (retries - 1)), self.max_delay)
        else:
            delay = min(delay, self.max_delay)

        spider.logger.info(
            "429 on %s, backing off %.1fs (retry %d/%d)",
            request.url, delay, retries, self.max_retries,
        )

        engine = self.crawler.engine
        engine.pause()
        reactor.callLater(delay, engine.unpause)

        new_request = request.replace(dont_filter=True)
        new_request.meta["retry_times"] = retries
        return new_request

    @staticmethod
    def _retry_after_seconds(header_value):
        if not header_value:
            return None
        header_value = header_value.decode() if isinstance(header_value, bytes) else header_value
        if header_value.isdigit():
            return float(header_value)
        try:
            return max(parsedate_to_datetime(header_value).timestamp() - time(), 0)
        except (TypeError, ValueError):
            return None

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)
