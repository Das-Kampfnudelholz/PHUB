'''
PHUB core module.
'''

import time
import logging

import requests

from . import utils
from . import consts
from . import errors
from . import locals

from .modules import parser

from .objects import (
    Param, NO_PARAM,
    Video, User, Pornstar, Account,
    Query, JSONQuery, HTMLQuery,
    MemberQuery, PSQuery
)

logger = logging.getLogger(__name__)

class Client:
    '''
    Represents a client capable of handling requests
    with Pornhub.
    '''
    
    def __init__(self,
                 username: str = None,
                 password: str = None,
                 *,
                 language: str = 'en,en-US',
                 delay: int = 0,
                 proxies: dict = None,
                 login: bool = True) -> None:
        '''
        Initialise a new client.
        
        Args:
            username (str): Optional account username/address to connect to.
            password (str): Optional account password to connect to.
            language (str): Language locale (fr, en, ru, etc.)
            delay  (float): Minimum delay between requests.
            proxies (dict): Dictionnary of proxies for the requests.
            login   (bool): Wether to automatically login after initialisation.
        '''
        
        logger.debug('Initialised new Client %s', self)
        
        # Initialise session
        self.reset()
        
        self.proxies = proxies
        self.language = {'Accept-Language': language}
        self.credentials = {'username': username,
                            'password': password}
        
        self.delay = delay
        self.start_delay = False
        
        # Connect account
        self.logged = False
        self.account = Account(self)
        logger.debug('Connected account to client %s', self.account)
        
        # Automatic login
        if login and self.account:
            logger.debug('Automatic login triggered')
            self.login()
    
    def reset(self) -> None:
        '''
        Reset the client requests session.
        '''
        
        # Initialise session
        self.session = requests.Session()
        
        # Bypass age disclaimer
        self.session.cookies.set('accessAgeDisclaimerPH', '1')
        self.session.cookies.set('accessAgeDisclaimerUK', '1')
        self.session.cookies.set('accessPH', '1')
        self.session.cookies.set('age_verified', '1')
    
    def call(self,
             func: str,
             method: str = 'GET',
             data: dict = None,
             headers: dict = {},
             timeout: float = 30,
             throw: bool = True,
             silent: bool = False) -> requests.Response:
        '''
        Send a request.
        
        Args:
            func      (str): URL or PH function to call.
            method    (str): Request method.
            data     (dict): Optional data to send to the server.
            headers  (dict): Request optional headers.
            timeout (float): Request maximum response time.
            throw    (bool): Wether to raise an error when a request explicitely fails.
            silent   (bool): Make the call logging one level deeper.
        
        Returns:
            requests.Response: The fetched response.
        '''
        
        logger.log(logging.DEBUG if silent else logging.INFO, 'Making call %s', func)
        
        # Delay
        if self.start_delay:
            time.sleep(self.delay)
        else:
            self.start_delay = True

        url = func if 'http' in func else utils.concat(consts.HOST, func)
        
        for i in range(consts.MAX_CALL_RETRIES):
            
            try:
                # Send request
                response = self.session.request(
                    method = method,
                    url = url,
                    headers = consts.HEADERS | headers | self.language,
                    data = data,
                    timeout = timeout,
                    proxies = self.proxies
                )
                
                # Silent 429 errors
                if b'429</title>' in response.content:
                    raise ConnectionError('Pornhub raised error 429: too many requests')
                
                # Attempt to resolve challenge if needed
                if challenge := consts.re.get_challenge(response.text, False):
                    logger.info('\n\nChallenge found, attempting to resolve\n\n')
                    parser.challenge(self, *challenge)
                    continue # Reload page
                
                break
            
            except Exception as err:
                logger.log(logging.DEBUG if silent else logging.WARNING,
                           f'Call failed: {repr(err)}. Retrying (attempt {i + 1}/{consts.MAX_CALL_RETRIES})')
                time.sleep(consts.MAX_CALL_TIMEOUT)
                continue
        
        else:
            raise ConnectionError(f'Call failed after {i + 1} retries. Aborting.')

        if throw: response.raise_for_status()
        return response
    
    def login(self,
              force: bool = False,
              throw: bool = True) -> bool:
        '''
        Attempt to log in.
        
        Args:
            force (bool): Wether to force the login (used to reconnect).
            throw (bool): Wether to raise an error if this fails.
        
        Returns:
            bool: Wether the login was successfull.
        '''
        
        logger.debug('Attempting login')
        
        if not force and self.logged:
            logger.error('Client is already logged in')
            raise errors.ClientAlreadyLogged()
    
        # Get token
        page = self.call('').text
        token = consts.re.get_token(page)
        
        # Send credentials
        payload = consts.LOGIN_PAYLOAD | self.credentials | {'token': token}
        response = self.call('front/authenticate', method = 'POST', data = payload)
        
        # Parse response
        data = response.json()
        success = int(data.get('success'))
        message = data.get('message')
        
        if throw and not success:
            logger.error('Login failed: Received error: %s', message)
            raise errors.LoginFailed(message)
        
        # Update account data
        self.account.connect(data)
        self.logged = bool(success)
        return self.logged
    
    def get(self, video: str | Video) -> Video:
        '''
        Fetch a Pornhub video.
        
        Args:
            video (str): Video full URL, partial URL or viewkey.
        
        Returns:
            Video: The corresponding video object.
        '''
        
        logger.debug('Fetching video at', video)

        if isinstance(video, Video):
            # User might want to re-init a video,
            # or use another client
            url = video.url
        
        elif 'http' in video:
            # Support full URLs
            url = video
        
        else:
            if 'key=' in video:
                # Support partial URLs
                key = video.split('key=')[1]
            
            else:
                # Support key only
                key = str(video)
            
            url = utils.concat(consts.HOST, 'view_video.php?viewkey=' + key)
        
        return Video(self, url)

    def get_user(self, user: str) -> User | Pornstar:
        '''
        Get a specific user.
        
        Args:
            user (str): user URL or name.
        
        Returns:
            User: The corresponging user object.
        '''
        
        logger.debug('Fetching user %s', user)
        return User.get(self, user)

    def search(self,
               query: str,
               param: locals.constant = NO_PARAM,
               feature = JSONQuery) -> Query:
        '''
        Performs searching on Pornhub.
        
        Args:
            query (str): The query to search.
            param (Param): Filters parameter.
            feature (Query): Query to use for parsing.
        
        Returns:
            Query: Initialised query.
        '''
        
        # Assert param type
        assert isinstance(param, Param)
        logger.info('Opening search query for `%s`', query)
        
        func = 'video/search' if feature is HTMLQuery else 'search'
        return feature(self, func, Param('search', query) | param)

    def search_user(self,
                    username: str = None,
                    country: str = None,
                    city: str = None,
                    age: tuple[int] = None,
                    param: Param = NO_PARAM
                    ) -> MemberQuery:
        '''
        Search for users in the community.
        
        Args:
            username (str): The member username.
            country (str): The member **country code** (AF, FR, etc.)
            param (Param): Filters parameter.
        
        Returns:
            MQuery: Initialised query.
        
        '''
        
        params = (param
                  | Param('username', username)
                  | Param('city', city)
                  | Param('country', country))
        
        if age:
            params |= Param('age1', age[0])
            params |= Param('age2', age[1])
        
        return MemberQuery(self, 'user/search', params)
    
    def search_pornstar(self,
                        name: str = None,
                        sort_param: Param = NO_PARAM) -> PSQuery:
        '''
        Search for pornstars.
        
        Args:
            name (str): The pornstar name.
            sort_param (Param): Query sort parameter.
        
        Returns:
            PQuery: Initialised query.
        '''
        
        # TODO
        if sort_param.value: # Should be o => mp/mv/nv
            raise NotImplementedError('PS search parameters are not implemented')
                
        sort_param |= Param('search', '+'.join(name.split())) # Format name
        
        return PSQuery(self, 'pornstars/search', sort_param)

# EOF
