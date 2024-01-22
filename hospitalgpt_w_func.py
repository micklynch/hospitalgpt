from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager, config_list_from_json
import requests
import datetime
from dateutil.relativedelta import relativedelta
from typing import List, Optional, Dict, Union


openai_config_list = config_list_from_json(
    "OAI_CONFIG_LIST",
    filter_dict={
        "model": ["gpt-4-0613"],
    },
)

gpt4_config = {
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


def get_patients_between_ages_and_condition(min_age: int, max_age: int, condition: str) -> List[Dict[str, Union[str, int, None]]]:
    today = datetime.date.today()
    max_birthdate = today - relativedelta(years=min_age)
    max_birthdate = max_birthdate.strftime('%Y-%m-%d')

    min_birthdate = today - relativedelta(years=max_age + 1)
    min_birthdate = min_birthdate.strftime('%Y-%m-%d')
    
    # Get conditions
    r = requests.get(f'https://hapi.fhir.org/baseR4/Condition?_pretty=true&subject.birthdate=le{max_birthdate}&subject.birthdate=gt{min_birthdate}')
    conditions = r.json()
    # Filter out the conditions where the 'code' key does not exist
    entries = [entry for entry in conditions['entry'] if 'code' in entry['resource']]
    # Filter by condition
    filtered_conditions = [entry for entry in entries
        if any(condition.lower() in cond['display'].lower() for cond in entry['resource']['code']['coding'])]
    patients = []
    # Get patient data for each condition
    for cond in filtered_conditions:
      patient_id = cond['resource']['subject']['reference'].split('/')[1]
      r = requests.get(f'https://hapi.fhir.org/baseR4/Patient/{patient_id}?_pretty=true')
      patient = r.json()
      
      if 'telecom' in patient and 'maritalStatus' in patient:
          full_name = patient['name'][0]['given'][0] + " " + patient['name'][0]['family']
          email = next((t['value'] for t in patient['telecom'] if t['system'] == 'email'), None)

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


user_proxy = UserProxyAgent(
    name="User_proxy",
    human_input_mode="TERMINATE",
    code_execution_config={"last_n_messages": 2, "work_dir": "coding", "use_docker": False},
    function_map={
            "get_patients_between_ages_and_condition": get_patients_between_ages_and_condition,
    },
)
data_analyst = AssistantAgent(
    name="data_analyst",
    system_message="""
    Data analyst.  Only use the functions you have been provided with. Reply TERMINATE when the task is done.",
    """,
    llm_config=gpt4_config,
)


user_proxy.initiate_chat(
    data_analyst, message="Find all the patients aged between 100 and 105 with Hyperglycemia")

