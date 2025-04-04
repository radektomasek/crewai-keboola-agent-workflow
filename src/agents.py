from crewai import Agent
from crewai.project import agent
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4-turbo", temperature=0)

@agent
def analytics_agent() -> Agent:
    return Agent(
        role="Data Analyst",
        goal="Perform accurate calculations and insights from Keboola usage data",
        backstory=(
            "Expert data analyst with extensive experience in processing CSV data, "
            "calculating summaries, and generating accurate metrics. You always verify "
            "your calculations by double-checking your work and processing the entire dataset, "
            "not just samples. You pay close attention to column names, data types, and "
            "handle missing or empty values appropriately."
        ),
        tools=[],
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )



