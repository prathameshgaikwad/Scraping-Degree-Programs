# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

import json
import os

from itemadapter import ItemAdapter


class DurableJsonLinesPipeline:
    """Appends each item to <spider.name>.jsonl and fsyncs immediately.

    Guarantees scraped items survive a forced shutdown (kill/taskkill),
    unlike Scrapy's own JSON feed export, which only writes its closing
    bracket (and can lose buffered items) when the spider closes cleanly.
    """

    def open_spider(self, spider):
        self.file = open(f"{spider.name}.jsonl", "a", encoding="utf-8")

    def close_spider(self, spider):
        self.file.close()

    def process_item(self, item, spider):
        self.file.write(json.dumps(ItemAdapter(item).asdict(), ensure_ascii=False) + "\n")
        self.file.flush()
        os.fsync(self.file.fileno())
        return item
