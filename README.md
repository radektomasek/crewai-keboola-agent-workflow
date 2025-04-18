# Keboola Insights Crew

A CrewAI-based solution for analyzing Keboola usage data and sending reports to Slack.

## Key Changes in this Refactored Version

1. **External Data Download**: The CSV file is now downloaded separately (outside of AI) and passed as an input to avoid AI hallucination/modification of the input file.
2. **Improved Formatting**: The Slack report now has better spacing between companies for improved readability.

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Set up the required environment variables in a `.env` file:
```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
OPENAI_API_KEY=your_openai_api_key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

## Usage

### 1. Download the Data Separately

First, download your Keboola data using the Keboola Storage API or Keboola Connection UI. Save the data as a CSV file.

### 2. Run the Analysis

Use the following command to run the analysis with your pre-downloaded CSV file:

```bash
python -m simple_extract_calculation_notification.main --csv-file /path/to/your/data.csv --table-id your.table.id
```

Arguments:
- `--csv-file`: Path to the pre-downloaded CSV file (required)
- `--table-id`: Keboola table ID for reference in reports (default: "in.c-usage.usage_data")

## Structure

- `crew.py`: Defines the CrewAI crew and agents
- `tools.py`: Contains the SlackPostTool for sending reports to Slack
- `main.py`: Main entry point, handles loading the CSV file and starting the crew
- `config/tasks.yaml`: Defines the tasks for the crew
- `config/agents.yaml`: Defines the agent configuration

## Tasks Flow

1. `process_data_task`: Verifies the CSV data has been loaded correctly
2. `calculate_billed_credits_task`: Calculates total billed credits per company
3. `calculate_error_rate_task`: Calculates average error rate per company
4. `generate_usage_summary_task`: Combines the results into a summary report
5. `slack_posting_task`: Formats and posts the report to Slack

## Report Format

The Slack report will be formatted as follows:

```
Here is the summary of the Keboola Usage Report for `Table your.table.id`:

- Company A:
	• Total Billed Credits: 123.45
	• Error Rate: 0.0123

- Company B:
	• Total Billed Credits: 678.90
	• Error Rate: 0.0456
```
