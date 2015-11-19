try:
    from urllib.parse import parse_qsl
except ImportError:
    from urlparse import parse_qsl

import requests

from django.views.generic.base import TemplateView

from allauth.socialaccount.providers.oauth2.client import (OAuth2Client,
                                                           OAuth2Error)
from allauth.socialaccount.providers.oauth2.views import (OAuth2Adapter,
                                                          OAuth2LoginView,
                                                          OAuth2CallbackView)
from .provider import UntappdProvider


class UntappdOAuth2Client(OAuth2Client):
    """
    Custom client because Untappd:
        * uses redirect_url instead of redirect_uri
        * nests access_token inside an extra 'response' object
    """

    def get_access_token(self, code):
        data = {'client_id': self.consumer_key,
                'redirect_url': self.callback_url,
                'grant_type': 'authorization_code',
                'client_secret': self.consumer_secret,
                'code': code}
        params = None
        self._strip_empty_keys(data)
        url = self.access_token_url
        if self.access_token_method == 'GET':
            params = data
            data = None
        # TODO: Proper exception handling
        resp = requests.request(self.access_token_method,
                                url,
                                params=params,
                                data=data)
        access_token = None
        if resp.status_code == 200:
            access_token = resp.json()['response']
        if not access_token or 'access_token' not in access_token:
            raise OAuth2Error('Error retrieving access token: %s'
                              % resp.content)
        return access_token


class UntappdOAuth2Adapter(OAuth2Adapter):
    provider_id = UntappdProvider.id
    access_token_url = 'https://untappd.com/oauth/authorize/'
    access_token_method = 'GET'
    authorize_url = 'https://untappd.com/oauth/authenticate/'
    user_info_url = 'https://api.untappd.com/v4/user/info/'
    supports_state = False

    def complete_login(self, request, app, token, **kwargs):
        resp = requests.get(self.user_info_url,
                            params={'access_token': token.token})
        extra_data = resp.json()
        # TODO: get and store the email from the user info json
        return self.get_provider().sociallogin_from_response(request,
                                                             extra_data)


class HomePageView(TemplateView):
    template_name = 'home.html'


class UntappdOAuth2CallbackView(OAuth2CallbackView):
    """ Custom OAuth2CallbackView to return UntappdOAuth2Client """

    def get_client(self, request, app):
        client = super(UntappdOAuth2CallbackView, self).get_client(request,
                                                                   app)
        untappd_client = UntappdOAuth2Client(
            client.request, client.consumer_key, client.consumer_secret,
            client.access_token_method, client.access_token_url,
            client.callback_url, client.scope)
        return untappd_client

oauth2_login = OAuth2LoginView.adapter_view(UntappdOAuth2Adapter)
oauth2_callback = UntappdOAuth2CallbackView.adapter_view(UntappdOAuth2Adapter)
