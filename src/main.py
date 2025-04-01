import os
from dotenv import load_dotenv
from src.crew_base import KeboolaInsightsCrew

load_dotenv()

if __name__ == "__main__":
    load_dotenv()

    table_id = os.getenv("KBC_TABLE_ID")

    crew = KeboolaInsightsCrew(inputs={"table_id": table_id})
    result = crew.analytics_pipeline_crew().kickoff()

    print("\n Result: ")
    print(result)