import os
import click
import urllib.parse
from dataclasses import dataclass
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from fabric import Connection
from invoke.exceptions import UnexpectedExit


# --- Data Structures ---

@dataclass
class Task:
    original_uri: str
    host_string: str  # user@host:port
    base_dir: str  # Remote base directory from URI
    branch: str
    package_subpath: str
    env_type: str  # 'venv', 'conda', 'system'
    env_path: str  # path or env name
    pip_options: str

    @property
    def full_remote_path(self):
        # Handle trailing slashes gracefully
        base = self.base_dir.rstrip('/')
        sub = self.package_subpath.lstrip('/')
        return f"{base}/{sub}"

    def __str__(self):
        return f"[{self.host_string}] {self.package_subpath} ({self.branch})"


# --- Configuration Parsing ---

def parse_config_line(line: str) -> Task:
    """Parses a single line of the CSV config."""
    parts = [p.strip() for p in line.split(',')]

    if len(parts) < 4:
        raise ValueError(f"Invalid config line format: {line}")

    # unpacking with optional pip options
    ssh_uri = parts[0]
    git_branch = parts[1]
    package_path = parts[2]
    env_context = parts[3]
    pip_opts = parts[4] if len(parts) > 4 else ""

    # Parse SSH URI
    parsed_uri = urllib.parse.urlparse(ssh_uri)
    if parsed_uri.scheme != 'ssh':
        raise ValueError(f"URI must start with ssh:// : {ssh_uri}")

    # Build Host String for Fabric (user@host:port)
    host_str = parsed_uri.hostname
    if parsed_uri.username:
        host_str = f"{parsed_uri.username}@{host_str}"
    if parsed_uri.port:
        host_str = f"{host_str}:{parsed_uri.port}"

    # Parse Environment Context
    if ':' in env_context:
        e_type, e_path = env_context.split(':', 1)
    else:
        # Default fallback if format is missing
        e_type, e_path = 'system', ''

    return Task(
        original_uri=ssh_uri,
        host_string=host_str,
        base_dir=parsed_uri.path,
        branch=git_branch,
        package_subpath=package_path,
        env_type=e_type.lower(),
        env_path=e_path,
        pip_options=pip_opts
    )


def group_tasks_by_host(config_path: str) -> Dict[str, List[Task]]:
    tasks_by_host = {}

    with open(config_path, 'r') as f:
        # Skip empty lines or comments
        lines = [l for l in f.readlines() if l.strip() and not l.strip().startswith('#')]

        for line in lines:
            try:
                task = parse_config_line(line)
                if task.host_string not in tasks_by_host:
                    tasks_by_host[task.host_string] = []
                tasks_by_host[task.host_string].append(task)
            except Exception as e:
                click.secho(f"Skipping invalid line: {line.strip()} -> {e}", fg='yellow')

    return tasks_by_host


# --- Core Logic ---

def get_activation_command(task: Task) -> str:
    """Generates the shell command to activate the python environment."""
    if task.env_type == 'conda':
        # Hardcoded base path as requested
        conda_base = "~/miniconda3"
        return f"source {conda_base}/etc/profile.d/conda.sh && conda activate {task.env_path}"

    elif task.env_type == 'venv':
        # Assumes standard venv structure
        activation_script = os.path.join(task.env_path, 'bin', 'activate')
        return f"source {activation_script}"

    # 'system' or unknown types return a no-op that always succeeds
    return "true"


