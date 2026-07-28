import json
import scrapy
from eden_crawler.items import DynamicItem


class IpCheckSpider(scrapy.Spider):
    name = "ip_test"
    custom_settings = {"ITEM_PIPELINES": {}}

    async def start(self):
        yield scrapy.Request("http://ip-api.com/json", callback=self.parse)

    def parse(self, response):
        data = json.loads(response.text)
        item = DynamicItem()
        item["ip"] = data.get("query")
        item["country"] = data.get("country")
        item["region"] = data.get("regionName")
        item["city"] = data.get("city")
        item["org"] = data.get("org")
        # 供 notifier 展示的汇总 name
        item["name"] = f'{data.get("query")} — {data.get("country")} {data.get("regionName")} {data.get("city")}'
        yield item
