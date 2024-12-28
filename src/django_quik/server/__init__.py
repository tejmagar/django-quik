import re
import socket
import threading
import uuid

from collections.abc import Callable
from threading import Thread
from typing import OrderedDict, List, Tuple

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from .http import (
    Stream,
    read_headers,
    parse_headers,
    modify_headers,
    build_header_bytes,
    StreamReadException,
    StreamWriteException,
    header_value,
    read_text_body
)
from ..config import Configuration


class ThreadSafeChangeCallbacks:
    """
    Thread Safe class to manage callbacks to work with file changes.
    """

    def __init__(self, configuration: Configuration):
        """
        Create new ThreadSafeChangeCallbacks instance.
        :param configuration: Configuration instance.
        """

        self.configuration = configuration
        self.dir_change_callbacks: dict[uuid, Callable] = {}
        self.lock = threading.Lock()

    def set_callback(self, key: uuid.UUID, callback: Callable) -> None:
        """
        Address new callback
        :param key: Unique UUID
        :param callback: Callable function
        :return: None
        """

        with self.lock:
            self.dir_change_callbacks.setdefault(key, callback)

    def remove_callback(self, key: uuid.UUID) -> None:
        """
        Remove callback function from the store.
        :param key: Unique UUID key of the callback.
        :return:
        """

        with self.lock:
            if self.dir_change_callbacks.get(key):
                del self.dir_change_callbacks[key]

    def get_all(self) -> dict:
        """
        Return dictionaries copy of consisting of key and callable function.
        :return: Callback functions.
        """

        with self.lock:
            return self.dir_change_callbacks.copy()


class FilesWatchEventHandler(FileSystemEventHandler):
    def __init__(self, dir_change_callbacks: ThreadSafeChangeCallbacks, delay: int = 0.8):
        """
        Create new FilesWatchEventHandler instance.

        :param dir_change_callbacks: Instance of ThreadSafeChangeCallbacks.
        :param delay: Delay in milliseconds to wait before broadcasting file change.
        """

        self.dir_change_callbacks = dir_change_callbacks
        self.timer = None
        self.delay = delay

    def on_modified(self, event: FileSystemEvent) -> None:
        if self.timer:
            # Timer already specified, cancel existing timer.
            self.timer.cancel()

        self.timer = threading.Timer(self.delay, self.trigger_notify)
        self.timer.start()

    def trigger_notify(self) -> None:
        for stream_id, callback in self.dir_change_callbacks.get_all().items():
            # Invoke callback function.
            callback()


