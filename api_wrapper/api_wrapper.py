from datetime import datetime
import importlib.util
import logging
import os
import sys
import uuid
import requests
from typing import Optional

import tomli
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Set a longer timeout for the app to handle long-running operations
app = FastAPI(
    title="CrewAI Content Orchestrator",
    # Note: When running with uvicorn, use the following command line options:
    # --timeout-keep-alive 300 --timeout-graceful-shutdown 300
)

# Add CORS middleware with security settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

# Add trusted host middleware for security
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"],  # In production, specify your actual domains
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# In-memory storage for jobs
jobs = {}

# Load environment variables from .env file
load_dotenv()
logger.info("Loaded environment variables from .env file")

# Load secrets from .streamlit/secrets.toml
try:
    with open(".streamlit/secrets.toml", "rb") as f:
        secrets = tomli.load(f)
        for key, value in secrets.items():
            if isinstance(value, str):
                os.environ[key] = value
        logger.info("Successfully loaded secrets from .streamlit/secrets.toml")
except Exception as e:
    logger.warning(f"Could not load secrets: {e}")

# Import the user's script
script_path = os.getenv("DATA_APP_ENTRYPOINT")
if not script_path:
    logger.error("DATA_APP_ENTRYPOINT environment variable is not set")
    sys.exit(1)

# Check if the script file exists
if not os.path.exists(script_path):
    logger.error(f"Script file not found: {script_path}")
    logger.error(
        "Please make sure the file exists and DATA_APP_ENTRYPOINT is set correctly"
    )
    sys.exit(1)

# Add the src directory to the Python path if it exists
script_dir = os.path.dirname(script_path)
parent_dir = os.path.dirname(script_dir)

# Add both the script directory and its parent to the Python path
# This helps with imports in various project structures
logger.info(f"Adding script directory to Python path: {script_dir}")
sys.path.insert(0, script_dir)

# If there's a src directory, add it too
src_dir = os.path.join(parent_dir, "src")
if os.path.exists(src_dir):
    logger.info(f"Adding src directory to Python path: {src_dir}")
    sys.path.insert(0, src_dir)

# Also add the parent directory to handle imports like 'from project_name import x'
logger.info(f"Adding parent directory to Python path: {parent_dir}")
sys.path.insert(0, parent_dir)

try:
    spec = importlib.util.spec_from_file_location("user_script", script_path)
    user_module = importlib.util.module_from_spec(spec)
    sys.modules["user_script"] = user_module
    spec.loader.exec_module(user_module)
    logger.info(f"Successfully loaded user script from {script_path}")
except Exception as e:
    logger.error(f"Failed to load user script: {e}")
    raise


