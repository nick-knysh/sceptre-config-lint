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
from pathspec import PathSpec

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


def validate_template(filename, linter_options):
    cfn_args = [filename]
    if (linter_options):
        cfn_args.extend(linter_options.split(' '))
    (args, temple_filenames, formatter) = cfnlint.core.get_args_filenames(cfn_args)
    matches = list(cfnlint.core.get_matches(temple_filenames, args))
    error_msg = formatter.print_matches(matches, cfnlint.core.get_used_rules(), temple_filenames)
    exit_code = cfnlint.core.get_exit_code(matches, args.non_zero_exit_code)
    return exit_code, error_msg

def get_template_params(filename):
    return cfn_yaml.load(filename)['Parameters']

def get_config_data(config_filename, variables):
    return load_config(config_filename, variables)

def match_params(config_params, template_params):
    # get params set's diff
    config_params_set = set(config_params.keys())
    # print(f"config_params_set={config_params_set}")
    template_params_set = set(template_params.keys())
    # print(f"template_params_set={template_params_set}")
    conf_xtra_error = config_params_set - template_params_set
    tpl_xtra = template_params_set - config_params_set
    tpl_missing = []
    for miss in tpl_xtra:
        if 'Default' not in template_params.get(miss, {}):
            tpl_missing.append(miss)
    if conf_xtra_error or tpl_missing:
        errors = []
        if conf_xtra_error:
            errors.append(f"Unknown params in config: {conf_xtra_error}")
        if tpl_missing:
            errors.append(f"Missing template params: {tpl_missing}")
        return 1, '\n'.join(errors)
    else:
        return 0, None


def process_config(config_filename, variables_filename, project_home, linter_options, is_try_default_template_path=True, verbose: bool = False):
    try:
        config = get_config_data(config_filename, variables_filename)
        template_path = os.path.join(project_home, config['template_path'])
        rel_config_path = config_filename[len(project_home) + 1:]
        rel_template_path = template_path[len(project_home) + 1:]
        if verbose:
            print(f"-- Processing config file: {rel_config_path}\t|\t[template:{rel_template_path}]")
        if not os.path.exists(template_path) and is_try_default_template_path:
            alt_template_path = os.path.join(project_home, 'templates', config['template_path'])
            if os.path.exists(alt_template_path) and os.path.isfile(alt_template_path):
                template_path = alt_template_path
        template_exit_code, template_errors = validate_template(template_path, linter_options)
        # template_exit_code, template_errors = 0, ""
        params_exit_code, params_errors = match_params(
            config['parameters'], get_template_params(template_path)
        )
        exit_code = max(template_exit_code, params_exit_code)
        if exit_code != 0 and (template_errors or params_errors):
            errors = []
            if template_errors:
                errors.append(f"FAILED: >> template errors for {rel_template_path}:")
                errors.append(template_errors)
            if params_errors:
                errors.append(f"FAILED: >>> config params errors for {rel_config_path}:")
                errors.append(params_errors)
            return exit_code, '\n'.join(errors)
        else:
            return 0, "OK"
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

def list_files_recursively(root_dir, include_filters, skip_filters):
    file_list = []
    spec = PathSpec.from_lines("gitwildmatch", include_filters)
    skip_spec = PathSpec.from_lines("gitwildmatch", skip_filters)
    for root, dirs, files in os.walk(root_dir):
        for file_name in files:
            file_path = os.path.join(root, file_name)[len(root_dir) + 1:]
            # print("checking file: ", file_path)
            matches_includes = not spec or spec.match_file(str(file_path))
            if matches_includes and not (skip_spec and skip_spec.match_file(str(file_path))):
                file_list.append(file_path)
    return file_list


if __name__ == '__main__':
    CONFIG_DIR = 'config'
    VARIABLES_FILENAME = 'variables.yaml'

    parser = argparse.ArgumentParser(description="Parse parameters from a CloudFormation template and config file.")
    parser.add_argument("-v", "--verbose", default=False, action="store_true", required=False, help="Verbose mode.")
    parser.add_argument("-c", "--config", required=False, help="Relative path to selected config YAML file.")
    parser.add_argument("-s", "--skip", required=False, help="Comma-delimited Relative paths to skipped config YAML file.")
    parser.add_argument("-o", "--linter-options", required=False, help="cfn-lint options string")
    parser.add_argument("-ti", "--linter-ignore-options", required=False, help="cfn-lint options string")
    parser.add_argument("project_home", nargs=1, default=None, help="Path to the config YAML file with parameters.")
    import sys
    print(f"args={sys.argv[1:]}")
    args = parser.parse_args()
    print(f"..config={args.config}")
    print(f"..skip={args.skip}")
    print(f"..linter-options={args.linter_options}")
    print(f"..linter-ignore-options={args.linter_ignore_options}")
    print(f"project_home_dir: {args.project_home[0]}")
    config_filter = args.config
    project_home = args.project_home[0]
    variables_file = os.path.join(project_home, VARIABLES_FILENAME)
    variables = {}
    if os.path.exists(variables_file) and os.path.isfile(variables_file):
        variables = load_var_file(variables_file)
    comp_exit_code = 0
    if not os.path.exists(os.path.join(project_home, CONFIG_DIR)):
        print("no config folder to process")
        sys.exit(0)
    skip_files = ['**/config.yaml']
    if args.skip:
        skip_files.extend(args.skip.split(','))
    configs = list_files_recursively(
        os.path.join(project_home, CONFIG_DIR),
        config_filter.split(',') if config_filter else ['**/*.yaml', '**/*.yml'],
        skip_files
    )

    for config_path in configs:
        # print(f"Validating config: {config_path}")
        comp_exit_code, error_msg = process_config(
            os.path.join(project_home, 'config', config_path), 
            variables, 
            project_home, 
            " ".join(list(filter(None, ["-i " + args.linter_ignore_options if args.linter_ignore_options else None, args.linter_options]))), 
            is_try_default_template_path=True,
            verbose=args.verbose
        )
        if comp_exit_code > 0:
            print(f'\n[!] Validation failed for [{config_path}] with following errors:')
            print(error_msg)
        else:
            if error_msg and args.verbose:
                print(error_msg)

    print(f"configs checked: {len(configs)}")
    sys.exit(comp_exit_code)


