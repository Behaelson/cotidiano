import pyautogui as pag, time, sys

# Método para pegar um link do Google Spreadsheets que direciona ao google Imagens, e, então, abre a imagem em 
# uma nova aba e, retorna a planilha, seguindo o loop

pag.moveTo(1200,400)
x=92
while x > 0:
    time.sleep(1)
    pag.hotkey('alt', 'enter')
    time.sleep(2)
    pag.moveTo(120, 450)
    time.sleep(5)
    pag.rightClick()
    pag.moveTo(140, 470)
    time.sleep(1)
    pag.click()
    pag.hotkey('ctrl', 'w')
    time.sleep(1)
    pag.hotkey('ctrl', '1')
    time.sleep(1)
    pag.hotkey('down')
    time.sleep(1)
    x -= 1