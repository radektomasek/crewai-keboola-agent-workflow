#!/usr/bin/env python3
"""
Unified CrewAI Content Generation Client

This script provides a unified interface for interacting with the CrewAI content generation API,
supporting both direct content generation and human-in-the-loop (HITL) workflows.

Usage:
    # Start a new job:
    python api_client.py --topic "Your Topic" [options]
    
    # Provide feedback or approval for an existing job:
    python api_client.py --job-id "your-job-id" [--approve | --feedback "Your feedback"]

Options:
    --topic TEXT            Topic for content generation (required for new jobs)
    --url TEXT              API URL (default: http://localhost:8888)
    --mode [direct|hitl]    Mode of operation (default: direct)
    --wait                  Wait for result instead of polling (only for direct mode)
    --webhook TEXT          Webhook URL for notifications (default: http://localhost:8889/webhook)
    --job-id TEXT           Job ID to provide feedback for (for existing jobs)
    --feedback TEXT         Feedback to provide if not approving (only for hitl mode)
    --approve               Approve content instead of providing feedback (only for hitl mode)
    --async                 Use asyncio for HITL workflow (more efficient)
    --no-webhook            Disable webhook notifications
"""

import argparse
import json
import requests
import sys
import time
import asyncio
import aiohttp
from datetime import datetime

# Constants
DEFAULT_API_URL = "http://localhost:8888"
DEFAULT_WEBHOOK_URL = "http://localhost:8889/webhook"


