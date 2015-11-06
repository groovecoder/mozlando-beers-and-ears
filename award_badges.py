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


# See: https://untappd.com/api/docs
UNTAPPD_BASE_URL = 'https://api.untappd.com/v4'
UNTAPPD_CLIENT_ID = os.getenv('UNTAPPD_CLIENT_ID', None)
UNTAPPD_CLIENT_SECRET = os.getenv('UNTAPPD_CLIENT_SECRET', None)
DEFAULT_CACHE_AGE = int(os.getenv('DEFAULT_CACHE_AGE', 60 * 60 * 24 * 7))

BADGES_BASE_URL = 'https://badges.mozilla.org/en-US/badges/badge/'
BADGES_VALET_USERNAME = os.getenv('BADGES_VALET_USERNAME', None)
BADGES_VALET_PASSWORD = os.getenv('BADGES_VALET_PASSWORD', None)

CACHE_PATH_TMPL = 'cache/%s/%s'

UNTAPPD_USERS = [
    'groovecoder',
]

MOZLANDO_START_DATETIME = datetime(2015, 12, 7)
MOZLANDO_END_DATETIME = datetime(2015, 12, 11, 23, 59, 59, 999999)
MOZLANDO_BEERS_AND_EARS_BADGE = 'mozlando-beers-and-ears'
EPCOT_MIN_LATITUDE = 28.375647
EPCOT_MAX_LATITUDE = 28.367444
EPCOT_MIN_LONGITUDE = -81.553245
EPCOT_MAX_LONGITUDE = -81.545134


def main():
    emails_to_award = []

    if not UNTAPPD_CLIENT_ID or not UNTAPPD_CLIENT_SECRET:
        print ('You must set UNTAPPD_CLIENT_ID and UNTAPPD_CLIENT_SECRET'
               ' environment variables to use Untappd API.')
        return

    for user in UNTAPPD_USERS:
        beers = []
        beer_ids = []

        print 'Fetching user activity for %s' % user
        checkins = untappd_api_get('user/checkins/%s' % user, dict(limit=5),
                                   'activity', DEFAULT_CACHE_AGE)

        for checkin in checkins['response']['checkins']['items']:
            checkin_timetuple = parsedate(checkin.get('created_at'))
            checkin_beer = checkin.get('beer')
            checkin_location = checkin.get('venue').get('location')
            if (( # checked in during Mozlando date/time
                 MOZLANDO_START_DATETIME.timetuple() < checkin_timetuple and
                 checkin_timetuple < MOZLANDO_END_DATETIME.timetuple()
                )
                and # checked in at Epcot
                (
                 (
                  EPCOT_MIN_LATITUDE <= checkin_location['lat'] and
                  checkin_location['lat'] <= EPCOT_MAX_LATITUDE
                 )
                 and
                 (
                  EPCOT_MIN_LONGITUDE <= checkin_location['lng'] and
                  checkin_location['lng'] <= EPCOT_MAX_LONGITUDE
                 )
                )
                and # checked in a unique beer
                (
                 checkin_beer['bid'] not in beer_ids
                )
               ):
                beers.append(checkin_beer)
                beer_ids.append(checkin_beer['bid'])
            # if there are 12 check-ins, add the user's email to the list
        if len(beers) >= 12:
            # add the user's email to the list
            pass

    if not BADGES_VALET_USERNAME or not BADGES_VALET_PASSWORD:
        print ('You must set BADGES_VALET_USERNAME and BADGES_VALET_PASSWORD'
               ' for awarding badges.')
        return
    else:
        award_badge(MOZLANDO_BEERS_AND_EARS_BADGE, emails_to_award)

    #print_contributors_by_level(contributors)


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


def award_badge(badge_slug, emails):
    """Award a badge with the specified slug to the specified emails."""
    print 'Awarding the %s badge.' % badge_slug

    r = requests.post(
        '%s%s/awards' % (BADGES_BASE_URL, badge_slug),
        data=json.dumps({'emails': emails, 'description': ''}),
        headers={'content-type': 'application/json'},
        verify=False, # To workaround SSL cert issue.
        auth=(BADGES_VALET_USERNAME, BADGES_VALET_PASSWORD),)

    if r.status_code != 200:
        print 'Something went wrong awarding badge %s (Status=%s).' % (
            badge_slug, r.status_code)
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


if __name__ == '__main__':
    main()
