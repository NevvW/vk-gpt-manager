import pandas as pd

def toCSV(file):
    df = pd.read_excel(file)

    df = df.rename(columns={
        df.columns[0]: 'name',
        df.columns[1]: 'description',
        df.columns[2]: 'price'
    })

    df = df[df['name'] != 'Наименование']
    df['price'] = df['price'].str.replace(r'-(?=\d+)', '.', regex=True)

    df_cleaned = df.dropna(subset=['price'])

    df_cleaned.to_csv("products.csv", index=False)
