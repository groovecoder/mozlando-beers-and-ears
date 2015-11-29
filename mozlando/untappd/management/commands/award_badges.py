#!/usr/bin/env python
from datetime import datetime
from email.utils import parsedate
import hashlib
import json
import os
import requests
import time
import urllib
from os.path import dirname

from django.core.management.base import BaseCommand

from allauth.socialaccount.models import SocialAccount


# See: https://untappd.com/api/docs
UNTAPPD_BASE_URL = 'https://api.untappd.com/v4'
UNTAPPD_CLIENT_ID = os.getenv('UNTAPPD_CLIENT_ID', None)
UNTAPPD_CLIENT_SECRET = os.getenv('UNTAPPD_CLIENT_SECRET', None)
DEFAULT_CACHE_AGE = int(os.getenv('DEFAULT_CACHE_AGE', 60 * 60 * 24 * 7))

CREDLY_BASE_URL = 'https://api.credly.com/v1.1'
CREDLY_API_KEY = os.getenv('CREDLY_API_KEY', None)
CREDLY_API_SECRET = os.getenv('CREDLY_API_SECRET', None)
CREDLY_USERNAME = os.getenv('CREDLY_USERNAME', None)
CREDLY_PASSWORD = os.getenv('CREDLY_PASSWORD', None)
CREDLY_BADGE_ID = 61615

CACHE_PATH_TMPL = 'cache/%s/%s'

# Mozlando values
NUM_BEERS = 12
START_DATETIME = datetime(2015, 12, 7)
END_DATETIME = datetime(2015, 12, 11, 23, 59, 59, 999999)
MOZLANDO_BEERS_AND_EARS_BADGE = 'mozlando-beers-and-ears'
MIN_LATITUDE = 28.367444
MAX_LATITUDE = 28.375647
MIN_LONGITUDE = -81.553245
MAX_LONGITUDE = -81.545134

# Test values (Cherry Street in Tulsa Nov 23-27)
# NUM_BEERS = 2
# START_DATETIME = datetime(2015, 11, 23)
# END_DATETIME = datetime(2015, 11, 27, 23, 59, 59, 999999)
# MIN_LATITUDE = 36.136844
# MAX_LATITUDE = 36.143845
# MIN_LONGITUDE = -95.97546
# MAX_LONGITUDE = -95.940098

# Test values (Portland Nov 3-6)
# NUM_BEERS = 2
# START_DATETIME = datetime(2015, 11, 3)
# END_DATETIME = datetime(2015, 11, 6, 23, 59, 59, 999999)
# MIN_LATITUDE = 45.521143
# MAX_LATITUDE = 45.526412
# MIN_LONGITUDE = -122.684202
# MAX_LONGITUDE = -122.671810
# CREDLY_BADGE_ID = 61628

class Command(BaseCommand):

  def handle(self, *args, **options):
    emails_to_award = []

    if not UNTAPPD_CLIENT_ID or not UNTAPPD_CLIENT_SECRET:
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
            DEFAULT_CACHE_AGE
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
                 START_DATETIME.timetuple() < checkin_timetuple and
                 checkin_timetuple < END_DATETIME.timetuple()
                ):
                print 'Match Checkin: Time: {0}'.format(checkin_timetuple)
                if ( # checked in at Epcot
                 (
                  MIN_LATITUDE <= checkin_lat and
                  checkin_lat <= MAX_LATITUDE
                 )
                 and
                 (
                  MIN_LONGITUDE <= checkin_lng and
                  checkin_lng <= MAX_LONGITUDE
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
        if len(beers) >= NUM_BEERS:
            print "Found 2 matching beers; badge time!"
            # add the user's email to the list
            emails_to_award.append(account.user.emailaddress_set.all()[0].email)

    if (not CREDLY_API_KEY
        or not CREDLY_API_SECRET
        or not CREDLY_USERNAME
        or not CREDLY_PASSWORD):
        print ('You must set CREDLY_API_KEY, CREDLY_API_SECRET, '
               'CREDLY_USERNAME, and CREDLY_PASSWORD for awarding '
               'badges.')
        return
    else:
        credly_token_response = credly_api_post(
            '/authenticate',
            "",
            None,
            (CREDLY_USERNAME,CREDLY_PASSWORD)
        )
        credly_token = json.loads(credly_token_response.content)['data']['token']
        for email_to_award in emails_to_award:
            award_badge(email_to_award, credly_token)


def untappd_api_url(url, params=None):
    """Append the Untappd client details, if available"""
    url = '%s/%s' % (UNTAPPD_BASE_URL, url)
    if not params:
        params = {}
    if UNTAPPD_CLIENT_ID and UNTAPPD_CLIENT_SECRET:
        params.update(dict(
            client_id = UNTAPPD_CLIENT_ID,
            client_secret = UNTAPPD_CLIENT_SECRET
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
    cache_path = CACHE_PATH_TMPL % (cache_name, path_hash)

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
    url = '%s%s?%s' % (CREDLY_BASE_URL, path, urllib.urlencode(params))
    print 'credly url: %s' % url
    r = requests.post(
        url,
        data,
        headers={
            'X-Api-Key': CREDLY_API_KEY,
            'X-Api-Secret': CREDLY_API_SECRET
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
                            'badge_id': CREDLY_BADGE_ID
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
