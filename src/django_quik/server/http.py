import socket

from copy import deepcopy
from collections import OrderedDict
from typing import (
    List,
    Tuple,
    Optional
)


class StreamReadException(Exception):
    """
    Occurs if failed to read stream from socket.
    """
    pass


class StreamWriteException(Exception):
    """
    Occurs if failed to write stream to socket.
    """
    pass


class Stream:
    """
    A class for reading, writing and restoring stream of bytes from socket.
    """

    def __init__(self, sock: socket.socket, buffer_size=1024):
        """
        Create new stream.
        :param sock: Socket
        :param buffer_size: Buffer size
        """

        self.sock = sock
        self.buffer_size = buffer_size
        self.restored_bytes = b''

    def read_chunk(self, buffer_size: int = None) -> bytes:
        """
        Read bytes from socket. Return restored bytes if present or read and return fresh bytes.
        :param buffer_size: Buffer size
        :return: bytes
        """

        # If there are existing bytes, return all those bytes.
        if len(self.restored_bytes) > 0:
            restored_bytes_cloned = deepcopy(self.restored_bytes)

            # Reset restored bytes.
            self.restored_bytes = b''
            return restored_bytes_cloned

        # Take default buffer size or buffer size passed as argument.
        current_buffer_size = buffer_size if buffer_size else self.buffer_size
        data = self.sock.recv(current_buffer_size)
        if len(data) == 0:
            raise StreamReadException('Stream is empty. Probably client disconnected.')

        return data

    def write_chunk(self, data: bytes) -> None:
        """
        Writes all the data to socket.

        :param data: bytes
        :return: None
        """
        try:
            self.sock.sendall(data)
        except socket.error:
            raise StreamWriteException('Writing to stream failed. Probably client disconnected.')

    def restore_bytes(self, data: bytes = None) -> None:
        """
        Use for restoring misread bytes back to the stream.
        :param data: bytes
        :return: None
        """
        self.restored_bytes += data

    def close(self) -> None:
        """
        Closes inner socket. If already closed, fails silently.
        :return:
        """

        try:
            self.sock.close()
        except socket.error:
            pass


def read_headers(stream: Stream) -> bytes:
    """
    Read headers from stream.

    :param stream: Stream
    :return: bytes
    """

    HEADER_END_BYTES = b'\r\n\r\n'
    buffer = b''

    # Keep reading headers in the buffer until double CRLF are found.
    # No header size limit is set. Might fill up RAM :/
    while True:
        buffer += stream.read_chunk()

        # Fill up buffer until there is data to compare with HEADER_END_BYTES.
        if len(buffer) < len(HEADER_END_BYTES):
            continue

        matched_index = buffer.find(HEADER_END_BYTES)
        if matched_index != -1:
            header_bytes = buffer[:matched_index]

            # Stream might have read bytes from the body too. So, restore back in the stream.
            # Also skip HEADER_END_BYTES
            misread_bytes = buffer[matched_index + len(HEADER_END_BYTES):]
            stream.restore_bytes(misread_bytes)
            return header_bytes


def extract_http_starting_header_info(line: str) -> Optional[Tuple[str, str, str]]:
    """
    Extracts starting header line of the HTTP request.
    :param line: Beginning header line
    :return: Optional (request_method, request_path, http_version)
    """

    values = line.split(' ')
    if len(values) >= 3:
        request_method = values[0]
        request_path = ' '.join(values[1:-1])
        http_version = values[-1]
        return request_method, request_path, http_version

    return None


def parse_headers(data: bytes) -> Tuple[Optional[Tuple[str, str, str]], OrderedDict[str, List[str]]]:
    """
    Parse raw header bytes and return the result.

    :param data: Raw header bytes.
    :return: request_method, path, http_version
    """

    headers = OrderedDict()
    header_lines = data.decode(errors='ignore').split('\r\n')

    for header_line in header_lines:
        # Simply ignore invalid header.
        if header_line.find(":") == -1:
            continue

        raw_key, raw_value = header_line.split(':', 1)
        key, value = raw_key.strip(), raw_value.strip()

        if headers.get(key):
            headers[key].append(value)
        else:
            headers[key] = [value]

    request_info = None
    if len(header_lines) > 0:
        request_info = extract_http_starting_header_info(header_lines[0])

    return request_info, headers


def header_value(headers: OrderedDict[str, List[str]], name: str) -> Optional[str]:
    """
    Header can have multiple values with same name. Extract only first found value.
    :param headers: Headers
    :param name: Header Name
    :return: Header value
    """

    for header in headers.keys():
        if header.lower() == name.lower():
            values = headers[header]
            if len(values) > 0:
                return values[0]

    return None


def modify_headers(headers: OrderedDict[str, List[str]], name: str, value: str) -> None:
    """
    Modify the provided header dictionary object. If the header is not present, adds new header with the given name and value.

    :param headers: Headers
    :param name: Header Name
    :param value: New value
    :return: None
    """

    is_found = False

    for header in headers.keys():
        if header.lower() == name.lower():
            headers[name] = [value]
            is_found = True

    if not is_found:
        headers[name] = [value]


def build_header_bytes(request_info: Tuple[str, str, str], headers: OrderedDict[str, List[str]]) -> bytes:
    """
    Create the header bytes from the request info and headers.

    :param request_info: (request_method, path, http_version)
    :param headers: Headers
    :return: bytes
    """

    data = f'{request_info[0]} {request_info[1]} {request_info[2]}\r\n'.encode(errors='ignore')

    for key, values in headers.items():
        for value in values:
            data += f'{key}: {value}\r\n'.encode(errors='ignore')

    data += b'\r\n'
    return data


def read_text_body(stream: Stream, content_length: int) -> str:
    """
    Read text body from stream as str.

    :param stream: Stream
    :param content_length: Content-Length
    :return: response body
    """

    buffer = b''
    read_size = 0
    while read_size < content_length:
        chunk = stream.read_chunk()
        buffer += chunk
        read_size += len(chunk)

    decoded = buffer.decode(errors='ignore')
    return decoded
