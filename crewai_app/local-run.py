import os
from dotenv import load_dotenv
from main import KeboolaInsightsCrew

load_dotenv()

if __name__ == "__main__":
    load_dotenv()

    crew_inputs = {
        "table_id": os.getenv("KBC_TABLE_ID"),
        "slack_webhook_url": os.getenv("SLACK_WEBHOOK_URL"),
        "kbc_api_token": os.getenv("KBC_API_TOKEN"),
        "kbc_api_url": os.getenv("KBC_API_URL"),
    }

    crew = KeboolaInsightsCrew(inputs=crew_inputs)
    result = crew.analyze_data_with_no_approval()
