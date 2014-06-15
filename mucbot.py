#!/usr/bin/env python
import argparse
import inspect
import logging
import os
import random
import requests
from html.parser import HTMLParser

import feedparser
from sleekxmpp import ClientXMPP

class MUCBot(ClientXMPP):
    _NO_VOTINGS_MESSAGE = 'No votings at the moment'
    _CMD_PREFIX = '!'

    def __init__(self, jid, password, surl_api,
                 surl_sig, muc_room, muc_nick):
        super().__init__(jid, password)
        self._surl_api = surl_api
        self._surl_sig = surl_sig
        self._vote_subject = None
        self._votes_up = set()
        self._votes_down = set()
        self._slaps = ()
        self._muc_room = muc_room
        self._muc_nick = muc_nick
        self._cmds = {'help': self._help,
                      'chuck': self._chuck_norris,
                      'surl': self._shorten_url,
                      'wiki': self._wikipedia,
                      'taunt': self._taunt}
        self._muc_cmds = {'help': self._help,
                          'chuck': self._chuck_norris,
                          'surl': self._shorten_url,
                          'vstart': self._vote_start,
                          'vup': self._vote_up,
                          'vdown': self._vote_down,
                          'vstat': self._vote_stat,
                          'vend': self._vote_end,
                          'slap': self._slap,
                          'meal': self._meal,
                          'hug': self._hug,
                          'kiss': self._kiss,
                          'wiki': self._wikipedia,
                          'taunt': self._taunt}
        self.add_event_handler('session_start', self.start)
        self.add_event_handler('message', self.message)
        self.register_plugin('xep_0045')

    def start(self, event):
        self.get_roster()
        self.send_presence()
        self.plugin['xep_0045'].joinMUC(self._muc_room,
                                        self._muc_nick,
                                        wait=True)

    def message(self, msg):
        body = msg['body']
        if not body.startswith(self._CMD_PREFIX):
            return
        msg_type = msg['type']
        cmd_args = body.strip().split(' ')
        # Strip command prefix
        cmd = cmd_args[0][len(self._CMD_PREFIX):]
        # MUC provides more commands as normal chat
        if msg_type in ('normal', 'chat'):
            cmds = self._cmds
        elif msg_type == 'groupchat':
            cmds = self._muc_cmds
        if cmd not in cmds:
            return
        resp = cmds[cmd](msg, *cmd_args[1:])
        if msg_type in ('normal', 'chat'):
            msg.reply(resp).send()
        elif msg_type == 'groupchat':
            # Send help always as normal chat
            if cmd == 'help':
                self.send_message(mto=msg['from'],
                                  mbody=resp,
                                  mtype='chat')
            else:
                self.send_message(mto=msg['from'].bare,
                                  mbody=resp,
                                  mtype=msg_type)

    def _help(self, msg, *args):
        """Returns a help string containing all commands"""
        msg_type = msg['type']
        # MUC provides more commands as normal chat
        if msg_type in ('normal', 'chat'):
            cmds = self._cmds
        elif msg_type == 'groupchat':
            cmds = self._muc_cmds
        docs = []
        if args: # help <command>
            cmd = args[0]
            if len(args) > 1 or cmd not in cmds:
                return
            doc = inspect.getdoc(cmds[cmd])
            docs.append(doc)
        else: # help
            docs.append('Available commands:{}'.format(os.linesep))
            for cmd in sorted(cmds.keys()):
                doc = inspect.getdoc(cmds[cmd])
                if cmd == 'help' or not doc:
                    continue
                lines = doc.splitlines()
                docs.append('{}{}: {}'.format(self._CMD_PREFIX, cmd, lines[0]))
            bottom = ('{0}Type !help <command name> to get more info '
                      'about that specific command.').format(os.linesep)
            docs.append(bottom)
        src = 'Source code available at http://kurzma.ch/botsrc'
        docs.append(src)
        return os.linesep.join(docs)

    def _chuck_norris(self, msg, *args):
        """Displays a random Chuck Norris joke from http://icndb.com

You can optionally change the name of the main character by appending \
him as arguments: chuck <firstname> <lastname>
        """
        params = None
        if args:
            if len(args) != 2:
                return 'You must append a firstname *and* a lastname'
            params = {'firstName': args[0], 'lastName': args[1]}
        request = requests.get('http://api.icndb.com/jokes/random',
                               params = params)
        joke = request.json()['value']['joke']
        return HTMLParser().unescape(joke)

    def _shorten_url(self, msg, *args):
        """Shorten a URL with the http://kurzma.ch URL shortener

shorturl http://myurl.com
        """
        if not args:
            return "You must provide a URL to shorten"
        params = {'signature': self._surl_sig,
                  'url': args,
                  'action': 'shorturl',
                  'format': 'json'}
        request = requests.get(self._surl_api, params = params)
        if request.status_code == requests.codes.ok:
            json = request.json()
            return '{}: {}'.format(json['title'], json['shorturl'])
        return 'Something went wrong :('

    def _vote_start(self, msg, *args):
        """Starts a voting

You have to provide a subject: vstart <subject>
        """
        if self._vote_subject:
            return 'A vote is already running'
        if not args:
            return 'No subject given. Use vstart <subject>'
        self._vote_subject = ' '.join(args)
        return 'Voting started'

    def _vote_up(self, msg, *args):
        """Vote up for the current voting"""
        if not self._vote_subject:
            return self._NO_VOTINGS_MESSAGE
        user = msg['from'].resource
        if user in self._votes_up:
            return 'You already voted {}'.format(user)
        if user in self._votes_down:
            self._votes_down.remove(user)
        self._votes_up.add(user)
        return '{} voted up'.format(user)

    def _vote_down(self, msg, *args):
        """Vote down for the current voting"""
        if not self._vote_subject:
            return self._NO_VOTINGS_MESSAGE
        user = msg['from'].resource
        if user in self._votes_down:
            return 'You already voted down'
        if user in self._votes_up:
            self._votes_up.remove(user)
        self._votes_down.add(user)
        return '{} voted down'.format(user)

    def _vote_stat(self, msg, *args):
        """Displays statistics for the current voting"""
        if self._vote_subject:
            return 'Subject: "{}". Votes up: {:d}. Votes down: {:d}'.format(
                self._vote_subject,
                len(self._votes_up),
                len(self._votes_down))
        return self._NO_VOTINGS_MESSAGE

    def _vote_end(self, msg, *args):
        """Ends the current voting and shows the result"""
        if not self._vote_subject:
            return self._NO_VOTINGS_MESSAGE
        result = 'Voting "{}" ended. {:d} votes up. {:d} votes down'.format(
            self._vote_subject,
            len(self._votes_up),
            len(self._votes_down))
        self._vote_subject = None
        self._votes_up.clear()
        self._votes_down.clear()
        return result

    def _slap(self, msg, *args):
        """Slaps the given user

Simply type: !slap <nick> an it will slap the person
        """
        nick = ' '.join(args)
        if not nick:
            return 'You have to provide a nick name'
        dirpath = os.path.dirname(os.path.realpath(__file__))
        filepath = os.path.join(dirpath, 'slaps.txt')
        with open(filepath) as f:
            slaps = tuple(slap.strip() for slap in f)
            slap = random.choice(slaps).format(nick=nick)
            return '/me {}'.format(slap)

    def _meal(self, msg, *args):
        """Displays a 'enjoy your meal' message"""
        return 'Guten Appetit'

    def _hug(self, msg, *args):
        """Hugs the given user"""
        if args:
            return '/me hugs {}'.format(' '.join(args))
        else:
            return 'Who should I hug?'

    def _kiss(self, msg, *args):
        """Kisses the given user

You can optionally specify the part of the body: \
kiss <nick> <part of body>
        """
        args_len = len(args)
        if not args:
            return 'Who should I kiss?'
        if args_len == 1:
            return '/me kisses {} :-*'.format(args[0])
        elif args_len == 2:
            return '/me kisses {} on the {} :-*'.format(args[0], args[1])
        else:
            return 'Too many arguments'

    def _wikipedia(self, msg, *args):
        """Displays a random page from the german Wikipedia

You can display today's featured article: wiki today
        """
        if 'today' in args:
            url = ('https://de.wikipedia.org/w/api.php'
                   '?action=featuredfeed&feed=featured')
            feed = feedparser.parse(url)
            today = feed['items'][-1]
            return self._shorten_url(msg, today['link'])
        params = {'action': 'query',
                  'format': 'json',
                  'generator': 'random',
                  'grnnamespace': 0,
                  'grnlimit': 1,
                  'prop': 'info',
                  'inprop': 'url'}
        req = requests.get('http://de.wikipedia.org/w/api.php', params=params)
        json = req.json()
        pages = json['query']['pages']
        page = list(pages.values())[0]
        url = self._shorten_url(msg, page['fullurl'])
        return '{}'.format(url)

    def _taunt(self, msg, *args):
        """Taunts the given user"""
        dirpath = os.path.dirname(os.path.realpath(__file__))
        filepath = os.path.join(dirpath, 'mother_jokes.txt')
        with open(filepath) as f:
            jokes = tuple(joke.strip() for joke in f)
        joke = random.choice(jokes)
        nick = "{}'s".format(' '.join(args)) if args else 'Deine'
        return joke.format(nick=nick)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('jid',
                        help='the JID of the bot')
    parser.add_argument('pwd',
                        help='the password for the given JID')
    parser.add_argument('surl_api',
                        help='the API URL to the URL shortener')
    parser.add_argument('surl_sig',
                         help='the signaturen for the URL shortener')
    parser.add_argument('muc_room',
                        help='the MUC room to join')
    parser.add_argument('muc_nick',
                        help='the nick name that should be used')
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR,
                        format='%(levelname)-8s %(message)s')
    bot = MUCBot(args.jid, args.pwd, args.surl_api,
                 args.surl_sig, args.muc_room, args.muc_nick)
    bot.connect()
    bot.process(block=True)
