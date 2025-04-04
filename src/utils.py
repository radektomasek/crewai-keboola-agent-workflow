import json
import re
from typing import List, Dict

from langchain_openai import ChatOpenAI

def extract_metrics_with_ai_per_customer(tasks, llm) -> List[Dict[str, str]]:
    """
    Extract per-customer metrics from task outputs using AI.

    Args:
        tasks: List of CrewAI task objects
        llm: LLM instance for interpretation

    Returns:
        List of dicts with structure: [{ "company": ..., "billed_credits": ..., "error_rate": ... }]
    """
    all_outputs = []
    for task in tasks:
        if hasattr(task, 'output') and task.output:
            all_outputs.append(str(task.output))

    if not all_outputs:
        return []

    full_output = "\n".join(all_outputs)

    prompt = f"""
You are given task outputs from different analytics tasks. Each line represents a customer and their metric:

{full_output}

Your job is to extract the company name, total billed credits, and error rate for each customer.
Return the result in **valid JSON array** like this:

[
  {{
    "company": "Customer 01",
    "billed_credits": "1018.89",
    "error_rate": "0.0308"
  }},
  ...
]

If any value is missing, use "N/A".
Only include companies with at least one known value.
Do not explain anything. Only return valid JSON array.
"""

    try:
        response = llm.invoke(prompt)

        response_text = response.content if hasattr(response, "content") else str(response)

        json_match = re.search(r'\[\s*\{.*?\}\s*\]', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))

        print("No valid JSON detected.")
        return []

    except Exception as e:
        print(f"Failed to extract per-customer metrics: {e}")
        return []

def format_slack_summary_with_ai_per_customer(tasks, table_id: str, llm=None) -> str:
    """
    Use AI to format a Slack summary with per-customer metrics.

    Args:
        tasks: CrewAI task objects
        table_id: Source table
        llm: LLM instance

    Returns:
        Formatted string for Slack
    """
    if llm is None:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    customers = extract_metrics_with_ai_per_customer(tasks, llm)

    if not customers:
        return f"No usable data found for table `{table_id}`."

    lines = [f"Here is the summary of the Keboola Usage Report for Table `{table_id}`:\n"]
    for customer in customers:
        line = (
            f"- *{customer['company']}*:\n"
            f"  • Total Billed Credits: {customer['billed_credits']}\n"
            f"  • Error Rate: {customer['error_rate']}\n"
        )
        lines.append(line)

    lines.append("\nThe report has been successfully posted to the Slack channel.")
    return "\n".join(lines)