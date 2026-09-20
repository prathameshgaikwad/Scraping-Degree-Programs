import json
import re

import scrapy


class qs_spidy(scrapy.Spider):
    """Crawls topuniversities.com (QS) via its real JSON search endpoint
    (/pd/endpoint) instead of the JS-rendered HTML page — found by
    inspecting the page's own XHR call in DevTools.

    QS_SEARCH_URLS in settings.py holds one endpoint URL per saved filter
    (study_level/subjects); this spider walks every page of each one.
    """

    name = 'qs-spidy'
    # topuniversities.com/robots.txt states "crawl-delay: 10" — honored here
    # even though ROBOTSTXT_OBEY is off project-wide.
    custom_settings = {'DOWNLOAD_DELAY': 10}

    def _headers(self):
        return {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'}

    async def start(self):
        for url in self.settings.getlist('QS_SEARCH_URLS'):
            yield scrapy.Request(
                self._set_page(url, 1),
                callback=self.parse,
                headers=self._headers(),
                meta={'page': 1, 'base_url': url},
            )

    def parse(self, response):
        payload = json.loads(response.text)
        for row in payload.get('data', []):
            yield {
                'name': row.get('program_name'),
                'university_name': row.get('uni_name'),
                'campus_name': ', '.join(row.get('campus_name') or []),
                'region': ', '.join(row.get('region') or []),
                'country': ', '.join(row.get('country') or []),
                'city': ', '.join(row.get('city') or []),
                'rankings_position': row.get('rankings_position'),
                'program_url': response.urljoin(row['program_url']) if row.get('program_url') else None,
                'university_url': response.urljoin(row['uni_url']) if row.get('uni_url') else None,
                'source_search_url': response.meta['base_url'],
            }

        page = response.meta['page']
        total_pages = -(-payload.get('total_count', 0) // payload.get('pagerlimit', 10) or 1)
        if page < total_pages:
            base_url = response.meta['base_url']
            yield scrapy.Request(
                self._set_page(base_url, page + 1),
                callback=self.parse,
                headers=self._headers(),
                meta={'page': page + 1, 'base_url': base_url},
            )

    @staticmethod
    def _set_page(url, page):
        if re.search(r'[?&]page=\d+', url):
            return re.sub(r'page=\d+', f'page={page}', url)
        sep = '&' if '?' in url else '?'
        return f'{url}{sep}page={page}'