def generate_content_direct(topic, api_url, wait=False, webhook_url=None):
    """Generate content using the API wrapper without human approval"""
    print(
        f"Generating content on topic '{topic}' using direct mode (no human approval)..."
    )

    # Prepare the request payload
    payload = {
        "crew": "ContentCreationCrew",
        "inputs": {
            "topic": topic,
            "require_approval": False,  # Skip human approval
        },
        "wait": wait,  # Whether to wait for completion
    }

    # Add webhook URL if explicitly provided
    if webhook_url:
        payload["webhook_url"] = webhook_url
        print(f"Webhook notifications will be sent to: {webhook_url}")

    try:
        # Send the request to the API
        response = requests.post(
            f"{api_url}/kickoff",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        # Check if the request was successful
        if response.status_code == 200:
            result = response.json()

            if wait:
                # If wait=true, the result should contain the content directly
                print("\n" + "=" * 50)
                print(f"Content generated successfully!")
                print("=" * 50)

                if "result" in result and "content" in result["result"]:
                    print(f"\n{result['result']['content']}")
                else:
                    print(json.dumps(result, indent=2))
            else:
                # If wait=false, we need to poll for the result
                job_id = result.get("job_id")
                print(f"Job created with ID: {job_id}")
                print(f"Status: {result.get('status', 'unknown')}")
                
                if webhook_url:
                    print(f"\nWebhook notifications will be sent to: {webhook_url}")
                    print("You can monitor the job status through webhook notifications.")
                    print(f"To check job status manually: {api_url}/job/{job_id}")
                else:
                    if (
                        result.get("status") == "queued"
                        or result.get("status") == "processing"
                    ):
                        print("\nPolling for job completion...")
                        poll_until_complete(job_id, api_url)
                
                # Always show how to check status manually
                if not webhook_url:
                    print(f"\nTo check job status manually: {api_url}/job/{job_id}")

            return True
        else:
            print(f"Error: API returned status code {response.status_code}")
            print(response.text)
            return False

    except Exception as e:
        print(f"Error: {str(e)}")
        return False


def poll_until_complete(job_id, api_url, max_attempts=30, delay=2):
    """Poll the job status until it's completed or max attempts reached"""
    attempts = 0

    while attempts < max_attempts:
        try:
            response = requests.get(f"{api_url}/job/{job_id}")

            if response.status_code == 200:
                job_data = response.json()
                status = job_data.get("status")

                print(f"Job status: {status}")

                if status == "completed":
                    print("\n" + "=" * 50)
                    print(f"Content generated successfully!")
                    print("=" * 50)

                    if "result" in job_data and "content" in job_data["result"]:
                        print(f"\n{job_data['result']['content']}")
                    else:
                        print(json.dumps(job_data, indent=2))

                    return True
                elif status == "error":
                    print(f"Error: {job_data.get('error', 'Unknown error')}")
                    return False
                elif status == "pending_approval":
                    print(
                        "Job is waiting for human approval. This shouldn't happen with require_approval=false."
                    )
                    return False
            else:
                print(f"Error checking job status: {response.status_code}")
                print(response.text)
                return False

        except Exception as e:
            print(f"Error polling job status: {str(e)}")
            return False

        attempts += 1
        time.sleep(delay)

    print(f"Max polling attempts reached. Job may still be processing.")
    return False


def test_hitl_workflow_sync(
    topic, api_url, approve=False, feedback=None, webhook_url=None
):
    """Test the Human-in-the-Loop workflow using synchronous requests"""
    print(f"Starting content creation with HITL for topic: {topic}")

    # Prepare the request payload
    payload = {
        "crew": "ContentCreationCrew",
        "inputs": {"topic": topic, "require_approval": True},
    }

    # Add webhook URL if provided
    if webhook_url:
        payload["webhook_url"] = webhook_url
        print(f"Webhook notifications will be sent to: {webhook_url}")

    print(f"Sending request to {api_url}/kickoff...")

    response = requests.post(f"{api_url}/kickoff", json=payload)

    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
        return False

    job_data = response.json()
    job_id = job_data.get("job_id")

    print(f"Job created with ID: {job_id}")
    print(f"Initial status: {job_data.get('status')}")
    
    if webhook_url:
        print(f"\nWebhook notifications will be sent to: {webhook_url}")
        print("You can monitor the job status through webhook notifications.")
        print(f"To check job status manually: {api_url}/job/{job_id}")
        print(f"To approve or provide feedback later, run:")
        print(f"  python api_client.py --job-id {job_id} --approve")
        print(f"  python api_client.py --job-id {job_id} --feedback \"Your feedback here\"")
        
        # If using webhooks, don't poll - let the webhook handle it
        if approve or feedback:
            # If approve or feedback is provided, handle it immediately
            return handle_job_feedback(job_id, api_url, approve, feedback)
        else:
            # Otherwise, just return the job ID and let webhooks handle it
            return True

    # Poll for job status until pending_approval
    max_polls = 30
    poll_count = 0

    while poll_count < max_polls:
        poll_count += 1
        print(f"\nPolling job status ({poll_count}/{max_polls})...")

        job_response = requests.get(f"{api_url}/job/{job_id}")

        if job_response.status_code != 200:
            print(
                f"Error getting job status: {job_response.status_code} - {job_response.text}"
            )
            continue

        job_status = job_response.json()
        status = job_status.get("status")

        print(f"Current status: {status}")

        if status == "completed":
            print("\nJob completed successfully!")
            print("\nResult:")
            print(json.dumps(job_status.get("result"), indent=2))
            return True
        elif status == "error":
            print("\nJob failed with error:")
            print(job_status.get("error"))
            return False
        elif status == "pending_approval":
            print("\nJob is waiting for human approval.")
            print("\nContent for review:")
            content = job_status.get("result", {}).get(
                "content", "No content available"
            )
            print("-" * 80)
            print(content[:500] + "..." if len(content) > 500 else content)
            print("-" * 80)

            # Provide feedback or approval
            if approve:
                feedback_payload = {
                    "feedback": "Content approved as is.",
                    "approved": True,
                }
                print("\nApproving content...")
            else:
                if not feedback:
                    feedback = "Please make the content more concise and add more specific examples."
                feedback_payload = {"feedback": feedback, "approved": False}
                print(f"\nProviding feedback: {feedback}")

            feedback_response = requests.post(
                f"{api_url}/job/{job_id}/feedback", json=feedback_payload
            )

            if feedback_response.status_code != 200:
                print(
                    f"Error providing feedback: {feedback_response.status_code} - {feedback_response.text}"
                )
                return False
            else:
                print("Feedback submitted successfully!")

                if approve:
                    print("Content approved, job should be completed.")
                    return True
                else:
                    print("Content being revised with feedback...")
                    print("Continuing to poll for updated content...")

                    # Reset poll count to continue monitoring
                    poll_count = 0
                    max_polls = 15

        # Wait before polling again
        time.sleep(5)

    print("\nReached maximum number of polling attempts. Job may still be processing.")
    return False


def handle_job_feedback(job_id, api_url, approve=False, feedback=None):
    """Handle feedback for an existing job"""
    print(f"Handling feedback for job ID: {job_id}")
    
    # First, check the current job status
    job_response = requests.get(f"{api_url}/job/{job_id}")
    
    if job_response.status_code != 200:
        print(f"Error getting job status: {job_response.status_code} - {job_response.text}")
        return False
        
    job_status = job_response.json()
    status = job_status.get("status")
    
    print(f"Current job status: {status}")
    
    if status != "pending_approval":
        print(f"Job is not in a state that can accept feedback. Current status: {status}")
        print("Only jobs with status 'pending_approval' can receive feedback.")
        return False
    
    # Display the content for review
    content = job_status.get("result", {}).get("content", "No content available")
    print("\nContent for review:")
    print("-" * 80)
    print(content[:500] + "..." if len(content) > 500 else content)
    print("-" * 80)
    
    # Prepare feedback payload
    if approve:
        feedback_payload = {
            "feedback": "Content approved as is.",
            "approved": True,
        }
        print("\nApproving content...")
    else:
        if not feedback:
            feedback = input("Please enter your feedback (or press Enter for default feedback): ")
            if not feedback:
                feedback = "Please make the content more concise and add more specific examples."
        feedback_payload = {"feedback": feedback, "approved": False}
        print(f"\nProviding feedback: {feedback}")
    
    # Submit feedback
    feedback_response = requests.post(
        f"{api_url}/job/{job_id}/feedback", json=feedback_payload
    )
    
    if feedback_response.status_code != 200:
        print(f"Error providing feedback: {feedback_response.status_code} - {feedback_response.text}")
        return False
    else:
        print("Feedback submitted successfully!")
        
        if approve:
            print("Content approved, job is now completed.")
            return True
        else:
            print("Content being revised with feedback...")
            print("You can check the job status later or wait for webhook notifications.")
            return True


async def test_hitl_workflow_async(
    topic, api_url, approve=False, feedback=None, webhook_url=None
):
    """Test the Human-in-the-Loop workflow using asynchronous requests"""
    print(f"\n=== Starting Content Creation with HITL for topic: {topic} ===")
    print("Sending request...")

    async with aiohttp.ClientSession() as session:
        # Step 1: Start a content creation job with HITL
        data = {
            "crew": "ContentCreationCrew", 
            "inputs": {"topic": topic, "require_approval": True}
        }

        # Add webhook URL if provided
        if webhook_url:
            data["webhook_url"] = webhook_url
            print(f"Webhook notifications will be sent to: {webhook_url}")

        async with session.post(f"{api_url}/kickoff", json=data) as response:
            result = await response.json()
            print("\nJob started:")
            print(json.dumps(result, indent=2))

            # Get the job ID
            job_id = result.get("job_id")
            if not job_id:
                print("Error: No job ID returned")
                return False
                
        if webhook_url:
            print(f"\nWebhook notifications will be sent to: {webhook_url}")
            print("You can monitor the job status through webhook notifications.")
            print(f"To check job status manually: {api_url}/job/{job_id}")
            print(f"To approve or provide feedback later, run:")
            print(f"  python api_client.py --job-id {job_id} --approve")
            print(f"  python api_client.py --job-id {job_id} --feedback \"Your feedback here\"")
            
            # If using webhooks, don't poll - let the webhook handle it
            if approve or feedback:
                # If approve or feedback is provided, handle it immediately
                return await handle_job_feedback_async(session, job_id, api_url, approve, feedback)
            else:
                # Otherwise, just return the job ID and let webhooks handle it
                return True

        # Step 2: Poll for job status until it's pending approval
        print("\n=== Polling for Job Status ===")
        job_status = await poll_until_pending_approval_async(session, api_url, job_id)

        if not job_status or job_status.get("status") != "pending_approval":
            print(
                f"Job did not reach pending_approval state. Current status: {job_status.get('status', 'unknown')}"
            )
            return False

        # Step 3: Display the content for review
        content = job_status.get("result", {}).get("content", "")
        print("\n=== Content Ready for Review ===")
        print("-" * 80)
        print(content[:500] + "..." if len(content) > 500 else content)
        print("-" * 80)

        # Step 4: Provide feedback or approval
        if approve:
            feedback_data = {"feedback": "Content approved as is.", "approved": True}
            print("\n=== Approving Content ===")
        else:
            if not feedback:
                feedback = "Please make the content more concise and add more specific examples."
            feedback_data = {"feedback": feedback, "approved": False}
            print(f"\n=== Providing Feedback ===\n{feedback}")

        async with session.post(
            f"{api_url}/job/{job_id}/feedback", json=feedback_data
        ) as response:
            feedback_result = await response.json()
            print("\nFeedback submitted:")
            print(json.dumps(feedback_result, indent=2))

        # Step 5: If not approved, poll for the revised content
        if not approve:
            print("\n=== Polling for Revised Content ===")
            final_status = await poll_until_completed_async(session, api_url, job_id)
            return final_status is not None
        else:
            return True


async def handle_job_feedback_async(session, job_id, api_url, approve=False, feedback=None):
    """Handle feedback for an existing job asynchronously"""
    print(f"\n=== Handling Feedback for Job ID: {job_id} ===")
    
    # First, check the current job status
    async with session.get(f"{api_url}/job/{job_id}") as response:
        job_status = await response.json()
        status = job_status.get("status")
        
        print(f"Current job status: {status}")
        
        if status != "pending_approval":
            print(f"Job is not in a state that can accept feedback. Current status: {status}")
            print("Only jobs with status 'pending_approval' can receive feedback.")
            return False
        
        # Display the content for review
        content = job_status.get("result", {}).get("content", "No content available")
        print("\n=== Content for Review ===")
        print("-" * 80)
        print(content[:500] + "..." if len(content) > 500 else content)
        print("-" * 80)
        
        # Prepare feedback payload
        if approve:
            feedback_data = {"feedback": "Content approved as is.", "approved": True}
            print("\n=== Approving Content ===")
        else:
            if not feedback:
                feedback = input("Please enter your feedback (or press Enter for default feedback): ")
                if not feedback:
                    feedback = "Please make the content more concise and add more specific examples."
            feedback_data = {"feedback": feedback, "approved": False}
            print(f"\n=== Providing Feedback ===\n{feedback}")
        
        # Submit feedback
        async with session.post(f"{api_url}/job/{job_id}/feedback", json=feedback_data) as response:
            feedback_result = await response.json()
            print("\nFeedback submitted:")
            print(json.dumps(feedback_result, indent=2))
            
            if approve:
                print("Content approved, job is now completed.")
                return True
            else:
                print("Content being revised with feedback...")
                print("You can check the job status later or wait for webhook notifications.")
                return True


async def poll_until_pending_approval_async(
    session, api_url, job_id, max_attempts=30, delay=5
):
    """Poll until job reaches pending_approval status"""
    for attempt in range(1, max_attempts + 1):
        async with session.get(f"{api_url}/job/{job_id}") as response:
            job_status = await response.json()
            status = job_status.get("status")

            print(f"Attempt {attempt}: Status = {status}")

            if status == "pending_approval":
                print("\nJob is ready for human review!")
                return job_status
            elif status == "error":
                print("\nJob failed with error:")
                print(job_status.get("error", "Unknown error"))
                return None
            elif status == "processing" or status == "queued":
                print(f"Job still {status}... waiting {delay} seconds")
                await asyncio.sleep(delay)
            else:
                print(f"Unexpected status: {status}")
                return job_status

    print("Maximum polling attempts reached.")
    return None


async def poll_until_completed_async(
    session, api_url, job_id, max_attempts=30, delay=5
):
    """Poll until job reaches completed status"""
    for attempt in range(1, max_attempts + 1):
        async with session.get(f"{api_url}/job/{job_id}") as response:
            job_status = await response.json()
            status = job_status.get("status")

            print(f"Attempt {attempt}: Status = {status}")

            if status == "completed":
                print("\nJob completed successfully!")
                content = job_status.get("result", {}).get("content", "")
                print("\n=== Revised Content ===")
                print("-" * 80)
                print(content[:500] + "..." if len(content) > 500 else content)
                print("-" * 80)
                return job_status
            elif status == "error":
                print("\nJob failed with error:")
                print(job_status.get("error", "Unknown error"))
                return None
            elif status == "processing" or status == "queued":
                print(f"Job still {status}... waiting {delay} seconds")
                await asyncio.sleep(delay)
            else:
                print(f"Unexpected status: {status}")
                return job_status

    print("Maximum polling attempts reached.")
    return None


def main():
    """Main function to parse arguments and call the appropriate method"""
    parser = argparse.ArgumentParser(
        description="Unified CrewAI Content Generation Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Direct content generation with waiting
  python api_client.py --topic "Artificial Intelligence" --mode direct --wait
  
  # HITL workflow with webhook notifications (recommended)
  python api_client.py --topic "Climate Change" --mode hitl --webhook http://localhost:8889/webhook
  
  # HITL workflow with automatic approval
  python api_client.py --topic "Climate Change" --mode hitl --approve
  
  # HITL workflow with feedback
  python api_client.py --topic "Renewable Energy" --mode hitl --feedback "Add more examples about solar power"
  
  # HITL workflow with async mode
  python api_client.py --topic "Digital Privacy" --mode hitl --async
  
  # Provide feedback for an existing job
  python api_client.py --job-id "your-job-id" --feedback "Please add more examples"
  
  # Approve an existing job
  python api_client.py --job-id "your-job-id" --approve
""",
    )

    parser.add_argument("--topic", help="Topic for content generation (required for new jobs)")
    parser.add_argument("--url", default=DEFAULT_API_URL, help="API URL")
    parser.add_argument(
        "--mode",
        choices=["direct", "hitl"],
        default="direct",
        help="Mode of operation (direct = no human approval, hitl = human-in-the-loop)",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for the result instead of polling (only for direct mode)",
    )
    parser.add_argument(
        "--webhook", help="Webhook URL to receive notifications (default for HITL: http://localhost:8889/webhook)"
    )
    parser.add_argument(
        "--no-webhook",
        action="store_true",
        help="Disable webhook notifications",
    )
    parser.add_argument(
        "--job-id",
        help="Job ID to provide feedback for (for existing jobs)",
    )
    parser.add_argument(
        "--feedback", help="Feedback to provide if not approving (only for hitl mode)"
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Approve content instead of providing feedback (only for hitl mode)",
    )
    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        help="Use asyncio for HITL workflow (more efficient)",
    )

    args = parser.parse_args()
    
    # Set webhook URL based on mode and arguments
    webhook_url = None
    if args.no_webhook:
        webhook_url = None  # Explicitly disable webhooks
    elif args.webhook:
        webhook_url = args.webhook  # Use explicitly provided webhook
    elif args.mode == "hitl":
        webhook_url = DEFAULT_WEBHOOK_URL  # Use default webhook only for HITL mode
    
    # Check if we're handling an existing job
    if args.job_id:
        if not (args.approve or args.feedback is not None):
            print("Error: When using --job-id, you must specify either --approve or --feedback")
            sys.exit(1)
            
        if args.use_async:
            success = asyncio.run(
                handle_job_feedback_async(
                    aiohttp.ClientSession(), args.job_id, args.url, args.approve, args.feedback
                )
            )
        else:
            success = handle_job_feedback(args.job_id, args.url, args.approve, args.feedback)
    else:
        # We're starting a new job
        if not args.topic:
            print("Error: --topic is required when starting a new job")
            sys.exit(1)
            
        # Validate arguments
        if args.mode == "direct" and (args.feedback is not None or args.approve):
            print("Warning: --feedback and --approve are ignored in direct mode")

        if args.mode == "direct" and args.use_async:
            print("Warning: --async is ignored in direct mode")

        # Execute the appropriate function based on mode
        if args.mode == "direct":
            success = generate_content_direct(args.topic, args.url, args.wait, webhook_url)
        else:  # hitl mode
            if args.use_async:
                success = asyncio.run(
                    test_hitl_workflow_async(
                        args.topic, args.url, args.approve, args.feedback, webhook_url
                    )
                )
            else:
                success = test_hitl_workflow_sync(
                    args.topic, args.url, args.approve, args.feedback, webhook_url
                )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
