import pandas as pd
df = pd.read_parquet("processed_recipes.parquet")
print(df.head())
print(df.shape)
