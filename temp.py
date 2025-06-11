# # test_gpt.py
#
# import openai
# from openai import OpenAI
# from config import OPENAI_API_KEY
#
# client = OpenAI(api_key=OPENAI_API_KEY)
#
# response = client.chat.completions.create(
#     model="gpt-3.5-turbo",
#     messages=[
#         {"role": "system", "content": "Скажи «Привет»"},
#         {"role": "user",   "content": "Проверка"}
#     ],
#     max_tokens=10
# )
#
# print(response.output_text)
from utils import HistoryManager

HistoryManager()