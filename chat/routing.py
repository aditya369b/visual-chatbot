from channels.routing import route, include
from chat.consumers import ws_message, ws_connect, ws_check, ws_check2

ws_routing = [
    route("websocket.receive", ws_message),
    route("websocket.connect", ws_connect),
]

ws_routing2 = [
	route("websocket.receive", ws_check),
	route("websocket.connect", ws_check2),
]

channel_routing = [
    include(ws_routing, path=r"^/chat"),
    include(ws_routing2, path=r"^/users"),
]
