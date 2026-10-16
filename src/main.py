from zulip_handler import zulipHandler
from database_handlers import notionHandler, zoteroHandler
from paper_handlers import arxiveHandler, openreviewHandler, zoteroTranslationHandler
import config
from config import ZULIP_EMAIL, ZULIP_API_KEY, ZULIP_SITE
from handler_wrapper import HandlerWrapper
import atexit
import sys


def database_handler(handler_class, **credentials):
    """Wraps a database handler, or returns None (disabling it) if any of its credentials
    in config.py are empty or missing. `credentials` maps init kwarg -> config variable name."""
    values = {kwarg: getattr(config, name, None) for kwarg, name in credentials.items()}
    missing = [credentials[kwarg] for kwarg, value in values.items() if not str(value or '').strip()]
    if missing:
        print(f"{handler_class.__name__} disabled: {', '.join(missing)} not set in config.py.")
        return None
    return HandlerWrapper(handler_class, init_kwargs=values, retry_interval=300)  # Retry every 5 minutes

if __name__ == "__main__":
    # Under systemd stdout is not a terminal, so print() output would be block-buffered
    # and show up in the journal late or not at all.
    sys.stdout.reconfigure(line_buffering=True)

    translation_handler = zoteroTranslationHandler()
    paper_handlers = [arxiveHandler(fallback=translation_handler), openreviewHandler(), translation_handler]

    database_handlers = [
        database_handler(notionHandler, auth_token='NOTION_TOKEN', database_id='NOTION_DATABASE_ID'),
        database_handler(zoteroHandler, group_id='ZOTERO_GROUP_ID', api_key='ZOTERO_API_KEY'),
    ]
    database_handlers = [handler for handler in database_handlers if handler is not None]
    if not database_handlers:
        print("Warning: no databases configured; papers will only be summarised in Zulip.")

    # Ensure that threads are stopped when the program exits
    def cleanup():
        for handler in database_handlers:
            handler.stop_periodic_reinitialization()
    atexit.register(cleanup)

    zlp_handler = zulipHandler(
        email=ZULIP_EMAIL,
        api_key=ZULIP_API_KEY,
        site=ZULIP_SITE,
        paper_handlers=paper_handlers,
        database_handlers=database_handlers,
        easter_egg_reply=getattr(config, 'EASTER_EGG_REPLY', None)  # optional reply to "Guess who's back?"
    )
    zlp_handler.run()
