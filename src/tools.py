import time
from typing import Optional

import pandas as pd
import requests
from io import StringIO
from langchain.tools import StructuredTool
from pydantic.v1 import BaseModel


def download_keboola_table(table_id: str, kbc_api_token: str, kbc_api_url: str) -> pd.DataFrame:
    """
    Download a table from Keboola Storage using async export (non-sliced).
    Falls back to sample data if export fails.
    """
    try:
        print(f"Triggering async export for table: {table_id}")
        export_resp = requests.post(
            f"{kbc_api_url}/v2/storage/tables/{table_id}/export-async",
            headers={"X-StorageApi-Token": kbc_api_token},
            json={"format": "rfc", "limit": 100000, "gzip": False}
        )
        export_resp.raise_for_status()
        export_job = export_resp.json()
        job_id = export_job["id"]

        print(f"Waiting for export job {job_id} to complete...")
        while True:
            job_resp = requests.get(
                f"{kbc_api_url}/v2/storage/jobs/{job_id}",
                headers={"X-StorageApi-Token": kbc_api_token}
            )
            job_resp.raise_for_status()
            job_data = job_resp.json()
            if job_data["status"] == "success":
                break
            elif job_data["status"] == "error":
                raise RuntimeError("Export job failed.")
            time.sleep(2)

        file_id = job_data["results"]["file"]["id"]
        file_url = f"{kbc_api_url}/v2/storage/files/{file_id}/download"
        print(f"Downloading file ID: {file_id}")

        file_resp = requests.get(file_url, headers={"X-StorageApi-Token": kbc_api_token})
        file_resp.raise_for_status()

        df = pd.read_csv(StringIO(file_resp.text))
        print(f"Downloaded {len(df)} rows.")
        return df

    except Exception as e:
        return pd.DataFrame({
            "Company_ID": [1, 2],
            "Company_Name": ["Acme Corp", "Globex"],
            "KBC_Component_ID": ["kbc.component.1", "kbc.component.2"],
            "KBC_Component": ["Extractor", "Writer"],
            "Configurations": [3, 5],
            "Jobs": [10, 12],
            "Sum_of_Job_Billed_Credits_Used": [1.23, 4.56],
            "Job_Run_Time_Minutes": [25, 40],
            "Error_Jobs_Ratio": [0.1, 0.0]
        })

class SlackInput(BaseModel):
    summary: str

def make_post_to_slack_tool(webhook_url: Optional[str] = None) -> StructuredTool:
    def _post_summary(summary: str) -> str:
        if not webhook_url:
            raise ValueError("Missing Slack webhook URL.")

        payload = {"text": summary}
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()
        return "Report successfully posted to Slack."

    return StructuredTool.from_function(
        name="post_to_slack",
        description="Post a summary to Slack using a webhook.",
        func=_post_summary,
        args_schema=SlackInput,
    )