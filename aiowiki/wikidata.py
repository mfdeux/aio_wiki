
from .http_client import HTTPClient

BASE_API_URL = 'https://www.wikidata.org/w/api.php'
BASE_SPARQL_URL = 'https://query.wikidata.org/sparql'


class Client:
    def __init__(self, lang: str = 'en', user_agent: str = 'wikipedia (https://github.com/goldsmith/Wikipedia/)',
                 proxy: str = None, rate_limit: int = 60):
        self.lang = lang
        self.base_api_url = 'https://www.wikidata.org/w/api.php'
        self.base_sparql_url = 'https://query.wikidata.org/sparql'
        self.http_client = HTTPClient(user_agent=user_agent, proxy=proxy, rate_limit=rate_limit)

    async def sparql(self, query: str):
        """
        Query SPARQL endpoint
        """
        query_params = {
            'query': query
        }
        try:
            return await self.http_client.get(url=self.base_sparql_url, params=query_params,
                                              headers={'accept': 'application/sparql-results+json'},
                                              is_json=True)
        except:
            raise

    async def base_api(self, **kwargs):
        try:
            return await self.http_client.get(url=self.base_api_url, params=kwargs,
                                              is_json=True)
        except:
            raise

    async def search(self, query: str):
        """
        Query entity search endpoint

        https://www.wikidata.org/w/api.php?action=wbsearchentities&search=Google&language=en&format=json
        """
        query_params = {
            'action': 'wbsearchentities',
            'search': query,
            'language': self.lang,
            'format': 'json'
        }

        try:
            resp = await self.base_api(**query_params)
        except:
            raise

        return resp.get('search')

    async def search_properties(self, query: str):
        """
        Query entity property search endpoint

        https://www.wikidata.org/w/api.php?action=wbsearchentities&search=insta&language=en&type=property

        SELECT ?item WHERE {
            ?item rdfs:label "Google"@en
        }
        """

        query_params = {
            'action': 'wbsearchentities',
            'search': query,
            'type': 'property',
            'language': self.lang,
            'format': 'json'
        }

        try:
            resp = await self.base_api(**query_params)
        except:
            raise

        return resp.get('search')

    async def entity(self, entity_ids: str):
        """
        Retrieve all entity properties

        https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q95&languages=en&format=json
        """
        if isinstance(entity_ids, str):
            _entity_ids = entity_ids
        elif isinstance(entity_ids, list):
            _entity_ids = '|'.join(entity_ids)
        else:
            raise TypeError('Entity IDs argument must be either a string or list of strings')

        query_params = {
            'action': 'wbgetentities',
            'ids': _entity_ids,
            'language': self.lang,
            'format': 'json'
        }

        try:
            return await self.base_api(**query_params)
        except:
            raise
