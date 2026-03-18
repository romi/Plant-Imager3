# Remote System and Package Update Utility.

This module provides a robust framework for managing and updating Python packages across multiple remote servers via SSH.
It automates the process of pulling Git updates, managing local stashes, and performing editable pip installations within specific virtual or Conda environments.

## Requirements

Some non-standard packages are required:

- click
- fabric

You may install them with:
```shell
pip install click fabric
```

## Key Features

- **Multi-host Parallelization**: Utilizes thread pools to connect to and update multiple servers concurrently, significantly reducing maintenance time.
- **Environment Awareness**: Supports activation of specific Python environments (Conda, venv, or system) before performing package operations.
- **Git Workflow Automation**: Handles fetching, branch switching, pulling, and temporary stashing of local changes to ensure a clean update state.
- **Configuration-Driven**: Processes updates based on a simple CSV-formatted configuration file
  defining host URIs, branches, and environment paths.
- **Comprehensive Reporting**: Provides a detailed execution report at the end of the process, categorizing successes, warnings, and failures for each host.

## Usage Examples

To run the updater from the command line, provide a CSV configuration file:

```shell
python system_updater.py --config servers.csv --workers 5
```

The CSV format should follow:
```csv
ssh://user@host:port/path/to/repo,branch_name,subpackage_folder,env_type:env_path
```

See CSV examples in the `scripts` directory: `update_config.csv` & `update_config_dev.csv`.