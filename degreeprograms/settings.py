# Scrapy settings for degreeprograms project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "degreeprograms"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
DOWNLOAD_DELAY = 3
REDIRECT_ENABLED = True

# Serialize requests to mastersportal.com (one at a time) instead of
# racing several in parallel — that's what kept tripping its rate limit.
CONCURRENT_REQUESTS_PER_DOMAIN = 1

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# 429 handled by TooManyRequestsRetryMiddleware (honors Retry-After,
# pauses the engine), so it's excluded from Scrapy's default RETRY_HTTP_CODES.
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408]

# TooManyRequestsRetryMiddleware tuning (used when the server sends no
# Retry-After header). Observed in practice: mastersportal.com can 429 an
# IP for well over 15 minutes straight (900s cap + 10 retries still gave
# up before it lifted). Ceiling raised to 30 min/15 retries — a truly long
# ban still needs a rerun later, no amount of in-process backoff can force
# the server to unblock sooner. Override per-crawl with -s if needed.
TOOMANYREQUESTS_BASE_DELAY = 10
TOOMANYREQUESTS_MAX_DELAY = 1800
TOOMANYREQUESTS_MAX_RETRIES = 15

DOWNLOADER_MIDDLEWARES = {
    "degreeprograms.middlewares.TooManyRequestsRetryMiddleware": 543,
}

ITEM_PIPELINES = {
    "degreeprograms.pipelines.DurableJsonLinesPipeline": 300,
}

# mastersportal-spidy crawls these one by one (see spiders/mastersportal.py).
# Add/remove search URLs here instead of editing spider code.
MASTERSPORTAL_SEARCH_URLS = [
    "https://www.mastersportal.com/search/master?kw=artificial+intelligence",
    "https://www.mastersportal.com/search/master?kw=machine+learning",
    "https://www.mastersportal.com/search/master?kw=data+science",
    "https://www.mastersportal.com/search/master?kw=semiconductor",
    "https://www.mastersportal.com/search/master?kw=microelectronics",
    "https://www.mastersportal.com/search/master?kw=nanomaterials",
    "https://www.mastersportal.com/search/master?kw=materials+science",
]

# qs-spidy crawls these (see spiders/qs.py). Each is the real /pd/endpoint
# JSON search call (study_level=[3] is Masters; subjects is a QS subject-ID
# list) — found via the page's own DevTools XHR, not the page URL itself.
# Default combines Data Science & AI (4049), Materials Engineering (4051)
# and Materials Science (493) in one query. Add more URLs (other subject
# ID combos) as separate list entries.
QS_SEARCH_URLS = [
    "https://www.topuniversities.com/pd/endpoint?study_level=[3]&subjects=[4049,4051,493]",
]

SPIDER_MODULES = ["degreeprograms.spiders"]
NEWSPIDER_MODULE = "degreeprograms.spiders"

# Item persistence is handled by DurableJsonLinesPipeline (fsyncs each item
# to <spider-name>.jsonl immediately), not Scrapy's FEEDS export — FEEDS only
# writes output.json's closing bracket on a clean spider close, so a forced
# shutdown lost everything buffered in memory.

# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "degreeprograms (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = False

# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
#DOWNLOAD_DELAY = 3
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 16
#CONCURRENT_REQUESTS_PER_IP = 16

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "degreeprograms.middlewares.DegreeprogramsSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "degreeprograms.middlewares.DegreeprogramsDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "degreeprograms.pipelines.DegreeprogramsPipeline": 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
