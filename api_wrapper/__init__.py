# API Wrapper Package

from api_wrapper.api_wrapper import app

# Import the main functions from api_client instead of a non-existent APIClient class
from api_wrapper.api_client import (
    generate_content_direct,
    test_hitl_workflow_sync,
    test_hitl_workflow_async,
    handle_job_feedback
)

__all__ = [
    'app',
    'generate_content_direct',
    'test_hitl_workflow_sync',
    'test_hitl_workflow_async',
    'handle_job_feedback'
]
