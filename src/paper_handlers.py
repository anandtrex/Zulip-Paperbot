import re
import time
import requests
from urllib.parse import urlparse, unquote
import xml.etree.ElementTree as ET
from datetime import datetime


def paper_info_to_bibtex(paper_info, is_arxive=False):
    year = str(datetime.fromisoformat(paper_info['publish_date'].rstrip('Z')).year)
    bib_id = paper_info['authors'][0].split(' ')[1].lower() + year + re.sub(r'[^a-zA-Z]*$', '', paper_info['title'].split(' ')[0].lower())
    bib = (f"@misc{{{bib_id},\n"
           f"      title = {{{paper_info['title']}}},\n"
           f"      author = {{{' and '.join(', '.join([a.split()[-1], ' '.join(a.split()[:-1])]) for a in paper_info['authors'])}}},\n"
           f"      year = {{{year}}},\n"
           f"      url = {{{paper_info['link']}}}")
    if is_arxive:
        add = (",\n"
               f"      eprint = {{{paper_info['id']}}},\n"
               f"      archivePrefix = {{arXiv}},\n"
               f"      primaryClass = {{{paper_info['category']}}}\n")
    else:
        add = "\n"
    return bib + add + "}" 


# arXiv and Crossref ask API clients to identify themselves; anonymous clients get throttled first.
HEADERS = {'User-Agent': 'ZulipNotionPaperBot/1.0 (+https://github.com/anandtrex/ZulipNotionPaperBot)'}


class paperHandler:

    def __init__(self):
        self.log = []

    def note(self, reason, response=None):
        """Records why no info was returned, for the bot's log."""
        if response is not None:
            reason += f" (HTTP {response.status_code}: {response.text[:200].strip()!r})"
        self.log.append(reason)

    def flush_log(self):
        out = self.log
        self.log = []
        return out


class ArxivUnavailableError(RuntimeError):
    pass


