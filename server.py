#!/usr/bin/env python
import tornado.curl_httpclient
import tornado.ioloop
import tornado.web
from tornado.web import HTTPError
from tornado import template
import tornado.locks
from tornado import gen
import argparse
import collections
import concurrent.futures
import json
import logging
import os
import re
import socket
import uuid
import urllib

import db

logger = logging.getLogger(__name__)
tornado.ioloop.IOLoop.current().set_blocking_log_threshold(1)

APP_KEY = os.environ.get('DBX_APP_KEY')
APP_SECRET = os.environ.get('DBX_APP_SECRET')
BASE_URL = os.environ.get('BASE_URL')
COOKIE_SECRET = os.environ.get('COOKIE_SECRET')

USER_AGENT = 'PubFolder/1.0 (Python 3.6)'

io_loop = tornado.ioloop.IOLoop.current()
http_client = tornado.curl_httpclient.CurlAsyncHTTPClient(io_loop, max_clients=16)

class OurHandler(tornado.web.RequestHandler):
    def write_error(self, status_code, **kwargs):
        self.set_status(status_code)

        if 'message' in kwargs:
            message = kwargs['message']
        else:
            try:
                message = kwargs['exc_info'][1].log_message
            except Exception:
                message = 'Unknown error.'

        self.render('error.html', error_message='Error %s' % status_code, details=message)

    def render(self, template_name, **kwargs):
        kwargs['logged_in'] = bool(self.get_secure_cookie('dbx_uid'))
        return super().render(template_name, **kwargs)

class PublicFolderHandler(OurHandler):
    @gen.coroutine
    def get(self, uid, path):
        token = db.get_auth(uid)
        if token is None:
            # TODO: render something saying that the user is not authenticated with us
            self.render('error.html', error_message="404: Page Not Found :(", details="This is not the page you are looking for.")
            return

        # Try to list shared links for the user for this path
        url = 'https://api.dropboxapi.com/2/sharing/list_shared_links'
        body = json.dumps({
            "path": '/' + path,
        })
        hreq = tornado.httpclient.HTTPRequest(url, method='POST', user_agent=USER_AGENT, headers={
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json',
        }, body=body, request_timeout=120)

        try:
            resp = yield http_client.fetch(hreq)
        except Exception as e:
            logger.exception("Exception when requesting %r", url)
            raise HTTPError(500, 'Unable to obtain link from Dropbox')

        js = json.loads(resp.buffer.read().decode('utf8'))

        # TODO: Filter links without public visibility
        try:
            url = js['links'][0]['url']
            path = js['links'][0]['path_lower'][1:]
        except IndexError:
            path = None
            url = None

        if url is None:
            # Generate the shared link for that path
            url = 'https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings'

            body = json.dumps({
                "path": '/' + path,
                "settings": {
                    "requested_visibility": "public",
                },
            })
            hreq = tornado.httpclient.HTTPRequest(url, method='POST', user_agent=USER_AGENT, headers={
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json',
            }, body=body, request_timeout=120)

            try:
                resp = yield http_client.fetch(hreq)
            except Exception as e:
                logger.exception("Exception when requesting %r", url)
                raise HTTPError(500, 'Unable to obtain link from Dropbox')

            js = json.loads(resp.buffer.read().decode('utf8'))
            url = js['url']
            path = js['path_lower'][1:]

        # Make it a direct link
        try:
            sid = re.search(r'^https://www.dropbox.com/s/([^/]*)/', url).group(1)
        except Exception:
            # Fall back on using the DL link
            url = url.replace('?dl=0', '?dl=1')
        else:
            url = 'https://dl.dropboxusercontent.com/1/view/{sid}/{path}'.format(sid=sid, path=path)

        self.redirect(url)

