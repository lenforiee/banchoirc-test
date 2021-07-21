import socket
import time
import re
import select
import traceback
import socketserver
from typing import Set, Union, List, Dict

NAME = "Kisumi"
VERSION = ".".join(list(map(str, (0,0,1)))) + "alpha"
WHITE_SPACE = re.compile(r"\r?\n")

def safe_name(string: Union[str, bytes]):
    if isinstance(string, bytes):
        return string.lower().replace(b" ", b"_").rstrip()

    return string.lower().replace(" ", "_").rstrip()

# Custom Bancho IRC exception.
class BanchoIRCException(Exception):
    """Custom expection."""
    def __init__(self, code_error: int, error: str):
        self.code: int = code_error
        self.error: str = error

    def __str__(self):
        return repr(self.error)

class BanchoClient(socketserver.BaseRequestHandler):
    """Represents a standalone client."""
    def __init__(self, request, address, server):
        self.server: BanchoIRC = server
        self.addresses = address
        self.request: socket.socket = request
        self.nickname: str = ""
        self.ping_time: int = int(time.time())
        self.queue: bytearray = bytearray() # Bytearray is much faster than bytes.
        self.safe_nick: str = ""
        self.channels: List[BanchoChannel] = []
        super().__init__(request, address, server)
    
    def __str__(self):
        return f"{self.nickname}!{self.nickname}@{NAME}"

    def dequeue(self):
        buffer = bytearray()
        buffer += self.queue
        self.queue = bytearray()
        return buffer

    def add_queue(self, message: str):
        self.queue += (message + "\r\n").encode()
    
    def handle(self):
        while True:
            reader, _, _ = select.select([self.request], [], [], 0.1)

            if (queue := self.dequeue()):
                self.request.send(queue)

            if self.request in reader:
                recived = self.request.recv(1024).decode("utf-8")

                if not recived:
                    # No data, no connection.
                    break
                try:
                    client_data = WHITE_SPACE.split(recived)[:-1]
                    for cmd in client_data:
                        print(cmd)
                        if len(cmd) > 0:
                            command, args = cmd.split(" ", 1)
                        else:
                            command, args = (cmd, "")

                        if command == "CAP":
                            continue

                        handler = getattr(self, f"handler_{command.lower()}", None)
                        if not handler:
                            raise BanchoIRCException(421, f"{command} :Unknown Command!")
                        handler(args)
                except BanchoIRCException as e:
                    self.request.send(f":{NAME} {e.code} {e.error}\r\n".encode())
                except Exception as e:
                    self.request.send(f":{NAME} ERROR {repr(e)}".encode())
                    print(traceback.print_exc())

    def handler_nick(self, nickname):
        if not nickname:
            return self.add_queue(f":{NAME} 431 :No nickname was found!")

        self.nickname = nickname
        self.safe_nick = safe_name(self.nickname)

        if self.safe_nick in self.server.clients:
            raise BanchoIRCException(432, f"NICK :{nickname}")

        self.server.on_add_client(self)
        self.add_queue(f":{NAME} 001 {self.nickname} :Welcome to the Internet Relay Network {str(self)}!")
        self.add_queue(f":{NAME} 251 :There are {len(self.server.clients)} users and 0 services on 1 server")
        self.add_queue(f":{NAME} 375 :- {NAME} Message of the day -")
        self.add_queue(f":{NAME} 372 {self.nickname} :- {self.server.motd}")
        self.add_queue(f":{NAME} 376 :End of MOTD command")

    def handler_ping(self, _):
        self.ping_time = int(time.time())
        self.add_queue(f":{NAME} PONG :{NAME}")

    def handler_privmsg(self, args):
        channel, msg = args.split(" ", 1)
        if channel.startswith("#") or channel.startswith("$"):
            chan = self.server.channels.get(channel)
            if not chan:
                raise BanchoIRCException(403, f"{channel} :Cannot send message to not existing channel")

            if not chan in self.channels:
                raise BanchoIRCException(404, f"{channel} :Cannot send the message to channel!")
            for client in filter(lambda u: u != self, chan.users):
                client.add_queue(f":{str(self)} PRIVMSG {channel} {msg}")
        else:
            user = self.server.clients.get(channel, None)

            if not user:
                raise BanchoIRCException(401, f"PRIVMSG :{channel}")
            user.add_queue(f":{str(self)} PRIVMSG {channel} {msg}")
    
    def handler_part(self, channel: str):
        chan = self.server.channels.get(channel, None)
        if chan in self.channels:
            if not chan:
                pass

            for client in chan.users:
                client.add_queue(f":{str(self)} PART :{channel}")
            self.part_channel(chan)
        else:
            self.add_queue(f":{NAME} 403 {channel} {channel}")

    def handler_join(self, channel: str):
        chan = self.server.channels.get(channel, None)

        if not chan:
            raise BanchoIRCException(403, f"{channel} :No channel named {channel} has been found!")
        self.join_channel(chan)
        
        #self.add_queue(f":Unknown TOPIC {chan.name} :{chan.description}")
        for client in chan.users:
            client.add_queue(f":{str(self)} JOIN :{chan.name}")

        nicks = " ".join([client.nickname for client in chan.users])
        self.add_queue(f":{NAME} 353 {self.nickname} = {chan.name} :{nicks}")
        self.add_queue(f":{NAME} 366 {self.nickname} {chan.name} :End of /NAMES list")

    def handler_user(self, args):
        # Not really useful for me.
        pass
    
    def handler_quit(self, args):
        resp = f":{str(self)} QUIT :{args.lstrip(':')}"
        for chan in self.channels:
            for client in chan.users:
                client.add_queue(resp)

            chan.on_user_leave(self)
        self.server.on_remove_client(self)
    
    def join_channel(self, channel):
        if channel and channel not in self.channels:
            self.channels.append(channel)
            channel.on_user_join(self)

    def part_channel(self, channel):
        if channel and channel in self.channels:
            self.channels.remove(channel)
            channel.on_user_leave(self)

class BanchoIRC(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """A main IRC server instance."""
    def __init__(self, address: tuple, handler_class: BanchoClient):
        self.daemon_threads = True
        self.allow_reuse_address = True
        self.server_name: str = NAME
        self.address: tuple = address
        self.channels: Dict[str, BanchoChannel] = {"#polish": BanchoChannel(self, "#polish", "Polski kanał dla polaków", False)}
        self.clients: Dict[str, BanchoClient] = {}
        self.motd: str = f"Welcome to {NAME} Bancho Internet Relay Chat Protocol v{VERSION}!"
        super().__init__(address, handler_class)

    def on_add_client(self, client: BanchoClient):
        self.clients[client.safe_nick] = client

    def on_remove_client(self, client: BanchoClient):
        del self.clients[client.safe_nick]

    def destruct_channel(self, channel):
        del self.channels[channel.name]

class BanchoChannel:
    """Represetnts a one bancho text channel."""
    def __init__(self, server: BanchoIRC, name: str, desc: str, destruct: bool = True) -> None:
        self.server: BanchoIRC = server
        self.name: str = name
        self.destructable: bool = destruct
        self.safe_name: str = safe_name(self.name)
        self.description: str = desc
        self.users: Set[BanchoClient] = set()
        self._key: bytes = b""

    def on_user_join(self, user: BanchoClient) -> None:
        self.users.add(user)

    def on_user_leave(self, user: BanchoClient) -> None:
        self.users.remove(user)
        if not self.users and self.destructable:
            self.server.destruct_channel(self)

bancho = BanchoIRC(("127.0.0.1", 6667), BanchoClient)
bancho.serve_forever()