class arxiveHandler(paperHandler):

    def extract_ids(self, message_content):
        arxiv_regex = r'\b(?:arXiv:)?(\d{4}\.\d{5})\b|https?://arxiv\.org/abs/(\d{4}\.\d{5})'
        matches = re.findall(arxiv_regex, message_content)
        arxiv_ids = [arxiv_id for match in matches for arxiv_id in match if arxiv_id]
        return arxiv_ids

    # arXiv asks API users to wait at least 3 seconds between requests.
    MAX_ATTEMPTS = 4

    def __init__(self, fallback=None):
        """fallback: optional zoteroTranslationHandler, used to look papers up when the arXiv API is unavailable."""
        super().__init__()
        self.fallback = fallback

    def query_api(self, arxiv_id):
        url = f'https://export.arxiv.org/api/query?id_list={arxiv_id}'
        last_attempt = self.MAX_ATTEMPTS - 1
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                response = requests.get(url, headers=HEADERS, timeout=30)
            except requests.exceptions.Timeout:
                if attempt == last_attempt:
                    raise ArxivUnavailableError("the arXiv API is not responding, please try again in a few minutes") from None
                time.sleep(3 * 2 ** attempt)
                continue
            if response.status_code not in (429, 503) or attempt == last_attempt:
                return response
            retry_after = response.headers.get('Retry-After', '')
            time.sleep(max(int(retry_after) if retry_after.isdigit() else 0, 3 * 2 ** attempt))

    def get_info(self, arxiv_id):
        try:
            return self.get_info_from_api(arxiv_id)
        except ArxivUnavailableError as e:
            if self.fallback is None:
                raise
            print(f"arXiv API unavailable for {arxiv_id} ({e}), falling back to the Zotero translation server")
            try:
                info = self.fallback.search(f"arXiv:{arxiv_id}")
            except RuntimeError as fallback_error:
                raise ArxivUnavailableError(f"{e} (fallback also failed: {fallback_error})") from None
            finally:
                self.log.extend(self.fallback.flush_log())
            if info:
                info.update({"id": arxiv_id, "category": None, "github_repo": self.get_github_url(arxiv_id),
                             "link": info.get('link') or f"http://arxiv.org/abs/{arxiv_id}"})
            return info

    def get_info_from_api(self, arxiv_id):
        response = self.query_api(arxiv_id)
        if response.status_code in (429, 503):
            raise ArxivUnavailableError(f"the arXiv API is rate limiting requests (HTTP {response.status_code}), please try again in a few minutes")
        if response.status_code != 200:
            self.note("arXiv API request failed", response)
            return
        root = ET.fromstring(response.content)
        entry = root.find('{http://www.w3.org/2005/Atom}entry')
        if entry is None:
            self.note(f"arXiv API returned no entry for {arxiv_id}", response)
        else:
            title = entry.find('{http://www.w3.org/2005/Atom}title').text.strip().replace("\n", " ")
            authors = [author.find('{http://www.w3.org/2005/Atom}name').text for author in entry.findall('{http://www.w3.org/2005/Atom}author')]
            abstract = entry.find('{http://www.w3.org/2005/Atom}summary').text.strip().replace("\n", " ")
            link = entry.find('{http://www.w3.org/2005/Atom}id').text
            publish_date = entry.find('{http://www.w3.org/2005/Atom}published').text
            category_element = entry.find('{http://www.w3.org/2005/Atom}category')
            if category_element is not None:
                primary_category = category_element.attrib.get('term', '')
            else:
                primary_category = None
            year = datetime.fromisoformat(publish_date.rstrip('Z')).year
            info = {"title": title, "authors": authors, "abstract": abstract, "link": link, "publish_date": publish_date,
                    "year": year, "id": arxiv_id, "category": primary_category, "github_repo": self.get_github_url(arxiv_id)}
            bibtex = paper_info_to_bibtex(info, is_arxive=False)
            info['bibtex'] = bibtex
            return info


    def get_all_repositories(self, paper_id):
        base_url = f"https://paperswithcode.com/api/v1/papers/{paper_id}/repositories/"
        repositories = []
        while base_url:
            response = requests.get(base_url)
            if response.status_code == 200:
                data = response.json()
                repositories.extend(data.get('results', []))
                base_url = data.get('next')
            else:
                break
        return repositories

    def get_official_repositories(self, paper_id):
        all_repositories = self.get_all_repositories(paper_id)
        official_repos = [repo for repo in all_repositories if repo.get('is_official') == True]
        return official_repos

    def get_github_url(self, arxiv_id):
        # Papers with Code shut down in 2025; use Hugging Face Papers instead.
        try:
            arxiv_id = arxiv_id.split("v")[0]
            r = requests.get(f"https://huggingface.co/api/papers/{arxiv_id}", timeout=10)
            if r.status_code == 200:
                return r.json().get("githubRepo")
        except Exception as e:
            print(f"GitHub lookup failed for {arxiv_id}: {e}")
        return None


class openreviewHandler(paperHandler):

    def extract_ids(self, message_content):
        openreview_regex = r'https?://openreview\.net/(forum|pdf)\?id=([A-Za-z0-9_]+)'
        matches = re.findall(openreview_regex, message_content)
        openreview_ids = [match[1] for match in matches]
        return openreview_ids

    def get_info(self, openreview_id):
        api2 = True
        api_url = f"https://api2.openreview.net/notes?id={openreview_id}"
        response = requests.get(api_url)
        if response.status_code != 200:
            api2 = False
            api_url = f"https://api.openreview.net/notes?id={openreview_id}"
            response = requests.get(api_url)
            if response.status_code != 200:
                self.note("OpenReview API request failed", response)
                return
        paper_data = response.json().get('notes', [])
        if not paper_data:
            self.note(f"OpenReview API returned no notes for {openreview_id}", response)
        else:
            paper = paper_data[0]
            title = paper['content']['title']['value'] if api2 else paper['content']['title'].replace("\n" " ")
            authors = paper['content']['authors']['value'] if api2 else paper['content']['authors']
            abstract = paper['content']['abstract']['value'].replace("\n", " ") if api2 else paper['content']['abstract'].replace("\n", " ")
            link = f"https://openreview.net/forum?id={openreview_id}"
            publish_date = datetime.utcfromtimestamp(paper.get('cdate') / 1000).isoformat() + 'Z'
            year = datetime.fromisoformat(publish_date.rstrip('Z')).year
            info = {"title": title, "authors": authors, "abstract": abstract, "link": link,
                    "publish_date": publish_date, "year": year}
            bibtex = paper_info_to_bibtex(info, is_arxive=False)
            info['bibtex'] = bibtex
            return info


