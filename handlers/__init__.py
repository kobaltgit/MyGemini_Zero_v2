"""
Handlers package for MyGemini Zero v2.
Registers and exports all aiogram 3.x routers in prioritized order.
"""

from aiogram import Dispatcher
from handlers.start import router as start_router
from handlers.commands import router as commands_router
from handlers.auth import router as auth_router
from handlers.history import router as history_router
from handlers.guide import router as guide_router
from handlers.translate import router as translate_router
from handlers.feedback import router as feedback_router
from handlers.profile import router as profile_router
from handlers.admin import router as admin_router
from handlers.settings import router as settings_router
from handlers.dialogs import router as dialogs_router
from handlers.memory import router as memory_router
from handlers.subscription import router as subscription_router
from handlers.chat import router as chat_router


def register_all_routers(dp: Dispatcher) -> None:
    """Includes all application routers in prioritized order."""
    # Priority 1: /start and Onboarding
    dp.include_router(start_router)
    # Priority 2: Slash commands & Reply buttons
    dp.include_router(commands_router)
    # Priority 3: Authentication & Vault unlock/panic
    dp.include_router(auth_router)
    # Priority 4: History & Interactive Calendar
    dp.include_router(history_router)
    # Priority 5: Documentation & Guides
    dp.include_router(guide_router)
    # Priority 6: Translation mode & Support Feedback
    dp.include_router(translate_router)
    dp.include_router(feedback_router)
    # Priority 7: Profile, Settings, Dialogs, Memory, Subscriptions
    dp.include_router(profile_router)
    dp.include_router(admin_router)
    dp.include_router(settings_router)
    dp.include_router(dialogs_router)
    dp.include_router(memory_router)
    dp.include_router(subscription_router)
    # Priority 8: General chat & multimodal fallback (must be last)
    dp.include_router(chat_router)
