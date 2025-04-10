from datetime import datetime
import importlib.util
import logging
import os
import sys
import uuid

import tomli
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from crewai_app import KeboolaInsightsCrew

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
async def kickoff_analytics(request: Request, background_tasks: BackgroundTasks):
    """
    Kickoff the KeboolaInsightsCrew pipeline with a provided table_id.
    Env vars are used for the rest of the configuration.
    """
    try:
        data = await request.json()
        job_id = str(uuid.uuid4())
        env_vars = data.get("env_vars", {})
        inputs = data.get("inputs", {})
        table_id = inputs.get("table_id", "in.c-usage.usage_data_customer")

        if not table_id:
            return JSONResponse(
                status_code=422,
                content={"error": "Missing required parameter: table_id"},
            )

        logger.info(f"Received kickoff request for table_id: {table_id}")
        logger.info(f"Received env_vars override: {env_vars}")

        for key, value in env_vars.items():
            if isinstance(value, str):
                logger.info(f"Setting env var {key} from request")
                os.environ[key] = value

        crew_inputs = {
            "table_id": table_id,
            "slack_webhook_url": os.getenv("SLACK_WEBHOOK_URL"),
            "kbc_api_token": os.getenv("KBC_API_TOKEN"),
            "kbc_api_url": os.getenv("KBC_API_URL"),
        }

        logger.info("Prepared crew inputs")

        def run_pipeline():
            crew = KeboolaInsightsCrew(inputs=crew_inputs)
            result = crew.analyze_data_with_no_approval()
            logger.info(f"Async crew result: {result}")

            logger.info("Running crew synchronously (wait=true)")
            crew = KeboolaInsightsCrew(inputs=crew_inputs)
            result = crew.analyze_data_with_no_approval()

            return {
                "job_id": job_id,
                "status": result.get("status"),
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error(f"Error setting up crew kickoff: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})


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
