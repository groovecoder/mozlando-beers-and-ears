#!/usr/bin/env python
from email.utils import parsedate
import hashlib
import json
import os
import requests
import time
import urllib
from os.path import dirname

from django.conf import settings
from django.core.management.base import BaseCommand

from allauth.socialaccount.models import SocialAccount


class Command(BaseCommand):

  def handle(self, *args, **options):
    emails_to_award = []

    if not settings.UNTAPPD_CLIENT_ID or not settings.UNTAPPD_CLIENT_SECRET:
        print ('You must set UNTAPPD_CLIENT_ID and UNTAPPD_CLIENT_SECRET'
               ' environment variables to use Untappd API.')
        return

    for account in SocialAccount.objects.filter(provider='untappd'):
        username = account.user.username
        beers = []
        beer_ids = []

        print 'Fetching user activity for %s' % username
        checkins = untappd_api_get(
            'user/checkins/%s' % username, dict(limit=50), 'activity',
            settings.DEFAULT_CACHE_AGE
        )

        if 'checkins' not in checkins['response']:
            print "User %s has no checkins." % username
            continue

        for checkin in checkins['response']['checkins']['items']:
            checkin_timetuple = parsedate(checkin.get('created_at'))
            checkin_beer = checkin.get('beer')
            if 'location' in checkin.get('venue'):
                checkin_location = checkin.get('venue').get('location')
                checkin_lat = checkin_location.get('lat')
                checkin_lng = checkin_location.get('lng')
            else:
                print "%s checkin had no location." % checkin_beer['beer_name']
                continue
            if ( # checked in during Mozlando date/time
                 settings.START_DATETIME.timetuple() < checkin_timetuple and
                 checkin_timetuple < settings.END_DATETIME.timetuple()
                ):
                print 'Match Checkin: Time: {0}'.format(checkin_timetuple)
                if ( # checked in at Epcot
                 (
                  settings.MIN_LATITUDE <= checkin_lat and
                  checkin_lat <= settings.MAX_LATITUDE
                 )
                 and
                 (
                  settings.MIN_LONGITUDE <= checkin_lng and
                  checkin_lng <= settings.MAX_LONGITUDE
                 )
                   ):
                    print 'Match Checkin: Lat: %s Lng: %s' % (checkin_lat,
                                                              checkin_lng)
                    if ( # checked in a unique beer
                     checkin_beer['bid'] not in beer_ids
                    ):
                        print 'Match Checkin: Beer: %s' % checkin_beer
                        beers.append(checkin_beer)
                        beer_ids.append(checkin_beer['bid'])
            # if there are 12 check-ins, add the user's email to the list
        if len(beers) >= settings.NUM_BEERS:
            print "Found %s matching beers; badge time!" % settings.NUM_BEERS
            # add the user's email to the list
            emails_to_award.append(account.user.emailaddress_set.all()[0].email)

    if (not settings.CREDLY_API_KEY
        or not settings.CREDLY_API_SECRET
        or not settings.CREDLY_USERNAME
        or not settings.CREDLY_PASSWORD):
        print ('You must set CREDLY_API_KEY, CREDLY_API_SECRET, '
               'CREDLY_USERNAME, and CREDLY_PASSWORD for awarding '
               'badges.')
        return
    else:
        credly_token_response = credly_api_post(
            '/authenticate',
            "",
            None,
            (settings.CREDLY_USERNAME,settings.CREDLY_PASSWORD)
        )
        credly_token = json.loads(credly_token_response.content)['data']['token']
        for email_to_award in emails_to_award:
            award_badge(email_to_award, credly_token)


def untappd_api_url(url, params=None):
    """Append the Untappd client details, if available"""
    url = '%s/%s' % (settings.UNTAPPD_BASE_URL, url)
    if not params:
        params = {}
    if settings.UNTAPPD_CLIENT_ID and settings.UNTAPPD_CLIENT_SECRET:
        params.update(dict(
            client_id = settings.UNTAPPD_CLIENT_ID,
            client_secret = settings.UNTAPPD_CLIENT_SECRET
        ))
    if params:
        url = '%s?%s' % (url, urllib.urlencode(params))
    return url


def untappd_api_get(path, params=None, cache_name=False, cache_timeout=3600):
    """Cached HTTP GET to the API"""
    url = untappd_api_url(path, params)

    # If no cache name, then cache is disabled.
    if not cache_name:
        return requests.get(url).json()

    # Build a cache path based on MD5 of URL
    path_hash = hashlib.md5(url).hexdigest()
    cache_path = settings.CACHE_PATH_TMPL % (cache_name, path_hash)

    # Create the cache path, if necessary
    cache_dir = dirname(cache_path)
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)

    # Attempt to load up data from cache
    data = None
    if os.path.exists(cache_path) and file_age(cache_path) < cache_timeout:
        try:
            data = json.load(open(cache_path, 'r'))
        except ValueError:
            pass

    # If data was missing or stale from cache, finally perform GET
    if not data:
        data = requests.get(url).json()
        json.dump(data, open(cache_path, 'w'))

    return data


def credly_api_post(path, data, token=None, user_pw=None):
    auth=None
    params = {}
    if user_pw:
        auth = requests.auth.HTTPBasicAuth(*user_pw)
    if token:
        params = {'access_token': token}
    url = '%s%s?%s' % (settings.CREDLY_BASE_URL,
                       path, urllib.urlencode(params))
    print 'credly url: %s' % url
    r = requests.post(
        url,
        data,
        headers={
            'X-Api-Key': settings.CREDLY_API_KEY,
            'X-Api-Secret': settings.CREDLY_API_SECRET
        },
        auth=auth
        # verify=False, # To workaround SSL cert issue.
    )
    return r


def award_badge(email, token):
    """Award a badge with the specified slug to the specified emails."""

    print 'Awarding the badge.'
    r = credly_api_post('/member_badges',
                        {
                            'email': email,
                            'first_name': None,
                            'last_name': None,
                            'badge_id': settings.CREDLY_BADGE_ID
                        },
                        token
    )

    if r.status_code != 200:
        print 'Something went wrong awarding badge: '
        print r.content
        return

    response = json.loads(r.content)

    if 'successes' in response:
        successes = response['successes']
        print 'Badge awarded to: %s' % [k for k in successes.keys()]

    if 'errors' in response:
        errors = response['errors']
        already_awarded = [x for x in errors.keys()
                           if errors[x] == 'ALREADYAWARDED']
        print 'Badge had already been awarded to: %s' % (
            [k for k in already_awarded])
        print 'Error awarding badge to: %s' % (
            [k for k in errors if k not in already_awarded])


def file_age(fn):
    """Get the age of a file in seconds"""
    return time.time() - os.stat(fn).st_mtime
