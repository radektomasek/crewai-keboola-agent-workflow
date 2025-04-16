#!/usr/bin/env python
import argparse
import warnings
from dotenv import load_dotenv
from .crew import KeboolaInsightsCrew

load_dotenv()

warnings.filterwarnings('ignore', category=SyntaxWarning, module="pysbd")

def run():
    """
    Run the Keboola Insights Crew with command line arguments for table ID.
    """
    parser = argparse.ArgumentParser(description='Run Keboola Insights Crew analysis')
    parser.add_argument(
        '--table-id',
        type=str,
        default="in.c-usage.usage_data",
        help='Keboola table ID to analyze (default: in.c-usage.usage_data)'
    )

    args = parser.parse_args()

    inputs = {
        "kbc_table_id": args.table_id
    }

    try:
        print(f"Starting data analysis for Keboola table: {args.table_id}")
        crew_result = KeboolaInsightsCrew().crew().kickoff(inputs=inputs)
        print("Analysis completed successfully")
        print("\n\n########################")
        print("## Analysis Report")
        print("########################\n")
        print(f"Final Results: {crew_result}")
        return crew_result
    except Exception as e:
        print(f"An error occurred while running the crew: {e}")
        raise

if __name__ == "__main__":
    print("## Welcome to Keboola Insights Crew")
    print('-------------------------------------')
    run()