def execute_task(conn: Connection, task: Task):
    """Executes the update sequence for a single package."""

    # 1. Navigate to directory
    with conn.cd(task.base_dir):
        click.echo(f"  -> Processing {task.base_dir} - {task.package_subpath} @ {task.host_string}...")

        # 2. Fetch latest remote info so we know about new branches
        conn.run("git fetch origin", hide=True)

        # 3. Check for tracked changes (ignore untracked files with -uno)
        status_res = conn.run("git status --porcelain -uno", hide=True, warn=True)
        is_dirty = bool(status_res.stdout.strip())

        # 4. Stash if dirty
        stashed = False
        if is_dirty:
            conn.run("git stash", hide=True)
            stashed = True
            click.echo("     (Stashed local changes)")

        try:
            # Determine current branch before doing anything
            current_branch_res = conn.run("git rev-parse --abbrev-ref HEAD", hide=True, warn=True)
            current_branch = current_branch_res.stdout.strip() if current_branch_res.ok else ""

            branch_changed = (current_branch != task.branch)

            # 5. Robust Checkout Logic
            branch_exists = conn.run(f"git rev-parse --verify {task.branch}", hide=True, warn=True).ok

            if branch_exists:
                conn.run(f"git checkout {task.branch}", hide=True)
            else:
                conn.run(f"git checkout -b {task.branch} --track origin/{task.branch}", hide=True)
                branch_changed = True  # Newly created branch means state changed

            # Record commit hash before pull
            before_hash = conn.run("git rev-parse HEAD", hide=True).stdout.strip()

            # 6. Pull latest updates
            conn.run(f"git pull origin {task.branch}", hide=True)

            # Record commit hash after pull
            after_hash = conn.run("git rev-parse HEAD", hide=True).stdout.strip()

            pull_changed = (before_hash != after_hash)

            if pull_changed or branch_changed:
                click.echo(f"     (Checked out and pulled updates for {task.branch})")
            else:
                click.echo(f"     (Already up-to-date on {task.branch})")

            # 7. Pop Stash (if we stashed)
            if stashed:
                pop_res = conn.run("git stash pop", hide=True, warn=True)
                if pop_res.failed:
                    click.secho(f"     WARNING: Git stash pop failed (conflict?) in {task.full_remote_path}",
                                fg='yellow')
                else:
                    click.echo("     (Restored stash)")

            # 8. Conditionally Pip Install
            if branch_changed or pull_changed:
                activate_cmd = get_activation_command(task)

                with conn.prefix(activate_cmd):
                    cmd = f"pip install -e {task.package_subpath} {task.pip_options}"
                    click.echo(f"     (Installing: {cmd})")
                    conn.run(cmd, hide=True)
            else:
                click.echo("     (No changes detected, skipping pip install)")

        except UnexpectedExit as e:
            # Re-raise to be caught by the host processor
            raise RuntimeError(f"Command failed: {e.result.command}\nStderr: {e.result.stderr}")


def process_host(host_string: str, tasks: List[Task]) -> List[str]:
    """
    Worker function running in a thread.
    Processes all tasks for a specific host sequentially.
    """
    logs = []

    try:
        # Connect to host
        # ForwardAgent=True is often useful for git pulls over SSH from the remote machine
        conn = Connection(host_string, forward_agent=True)
        logs.append(f"Successfully connected to {host_string}")

        for task in tasks:
            try:
                execute_task(conn, task)
                logs.append(f"[SUCCESS] {task.package_subpath}")
            except Exception as e:
                logs.append(f"[FAILURE] {task.package_subpath}: {str(e)}")
                # CRITICAL: Stop processing this host if one component fails?
                # Based on 'update system', usually dependencies matter.
                # We break here to prevent cascading errors.
                logs.append("Aborting remaining tasks for this host due to failure.")
                break

        conn.close()

    except Exception as e:
        logs.append(f"[CONNECTION ERROR] Could not connect or fatal error on {host_string}: {e}")

    return logs


# --- CLI Entry Point ---

@click.command()
@click.option('--config', '-c', required=True, type=click.Path(exists=True), help='Path to configuration CSV.')
@click.option('--workers', '-w', default=4, help='Number of parallel host connections.')
def main(config, workers):
    """
    System Update Tool.
    Updates git repositories and pip installs packages across multiple hosts via SSH.
    """
    click.secho("Parsing configuration...", fg='blue')
    tasks_by_host = group_tasks_by_host(config)

    if not tasks_by_host:
        click.secho("No valid tasks found.", fg='red')
        return

    click.echo(f"Found {len(tasks_by_host)} unique hosts to process.")

    # We store results to print them cleanly at the end
    results = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Map futures to hosts
        future_to_host = {
            executor.submit(process_host, host, tasks): host
            for host, tasks in tasks_by_host.items()
        }

        for future in as_completed(future_to_host):
            host = future_to_host[future]
            try:
                logs = future.result()
                results[host] = logs
            except Exception as exc:
                results[host] = [f"CRITICAL THREAD ERROR: {exc}"]

    # --- Final Report ---
    click.secho("\n=== Execution Report ===", fg='blue', bold=True)

    for host, logs in results.items():
        click.secho(f"\nHost: {host}", bold=True, underline=True)
        for log in logs:
            if "[FAILURE]" in log or "ERROR" in log:
                click.secho(log, fg='red')
            elif "[SUCCESS]" in log:
                click.secho(log, fg='green')
            elif "WARNING" in log:
                click.secho(log, fg='yellow')
            else:
                click.echo(log)


if __name__ == '__main__':
    main()