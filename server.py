#!/usr/bin/env python
import tornado.ioloop
import tornado.web
from tornado.web import HTTPError
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

logger = logging.getLogger(__name__)
tornado.ioloop.IOLoop.current().set_blocking_log_threshold(1)

APP_KEY = os.environ.get('DBX_APP_KEY')
APP_SECRET = os.environ.get('DBX_APP_SECRET')
BASE_URL = os.environ.get('BASE_URL')

class PublicFolderHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self, uid, path):
        pass

class ListFolderHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
        pass

class LoginHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
        print(self.request.uri)
        url = urllib.parse.urljoin(BASE_URL, '/login/continue')
        self.redirect('https://www.dropbox.com/oauth2/authorize?client_id={client_id}&redirect_uri={redirect_uri}'.format(client_id=APP_KEY, redirect_uri=urllib.parse.quote(url)))

class LoginContinueHandler(tornado.web.RequestHandler):
    @gen.coroutine
    def get(self):
        print(self.request.uri)
        self.write(self.request.uri)

def make_app():
    return tornado.web.Application([
        (r"/(\d+)/(.*)", PublicFolderHandler),
        (r"/list", ListFolderHandler),
        (r"/login", LoginHandler),
        (r"/login/continue", LoginContinueHandler),
    ], debug=True)

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
