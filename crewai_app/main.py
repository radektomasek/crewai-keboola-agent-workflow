import logging
from datetime import datetime
from typing import Dict, Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from langchain_openai import ChatOpenAI
from crewai_app.tools import download_keboola_table, make_post_to_slack_tool
from crewai_app.utils import format_slack_summary_with_ai_per_customer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@CrewBase
class KeboolaInsightsCrew:
    def __init__(self, inputs):
        self.inputs = inputs or {}
        self.table_id = self.inputs.get("table_id")
        self.kbc_api_token = self.inputs.get("kbc_api_token")
        self.kbc_api_url = self.inputs.get("kbc_api_url", "https://connection.keboola.com")
        self.slack_webhook_url = self.inputs.get("slack_webhook_url")

        if not self.table_id or not self.kbc_api_token or not self.slack_webhook_url:
            raise ValueError("Missing one of: table_id, kbc_api_token, slack_webhook_url")

        self.df = download_keboola_table(self.table_id, self.kbc_api_token, self.kbc_api_url)

    def _llm(self):
        return ChatOpenAI(model="gpt-4o-mini", temperature=0)

    @agent
    def analytics_agent(self) -> Agent:
        from crewai_app.agents import analytics_agent
        return analytics_agent()

    @task
    def calculate_billed_credits_task(self) -> Task:
        from crewai_app.tasks import calculate_billed_credits_task
        return calculate_billed_credits_task(self.df)

    @task
    def calculate_error_rate_task(self) -> Task:
        from crewai_app.tasks import calculate_error_rate_task
        return calculate_error_rate_task(self.df)

    @crew
    def analytics_pipeline_crew(self) -> Crew:
        return Crew(
            agents=[
                self.analytics_agent()
            ],
            tasks=[
                self.calculate_billed_credits_task(),
                self.calculate_error_rate_task()
            ],
            process=Process.sequential,
            verbose=True,
        )

    def analyze_data_with_no_approval(self) -> Dict[str, Any]:
        """
        Run the analytics pipeline, generate a per-customer summary using AI,
        and post the results to Slack. No manual verification is required.

        Returns:
            Dictionary with status, Slack message, result string, and timestamp.
        """
        logger.info("Starting data analysis pipeline with no approval required.")

        try:
            logger.info("Creating analytics pipeline Crew instance.")
            crew = self.analytics_pipeline_crew()

            if crew is None:
                raise ValueError("analytics_pipeline_crew returned None")

            logger.info(f"Crew object of type: {type(crew).__name__} created.")
            logger.info("Calling kickoff on crew.")
            result = crew.kickoff()

            logger.info("Formatting Slack summary using AI.")
            summary = format_slack_summary_with_ai_per_customer(crew.tasks, self.table_id)

            logger.info("Creating Slack tool and posting summary.")
            slack_tool = make_post_to_slack_tool(self.slack_webhook_url)
            slack_tool.invoke({"summary": summary})

            logger.info("Slack message posted successfully.")
            return {
                "status": "success",
                "slack_message": summary,
                "result": str(result),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error during data analysis: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

            return {
                "status": "error",
                "error": str(e),
                "error_type": e.__class__.__name__,
                "timestamp": datetime.now().isoformat(),
            }

def get_status(status: str) -> Dict[str, Any]:
    """
    Get the current status of the service.
    """
    return {"status": status, "timestamp": datetime.now().isoformat()}