class ListFolderHandler(OurHandler):
    @gen.coroutine
    def get(self, path):
        token = None
        uid = self.get_secure_cookie('dbx_uid')
        if uid:
            uid = uid.decode('utf8')
            token = db.get_auth(uid)
        if token is None:
            self.clear_cookie('dbx_uid')
            self.render('error.html', error_message="User not found", details="You are not logged in, or your Dropbox authorization has expired. Please login again to reauthorize your Dropbox.")
            return

        path = path.rstrip('/')

        url = 'https://api.dropboxapi.com/2/files/list_folder'
        body = json.dumps({
            "path": path,
        })
        hreq = tornado.httpclient.HTTPRequest(url, method='POST', user_agent=USER_AGENT, headers={
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json',
        }, body=body, request_timeout=120)

        try:
            resp = yield http_client.fetch(hreq)
        except Exception as e:
            logger.exception("Exception when requesting %r", url)
            raise HTTPError(500, 'Unable to obtain folder list from Dropbox')

        js = json.loads(resp.buffer.read().decode('utf8'))

        for entry in js['entries']:
            if entry['.tag'] == 'file':
                entry['our_path'] = urllib.parse.urljoin(BASE_URL, uid) + entry['path_lower']
            else:
                entry['our_path'] = urllib.parse.urljoin(BASE_URL, 'list') + entry['path_lower'] + '/'

        self.render('list.html', entries=js['entries'])

class RootHandler(OurHandler):
    @gen.coroutine
    def get(self):
        self.render('home.html')

class FAQHandler(OurHandler):
    @gen.coroutine
    def get(self):
        self.render('faq.html')

class Error404Handler(OurHandler):
    @gen.coroutine
    def get(self, path):
        self.set_status(404)
        self.render('error.html', error_message="404: Page Not Found :(", details="This is not the page you are looking for.")

class LoginHandler(OurHandler):
    @gen.coroutine
    def get(self):
        url = urllib.parse.urljoin(BASE_URL, '/login/continue')
        self.render("login.html",client_id=APP_KEY, redirect_uri=urllib.parse.quote(url))

class LoginContinueHandler(OurHandler):
    @gen.coroutine
    def get(self):
        code = self.get_argument('code')

        url = 'https://api.dropboxapi.com/oauth2/token'
        body = urllib.parse.urlencode({
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': urllib.parse.urljoin(BASE_URL, '/login/continue'),
        })
        hreq = tornado.httpclient.HTTPRequest(url, method='POST', user_agent=USER_AGENT,
                                              auth_username=APP_KEY, auth_password=APP_SECRET,
                                              body=body, request_timeout=120)

        try:
            resp = yield http_client.fetch(hreq)
        except Exception:
            logger.exception("Exception when requesting %r", url)
            raise HTTPError(500, 'Unable to obtain authorization code from Dropbox')

        js = json.loads(resp.buffer.read().decode('utf8'))

        self.set_secure_cookie('dbx_uid', js['uid'])
        db.store_auth(uid=js['uid'], access_token=js['access_token'])

        # Example JS:
        # {
        #     access_token: "-c0JMq0qLncAAAAAAABqMedBF0-_QbmwWHToG4jXXctB1qNBSxm0aZYhupbtC3PK",
        #     token_type: "bearer",
        #     uid: "113409",
        #     account_id: "dbid:AABkoAh-HU3E5gJ2Ed1XR_Yait3IBadk0Ps"
        # }

        self.write(json.dumps(js))

class LogoutHandler(OurHandler):
    @gen.coroutine
    def get(self):
        self.clear_cookie('dbx_uid')
        self.render('error.html', error_message='Logged out', details='You have been logged out.')

def make_app():
    return tornado.web.Application([
        (r"/", RootHandler),
        (r"/(\d+)/(.*)", PublicFolderHandler),
        (r"/list(/?.*)", ListFolderHandler),
        (r"/login", LoginHandler),
        (r"/login/continue", LoginContinueHandler),
        (r"/logout", LogoutHandler),
        (r"/faq", FAQHandler),
        (r"/(.*)", Error404Handler),
    ], template_path="templates", cookie_secret=COOKIE_SECRET, debug=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run the Tornado server")
    parser.add_argument('start_port', default=8000, type=int, nargs='?',
                        help="What port should we start on? (default 8000)")
    parser.add_argument('offset_port', default=0, type=int, nargs='?',
                        help="Add this number to the port number (optional)")
    args = parser.parse_args()

    port = args.start_port + args.offset_port
    logger.info("Starting Tornado on port %s", port)

    app = make_app()
    app.listen(port, address='127.0.0.1')
    try:
        tornado.ioloop.IOLoop.current().start()
    finally:
        print("Stopping the server :(")
Error404Handler
