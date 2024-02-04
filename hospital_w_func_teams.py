from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager, config_list_from_json
import requests
import datetime
from dateutil.relativedelta import relativedelta
from typing import List, Optional, Dict, Union
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# Here is the OpenAI details that will be used for the group chat. We use GPT-4 as you need 
# a powerful model to handle a complex conversation
openai_config_list = config_list_from_json(
    "OAI_CONFIG_LIST",
    filter_dict={
        "model": ["gpt-4"],
    },
)

# Here is the Mixtral details that will be used for generating the emails to users. 
# We use Mixtral as it is much cheaper and can easily handle the task of writing an email.
openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.deepinfra.com/v1/openai",
)

# This is where we store the list of patient details that are
# returned from the FHIR server. We use this list when generating outreach emails
patients = []


"""
STEP 1: 
Define the cohort criteria. This involves a group chat between the admin and the epidemiologist.
We also include a critic who will review the criteria and ensure it meets the required fields.
"""
def define_cohort_information(target_cohort) -> str:
    gpt4_config_define = {
        "cache_seed": 42,  # change the cache_seed for different trials
        "temperature": 0,
        "config_list": openai_config_list,
        "timeout": 120,
    }

    user_proxy = UserProxyAgent(
        name="Admin",
        max_consecutive_auto_reply=3,
        is_termination_msg=lambda x: x.get("content", "") and x.get(
            "content", "").rstrip().endswith("TERMINATE"),
        human_input_mode="TERMINATE",
    )

    critic = AssistantAgent(
        name="Critic",
        system_message="""
        Critic. I will review the criteria defined by the epidemiologist and ensure it meets the required fields.
        The required fields min age, max age and previous conditions.
        You must add TERMINATE to the end of your reply.
        """,
        llm_config=gpt4_config_define,
    )

    epidemiologist = AssistantAgent(
        name="epidemiologist",
        system_message="""
        Epidemiologist. You are an expert in the healthcare system. You define the criteria to target patients
        for outreach. The criteria must be min age, max age and any previous conditions. The conditions must be
        in the format of snowmed display names e.g. Osteoporsis (Disorder), Acute bronchitis, Hyperglycemia.
        
        You must add TERMINATE to the end of your reply.

        Examples:
        - Patients aged 50 to 70 with Osteoporsis. TERMINATE
        - Male patients aged between 100 and 120 with Myocardial disease. TERMINATE
        - Patients aged between 80 and 100 with Acute bronchitis. TERMINATE
        """,
        llm_config=gpt4_config_define,
    )


    # Create groupchat
    groupchat = GroupChat(
        agents=[user_proxy, epidemiologist, critic], messages=[])
    manager = GroupChatManager(groupchat=groupchat, llm_config=gpt4_config_define)


    user_proxy.initiate_chat(
        manager,
        message=target_cohort,
    )

    user_proxy.stop_reply_at_receive(manager)
    user_proxy.send(
        "Give me criteria that was just defined again, return only the criteria and add TERMINATE to the end of the message", manager)
    
    return user_proxy.last_message()["content"]

"""
STEP 2: 
Once the definition of the cohort criteria is complete, we can start the data analysis. This
involves using a defined function to search for patients within a FHIR R4 API server.
"""
def find_patients(criteria: str) -> None:
    gpt4_config_data = {
    "cache_seed": 42,  # change the cache_seed for different trials
    "temperature": 0,
    "functions": [
        {
            "name": "get_patients_between_ages_and_condition",
            "description":     '''
            Fetches and returns a list of patients from a specified FHIR R4 API endpoint based on the patients' age range and condition.
            
            Returns:
            An array of dictionary where each dictionary represents a patient and contains the patient's full name, age, MRN, email address, and condition.

            Example usage:
            >>> get_patients_between_ages_and_condition(50, 70, "Myocardial")
            This will return all patients who are between the ages of 50 and 70 (inclusive) and who have a condition with the name containing 'Myocardial'.
            ''',
            "parameters": {
                    "type": "object",
                    "properties": {
                        "min_age": {
                            "type": "number",
                            "description": "The minimum age to filter patients by. It returns only patients older than or equal to this age.",
                        },
                        "max_age": {
                            "type": "number",
                            "description": "The maximum age to filter patients by. It returns only patients younger than this age.",
                        },
                        "condition": {
                            "type": "string",
                            "description": "The specific health condition to filter patients by. It returns only patients who have this condition.",
                        }
                    },
                "required": ["min_age, max_age, condition"],
            },
        }
    ],
    "config_list": openai_config_list,
    "timeout": 120,
}
    user_proxy = UserProxyAgent(
        name="User_proxy",
        max_consecutive_auto_reply=3,
        code_execution_config={"last_n_messages": 2, "work_dir": "coding", "use_docker": False},
        is_termination_msg=lambda x: x.get("content", "") and x.get(
                "content", "").rstrip().endswith("TERMINATE"),
        human_input_mode="TERMINATE",
        function_map={
                "get_patients_between_ages_and_condition": get_patients_between_ages_and_condition,
        },
        )


    data_analyst = AssistantAgent(
        name="data_analyst",
        system_message="""
        Data analyst. Only use the function you have been provided with. Find all the
        patients that match the defined criteria. 
        You must add TERMINATE to the end of your reply.
        """,
        llm_config=gpt4_config_data,
    )

    #user_proxy.initiate_chat(
    #   data_analyst, message=f"{cohort_definition}")

    ## Injecting in some text in order to find an actual patient to match the criteria
    user_proxy.initiate_chat(
    data_analyst, message=f"patients aged between 100 and 105 with Hyperglycemia")

    return

