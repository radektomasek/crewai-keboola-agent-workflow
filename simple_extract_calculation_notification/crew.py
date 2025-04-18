import os

from crewai import Agent, Crew, Process, Task
from crewai.llm import LLM
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv
from .tools import KeboolaDownloadTool, SlackPostTool

load_dotenv()

@CrewBase
class KeboolaInsightsCrew:
    """KeboolaInsightsCrew crew"""

    def __init__(self, inputs=None):
        kbc_api_token = os.getenv("KBC_API_TOKEN")
        if not kbc_api_token:
            raise EnvironmentError("KBC_API_TOKEN not found in the environment variables")

        kbc_api_url = os.getenv("KBC_API_URL")
        if not kbc_api_url:
            raise EnvironmentError("KBC_API_URL not found in the environment variables")

        slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not slack_webhook_url:
            raise EnvironmentError("SLACK_WEBHOOK_URL not found in the environment variables")

        llm_api_key = os.getenv("OPENAI_API_KEY")
        if not llm_api_key:
            raise EnvironmentError("OPENAI_API_KEY not found in the environment variables")

        llm_base_url = os.getenv("OPENAI_API_BASE")
        if not llm_base_url:
            raise EnvironmentError("OPENAI_API_BASE not found in the environment variables")

        model = os.getenv("OPENAI_MODEL", "gpt-4o")

        self.kbc_api_token = kbc_api_token
        self.kbc_api_url = kbc_api_url
        self.slack_webhook_url = slack_webhook_url

        self.llm = LLM(
            model=model,
            temperature=0.2,
            api_key=llm_api_key,
            base_url=llm_base_url,
        )

        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.agents_config = os.path.join(current_dir, "config", "agents.yaml")
        self.tasks_config = os.path.join(current_dir, "config", "tasks.yaml")
        self.inputs = inputs or {}

    @agent
    def data_analyst(self) -> Agent:
        """Create the data analyst agent with tools"""
        download_tool = KeboolaDownloadTool(
            kbc_api_token=self.kbc_api_token,
            kbc_api_url=self.kbc_api_url
        )

        slack_tool = SlackPostTool(
            webhook_url=self.slack_webhook_url
        )

        return Agent(
            config=self.agents_config["data_analyst"],
            tools=[download_tool, slack_tool],
            verbose=True,
            llm=self.llm
        )

    @task
    def download_data_task(self) -> Task:
        """Task to download data from Keboola"""
        task_config = self.tasks_config["download_data_task"].copy()

        if "description" in task_config and self.inputs:
            task_config["description"] = task_config["description"].format(
                **self.inputs
            )

        return Task(
            config=task_config,
            agent=self.data_analyst()
        )

    @task
    def calculate_billed_credits_task(self) -> Task:
        """Task to calculate billed credits from the downloaded data"""
        task_config = self.tasks_config["calculate_billed_credits_task"].copy()

        return Task(
            config=task_config,
            agent=self.data_analyst()
        )

    @task
    def calculate_error_rate_task(self) -> Task:
        """Task to calculate error rate from the downloaded data"""
        task_config = self.tasks_config["calculate_error_rate_task"].copy()

        return Task(
            config=task_config,
            agent=self.data_analyst()
        )

    @task
    def generate_usage_summary_task(self) -> Task:
        """Task to generate a summary"""
        task_config = self.tasks_config["generate_usage_summary_task"].copy()

        return Task(
            config=task_config,
            agent=self.data_analyst()
        )

    @task
    def slack_posting_task(self) -> Task:
        """Task that ONLY posts a message to Slack. This must be run."""
        task_config = self.tasks_config["slack_posting_task"].copy()

        if "description" in task_config and self.inputs:
            task_config["description"] = task_config["description"].format(
                **self.inputs
            )

        return Task(
            config=task_config,
            agent=self.data_analyst()
        )

    @crew
    def crew(self) -> Crew:
        """Creates the KeboolaInsightsCrew crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            inputs=self.inputs,  # Updated to use inputs directly
            process=Process.sequential,
            chat_llm=self.llm,
            verbose=True,
        )