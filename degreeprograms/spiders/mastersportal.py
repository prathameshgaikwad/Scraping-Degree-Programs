import scrapy


class mastersportal_spidy(scrapy.Spider):
    """Crawls a list of mastersportal.com search URLs, one after another.

    URLs come from the MASTERSPORTAL_SEARCH_URLS setting so new searches
    (keywords, locations, filters) can be added without touching code.
    CONCURRENT_REQUESTS_PER_DOMAIN=1 in settings.py keeps this and every
    other mastersportal.com request serialized against the same rate limit.
    """

    name = 'mastersportal-spidy'

    async def start(self):
        for url in self.settings.getlist('MASTERSPORTAL_SEARCH_URLS'):
            yield scrapy.Request(url, callback=self.parse)

    def parse(self, response):
        for card in response.css('section.Card.ProgrammeCard'):
            location = card.css('span.Locations::text').get(default='').strip()
            city, _, country = location.partition(',')
            item = {
                'name': card.css('h2.Title::text').get(default='').strip() or None,
                'degree_program': card.css('span.Tag::text').get(default='').strip() or None,
                'university_name': card.css('strong.OrganisationName::text').get(default='').strip() or None,
                'country': country.strip() or None,
                'city': city.strip() or None,
                'fee': card.css('span.CurrentPrice b::text').get(default='').strip() or None,
                'program_duration': card.css('span.Duration::text').get(default='').strip() or None,
                'source_search_url': response.url,
            }
            detail_url = card.css('a.VisitProgramme::attr(href)').get()
            if detail_url:
                yield response.follow(detail_url, callback=self.parse_detail, meta={'item': item})
            else:
                yield item

        next_page = response.css('nav.Pagination a[name="next"]::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_detail(self, response):
        item = response.meta['item']
        item['deadline'] = response.css('.DeadlinesList time::attr(datetime)').get(default='').strip() or None
        item['program_duration'] = (
            response.css('.DurationList .Duration::text').get(default='').strip() or item['program_duration']
        )
        item['fee'] = (
            response.css('.TuitionFeeContainer[data-target="international"] .Title::text').get(default='').strip()
            or item['fee']
        )
        item['requirements'] = {
            'ielts': response.css('.IELTSCard .Score span::text').get(default='').strip() or None,
            'gre': response.css('.GRECard .ScoreContainer::text').get(default='').strip() or None,
            'gpa': response.css('.GPACard .Score span::text').get(default='').strip() or None,
        }
        yield item
