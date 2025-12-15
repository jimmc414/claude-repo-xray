"""
Config loader for repo-xray.

Handles loading configuration from files, merging with CLI overrides,
and providing default configuration.
"""

import json
import os
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, Optional


# Default configuration - all sections enabled
DEFAULT_CONFIG = {
    "_version": "1.0",

    "analysis": {
        "skeleton": True,
        "complexity": True,
        "git": True,
        "imports": True,
        "calls": True,
        "side_effects": True,
        "tests": True,
        "tech_debt": True,
        "types": True,
        "decorators": True,
        "author_expertise": True,
        "commit_sizes": True,
    },

    "sections": {
        "summary": True,
        "prose": True,
        "mermaid": True,
        "architectural_pillars": True,
        "maintenance_hotspots": True,
        "complexity_hotspots": True,
        "critical_classes": {
            "enabled": True,
            "count": 10,
        },
        "data_models": True,
        "logic_maps": {
            "enabled": True,
            "count": 5,
        },
        "import_analysis": True,
        "layer_details": True,
        "git_risk": True,
        "coupling": True,
        "freshness": True,
        "side_effects": True,
        "side_effects_detail": True,
        "entry_points": True,
        "environment_variables": True,
        "hazards": True,
        "test_coverage": True,
        "tech_debt_markers": True,
        "verify_imports": True,
        "signatures": True,
        "state_mutations": True,
        "verify_commands": True,
        "persona_map": True,
        "explain": True,
    },

    "output": {
        "format": "markdown",
        "relative_paths": True,
    },
}


def get_default_config() -> Dict[str, Any]:
    """Return a copy of the default configuration with all sections enabled."""
    import copy
    return copy.deepcopy(DEFAULT_CONFIG)