class WebServer:
    """
    Custom webserver from scratch to proxy forward and notify file changes through websocket.
    """

    def __init__(self, configuration: Configuration):
        """
        Create new WebServer instance.
        :param configuration: Configuration
        """

        self.configuration = configuration

        # Unique UUID path for serving refresh text/event-stream event.
        self.refresh_path = f'/{str(uuid.uuid4())}/'

        self.dir_change_callbacks = ThreadSafeChangeCallbacks(configuration)

        # Start file change monitor thread.
        file_change_monitor_thread = threading.Thread(target=self.listen_files_change)
        file_change_monitor_thread.daemon = True
        file_change_monitor_thread.start()

    def listen_files_change(self):
        event_handler = FilesWatchEventHandler(self.dir_change_callbacks)
        observer = Observer()

        for path in self.configuration.watch_dirs:
            observer.schedule(event_handler, path, recursive=True)

        observer.start()

    def listen(self):
        # Create new server socket, bind in specified address and listen for incoming requests.
        server = socket.create_server((self.configuration.host, self.configuration.port), reuse_port=True)
        server.listen()

        while True:
            # Accept incoming TCP connection.
            client, _ = server.accept()

            # Spawn new thread for each client to run in background and continue accepting new clients.
            thread = Thread(target=self.handle_client, args=(client,))
            thread.daemon = True
            thread.start()

    def handle_client(self, sock: socket.socket) -> None:
        """
        Handle request of each client connection.
        :param sock: Socker instance of client.
        :return: None
        """

        stream = None

        try:
            stream = Stream(sock)
            header_bytes = read_headers(stream)
            request_info, headers = parse_headers(header_bytes)
            self.serve_page(stream, request_info, headers)
        except (StreamReadException, StreamWriteException, Exception):
            stream.close()

    def inject_event_code(self, html: str) -> str:
        """
        Inject reloading script in the HTML page.
        :param html:
        :return: HTML code with injected reloading script.
        """

        injected_code = '<script>\r\n'
        injected_code += f'const evtSource = new EventSource("{self.refresh_path}")'
        injected_code += '''
           evtSource.onmessage = (event) => {
             location.reload();
           };

           evtSource.onerror = () => {
             location.reload();
           }
           </script>
           '''

        # Search for body end tag and inject the reloading script.
        if re.search(r'</body>', html, re.IGNORECASE):
            html = re.sub(r'</body>', f'{injected_code}</body>', html, flags=re.IGNORECASE)

        return html

    @staticmethod
    def send_data_client_to_django_server(stream_client: Stream, stream_target: Stream) -> None:
        """
        Send data received from client to the Django server.

        :param stream_client: Stream client instance.
        :param stream_target: Stream target instance.
        :return: None
        """

        while True:
            try:
                stream_target.write_chunk(stream_client.read_chunk())
            except (StreamReadException, StreamWriteException, OSError, Exception):
                # If anything goes wrong, shutdown both streams.
                stream_client.close()
                stream_target.close()
                return

    def send_data_django_server_to_client(self, stream_target: Stream, stream_client: Stream) -> None:
        """
        Send data received from Django server to the client.

        :param stream_target: Stream target instance of Django Server.
        :param stream_client: Stream client instance.
        :return: None
        """

        # Read response headers from Django server.
        try:
            raw_headers = read_headers(stream_target)
        except (StreamReadException, StreamWriteException, OSError, Exception):
            # If anything goes wrong, shutdown both streams.
            stream_target.close()
            stream_client.close()
            return

        response_info, headers = parse_headers(raw_headers)

        # Extract content type from response.
        content_type = header_value(headers, 'Content-Type')

        # If response header is text/html, we read the whole html page and inject custom html code to
        # trigger file changes.
        if content_type and 'text/html' in content_type:
            try:
                # Read data from Django server.
                response_body = read_text_body(headers, stream_target)
                response_body = self.inject_event_code(response_body)
                response_body_bytes = response_body.encode()

                # Force connection close by the browser if Django server tries to use keep alive connection.
                modify_headers(headers, 'Content-Length', f'{len(response_body_bytes)}')

                # Inject custom header for debug purpose.
                modify_headers(headers, 'X-Proxy-Server', 'Django Quik Injected')

                response_info = ('HTTP/1.0', response_info[1], response_info[2])
                modify_headers(headers, 'Connection', 'Close')
                header_bytes = build_header_bytes(response_info, headers)

                # Write response headers received from Django server to connected client.
                stream_client.write_chunk(header_bytes)

                # Write response body to stream client.
                stream_client.write_chunk(response_body_bytes)

                stream_client.close()
                stream_target.close()
            except (StreamReadException, StreamWriteException, OSError, Exception) as e:
                stream_client.close()
                stream_target.close()

        else:
            upgrade_header = header_value(headers, 'Upgrade')

            # Except for websocket, downgrade HTTP version to HTTP/1.0.
            if not upgrade_header or (upgrade_header and not "websocket" in upgrade_header.lower()):
                # Downgrade HTTP Version to HTTP/1.0
                response_info = ('HTTP/1.0', response_info[1], response_info[2])
                modify_headers(headers, 'Connection', 'Close')

            # Inject custom header for debug purpose.
            modify_headers(headers, 'X-Proxy-Server', 'Django Quik Stream')

            # Body content is not modified, using existing headers without modification.
            header_bytes = build_header_bytes(response_info, headers)

            # Write response headers received from Django server to connected client.
            stream_client.write_chunk(header_bytes)

            # Proxy all other content types
            while True:
                try:
                    stream_client.write_chunk(stream_target.read_chunk())
                except (StreamReadException, StreamWriteException, OSError, Exception):
                    # If anything goes wrong, shutdown both streams.
                    stream_target.close()
                    stream_client.close()
                    return

    def serve_refresh_event_page(self, stream_client: Stream) -> None:
        """
        Refresh page using server side event.
        :param stream_client: Stream client instance.
        :return:
        """

        response_headers = 'HTTP/1.0 200 OK\r\n'
        response_headers += 'Content-Type: text/event-stream\r\n'
        response_headers += 'Cache-Control: no-cache\r\n'
        response_headers += 'Connection: keep-alive\r\n'
        response_headers += '\r\n'

        stream_id = uuid.uuid4()

        # Write response headers immediately.
        stream_client.write_chunk(response_headers.encode())

        def file_change_callback():
            """
            Function for sending server side events data.
            :return:
            """

            try:
                print('File changed. Reloading page...')
                stream_client.write_chunk('data: file changed\n\n'.encode())
            except (StreamReadException, StreamWriteException, OSError, Exception):
                self.dir_change_callbacks.remove_callback(stream_id)

        # Attach callbacks to thread safe ThreadSafeChangeCallbacks instance.
        self.dir_change_callbacks.set_callback(stream_id, file_change_callback)

    def serve_page(self, stream_client: Stream, request_info: Tuple[str, str, str],
                   headers: OrderedDict[str, List[str]]) -> None:
        """
        Serve one page per connection. Supports HTTP/1.0, HTTP/1.1 and WebSocket protocol.

        :param stream_client: Stream client instance.
        :param request_info: Tuple of (request_method, path, http_version)
        :param headers: Headers
        :return: None
        """

        request_method, path, http_version = request_info

        # Client requested custom text/event-stream page created by Django Quik.
        if path.startswith(self.refresh_path):
            return self.serve_refresh_event_page(stream_client)

        http_version = 'HTTP/1.0'  # Use HTT                http_version P/1.0 for easy parsing. Use single connection per page.
        header_bytes_to_proxy = build_header_bytes((request_method, path, http_version), headers)

        # Create new socket connection for each new request.
        sock_proxy = socket.create_connection((self.configuration.host, self.configuration.proxy_port))
        stream_proxy = Stream(sock_proxy)
        stream_proxy.write_chunk(header_bytes_to_proxy)

        threads = []
        # Listen client body in new thread and send received data to django server.
        client_to_django_server_send_thread = threading.Thread(
            target=self.send_data_client_to_django_server,
            args=(stream_client, stream_proxy)
        )
        client_to_django_server_send_thread.daemon = True
        client_to_django_server_send_thread.start()
        threads.append(client_to_django_server_send_thread)

        # Listen django server in new thread and send data to client including header and body.
        django_to_client_thread = threading.Thread(
            target=self.send_data_django_server_to_client,
            args=(stream_proxy, stream_client)
        )
        django_to_client_thread.daemon = True
        django_to_client_thread.start()
        threads.append(django_to_client_thread)

        # Wait for threads to complete.
        for thread in threads:
            thread.join()
