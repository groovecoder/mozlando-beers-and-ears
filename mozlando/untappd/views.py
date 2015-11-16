import requests

from django.views.generic.base import TemplateView

from allauth.socialaccount.providers.oauth2.views import (OAuth2Adapter,
                                                          OAuth2LoginView,
                                                          OAuth2CallbackView)
from .provider import UntappdProvider


class UntappdOAuth2Adapter(OAuth2Adapter):
    provider_id = UntappdProvider.id
    access_token_url = 'https://untappd.com/oauth/authorize/?client_id=CLIENTID&client_secret=CLIENTSECRET&response_type=code&redirect_url=REDIRECT_URL&code=CODE'
    authorize_url = 'https://untappd.com/oauth/authenticate/'
    user_info_url = 'https://api.untappd.com/v4/user/info/'

    def complete_login(self, request, app, token, **kwargs):
        resp = requests.get(self.user_info_url,
                            params={'access_token': token.token})
        extra_data = resp.json()
        # TODO: get the email from the user info json
        return self.get_provider().sociallogin_from_response(request,
                                                             extra_data)


class HomePageView(TemplateView):
    template_name = 'home.html'


oauth2_login = OAuth2LoginView.adapter_view(UntappdOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(UntappdOAuth2Adapter)
