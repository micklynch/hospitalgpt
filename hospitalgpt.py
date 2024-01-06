from autogen import AssistantAgent, UserProxyAgent, config_list_from_json

openai_config_list = config_list_from_json(
    "OAI_CONFIG_LIST",
    filter_dict={
        "model": ["gpt-4-1106-preview"],
    },
)

mixtral_config_list = config_list_from_json(
    "OAI_CONFIG_LIST",
    filter_dict={
        "model": ["mistralai/Mixtral-8x7B-Instruct-v0.1"],
    },
)

assistant = AssistantAgent("assistant", llm_config={"config_list": openai_config_list})
user_proxy = UserProxyAgent("user_proxy")
user_proxy.initiate_chat(assistant, message="What model are you using?")