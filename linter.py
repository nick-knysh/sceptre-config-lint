from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlparse
import cfnlint.core
import sys
import argparse

import requests
import yaml
from jinja2 import Template
from cfnlint.decode import cfn_yaml

# methods:
# load_config, get_local_content, get_url_content, get_content
# are from sceptre project: https://github.com/Sceptre/sceptrelint/blob/main/pre_commit_hooks/util.py


def load_config(config_path: str, variables: dict = dict) -> Any:
    """
    Produce a Python object (usually dict-like) from the config file
    at `config_path`

    :param config_path: path to config file, can be absolute or relative to
                        working directory
    :return: Python object representing structure of config file
    """

    # Let YAML handle tags naively
    def default_constructor(loader: Any, tag_suffix: Any, node: Any) -> str:
        return tag_suffix + ' ' + node.value
    yaml.FullLoader.add_multi_constructor('', default_constructor)

    with open(config_path, encoding='utf-8') as new_file:
        # Load template with blanks for all variables
        template = Template(new_file.read())
        return yaml.load(template.render(var=variables), Loader=yaml.FullLoader)


def get_local_content(path: str) -> list[str]:
    """
    Gets file contents from a file on the local machine
    :param path: The absolute path to a file
    The path can reference a file containing yaml or json content.
    The default is to assume json content.
    """
    try:
        filename, file_extension = os.path.splitext(path)
        with open(path, encoding='utf-8') as file:
            raw_content = file.read()
    except (OSError, TypeError) as e:
        raise e

    content = []
    if raw_content:
        if file_extension == '.yaml' or file_extension == '.yml':
            content = yaml.safe_load(raw_content)
        else:
            content = json.loads(raw_content)

    return content


def get_url_content(path: str) -> list[str]:
    """
    Gets file contents from a file at a URL location
    :param path: The URL reference to a file
    The path can reference a file containing yaml or json content.
    The default is to assume json content.
    """
    url = urlparse(path)
    filename, file_extension = os.path.splitext(url.path)
    try:
        response = requests.get(path)
        raw_content = response.text
        if response.status_code != requests.codes.ok:
            raise requests.exceptions.HTTPError(raw_content)
    except requests.exceptions.RequestException as e:
        raise e

    content = []
    if raw_content:
        if file_extension == '.yaml' or file_extension == '.yml':
            content = yaml.safe_load(raw_content)
        else:
            content = json.loads(raw_content)

    return content


def get_content(file: str) -> list[str]:

    if file.startswith('http'):
        content = get_url_content(file)
    else:
        content = get_local_content(file)

    return content


def load_var_file(file_path):
    """
    Load a YAML file containing variables and return a dictionary of
    the contents.

    :param file_path: Path to YAML file containing variables
    :return: Dictionary containing variables
    """
    with open(file_path, 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise exc


def validate_template(filename):
    (args, temple_filenames, formatter) = cfnlint.core.get_args_filenames([filename])
    matches = list(cfnlint.core.get_matches(temple_filenames, args))
    error_msg = formatter.print_matches(matches, cfnlint.core.get_used_rules(), temple_filenames)
    exit_code = cfnlint.core.get_exit_code(matches, args.non_zero_exit_code)
    return exit_code, error_msg

def get_template_params(filename):
    return cfn_yaml.load(filename)['Parameters']

def get_config_data(config_filename, variables):
    config = load_config(config_filename, variables)
    return config

def match_params(config_params, template_params):
    # get params set's diff
    config_params_set = set(config_params.keys())
    template_params_set = set(template_params.keys())
    conf_xtra_error = config_params_set - template_params_set
    tpl_xtra = config_params_set - template_params_set
    tpl_missing = []
    for miss in tpl_xtra:
        if 'Default' not in template_params[miss]:
            tpl_missing.append(miss)
    if conf_xtra_error or tpl_missing:
        errors = []
        if conf_xtra_error:
            errors.append(f"Following config params are not present in the template: {conf_xtra_error}")
        if tpl_missing:
            errors.append(f"Following template params value are missing: {tpl_missing}")
        return 1, '\n'.join(errors)
    else:
        return 0, None


def process_config(config_filename, variables_filename, project_home, is_try_default_template_path=True):
    try:
        config = get_config_data(config_filename, variables_filename)
        template_path = os.path.join(project_home, config['template_path'])
        if not os.path.exists(template_path) and is_try_default_template_path:
            alt_template_path = os.path.join(project_home, 'templates', config['template_path'])
            if os.path.exists(alt_template_path) and os.path.isfile(alt_template_path):
                template_path = alt_template_path
        template_exit_code, template_errors = validate_template(template_path)
        params_exit_code, params_errors = match_params(
            get_template_params(template_path), get_template_params(template_path)
        )
        exit_code = max(template_exit_code, params_exit_code)
        if exit_code != 0:
            errors = []
            if template_errors:
                errors.append(template_errors)
            if params_errors:
                errors.append(params_errors)
            return exit_code, '\n'.join(errors)
        else:
            return 0, None
    except Exception as e:
        return 1, f"Failed to process config file: {config_filename}: {e}"



def collect_configs(config_directory):
    file_paths = []

    def collect_files_in(directory):
        for foldername, subfolders, filenames in os.walk(directory):
            for subfolder in subfolders:
                collect_files_in(subfolder)
            for filename in filenames:
                if filename.endswith('.yaml') or filename.endswith('.yml') and filename != 'config.yaml':
                    file_path = os.path.join(foldername, filename)
                    file_paths.append(os.path.relpath(file_path, config_directory))

    collect_files_in(config_directory)
    return file_paths


if __name__ == '__main__':
    CONFIG_DIR = 'config'
    VARIABLES_FILENAME = 'variables.yaml'

    parser = argparse.ArgumentParser(description="Parse parameters from a CloudFormation template and config file.")
    parser.add_argument("-c", "--config", required=False, help="Relative path to selected config YAML file.")
    parser.add_argument("-s", "--skip", required=False, help="Comma-delimited Relative paths to skipped config YAML file.")
    parser.add_argument("project_home", nargs=1, default=None, help="Path to the config YAML file with parameters.")
    args = parser.parse_args()
    print(f"project_home_dir: {args.project_home[0]}")
    config_filter = args.config
    project_home = args.project_home[0]
    variables_file = os.path.join(project_home, VARIABLES_FILENAME)
    variables = {}
    if os.path.exists(variables_file) and os.path.isfile(variables_file):
        variables = load_var_file(variables_file)
    comp_exit_code = 0
    if os.path.exists(os.path.join(project_home, CONFIG_DIR)):
        print("no config folder to process")
        sys.exit(0)
    configs = collect_configs(os.path.join(project_home, CONFIG_DIR))
    if config_filter:
        configs = list(filter(lambda x: x.endswith(config_filter), configs))
    skip_files = ['config.yaml']
    if args.skip:
        skip_files.extend(args.skip.split(','))
    print(skip_files)
    for config_path in filter(lambda x: not (next(filter(lambda skip: x.endswith(skip), skip_files), False)), configs):
        # print(f"Validating config: {config_path}")
        comp_exit_code, error_msg = process_config(os.path.join(project_home, 'config', config_path), variables, project_home)
        if error_msg:
            print(f'\nValidation failed for [{config_path}] with following errors:')
            print(error_msg)
    sys.exit(comp_exit_code)


