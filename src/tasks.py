from crewai import Task
from crewai.project import task

from src.agents import keboola_reader_agent, analytics_agent, slack_notifier_agent


@task
def read_keboola_data_task(table_id: str) -> Task:
    return Task(
        description=f"Connect to Keboola Storage API and download the data from table ID `{table_id}`. Return the content as a structured table (e.g., CSV or DataFrame).",
        expected_output="A CSV or DataFrame representation of the downloaded table data.",
        agent=keboola_reader_agent(),
        human_input=False,
    )

@task
def calculate_billed_credits_task() -> Task:
    return Task(
        description="Calculate the total billed credits from the Keboola usage data.",
        expected_output="Total billed credits used.",
        agent=analytics_agent(),
        human_input=False,
    )

@task
def calculate_error_rate_task() -> Task:
    return Task(
        description="Calculate the error rate from the 'Error Jobs Ratio' column.",
        expected_output="A single numeric value representing the error rate.",
        agent=analytics_agent(),
        human_input=False,
    )

@task
def send_results_to_slack_task(analytics_summary: str) -> Task:
    return Task(
        description=f"Post the following summary to Slack:\n\n{analytics_summary}",
        expected_output="Slack message sent confirmation",
        agent=slack_notifier_agent(),
        human_input=False,
    )