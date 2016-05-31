import scrapy
import os
import lxml.etree as et
from tidylib import tidy_document as TD
import shutil
from PIL import Image
from lxml.etree import HTMLParser
import shutil
try:
    from urllib.request import urlretrieve  # Python 3
except ImportError:
    from urllib import urlretrieve

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

OUT_DIR = 'book/'
TMPL_DIR = 'tmpl'


class Template:
    def __init__(self, filename):
        f = open(filename)
        self.template = f.read()
        self.content = self.template

    def new_content(self):
        self.content = self.template
        return self

    def set_title(self, title):
        self.content = self.content.replace('__TITLE__', title)
        return self

    def set_content_type(self, type):
        self.content = self.content.replace('__CONTENT_TYPE__', type)
        return self

    def set_description(self, description):
        self.content = self.content.replace('__DESCRIPTION__', description)
        return self

    def set_body(self, body):
        self.content = self.content.replace('__BODY__', body)
        return self

    def replace(self, placeholder, value):
        self.content = self.content.replace(placeholder, value)
        return self


class BlogSpider(scrapy.Spider):
    name = 'blogspider'
    # start_urls = ['http://www.vinadia.org/dem-giua-ban-ngay-vu-thu-hien/']
    start_urls = ['http://www.vinadia.org/nhan-van-giai-pham-thuy-khue/']
    # start_urls = ['http://www.vinadia.org/ai-giet-anh-em-ngo-dinh-diem/']
    html_tmpl = Template(os.path.join(TMPL_DIR, 'html.html'))
    content_tmpl = Template(os.path.join(TMPL_DIR, 'content.opf'))
    toc_tmpl = Template(os.path.join(TMPL_DIR, 'toc.ncx'))
    index = 0
    html_dir = os.path.join(OUT_DIR, 'html')

    def __init__(self, name=None, **kwargs):
        super(BlogSpider, self).__init__(name, **kwargs)

    def parse2(self, response):
        f = open('test.html', 'w')
        f.write(self.remove_tag_by_class(response.text, 'ssba'))

    def parse(self, response):
        self.html_tmpl.new_content()
        self.fill_meta(response)

        self.download_cover(response)

        content = response.css('div#content').extract_first()
        self.html_tmpl.set_body(content)

        content = self.html_tmpl.content
        content = self.remove_tag_by_class(content, 'ssba')
        content = self.remove_tag_by_class(content, 'breadcrumb')
        content = self.fix_xhtml(content)

        if os.path.isdir(self.html_dir):
            shutil.rmtree(self.html_dir)
        os.makedirs(self.html_dir)

        self.html_tmpl.set_body(content)
        f = open(os.path.join(self.html_dir, '00.html'), 'w')
        f.write(content)

        nav_points = ''
        manifest_itmes = ''
        toc_refs = ''

        chapters = response.css('#sidebar ul li a')
        for c in chapters:
            self.index += 1
            href = c.css('::attr(href)').extract_first()
            text = c.css('::text').extract_first()
            request = scrapy.Request(href, callback=self.parse_chapter)
            request.meta['_index'] = self.index
            yield request

            nav_points += """
            <navPoint id="a{0:0>2}" playOrder="{0}">
                <navLabel>
                    <text>{1}</text>
                </navLabel>
                <content src="html/{0:0>2}.html"/>
            </navPoint>""".format(self.index, text)

            manifest_itmes += """
            <item href="html/{0:0>2}.html" id="id{0:0>2}" media-type="application/x-dtbncx+xml"/>""".format(self.index)

            toc_refs += """
            <itemref idref="id{:0>2}"/>""".format(self.index)

        # Build toc.ncx
        title = response.xpath('//title/text()').extract_first()
        self.toc_tmpl.replace('__NAV_POINTS__', nav_points)
        self.toc_tmpl.replace('__TITLE__', title)
        f = open(os.path.join(OUT_DIR, 'toc.ncx'), 'w')
        f.write(self.toc_tmpl.content)

        # Build content.opf
        self.content_tmpl.replace('__TITLE__', title)
        self.content_tmpl.replace('__MANIFEST_ITEMS__', manifest_itmes)
        self.content_tmpl.replace('__TOC_REFS__', toc_refs)
        f = open(os.path.join(OUT_DIR, 'content.opf'), 'w')
        f.write(self.content_tmpl.content)

    def parse_chapter(self, response):
        self.html_tmpl.new_content()
        self.fill_meta(response)

        content = response.css('div#content').extract_first()
        self.html_tmpl.set_body(content)

        content = self.html_tmpl.content
        content = self.remove_tag_by_class(content, 'ssba')
        content = self.remove_tag_by_class(content, 'breadcrumb')
        content = self.fix_xhtml(content)

        f = open(os.path.join(self.html_dir, '{:0>2}.html'.format(response.meta['_index'])), 'w')
        f.write(content)

    def fill_meta(self, response):
        title = response.xpath('//title/text()').extract_first()
        content_type = response.xpath('//meta[@http-equiv="Content-Type"]/@content').extract_first()
        description = response.xpath('//meta[@name="description"]/@content').extract_first()
        self.html_tmpl.set_title(title)
        self.html_tmpl.set_content_type(content_type)
        self.html_tmpl.set_description(description)

    def remove_tag_by_class(self, content, cls):
        # return content
        parser = HTMLParser(encoding='utf-8', recover=True)
        tree = et.parse(StringIO(content), parser)
        for element in tree.xpath('//div[contains(@class, "{}")]'.format(cls)):
            element.getparent().remove(element)
        return et.tostring(tree, encoding='utf-8', with_tail=False).decode('utf-8')
        # return "".join([e.decode('utf-8') for e in et.tostringlist(tree)])

    def fix_xhtml(self, content):
        v, e = TD(content, options={'output-xhtml': 1})
        return v

    def download_cover(self, response):
        shutil.copy(os.path.join(TMPL_DIR, 'cover.jpeg'), os.path.join(OUT_DIR, 'cover.jpeg'))
        src = response.css('div#content img::attr(src)').extract_first()
        if src:
            _, r = urlretrieve(src, 'cover')
            type = r.get_content_type().split('/')[1]
            shutil.move('cover', 'cover.' + type)
            if type != 'jpeg':
                img = Image.open('cover.' + type)
                img.save('cover.jpeg')
            shutil.move('cover.jpeg', os.path.join(OUT_DIR, 'cover.jpeg'))


