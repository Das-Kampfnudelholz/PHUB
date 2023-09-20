from __future__ import annotations

import json
from functools import cache

from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from ..core import Client

from . import Video, User, FeedItem
from .. import utils
from .. import consts
from .. import errors

QueryItem = Video | FeedItem

class Query:
    '''
    A Base query for type hints that handles
    getting items. 
    '''
    
    BASE: str = None
    PAGE_LENGTH: int = None
    
    def __init__(self, client: Client, args: str) -> None:
        '''
        Initialise a new query.
        '''

        self.client = client
        self.url = utils.concat(self.BASE, args) + '&page='
    
    def __repr__(self) -> str:
        
        return f'phub.Query(url={self.url})'
    
    def __getitem__(self, index: int | slice | tuple) -> QueryItem | Generator[QueryItem, None, None] | tuple[QueryItem]:
        '''
        Get one or multiple items from the query.
        '''
        
        assert isinstance(index, (int, slice, tuple))
        
        if isinstance(index, int):
            return self.get(index)
        
        if isinstance(index, tuple):
            return tuple(self.get(i) for i in index)
        
        def wrap() -> Generator[Video, None, None]:
            # Support slices
            
            for i in range(index.start or 0,
                           index.stop  or 0,
                           index.step  or 1):
                
                yield self.get(i)
        
        return wrap()
    
    # Methods defined by children    
    def get(self, index: int) -> QueryItem:
        '''
        Get a single query item.
        '''
        
        return NotImplemented
    
    def _get_page(self, index: int) -> list:
        '''
        Get a query page.
        '''
        
        return NotImplemented

class JQuery(Query):
    '''
    Represents a query able to parse JSON data.
    '''
    
    BASER = consts.API_ROOT
    PAGE_LENGTH = 30
    
    @cache
    def get(self, index: int) -> Video:
        '''
        Get a video at an index.
        '''
        
        assert isinstance(index, int)
        
        data = self._get_page(index // self.PAGE_LENGTH)[index % self.PAGE_LENGTH]
        
        # Create the object and inject data
        video = Video(self.client, url = data['url'])
        video.data = {f'data@{k}': v for k, v in data.items()} # NOTE - Repetitive w/ Video.fetch
        
        return video
    
    @cache
    def _get_page(self, index: int) -> list[dict]:
        '''
        Fetch a page.
        '''
        
        raw = self.client.call(self.url + str(index + 1)).text
        data = json.loads(raw).get('videos')

        if data is None: raise errors.URLError('Invalid API response')

        return data

class HQuery(Query):
    '''
    Represents a Query able to parse HTML data.
    '''
    
    BASE = consts.HOST
    PAGE_LENGTH = 32
    
    # self.url = utils.concat(consts.HOST, args) + '?&'['?' in args] + 'page='
    
    @cache
    def get(self, index: int) -> Video:
        '''
        Get a single video at an index.
        '''
        
        video = self._get_page(index // self.PAGE_LENGTH)[index % self.PAGE_LENGTH]
        
        url = f'{consts.HOST}view_video.php?viewkey={video[0]}'
        
        obj = Video(self.client, url)
        obj.data = {f'page@title': video[2]}
        
        return obj
    
    @cache
    def _get_page(self, index: int) -> list:
        '''
        Fetch a page.
        '''
        
        url = self.url + str(index + 1)
        raw = self.client.call(url).text
        
        container = raw.split('class="container')[1]
        
        videos: list = consts.re.get_videos(container)
        
        return videos

class FQuery(Query):
    '''
    Represents a query able to parse user feeds.
    '''
    
    BASE = consts.HOST
    PAGE_LENGTH = 14 # TODO - one of them is sus, should be 13
    
    @cache
    def get(self, index: int) -> FeedItem:
        '''
        Get a single item at an index.
        '''
        
        user_url, item = self._get_page(index // self.PAGE_LENGTH)[index % self.PAGE_LENGTH]
        
        obj = FeedItem(
            raw = item,
            user = User(self.client, 'NotImplemented', user_url)
        )
        
        return obj
    
    @cache
    def _get_page(self, index: int) -> list:
        '''
        Fetch a page.
        '''
        
        url = self.url + str(index + 1)
        raw = self.client.call(url).text
        return consts.re.feed_items(raw)

# EOF