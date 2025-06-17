import pandas as pd

# 1) Читаем файл. Для .xls нужен xlrd (pip install xlrd).
df = pd.read_excel('gg.xlsx')

df_cleaned = df.dropna(subset=['price'])

# Сохраняем в CSV
df_cleaned.to_csv("products.csv", index=False)

# # 2) Переименуем колонки для удобства
# df = df.rename(columns={
#     df.columns[0]: 'name1',  # столбец A
#     df.columns[1]: 'price1', # столбец B
#     df.columns[3]: 'name2',  # столбец D
#     df.columns[4]: 'price2', # столбец E
# })
#
# # 3) Заполняем объединённые ячейки в колонках name1 и name2
# df[['name1', 'name2']] = df[['name1', 'name2']].ffill()
#
# # 4) Собираем два списка и приводим к единой форме
# items1 = df[['name1', 'price1']].rename(columns={'name1': 'name', 'price1': 'price'})
# items2 = df[['name2', 'price2']].rename(columns={'name2': 'name', 'price2': 'price'})
#
# # 5) Конкатенируем, удаляем пустые и сбрасываем индексы
# result = pd.concat([items1, items2], ignore_index=True)
# result = result.dropna(subset=['name', 'price']).reset_index(drop=True)

# 6) Сохраняем в новый файл
# result.to_csv('merged_products.csv', index=False)
