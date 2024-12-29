import os
import subprocess
import sys

from types import ModuleType
from typing import Tuple, List, Optional

from django.apps import apps

from django_quik.loader import load_template_dirs

MAPPING_FILENAME = 'tailwind.mapping'


def generate_tailwind_config_file(settings_module: ModuleType):
    tailwind_config = '''
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [],
  theme: {
    extend: {},
  },
  plugins: [],
}
'''

    dirs_to_watch = []
    for app_config in apps.get_app_configs():
        module_path_list = app_config.module.__path__

        # Loop through module path list
        for module_path in module_path_list:
            # Only watch project modules.
            if module_path.startswith(sys.prefix):
                continue

            dirs_to_watch.append(module_path)

    dirs_to_watch.extend(load_template_dirs(settings_module))

    content_dir_patterns = []
    for watch_dir in dirs_to_watch:
        relative_watch_dir = os.path.relpath(watch_dir, os.getcwd())
        path_suffix = '/**/*.{html,js,py}'
        tailwind_match_pattern = f'./{relative_watch_dir}{path_suffix}'
        content_dir_patterns.append(tailwind_match_pattern)

    structured_content = '[\n'
    for idx, dir_pattern in enumerate(content_dir_patterns):
        structured_content += f'    "{dir_pattern}"'

        if idx < len(content_dir_patterns) - 1:
            structured_content += ',\n'

    structured_content += '\n  ]'

    tailwind_config = tailwind_config.replace('content: []', f'content: {structured_content}')

    if os.path.exists('tailwind.config.js'):
        answer = input('The file already exists. Override file? Enter y/N\n').lower()
        if not (answer == 'y' or answer == 'yes'):
            print('Aborting.')
            exit(0)

    with open('tailwind.config.js', 'w') as file:
        file.write(tailwind_config)

    print('The tailwind.config.js file was created.')

    if not os.path.exists(MAPPING_FILENAME):
        create_sample_mapping()
        print(f'Created {MAPPING_FILENAME}')
        print(f'You can add multiple mappings in {MAPPING_FILENAME}. Modify according to your needs.')


def create_sample_mapping() -> None:
    # Create new starting point to accept tailwindcss build commands.
    with open(MAPPING_FILENAME, 'w') as file:
        file.write('# You can add multiple mappings here. Modify according to your needs.\n')
        file.write('static/scss/style.scss static/css/style.css\n')
        file.write('static/scss/admin.scss static/css/admin.css\n')


def parse_mapping(content: str) -> List[Tuple[str, str]]:
    all_mappings = []

    for idx, line in enumerate(content.splitlines()):
        if line.strip().startswith('#'):
            continue

        # Split in and out file paths by whitespace.
        mappings = line.split(" ")
        if len(mappings) < 2:
            print(f'Warning: Invalid format in {MAPPING_FILENAME} line number: {idx}.')
            continue

        # Strip out double quotes containing white space in path
        path_in = mappings[0].replace('"', '')
        path_out = mappings[1].replace('"', '')
        all_mappings.append((path_in, path_out))

    return all_mappings


def build_command_line_from_mapping(mapping: List[Tuple[str, str]]) -> Optional[str]:
    if not mapping:
        return

    command = 'npx tailwindcss'
    # Construct in paths.
    in_parts = ' '.join(in_path for (in_path, out_path) in mapping)
    # Construct out paths.
    out_parts = ' '.join(out_path for (in_path, out_path) in mapping)

    # Build working command which watches tailwind css files and builds to output paths.
    command = f'{command} -i {in_parts} -o {out_parts} --watch'
    return command


def handle_tailwind_build() -> None:
    if not os.path.exists(MAPPING_FILENAME):
        # Create example mapping
        create_sample_mapping()
        print(
            f'The {MAPPING_FILENAME} file was created. Modify according to your needs. Skipping tailwind watch for now.\n\n'
        )
        return

    with open(MAPPING_FILENAME) as file:
        mappings = parse_mapping(file.read())

    valid_mappings = []
    for (file_in, file_out) in mappings:
        if not os.path.exists(file_out):
            print(f'The file {file_in} does not exist. Please fix the path or remove mapping from {MAPPING_FILENAME}\n')
            continue

        # Only append valid input files to mapping.
        valid_mappings.append((file_in, file_out))

    if len(valid_mappings) > 0:
        command_line = build_command_line_from_mapping(valid_mappings)
        subprocess.run(command_line.split(" "))
    else:
        print(f'No valid tailwind mappings were found in {MAPPING_FILENAME}.')
