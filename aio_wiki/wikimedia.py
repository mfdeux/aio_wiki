import functools
import re

from .exceptions import (DisambiguationError, HTTPTimeoutError, ODD_ERROR_MESSAGE, PageError, RedirectError,
                         WikipediaException)
from .http_client import HTTPClient


def cached_property(f):
    @functools.wraps(f)
    def wrapped(self, *args, **kwargs):
        if not getattr(self, '_{}'.format(f.__name__), False):
            return f(self, *args, **kwargs)
        return getattr(self, '_{}'.format(f.__name__))

    return wrapped


class Client:

    def __init__(self, lang: str = 'en', user_agent: str = 'wikipedia (https://github.com/goldsmith/Wikipedia/)',
                 proxy: str = None, rate_limit: int = 60):
        self.api_url = 'http://' + lang.lower() + '.wikipedia.org/w/api.php'
        self.http_client = HTTPClient(user_agent=user_agent, proxy=proxy, rate_limit=rate_limit)

    def set_lang(self, lang: str):
        """
        Change the language of the API being requested.
        Set `prefix` to one of the two letter prefixes found on the `list of all Wikipedias <http://meta.wikimedia.org/wiki/List_of_Wikipedias>`_.
        After setting the language, the cache for ``search``, ``suggest``, and ``summary`` will be cleared.
        .. note:: Make sure you search for page titles in the language that you have set.
        """
        self.api_url = 'http://{}.wikipedia.org/w/api.php'.format(lang.lower())

    def set_user_agent(self, user_agent: str):
        """
        Set the User-Agent string to be used for all requests.
        Arguments:
        * user_agent_string - (string) a string specifying the User-Agent header
        """
        self.http_client.headers.update({'User-Agent': user_agent})

    async def api(self, **kwargs):

        """
                Make a request to the Wikipedia API using the given search parameters.
                Returns a parsed dict of the JSON response.
                """

        kwargs['format'] = 'json'
        if not 'action' in kwargs:
            kwargs['action'] = 'query'

        try:
            resp = await self.http_client.get(url=self.api_url, params=kwargs, is_json=True)
        except:
            raise

        return resp

        #     if 'error' in resps:
        #         if resps['error']['info'] in ('HTTP request timed out.', 'Pool queue is full'):
        #             raise HTTPTimeoutError('{0}|{1}'.format(latitude, longitude))
        #         else:
        #             raise WikipediaException(resps['error']['info'])

    async def ping(self):
        return await self.api()

    async def search(self, query: str, limit: int = 10, suggestion: bool = False):
        """
        Do a Wikipedia search for `query`.
        Keyword arguments:
        * results - the maxmimum number of results returned
        * suggestion - if True, return results and suggestion (if any) in a tuple
        """

        query_params = {
            'list': 'search',
            # 'srwhat': what,
            'srprop': '',
            'srlimit': limit,
            'limit': limit,
            'srsearch': query,
            'srinfo': 'suggestion' if suggestion else ''
        }

        resp = await self.api(**query_params)

        if 'error' in resp:
            if resp['error']['info'] in ('HTTP request timed out.', 'Pool queue is full'):
                raise HTTPTimeoutError(query)
            else:
                raise WikipediaException(resp['error']['info'])

        search_results = (d['title'] for d in resp['query']['search'])

        if suggestion:
            if resp['query'].get('searchinfo'):
                return list(search_results), resp['query']['searchinfo']['suggestion']
            else:
                return list(search_results), None

        return list(search_results)

    async def geosearch(self, latitude: float, longitude: float, radius: int = 5000, title: str = None,
                        limit: int = 100):
        """
        Do a wikipedia geo search for `latitude` and `longitude`
        using HTTP API described in http://www.mediawiki.org/wiki/Extension:GeoData
        Arguments:
        * latitude (float)
        * longitude (float)
        Keyword arguments:
        * title - The title of an article to search for
        * results - the maximum number of results returned
        * radius - Search radius in meters. The value must be between 10 and 10000
        """

        query_params = {
            'list': 'geosearch',
            'gsradius': radius,
            'gscoord': '{0}|{1}'.format(latitude, longitude),
            'gslimit': limit,
            'title': title if title else ''
        }

        resp = await self.api(**query_params)

        if 'error' in resp:
            if resp['error']['info'] in ('HTTP request timed out.', 'Pool queue is full'):
                raise HTTPTimeoutError('{0}|{1}'.format(latitude, longitude))
            else:
                raise WikipediaException(resp['error']['info'])

        search_pages = resp['query'].get('pages', None)
        if search_pages:
            search_results = (v['title'] for k, v in search_pages.items() if k != '-1')
        else:
            search_results = (d['title'] for d in resp['query']['geosearch'])

        return list(search_results)

    async def suggest(self, query: str):
        """
        Get a Wikipedia search suggestion for `query`.
        Returns a string or None if no suggestion was found.
        """

        query_params = {
            'list': 'search',
            'srinfo': 'suggestion',
            'srprop': '',
            'srsearch': query
        }

        resp = await self.api(**query_params)

        if resp['query'].get('search'):
            return resp['query']['search']

        if 'error' in resp:
            if resp['error']['info'] in ('HTTP request timed out.', 'Pool queue is full'):
                raise HTTPTimeoutError('')
            else:
                raise WikipediaException(resp['error']['info'])

        return

    async def random(self, pages=1):
        """
        Get a list of random Wikipedia article titles.
        http://en.wikipedia.org/w/api.php?action=query&list=random&rnlimit=5000&format=jsonfm
        .. note:: Random only gets articles from namespace 0, meaning no Category, User talk, or other meta-Wikipedia pages.
        Keyword arguments:
        * pages - the number of random pages returned (max of 10)
        """
        query_params = {
            'list': 'random',
            'rnnamespace': 0,
            'rnlimit': pages,
        }

        resp = await self.api(**query_params)

        titles = [page['title'] for page in resp['query']['random']]

        if len(titles) == 1:
            return titles[0]

        return titles

    async def summary(self, title, sentences=0, chars=0, auto_suggest=True, redirect=True):
        """
        Plain text summary of the page.
        .. note:: This is a convenience wrapper - auto_suggest and redirect are enabled by default
        Keyword arguments:
        * sentences - if set, return the first `sentences` sentences (can be no greater than 10).
        * chars - if set, return only the first `chars` characters (actual text returned may be slightly longer).
        * auto_suggest - let Wikipedia find a valid page title for the query
        * redirect - allow redirection without raising RedirectError
        """

        # use auto_suggest and redirect to get the correct article
        # also, use page's error checking to raise DisambiguationError if necessary
        page_info = await self.page(title, auto_suggest=auto_suggest, redirect=redirect)
        title = page_info.title
        pageid = page_info.pageid

        query_params = {
            'prop': 'extracts',
            'explaintext': '',
            'titles': title
        }

        if sentences:
            query_params['exsentences'] = sentences
        elif chars:
            query_params['exchars'] = chars
        else:
            query_params['exintro'] = ''

        resp = await self.api(**query_params)
        summary = resp['query']['pages'][pageid]['extract']

        return summary

    async def page(self, title=None, pageid=None, auto_suggest=True, redirect=True, preload=False):
        """
        Get a WikipediaPage object for the page with title `title` or the pageid
        `pageid` (mutually exclusive).
        Keyword arguments:
        * title - the title of the page to load
        * pageid - the numeric pageid of the page to load
        * auto_suggest - let Wikipedia find a valid page title for the query
        * redirect - allow redirection without raising RedirectError
        * preload - load content, summary, images, references, and links during initialization
        """

        if title is not None:
            if auto_suggest:
                results, suggestion = await self.search(title, limit=1, suggestion=True)
                try:
                    title = suggestion or results[0]
                except IndexError:
                    # if there is no suggestion or search results, the page doesn't exist
                    raise PageError(title)
            return WikipediaPage(title, redirect=redirect, preload=preload)
        elif pageid is not None:
            return WikipediaPage(pageid=pageid, preload=preload)
        else:
            raise ValueError("Either a title or a pageid must be specified")

    async def languages(self):
        """
        List all the currently supported language prefixes (usually ISO language code).
        Can be inputted to `set_lang` to change the Mediawiki that `wikipedia` requests
        results from.
        Returns: dict of <prefix>: <local_lang_name> pairs. To get just a list of prefixes,
        use `wikipedia.languages().keys()`.
        """

        query_params = {
            'meta': 'siteinfo',
            'siprop': 'languages'
        }

        response = await self.api(**query_params)

        languages = response['query']['languages']

        return {
            lang['code']: lang['*']
            for lang in languages
        }

    def donate(self):
        """
        Open up the Wikimedia donate page in your favorite browser.
        """
        import webbrowser

        webbrowser.open('https://donate.wikimedia.org/w/index.php?title=Special:FundraiserLandingPage', new=2)


