import socket
import socketserver
from typing import Set, Union

# Custom Bancho IRC exception.
class BanchoIRCException(Exception):
    pass

class BanchoIRC:
    pass

class BanchoClient:
    pass

def safe_name(string: Union[str, bytes]):
    if isinstance(string, bytes):
        return string.lower().replace(b" ", b"_").rstrip()

    return string.lower().replace(" ", "_").rstrip()

class BanchoChannel:
    """Represetnts a one bancho text channel"""
    def __init__(self, server: BanchoIRC, name: bytes, desc: bytes, destruct: bool = True) -> None:
        self.server: BanchoIRC = server
        self.name: bytes = name
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