def process_job_in_background(
    job_id: str,
    crew_name: str,
    inputs: dict,
    webhook_url: Optional[str] = None,
):
    """
    Process a crew job in the background and update its status
    """
    try:
        logger.info(f"Starting background job {job_id} for crew {crew_name}")

        # Update job status to processing
        jobs[job_id]["status"] = "processing"

        # Check if require_approval is specified in inputs
        require_approval = inputs.pop("require_approval", True)
        logger.info(f"Require approval: {require_approval}")

        # Check for required environment variables based on crew type
        if crew_name == "ConvoNewsletterCrew":
            required_env_vars = ["ANTHROPIC_API_KEY", "EXA_API_KEY"]
            optional_env_vars = ["MODEL"]
            
            missing_vars = []
            for var in required_env_vars:
                if not os.getenv(var):
                    logger.warning(f"Required environment variable {var} is not set for {crew_name}")
                    missing_vars.append(var)
            
            for var in optional_env_vars:
                if not os.getenv(var):
                    logger.info(f"Optional environment variable {var} is not set for {crew_name}, will use default")
            
            if missing_vars:
                logger.error(f"Missing required environment variables for {crew_name}: {', '.join(missing_vars)}")
                raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        else:
            # Generic check for other crew types
            common_env_vars = ["OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
            missing_vars = []
            for var in common_env_vars:
                if not os.getenv(var):
                    logger.warning(f"Environment variable {var} is not set")
                    missing_vars.append(var)
            
            if missing_vars:
                logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")
                logger.warning("Some crew implementations may require these variables")

        # Get the crew class from the user module
        crew_class = getattr(user_module, crew_name)
        
        # Determine if the crew class is a CrewBase class
        is_crew_base = hasattr(crew_class, '__crewbase__')
        logger.info(f"Crew class {crew_name} is CrewBase: {is_crew_base}")
        
        # Initialize the crew instance based on its type
        try:
            # First try initializing with inputs
            crew_instance = crew_class(inputs=inputs)
            logger.info(f"Created crew instance with inputs parameter")
        except TypeError:
            try:
                # If that fails, try without inputs parameter
                crew_instance = crew_class()
                logger.info(f"Created crew instance without inputs parameter")
            except Exception as e:
                logger.error(f"Failed to create crew instance: {e}")
                raise
        
        logger.info(f"Created crew instance of type: {type(crew_instance).__name__}")

        # For CrewBase classes, we need to find a method that returns a Crew object
        # These are typically decorated with @crew
        crew_methods = []
        for method_name in dir(crew_instance):
            if not method_name.startswith("_") and callable(
                getattr(crew_instance, method_name)
            ):
                method = getattr(crew_instance, method_name)
                # Check if this is a crew method (has a __crew__ attribute or returns a Crew)
                if hasattr(method, "__crew__"):
                    crew_methods.append(method_name)
                    logger.info(
                        f"Found crew method with __crew__ attribute: {method_name}"
                    )
                elif (
                    hasattr(method, "__annotations__")
                    and "return" in method.__annotations__
                    and method.__annotations__["return"] is not None
                    and hasattr(method.__annotations__["return"], "__name__")
                    and method.__annotations__["return"].__name__ == "Crew"
                ):
                    crew_methods.append(method_name)
                    logger.info(
                        f"Found crew method with Crew return annotation: {method_name}"
                    )

        if not crew_methods:
            # If no crew methods found, try to use create_content_with_hitl directly
            if hasattr(user_module, "create_content_with_hitl"):
                logger.info(
                    "No crew methods found, using create_content_with_hitl directly"
                )

                # Add require_approval back to inputs for create_content_with_hitl
                inputs_with_approval = inputs.copy()
                inputs_with_approval["require_approval"] = require_approval

                # Call create_content_with_hitl directly
                result = user_module.create_content_with_hitl(
                    topic=inputs["topic"],
                    feedback=inputs.get("feedback"),
                    require_approval=require_approval,
                )

                # Convert result to a dictionary if it's not already
                if not isinstance(result, dict):
                    result_dict = {"content": str(result), "length": len(str(result))}
                else:
                    result_dict = result

                # Check if the result indicates human approval is needed and require_approval is True
                if require_approval and result_dict.get("status") == "needs_approval":
                    # Update job status to waiting for human input
                    jobs[job_id] = {
                        **jobs[job_id],
                        "status": "pending_approval",
                        "result": result_dict,
                        "retry_crew": crew_name,  # Store crew for retry
                        "retry_inputs": inputs,
                    }

                    logger.info(f"Job {job_id} waiting for human approval")

                    # Send webhook notification if URL is provided
                    if webhook_url:
                        try:
                            webhook_payload = {
                                "job_id": job_id,
                                "status": "pending_approval",
                                "crew": crew_name,
                                "result": result_dict,
                            }

                            requests.post(
                                webhook_url,
                                json=webhook_payload,
                                headers={"Content-Type": "application/json"},
                                timeout=10,
                            )
                            logger.info(
                                f"Webhook notification sent for job {job_id} "
                                "pending approval"
                            )
                        except Exception as webhook_error:
                            logger.error(
                                f"Failed to send webhook notification for job "
                                f"{job_id}: {str(webhook_error)}"
                            )
                else:
                    # Update job with success result
                    jobs[job_id] = {
                        **jobs[job_id],
                        "status": "completed",
                        "completed_at": datetime.now().isoformat(),
                        "result": result_dict,
                    }

                    logger.info(f"Job {job_id} completed successfully")

                    # Send webhook notification if URL is provided
                    if webhook_url:
                        try:
                            webhook_payload = {
                                "job_id": job_id,
                                "status": "completed",
                                "crew": crew_name,
                                "completed_at": jobs[job_id]["completed_at"],
                                "result": result_dict,
                            }

                            requests.post(
                                webhook_url,
                                json=webhook_payload,
                                headers={"Content-Type": "application/json"},
                                timeout=10,
                            )
                            logger.info(f"Webhook notification sent for job {job_id}")
                        except Exception as webhook_error:
                            logger.error(
                                f"Failed to send webhook notification for job "
                                f"{job_id}: {str(webhook_error)}"
                            )

                return
            else:
                raise ValueError(
                    f"No crew methods found in {crew_name} and "
                    "no create_content_with_hitl function available"
                )

        # Choose the appropriate crew method based on inputs
        if "feedback" in inputs and "content_crew_with_feedback" in crew_methods:
            crew_method_name = "content_crew_with_feedback"
        else:
            crew_method_name = crew_methods[0]  # Default to first crew method

        logger.info(f"Using crew method: {crew_method_name}")

        # Get the crew method
        crew_method = getattr(crew_instance, crew_method_name)
        logger.info(f"Crew method type: {type(crew_method).__name__}")

        # First call the crew method to get the Crew object
        logger.info("Calling crew method to get crew object")
        crew_object = crew_method()

        if crew_object is None:
            raise ValueError(
                f"Crew method {crew_method_name} returned None instead of a Crew object"
            )

        logger.info(f"Crew object type: {type(crew_object).__name__}")

        # Now call kickoff on the crew object
        # Try different approaches to kickoff based on what the crew supports
        try:
            # First try with inputs parameter
            logger.info("Attempting to call kickoff with inputs parameter")
            result = crew_object.kickoff(inputs=inputs)
        except TypeError as e:
            if "unexpected keyword argument 'inputs'" in str(e):
                # If that fails with the specific error about inputs, try without inputs
                logger.info("Calling kickoff without inputs parameter")
                result = crew_object.kickoff()
            else:
                # If it's a different TypeError, re-raise
                raise
            
        logger.info(f"Kickoff result type: {type(result).__name__}")

        # Convert result to a dictionary if it's a TaskOutput object
        result_dict = {}
        if hasattr(result, "raw"):
            content = str(result.raw)
            result_dict = {"content": content, "length": len(content)}
        elif isinstance(result, dict):
            result_dict = result
        else:
            content = str(result)
            result_dict = {"content": content, "length": len(content)}

        # Check if the result indicates human approval is needed and require_approval is True
        if (
            require_approval
            and isinstance(result_dict, dict)
            and result_dict.get("status") == "needs_approval"
        ):
            # Update job status to waiting for human input
            jobs[job_id] = {
                **jobs[job_id],
                "status": "pending_approval",
                "result": result_dict,
                "retry_crew": crew_name,  # Store crew for retry
                "retry_inputs": inputs,
            }

            logger.info(f"Job {job_id} waiting for human approval")

            # Send webhook notification if URL is provided
            if webhook_url:
                try:
                    webhook_payload = {
                        "job_id": job_id,
                        "status": "pending_approval",
                        "crew": crew_name,
                        "result": result_dict,
                    }

                    requests.post(
                        webhook_url,
                        json=webhook_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                    )
                    logger.info(
                        f"Webhook notification sent for job {job_id} pending approval"
                    )
                except Exception as webhook_error:
                    logger.error(
                        f"Failed to send webhook notification for job "
                        f"{job_id}: {str(webhook_error)}"
                    )
        else:
            # Update job with success result
            jobs[job_id] = {
                **jobs[job_id],
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "result": result_dict,
            }

            logger.info(f"Job {job_id} completed successfully")

            # Send webhook notification if URL is provided
            if webhook_url:
                try:
                    webhook_payload = {
                        "job_id": job_id,
                        "status": "completed",
                        "crew": crew_name,
                        "completed_at": jobs[job_id]["completed_at"],
                        "result": result_dict,
                    }

                    requests.post(
                        webhook_url,
                        json=webhook_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                    )
                    logger.info(f"Webhook notification sent for job {job_id}")
                except Exception as webhook_error:
                    logger.error(
                        f"Failed to send webhook notification for job "
                        f"{job_id}: {str(webhook_error)}"
                    )

    except Exception as e:
        logger.error(f"Error processing job {job_id}: {str(e)}")

        # Update job with error information
        jobs[job_id] = {
            **jobs[job_id],
            "status": "error",
            "error_at": datetime.now().isoformat(),
            "error": str(e),
            "error_type": e.__class__.__name__,
        }

        # Send webhook notification about error if URL is provided
        if webhook_url:
            try:
                webhook_payload = {
                    "job_id": job_id,
                    "status": "error",
                    "crew": crew_name,
                    "error_at": jobs[job_id]["error_at"],
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                }

                requests.post(
                    webhook_url,
                    json=webhook_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                logger.info(f"Error webhook notification sent for job {job_id}")
            except Exception as webhook_error:
                logger.error(
                    f"Failed to send error webhook notification for job "
                    f"{job_id}: {str(webhook_error)}"
                )


@app.get("/")
async def root():
    """Root endpoint with application status"""
    return {
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for the proxy"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "module_loaded": user_module is not None,
        "active_jobs": len([j for j in jobs.values() if j["status"] == "processing"]),
    }


@app.post("/kickoff")
async def kickoff_crew(request: Request, background_tasks: BackgroundTasks):
    """
    Kickoff a crew asynchronously and return a job ID
    """
    try:
        data = await request.json()
        crew_name = data.get("crew", "ContentCreationCrew")
        inputs = data.get("inputs", {})
        webhook_url = data.get("webhook_url")
        wait = data.get("wait", False)  # Option to wait for completion
        require_approval = inputs.get(
            "require_approval", True
        )  # Get require_approval from inputs
        
        # Get environment variables from request if provided
        env_vars = data.get("env_vars", {})
        
        # Special handling for ConvoNewsletterCrew
        if crew_name == "ConvoNewsletterCrew":
            # Check for required environment variables
            if "ANTHROPIC_API_KEY" not in env_vars and not os.getenv("ANTHROPIC_API_KEY"):
                return JSONResponse(
                    status_code=400,
                    content={"error": "ANTHROPIC_API_KEY is required for ConvoNewsletterCrew"},
                )
                
            # Check for EXA_API_KEY
            if "EXA_API_KEY" not in env_vars and not os.getenv("EXA_API_KEY"):
                logger.warning("EXA_API_KEY is not provided for ConvoNewsletterCrew, some functionality may not work")
        
        # Set environment variables from request
        for key, value in env_vars.items():
            if isinstance(value, str):
                logger.info(f"Setting environment variable from request: {key}")
                os.environ[key] = value

        logger.info(f"Kickoff request for crew {crew_name} with inputs: {inputs}")
        logger.info(
            f"Wait for completion: {wait}, Require approval: {require_approval}"
        )

        # Check if the crew exists in the user module
        if not hasattr(user_module, crew_name):
            logger.error(f"Crew {crew_name} not found in user module")
            return JSONResponse(
                status_code=404,
                content={"error": f"Crew {crew_name} not found"},
            )

        # Generate a unique job ID
        job_id = str(uuid.uuid4())

        # Initialize job in the jobs dictionary
        jobs[job_id] = {
            "id": job_id,
            "crew": crew_name,
            "inputs": inputs,
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "webhook_url": webhook_url,
        }

        logger.info(f"Created job {job_id} for crew {crew_name}")

        if wait:
            # Synchronous execution - wait for result
            try:
                logger.info(f"Executing job {job_id} synchronously")

                # Check if we should use create_content_with_hitl directly
                if (
                    hasattr(user_module, "create_content_with_hitl")
                    and crew_name == "ContentCreationCrew"
                ):
                    logger.info(
                        "Using create_content_with_hitl directly for synchronous execution"
                    )

                    # Call create_content_with_hitl directly
                    result = user_module.create_content_with_hitl(
                        topic=inputs["topic"],
                        feedback=inputs.get("feedback"),
                        require_approval=require_approval,
                    )

                    # Convert result to a dictionary if it's not already
                    if not isinstance(result, dict):
                        result_dict = {
                            "content": str(result),
                            "length": len(str(result)),
                        }
                    else:
                        result_dict = result

                    # Update job with success result
                    jobs[job_id] = {
                        **jobs[job_id],
                        "status": "completed"
                        if result_dict.get("status") != "needs_approval"
                        else "pending_approval",
                        "completed_at": datetime.now().isoformat(),
                        "result": result_dict,
                    }

                    return {
                        "job_id": job_id,
                        "status": jobs[job_id]["status"],
                        "result": result_dict,
                    }

                # Otherwise, use the crew approach
                crew_class = getattr(user_module, crew_name)
                
                # Determine if the crew class is a CrewBase class
                is_crew_base = hasattr(crew_class, '__crewbase__')
                logger.info(f"Crew class {crew_name} is CrewBase: {is_crew_base}")
                
                # Initialize the crew instance based on its type
                try:
                    # First try initializing with inputs
                    crew_instance = crew_class(inputs=inputs)
                    logger.info(f"Created crew instance with inputs parameter")
                except TypeError:
                    try:
                        # If that fails, try without inputs parameter
                        crew_instance = crew_class()
                        logger.info(f"Created crew instance without inputs parameter")
                    except Exception as e:
                        logger.error(f"Failed to create crew instance: {e}")
                        raise
                
                logger.info(f"Created crew instance of type: {type(crew_instance).__name__}")

                # For CrewBase classes, we need to find a method that returns a Crew object
                # These are typically decorated with @crew
                crew_methods = []
                for method_name in dir(crew_instance):
                    if not method_name.startswith("_") and callable(
                        getattr(crew_instance, method_name)
                    ):
                        method = getattr(crew_instance, method_name)
                        # Check if this is a crew method (has a __crew__ attribute or returns a Crew)
                        if hasattr(method, "__crew__"):
                            crew_methods.append(method_name)
                            logger.info(
                                f"Found crew method with __crew__ attribute: {method_name}"
                            )
                        elif (
                            hasattr(method, "__annotations__")
                            and "return" in method.__annotations__
                            and method.__annotations__["return"] is not None
                            and hasattr(method.__annotations__["return"], "__name__")
                            and method.__annotations__["return"].__name__ == "Crew"
                        ):
                            crew_methods.append(method_name)
                            logger.info(
                                f"Found crew method with Crew return annotation: {method_name}"
                            )

                if not crew_methods:
                    logger.error(f"No crew methods found in {crew_name}")
                    raise ValueError(f"No crew methods found in {crew_name}")

                # Choose the appropriate crew method based on inputs
                if (
                    "feedback" in inputs
                    and "content_crew_with_feedback" in crew_methods
                ):
                    crew_method_name = "content_crew_with_feedback"
                else:
                    crew_method_name = crew_methods[0]  # Default to first crew method

                logger.info(f"Using crew method: {crew_method_name}")

                # Get the crew method
                crew_method = getattr(crew_instance, crew_method_name)
                logger.info(f"Crew method type: {type(crew_method).__name__}")

                # First call the crew method to get the Crew object
                logger.info("Calling crew method to get crew object")
                crew_object = crew_method()

                if crew_object is None:
                    raise ValueError(
                        f"Crew method {crew_method_name} returned None "
                        "instead of a Crew object"
                    )

                logger.info(f"Crew object type: {type(crew_object).__name__}")

                # Now call kickoff on the crew object
                # Try different approaches to kickoff based on what the crew supports
                try:
                    # First try with inputs parameter
                    logger.info("Attempting to call kickoff with inputs parameter")
                    result = crew_object.kickoff(inputs=inputs)
                except TypeError as e:
                    if "unexpected keyword argument 'inputs'" in str(e):
                        # If that fails with the specific error about inputs, try without inputs
                        logger.info("Calling kickoff without inputs parameter")
                        result = crew_object.kickoff()
                    else:
                        # If it's a different TypeError, re-raise
                        raise
                
                logger.info(f"Kickoff result type: {type(result).__name__}")

                # Convert result to a dictionary if it's a TaskOutput object
                result_dict = {}
                if hasattr(result, "raw"):
                    content = str(result.raw)
                    result_dict = {"content": content, "length": len(content)}
                elif isinstance(result, dict):
                    result_dict = result
                else:
                    content = str(result)
                    result_dict = {"content": content, "length": len(content)}

                # Update job with success result
                jobs[job_id] = {
                    **jobs[job_id],
                    "status": "completed",
                    "completed_at": datetime.now().isoformat(),
                    "result": result_dict,
                }

                return {"job_id": job_id, "status": "completed", "result": result_dict}
            except Exception as e:
                # Update job with error information
                jobs[job_id] = {
                    **jobs[job_id],
                    "status": "error",
                    "error_at": datetime.now().isoformat(),
                    "error": str(e),
                    "error_type": e.__class__.__name__,
                }

                return JSONResponse(
                    status_code=500,
                    content={"job_id": job_id, "status": "error", "error": str(e)},
                )
        else:
            # Asynchronous execution - start in background
            background_tasks.add_task(
                process_job_in_background,
                job_id,
                crew_name,
                inputs,
                webhook_url,
            )

            return {
                "job_id": job_id,
                "status": "queued",
                "message": "Crew kickoff started in the background",
            }

    except Exception as e:
        logger.error(f"Error setting up crew kickoff: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/job/{job_id}")
async def get_job(job_id: str):
    """Get the status and result of a specific job"""
    if job_id not in jobs:
        return JSONResponse(
            status_code=404, content={"error": f"Job with ID {job_id} not found"}
        )

    return jobs[job_id]


@app.post("/job/{job_id}/feedback")
async def provide_feedback(
    job_id: str, request: Request, background_tasks: BackgroundTasks
):
    """
    Provide human feedback for a job and optionally resume processing
    """
    if job_id not in jobs:
        return JSONResponse(
            status_code=404, content={"error": f"Job with ID {job_id} not found"}
        )

    # Check if job is in a state that can accept feedback
    if jobs[job_id].get("status") != "pending_approval":
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    f"Job {job_id} is not in a state that can accept feedback. "
                    f"Current status: {jobs[job_id].get('status')}"
                )
            },
        )

    try:
        data = await request.json()
        feedback = data.get("feedback", "")
        approved = data.get("approved", False)

        # Update job with feedback
        jobs[job_id]["feedback"] = feedback
        jobs[job_id]["human_approved"] = approved
        jobs[job_id]["feedback_at"] = datetime.now().isoformat()

        # Get the webhook URL if it exists
        webhook_url = jobs[job_id].get("webhook_url")

        if approved:
            # If approved, mark as completed
            jobs[job_id]["status"] = "completed"

            # Send webhook notification if URL is provided
            if webhook_url:
                try:
                    webhook_payload = {
                        "job_id": job_id,
                        "status": "completed",
                        "feedback": feedback,
                        "approved": True,
                        "completed_at": datetime.now().isoformat(),
                    }

                    requests.post(
                        webhook_url,
                        json=webhook_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                    )
                    logger.info(f"Approval webhook notification sent for job {job_id}")
                except Exception as webhook_error:
                    logger.error(
                        f"Failed to send approval webhook notification for job "
                        f"{job_id}: {str(webhook_error)}"
                    )

            return {
                "message": "Feedback recorded and job marked as completed",
                "job_id": job_id,
            }
        else:
            # If not approved, restart the job with feedback
            # Get the original crew and inputs
            retry_crew = jobs[job_id].get("retry_crew")
            retry_inputs = (
                jobs[job_id].get("retry_inputs", {}).copy()
            )  # Make a copy to avoid modifying the original

            # Add feedback to inputs
            retry_inputs["feedback"] = feedback

            # Update job status to processing again
            jobs[job_id]["status"] = "processing"

            # Start retry in background
            background_tasks.add_task(
                process_job_in_background,
                job_id,
                retry_crew,
                retry_inputs,
                webhook_url,
            )

            return {
                "message": (
                    "Feedback recorded and content generation restarted with feedback"
                ),
                "job_id": job_id,
            }

    except Exception as e:
        logger.error(f"Error processing feedback for job {job_id}: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/jobs")