"""
STEP 2.1: 
This is a helper function to get the patient details from a FHIR R4 API server based
on the patient's birthdate and the condition name.
This function is used by the data analyst.
"""
def get_patients_between_ages_and_condition(min_age: int, max_age: int, condition: str) -> List[Dict[str, Union[str, int, None]]]:
    today = datetime.date.today()
    max_birthdate = today - relativedelta(years=min_age)
    max_birthdate = max_birthdate.strftime('%Y-%m-%d')

    min_birthdate = today - relativedelta(years=max_age + 1)
    min_birthdate = min_birthdate.strftime('%Y-%m-%d')

    # Get conditions
    r = requests.get(f'https://hapi.fhir.org/baseR4/Condition?_pretty=true&subject.birthdate=le{max_birthdate}&subject.birthdate=gt{min_birthdate}')
    conditions = r.json()
        
    # Check if conditions is empty
    if 'entry' not in conditions or not conditions['entry']:
        # Handle the empty conditions case, you can return an empty list or raise an exception
        return "No patients match the given criteria"
    
    # Filter out the conditions where the 'code' key does not exist
    entries = [entry for entry in conditions['entry'] if 'code' in entry['resource']]
    # Filter by condition
    filtered_conditions = [entry for entry in entries
        if any(condition.lower() in cond['display'].lower() for cond in entry['resource']['code']['coding'])]
    # Get patient data for each condition
    for cond in filtered_conditions:
      patient_id = cond['resource']['subject']['reference'].split('/')[1]
      r = requests.get(f'https://hapi.fhir.org/baseR4/Patient/{patient_id}?_pretty=true')
      patient = r.json()

      if 'telecom' in patient and 'maritalStatus' in patient:
          full_name = patient['name'][0]['given'][0] + " " + patient['name'][0]['family']
          email = next((t['value'] for t in patient['telecom'] if t['system'] == 'email'), "test@test.com")

          # Check for 'type' key in each identifier before accessing its value
          mrn = next((i['value'] for i in patient['identifier'] if 'type' in i and i['type']['text'] == 'Medical Record Number'), None)
          patient_age = relativedelta(datetime.datetime.now(), datetime.datetime.strptime(patient['birthDate'], '%Y-%m-%d')).years
          patient_condition = cond['resource']['code']['coding'][0]['display']
          # Get postal code
          postal_code = patient['address'][0]['postalCode'] if 'address' in patient and patient['address'] else None

          patients.append(
              {
                  'patient_url': f"https://hapi.fhir.org/baseR4/Patient/{patient_id}?_pretty=true",
                  'full_name': full_name,
                  'age': patient_age,
                  'postal_code': postal_code,
                  'MRN': mrn,
                  'email': email,
                  'condition': patient_condition
              }
          )
    return patients

"""
STEP 3: 
This is a function which generates the emails for the patients.
"""
def write_outreach_emails(patient_details: List, user_proposal: str) -> None:
    MODEL_DI = "mistralai/Mixtral-8x7B-Instruct-v0.1"
    # Check if patient_details has any values before continuing
    if not patient_details:
        print("No patients found")
        return
    for patient in patient_details:
        chat_completion = openai_client.chat.completions.create(
            model=MODEL_DI,
            messages=[{"role": "user", "content": "Write an email to the patient named " + patient["full_name"] + 
                       " to arrange a screening based on the following  " +user_proposal+ 
                       "because they have previously had " + patient["condition"] + "."}],
            stream=False,
            # top_p=0.5,
        )

        # Write each individuals email into a text file. Call the file with the patient MRN and add the name, MRN, postcode and email
        # address into the start of the text file
        with open(f"{patient['MRN']}.txt", "w") as f:
            f.write(f"Name: {patient['full_name']}\n")
            f.write(f"MRN: {patient['MRN']}\n")
            f.write(f"Postcode: {patient['postal_code']}\n")
            f.write(f"Email: {patient['email']}\n")
            f.write("\n")
            f.write(f"Patient: {patient['patient_url']}\n")
            f.write(chat_completion.choices[0].message.content)
            f.write("\n")
            f.write("-----------------------------------------")
            

        
        
    return


# Define the diagnostic screening we wish to perform
user_proposal = "Find patients for colonoscopy screening"
# Define the cohort information based on the user's proposal
criteria_definition = define_cohort_information(user_proposal)
# Find the patients based on the criteria
find_patients(criteria_definition)
# Write the emails to the patients
write_outreach_emails(patients, user_proposal)
