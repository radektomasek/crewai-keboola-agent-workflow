import logging
from datetime import datetime
from typing import Dict, Any

from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from langchain_openai import ChatOpenAI
from tools import download_keboola_table, make_post_to_slack_tool
from utils import format_slack_summary_with_ai_per_customer

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
        crew = Crew(
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
        return crew

    def run_pipeline_and_post_to_slack(self):
        """Run the analytics pipeline and post results to Slack."""
        try:
            crew = self.analytics_pipeline_crew()
            result = crew.kickoff()

            summary = format_slack_summary_with_ai_per_customer(crew.tasks, self.table_id)

            slack_tool = make_post_to_slack_tool(self.slack_webhook_url)
            slack_tool.invoke({"summary": summary})

            return {
                "status": "success",
                "slack_message": summary,
                "result": str(result),
            }
        except Exception as e:
            import traceback
            print(f"Error in run_pipeline_and_post_to_slack: {str(e)}")
            traceback.print_exc()

            return {
                "status": "error",
                "message": str(e),
            }

def get_status() -> Dict[str, Any]:
    """
    Get the current status of the service.
    """
    return {"status": "running", "timestamp": datetime.now().isoformat()}