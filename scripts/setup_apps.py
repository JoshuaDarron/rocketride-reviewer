#!/usr/bin/env python3
"""Interactive setup helper for RocketRide PR Reviewer GitHub Apps.

Walks the user through creating and configuring the three required GitHub Apps
(claude-reviewer, gpt-reviewer, gemini-reviewer) and outputs the repository
secrets they need to add.

Usage:
    python scripts/setup_apps.py           # Interactive setup
    python scripts/setup_apps.py --verify  # Verify existing app credentials
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# App definitions: name, bot username, description
APPS = [
    {
        "name": "claude-reviewer",
        "bot_username": "claude-reviewer[bot]",
        "description": "Claude AI code reviewer (also used for aggregation)",
        "app_id_secret": "CLAUDE_APP_ID",
        "private_key_secret": "CLAUDE_APP_PRIVATE_KEY",
    },
    {
        "name": "gpt-reviewer",
        "bot_username": "gpt-reviewer[bot]",
        "description": "GPT AI code reviewer",
        "app_id_secret": "GPT_APP_ID",
        "private_key_secret": "GPT_APP_PRIVATE_KEY",
    },
    {
        "name": "gemini-reviewer",
        "bot_username": "gemini-reviewer[bot]",
        "description": "Gemini AI code reviewer",
        "app_id_secret": "GEMINI_APP_ID",
        "private_key_secret": "GEMINI_APP_PRIVATE_KEY",
    },
]

REQUIRED_PERMISSIONS = {
    "Pull requests": "Read & Write",
    "Issues": "Read & Write",
    "Contents": "Read",
}

REQUIRED_EVENTS = [
    "Pull request",
    "Issue comment",
    "Pull request review comment",
]

API_KEY_SECRETS = [
    ("OPENAI_API_KEY", "OpenAI API key for GPT reviewer"),
    ("ANTHROPIC_API_KEY", "Anthropic API key for Claude reviewer and aggregator"),
    ("GOOGLE_API_KEY", "Google AI API key for Gemini reviewer"),
]


def print_header(text: str) -> None:
    """Print a formatted section header."""
    width = max(len(text) + 4, 60)
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)
    print()


def print_step(number: int, text: str) -> None:
    """Print a numbered step."""
    print(f"  {number}. {text}")


def print_permissions() -> None:
    """Print the required permissions table."""
    print("  Required permissions:")
    for perm, level in REQUIRED_PERMISSIONS.items():
        print(f"    - {perm}: {level}")
    print()


def print_events() -> None:
    """Print the required event subscriptions."""
    print("  Required event subscriptions:")
    for event in REQUIRED_EVENTS:
        print(f"    - {event}")
    print()


def prompt_yes_no(message: str) -> bool:
    """Prompt for a yes/no answer."""
    while True:
        response = input(f"  {message} [y/n]: ").strip().lower()
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("  Please enter 'y' or 'n'.")


def prompt_input(message: str) -> str:
    """Prompt for user input."""
    return input(f"  {message}: ").strip()


def setup_interactive() -> None:
    """Run the interactive setup flow."""
    print_header("RocketRide PR Reviewer - GitHub App Setup")

    print("This script will guide you through creating the three GitHub Apps")
    print("required for the RocketRide PR Reviewer action.")
    print()
    print("Each app posts reviews under its own identity, so you need three")
    print("separate GitHub Apps installed on your repository.")
    print()
    print("Before starting, make sure you have admin access to the GitHub")
    print("organization or user account where you want to install the apps.")
    print()

    if not prompt_yes_no("Ready to begin?"):
        print("\nSetup cancelled.")
        sys.exit(0)

    collected: dict[str, dict[str, str]] = {}

    for i, app in enumerate(APPS, start=1):
        print_header(f"App {i}/3: {app['name']}")

        print(f"  Create a new GitHub App named: {app['name']}")
        print(f"  Description: {app['description']}")
        print()

        print_step(1, "Go to: https://github.com/settings/apps/new")
        print_step(2, f"Set the GitHub App name to: {app['name']}")
        print_step(
            3,
            "Set the Homepage URL to your repository URL "
            "(or https://github.com/your-org/your-repo)",
        )
        print_step(4, "Uncheck 'Active' under Webhook (not needed)")
        print()

        print_permissions()
        print_events()

        print_step(5, "Click 'Create GitHub App'")
        print_step(6, "Note the App ID displayed on the app settings page")
        print_step(
            7,
            "Under 'Private keys', click 'Generate a private key' "
            "and save the .pem file",
        )
        print_step(
            8,
            "Go to 'Install App' in the sidebar and install it on your repository",
        )
        print()

        input("  Press Enter when you have completed these steps...")
        print()

        app_id = prompt_input(f"Enter the App ID for {app['name']}")
        if not app_id.isdigit():
            print(f"  Warning: App ID should be a number, got '{app_id}'")
            if not prompt_yes_no("Continue anyway?"):
                print("\nSetup cancelled.")
                sys.exit(1)

        private_key_path = prompt_input(
            f"Enter the path to the private key .pem file for {app['name']}"
        )
        pem_path = Path(private_key_path).expanduser()
        if not pem_path.exists():
            print(f"  Warning: File not found: {pem_path}")
            if not prompt_yes_no("Continue anyway?"):
                print("\nSetup cancelled.")
                sys.exit(1)
        elif pem_path.suffix != ".pem":
            print(f"  Warning: Expected a .pem file, got: {pem_path.name}")
        else:
            print(f"  Found: {pem_path}")

        collected[app["name"]] = {
            "app_id": app_id,
            "private_key_path": str(pem_path),
            "app_id_secret": app["app_id_secret"],
            "private_key_secret": app["private_key_secret"],
        }

        print(f"\n  {app['name']} configured successfully.")

    # Summary
    print_header("Setup Complete - Repository Secrets")

    print("Add the following secrets to your GitHub repository:")
    print("  Settings > Secrets and variables > Actions > New repository secret")
    print()

    print("  API Key Secrets:")
    print("  " + "-" * 56)
    for secret_name, description in API_KEY_SECRETS:
        print(f"    {secret_name:<25} {description}")
    print()

    print("  GitHub App Secrets:")
    print("  " + "-" * 56)
    for app_name, info in collected.items():
        print(
            f"    {info['app_id_secret']:<25} "
            f"{info['app_id']} (App ID for {app_name})"
        )
        print(
            f"    {info['private_key_secret']:<25} "
            f"Contents of {info['private_key_path']}"
        )
    print()

    print(
        "  Total secrets to configure: " f"{len(API_KEY_SECRETS) + len(collected) * 2}"
    )
    print()

    # Print example workflow snippet
    print_header("Example Workflow Snippet")
    print("  Add this to .github/workflows/review.yml:")
    print()
    print("  - uses: your-org/rocketride-reviewer@main")
    print("    with:")
    for secret_name, _ in API_KEY_SECRETS:
        input_name = secret_name.lower()
        print(f"      {input_name}: ${{{{ secrets.{secret_name} }}}}")
    for app in APPS:
        for suffix in ("app_id", "app_private_key"):
            secret = f"{app['name'].replace('-', '_').upper()}_{suffix.upper()}"
            input_name = f"{app['name'].replace('-', '_')}_{suffix}"
            print(f"      {input_name}: ${{{{ secrets.{secret} }}}}")
    print()

    print("See .github/workflows/example-usage.yml for a complete example.")
    print()


def verify_apps() -> None:
    """Verify that existing GitHub App credentials are valid.

    Attempts to authenticate each app by generating an installation token.
    Requires PyGithub to be installed.
    """
    print_header("RocketRide PR Reviewer - Credential Verification")

    try:
        import jwt
    except ImportError:
        print("  Error: PyJWT is required for verification.")
        print("  Install it with: pip install PyJWT cryptography")
        sys.exit(1)

    try:
        import httpx
    except ImportError:
        print("  Error: httpx is required for verification.")
        print("  Install it with: pip install httpx")
        sys.exit(1)

    results: list[tuple[str, bool, str]] = []

    for app in APPS:
        print(f"  Checking {app['name']}...")

        app_id = prompt_input(f"Enter the App ID for {app['name']}")
        private_key_path = prompt_input(
            f"Enter the path to the private key .pem file for {app['name']}"
        )

        pem_path = Path(private_key_path).expanduser()
        if not pem_path.exists():
            results.append((app["name"], False, f"Key file not found: {pem_path}"))
            continue

        try:
            private_key = pem_path.read_text()
        except OSError as e:
            results.append((app["name"], False, f"Could not read private key: {e}"))
            continue

        # Generate a JWT for the GitHub App
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": app_id,
        }

        try:
            token = jwt.encode(payload, private_key, algorithm="RS256")
        except Exception as e:
            results.append((app["name"], False, f"JWT encoding failed: {e}"))
            continue

        # Try to authenticate with the GitHub API
        try:
            response = httpx.get(
                "https://api.github.com/app",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                actual_name = data.get("name", "unknown")
                results.append((app["name"], True, f"Authenticated as '{actual_name}'"))
            elif response.status_code == 401:
                results.append(
                    (
                        app["name"],
                        False,
                        "Auth failed (401). " "Check App ID and private key.",
                    )
                )
            else:
                results.append(
                    (
                        app["name"],
                        False,
                        f"Unexpected status {response.status_code}: "
                        f"{response.text[:200]}",
                    )
                )
        except httpx.HTTPError as e:
            results.append((app["name"], False, f"HTTP request failed: {e}"))

    # Print results
    print_header("Verification Results")

    all_passed = True
    for name, success, message in results:
        status = "PASS" if success else "FAIL"
        if not success:
            all_passed = False
        print(f"  [{status}] {name}: {message}")

    print()
    if all_passed:
        print("  All apps verified successfully.")
    else:
        print("  Some apps failed verification. Check the errors above.")
        sys.exit(1)


def main() -> None:
    """Entry point for the setup script."""
    parser = argparse.ArgumentParser(
        description="Setup helper for RocketRide PR Reviewer GitHub Apps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/setup_apps.py           # Interactive setup\n"
            "  python scripts/setup_apps.py --verify  # Verify existing credentials\n"
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing GitHub App credentials instead of running setup",
    )

    args = parser.parse_args()

    if args.verify:
        verify_apps()
    else:
        setup_interactive()


if __name__ == "__main__":
    main()
