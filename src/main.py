from zulip_handler import zulipHandler
from database_handlers import notionHandler, zoteroHandler
from paper_handlers import arxiveHandler, openreviewHandler, zoteroTranslationHandler
from config import (
    ZULIP_EMAIL, ZULIP_API_KEY, ZULIP_SITE,
    NOTION_TOKEN, NOTION_DATABASE_ID,
    ZOTERO_API_KEY, ZOTERO_GROUP_ID
)
from handler_wrapper import HandlerWrapper
import atexit

if __name__ == "__main__":
    translation_handler = zoteroTranslationHandler()
    paper_handlers = [arxiveHandler(fallback=translation_handler), openreviewHandler(), translation_handler]

    database_handlers = [
        HandlerWrapper(
            notionHandler,
            init_kwargs={
                'auth_token': NOTION_TOKEN,
                'database_id': NOTION_DATABASE_ID
            },
            retry_interval=300  # Retry every 5 minutes
        ),
        HandlerWrapper(
            zoteroHandler,
            init_kwargs={
                'group_id': ZOTERO_GROUP_ID,
                'api_key': ZOTERO_API_KEY
            },
            retry_interval=300  # Retry every 5 minutes
        ),
    ]

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
        database_handlers=database_handlers
    )
    zlp_handler.run()
