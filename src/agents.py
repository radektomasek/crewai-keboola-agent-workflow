from crewai import Agent
from crewai.project import agent
from langchain_openai import ChatOpenAI

@agent
def keboola_reader_agent() -> Agent:
    return Agent(
        role="Keboola Reader",
        goal="Download data from Keboola table for further analysis",
        backstory="You're a data integration agent who specializes in accessing and extracting structured data from the Keboola platform.",
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        verbose=True
    )

@agent
def analytics_agent() -> Agent:
    return Agent(
        role="Data Analyst",
        goal="Perform analytics on Keboola data",
        backstory="You're a data analyst who extracts insights from platform usage data.",
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        verbose=True,
    )

@agent
def slack_notifier_agent() -> Agent:
    return Agent(
        role="Slack Notifier",
        goal="Post key analytics insights to a Slack channel",
        backstory="You handle communication and send reports to stakeholders via Slack.",
        llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
        verbose=True,
    )