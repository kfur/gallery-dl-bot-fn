
import telebot
from gallery_dl import config, job, exception
from urlextract import URLExtract

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
config.set(("extractor",), "image-range", "1-10")
config.set(("extractor",), "download", False)
config.set(("extractor",), "timeout", 2)

url_extractor = URLExtract()

def get_img_links(url):
    j = GetUrlJob(url)
    j.run()
    return j.urls


def main(params):
    try:
        bot = telebot.TeleBot(params['BOT_TOKEN'])
        msg = params['message']
        chat_id = msg['chat']['id']
        msg_txt = msg.get('text')
        if not msg_txt:
            bot.send_message(chat_id, 'Please send me url to image')
            return {}
        if msg_txt == '/start':
            bot.send_message(chat_id, 'Send me url to image and i\'ll upload it to telegram')
            return {}
        _main(bot, chat_id, msg_txt)
    except Exception as e:
        if msg['chat']['type'] == 'private':
            bot.send_message(chat_id, 'ERROR: ' + str(e))
        print('ERROR: ', e)

    return {}

def _main(bot, chat_id, msg_txt):
    urls = url_extractor.find_urls(msg_txt)
    if len(urls) == 0:
        return
    direct_urls = get_img_links(urls[0])
    for u in direct_urls:
        try:
            bot.send_photo(chat_id, u)
        except Exception as e:
            print('ERROR: ', e)
    return None
