import pandas as pd

Tabela0 = {
    'Roupa': ['Camisa coquete', 'Short beira cu', 'Saia plissada'],
    'Preço': ['15,00', '10,00', '20,00']
}
df = pd.DataFrame(Tabela0)
a = df.sum('Preço')
print(df, a)