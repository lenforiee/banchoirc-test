import socket
import time
import select
from typing import Set, Union, List

def safe_name(string: Union[str, bytes]):
    if isinstance(string, bytes):
        return string.lower().replace(b" ", b"_").rstrip()

    return string.lower().replace(" ", "_").rstrip()

# Custom Bancho IRC exception.
class BanchoIRCException(Exception):
    """Custom expection."""
    pass

class BanchoIRC:
    """A main IRC server instance."""
    def __init__(self, name: str, address: tuple):
        self.server_name: str = name
        self.address: tuple = address
        self.channels: List[BanchoChannel] = []
        self.clients: Set[BanchoClient] = set()

    def on_add_client(self, client: BanchoClient):
        self.clients.add(client)

    def on_remove_client(self, client: BanchoClient):
        self.clients.remove(client)

class BanchoChannel:
    """Represetnts a one bancho text channel."""
    def __init__(self, server: BanchoIRC, name: bytes, desc: bytes, destruct: bool = True, autojoin: bool = False) -> None:
        self.server: BanchoIRC = server
        self.name: bytes = name
        self.auto_join: bool = autojoin
        self.destructable: bool = destruct
        self.safe_name: bytes = safe_name(self.name)
        self.description: bytes = desc
        self.users: Set[BanchoClient] = {}
        self._key: bytes = b""

    def on_user_join(self, user: BanchoClient) -> None:
        self.users.add(user)

    def on_user_leave(self, user: BanchoClient) -> None:
        self.users.remove(user)
        if not self.users and self.destructable:
            self.server.destruct_channel(self)

class BanchoClient:
    """Represents a standalone client."""
    def __init__(self, server: BanchoIRC, client: socket.socket):
        self.server: BanchoIRC = server
        self.client: socket.socket = client
        self.nickname: bytes = None
        self.ping_time: int = int(time.time())
        self.queue: bytearray = bytearray() # Bytearray is much faster than bytes.
        self.safe_nick: bytes = safe_name(self.nickname)
        self.channels: List[BanchoChannel] = []
    
    def join_channel(self, channel: BanchoChannel):
        if channel and channel not in self.channels:
            self.channels.append(channel)
            channel.on_user_join(self)

    def part_channel(self, channel: BanchoChannel):
        if channel and channel in self.channels:
            self.channels.remove(channel)
            channel.on_user_join(channel)
