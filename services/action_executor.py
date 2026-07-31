import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

ACTION_DISPLAY_NAMES = {
    'hue.toggle': 'Toggle light',
    'hue.on': 'Turn light on',
    'hue.off': 'Turn light off',
    'wemo.toggle': 'Toggle {device}',
    'wemo.on': 'Turn {device} on',
    'wemo.off': 'Turn {device} off',
    'rinnai.circulate': 'Run water heater circulation for {duration} minutes',
    'garage.toggle': 'Toggle garage door {door}',
    'roon.play': 'Play {source} on {zone}',
    'roon.pause': 'Pause {zone}',
    'roon.stop': 'Stop {zone}',
}


def get_action_display(action_type: str, params: dict) -> str:
    template = ACTION_DISPLAY_NAMES.get(action_type, action_type)
    try:
        return template.format(**params)
    except (KeyError, ValueError):
        return action_type


class ActionExecutor:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}
    
    def register(self, action_type: str, handler: Callable):
        self._handlers[action_type] = handler
        logger.debug(f"Registered action handler: {action_type}")
    
    async def execute(self, action_type: str, params: dict) -> dict:
        handler = self._handlers.get(action_type)
        if not handler:
            return {"status": "error", "message": f"Unknown action type: {action_type}"}
        
        try:
            result = handler(params)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        except Exception as e:
            logger.exception(f"Error executing action {action_type}: {e}")
            return {"status": "error", "message": str(e)}


action_executor = ActionExecutor()


def init_action_executor():
    from services.hue_service import hue_service
    from services.wemo_service import wemo_service
    from services.rinnai_service import rinnai_service
    from services.meross_service import meross_service
    
    action_executor.register('hue.toggle', lambda _: hue_service.toggle())
    action_executor.register('hue.on', lambda p: hue_service.turn_on(p.get('brightness', 128)))
    action_executor.register('hue.off', lambda _: hue_service.turn_off())
    
    action_executor.register('wemo.toggle', lambda p: wemo_service.toggle(p['device']))
    action_executor.register('wemo.on', lambda p: wemo_service.turn_on(p['device']))
    action_executor.register('wemo.off', lambda p: wemo_service.turn_off(p['device']))
    
    action_executor.register('rinnai.circulate', lambda p: rinnai_service.start_circulation(p.get('duration', 5)))
    action_executor.register('garage.toggle', lambda p: meross_service.toggle_door(p['door']))

    from services.roon_service import roon_service

    def _roon_play(params: dict):
        source = (params.get("source") or "queue").lower()
        zone = params["zone"]
        if source == "playlist":
            playlist = params.get("playlist")
            if not playlist:
                return {"status": "error", "message": "playlist is required when source=playlist"}
            return roon_service.play_playlist(zone, playlist)
        return roon_service.play_queue(zone)

    action_executor.register("roon.play", _roon_play)
    action_executor.register("roon.pause", lambda p: roon_service.pause(p["zone"]))
    action_executor.register("roon.stop", lambda p: roon_service.stop(p["zone"]))
    
    logger.info("Action executor initialized")
