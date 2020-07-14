
from aiogram.bot import Bot
from aiogram.utils.exceptions import TelegramAPIError
import asyncio
from gallery_dl import config, job, exception, __version__ as gdl_version
from urlextract import URLExtract
import re
import traceback
import urllib3


class TGAction:

    def __init__(self, bot, chat_id, action, period=4):
        self.bot = bot
        self.action = action
        self.chat_id = chat_id
        self.period = period

    async def update(self):
        while True:
            await self.bot.send_chat_action(self.chat_id, self.action)
            await asyncio.sleep(self.period)

    async def __aenter__(self):
        self.task = asyncio.get_event_loop().create_task(self.update())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self.task:
            return
        if not self.task.cancelled():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


class NoUrlError(Exception):
    pass


class GetUrlJob(job.Job):
    """Print download urls"""
    maxdepth = 1

    def __init__(self, url, parent=None, depth=1):
        job.Job.__init__(self, url, parent)
        self.depth = depth
        self.urls = []
        if depth >= self.maxdepth:
            self.handle_queue = self.handle_url

    def handle_url(self, url, _):
        self.urls.append(url)

    def handle_urllist(self, urls, _):
        self.urls.extend(urls)
        # prefix = ""
        # for url in urls:
        #     print(prefix, url, sep="")
        #     prefix = "| "

    def handle_queue(self, url, _):
        try:
            GetUrlJob(url, self, self.depth + 1).run()
        except exception.NoExtractorError:
            self._write_unsupported(url)


config.load()  # load default config files
config.set(("extractor",), "image-range", "1")
config.set(("extractor",), "chapter-range", "1")
config.set(("extractor",), "download", False)
config.set(("extractor",), "timeout", 10)
config.set(("extractor",), "verify", False)
config.set(("extractor",), "sleep", 0.01)

url_extractor = URLExtract()


# get cmd name from message
def cmd_from_message(message):
    cmd = None
    if 'entities' in message:
        for e in message['entities']:
            if e['type'] == 'bot_command':
                cmd = message['text'][e['offset'] + 1:e['length']]

    return cmd


async def get_img_links(url):
    return await asyncio.get_event_loop().run_in_executor(None, _get_img_links, url)


def _get_img_links(url):
    j = GetUrlJob(url)
    j.run()
    return j.urls


async def _main(params):
    task = asyncio.wait_for(_main_task(params), int(params['TIMEOUT']))
    try:
        await task
    except asyncio.TimeoutError:
        print('Request timeout')
    except Exception:
        traceback.print_exc()

async def _main_task(params):
    try:
        bot = Bot(params['BOT_TOKEN'])
        msg = params['message']
        chat_id = msg['chat']['id']
        msg_txt = msg.get('text')

        print(msg)
        if not msg_txt:
            await bot.send_message(chat_id, 'Please send me url to image')
            return
        if msg_txt == '/start':
            await bot.send_message(chat_id, 'Send me url to image and i\'ll upload it to telegram')
            return
        if msg_txt == '/version':
            await bot.send_message(chat_id, 'gallery-dl version: ' + gdl_version)
            return
        cmd = cmd_from_message(msg)
        if cmd is not None:
            if cmd == 'all':
                # retrieve all avalibale links
                config.unset(("extractor",), "image-range")
            elif cmd == 'p':
                # granular image links extraction
                pic_range_re = re.compile('([0-9]+)(-([0-9]+))?')
                pic_range_match = pic_range_re.search(msg_txt)
                if pic_range_match is None:
                    await bot.send_message(chat_id, 'Wrong command, correct example: /p 3-10 manga.com/chapter1')
                    return
                start, _, end = pic_range_match.groups()
                if end is None:
                    config.set(("extractor",), "image-range", start)
                elif int(start) > int(end):
                    await bot.send_message(chat_id, 'Start number bigger then end, correct example: /p 3-10 manga.com/chapter1')
                    return
                else:
                    config.set(("extractor",), "image-range", start+'-'+end)
        try:
            await handle_request(bot, chat_id, msg_txt)
        except NoUrlError:
            if msg['chat']['type'] == 'private':
                if cmd is not None:
                    if cmd == 'all':
                        await bot.send_message(chat_id, 'Wrong command, correct example: /all manga.com/chapter1')
                    elif cmd == 'p':
                        await bot.send_message(chat_id, 'Wrong command, correct example: /p 3-10 manga.com/chapter1')
                else:
                    await bot.send_message(chat_id, 'Couldn\'t find any url in message, send me one')
            print('No url in message')
    except asyncio.CancelledError:
        try:
            if msg['chat']['type'] == 'private':
                await bot.send_message(chat_id, 'Request timeout')
        except TelegramAPIError as e:
            print(e.__class__.__name__ + ': ' + str(e))
        raise
    except exception.NoExtractorError:
        try:
            if msg['chat']['type'] == 'private':
                await bot.send_message(chat_id, 'ERROR: Unsupported URL')
        except TelegramAPIError as e:
            print(e.__class__.__name__ + ': ' + str(e))
    except Exception as e:
        try:
            if msg['chat']['type'] == 'private':
                await bot.send_message(chat_id, 'ERROR: ' + str(e))
        except TelegramAPIError as e:
            print(e.__class__.__name__ + ': ' + str(e))
        traceback.print_exc()


async def handle_request(bot, chat_id, msg_txt):
    urls = url_extractor.find_urls(msg_txt)
    if len(urls) == 0:
        raise NoUrlError()
    direct_urls = await get_img_links(urls[0])
    if len(direct_urls) == 0:
        raise Exception('failed find photos')
    async with TGAction(bot, chat_id, "upload_photo"):
        for u in direct_urls:
            try:
                await bot.send_photo(chat_id, u)
                await asyncio.sleep(0.1)
            except TelegramAPIError as e:
                print(e.__class__.__name__ + ': ' + str(e))
    return None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def main(params):
    asyncio.get_event_loop().run_until_complete(_main(params))
    return {}

