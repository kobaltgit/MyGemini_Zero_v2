"""
Handlers package for MyGemini Zero v2.
Registers and exports all aiogram 3.x routers.
"""

from aiogram import Dispatcher
from handlers.commands import router as commands_router
from handlers.start import router as start_router
from handlers.auth import router as auth_router
from handlers.profile import router as profile_router
from handlers.admin import router as admin_router
from handlers.settings import router as settings_router
from handlers.dialogs import router as dialogs_router
from handlers.memory import router as memory_router
from handlers.subscription import router as subscription_router
from handlers.chat import router as chat_router


def register_all_routers(dp: Dispatcher) -> None:
    """Includes all application routers in prioritized order."""
    # Priority 1: Slash commands & Reply keyboard buttons
    dp.include_router(commands_router)
    dp.include_router(start_router)
    dp.include_router(auth_router)
    dp.include_router(profile_router)
    dp.include_router(admin_router)
    dp.include_router(settings_router)
    dp.include_router(dialogs_router)
    dp.include_router(memory_router)
    dp.include_router(subscription_router)
    # Chat router must be included last to catch text/multimodal fallbacks
    dp.include_router(chat_router)
