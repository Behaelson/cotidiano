from dash import Dash, html, dcc, Input, Output

# Caminho para a pasta de assets (CSS)
path = "C:\\Users\\Admin\\Documents\\assets" # Meu caminho

# Dá o Start no Dash
app = Dash(__name__, assets_folder=path)

# Layout da página [HTML]
    # ClassName = "nome-da-classe" -> Para aplicar o CSS
    # Children = "conteúdo" -> Para colocar o conteúdo dentro do elemento HTML

app.layout = html.Div(className='main-container', children=[
    
    html.Header(className='header', children=[
        html.H1("Python + HTML/CSS = DASH"),        # H1 = Título principal
        html.P("Dash é uma biblioteca/framework " \
        "muito útil para códigos integrados")       # P = Parágrafo
    ]),                                             # \ = Quebra de linha

    html.Div(className='content-card', children=[
        html.H2("Bem-vindo!"),
        html.P("Este é um exemplo de como a biblioteca Dash" \
        " utiliza componentes Python para gerar HTML."),
        
        dcc.Input(
            id='input-nome', 
            type='text', 
            placeholder='Digite seu nome...', 
            className='custom-input'
            ),
        html.Div(id='output-saudacao', className='output-text')
    ])
])

# Callback para acionar a interatividade
@app.callback(
    Output('output-saudacao', 'children'),  # Vai ser atualizado
    Input('input-nome', 'value')            # Aciona a atualização
)

def atualizar_saudacao(valor):
    if valor:
        return f"Ei, {valor}! Já se inscreveu no Processo Seletivo da for_code?"
    return "Aguardando seu nome..."

if __name__ == '__main__':
    app.run(debug=True)