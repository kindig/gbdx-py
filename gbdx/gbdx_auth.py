"""Some functions for interacting with GBDX end points."""
import os
import base64
import json
from ConfigParser import ConfigParser, NoOptionError
from datetime import datetime

from oauthlib.oauth2 import LegacyApplicationClient
from requests_oauthlib import OAuth2Session

GBDX_AUTH_URL = 'https://geobigdata.io/auth/v1/oauth/token/'

def session_from_envvars(auth_url=GBDX_AUTH_URL,
                         environ_template=(('username', 'GBDX_USERNAME'),
                                           ('password', 'GBDX_PASSWORD'),
                                           ('client_id', 'GBDX_CLIENT_ID'),
                                           ('client_secret', 'GBDX_CLIENT_SECRET'))):
    """Returns a session with the GBDX authorization token baked in,
    pulling the credentials from environment variables.

    config_template - An iterable of key, value pairs. The key should
                      be the variables used in the oauth workflow, and
                      the values being the environment variables to
                      pull the configuration from.  Change the
                      template values if your envvars differ from the
                      default, but make sure the keys remain the same.
    """
    def save_token(token):
        s.token = token
    
    environ = {var:os.environ[envvar] for var, envvar in environ_template}
    s = OAuth2Session(client=LegacyApplicationClient(environ['client_id']),
                      auto_refresh_url=auth_url,
                      auto_refresh_kwargs={'client_id':environ['client_id'],
                                           'client_secret':environ['client_secret']},
                      token_updater=save_token)

    s.fetch_token(auth_url, **environ)
    return s


def session_from_config(config_file):
    """Returns a requests session object with oauth enabled for
    interacting with GBDX end points."""
    
    def save_token(token_to_save):
        """Save off the token back to the config file."""
        if not 'gbdx_token' in set(cfg.sections()):
            cfg.add_section('gbdx_token')
        cfg.set('gbdx_token', 'json', json.dumps(token_to_save))
        with open(config_file, 'w') as sink:
            cfg.write(sink)

    # Read the config file (ini format).
    cfg = ConfigParser()
    if not cfg.read(config_file):
        raise RuntimeError('No ini file found at {} to parse.'.format(config_file))

    try:
        client_id = cfg.get('gbdx', 'client_id')
        client_secret = cfg.get('gbdx', 'client_secret')
        api_key = base64.b64encode("{}:{}".format(client_id, client_secret))
    except NoOptionError:
        #user probably was given an apikey instead
        api_key = cfg.get('gbdx','api_key')
        (client_id, client_secret) = _unpack_apikey(api_key)

    # See if we have a token stored in the config, and if not, get one.
    if 'gbdx_token' in set(cfg.sections()):
        # Parse the token from the config.
        token = json.loads(cfg.get('gbdx_token','json'))

        # Update the token expiration with a little buffer room.
        token['expires_at'] = (datetime.fromtimestamp(token['expires_at']) -
                               datetime.now()).total_seconds() - 600

        # Note that to use a token from the config, we have to set it
        # on the client and the session!
        s = OAuth2Session(client_id, client=LegacyApplicationClient(client_id, token=token),
                          auto_refresh_url=cfg.get('gbdx','auth_url'),
                          auto_refresh_kwargs={'client_id':client_id,
                                               'client_secret':client_secret},
                          token_updater=save_token)
        s.token = token
    else:
        # No pre-existing token, so we request one from the API.
        sess = OAuth2Session(client_id, client=LegacyApplicationClient(client_id),
                          auto_refresh_url=cfg.get('gbdx','auth_url'),
                          auto_refresh_kwargs={'client_id':client_id,
                                               'client_secret':client_secret},
                          token_updater=save_token)

        # Get the token and save it to the config.
        headers = {"Authorization": "Basic {}".format(api_key),
                   "Content-Type": "application/x-www-form-urlencoded"}
        token = sess.fetch_token(cfg.get('gbdx','auth_url'),
                              username=cfg.get('gbdx','user_name'),
                              password=cfg.get('gbdx','user_password'),
                              headers=headers)
        save_token(token)
        
#     else:
#         # No pre-existing token, so we request one from the API.
#         s = OAuth2Session(client_id, client=LegacyApplicationClient(client_id),
#                           auto_refresh_url=cfg.get('gbdx','auth_url'),
#                           auto_refresh_kwargs={'client_id':client_id,
#                                                'client_secret':client_secret},
#                           token_updater=save_token)
# 
#         # Get the token and save it to the config.
#         token = s.fetch_token(cfg.get('gbdx','auth_url'), 
#                               username=cfg.get('gbdx','user_name'),
#                               password=cfg.get('gbdx','user_password'),
#                               client_id=client_id,
#                               client_secret=client_secret)
#         save_token(token)

    return s

def get_session(config_file=None):
    """Returns a requests session with gbdx oauth2 baked in.

    If you provide a path to a config file, it will look there for the
    credentials.  If you don't it will try to pull the credentials
    from environment variables (GBDX_USERNAME, GBDX_PASSWORD,
    GBDX_CLIENT_ID, GBDX_CLIENT_SECRET).  If that fails and you have a
    '~/.gbdx-config' ini file, it will read from that.
    """
    # If not config file, try using environment variables.  If that
    # fails and their is a config in the default location, use that.
    if not config_file:
        try:
            return session_from_envvars()
        except Exception as e:
            config_file = os.path.expanduser('~/.gbdx-config')
            if os.path.isfile(config_file):
                return session_from_config(config_file)
            else:
                raise
    else:
        return session_from_config(config_file)

def _unpack_apikey(apikey):
    """
    Converts an api key into client_id and client_secret values
    """
    tmp = apikey.split(':')
    client_id = tmp[0]
    client_secret = ":".join(tmp[1:])
    return (client_id, client_secret)

def configure(config_file=None, auth_url=GBDX_AUTH_URL):
    """
    Prompts user for the basic credentials required to generate
    the ~/.gbdx-config file.
    """
    #collect the configuration data from the user...
    config_data = {"auth_url":auth_url}
    print("Please provide the following information.")
    config_data['user_name'] = raw_input("user_name: ")
    config_data['user_password'] = raw_input("user_password: ")

    #TODO: I haven't had much luck being able to copy-paste in
    # an apikey and not have encoding problems, like what happens
    # with "\" as a character creating an escape, etc...
    #apikey = raw_input("api_key: ")
    #if not apikey:
    #    config_data['client_id'] = raw_input("client_id: ")
    #    config_data['client_secret'] = raw_input("client_secret: ")
    #else:
    #    config_data['api_key'] = apikey
    config_data['client_id'] = raw_input("client_id: ")
    config_data['client_secret'] = raw_input("client_secret: ")
    #save data to a new config file
    cfg = ConfigParser()
    cfg.add_section("gbdx")
    for (key,value) in config_data.iteritems():
        cfg.set("gbdx", key, value)
    if not config_file:
        config_file = os.path.expanduser('~/.gbdx-config')
    with open(config_file, 'w') as cfg_file:
        cfg.write(cfg_file)

