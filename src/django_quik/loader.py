import importlib
import os
import sys

from types import ModuleType
from typing import List, Optional


def load_manage_py() -> ModuleType:
    """
    Load manage.py file form current working directory.

    :return: ModuleType
    """

    return importlib.__import__('manage')


def load_settings_module_path(manage_py_module: ModuleType) -> Optional[str]:
    """
    Load settings module by executing main function from manage.py file.

    :return: ModuleType
    """

    settings_module_path = os.environ.get('DJANGO_SETTINGS_MODULE')
    if settings_module_path:
        return settings_module_path

    cloned_args = sys.argv.copy()

    # Remove all command line arguments
    for i in range(1, len(sys.argv)):
        sys.argv.pop()

    # Add check argument which runs main function of manage.py file and load settings path in environment variable.
    sys.argv.append('check')

    if hasattr(manage_py_module, 'main'):
        manage_py_module.main()
        settings_module_path = os.environ.get('DJANGO_SETTINGS_MODULE')

    # Pop check argument.
    sys.argv.pop()

    # Put back actual arguments back.
    for i in range(1, len(cloned_args)):
        sys.argv.append(cloned_args[i])

    return settings_module_path


def load_settings_module(settings_module_path: str) -> ModuleType:
    """
    Load settings.py file form current working directory.
    :return: ModuleType
    """

    return importlib.import_module(settings_module_path)


def load_template_dirs(settings_module: ModuleType) -> List[str]:
    """
    Load all the template directories. APP_DIRS is not supported yet.
    :return: ModuleType
    """

    if not hasattr(settings_module, 'TEMPLATES'):
        return []

    templates = getattr(settings_module, 'TEMPLATES')
    if type(templates) is not list:
        print('Warn: Templates specified is not list.')
        return []

    template_dirs = []

    # Loop through TEMPLATES list of the settings.
    for template in templates:
        # If items of TEMPLATES is not dictionary, skip.
        if not type(template) is dict:
            print('Warn: Template specified is not dict.')
            continue

        # Get DIRS from TEMPLATES array.
        dirs = template.get('DIRS')
        if type(dirs) is not list:
            continue

        # Add all the specified directories in the list.
        template_dirs.extend(dirs)

    return template_dirs


def load_static_files_dirs(settings_module: ModuleType) -> List[str]:
    """
    Load all the directory paths having static files.
    :param settings_module:
    :return:
    """

    static_file_dirs = []

    if hasattr(settings_module, 'STATIC_ROOT'):
        static_file_dirs.append(settings_module.STATIC_ROOT)

    if hasattr(settings_module, 'STATICFILES_DIRS'):
        static_file_dirs.extend(settings_module.STATICFILES_DIRS)

    return static_file_dirs


def load_dirs_to_watch(settings_module: ModuleType) -> List[str]:
    """
    Load all the dirs which requires reloading the page.
    :return: ModuleType
    """

    dirs = []

    # Load all parent template directory paths from settings.
    template_dirs = load_template_dirs(settings_module)
    dirs.extend(template_dirs)

    # Load all the static file directory paths.
    static_file_dirs = load_static_files_dirs(settings_module)
    dirs.extend(static_file_dirs)

    return dirs


def load_valid_watch_dirs(settings_module: ModuleType):
    watch_dirs = []
    watch_dirs_from_settings = load_dirs_to_watch(settings_module)

    # Filter out non-existing directories.
    for watch_dir in watch_dirs_from_settings:
        if os.path.exists(watch_dir) and os.path.isdir(watch_dir):
            watch_dirs.append(watch_dir)

    return watch_dirs
