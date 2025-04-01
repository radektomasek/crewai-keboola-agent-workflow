import os
import time
import pandas as pd
import requests
from io import StringIO

def download_keboola_table(table_id: str) -> pd.DataFrame:
    """
    Download a table from Keboola Storage using async export (non-sliced).
    Falls back to sample data if export fails.
    """
    token = os.getenv("KBC_API_TOKEN")
    api_url = os.getenv("KBC_API_URL", "https://connection.keboola.com")

    print(f"🔍 KBC_API_URL: {api_url}")
    print(f"🔍 KBC_TABLE_ID: {table_id}")
    print(f"🔐 Token (first 7 chars): {token[:7] if token else 'missing'}")

    try:
        print(f"Triggering async export for table: {table_id}")
        export_resp = requests.post(
            f"{api_url}/v2/storage/tables/{table_id}/export-async",
            headers={"X-StorageApi-Token": token},
            json={"format": "rfc", "limit": 100000, "gzip": False}
        )
        export_resp.raise_for_status()
        export_job = export_resp.json()
        job_id = export_job["id"]

        print(f"Waiting for export job {job_id} to complete...")
        while True:
            job_resp = requests.get(
                f"{api_url}/v2/storage/jobs/{job_id}",
                headers={"X-StorageApi-Token": token}
            )
            job_resp.raise_for_status()
            job_data = job_resp.json()
            if job_data["status"] == "success":
                break
            elif job_data["status"] == "error":
                raise RuntimeError("❌ Export job failed.")
            time.sleep(2)

        file_id = job_data["results"]["file"]["id"]
        file_url = f"{api_url}/v2/storage/files/{file_id}/download"
        print(f"Downloading file ID: {file_id}")

        file_resp = requests.get(file_url, headers={"X-StorageApi-Token": token})
        file_resp.raise_for_status()

        df = pd.read_csv(StringIO(file_resp.text))
        print(f"Downloaded {len(df)} rows.")
        return df

    except Exception as e:
        print(f"Error downloading table: {e}")
        print("Using sample fallback data.")
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


def post_to_slack(message: str):
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not slack_webhook:
        raise EnvironmentError("Missing SLACK_WEBHOOK_URL")

    response = requests.post(slack_webhook, json={"text": message})
    response.raise_for_status()