def load_config(config_path: Optional[str] = None, target_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from file, falling back to defaults.

    Search order:
    1. Explicit config_path if provided
    2. .xray.json in target directory
    3. Default configuration (all enabled)

    Args:
        config_path: Explicit path to config file
        target_dir: Target directory to check for .xray.json

    Returns:
        Configuration dictionary
    """
    config = get_default_config()

    # Try explicit config path first
    if config_path:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                user_config = json.load(f)
            config = _merge_configs(config, user_config)
            return config
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")

    # Try .xray.json in target directory
    if target_dir:
        local_config = os.path.join(target_dir, '.xray.json')
        if os.path.exists(local_config):
            with open(local_config, 'r') as f:
                user_config = json.load(f)
            config = _merge_configs(config, user_config)
            return config

    # Return defaults
    return config


def _merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge override config into base config.

    Override values replace base values. Nested dicts are merged recursively.
    """
    import copy
    result = copy.deepcopy(base)

    for key, value in override.items():
        if key.startswith('_'):
            # Skip metadata keys like _version, _comment
            continue
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def merge_cli_overrides(config: Dict[str, Any], args: Namespace) -> Dict[str, Any]:
    """
    Apply CLI flag overrides to configuration.

    CLI flags take precedence over config file settings.
    Supports both positive flags (--mermaid) and negative flags (--no-mermaid).

    Args:
        config: Base configuration dictionary
        args: Parsed command line arguments

    Returns:
        Configuration with CLI overrides applied
    """
    import copy
    result = copy.deepcopy(config)

    # Map CLI args to config paths
    # Analysis switches
    analysis_map = {
        'skeleton': 'skeleton',
        'complexity': 'complexity',
        'git': 'git',
        'imports': 'imports',
        'calls': 'calls',
        'side_effects': 'side_effects',
        'tests': 'tests',
        'tech_debt': 'tech_debt',
        'types': 'types',
        'decorators': 'decorators',
        'author_expertise': 'author_expertise',
        'commit_sizes': 'commit_sizes',
    }

    # Section switches (simple boolean)
    section_map = {
        'mermaid': 'mermaid',
        'priority_scores': ['architectural_pillars', 'maintenance_hotspots'],  # Maps to two sections
        'hazards': 'hazards',
        'data_models': 'data_models',
        'entry_points': 'entry_points',
        'side_effects_detail': 'side_effects_detail',
        'verify_imports': 'verify_imports',
        'layer_details': 'layer_details',
        'prose': 'prose',
        'signatures': 'signatures',
        'state_mutations': 'state_mutations',
        'verify_commands': 'verify_commands',
        'explain': 'explain',
        'persona_map': 'persona_map',
    }

    # Section switches with parameters
    param_section_map = {
        'inline_skeletons': 'critical_classes',
        'logic_maps': 'logic_maps',
    }

    # Apply analysis overrides
    for arg_name, config_key in analysis_map.items():
        value = getattr(args, arg_name, None)
        if value is not None:
            result['analysis'][config_key] = value
        # Check for --no-{arg} style
        no_value = getattr(args, f'no_{arg_name}', None)
        if no_value:
            result['analysis'][config_key] = False

    # Apply simple section overrides
    for arg_name, config_key in section_map.items():
        value = getattr(args, arg_name, None)
        if value is not None and value is not False:
            if isinstance(config_key, list):
                # Maps to multiple sections (e.g., priority_scores)
                for key in config_key:
                    result['sections'][key] = True
            else:
                result['sections'][config_key] = True
        # Check for --no-{arg} style
        no_value = getattr(args, f'no_{arg_name}', None)
        if no_value:
            if isinstance(config_key, list):
                for key in config_key:
                    result['sections'][key] = False
            else:
                result['sections'][config_key] = False

    # Apply parameterized section overrides
    for arg_name, config_key in param_section_map.items():
        value = getattr(args, arg_name, None)
        if value is not None:
            if isinstance(result['sections'][config_key], dict):
                result['sections'][config_key]['enabled'] = True
                result['sections'][config_key]['count'] = value
            else:
                result['sections'][config_key] = {'enabled': True, 'count': value}
        # Check for --no-{arg} style
        no_value = getattr(args, f'no_{arg_name}', None)
        if no_value:
            if isinstance(result['sections'][config_key], dict):
                result['sections'][config_key]['enabled'] = False
            else:
                result['sections'][config_key] = False

    # Apply output format override
    if hasattr(args, 'output') and args.output:
        result['output']['format'] = args.output

    return result


def get_active_analyses(config: Dict[str, Any]) -> list:
    """
    Get list of active analysis types from config.

    Returns:
        List of analysis names that are enabled
    """
    return [name for name, enabled in config.get('analysis', {}).items() if enabled]


def is_section_enabled(config: Dict[str, Any], section_name: str) -> bool:
    """
    Check if a section is enabled in the config.

    Handles both simple boolean sections and dict sections with 'enabled' key.

    Args:
        config: Configuration dictionary
        section_name: Name of the section to check

    Returns:
        True if section is enabled, False otherwise
    """
    sections = config.get('sections', {})
    section = sections.get(section_name)

    if section is None:
        return False
    if isinstance(section, bool):
        return section
    if isinstance(section, dict):
        return section.get('enabled', True)
    return bool(section)


def get_section_param(config: Dict[str, Any], section_name: str, param: str, default: Any = None) -> Any:
    """
    Get a parameter value from a section config.

    Args:
        config: Configuration dictionary
        section_name: Name of the section
        param: Parameter name to retrieve
        default: Default value if not found

    Returns:
        Parameter value or default
    """
    sections = config.get('sections', {})
    section = sections.get(section_name)

    if isinstance(section, dict):
        return section.get(param, default)
    return default


def generate_config_template() -> str:
    """
    Generate a JSON config template string for --init-config.

    Returns:
        Pretty-printed JSON config string
    """
    config = get_default_config()
    config['_comment'] = "repo-xray configuration. Set sections to false to disable them."
    return json.dumps(config, indent=2)
