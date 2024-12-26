import os
import sys
import re
import threading
from time import sleep

from typing import Tuple

from . import LOGO
from .config import Configuration
from .loader import (
    load_manage_py,
    load_settings_module,
    load_settings_module_path,
    load_valid_watch_dirs
)
from .server import WebServer

DJANGO_QUIK_ADDRESS = ('127.0.0.1', 8000)
DJANGO_PROXY_PORT = 8001


def run_blocking_proxy_server(configuration: Configuration):
    # Give some time to boot Django server.
    sleep(2)

    # Start proxy web server.
    web_server = WebServer(configuration)
    web_server.listen()


def override_run_server_args() -> Tuple[str, int, int]:
    # Default host for both Django Quik and Django's development server.
    host = DJANGO_QUIK_ADDRESS[0]
    quik_serve_port = DJANGO_QUIK_ADDRESS[1]
    django_serve_port = DJANGO_PROXY_PORT

    # Modify django quik equivalent python manage.py runserver to python manage.py runserver x.x.x.x:port
    if len(sys.argv) == 2:
        # No binding address is specified, using default binding host and port for serving Django's
        # development server.
        sys.argv.append(f'127.0.0.1:{django_serve_port}')

    else:
        # Search for binding address and replace with different_one.
        for i in range(2, len(sys.argv)):
            django_custom_address_pattern = r"^\d{1,3}(\.\d{1,3}){3}:\d{1,5}$"
            match_result = re.match(django_custom_address_pattern, sys.argv[i])

            if match_result:
                bind_address = sys.argv[i]
                # User assigned host and port for Django Quik
                host, quik_serve_port = bind_address.split(':')

                # Swap ports so Django Quik can serve to the user assigned port.
                if int(quik_serve_port) == int(django_serve_port):
                    quik_serve_port, django_serve_port = int(django_serve_port), int(quik_serve_port)

                # Replace command line argument where host and port is specified.
                sys.argv[i] = f'{host}:{django_serve_port}'

    return host, quik_serve_port, django_serve_port


def is_cli_running() -> bool:
    return os.environ.get('CLI_RUNNING', '0') == '1'


def set_cli_running_state() -> None:
    os.environ.setdefault('CLI_RUNNING', '1')


def handle_cli():
    """
    This function is executed from the command line and is called multiple times by Django for reloading the project.
    :return:
    """

    if not is_cli_running():
        print(LOGO)

    # Set PYTHON_PATH as the current working directory.
    sys.path.insert(0, os.getcwd())

    try:
        manage_py = load_manage_py()
    except ImportError:
        print("Failed to import manage.py file. Are you sure manage.py file exists?")
        exit(1)

    settings_module_path = load_settings_module_path(manage_py)
    if not settings_module_path:
        print('Could not find django settings module. It is set in DJANGO_SETTINGS_MODULE environment variable?')
        exit(1)

    try:
        settings_module = load_settings_module(settings_module_path)
    except ImportError:
        print(f'Could not load settings: {settings_module_path}')
        exit(1)

    if hasattr(manage_py, 'main'):
        # Modify run server arguments.
        if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
            host, django_quik_port, django_server_port = override_run_server_args()

            if not is_cli_running():
                serve_address = f'http://{host}:{django_quik_port}'
                print(f'Starting Django Quik development server at: {serve_address}')
                print('Django Quik will proxy forward your requests to Django\'s development server.')
                print('\n')

                # Create configurations
                configuration = Configuration(
                    host='0.0.0.0',
                    port=8000,
                    proxy_port=django_server_port,
                    watch_dirs=load_valid_watch_dirs(settings_module)
                )

                # Run proxy server in background thread.
                thread = threading.Thread(target=run_blocking_proxy_server, args=(configuration,))
                thread.daemon = True
                thread.start()

        set_cli_running_state()
        manage_py.main()
    else:
        print('The main() function is missing from manage.py file.')
        exit(1)