class WikipediaPage:
    '''
    Contains data from a Wikipedia page.
    Uses property methods to filter data from the raw HTML.
    '''

    def __init__(self, title=None, pageid=None, redirect=True, preload=False, original_title=''):
        if title is not None:
            self.title = title
            self.original_title = original_title or title
        elif pageid is not None:
            self.pageid = pageid
        else:
            raise ValueError("Either a title or a pageid must be specified")

        self.__load(redirect=redirect, preload=preload)

        if preload:
            for prop in ('content', 'summary', 'images', 'references', 'links', 'sections'):
                getattr(self, prop)

    def __repr__(self):
        return '<WikipediaPage {}>'.format(self.title)

    def __eq__(self, other):
        try:
            return (
                    self.pageid == other.pageid
                    and self.title == other.title
                    and self.url == other.url
            )
        except:
            return False

    async def __api(self, **kwargs):

        """
                Make a request to the Wikipedia API using the given search parameters.
                Returns a parsed dict of the JSON response.
                """

        kwargs['format'] = 'json'
        if not 'action' in kwargs:
            kwargs['action'] = 'query'

        try:
            resp = await self.http_client.get(url=self.api_url, params=kwargs, is_json=True)
        except:
            raise

        return resp

    def __load(self, redirect=True, preload=False):
        '''
        Load basic information from Wikipedia.
        Confirm that page exists and is not a disambiguation/redirect.
        Does not need to be called manually, should be called automatically during __init__.
        '''
        query_params = {
            'prop': 'info|pageprops',
            'inprop': 'url',
            'ppprop': 'disambiguation',
            'redirects': '',
        }
        if not getattr(self, 'pageid', None):
            query_params['titles'] = self.title
        else:
            query_params['pageids'] = self.pageid

        request = self.__api(**query_params)

        query = request['query']
        pageid = list(query['pages'].keys())[0]
        page = query['pages'][pageid]

        # missing is present if the page is missing
        if 'missing' in page:
            if hasattr(self, 'title'):
                raise PageError(self.title)
            else:
                raise PageError(pageid=self.pageid)

        # same thing for redirect, except it shows up in query instead of page for
        # whatever silly reason
        elif 'redirects' in query:
            if redirect:
                redirects = query['redirects'][0]

                if 'normalized' in query:
                    normalized = query['normalized'][0]
                    assert normalized['from'] == self.title, ODD_ERROR_MESSAGE

                    from_title = normalized['to']

                else:
                    from_title = self.title

                assert redirects['from'] == from_title, ODD_ERROR_MESSAGE

                # change the title and reload the whole object
                self.__init__(redirects['to'], redirect=redirect, preload=preload)

            else:
                raise RedirectError(getattr(self, 'title', page['title']))

        # since we only asked for disambiguation in ppprop,
        # if a pageprop is returned,
        # then the page must be a disambiguation page
        elif 'pageprops' in page:
            query_params = {
                'prop': 'revisions',
                'rvprop': 'content',
                'rvparse': '',
                'rvlimit': 1
            }
            if hasattr(self, 'pageid'):
                query_params['pageids'] = self.pageid
            else:
                query_params['titles'] = self.title
            request = self.__api(query_params)
            html = request['query']['pages'][pageid]['revisions'][0]['*']

            lis = BeautifulSoup(html, 'html.parser').find_all('li')
            filtered_lis = [li for li in lis if not 'tocsection' in ''.join(li.get('class', []))]
            may_refer_to = [li.a.get_text() for li in filtered_lis if li.a]

            raise DisambiguationError(getattr(self, 'title', page['title']), may_refer_to)

        else:
            self.pageid = pageid
            self.title = page['title']
            self.url = page['fullurl']

    def __continued_query(self, query_params):
        '''
        Based on https://www.mediawiki.org/wiki/API:Query#Continuing_queries
        '''
        query_params.update(self.__title_query_param)

        last_continue = {}
        prop = query_params.get('prop', None)

        while True:
            params = query_params.copy()
            params.update(last_continue)

            request = self.__api(**params)

            if 'query' not in request:
                break

            pages = request['query']['pages']
            if 'generator' in query_params:
                for datum in pages.values():  # in python 3.3+: "yield from pages.values()"
                    yield datum
            else:
                for datum in pages[self.pageid][prop]:
                    yield datum

            if 'continue' not in request:
                break

            last_continue = request['continue']

    @property
    def __title_query_param(self):
        if getattr(self, 'title', None) is not None:
            return {'titles': self.title}
        else:
            return {'pageids': self.pageid}

    @property
    @cached_property
    def html(self):
        '''
        Get full page HTML.
        .. warning:: This can get pretty slow on long pages.
        '''

        if not getattr(self, '_html', False):
            query_params = {
                'prop': 'revisions',
                'rvprop': 'content',
                'rvlimit': 1,
                'rvparse': '',
                'titles': self.title
            }

            request = self.__api(**query_params)
            self._html = request['query']['pages'][self.pageid]['revisions'][0]['*']

        return self._html

    @property
    @cached_property
    def content(self):
        '''
        Plain text content of the page, excluding images, tables, and other data.
        '''

        if not getattr(self, '_content', False):
            query_params = {
                'prop': 'extracts|revisions',
                'explaintext': '',
                'rvprop': 'ids'
            }
            if not getattr(self, 'title', None) is None:
                query_params['titles'] = self.title
            else:
                query_params['pageids'] = self.pageid
            request = self.__api(**query_params)
            self._content = request['query']['pages'][self.pageid]['extract']
            self._revision_id = request['query']['pages'][self.pageid]['revisions'][0]['revid']
            self._parent_id = request['query']['pages'][self.pageid]['revisions'][0]['parentid']

        return self._content

    @property
    @cached_property
    def revision_id(self):
        '''
        Revision ID of the page.
        The revision ID is a number that uniquely identifies the current
        version of the page. It can be used to create the permalink or for
        other direct API calls. See `Help:Page history
        <http://en.wikipedia.org/wiki/Wikipedia:Revision>`_ for more
        information.
        '''

        if not getattr(self, '_revid', False):
            # fetch the content (side effect is loading the revid)
            self.content

        return self._revision_id

    @property
    @cached_property
    def parent_id(self):
        '''
        Revision ID of the parent version of the current revision of this
        page. See ``revision_id`` for more information.
        '''

        if not getattr(self, '_parentid', False):
            # fetch the content (side effect is loading the revid)
            self.content

        return self._parent_id

    @property
    @cached_property
    def summary(self):
        '''
        Plain text summary of the page.
        '''

        if not getattr(self, '_summary', False):
            query_params = {
                'prop': 'extracts',
                'explaintext': '',
                'exintro': '',
            }
            if not getattr(self, 'title', None) is None:
                query_params['titles'] = self.title
            else:
                query_params['pageids'] = self.pageid

            request = self.__api(query_params)
            self._summary = request['query']['pages'][self.pageid]['extract']

        return self._summary

    @property
    @cached_property
    def images(self):
        '''
        List of URLs of images on the page.
        '''

        if not getattr(self, '_images', False):
            self._images = [
                page['imageinfo'][0]['url']
                for page in self.__continued_query({
                    'generator': 'images',
                    'gimlimit': 'max',
                    'prop': 'imageinfo',
                    'iiprop': 'url',
                })
                if 'imageinfo' in page
            ]

        return self._images

    @property
    @cached_property
    def coordinates(self):
        '''
        Tuple of Decimals in the form of (lat, lon) or None
        '''
        if not getattr(self, '_coordinates', False):
            query_params = {
                'prop': 'coordinates',
                'colimit': 'max',
                'titles': self.title,
            }

            request = self.__api(query_params)

            if 'query' in request:
                coordinates = request['query']['pages'][self.pageid]['coordinates']
                self._coordinates = (float(coordinates[0]['lat']), float(coordinates[0]['lon']))
            else:
                self._coordinates = None

        return self._coordinates

    @property
    @cached_property
    def references(self):
        '''
        List of URLs of external links on a page.
        May include external links within page that aren't technically cited anywhere.
        '''

        if not getattr(self, '_references', False):
            def add_protocol(url):
                return url if url.startswith('http') else 'http:' + url

            self._references = [
                add_protocol(link['*'])
                for link in self.__continued_query({
                    'prop': 'extlinks',
                    'ellimit': 'max'
                })
            ]

        return self._references

    @property
    @cached_property
    def links(self):
        '''
        List of titles of Wikipedia page links on a page.
        .. note:: Only includes articles from namespace 0, meaning no Category, User talk, or other meta-Wikipedia pages.
        '''

        if not getattr(self, '_links', False):
            self._links = [
                link['title']
                for link in self.__continued_query({
                    'prop': 'links',
                    'plnamespace': 0,
                    'pllimit': 'max'
                })
            ]

        return self._links

    @property
    @cached_property
    def categories(self):
        '''
        List of categories of a page.
        '''

        if not getattr(self, '_categories', False):
            self._categories = [re.sub(r'^Category:', '', x) for x in
                                [link['title']
                                 for link in self.__continued_query({
                                    'prop': 'categories',
                                    'cllimit': 'max'
                                })
                                 ]]

        return self._categories

    @property
    @cached_property
    def sections(self):
        '''
        List of section titles from the table of contents on the page.
        '''

        if not getattr(self, '_sections', False):
            query_params = {
                'action': 'parse',
                'prop': 'sections',
            }
            query_params.update(self.__title_query_param)

            request = self.__api(**query_params)
            self._sections = [section['line'] for section in request['parse']['sections']]

        return self._sections

    def section(self, section_title):
        '''
        Get the plain text content of a section from `self.sections`.
        Returns None if `section_title` isn't found, otherwise returns a whitespace stripped string.
        This is a convenience method that wraps self.content.
        .. warning:: Calling `section` on a section that has subheadings will NOT return
               the full text of all of the subsections. It only gets the text between
               `section_title` and the next subheading, which is often empty.
        '''

        section = u"== {} ==".format(section_title)
        try:
            index = self.content.index(section) + len(section)
        except ValueError:
            return None

        try:
            next_index = self.content.index("==", index)
        except ValueError:
            next_index = len(self.content)

        return self.content[index:next_index].lstrip("=").strip()
