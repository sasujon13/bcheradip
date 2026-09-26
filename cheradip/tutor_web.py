"""Bounded public web references for a curriculum title, with private-network blocking."""
import hashlib
import ipaddress
import socket
from urllib.parse import urlparse
from xml.etree import ElementTree
from html.parser import HTMLParser
import requests
from django.core.cache import cache


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'footer'):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'footer') and self.hidden:
            self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 80, 443):
        return False
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(x[4][0]).is_global for x in addresses)
    except (OSError, ValueError):
        return False


def article(url):
    for _ in range(3):
        if not public_url(url):
            return ''
        with requests.get(url, timeout=(3, 5), stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                from urllib.parse import urljoin
                url = urljoin(url, response.headers.get('Location', '')); continue
            response.raise_for_status()
            if 'text/html' not in response.headers.get('Content-Type', ''):
                return ''
            chunks, size = [], 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 400000:
                    break
                chunks.append(chunk)
            parser = TextOnly(); parser.feed(b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace'))
            return ' '.join(parser.parts)[:2000]
    return ''


def search(title, subject=''):
    if not title:
        return {'text': '', 'sources': [], 'status': 'No resolved topic for web lookup'}
    query = title[:200] + ' ' + subject[:100]
    key = 'tutor:web:v4:' + hashlib.sha256(query.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    sources, blocks = [], []
    # For these C concepts, read the primary manual instead of generic search
    # hits for the letter C or repository listings. Never invent an excerpt.
    programming = 'প্রোগ্রামিং' in subject or 'programming' in subject.lower()
    if programming:
        for terms, name, page in [
            (('চলক', 'variable'), 'GNU C: Variables', 'Variables'),
            (('ধ্রুবক', 'constant'), 'GNU C: Constants', 'Constants'),
        ]:
            if not any(term in title.lower() for term in terms):
                continue
            url = f'https://www.gnu.org/software/c-intro-and-ref/manual/html_node/{page}.html'
            try:
                content = article(url)
            except (requests.RequestException, ValueError):
                content = ''
            if content:
                label = 'W' + str(len(sources) + 1)
                sources.append({'reference': label, 'title': name, 'url': url, 'article_read': True})
                blocks.append(f'[{label}] {name}\nURL: {url}\n{content}')
    try:
        queries = [query]
        if 'প্রোগ্রামিং' in subject or 'programming' in subject.lower():
            concepts = [english for bengali, english in [('চলক', 'variables'), ('ধ্রুবক', 'constants'),
                ('ওয়ার্ড', 'keywords'), ('ওয়ার্ড', 'keywords'), ('ডেটাটাইপ', 'data types'),
                ('অ্যালগরিদম', 'algorithms'), ('ফাংশন', 'functions'), ('অ্যারে', 'arrays')]
                if bengali in title]
            if concepts:
                queries.append('C programming ' + ' '.join(dict.fromkeys(concepts)))
        queries.append('"' + title[:200] + '"')
        items = []
        for search_query in ([] if sources else queries):
            response = requests.get('https://www.bing.com/search', params={'q': search_query, 'format': 'rss'}, timeout=(3, 8))
            response.raise_for_status()
            root = ElementTree.fromstring(response.content[:500000])
            items = root.findall('./channel/item')
            if items:
                break
        for item in items[:3]:
            url = item.findtext('link', '')
            if not public_url(url):
                continue
            name = item.findtext('title', '')
            snippet = item.findtext('description', '')
            if programming and (name.strip().lower() == 'c - wikipedia' or
                                'github.com/topics/' in url):
                continue
            try:
                content = article(url)
            except (requests.RequestException, ValueError):
                content = ''
            label = 'W' + str(len(sources) + 1)
            sources.append({'reference': label, 'title': name, 'url': url, 'article_read': bool(content)})
            blocks.append(f'[{label}] {name}\nURL: {url}\n' + (content or 'Search excerpt only: ' + snippet))
    except (requests.RequestException, ValueError, ElementTree.ParseError):
        pass
    result = {'text': '\n\n'.join(blocks), 'sources': sources, 'status': 'Web references loaded' if sources else 'Web search unavailable; using stored references'}
    cache.set(key, result, 900 if sources else 30)
    return result
