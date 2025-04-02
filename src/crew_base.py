import re
from crewai import Agent, Crew, Process, Task
from crewai.crews import CrewOutput
from crewai.project import CrewBase, agent, crew, task
from langchain_openai import ChatOpenAI
from src.tools import download_keboola_table, make_post_to_slack_tool
from src.tasks import (
    read_keboola_data_task,
    calculate_billed_credits_task,
    calculate_error_rate_task,
)

import logging

logger = logging.getLogger(__name__)

def extract_number(text: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return match.group(0) if match else "N/A"

def format_slack_summary(result, table_id: str) -> str:
    billed_credits = "N/A"
    error_rate = "N/A"

    for output in result.tasks_output:
        print("DEBUG TASK OUTPUT:")
        print("  description:", getattr(output, "description", None))
        print("  output:", getattr(output, "output", None))

        description = getattr(output, "description", "").lower()
        content = getattr(output, "output", "")

        if "billed credits" in description:
            billed_credits = extract_number(content)
        elif "error rate" in description:
            error_rate = extract_number(content)

    return (
        f"Here is the summary of the Keboola Usage Report for Table `{table_id}`:\n\n"
        f"- Total Billed Credits: {billed_credits}\n"
        f"- Error Rate: {error_rate}\n\n"
        f"The report has been successfully posted to the Slack channel."
    )

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
    def keboola_reader_agent(self) -> Agent:
        from src.agents import keboola_reader_agent
        return keboola_reader_agent()

    @agent
    def analytics_agent(self) -> Agent:
        from src.agents import analytics_agent
        return analytics_agent()

    @task
    def read_keboola_data_task(self) -> Task:
        return read_keboola_data_task(self.table_id)

    @task
    def calculate_billed_credits_task(self) -> Task:
        return calculate_billed_credits_task()

    @task
    def calculate_error_rate_task(self) -> Task:
        return calculate_error_rate_task()

    @crew
    def analytics_pipeline_crew(self) -> Crew:
        crew = Crew(
            agents=[
                self.keboola_reader_agent(),
                self.analytics_agent(),
            ],
            tasks=[
                self.read_keboola_data_task(),
                self.calculate_billed_credits_task(),
                self.calculate_error_rate_task(),
            ],
            process=Process.sequential,
            verbose=True,
        )
        return crew

    def run_pipeline_and_post_to_slack(self):
        crew = self.analytics_pipeline_crew()
        result = crew.kickoff()

        summary = format_slack_summary(result, self.table_id)

        slack_tool = make_post_to_slack_tool(self.slack_webhook_url)
        slack_tool.invoke({"summary": summary})

        return {
            "status": "success",
            "slack_message": summary,
            "result": str(result),
        }
