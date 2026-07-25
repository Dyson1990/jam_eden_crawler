import json

import scrapy
from eden_crawler.items import DynamicItem, Asset


class CarSpider(scrapy.Spider):
    """
    汽车网站爬虫示例（XPath 版本）
    结构：品牌(1级) → 车系(2级) → 车型详情页
    """
    name = 'car'

    start_urls = ['https://www.autohome.com.cn/car/']

    custom_settings = {'DOWNLOAD_DELAY': 1}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.seen_brands = set()
        self.seen_series = set()

    def _make_url(self, raw, response):
        """Return absolute http URL, or None for invalid/dummy links."""
        if not raw:
            return None
        raw = raw.strip()
        if raw.startswith("javascript:") or raw == "#" or raw.startswith("void"):
            return None
        if raw.startswith("http"):
            return raw
        if raw.startswith("//"):
            return "https:" + raw
        return response.urljoin(raw)

    # ==================== 第1步：解析一级目录（品牌） ====================
    def parse(self, response):
        self.logger.info(f"正在解析一级目录页: {response.url}")

        brand_list = response.xpath(
            '//div[contains(@class, "brand-item")] | '
            '//div[contains(@class, "brand-list-item")] | '
            '//*[contains(@class, "item")]'
        )

        for brand in brand_list:
            brand_name = (
                brand.xpath('normalize-space(.//*[contains(@class, "brand-name")])').get('') or
                brand.xpath('normalize-space(.//h3)').get('') or
                brand.xpath('normalize-space(.//a)').get('')
            ).strip()

            brand_logo = brand.xpath('.//img/@src').get(default='')
            brand_url = brand.xpath('.//a/@href').get(default='')

            if not brand_name or brand_name in self.seen_brands:
                continue
            self.seen_brands.add(brand_name)

            brand_url = self._make_url(brand_url, response)

            self.logger.info(f"发现品牌: {brand_name}, Logo: {brand_logo}")

            item = DynamicItem()
            item["level"] = "level1"
            item["name"] = brand_name
            item["url"] = brand_url
            if brand_logo:
                item["logo"] = Asset(brand_logo, typ="blob")
            item["meta"] = json.dumps({"source": "brand_page"}, ensure_ascii=False)
            yield item

            if brand_url:
                yield scrapy.Request(
                    url=brand_url,
                    callback=self.parse_series,
                    meta={'brand_name': brand_name, 'level1_url': response.url},
                    priority=10,
                )

    # ==================== 第2步：解析二级目录（车系） ====================
    def parse_series(self, response):
        brand_name = response.meta['brand_name']
        self.logger.info(f"正在解析二级目录页 [{brand_name}]: {response.url}")

        series_list = response.xpath(
            '//*[contains(@class, "series-item")] | '
            '//*[contains(@class, "car-series-item")] | '
            '//*[contains(@class, "list-item")]'
        )

        for series in series_list:
            series_name = (
                series.xpath('normalize-space(.//*[contains(@class, "series-name")])').get('') or
                series.xpath('normalize-space(.//h4)').get('') or
                series.xpath('normalize-space(.//*[contains(@class, "name")])').get('')
            ).strip()

            series_image = (
                series.xpath('.//img/@src').get('') or
                series.xpath('.//*[contains(@class, "series-img")]//img/@src').get('')
            )
            series_url = series.xpath('.//a/@href').get(default='')

            if not series_name or series_name in self.seen_series:
                continue
            self.seen_series.add(series_name)

            series_url = self._make_url(series_url, response)

            self.logger.info(f"  发现车系: {series_name}, 图片: {series_image}")

            item = DynamicItem()
            item["level"] = "level2"
            item["name"] = series_name
            item["parent_name"] = brand_name
            item["url"] = series_url
            if series_image:
                item["image"] = Asset(series_image, typ="blob")
            item["meta"] = json.dumps({"brand": brand_name}, ensure_ascii=False)
            yield item

            if series_url:
                yield scrapy.Request(
                    url=series_url,
                    callback=self.parse_detail,
                    meta={
                        'brand_name': brand_name,
                        'series_name': series_name,
                        'level2_url': response.url,
                    },
                    priority=5,
                )

    # ==================== 第3步：解析详情页（车型） ====================
    def parse_detail(self, response):
        brand_name = response.meta['brand_name']
        series_name = response.meta['series_name']

        self.logger.info(f"正在解析详情页 [{brand_name}-{series_name}]: {response.url}")

        car_name = (
            response.xpath('normalize-space(//h1)').get('') or
            response.xpath('normalize-space(//*[contains(@class, "car-name")])').get('') or
            response.xpath('normalize-space(//*[contains(@class, "title")])').get('')
        ).strip()

        price = (
            response.xpath('normalize-space(//*[contains(@class, "price")])').get('') or
            response.xpath('normalize-space(//*[contains(@class, "guide-price")])').get('')
        ).strip()

        car_images = response.xpath(
            '//div[contains(@class, "gallery")]//img/@src | '
            '//div[contains(@class, "car-photo")]//img/@src'
        ).getall()
        car_images = [url for url in car_images if url.startswith('http')]

        specs = {}
        spec_rows = response.xpath(
            '//table[contains(@class, "spec-table")]//tr | '
            '//*[contains(@class, "param-row")]'
        )
        for row in spec_rows:
            key = (
                row.xpath('normalize-space(.//td[1])').get('') or
                row.xpath('normalize-space(.//*[contains(@class, "param-name")])').get('')
            ).strip()
            val = (
                row.xpath('normalize-space(.//td[last()])').get('') or
                row.xpath('normalize-space(.//*[contains(@class, "param-value")])').get('')
            ).strip()
            if key and val:
                specs[key] = val

        item = DynamicItem()
        item["brand"] = brand_name
        item["series"] = series_name
        item["name"] = car_name or f"{brand_name} {series_name}"
        item["price"] = price
        item["url"] = response.url
        if specs:
            item["specs"] = json.dumps(specs, ensure_ascii=False)
        if car_images:
            item["image"] = Asset(car_images[0], typ="blob")
            item["images"] = json.dumps(car_images[:5], ensure_ascii=False)
        yield item