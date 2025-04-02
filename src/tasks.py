from crewai import Task, Agent
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
        description=(
            "Calculate the total billed credits from the Keboola usage data. "
            "Use the most appropriate column, such as 'amount', 'usage_amount', or similar. "
            "If the data contains multiple types of usage (e.g., API Calls, Storage Usage), sum all of them. "
            "If no numeric usage data is found, respond with 'Unable to calculate billed credits'."
        ),
        expected_output="Total billed credits used, or a clear explanation if calculation is not possible.",
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
def send_results_to_slack_task(table_id: str) -> Task:
    return Task(
        description=(
            f"Generate a Slack message summary for table `{table_id}`.\n\n"
            f"Use results from:\n"
            f"- calculate_billed_credits_task\n"
            f"- calculate_error_rate_task"
        ),
        expected_output="A string message ready to be posted to Slack.",
        agent=slack_notifier_agent(),
        context=[
            calculate_billed_credits_task(),
            calculate_error_rate_task(),
        ],
        human_input=False,
    )