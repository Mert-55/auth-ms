# Tests for auth-ms

This directory contains unit tests for the auth-ms application.

## Setup

The tests require the main application dependencies to be installed. Since there's no `requirements.txt` in the root directory, you'll need to install the dependencies manually or set up a virtual environment with the project dependencies.

## Running Tests

Once dependencies are installed:

```bash
pytest tests/ -v
```

## Test Coverage

The test suite includes:

- **test_user_logic.py**: Unit tests for the `api/endpoints/user_logic.py` module
  - Name change validation (cooldown, uniqueness)
  - Email change validation (deliverability, uniqueness, verification reset)
  - Password change handling
  - Enable/disable user restrictions (self-modification prevention)
  - Admin status change restrictions (self-modification prevention)
  - Profile field updates

## Test Approach

Tests use lightweight mocks and fakes to avoid requiring actual database or Redis infrastructure:

- Mock user and session objects
- Patched database access functions
- Mocked email deliverability checks
- Isolated testing of business logic without framework overhead

## Development Dependencies

See `requirements-dev.txt` for testing dependencies:
- pytest
- pytest-asyncio