async def list_jobs(limit: int = 10, status: Optional[str] = None):
    """List all jobs with optional filtering"""
    filtered_jobs = []

    for job_id, job_data in jobs.items():
        if status is None or job_data.get("status") == status:
            # Create a copy without potentially large result data
            job_summary = {
                "id": job_id,
                "crew": job_data.get("crew"),
                "status": job_data.get("status"),
                "created_at": job_data.get("created_at"),
                "completed_at": job_data.get("completed_at", None),
                "has_result": "result" in job_data,
                "has_error": "error" in job_data,
            }
            filtered_jobs.append(job_summary)

    # Sort by created_at (newest first)
    filtered_jobs.sort(key=lambda x: x["created_at"], reverse=True)

    # Apply limit
    filtered_jobs = filtered_jobs[:limit]

    return {"jobs": filtered_jobs, "count": len(filtered_jobs), "total_jobs": len(jobs)}


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Delete a job from the jobs dictionary"""
    if job_id not in jobs:
        return JSONResponse(
            status_code=404, content={"error": f"Job with ID {job_id} not found"}
        )

    del jobs[job_id]
    return {"message": f"Job {job_id} deleted successfully"}


@app.get("/list-crews")
async def list_crews():
    """List available crews in the user module"""
    try:
        crews = []
        # First, find top-level functions that return Dict
        for name, obj in vars(user_module).items():
            if callable(obj) and not name.startswith("_"):
                if hasattr(obj, "__annotations__") and "return" in obj.__annotations__:
                    return_type = obj.__annotations__["return"]
                    if (
                        return_type is not None
                        and hasattr(return_type, "__name__")
                        and return_type.__name__ == "Dict"
                    ):
                        crews.append(name)

        # Look for classes with CrewBase functionality
        for class_name, class_obj in vars(user_module).items():
            if (
                isinstance(class_obj, type)
                and hasattr(class_obj, "__module__")
                and class_obj.__module__ == user_module.__name__
            ):
                # Check if this is a CrewBase class by looking for the is_crew_class attribute
                # or by checking if the class name contains "CrewBase"
                is_crew_base = False

                # Check if it's a wrapped CrewBase class
                if hasattr(class_obj, "is_crew_class") and getattr(
                    class_obj, "is_crew_class", False
                ):
                    is_crew_base = True
                # Or check if it's named like a CrewBase class
                elif "CrewBase" in class_obj.__name__:
                    is_crew_base = True

                if is_crew_base:
                    # Try to create an instance to inspect its methods
                    try:
                        instance = class_obj()

                        # Look for methods that return a Crew object
                        for method_name in dir(instance):
                            if not method_name.startswith("_") and callable(
                                getattr(instance, method_name)
                            ):
                                method = getattr(instance, method_name)

                                # Check if this method returns a Crew based on annotations
                                is_crew_method = False

                                # Check if it has the return type annotation for Crew
                                if (
                                    hasattr(method, "__annotations__")
                                    and "return" in method.__annotations__
                                    and method.__annotations__["return"] is not None
                                    and hasattr(
                                        method.__annotations__["return"], "__name__"
                                    )
                                    and method.__annotations__["return"].__name__
                                    == "Crew"
                                ):
                                    is_crew_method = True

                                # Or check if it's wrapped by the @crew decorator
                                elif (
                                    hasattr(method, "__closure__")
                                    and method.__closure__ is not None
                                ):
                                    # The @crew decorator wraps the original function
                                    is_crew_method = True

                                if is_crew_method and method_name not in crews:
                                    crews.append(method_name)
                                    logger.info(f"Found crew method: {method_name}")
                    except Exception as e:
                        logger.warning(
                            f"Could not inspect methods of {class_name}: {str(e)}"
                        )

        return {"crews": crews}
    except Exception as e:
        logger.error(f"Error listing crews: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})
