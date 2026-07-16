"""
Sends updates to a Discord bot.

Usage:
>>> from tqdm.contrib.discord import tqdm, trange
>>> for i in trange(10, token='{token}', channel_id='{channel_id}'):
...     ...

![screenshot](https://tqdm.github.io/img/screenshot-discord.png)
"""
from warnings import warn

from requests import Session
from requests.utils import default_user_agent

from ..auto import tqdm as tqdm_auto
from ..std import TqdmWarning
from ..utils import envwrap
from ..version import __version__
from .utils_worker import MonoWorker

__author__ = {"github.com/": ["casperdcl", "guigoruiz1"]}
__all__ = ['DiscordIO', 'tqdm_discord', 'tdrange', 'tqdm', 'trange']


class DiscordIO(MonoWorker):
    """Non-blocking file-like IO using a Discord Bot."""
    API = 'https://discord.com/api/v10'
    UA = f"tqdm (https://tqdm.github.io, {__version__}) {default_user_agent()}"

    def __init__(self, token, channel_id):
        """Creates a new message in the given `channel_id`."""
        super().__init__()
        self.token = token
        self.channel_id = channel_id
        self.session = Session()
        self.text = self.__class__.__name__
        self.message_id  # pylint: disable=pointless-statement

    @property
    def message_id(self):
        if hasattr(self, '_message_id'):
            return self._message_id  # pylint: disable=access-member-before-definition
        try:
            req = self.session.post(
                f'{self.API}/channels/{self.channel_id}/messages',
                headers={'Authorization': f'Bot {self.token}', 'User-Agent': self.UA},
                json={'content': f"`{self.text}`"})
            res = req.json()
            req.raise_for_status()
        except Exception as e:
            if req.status_code == 429:
                warn("Creation rate limit: try increasing `mininterval`.",
                     TqdmWarning, stacklevel=2)
            else:
                tqdm_auto.write(str(e))
        else:
            self._message_id = res['id']
            return self._message_id

    def write(self, s):
        """Replaces internal `message_id`'s text with `s`."""
        if not s:
            s = "..."
        s = s.replace('\r', '').strip()
        if s == self.text:
            return  # avoid duplicate message Bot error
        message_id = self.message_id
        if message_id is None:
            return
        self.text = s
        try:
            future = self.submit(
                self.session.patch,
                f'{self.API}/channels/{self.channel_id}/messages/{message_id}',
                headers={'Authorization': f'Bot {self.token}', 'User-Agent': self.UA},
                json={'content': f"`{self.text}`"})
        except Exception as e:
            tqdm_auto.write(str(e))
        else:
            return future

    def delete(self):
        """Deletes internal `message_id`."""
        try:
            future = self.submit(
                self.session.delete,
                f'{self.API}/channels/{self.channel_id}/messages/{self.message_id}',
                headers={'Authorization': f'Bot {self.token}', 'User-Agent': self.UA})
        except Exception as e:
            tqdm_auto.write(str(e))
        else:
            return future


class tqdm_discord(tqdm_auto):  # pylint: disable=inconsistent-mro
    """
    Standard `tqdm.auto.tqdm` but also sends updates to a Discord Bot.
    May take a few seconds to create (`__init__`).

    - create a discord bot (not public, no requirement of OAuth2 code
      grant, only send message permissions) & invite it to a channel:
      <https://discordpy.readthedocs.io/en/latest/discord.html>
    - copy the bot `{token}` & `{channel_id}` and paste below

    >>> from tqdm.contrib.discord import tqdm, trange
    >>> for i in tqdm(iterable, token='{token}', channel_id='{channel_id}'):
    ...     ...
    """
    @envwrap("tqdm", "discord", is_method=True)
    def __init__(self, *args, token=None, channel_id=None, **kwargs):
        """
        Parameters
        ----------
        token  : str, required. Discord bot token
            [default: ${TQDM_DISCORD_TOKEN}].
        channel_id  : int, required. Discord channel ID
            [default: ${TQDM_DISCORD_CHANNEL_ID}].

        See `tqdm.auto.tqdm.__init__` for other parameters.
        """
        if not kwargs.get('disable'):
            kwargs = kwargs.copy()
            self.dio = DiscordIO(token, channel_id)
        super().__init__(*args, **kwargs)

    def display(self, **kwargs):  # pylint: disable=arguments-differ
        super().display(**kwargs)
        fmt = self.format_dict
        if fmt.get('bar_format', None):
            fmt['bar_format'] = fmt['bar_format'].replace(
                '<bar/>', '{bar:10u}').replace('{bar}', '{bar:10u}')
        self.dio.write(self.format_meter(**fmt))

    def clear(self, *args, **kwargs):
        super().clear(*args, **kwargs)
        if not self.disable:
            self.dio.write("")

    def close(self):
        if self.disable:
            return
        super().close()
        if not (self.leave or (self.leave is None and self.pos == 0)):
            self.dio.delete()


def tdrange(*args, **kwargs):
    """Shortcut for `tqdm.contrib.discord.tqdm(range(*args), **kwargs)`."""
    return tqdm_discord(range(*args), **kwargs)


# Aliases
tqdm = tqdm_discord
trange = tdrange
