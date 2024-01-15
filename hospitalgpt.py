from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager, config_list_from_json

openai_config_list = config_list_from_json(
    "OAI_CONFIG_LIST",
    filter_dict={
        "model": ["gpt-4-0613"],
    },
)

mixtral_config_list = config_list_from_json(
    "OAI_CONFIG_LIST",
    filter_dict={
        "model": ["mistralai/Mixtral-8x7B-Instruct-v0.1"],
    },
)

gpt4_config = {
    "cache_seed": 42,  # change the cache_seed for different trials
    "temperature": 0,
    "config_list": openai_config_list,
    "timeout": 120,
}

mixtral_config = {
    "cache_seed": 42,  # change the cache_seed for different trials
    "temperature": 0,
    "config_list": mixtral_config_list,
    "timeout": 120,
}

user_proxy = UserProxyAgent(
   name="Admin",
   system_message="A human admin who will define the condition that the hospital planner needs to screen for",
    max_consecutive_auto_reply=15,
    is_termination_msg=lambda x: x.get("content", "").rstrip().endswith("TERMINATE"),
    code_execution_config={
        "work_dir": "groupchat",
        "use_docker": False,  # set to True or image name like "python:3" to use docker
    },
    human_input_mode="ALWAYS",
)

planner = AssistantAgent(
    name="hospital_planner",
    system_message="""
    Hospital administrator.

    Suggest a plan. Revise the plan based on feedback from admin and critic, until admin approval.
    The plan may involve an epidemiologist who defines the patient criteria to solve target outreach.
    The data analyst who can write code and an executor who will run the code to output a list of patients.
    An outreach assistant who can take the list of patients and write personalized messages to them.
    Explain the plan first. Be clear which step is performed by the epidemiologist, data analyst, executor
    and outreach admin.
    """,
    llm_config=gpt4_config,
)

epidemiologist = AssistantAgent(
    name="epidemiologist",
    system_message="""
    Epidemiologist. You are an expert in the healthcare system. You can help the planner to define which patients 
    that should receive outreach. Define the criteria based on their demographics, medications and past conditions. 
    When you have the criteria defined pass these onto the data analyst to write and execute code to search within
    a FHIR R4 API server for patients that match the criteria. 
    """,
    llm_config=gpt4_config,
)

data_analyst = AssistantAgent(
    name="data_analyst",
    system_message="""
    Data analyst. You are an expert in the healthcare data systems and FHIR standards. 

    You write python/shell code to find patients in a FHIR R4 API server that match the criteria defined by the epidemiologist.
    The FHIR API server URL is https://hapi.fhir.org/baseR4/.
    Wrap the code in a code block that specifies the script type. 
    The user can't modify your code. So do not suggest incomplete code which requires others to modify. 
    Don't use a code block if it's not intended to be executed by the executor.
    Don't include multiple code blocks in one response. Do not ask others to copy and paste the result. 
    Check the execution result returned by the executor.
    If the result indicates there is an error, fix the error and output the code again. 
    Suggest the full code instead of partial code or code changes. 
    If the error can't be fixed or if the task is not solved even after the code is executed successfully, 
    analyze the problem, revisit your assumption, collect additional info you need, and think of a different approach to try. 
    Save the output to a file called patients.csv.
    """,
    llm_config=gpt4_config,
)

executor = UserProxyAgent(
    name="Executor",
    system_message="""
        Executor. Execute the code written by the data analyst and report the result.
    """,
    human_input_mode="NEVER",
    code_execution_config={"last_n_messages": 3, "work_dir": "groupchat"},
)

outreach_admin = AssistantAgent(
    name="outreach_admin",
    system_message="""
    Outreach administrator. You are an expert in the healthcare system. You take the list of patients the patients.csv file and create a personalized 
    email to send to each patient. 
    You output a csv file called out.csv which contains the patient ids, names, email addresses and the text of the email you just created.
    """,
    llm_config=mixtral_config,
)

critic = AssistantAgent(
    name="Critic",
    system_message="""
    Critic. Double check plan, claims, code from other agents and provide feedback. 
    Check whether the plan includes adding verifiable info such as source URL.
    """,
    llm_config=gpt4_config,
)

# Create groupchat
groupchat = GroupChat(
    agents=[user_proxy, planner, epidemiologist, data_analyst, executor, outreach_admin, critic], messages=[])
manager = GroupChatManager(groupchat=groupchat, llm_config=gpt4_config)


user_proxy.initiate_chat(
    manager,
    message="""
    Contact all the patients that need a colonoscopy screening.
    """,
)