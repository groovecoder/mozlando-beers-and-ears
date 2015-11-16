from allauth.socialaccount import providers
from allauth.socialaccount.providers.base import ProviderAccount
from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider


class UntappdAccount(ProviderAccount):
    def get_profile_url(self):
        return self.account.extra_data.get('untappd_url')

    def get_avatar_url(self):
        return self.account.extra_data.get('user_avatar')

    def to_str(self):
        dflt = super(UntappdAccount, self).to_str()
        return self.account.extra_data.get('user_name', dflt)


class UntappdProvider(OAuth2Provider):
    id = 'untappd'
    name = 'Untappd'
    package = 'mozlando.untappd.provider'
    account_class = UntappdAccount

    def extract_uid(self, data):
        return str(data['id'])

    def extract_common_fields(self, data):
        return dict(email=data.get('email'),
                    username=data.get('login'),
                    name=data.get('name'))


providers.registry.register(UntappdProvider)