class zoteroTranslationHandler(paperHandler):
    """Fetches metadata for whitelisted sites via a Zotero translation-server
    (https://github.com/zotero/translation-server), which runs the same site
    translators as the Zotero Connector browser extension."""

    DEFAULT_DOMAINS = [
        'aclanthology.org', 'proceedings.neurips.cc', 'papers.nips.cc', 'proceedings.mlr.press', 'jmlr.org',
        'openaccess.thecvf.com', 'ojs.aaai.org', 'ijcai.org', 'dl.acm.org', 'ieeexplore.ieee.org',
        'link.springer.com', 'nature.com', 'science.org', 'sciencedirect.com', 'pnas.org', 'cell.com',
        'elifesciences.org', 'journals.plos.org', 'frontiersin.org', 'biorxiv.org', 'medrxiv.org',
        'pubmed.ncbi.nlm.nih.gov', 'ncbi.nlm.nih.gov', 'semanticscholar.org', 'doi.org', 'jneurosci.org',
    ]
    # Elsevier article ID, e.g. S0896-6273(24)00001-5 in cell.com URLs or S0896627324000015 in sciencedirect.com URLs.
    # Journals with HighWire-style article URLs (/content/<volume>/<issue>/<first page>), by ISSN.
    HIGHWIRE_JOURNALS = {'jneurosci.org': '0270-6474'}
    HIGHWIRE_PATH = re.compile(r'/content/(\d+)/\d+/(e?\d+)')
    ELSEVIER_PII = re.compile(r'S\d{4}-?\d{3}[\dX]\(?\d{2}\)?\d{5}-?[\dX]', re.IGNORECASE)
    PAPER_ITEM_TYPES = {'journalArticle', 'conferencePaper', 'preprint', 'report', 'thesis', 'book', 'bookSection', 'manuscript'}

    def __init__(self, server_url='http://localhost:1969', domains=None, timeout=30):
        super().__init__()
        self.server_url = server_url.rstrip('/')
        self.domains = [d.lower() for d in (domains if domains is not None else self.DEFAULT_DOMAINS)]
        self.timeout = timeout

    def is_whitelisted(self, url):
        host = (urlparse(url).hostname or '').lower()
        return any(host == d or host.endswith('.' + d) for d in self.domains)

    def extract_ids(self, message_content):
        # Stop at characters that delimit URLs in markdown/text, then drop trailing punctuation. Balanced
        # parentheses are kept, as in cell.com URLs (S0896-6273(24)00001-5), so that the ")" closing a
        # markdown [text](url) link still ends the URL.
        url_char = r'[^\s<>()\[\]"\'`]'
        urls = re.findall(rf'https?://(?:{url_char}|\({url_char}*\))+', message_content)
        urls = [u.rstrip('.,;:!?\'"') for u in urls]
        return list(dict.fromkeys(u for u in urls if self.is_whitelisted(u)))

    def get_info(self, url):
        # Some publishers (cell.com, sciencedirect.com, jneurosci.org) block the translation server with a
        # Cloudflare challenge, so look their papers up by DOI instead, which the translation server resolves
        # via Crossref.
        doi = self.find_doi(url)
        if doi:
            info = self.search(doi)
            if info:
                info['link'] = url
                return info
        return self.translate('web', url)

    def find_doi(self, url):
        pii = self.find_pii(url)
        if pii:
            return self.pii_to_doi(pii)
        host = (urlparse(url).hostname or '').lower()
        issn = next((issn for d, issn in self.HIGHWIRE_JOURNALS.items() if host == d or host.endswith('.' + d)), None)
        match = self.HIGHWIRE_PATH.search(urlparse(url).path)
        if issn and match:
            return self.citation_to_doi(issn, *match.groups())
        return None

    def find_pii(self, url):
        match = self.ELSEVIER_PII.search(unquote(url))
        return re.sub(r'[-()]', '', match.group(0)).upper() if match else None

    def pii_to_doi(self, pii):
        items = self.query_crossref(f"Elsevier PII {pii}", {'filter': f'alternative-id:{pii}', 'select': 'DOI', 'rows': 1})
        return items[0]['DOI'] if items else None

    def citation_to_doi(self, issn, volume, first_page):
        description = f"ISSN {issn} volume {volume} page {first_page}"
        items = self.query_crossref(description, {'query.bibliographic': f"{volume} {first_page}", 'filter': f'issn:{issn}',
                                                  'select': 'DOI,volume,page', 'rows': 5})
        # The search is fuzzy, so only accept an exact volume and first-page match.
        for item in items or []:
            if item.get('volume') == volume and item.get('page', '').split('-')[0].lower() == first_page.lower():
                return item['DOI']
        if items:
            self.note(f"Crossref has no exact match for {description}")
        return None

    def query_crossref(self, description, params):
        """Returns the matching Crossref works, or None (with a note on why) if there are none."""
        try:
            response = requests.get('https://api.crossref.org/works', headers=HEADERS, timeout=self.timeout, params=params)
            if response.status_code != 200:
                self.note(f"Crossref lookup of {description} failed", response)
                return None
            items = response.json()['message']['items']
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            self.note(f"Crossref lookup of {description} failed: {e}")
            return None
        if not items:
            self.note(f"Crossref has no DOI for {description}", response)
        return items

    def search(self, identifier):
        """Looks up a DOI, ISBN, PMID or arXiv ID (e.g. 'arXiv:2609.04170')."""
        return self.translate('search', identifier)

    def translate(self, endpoint, query):
        try:
            response = requests.post(f"{self.server_url}/{endpoint}", data=query.encode('utf-8'),
                                     headers={'Content-Type': 'text/plain'}, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            print(f"Zotero translation server unavailable at {self.server_url}: {e}")
            raise RuntimeError(f"the Zotero translation server is not reachable at {self.server_url}") from None
        if response.status_code != 200:
            # 300 = multiple items on the page, 501 = no translator for the page or identifier
            self.note(f"Zotero translation server /{endpoint} request failed for {query}", response)
            return
        all_items = response.json()
        items = [item for item in all_items if item.get('itemType') in self.PAPER_ITEM_TYPES]
        if not items:
            item_types = [item.get('itemType') for item in all_items]
            self.note(f"Zotero translation server found no paper for {query} (item types: {item_types or 'none'})")
            return
        item = items[0]

        creators = item.get('creators', [])
        authors = [c for c in creators if c.get('creatorType') == 'author'] or creators
        authors = [c.get('name') or f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() for c in authors]
        year_match = re.search(r'\b(\d{4})\b', item.get('date', ''))
        info = {"title": item.get('title', ''), "authors": authors,
                "abstract": (item.get('abstractNote') or '').replace("\n", " "),
                "link": item.get('url') or (query if endpoint == 'web' else None), "publish_date": item.get('date'),
                "year": int(year_match.group(1)) if year_match else None,
                "bibtex": self.get_bibtex(item)}
        return info

    def get_bibtex(self, item):
        try:
            response = requests.post(f"{self.server_url}/export", params={'format': 'bibtex'},
                                     json=[item], timeout=self.timeout)
            if response.status_code == 200:
                return response.text.strip()
        except requests.exceptions.RequestException as e:
            print(f"BibTeX export failed: {e}")
        return ""
