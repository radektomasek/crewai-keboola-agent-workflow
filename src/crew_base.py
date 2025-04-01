from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from src.agents import keboola_reader_agent, analytics_agent, slack_notifier_agent
from src.tasks import read_keboola_data_task, calculate_billed_credits_task, calculate_error_rate_task, \
    send_results_to_slack_task


@CrewBase
class KeboolaInsightsCrew():
    def __init__(self, inputs):
        self.inputs = inputs or {}
        self.table_id = self.inputs.get("table_id")

        if not self.table_id:
            raise ValueError("Missing required input: table_id")

        from src.utils import download_keboola_table
        self.df = download_keboola_table(self.table_id)  # <-- DataFrame stored here


    @crew
    def analytics_pipeline_crew(self) -> Crew:
        if self.df is None or self.df.empty:
            raise RuntimeError("Could not download data or table is empty.")

        read_data_task = read_keboola_data_task(self.table_id)

        # Pass no arguments to the tasks (they can access self.df directly)
        billed_credits_task = calculate_billed_credits_task()
        error_rate_task = calculate_error_rate_task()

        analytics_summary = (
            f"Keboola Usage Report for Table `{self.table_id}`\n"
            "- Total Billed Credits: [insert result from billed_credits_task]\n"
            "- Error Rate: [insert result from error_rate_task]\n"
        )

        slack_task = send_results_to_slack_task(analytics_summary)

        return Crew(
            agents=[
                keboola_reader_agent(),
                analytics_agent(),
                slack_notifier_agent()
            ],
            tasks=[
                read_data_task,
                billed_credits_task,
                error_rate_task,
                slack_task
            ],
            process=Process.sequential,
            verbose=True
        )