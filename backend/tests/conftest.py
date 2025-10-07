"""
pytest configuration and fixtures for integration tests.
"""

import subprocess
import time
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db


def pytest_sessionstart(session):
    """
    Hook that runs before the entire test session starts.
    Starts Docker Compose test database.
    """
    print("\n" + "=" * 60)
    print("STARTING DOCKER COMPOSE TEST DATABASE...")
    print("=" * 60)

    try:
        # Start Docker Compose
        result = subprocess.run(
            ["docker", "compose", "-f", "compose.test.yaml", "up", "-d"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("Docker Compose started successfully!")
        print(f"   Output: {result.stdout.strip()}")

        # Wait for database to be ready
        print("\nWaiting for database to be ready...")
        max_retries = 30
        retry_count = 0

        while retry_count < max_retries:
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    "compose.test.yaml",
                    "ps",
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
            )

            # Check if healthcheck passed
            healthcheck_result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    "employee_directory_test_db",
                ],
                capture_output=True,
                text=True,
            )

            if "healthy" in healthcheck_result.stdout:
                print(f"Database is ready! (took {retry_count} seconds)")
                break

            retry_count += 1
            time.sleep(1)
            print(f"   Retry {retry_count}/{max_retries}...")

        if retry_count >= max_retries:
            print("ERROR: Database failed to become ready in time!")
            raise Exception("Test database healthcheck timeout")

    except subprocess.CalledProcessError as e:
        print(f"ERROR: Error starting Docker Compose: {e}")
        print(f"   stderr: {e.stderr}")
        raise
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        raise


def pytest_sessionfinish(session, exitstatus):
    """
    Hook that runs after the entire test session finishes.
    Stops and removes Docker Compose test database.
    """
    print("\n" + "=" * 60)
    print("STOPPING DOCKER COMPOSE TEST DATABASE...")
    print("=" * 60)

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", "compose.test.yaml", "down"],
            check=True,
            capture_output=True,
            text=True,
        )
        print("Docker Compose stopped successfully!")
        print(f"   Output: {result.stdout.strip()}")
        print(f"   Exit status: {exitstatus}")

    except subprocess.CalledProcessError as e:
        print(f"ERROR: Error stopping Docker Compose: {e}")
        print(f"   stderr: {e.stderr}")
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")


@pytest.fixture(scope="session")
def test_db_url():
    """
    Provides the test database connection URL.
    """
    return "postgresql://test_user:test_password@localhost:5433/test_employee_directory"


@pytest.fixture(scope="session")
def test_db_engine(test_db_url):
    """
    Creates a SQLAlchemy engine for the test database.
    """
    engine = create_engine(test_db_url, echo=False)
    return engine


@pytest.fixture(scope="session")
def test_db_session(test_db_engine):
    """
    Creates a session factory for the test database.
    """
    TestSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_db_engine
    )
    return TestSessionLocal


@pytest.fixture(scope="session")
def client(test_db_session):
    """
    Creates a FastAPI TestClient with test database dependency override.
    """

    def override_get_db():
        db = test_db_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
