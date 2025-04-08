from crewai import Task, Agent
from agents import analytics_agent

def calculate_billed_credits_task(df) -> Task:
    csv_data = df.to_csv(index=False)

    return Task(
        description=(
            "You are provided with Keboola usage data in CSV format.\n\n"
            "CSV Data:\n"
            f"```csv\n{csv_data}\n```\n\n"
            "Your task is to group this data by the 'Company_Name' column and calculate the **total billed credits** "
            "per company. You must:\n"
            "1. **Sum all numeric, non-empty values** in the 'Sum_of_Job_Billed_Credits_Used' column **for each company**.\n"
            "2. Do NOT calculate an average. Only calculate a total sum.\n"
            "3. Round each sum to exactly 2 decimal places.\n"
            "4. Present each result on a new line, in the following format:\n"
            "<Company Name> - Total Billed Credits: X.XX\n\n"
            "Only include companies with a valid numeric billed credits total. Do not include any explanation, commentary, or extra text. Return only the output in the specified format."
        ),
        expected_output="Lines like 'Company A - Total Billed Credits: 123.45'",
        agent=analytics_agent(),
        human_input=False,
    )

def calculate_error_rate_task(df) -> Task:
    csv_data = df.to_csv(index=False)

    return Task(
        description=(
            "You are provided with Keboola usage data in CSV format.\n\n"
            "CSV Data:\n"
            f"```csv\n{csv_data}\n```\n\n"
            "Group the data by the 'Company_Name' column and for each group:\n"
            "1. Calculate the average of all non-empty numeric values in the 'Error_Jobs_Ratio' column.\n"
            "2. Round the result to exactly 4 decimal places.\n"
            "3. Present the result in the following format (one line per company):\n"
            "<Company Name> - Error Rate: 0.XXXX\n"
            "Only include companies that have at least one numeric error ratio value.\n"
            "Do not add any commentary or explanation."
        ),
        expected_output="One line per company in '<Company Name> - Error Rate: 0.XXXX' format",
        agent=analytics_agent(),
        human_input=False,
    )

def generate_usage_summary_task(billed_output: str, error_output: str) -> Task:
    return Task(
        description=(
            "You are given grouped Keboola usage metrics from two previous calculations:\n\n"
            f"Billed Credits Output:\n{billed_output}\n\n"
            f"Error Rate Output:\n{error_output}\n\n"
            "Generate a summary report for Slack. For each company that appears in either list:\n"
            "- Include the company name\n"
            "- Include its total billed credits (X.XX) if available\n"
            "- Include its error rate (0.XXXX) if available\n\n"
            "Present the result in this format per company:\n"
            "Company: <Company Name>\n"
            "Total Billed Credits: X.XX\n"
            "Average Error Rate: 0.XXXX\n\n"
            "Only include companies that have at least one of the two values.\n"
            "Do not explain your process, just return the summary."
        ),
        expected_output="Formatted company summaries, ready for Slack",
        agent=analytics_agent(),
        human_input=False,
    )